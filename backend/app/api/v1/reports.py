"""
Endpoints para relatórios multi-moeda.
"""

import json
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.exchange_rate import CurrencyCode
from app.models.saved_report import SavedReportView
from app.schemas.report import (
    MonthlyExpenseReport,
    ExpenseTrendReport,
    BudgetVsActualReport,
    RealPlusProjectedReport,
    IncomeVsExpenseReport,
    AccountsBalanceReport,
    CategoryMonthlyPivotReport,
    SavedReportViewSchema,
    ReportTransactionDetail,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/expenses-monthly/{month}", response_model=MonthlyExpenseReport)
def get_monthly_expenses(
    month: str,
    currency: CurrencyCode = Query(CurrencyCode.BRL, description="Moeda para exibição"),
    account_ids: Optional[str] = Query(None, description="IDs das contas separados por vírgula"),
    db: Session = Depends(get_db)
):
    """Obtém relatório de despesas por categoria em um mês."""
    service = ReportService(db)
    acc_ids = None
    if account_ids:
        acc_ids = [int(x) for x in account_ids.split(",")]
    return service.get_monthly_expenses(month, currency, acc_ids)


@router.get("/expenses-trend", response_model=ExpenseTrendReport)
def get_expense_trend(
    start_month: str = Query(..., description="Mês inicial (YYYY-MM)"),
    end_month: str = Query(..., description="Mês final (YYYY-MM)"),
    currency: CurrencyCode = Query(CurrencyCode.BRL),
    category_ids: Optional[str] = Query(None, description="IDs das categorias"),
    db: Session = Depends(get_db)
):
    """Obtém tendência de despesas por categoria ao longo de vários meses."""
    service = ReportService(db)
    cat_ids = None
    if category_ids:
        cat_ids = [int(x) for x in category_ids.split(",")]
    return service.get_expense_trend(start_month, end_month, currency, cat_ids)


@router.get("/budget-vs-actual/{month}", response_model=BudgetVsActualReport)
def get_budget_vs_actual(
    month: str,
    currency: CurrencyCode = Query(CurrencyCode.BRL),
    db: Session = Depends(get_db)
):
    """Compara orçado vs realizado."""
    service = ReportService(db)
    return service.get_budget_vs_actual(month, currency)


@router.get("/real-plus-projected/{month}", response_model=RealPlusProjectedReport)
def get_real_plus_projected(
    month: str,
    currency: CurrencyCode = Query(CurrencyCode.BRL),
    reference_date: Optional[date] = Query(None, description="Data de referência"),
    db: Session = Depends(get_db)
):
    """Relatório Real + Projetado."""
    service = ReportService(db)
    return service.get_real_plus_projected(month, currency, reference_date)


@router.get("/income-vs-expense", response_model=IncomeVsExpenseReport)
def get_income_vs_expense(
    start_month: str = Query(..., description="Mês inicial"),
    end_month: str = Query(..., description="Mês final"),
    currency: CurrencyCode = Query(CurrencyCode.BRL),
    db: Session = Depends(get_db)
):
    """Relatório de receitas vs despesas."""
    service = ReportService(db)
    return service.get_income_vs_expense(start_month, end_month, currency)


@router.get("/category-monthly-pivot", response_model=CategoryMonthlyPivotReport)
def get_category_monthly_pivot(
    start_month: str = Query(..., description="Mês inicial (YYYY-MM)"),
    end_month: str = Query(..., description="Mês final (YYYY-MM)"),
    currency: CurrencyCode = Query(CurrencyCode.BRL, description="Moeda para exibição"),
    account_ids: Optional[str] = Query(None, description="IDs das contas separados por vírgula"),
    category_ids: Optional[str] = Query(None, description="IDs das categorias separados por vírgula"),
    db: Session = Depends(get_db)
):
    """Relatório pivô: categorias nas linhas, meses nas colunas."""
    service = ReportService(db)
    acc_ids = [int(x) for x in account_ids.split(",")] if account_ids else None
    cat_ids = [int(x) for x in category_ids.split(",")] if category_ids else None
    return service.get_category_monthly_pivot(
        start_month, end_month, currency, acc_ids, cat_ids
    )


@router.get("/transaction-details", response_model=List[ReportTransactionDetail])
def get_transaction_details(
    start_month: str = Query(..., description="Mês inicial (YYYY-MM)"),
    end_month: str = Query(..., description="Mês final (YYYY-MM)"),
    currency: CurrencyCode = Query(CurrencyCode.BRL),
    account_ids: Optional[str] = Query(None),
    category_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Retorna transações individuais para exportação detalhada."""
    service = ReportService(db)
    acc_ids = [int(x) for x in account_ids.split(",")] if account_ids else None
    cat_ids = [int(x) for x in category_ids.split(",")] if category_ids else None
    return service.get_transaction_details(
        start_month, end_month, currency, acc_ids, cat_ids
    )


# --- Saved Report Views ---

@router.get("/saved-views", response_model=List[SavedReportViewSchema])
def list_saved_views(db: Session = Depends(get_db)):
    """Lista todas as visões salvas."""
    views = db.query(SavedReportView).order_by(SavedReportView.name).all()
    return views


@router.post("/saved-views", response_model=SavedReportViewSchema)
def create_saved_view(
    data: SavedReportViewSchema,
    db: Session = Depends(get_db)
):
    """Cria uma nova visão salva."""
    # Validar JSON
    try:
        json.loads(data.filters_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="filters_json inválido")

    view = SavedReportView(name=data.name, filters_json=data.filters_json)
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.put("/saved-views/{view_id}", response_model=SavedReportViewSchema)
def update_saved_view(
    view_id: int,
    data: SavedReportViewSchema,
    db: Session = Depends(get_db)
):
    """Atualiza uma visão salva."""
    view = db.query(SavedReportView).filter(SavedReportView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Visão não encontrada")
    try:
        json.loads(data.filters_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="filters_json inválido")
    view.name = data.name
    view.filters_json = data.filters_json
    db.commit()
    db.refresh(view)
    return view


@router.delete("/saved-views/{view_id}")
def delete_saved_view(view_id: int, db: Session = Depends(get_db)):
    """Exclui uma visão salva."""
    view = db.query(SavedReportView).filter(SavedReportView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Visão não encontrada")
    db.delete(view)
    db.commit()
    return {"ok": True}


@router.get("/accounts-balance", response_model=AccountsBalanceReport)
def get_accounts_balance(db: Session = Depends(get_db)):
    """Obtém saldo atual de todas as contas."""
    service = ReportService(db)
    return service.get_accounts_balance()
