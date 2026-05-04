from typing import List, Optional
from decimal import Decimal
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import ImportBatch, Transaction, BankAccount, User, CurrencyCode
from app.models.import_batch import ImportStatus
from app.schemas.import_file import (
    ColumnMapping,
    ImportPreview,
    ImportResult,
    ImportProcess,
    ImportBatchResponse,
    ImportAnalysis,
    UncertainRow,
    OverlapCheckResponse,
    TransactionPreviewRow,
    ImportTemplateSchema,
)
from app.services.import_service import ImportService
from app.models.import_template import ImportTemplate
from app.utils.security import get_current_active_user
from app.services.balance_log_service import log_balance_change

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=ImportPreview)
async def upload_file(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload de arquivo para importação.

    Retorna preview dos dados e mapeamento de colunas detectado.
    Se existe template salvo para a conta, usa o mapeamento do template.
    """
    import json
    service = ImportService(db)
    try:
        result = await service.upload_and_preview(file, account_id)

        # Verificar se existe template salvo para esta conta
        template = db.query(ImportTemplate).filter(
            ImportTemplate.account_id == account_id
        ).first()
        if template:
            saved_mapping = json.loads(template.column_mapping)
            # Validar que as colunas do template existem no arquivo
            available_cols = set(result.columns)
            template_mapping = ColumnMapping(**saved_mapping)
            required_ok = (
                template_mapping.date_column in available_cols
                and template_mapping.description_column in available_cols
            )
            if required_ok:
                result.detected_mapping = template_mapping
                result.has_template = True

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")


@router.post("/process", response_model=ImportResult)
async def process_import(
    data: ImportProcess,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Processar importação com mapeamento definido.

    - Valida dados
    - Detecta duplicatas
    - Categoriza automaticamente
    - Valida saldo (opcional)
    - Salva template de mapeamento para reutilização
    """
    import json
    from datetime import datetime as dt
    service = ImportService(db)
    try:
        result = await service.process_import(
            batch_id=data.batch_id,
            column_mapping=data.column_mapping,
            account_id=data.account_id,
            validate_balance=data.validate_balance,
            expected_final_balance=data.expected_final_balance,
            skip_duplicates=data.skip_duplicates,
            card_payment_date_override=data.card_payment_date
        )

        # Salvar/atualizar template se import teve sucesso
        if result.success and result.imported_count > 0:
            mapping_json = json.dumps(data.column_mapping.model_dump(exclude_none=True))
            template = db.query(ImportTemplate).filter(
                ImportTemplate.account_id == data.account_id
            ).first()
            if template:
                template.column_mapping = mapping_json
                template.last_used_at = dt.utcnow()
                template.success_count += 1
            else:
                template = ImportTemplate(
                    account_id=data.account_id,
                    column_mapping=mapping_json,
                    last_used_at=dt.utcnow(),
                    success_count=1,
                )
                db.add(template)
            db.commit()

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar importação: {str(e)}")


@router.post("/analyze", response_model=ImportAnalysis)
async def analyze_import(
    data: ImportProcess,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Análise prévia (dry-run) de importação.

    Classifica cada linha como nova/duplicada/incerta SEM inserir no banco.
    Retorna estatísticas e linhas incertas para review do usuário.
    """
    from datetime import date as date_type
    from decimal import Decimal
    from app.utils.normalization import normalize_for_hash, calculate_similarity, find_near_duplicate
    from app.services.import_service import detect_installment, adjust_date_for_credit_card, find_previous_installment, get_installment_base_description

    service = ImportService(db)

    # Carregar batch e dados do arquivo
    batch = db.query(ImportBatch).filter(ImportBatch.id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    account = db.query(BankAccount).filter(BankAccount.id == data.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Parsear arquivo
    import os
    if not batch.temp_file_path or not os.path.exists(batch.temp_file_path):
        raise HTTPException(status_code=400, detail="Arquivo temporário não encontrado")

    file_ext = os.path.splitext(batch.filename)[1].lower()
    if file_ext == '.csv':
        raw_data = service._parse_csv(batch.temp_file_path)
    elif file_ext in ('.xlsx', '.xls'):
        raw_data = service._parse_excel(batch.temp_file_path)
    else:
        raise HTTPException(status_code=400, detail=f"Formato {file_ext} não suportado para análise")

    mapping = data.column_mapping
    new_count = 0
    duplicate_count = 0
    fuzzy_duplicate_count = 0
    uncertain_count = 0
    error_count = 0
    uncertain_rows = []
    seen_hashes = set()
    all_dates = []
    all_new_amounts = []  # Amounts of new (non-duplicate) transactions
    transactions_preview = []  # All transactions for review
    running_balance = Decimal("0")  # Saldo acumulado para validação linha a linha
    first_balance_divergence_row = None  # Primeira linha onde saldo diverge

    for idx, row in enumerate(raw_data):
        try:
            # Extrair data, descrição e valor
            date_str = row.get(mapping.date_column, '')
            description = row.get(mapping.description_column, '')
            if not date_str or not description:
                error_count += 1
                continue

            trans_date = service._parse_date(date_str)
            if not trans_date:
                error_count += 1
                continue

            description = str(description).strip()
            if not description:
                error_count += 1
                continue

            # Extrair valor
            amount_str = None
            if mapping.amount_column:
                amount_str = row.get(mapping.amount_column)
            elif mapping.valor_brl_column:
                amount_str = row.get(mapping.valor_brl_column)
            elif mapping.valor_usd_column:
                amount_str = row.get(mapping.valor_usd_column)
            elif mapping.valor_eur_column:
                amount_str = row.get(mapping.valor_eur_column)

            # Consolidar Entrada/Saída em valor único (formato C6, Nubank)
            amount = None
            if amount_str is not None:
                amount = service._parse_amount(amount_str)

            if amount is None and (mapping.credit_column or mapping.debit_column):
                credit_raw = row.get(mapping.credit_column) if mapping.credit_column else None
                debit_raw = row.get(mapping.debit_column) if mapping.debit_column else None
                credit_val = service._parse_amount(credit_raw) if credit_raw and str(credit_raw).strip() else Decimal("0")
                debit_val = service._parse_amount(debit_raw) if debit_raw and str(debit_raw).strip() else Decimal("0")
                credit_val = credit_val if credit_val is not None else Decimal("0")
                debit_val = debit_val if debit_val is not None else Decimal("0")
                consolidated = credit_val - abs(debit_val)
                if consolidated != 0:
                    amount = consolidated

            if amount is None:
                error_count += 1
                continue

            # Running balance e saldo do arquivo
            running_balance += amount
            file_balance_val = None
            balance_ok_val = None
            if mapping.balance_column:
                bal_str = row.get(mapping.balance_column)
                if bal_str:
                    file_balance_val = service._parse_amount(bal_str)
                    if file_balance_val is not None:
                        # Comparar com tolerância de 0.01
                        diff = abs(running_balance - file_balance_val)
                        balance_ok_val = diff < Decimal("0.02")
                        if not balance_ok_val and first_balance_divergence_row is None:
                            first_balance_divergence_row = idx + 1

            original_currency = account.currency

            # Extrair card_payment_date (se mapeado)
            card_payment_date = None
            if mapping.card_payment_date_column:
                cpd_str = row.get(mapping.card_payment_date_column)
                if cpd_str:
                    card_payment_date = service._parse_date(cpd_str)
            # Override global do formulário tem prioridade
            if data.card_payment_date:
                card_payment_date = data.card_payment_date

            # Detectar parcelas (coluna dedicada ou na descrição)
            installment_number, installment_total = None, None
            installment_str = row.get(mapping.installment_column) if mapping.installment_column else None

            if installment_str and str(installment_str).strip():
                installment_number, installment_total = detect_installment(str(installment_str))

            if installment_number is None:
                installment_number, installment_total = detect_installment(description)

            # Se parcela veio da coluna dedicada, adicionar ao final da descrição
            if installment_number is not None and installment_str and str(installment_str).strip():
                existing_n, _ = detect_installment(description)
                if existing_n is None:
                    description = f"{description} {installment_number} de {installment_total}"

            # Ajustar data para parcelas de cartão de crédito
            # Regra: parcela N cai no MÊS DA COMPRA + (N-1) meses.
            # Parcela 1 ou compra à vista: data original (trans_date) preservada.
            original_date = trans_date
            if (
                account.is_credit_card
                and installment_number is not None
                and installment_number > 1
            ):
                import calendar
                desc_base = get_installment_base_description(description)
                prev = find_previous_installment(
                    db, data.account_id, desc_base, installment_number, installment_total
                )
                if prev:
                    base_date = prev.date
                    offset_months = 1
                else:
                    base_date = trans_date
                    offset_months = installment_number - 1

                target_month = base_date.month + offset_months
                target_year = base_date.year
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                try:
                    trans_date = date_type(target_year, target_month, base_date.day)
                except ValueError:
                    last_day = calendar.monthrange(target_year, target_month)[1]
                    trans_date = date_type(target_year, target_month, last_day)

            all_dates.append(trans_date)

            # Layer 1: Hash exato
            trans_hash = Transaction.generate_hash(
                data.account_id, trans_date, description,
                amount, original_currency,
                card_payment_date=card_payment_date
            )

            # Para duplicatas intra-arquivo: usar sufixo (transações legítimas distintas)
            if trans_hash in seen_hashes:
                suffix = 1
                suffixed_hash = Transaction.generate_hash(
                    data.account_id, trans_date, description,
                    amount, original_currency, suffix,
                    card_payment_date=card_payment_date
                )
                while suffixed_hash in seen_hashes:
                    suffix += 1
                    suffixed_hash = Transaction.generate_hash(
                        data.account_id, trans_date, description,
                        amount, original_currency, suffix,
                        card_payment_date=card_payment_date
                    )
                # Verificar se hash com sufixo já existe no banco
                existing_suffixed = db.query(Transaction).filter(
                    Transaction.transaction_hash == suffixed_hash
                ).first()
                if existing_suffixed:
                    duplicate_count += 1
                    seen_hashes.add(suffixed_hash)
                    transactions_preview.append(TransactionPreviewRow(
                        row=idx + 1, date=trans_date.isoformat(),
                        description=description, amount=amount,
                        status="duplicate", is_installment=installment_number is not None,
                        adjusted_date=trans_date.isoformat() if trans_date != original_date else None,
                        running_balance=running_balance,
                        file_balance=file_balance_val,
                        balance_ok=balance_ok_val,
                    ))
                    continue
                else:
                    trans_hash = suffixed_hash

            existing = db.query(Transaction).filter(
                Transaction.transaction_hash == trans_hash
            ).first()

            if existing:
                duplicate_count += 1
                seen_hashes.add(trans_hash)
                transactions_preview.append(TransactionPreviewRow(
                    row=idx + 1, date=trans_date.isoformat(),
                    description=description, amount=amount,
                    status="duplicate", is_installment=installment_number is not None,
                    adjusted_date=trans_date.isoformat() if trans_date != original_date else None,
                    running_balance=running_balance,
                    file_balance=file_balance_val,
                    balance_ok=balance_ok_val,
                ))
                continue

            # Layer 2: Fuzzy matching
            row_status = "new"
            fuzzy_match = find_near_duplicate(
                db, data.account_id, trans_date,
                amount, original_currency, description,
                card_payment_date=card_payment_date
            )

            if fuzzy_match:
                # Calcular similaridade para classificar
                norm_new = normalize_for_hash(description)
                norm_existing = normalize_for_hash(fuzzy_match.description)
                similarity = calculate_similarity(norm_new, norm_existing)

                if similarity >= 0.85:
                    fuzzy_duplicate_count += 1
                    row_status = "duplicate"
                elif similarity >= 0.65:
                    uncertain_count += 1
                    row_status = "uncertain"
                    uncertain_rows.append(UncertainRow(
                        row=idx + 1,
                        date=trans_date.isoformat(),
                        description=description,
                        amount=amount,
                        similar_to_id=fuzzy_match.id,
                        similar_to_description=fuzzy_match.description,
                        similarity=round(similarity, 2),
                    ))
                else:
                    new_count += 1
            else:
                new_count += 1

            # Rastrear amounts para validação de saldo (apenas novas)
            if row_status == "new":
                all_new_amounts.append(amount)

            transactions_preview.append(TransactionPreviewRow(
                row=idx + 1, date=trans_date.isoformat(),
                description=description, amount=amount,
                status=row_status, is_installment=installment_number is not None,
                adjusted_date=trans_date.isoformat() if trans_date != original_date else None,
                running_balance=running_balance,
                file_balance=file_balance_val,
                balance_ok=balance_ok_val,
            ))

            seen_hashes.add(trans_hash)

        except Exception:
            error_count += 1

    # Verificar sobreposição
    overlap_info = None
    if all_dates:
        date_start = min(all_dates)
        date_end = max(all_dates)

        existing_count = db.query(Transaction).filter(
            Transaction.account_id == data.account_id,
            Transaction.date.between(date_start, date_end)
        ).count()

        if existing_count > 0:
            overlap_info = (
                f"Já existem {existing_count} transações entre "
                f"{date_start.strftime('%d/%m/%Y')} e {date_end.strftime('%d/%m/%Y')} nesta conta"
            )

    # Calcular totais para validação de saldo
    calculated_total = sum(all_new_amounts, Decimal("0.00")) if all_new_amounts else Decimal("0.00")
    positive_amounts = [a for a in all_new_amounts if a > 0]
    negative_amounts = [a for a in all_new_amounts if a < 0]
    positive_total = sum(positive_amounts, Decimal("0.00"))
    negative_total = sum(negative_amounts, Decimal("0.00"))

    return ImportAnalysis(
        batch_id=data.batch_id,
        total_rows=len(raw_data),
        new_count=new_count,
        duplicate_count=duplicate_count,
        fuzzy_duplicate_count=fuzzy_duplicate_count,
        uncertain_count=uncertain_count,
        error_count=error_count,
        date_range_start=min(all_dates).isoformat() if all_dates else None,
        date_range_end=max(all_dates).isoformat() if all_dates else None,
        overlap_info=overlap_info,
        uncertain_rows=uncertain_rows[:20],
        calculated_total=calculated_total,
        positive_total=positive_total,
        negative_total=negative_total,
        positive_count=len(positive_amounts),
        negative_count=len(negative_amounts),
        running_balance_final=running_balance,
        first_balance_divergence_row=first_balance_divergence_row,
        transactions_preview=transactions_preview,
    )


@router.get("/overlap-check", response_model=OverlapCheckResponse)
def check_overlap(
    account_id: int,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Verifica sobreposição de datas com importações anteriores.
    """
    from datetime import date as date_type

    try:
        sd = date_type.fromisoformat(start_date)
        ed = date_type.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas inválidas (formato: YYYY-MM-DD)")

    # Buscar batches que sobrepõem
    overlapping_batches = db.query(ImportBatch).filter(
        ImportBatch.account_id == account_id,
        ImportBatch.status.in_([ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_DUPLICATES]),
        ImportBatch.date_start <= ed,
        ImportBatch.date_end >= sd,
    ).all()

    # Contar transações existentes no período
    existing_count = db.query(Transaction).filter(
        Transaction.account_id == account_id,
        Transaction.date.between(sd, ed)
    ).count()

    batches_info = [
        {
            "id": b.id,
            "filename": b.filename,
            "imported_at": b.imported_at.isoformat() if b.imported_at else None,
            "date_start": b.date_start.isoformat() if b.date_start else None,
            "date_end": b.date_end.isoformat() if b.date_end else None,
            "imported_records": b.imported_records,
        }
        for b in overlapping_batches
    ]

    return OverlapCheckResponse(
        has_overlap=len(overlapping_batches) > 0,
        existing_transaction_count=existing_count,
        overlapping_batches=batches_info,
        message=(
            f"Já existem {existing_count} transações entre "
            f"{sd.strftime('%d/%m/%Y')} e {ed.strftime('%d/%m/%Y')}"
        ) if existing_count > 0 else "Nenhuma sobreposição encontrada",
    )


@router.get("/batches", response_model=List[ImportBatchResponse])
def list_batches(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar histórico de importações."""
    query = db.query(ImportBatch)

    if account_id:
        query = query.filter(ImportBatch.account_id == account_id)

    batches = query.order_by(ImportBatch.imported_at.desc()).limit(100).all()
    return batches


@router.get("/pending-count")
def get_pending_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Contar batches em status PENDING (uploaded mas não processados)."""
    count = db.query(ImportBatch).filter(
        ImportBatch.status == ImportStatus.PENDING
    ).count()
    return {"pending_count": count}


@router.get("/batches/{batch_id}", response_model=ImportBatchResponse)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter detalhes de um lote de importação."""
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    return batch


@router.delete("/batches/{batch_id}")
def revert_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reverter importação (excluir todas as transações do lote).
    """
    from app.models import Transaction, BankAccount
    from sqlalchemy import func

    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    # Calcular total das transações a serem excluídas
    total = db.query(func.sum(Transaction.amount)).filter(
        Transaction.import_batch_id == batch_id
    ).scalar() or Decimal("0.00")

    # Excluir transações
    deleted = db.query(Transaction).filter(
        Transaction.import_batch_id == batch_id
    ).delete()

    # Atualizar saldo da conta
    account = db.query(BankAccount).filter(BankAccount.id == batch.account_id).first()
    if account:
        log_balance_change(db, account, account.current_balance - total,
                           'revert_import', f'Reverted batch {batch_id} ({deleted} txns)')

    # Excluir batch
    db.delete(batch)
    db.commit()

    return {
        "message": f"Importação revertida. {deleted} transações excluídas.",
        "deleted_count": deleted
    }


@router.get("/templates/{account_id}")
def get_import_template(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Retorna template de importação salvo para uma conta."""
    import json
    template = db.query(ImportTemplate).filter(
        ImportTemplate.account_id == account_id
    ).first()
    if not template:
        return None
    return {
        "id": template.id,
        "account_id": template.account_id,
        "column_mapping": json.loads(template.column_mapping),
        "file_format_hints": json.loads(template.file_format_hints) if template.file_format_hints else None,
        "last_used_at": template.last_used_at.isoformat() if template.last_used_at else None,
        "success_count": template.success_count,
    }


@router.delete("/templates/{account_id}")
def delete_import_template(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Exclui template de importação de uma conta."""
    template = db.query(ImportTemplate).filter(
        ImportTemplate.account_id == account_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    db.delete(template)
    db.commit()
    return {"ok": True}


@router.post("/detect-columns")
async def detect_columns(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Detectar colunas automaticamente sem criar batch.
    Útil para preview rápido.
    """
    import tempfile
    import os

    service = ImportService(db)

    # Salvar temporariamente
    suffix = '.' + file.filename.split('.')[-1] if file.filename else ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        content = await file.read()
        temp.write(content)
        temp_path = temp.name

    try:
        file_type = service._get_file_type(file)
        if not file_type:
            raise HTTPException(status_code=400, detail="Tipo de arquivo não suportado")

        raw_data = service._parse_file(temp_path, file_type)
        mapping = service.column_detector.detect(raw_data)

        return {
            "columns": list(raw_data[0].keys()) if raw_data else [],
            "detected_mapping": mapping,
            "sample_rows": raw_data[:5]
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/bulk-upload")
async def bulk_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload de arquivo para importação em lote (múltiplas contas).

    O arquivo deve conter colunas de Banco e Conta para identificar
    onde cada transação será importada.

    Retorna preview dos dados e lista de contas encontradas.
    """
    import tempfile
    import os

    service = ImportService(db)

    # Validar tipo
    file_type = service._get_file_type(file)
    if not file_type:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não suportado")

    # Salvar temporariamente
    suffix = '.' + file.filename.split('.')[-1] if file.filename else ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        content = await file.read()
        temp.write(content)
        temp_path = temp.name

    try:
        raw_data = service._parse_file(temp_path, file_type)
        mapping = service.column_detector.detect(raw_data)

        # Extrair bancos e contas únicos do arquivo
        banks_accounts = set()
        if mapping.bank_column and mapping.account_column:
            for row in raw_data:
                bank = row.get(mapping.bank_column, '').strip()
                account = row.get(mapping.account_column, '').strip()
                if bank and account:
                    banks_accounts.add((bank, account))

        return {
            "total_rows": len(raw_data),
            "columns": list(raw_data[0].keys()) if raw_data else [],
            "detected_mapping": mapping,
            "banks_accounts_found": [{"bank": b, "account": a} for b, a in banks_accounts],
            "preview_rows": raw_data[:20],
            "temp_file_path": temp_path,
            "file_type": file_type.value
        }
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk-process")
async def bulk_process(
    temp_file_path: str = Form(...),
    file_type: str = Form(...),
    date_column: str = Form(...),
    description_column: str = Form(...),
    bank_column: str = Form(...),
    account_column: str = Form(...),
    amount_column: str = Form(""),
    category_column: str = Form(""),
    balance_column: str = Form(""),
    valor_brl_column: str = Form(""),
    valor_usd_column: str = Form(""),
    valor_eur_column: str = Form(""),
    card_payment_date_column: str = Form(""),
    create_missing_accounts: bool = Form(True),
    create_missing_categories: bool = Form(True),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Processar importação em lote com múltiplas contas.

    - Cria contas automaticamente se não existirem
    - Cria categorias automaticamente se não existirem
    - Agrupa transações por conta
    - Detecta duplicatas
    - Categoriza automaticamente (se não vier no arquivo)
    """
    import os
    from app.models import Bank, BankAccount, Transaction, ImportBatch, FileType, Category, CategoryType
    from app.services.categorization_service import CategorizationService
    from app.services.exchange_service import ExchangeService
    from collections import defaultdict
    from decimal import Decimal, ROUND_HALF_UP

    # Normalizar strings vazias para None
    amount_column = amount_column.strip() if amount_column else None
    category_column = category_column.strip() if category_column else None
    balance_column = balance_column.strip() if balance_column else None
    valor_brl_column = valor_brl_column.strip() if valor_brl_column else None
    valor_usd_column = valor_usd_column.strip() if valor_usd_column else None
    valor_eur_column = valor_eur_column.strip() if valor_eur_column else None
    card_payment_date_column = card_payment_date_column.strip() if card_payment_date_column else None

    # Converter string vazia para None
    amount_column = amount_column or None
    category_column = category_column or None
    balance_column = balance_column or None
    valor_brl_column = valor_brl_column or None
    valor_usd_column = valor_usd_column or None
    valor_eur_column = valor_eur_column or None
    card_payment_date_column = card_payment_date_column or None

    logger.info(f"bulk-process chamado com: date_column={date_column}, description_column={description_column}")
    logger.info(f"  valor_brl_column={valor_brl_column}, valor_usd_column={valor_usd_column}, valor_eur_column={valor_eur_column}")
    logger.info(f"  amount_column={amount_column}, category_column={category_column}")

    if not os.path.exists(temp_file_path):
        raise HTTPException(status_code=400, detail="Arquivo temporário não encontrado. Faça upload novamente.")

    service = ImportService(db)
    categorization = CategorizationService(db)
    exchange_service = ExchangeService(db)

    try:
        # Parse do arquivo
        ft = FileType(file_type)
        raw_data = service._parse_file(temp_file_path, ft)

        # Agrupar por banco/conta
        grouped = defaultdict(list)
        for idx, row in enumerate(raw_data):
            bank_name = str(row.get(bank_column, '')).strip()
            account_name = str(row.get(account_column, '')).strip()

            if not bank_name or not account_name:
                continue

            key = (bank_name, account_name)
            grouped[key].append((idx, row))

        # Cache de categorias para evitar queries repetidas
        category_cache = {}

        def get_or_create_category(category_name: str, amount: float) -> Optional[int]:
            """Busca ou cria categoria pelo nome."""
            if not category_name:
                return None

            category_name = category_name.strip()
            if not category_name:
                return None

            # Verificar cache
            cache_key = category_name.lower()
            if cache_key in category_cache:
                return category_cache[cache_key]

            # Buscar no banco
            category = db.query(Category).filter(
                Category.name.ilike(f"%{category_name}%")
            ).first()

            if category:
                category_cache[cache_key] = category.id
                return category.id

            # Criar nova categoria se permitido
            if create_missing_categories:
                # Determinar tipo baseado no valor
                cat_type = CategoryType.INCOME if amount > 0 else CategoryType.EXPENSE
                category = Category(
                    name=category_name,
                    type=cat_type,
                    color="#6B7280",
                    is_active=True
                )
                db.add(category)
                db.flush()
                category_cache[cache_key] = category.id
                results["categories_created"] = results.get("categories_created", 0) + 1
                return category.id

            return None

        # Processar cada grupo
        results = {
            "total_rows": len(raw_data),
            "accounts_processed": 0,
            "accounts_created": 0,
            "categories_created": 0,
            "transactions_imported": 0,
            "duplicates_skipped": 0,
            "errors": [],
            "accounts_summary": []
        }

        for (bank_name, account_name), rows in grouped.items():
            # Buscar ou criar banco
            bank = db.query(Bank).filter(Bank.name.ilike(f"%{bank_name}%")).first()
            if not bank:
                if create_missing_accounts:
                    bank = Bank(name=bank_name, code=None, color="#6B7280")
                    db.add(bank)
                    db.flush()
                else:
                    results["errors"].append(f"Banco não encontrado: {bank_name}")
                    continue

            # Buscar ou criar conta
            account = db.query(BankAccount).filter(
                BankAccount.bank_id == bank.id,
                BankAccount.name.ilike(f"%{account_name}%")
            ).first()

            if not account:
                if create_missing_accounts:
                    account = BankAccount(
                        bank_id=bank.id,
                        name=account_name,
                        account_type="checking",
                        initial_balance=Decimal("0.00"),
                        current_balance=Decimal("0.00"),
                        is_active=True
                    )
                    db.add(account)
                    db.flush()
                    results["accounts_created"] += 1
                else:
                    results["errors"].append(f"Conta não encontrada: {bank_name} - {account_name}")
                    continue

            # Criar batch para esta conta
            batch = ImportBatch(
                account_id=account.id,
                filename=f"bulk_import_{bank_name}_{account_name}",
                file_type=ft,
                total_records=len(rows),
                status="processing"
            )
            db.add(batch)
            db.flush()

            # Processar transações
            imported = 0
            duplicates = 0
            seen_hashes = set()  # Para detectar duplicatas dentro do mesmo arquivo

            for idx, row in rows:
                try:
                    # Extrair dados
                    date_str = row.get(date_column)
                    description = str(row.get(description_column, '')).strip()
                    balance_str = row.get(balance_column) if balance_column else None
                    category_str = row.get(category_column) if category_column else None

                    # Extrair valores multi-moeda
                    amount_str = row.get(amount_column) if amount_column else None
                    valor_brl_str = row.get(valor_brl_column) if valor_brl_column else None
                    valor_usd_str = row.get(valor_usd_column) if valor_usd_column else None
                    valor_eur_str = row.get(valor_eur_column) if valor_eur_column else None

                    if not date_str or not description:
                        continue

                    # Converter valores multi-moeda
                    valor_brl = service._parse_amount(valor_brl_str) if valor_brl_str and str(valor_brl_str).strip() else None
                    valor_usd = service._parse_amount(valor_usd_str) if valor_usd_str and str(valor_usd_str).strip() else None
                    valor_eur = service._parse_amount(valor_eur_str) if valor_eur_str and str(valor_eur_str).strip() else None
                    amount_generic = service._parse_amount(amount_str) if amount_str and str(amount_str).strip() else None

                    # Determinar moeda original e valor - verificar TODAS as colunas disponíveis
                    original_currency = CurrencyCode.BRL
                    original_amount = None

                    # Prioridade: BRL > USD > EUR > genérico
                    if valor_brl is not None:
                        original_currency = CurrencyCode.BRL
                        original_amount = valor_brl
                    elif valor_usd is not None:
                        original_currency = CurrencyCode.USD
                        original_amount = valor_usd
                    elif valor_eur is not None:
                        original_currency = CurrencyCode.EUR
                        original_amount = valor_eur
                    elif amount_generic is not None:
                        original_currency = CurrencyCode.BRL  # Default para BRL
                        original_amount = amount_generic

                    # Se ainda não encontrou valor, pular linha
                    if original_amount is None:
                        results["errors"].append(f"Linha {idx + 1}: Nenhum valor encontrado")
                        continue

                    # Converter data primeiro (necessário para câmbio)
                    trans_date = service._parse_date(date_str)
                    if not trans_date:
                        results["errors"].append(f"Linha {idx + 1}: Data inválida: {date_str}")
                        continue

                    # Definir valores para cada moeda
                    # Usar valores do CSV se disponíveis, senão calcular via câmbio
                    amount_brl = valor_brl
                    amount_usd = valor_usd
                    amount_eur = valor_eur

                    # Calcular valores faltantes via câmbio
                    try:
                        if original_currency == CurrencyCode.BRL:
                            # Valor original é BRL
                            if amount_brl is None:
                                amount_brl = original_amount
                            # Calcular USD se não veio no CSV
                            if amount_usd is None:
                                amount_usd = await exchange_service.convert(
                                    original_amount, CurrencyCode.BRL, CurrencyCode.USD, trans_date
                                )
                            # Calcular EUR se não veio no CSV
                            if amount_eur is None:
                                amount_eur = await exchange_service.convert(
                                    original_amount, CurrencyCode.BRL, CurrencyCode.EUR, trans_date
                                )

                        elif original_currency == CurrencyCode.USD:
                            # Valor original é USD
                            if amount_usd is None:
                                amount_usd = original_amount
                            # Calcular BRL se não veio no CSV
                            if amount_brl is None:
                                amount_brl = await exchange_service.convert(
                                    original_amount, CurrencyCode.USD, CurrencyCode.BRL, trans_date
                                )
                            # Calcular EUR se não veio no CSV
                            if amount_eur is None:
                                amount_eur = await exchange_service.convert(
                                    original_amount, CurrencyCode.USD, CurrencyCode.EUR, trans_date
                                )

                        elif original_currency == CurrencyCode.EUR:
                            # Valor original é EUR
                            if amount_eur is None:
                                amount_eur = original_amount
                            # Calcular BRL se não veio no CSV
                            if amount_brl is None:
                                amount_brl = await exchange_service.convert(
                                    original_amount, CurrencyCode.EUR, CurrencyCode.BRL, trans_date
                                )
                            # Calcular USD se não veio no CSV
                            if amount_usd is None:
                                amount_usd = await exchange_service.convert(
                                    original_amount, CurrencyCode.EUR, CurrencyCode.USD, trans_date
                                )

                    except ValueError as e:
                        # Se não conseguir cotação, usar zero para moedas não-originais
                        logger.warning(f"Linha {idx + 1}: Erro ao buscar câmbio: {e}")
                        if amount_brl is None:
                            amount_brl = original_amount if original_currency == CurrencyCode.BRL else Decimal("0.00")
                        if amount_usd is None:
                            amount_usd = original_amount if original_currency == CurrencyCode.USD else Decimal("0.00")
                        if amount_eur is None:
                            amount_eur = original_amount if original_currency == CurrencyCode.EUR else Decimal("0.00")

                    # Garantir que nenhum valor seja None
                    amount_brl = amount_brl or Decimal("0.00")
                    amount_usd = amount_usd or Decimal("0.00")
                    amount_eur = amount_eur or Decimal("0.00")

                    # Arredondar para 2 casas decimais
                    amount_brl = amount_brl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    amount_usd = amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    amount_eur = amount_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                    # Usar original_amount como amount (valor na moeda da conta)
                    amount = original_amount
                    balance_after = service._parse_amount(balance_str) if balance_str else None

                    if amount is None:
                        continue

                    # === Detecção de duplicados multi-camada ===
                    suffix = 0
                    is_duplicate = False
                    trans_hash = None

                    # Layer 1: Hash exato
                    trans_hash = Transaction.generate_hash(
                        account.id, trans_date, description, original_amount, original_currency
                    )

                    # Verificar no mesmo arquivo (intra-file dedup)
                    if trans_hash in seen_hashes:
                        if skip_duplicates:
                            duplicates += 1
                            is_duplicate = True
                        else:
                            # Mesmo arquivo, mesma transação - incrementar sufixo
                            while trans_hash in seen_hashes:
                                suffix += 1
                                trans_hash = Transaction.generate_hash(
                                    account.id, trans_date, description,
                                    original_amount, original_currency, suffix
                                )

                    # Verificar no banco
                    if not is_duplicate:
                        existing = db.query(Transaction).filter(
                            Transaction.transaction_hash == trans_hash
                        ).first()
                        if existing:
                            if skip_duplicates:
                                duplicates += 1
                                seen_hashes.add(trans_hash)
                                is_duplicate = True
                            else:
                                while existing:
                                    suffix += 1
                                    trans_hash = Transaction.generate_hash(
                                        account.id, trans_date, description,
                                        original_amount, original_currency, suffix
                                    )
                                    existing = db.query(Transaction).filter(
                                        Transaction.transaction_hash == trans_hash
                                    ).first()

                    # Layer 2: Fuzzy matching (se Layer 1 não encontrou)
                    if not is_duplicate and skip_duplicates:
                        from app.utils.normalization import find_near_duplicate
                        fuzzy_match = find_near_duplicate(
                            db, account.id, trans_date,
                            original_amount, original_currency, description,
                            card_payment_date=card_payment_date
                        )
                        if fuzzy_match:
                            duplicates += 1
                            is_duplicate = True

                    # Se é duplicata e skip_duplicates está ativo, pular
                    if is_duplicate:
                        continue

                    # Buscar/criar categoria do arquivo ou categorizar automaticamente
                    category_id = None
                    is_validated = False

                    if category_str:
                        # Categoria veio do arquivo
                        category_id = get_or_create_category(str(category_str), float(amount))
                        is_validated = True  # Já veio categorizado

                    if not category_id:
                        # Tentar categorizar automaticamente
                        category_id, confidence, method = categorization.categorize(
                            description, float(amount)
                        )
                        is_validated = (method == 'rule')

                    # Aprender com a categorização para melhorar futuras importações
                    if category_id:
                        categorization.learn_from_categorization(description, category_id)

                    # Criar transação
                    transaction = Transaction(
                        account_id=account.id,
                        category_id=category_id,
                        date=trans_date,
                        description=description,
                        original_description=description,
                        original_currency=original_currency,
                        original_amount=original_amount,
                        amount_brl=amount_brl,
                        amount_usd=amount_usd,
                        amount_eur=amount_eur,
                        amount=original_amount,  # Valor na moeda da conta
                        balance_after=balance_after,
                        transaction_hash=trans_hash,
                        is_validated=is_validated,
                        import_batch_id=batch.id
                    )
                    db.add(transaction)
                    seen_hashes.add(trans_hash)  # Marcar como processado
                    imported += 1

                    # Atualizar saldo (usar original_amount, na moeda da conta)
                    log_balance_change(db, account, account.current_balance + original_amount,
                                       'import', f'Historical import batch {batch.id}')

                except Exception as e:
                    # Não fazer rollback aqui, apenas registrar o erro e continuar
                    logger.warning(f"Erro na linha {idx + 1}: {str(e)}")
                    results["errors"].append(f"Linha {idx + 1}: {str(e)}")

            # Atualizar batch
            batch.imported_records = imported
            batch.duplicate_records = duplicates
            batch.status = "completed"

            # Preencher período do lote
            from sqlalchemy import func as sqlfunc
            date_range = db.query(
                sqlfunc.min(Transaction.date), sqlfunc.max(Transaction.date)
            ).filter(Transaction.import_batch_id == batch.id).first()
            if date_range and date_range[0]:
                batch.date_start = date_range[0]
                batch.date_end = date_range[1]

            results["accounts_processed"] += 1
            results["transactions_imported"] += imported
            results["duplicates_skipped"] += duplicates
            results["accounts_summary"].append({
                "bank": bank_name,
                "account": account_name,
                "imported": imported,
                "duplicates": duplicates
            })

        db.commit()

        # Limpar arquivo temporário
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        return results

    except Exception as e:
        import traceback
        error_msg = f"Erro no bulk-process: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        db.rollback()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=error_msg)
