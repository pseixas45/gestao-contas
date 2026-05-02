"""
Endpoints para relatórios multi-moeda.
"""

import json
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.database import get_db
from app.models.exchange_rate import CurrencyCode
from app.models.saved_report import SavedReportView
from app.models.transaction import Transaction
from app.models.account import BankAccount
from app.models.bank import Bank
from app.models.category import Category
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
    DashboardSummary,
    DashboardAccountBalance,
    DashboardTopCategory,
    DashboardMonthEvolution,
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


@router.get("/dashboard-summary", response_model=DashboardSummary)
def get_dashboard_summary(month: str = None, db: Session = Depends(get_db)):
    """Resumo executivo para o dashboard principal."""
    today = date.today()
    if month:
        # Parse YYYY-MM format
        try:
            year, mon = month.split('-')
            month_start = date(int(year), int(mon), 1)
        except (ValueError, IndexError):
            month_start = today.replace(day=1)
    else:
        month_start = today.replace(day=1)
    current_month = month_start.strftime("%Y-%m")

    # === Pré-carregar lookups (evitar N+1) ===
    # Categorias: dict id -> (name, color, type_str)
    all_categories = db.query(Category).all()
    cat_by_id = {
        c.id: (c.name, c.color, str(c.type).replace("CategoryType.", "").lower() if c.type else None)
        for c in all_categories
    }
    # Bancos: dict id -> (name, color)
    all_banks = db.query(Bank).all()
    bank_by_id = {b.id: (b.name, b.color) for b in all_banks}

    # 1. Contas e saldos
    accounts = db.query(BankAccount).filter(BankAccount.is_active == True).all()

    # Buscar últimas taxas de câmbio do cache (1 query por moeda)
    from app.models.exchange_rate import ExchangeRate as ExRate
    latest_rates: dict[str, Decimal] = {}
    for cur in ["USD", "EUR"]:
        rate_row = db.query(ExRate).filter(
            ExRate.currency == cur
        ).order_by(ExRate.date_ref.desc()).first()
        if rate_row and rate_row.sell_rate:
            latest_rates[cur] = rate_row.sell_rate
        else:
            latest_rates[cur] = Decimal("1")

    account_balances = []
    total_brl = Decimal("0")
    for acc in accounts:
        balance = acc.current_balance or Decimal("0")
        cur = acc.currency or "BRL"
        if cur == "BRL":
            bal_brl = balance
        else:
            bal_brl = balance * latest_rates.get(cur, Decimal("1"))
        total_brl += bal_brl
        bank_info = bank_by_id.get(acc.bank_id, ("", None))
        account_balances.append(DashboardAccountBalance(
            account_id=acc.id,
            account_name=acc.name,
            bank_name=bank_info[0],
            bank_color=bank_info[1],
            currency=cur,
            balance=balance,
            balance_brl=bal_brl,
            account_type=acc.account_type or "checking",
        ))

    # 2. Receitas e despesas do mês
    # Usar filtros da visão "Dashboard" salva, ou fallback para IDs fixos
    dashboard_view = db.query(SavedReportView).filter(
        SavedReportView.name == "Dashboard"
    ).first()
    if dashboard_view and dashboard_view.filters_json:
        import json
        filters = dashboard_view.filters_json if isinstance(dashboard_view.filters_json, dict) else json.loads(dashboard_view.filters_json)
        dashboard_cat_ids = set(filters.get("category_ids", []))
    else:
        # Fallback: excluir Aplicação(1), Casamento(2), Desp Trabalho(7), Divórcio(8),
        # Joceline(13), Reembolso Despesas(18), Resgate(22), Transferência(30)
        excluded = {1, 2, 7, 8, 13, 18, 22, 30}
        dashboard_cat_ids = set(cat_by_id.keys()) - excluded

    month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
    # Buscar só os campos necessários para evitar overhead de hidratar todos os campos
    month_txn_rows = db.query(Transaction.category_id, Transaction.amount_brl).filter(
        Transaction.date >= month_start,
        Transaction.date <= month_end,
    ).all()

    month_income = Decimal("0")
    month_expenses = Decimal("0")
    for cat_id, amt_brl in month_txn_rows:
        if not cat_id or cat_id not in dashboard_cat_ids:
            continue
        cat_data = cat_by_id.get(cat_id)
        if not cat_data:
            continue
        amt = amt_brl or Decimal("0")
        cat_type = cat_data[2]
        if cat_type == "income":
            month_income += amt
        elif cat_type == "expense":
            month_expenses += amt

    # Income sums positive values; expenses sums negative values -> negate for display
    month_income = abs(month_income)
    month_expenses = abs(month_expenses)

    # 3. Pendentes
    pending_count = db.query(func.count(Transaction.id)).filter(
        (Transaction.category_id == None) | (Transaction.is_validated == False)
    ).scalar() or 0

    # 4. Top 5 categorias de despesa do mês (usando filtro Dashboard)
    cat_totals: dict[int, Decimal] = {}
    for cat_id, amt_brl in month_txn_rows:
        if not cat_id or cat_id not in dashboard_cat_ids:
            continue
        cat_data = cat_by_id.get(cat_id)
        if cat_data and cat_data[2] == "expense":
            cat_totals[cat_id] = cat_totals.get(cat_id, Decimal("0")) + (amt_brl or Decimal("0"))

    total_cat = abs(sum(cat_totals.values())) or Decimal("1")
    top_cats = sorted(cat_totals.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
    top_categories = [
        DashboardTopCategory(
            category_id=cid,
            category_name=cat_by_id[cid][0],
            category_color=cat_by_id[cid][1],
            amount=abs(amt),
            percentage=float(abs(amt) / total_cat * 100),
        )
        for cid, amt in top_cats
    ]

    # 5. Evolução mensal (últimos 6 meses) — UMA query agregada, sem loop por mês
    evol_start = (month_start - relativedelta(months=5)).replace(day=1)
    evol_end = month_end
    evol_rows = db.query(Transaction.date, Transaction.category_id, Transaction.amount_brl).filter(
        Transaction.date >= evol_start,
        Transaction.date <= evol_end,
    ).all()

    monthly_buckets: dict[str, dict[str, Decimal]] = {}
    for tdate, cat_id, amt_brl in evol_rows:
        if not cat_id or cat_id not in dashboard_cat_ids:
            continue
        cat_data = cat_by_id.get(cat_id)
        if not cat_data:
            continue
        m_str = tdate.strftime("%Y-%m")
        if m_str not in monthly_buckets:
            monthly_buckets[m_str] = {"income": Decimal("0"), "expense": Decimal("0")}
        amt = amt_brl or Decimal("0")
        if cat_data[2] == "income":
            monthly_buckets[m_str]["income"] += amt
        elif cat_data[2] == "expense":
            monthly_buckets[m_str]["expense"] += amt

    monthly_evolution = []
    for i in range(5, -1, -1):
        m_date = month_start - relativedelta(months=i)
        m_str = m_date.strftime("%Y-%m")
        bucket = monthly_buckets.get(m_str, {"income": Decimal("0"), "expense": Decimal("0")})
        m_income = abs(bucket["income"])
        m_expense = abs(bucket["expense"])
        monthly_evolution.append(DashboardMonthEvolution(
            month=m_str,
            income=m_income,
            expense=m_expense,
            balance=m_income - m_expense,
        ))

    return DashboardSummary(
        total_balance_brl=total_brl,
        month_income=month_income,
        month_expenses=month_expenses,
        pending_count=pending_count,
        accounts=account_balances,
        top_categories=top_categories,
        monthly_evolution=monthly_evolution,
    )
