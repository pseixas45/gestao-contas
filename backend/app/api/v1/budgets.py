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
