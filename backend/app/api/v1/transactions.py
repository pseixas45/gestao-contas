import logging
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import date

from app.api.deps import get_db
from app.models import Transaction, BankAccount, Category, User
from app.models.exchange_rate import CurrencyCode
from app.services.balance_log_service import log_balance_change
from app.schemas.transaction import (
    TransactionCreate, TransactionUpdate, TransactionResponse,
    TransactionFilter, BulkCategorize, TransactionSuggestion
)
from app.utils.security import get_current_active_user
from app.services.categorization_service import CategorizationService
from app.services.exchange_service import ExchangeService

logger = logging.getLogger(__name__)

router = APIRouter()

# Palavras genéricas bancárias que não devem virar regras de categorização
_RULE_STOPWORDS = {
    'pix', 'pag', 'pagamento', 'pagamentos', 'transferencia', 'transf',
    'boleto', 'ted', 'doc', 'tit', 'titulo', 'int', 'sispag', 'cred',
    'deb', 'debito', 'credito', 'deposito', 'banco', 'resg', 'resgate',
    'qrs', 'parcela', 'parc', 'compra', 'venda', 'pgto', 'receb',
    'recebimento', 'lanc', 'lancamento', 'mov', 'movimentacao', 'tarifa',
    'taxa', 'envio', 'recebido', 'enviado', 'estorno', 'devolucao',
}


def _extract_rule_keyword(description: str) -> str:
    """Extrai a melhor palavra-chave da descrição para criar uma regra.

    Pula palavras genéricas bancárias e retorna a primeira palavra
    significativa com 3+ caracteres.
    """
    from app.services.categorization_service import TextProcessor
    text_proc = TextProcessor()
    normalized = text_proc.normalize(description)
    words = [w for w in (normalized or "").split() if len(w) >= 3]
    for word in words:
        if word not in _RULE_STOPWORDS:
            return word
    return ""


def _create_or_update_rule(db: Session, keyword: str, category_id: int):
    """Cria ou atualiza regra, desativando conflitantes."""
    from app.models import CategorizationRule, MatchType

    if not keyword:
        return

    # Desativar regras conflitantes (mesmo padrão, categoria diferente)
    conflicting = (
        db.query(CategorizationRule)
        .filter(
            CategorizationRule.pattern.ilike(keyword),
            CategorizationRule.category_id != category_id,
            CategorizationRule.is_active == True
        )
        .all()
    )
    for r in conflicting:
        r.is_active = False

    # Criar ou reativar regra para a categoria correta
    existing_rule = (
        db.query(CategorizationRule)
        .filter(
            CategorizationRule.pattern.ilike(keyword),
            CategorizationRule.category_id == category_id
        )
        .first()
    )
    if existing_rule:
        existing_rule.is_active = True
        existing_rule.hit_count += 1
    else:
        rule = CategorizationRule(
            category_id=category_id,
            pattern=keyword,
            match_type=MatchType.CONTAINS,
            priority=50
        )
        db.add(rule)


@router.get("")
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    card_payment_start: Optional[date] = None,
    card_payment_end: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    search: Optional[str] = None,
    is_validated: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar transações com filtros e saldo acumulado."""
    query = db.query(Transaction)

    # Aplicar filtros
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id is not None:
        if category_id == 0:
            query = query.filter(Transaction.category_id.is_(None))
        else:
            query = query.filter(Transaction.category_id == category_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if card_payment_start:
        query = query.filter(Transaction.card_payment_date >= card_payment_start)
    if card_payment_end:
        query = query.filter(Transaction.card_payment_date <= card_payment_end)
    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Transaction.amount <= max_amount)
    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))
    if is_validated is not None:
        query = query.filter(Transaction.is_validated == is_validated)

    # Ordenar e paginar
    total = query.count()
    offset = (page - 1) * limit
    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc())\
        .offset(offset).limit(limit).all()

    # Adicionar dados relacionados
    result = []
    for t in transactions:
        t_response = TransactionResponse.model_validate(t)
        t_response.account_name = t.account.name if t.account else None
        if t.category:
            t_response.category_name = t.category.name
            t_response.category_color = t.category.color
        result.append(t_response)

    # Calcular balance_before para saldo acumulado (apenas quando filtrado por conta)
    balance_before = None
    if account_id and transactions:
        account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if account:
            initial_balance = account.initial_balance or Decimal("0")

            # Soma de TODAS as transações da conta antes de start_date
            # Usa original_amount (moeda da conta) para saldo correto
            pre_filter_sum = Decimal("0")
            if start_date:
                pre_filter_sum = db.query(
                    func.coalesce(func.sum(Transaction.original_amount), 0)
                ).filter(
                    Transaction.account_id == account_id,
                    Transaction.date < start_date
                ).scalar()

            # Soma das transações filtradas em páginas anteriores (cronologicamente)
            # Em ordem DESC: página atual mostra posições [offset, offset+len).
            # Transações cronologicamente anteriores = posições [offset+len, total) em DESC
            # = as (total - offset - len) transações mais antigas no resultado filtrado.
            n_earlier = max(0, total - offset - len(transactions))
            pre_page_sum = Decimal("0")
            if n_earlier > 0:
                earlier_subq = query.with_entities(Transaction.original_amount).order_by(
                    Transaction.date.asc(), Transaction.id.asc()
                ).limit(n_earlier).subquery()
                pre_page_sum = db.query(
                    func.coalesce(func.sum(earlier_subq.c.original_amount), 0)
                ).scalar()

            balance_before = float(initial_balance + pre_filter_sum + pre_page_sum)

    return {
        "items": result,
        "total": total,
        "balance_before": balance_before,
    }


@router.get("/pending", response_model=List[TransactionResponse])
def list_pending_transactions(
    account_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar transações pendentes de categorização."""
    query = db.query(Transaction).filter(
        or_(
            Transaction.category_id == None,
            Transaction.is_validated == False
        )
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    transactions = query.order_by(Transaction.date.desc())\
        .offset((page - 1) * limit).limit(limit).all()

    result = []
    for t in transactions:
        t_response = TransactionResponse.model_validate(t)
        t_response.account_name = t.account.name if t.account else None
        result.append(t_response)

    return result


@router.get("/pending/count")
def count_pending_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Contar transações pendentes."""
    count = db.query(Transaction).filter(
        or_(
            Transaction.category_id == None,
            Transaction.is_validated == False
        )
    ).count()
    return {"count": count}


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter transação por ID."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    result = TransactionResponse.model_validate(transaction)
    result.account_name = transaction.account.name if transaction.account else None
    if transaction.category:
        result.category_name = transaction.category.name
        result.category_color = transaction.category.color
    return result


@router.post("", response_model=TransactionResponse)
async def create_transaction(
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Criar nova transação manualmente."""
    # Verificar se conta existe
    account = db.query(BankAccount).filter(BankAccount.id == transaction_data.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Verificar se categoria existe (se informada)
    if transaction_data.category_id:
        category = db.query(Category).filter(Category.id == transaction_data.category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    data = transaction_data.model_dump()
    amount = data["amount"]

    # Preencher campos multi-moeda a partir da moeda da conta
    account_currency = CurrencyCode(account.currency) if account.currency else CurrencyCode.BRL
    data["original_currency"] = account_currency
    if data.get("original_amount") is None:
        data["original_amount"] = amount

    # Preencher coluna da moeda nativa
    # Nota: usar "is None" em vez de setdefault porque model_dump() inclui chaves com valor None
    if account_currency == CurrencyCode.BRL:
        if data.get("amount_brl") is None:
            data["amount_brl"] = amount
    elif account_currency == CurrencyCode.USD:
        if data.get("amount_usd") is None:
            data["amount_usd"] = amount
    elif account_currency == CurrencyCode.EUR:
        if data.get("amount_eur") is None:
            data["amount_eur"] = amount

    # Converter para as outras moedas via câmbio
    trans_date = data.get("date")
    exchange_service = ExchangeService(db)
    try:
        if account_currency == CurrencyCode.BRL:
            if data.get("amount_usd") is None:
                data["amount_usd"] = await exchange_service.convert(amount, CurrencyCode.BRL, CurrencyCode.USD, trans_date)
            if data.get("amount_eur") is None:
                data["amount_eur"] = await exchange_service.convert(amount, CurrencyCode.BRL, CurrencyCode.EUR, trans_date)
        elif account_currency == CurrencyCode.USD:
            if data.get("amount_brl") is None:
                data["amount_brl"] = await exchange_service.convert(amount, CurrencyCode.USD, CurrencyCode.BRL, trans_date)
            if data.get("amount_eur") is None:
                data["amount_eur"] = await exchange_service.convert(amount, CurrencyCode.USD, CurrencyCode.EUR, trans_date)
        elif account_currency == CurrencyCode.EUR:
            if data.get("amount_brl") is None:
                data["amount_brl"] = await exchange_service.convert(amount, CurrencyCode.EUR, CurrencyCode.BRL, trans_date)
            if data.get("amount_usd") is None:
                data["amount_usd"] = await exchange_service.convert(amount, CurrencyCode.EUR, CurrencyCode.USD, trans_date)
    except ValueError as e:
        logger.warning(f"Erro ao buscar câmbio para transação manual: {e}")
        # Fallback: zero para moedas sem cotação
        if data.get("amount_brl") is None:
            data["amount_brl"] = amount if account_currency == CurrencyCode.BRL else Decimal("0.00")
        if data.get("amount_usd") is None:
            data["amount_usd"] = amount if account_currency == CurrencyCode.USD else Decimal("0.00")
        if data.get("amount_eur") is None:
            data["amount_eur"] = amount if account_currency == CurrencyCode.EUR else Decimal("0.00")

    transaction = Transaction(**data)
    transaction.is_validated = True  # Transações manuais são validadas
    transaction.set_hash()

    # Se hash já existe, incrementar sufixo (mesma lógica da importação)
    suffix = 0
    while db.query(Transaction).filter(
        Transaction.transaction_hash == transaction.transaction_hash
    ).first():
        suffix += 1
        transaction.transaction_hash = Transaction.generate_hash(
            transaction.account_id, transaction.date, transaction.description,
            transaction.original_amount, transaction.original_currency, suffix
        )

    db.add(transaction)

    # Atualizar saldo da conta (amount = valor na moeda da conta)
    log_balance_change(db, account, account.current_balance + amount,
                       'transaction_create', f'Transaction {transaction.description[:80]}')

    db.commit()
    db.refresh(transaction)

    result = TransactionResponse.model_validate(transaction)
    result.account_name = account.name
    return result


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    transaction_data: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar transação."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    old_amount = transaction.amount
    old_category_id = transaction.category_id
    update_data = transaction_data.model_dump(exclude_unset=True)

    # Verificar categoria (se informada)
    if "category_id" in update_data and update_data["category_id"]:
        category = db.query(Category).filter(Category.id == update_data["category_id"]).first()
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Se valor mudou, atualizar também os campos multi-moeda com conversão
    if "amount" in update_data:
        new_amount = update_data["amount"]
        account_currency = CurrencyCode(transaction.account.currency) if transaction.account.currency else CurrencyCode.BRL
        update_data["original_amount"] = new_amount

        # Moeda nativa
        if account_currency == CurrencyCode.BRL:
            update_data.setdefault("amount_brl", new_amount)
        elif account_currency == CurrencyCode.USD:
            update_data.setdefault("amount_usd", new_amount)
        elif account_currency == CurrencyCode.EUR:
            update_data.setdefault("amount_eur", new_amount)

        # Converter para as outras moedas
        trans_date = update_data.get("date", transaction.date)
        exchange_service = ExchangeService(db)
        try:
            if account_currency == CurrencyCode.BRL:
                update_data.setdefault("amount_usd", await exchange_service.convert(new_amount, CurrencyCode.BRL, CurrencyCode.USD, trans_date))
                update_data.setdefault("amount_eur", await exchange_service.convert(new_amount, CurrencyCode.BRL, CurrencyCode.EUR, trans_date))
            elif account_currency == CurrencyCode.USD:
                update_data.setdefault("amount_brl", await exchange_service.convert(new_amount, CurrencyCode.USD, CurrencyCode.BRL, trans_date))
                update_data.setdefault("amount_eur", await exchange_service.convert(new_amount, CurrencyCode.USD, CurrencyCode.EUR, trans_date))
            elif account_currency == CurrencyCode.EUR:
                update_data.setdefault("amount_brl", await exchange_service.convert(new_amount, CurrencyCode.EUR, CurrencyCode.BRL, trans_date))
                update_data.setdefault("amount_usd", await exchange_service.convert(new_amount, CurrencyCode.EUR, CurrencyCode.USD, trans_date))
        except ValueError as e:
            logger.warning(f"Erro ao buscar câmbio para atualização: {e}")

    for field, value in update_data.items():
        setattr(transaction, field, value)

    # Se valor mudou, atualizar saldo e recalcular hash
    if "amount" in update_data:
        difference = transaction.amount - old_amount
        log_balance_change(db, transaction.account,
                           transaction.account.current_balance + difference,
                           'transaction_update', f'Transaction {transaction.id} amount changed')
        transaction.set_hash()

        # Se novo hash colide com outro registro, usar sufixo
        suffix = 0
        while True:
            existing = db.query(Transaction).filter(
                Transaction.transaction_hash == transaction.transaction_hash,
                Transaction.id != transaction.id
            ).first()
            if not existing:
                break
            suffix += 1
            transaction.transaction_hash = Transaction.generate_hash(
                transaction.account_id, transaction.date, transaction.description,
                transaction.original_amount, transaction.original_currency, suffix
            )

    # Se categoria mudou, aprender com a mudança
    new_category_id = update_data.get("category_id")
    if new_category_id and new_category_id != old_category_id and transaction.description:
        categorization_service = CategorizationService(db)
        categorization_service.learn_from_categorization(
            transaction.description,
            new_category_id,
            old_category_id=old_category_id
        )

    db.commit()
    db.refresh(transaction)

    result = TransactionResponse.model_validate(transaction)
    result.account_name = transaction.account.name if transaction.account else None
    if transaction.category:
        result.category_name = transaction.category.name
        result.category_color = transaction.category.color
    return result


@router.patch("/{transaction_id}/category")
def update_transaction_category(
    transaction_id: int,
    category_id: int,
    create_rule: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar apenas a categoria de uma transação."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    old_category_id = transaction.category_id
    transaction.category_id = category_id
    transaction.is_validated = True

    # Aprender com esta categorização (passa old_category_id para decrementar)
    categorization_service = CategorizationService(db)
    categorization_service.learn_from_categorization(
        transaction.description,
        category_id,
        old_category_id=old_category_id
    )

    # Criar regra automática se solicitado
    if create_rule and transaction.description:
        keyword = _extract_rule_keyword(transaction.description)
        _create_or_update_rule(db, keyword, category_id)

    db.commit()
    return {"message": "Categoria atualizada com sucesso"}


@router.patch("/bulk-categorize")
def bulk_categorize(
    data: BulkCategorize,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Categorizar múltiplas transações de uma vez."""
    category = db.query(Category).filter(Category.id == data.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    updated = 0
    categorization_service = CategorizationService(db)
    rule_created = False

    for t_id in data.transaction_ids:
        transaction = db.query(Transaction).filter(Transaction.id == t_id).first()
        if transaction:
            old_category_id = transaction.category_id
            transaction.category_id = data.category_id
            transaction.is_validated = True
            categorization_service.learn_from_categorization(
                transaction.description,
                data.category_id,
                old_category_id=old_category_id
            )

            # Criar regra a partir da primeira transação do grupo
            if not rule_created and transaction.description:
                keyword = _extract_rule_keyword(transaction.description)
                if keyword:
                    _create_or_update_rule(db, keyword, data.category_id)
                    rule_created = True

            updated += 1

    db.commit()
    return {"message": f"{updated} transações atualizadas"}


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Excluir transação."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    # Atualizar saldo da conta
    account = transaction.account
    log_balance_change(db, account, account.current_balance - transaction.amount,
                       'transaction_delete', f'Transaction {transaction.id} deleted')

    db.delete(transaction)
    db.commit()
    return {"message": "Transação excluída com sucesso"}


@router.get("/{transaction_id}/suggestion", response_model=TransactionSuggestion)
def get_category_suggestion(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter sugestão de categoria para uma transação."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    categorization_service = CategorizationService(db)
    category_id, confidence, method = categorization_service.categorize(
        transaction.description,
        float(transaction.amount)
    )

    category_name = None
    if category_id:
        category = db.query(Category).filter(Category.id == category_id).first()
        if category:
            category_name = category.name

    return TransactionSuggestion(
        transaction_id=transaction_id,
        suggested_category_id=category_id,
        suggested_category_name=category_name,
        confidence=confidence,
        method=method
    )
