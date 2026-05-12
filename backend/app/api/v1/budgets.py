"""
Endpoints para gerenciamento de orçamentos mensais.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.budget import Budget
from app.models.category import Category, CategoryType
from app.models.exchange_rate import CurrencyCode
from app.schemas.budget import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetSuggestion,
    BudgetMonthSummary,
    CopyBudgetRequest,
    BulkBudgetCreate,
    BudgetGridRow,
    BudgetGridResponse,
    BudgetCellUpdate,
)
from app.services.budget_service import BudgetService
from app.services.exchange_service import ExchangeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budgets", tags=["budgets"])


# --- Grid endpoints (novo) ---

@router.get("/grid", response_model=BudgetGridResponse)
def get_budget_grid(
    start_month: str = Query(..., description="Mês inicial (YYYY-MM)"),
    end_month: str = Query(..., description="Mês final (YYYY-MM)"),
    currency: str = Query("BRL", description="Moeda para exibição"),
    db: Session = Depends(get_db)
):
    """Retorna grid pivô de orçamento: categorias × meses."""
    # Gerar lista de meses
    start_year, start_m = map(int, start_month.split('-'))
    end_year, end_m = map(int, end_month.split('-'))
    months = []
    y, m = start_year, start_m
    while (y, m) <= (end_year, end_m):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Coluna de valor conforme moeda
    amount_col = "amount_brl"
    if currency == "USD":
        amount_col = "amount_usd"
    elif currency == "EUR":
        amount_col = "amount_eur"

    # Buscar todos os budgets no range
    budgets = db.query(Budget).filter(
        Budget.month >= start_month,
        Budget.month <= end_month,
    ).all()

    # Buscar todas as categorias ativas
    all_categories = db.query(Category).filter(Category.is_active == True).order_by(Category.name).all()

    # Calcular média dos últimos 3 meses de transações reais (antes do start_month)
    from app.models.transaction import Transaction
    from dateutil.relativedelta import relativedelta
    from sqlalchemy import func, extract

    start_date_parsed = date(start_year, start_m, 1)
    avg_end = start_date_parsed - relativedelta(days=1)  # último dia do mês anterior
    avg_start = (start_date_parsed - relativedelta(months=3))  # 3 meses antes

    avg_amount_col = getattr(Transaction, amount_col)
    avg_query = db.query(
        Transaction.category_id,
        func.sum(avg_amount_col).label("total_amount"),
    ).filter(
        Transaction.date >= avg_start,
        Transaction.date <= avg_end,
        Transaction.category_id.isnot(None),
    ).group_by(Transaction.category_id).all()

    avg_map = {}
    for row in avg_query:
        avg_map[row.category_id] = row.total_amount / Decimal("3")

    # Montar mapa: {category_id: {month: amount}}
    budget_map = {}
    for b in budgets:
        if b.category_id not in budget_map:
            budget_map[b.category_id] = {}
        budget_map[b.category_id][b.month] = getattr(b, amount_col)

    # Montar linhas para TODAS as categorias ativas
    expense_rows = []
    income_rows = []
    transfer_rows = []

    for cat in all_categories:
        cat_values = budget_map.get(cat.id, {})
        values = {}
        total = Decimal("0.00")
        for mo in months:
            val = cat_values.get(mo, Decimal("0.00"))
            values[mo] = val
            total += val

        row = BudgetGridRow(
            category_id=cat.id,
            category_name=cat.name,
            category_type=cat.type.value if cat.type else "expense",
            category_color=cat.color,
            values=values,
            total=total,
            avg_3m=avg_map.get(cat.id),
        )

        if cat.type == CategoryType.EXPENSE:
            expense_rows.append(row)
        elif cat.type == CategoryType.INCOME:
            income_rows.append(row)
        elif cat.type == CategoryType.TRANSFER:
            transfer_rows.append(row)

    expense_total = sum(r.total for r in expense_rows)
    income_total = sum(r.total for r in income_rows)
    transfer_total = sum(r.total for r in transfer_rows)

    return BudgetGridResponse(
        months=months,
        currency=currency,
        expense_rows=expense_rows,
        expense_total=expense_total,
        income_rows=income_rows,
        income_total=income_total,
        transfer_rows=transfer_rows,
        transfer_total=transfer_total,
        grand_total=expense_total + income_total + transfer_total,
    )


@router.put("/cell")
async def update_budget_cell(
    data: BudgetCellUpdate,
    db: Session = Depends(get_db)
):
    """Atualizar uma célula do grid (upsert com conversão multi-moeda)."""
    input_currency = CurrencyCode(data.currency)
    amount = data.amount

    # Definir valores por moeda
    amount_brl = Decimal("0.00")
    amount_usd = Decimal("0.00")
    amount_eur = Decimal("0.00")

    if input_currency == CurrencyCode.BRL:
        amount_brl = amount
    elif input_currency == CurrencyCode.USD:
        amount_usd = amount
    elif input_currency == CurrencyCode.EUR:
        amount_eur = amount

    # Converter para as outras moedas usando 1o dia do mês como referência
    year, month_num = map(int, data.month.split('-'))
    ref_date = date(year, month_num, 1)
    exchange_service = ExchangeService(db)

    try:
        if input_currency == CurrencyCode.BRL:
            amount_usd = await exchange_service.convert(amount, CurrencyCode.BRL, CurrencyCode.USD, ref_date)
            amount_eur = await exchange_service.convert(amount, CurrencyCode.BRL, CurrencyCode.EUR, ref_date)
        elif input_currency == CurrencyCode.USD:
            amount_brl = await exchange_service.convert(amount, CurrencyCode.USD, CurrencyCode.BRL, ref_date)
            amount_eur = await exchange_service.convert(amount, CurrencyCode.USD, CurrencyCode.EUR, ref_date)
        elif input_currency == CurrencyCode.EUR:
            amount_brl = await exchange_service.convert(amount, CurrencyCode.EUR, CurrencyCode.BRL, ref_date)
            amount_usd = await exchange_service.convert(amount, CurrencyCode.EUR, CurrencyCode.USD, ref_date)
    except ValueError as e:
        logger.warning(f"Erro ao buscar câmbio para orçamento: {e}")

    # Upsert
    existing = db.query(Budget).filter(
        Budget.month == data.month,
        Budget.category_id == data.category_id,
    ).first()

    if amount == Decimal("0.00") and existing:
        # Valor zero = remover orçamento
        db.delete(existing)
        db.commit()
        return {"ok": True, "action": "deleted"}

    if existing:
        existing.amount_brl = amount_brl
        existing.amount_usd = amount_usd
        existing.amount_eur = amount_eur
        existing.input_currency = data.currency
    else:
        if amount == Decimal("0.00"):
            return {"ok": True, "action": "skipped"}
        budget = Budget(
            month=data.month,
            category_id=data.category_id,
            amount_brl=amount_brl,
            amount_usd=amount_usd,
            amount_eur=amount_eur,
            input_currency=data.currency,
        )
        db.add(budget)

    db.commit()
    return {
        "ok": True,
        "action": "updated" if existing else "created",
        "amount_brl": float(amount_brl),
        "amount_usd": float(amount_usd),
        "amount_eur": float(amount_eur),
    }


# --- Existing endpoints ---

@router.post("/", response_model=BudgetResponse)
def create_budget(
    budget_data: BudgetCreate,
    db: Session = Depends(get_db)
):
    """
    Cria ou atualiza um orçamento para uma categoria em um mês.

    Se já existir orçamento para a mesma categoria/mês, atualiza o valor.
    """
    service = BudgetService(db)
    budget = service.create(budget_data)

    category = db.query(Category).filter(Category.id == budget.category_id).first()

    return BudgetResponse(
        id=budget.id,
        month=budget.month,
        category_id=budget.category_id,
        amount_brl=budget.amount_brl,
        category_name=category.name if category else None,
        category_color=category.color if category else None
    )


@router.post("/bulk")
def create_budgets_bulk(
    data: BulkBudgetCreate,
    db: Session = Depends(get_db)
):
    """Cria múltiplos orçamentos de uma vez."""
    service = BudgetService(db)
    created = []

    for item in data.budgets:
        budget = service.create(BudgetCreate(
            month=data.month,
            category_id=item['category_id'],
            amount_brl=item['amount_brl']
        ))
        created.append(budget.id)

    return {"created_count": len(created), "budget_ids": created}


@router.get("/month/{month}", response_model=List[BudgetResponse])
def get_budgets_by_month(
    month: str,
    db: Session = Depends(get_db)
):
    """Obtém todos os orçamentos de um mês específico."""
    service = BudgetService(db)
    return service.get_by_month(month)


@router.get("/suggestions/{month}", response_model=List[BudgetSuggestion])
def get_budget_suggestions(
    month: str,
    db: Session = Depends(get_db)
):
    """Obtém sugestões de orçamento baseadas na média dos últimos 3 meses."""
    service = BudgetService(db)
    return service.get_suggestions(month)


@router.get("/comparison/{month}", response_model=BudgetMonthSummary)
def get_budget_comparison(
    month: str,
    db: Session = Depends(get_db)
):
    """Compara orçado vs realizado para um mês."""
    service = BudgetService(db)
    return service.get_comparison(month)


@router.put("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int,
    budget_data: BudgetUpdate,
    db: Session = Depends(get_db)
):
    """Atualiza um orçamento existente."""
    service = BudgetService(db)
    budget = service.update(budget_id, budget_data)

    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")

    category = db.query(Category).filter(Category.id == budget.category_id).first()

    return BudgetResponse(
        id=budget.id,
        month=budget.month,
        category_id=budget.category_id,
        amount_brl=budget.amount_brl,
        category_name=category.name if category else None,
        category_color=category.color if category else None
    )


@router.delete("/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db)
):
    """Remove um orçamento."""
    service = BudgetService(db)
    success = service.delete(budget_id)

    if not success:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")

    return {"success": True}


@router.post("/copy")
def copy_budgets(
    data: CopyBudgetRequest,
    db: Session = Depends(get_db)
):
    """Copia orçamentos de um mês para outro."""
    service = BudgetService(db)
    created = service.copy_month(data.source_month, data.target_month)

    return {
        "success": True,
        "copied_count": len(created),
        "source_month": data.source_month,
        "target_month": data.target_month
    }


@router.post("/from-suggestions/{month}")
def create_from_suggestions(
    month: str,
    db: Session = Depends(get_db)
):
    """Cria orçamentos automaticamente a partir das sugestões."""
    service = BudgetService(db)
    created = service.create_from_suggestions(month)

    return {
        "success": True,
        "created_count": len(created),
        "month": month
    }


@router.get("/installment-projections")
def get_installment_projections(
    db: Session = Depends(get_db)
):
    """
    Projeção de parcelas futuras.

    Busca todas as transações parceladas onde installment_number < installment_total,
    calcula as parcelas restantes com datas projetadas, e retorna em formato pivot
    (categoria × mês) com detalhamento por lançamento.
    """
    from app.models.transaction import Transaction
    from app.models.account import BankAccount
    from collections import defaultdict
    from dateutil.relativedelta import relativedelta

    import re

    # Buscar TODAS as transações parceladas (realizadas + com parcelas futuras)
    all_installments = db.query(Transaction).filter(
        Transaction.installment_number.isnot(None),
        Transaction.installment_total.isnot(None),
        Transaction.installment_total > 1
    ).all()

    # Agrupar por (conta + descrição base + total parcelas + valor arredondado)
    # Arredonda para inteiro para tolerar diferença de centavos entre parcelas
    # (ex: 1/4=383.61, 2/4=383.60 são a mesma compra)
    # Ainda separa compras genuinamente diferentes (ex: Positivo R$414 vs R$1241)
    groups_map = defaultdict(list)
    for t in all_installments:
        desc_clean = re.sub(r'\s*\d{1,2}\s*(?:de|/)\s*\d{1,2}\s*$', '', t.description).strip()
        amt_key = round(abs(float(t.amount_brl)))
        group_key = (t.account_id, desc_clean.upper(), t.installment_total, amt_key)
        groups_map[group_key].append(t)

    projections = []

    for (account_id, desc_upper, inst_total, amt_key), txns in groups_map.items():
        # Ordenar por installment_number
        txns.sort(key=lambda x: x.installment_number)

        # Determinar quantas compras paralelas existem no grupo
        # (ex: 2x L293 Shopping 724.50 10/10 = 2 compras distintas)
        from collections import Counter
        count_per_number = Counter(t.installment_number for t in txns)
        num_purchases = max(count_per_number.values())

        latest = txns[-1]
        category_id = latest.category_id
        category_name = latest.category.name if latest.category else "Sem categoria"
        category_color = latest.category.color if latest.category else None
        account_name = latest.account.name if latest.account else None
        desc_clean = re.sub(r'\s*\d{1,2}\s*(?:de|/)\s*\d{1,2}\s*$', '', latest.description).strip()

        # Parcelas realizadas — incluir todas as transações do banco
        realized_numbers = set()
        for t in txns:
            realized_numbers.add(t.installment_number)
            t_month = f"{t.date.year:04d}-{t.date.month:02d}"
            projections.append({
                "month": t_month,
                "category_id": category_id,
                "category_name": category_name,
                "category_color": category_color,
                "account_name": account_name,
                "description": desc_clean,
                "amount_brl": abs(float(t.amount_brl)),
                "installment_info": f"{t.installment_number}/{inst_total}",
                "status": "realized",
                "original_transaction_id": t.id,
            })

        # Parcelas futuras — projetar para cada compra paralela
        if latest.installment_number < inst_total:
            base_amount = abs(float(latest.amount_brl))
            base_date = latest.date
            for future_n in range(latest.installment_number + 1, inst_total + 1):
                if future_n in realized_numbers:
                    continue
                months_ahead = future_n - latest.installment_number
                future_date = base_date + relativedelta(months=months_ahead)
                future_month = f"{future_date.year:04d}-{future_date.month:02d}"
                for _ in range(num_purchases):
                    projections.append({
                        "month": future_month,
                        "category_id": category_id,
                        "category_name": category_name,
                        "category_color": category_color,
                        "account_name": account_name,
                        "description": desc_clean,
                        "amount_brl": base_amount,
                        "installment_info": f"{future_n}/{inst_total}",
                        "status": "projected",
                        "original_transaction_id": latest.id,
                    })

    # Organizar por mês
    all_months = sorted(set(p["month"] for p in projections))

    # Organizar por categoria com detalhes
    categories_data = defaultdict(lambda: {"items": [], "months": defaultdict(float)})

    for p in projections:
        key = p["category_id"] or 0
        cat = categories_data[key]
        cat["category_id"] = p["category_id"]
        cat["category_name"] = p["category_name"]
        cat["category_color"] = p["category_color"]
        cat["items"].append(p)
        cat["months"][p["month"]] += p["amount_brl"]

    # Montar resposta
    rows = []
    for key in sorted(categories_data.keys(), key=lambda k: categories_data[k]["category_name"]):
        cat = categories_data[key]
        # Detalhamento: agrupar items por descrição+conta
        detail_key = defaultdict(lambda: {"months": defaultdict(float), "items": []})
        for item in cat["items"]:
            dk = f"{item['description']}|{item['account_name'] or ''}"
            detail_key[dk]["description"] = item["description"]
            detail_key[dk]["account_name"] = item["account_name"]
            detail_key[dk]["months"][item["month"]] += item["amount_brl"]
            detail_key[dk]["items"].append({
                "month": item["month"],
                "amount_brl": item["amount_brl"],
                "installment_info": item["installment_info"],
                "status": item.get("status", "projected"),
            })

        details = []
        for dk_data in sorted(detail_key.values(), key=lambda x: x["description"]):
            details.append({
                "description": dk_data["description"],
                "account_name": dk_data["account_name"],
                "months": dict(dk_data["months"]),
                "total": sum(dk_data["months"].values()),
                "items": dk_data["items"],
            })

        rows.append({
            "category_id": cat["category_id"],
            "category_name": cat["category_name"],
            "category_color": cat["category_color"],
            "months": dict(cat["months"]),
            "total": sum(cat["months"].values()),
            "details": details,
        })

    # Totais por mês
    month_totals = {}
    for m in all_months:
        month_totals[m] = sum(r["months"].get(m, 0) for r in rows)

    return {
        "months": all_months,
        "rows": rows,
        "month_totals": month_totals,
        "grand_total": sum(month_totals.values()),
    }


@router.post("/from-installment-projections")
def copy_projections_to_budget(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Copia projeções de parcelas para o orçamento.

    Recebe: { "items": [ { "month": "YYYY-MM", "category_id": int, "amount_brl": float } ] }
    Para cada item, faz upsert no orçamento (soma ao valor existente ou cria novo).
    """
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Nenhum item para copiar")

    created = 0
    updated = 0

    for item in items:
        month = item["month"]
        category_id = item["category_id"]
        amount = Decimal(str(item["amount_brl"]))

        existing = db.query(Budget).filter(
            Budget.month == month,
            Budget.category_id == category_id
        ).first()

        if existing:
            existing.amount_brl = amount
            existing.updated_at = date.today()
            updated += 1
        else:
            budget = Budget(
                month=month,
                category_id=category_id,
                amount_brl=amount,
                amount_usd=Decimal("0"),
                amount_eur=Decimal("0"),
                input_currency="BRL",
            )
            db.add(budget)
            created += 1

    db.commit()

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "total": len(items),
    }
