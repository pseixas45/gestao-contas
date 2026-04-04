"""
Schemas para relatórios multi-moeda.
"""

from pydantic import BaseModel, ConfigDict, field_validator
from decimal import Decimal
from typing import Optional, List
from datetime import date
import re

from app.models.exchange_rate import CurrencyCode


class MonthlyExpense(BaseModel):
    """Despesa por categoria em um mês."""
    category_id: int
    category_name: str
    category_color: Optional[str] = None
    amount: Decimal  # Na moeda selecionada
    percentage: float  # Percentual do total


class MonthlyExpenseReport(BaseModel):
    """Relatório de despesas mensais."""
    month: str  # YYYY-MM
    currency: CurrencyCode
    total: Decimal
    categories: List[MonthlyExpense]


class ExpenseTrend(BaseModel):
    """Tendência de despesas ao longo do tempo."""
    month: str  # YYYY-MM
    amount: Decimal


class CategoryTrend(BaseModel):
    """Tendência de uma categoria ao longo do tempo."""
    category_id: int
    category_name: str
    category_color: Optional[str] = None
    months: List[ExpenseTrend]
    average: Decimal


class ExpenseTrendReport(BaseModel):
    """Relatório de tendência de despesas."""
    start_month: str
    end_month: str
    currency: CurrencyCode
    categories: List[CategoryTrend]


class BudgetVsActualItem(BaseModel):
    """Comparação orçado vs realizado por categoria."""
    category_id: int
    category_name: str
    category_color: Optional[str] = None
    budgeted: Decimal
    actual: Decimal
    difference: Decimal
    percentage: float  # Percentual utilizado
    status: str  # "ok", "warning", "over"


class BudgetVsActualReport(BaseModel):
    """Relatório orçado vs realizado."""
    month: str
    currency: CurrencyCode
    total_budgeted: Decimal
    total_actual: Decimal
    total_difference: Decimal
    overall_percentage: float
    items: List[BudgetVsActualItem]


class ProjectedExpense(BaseModel):
    """Despesa projetada."""
    category_id: int
    category_name: str
    projected: Decimal  # Valor projetado (orçamento)
    actual: Decimal     # Valor realizado até agora
    expected_total: Decimal  # Projeção final do mês


class RealPlusProjectedReport(BaseModel):
    """
    Relatório Versão 1: Real + Projetado.

    Mostra gastos reais até a data atual + projeção para o resto do mês.
    """
    month: str
    currency: CurrencyCode
    reference_date: date  # Data de referência (hoje ou fim do mês)
    total_actual: Decimal
    total_projected: Decimal
    total_expected: Decimal
    items: List[ProjectedExpense]


class IncomeVsExpenseMonth(BaseModel):
    """Receita vs Despesa de um mês."""
    month: str
    income: Decimal
    expense: Decimal
    balance: Decimal


class IncomeVsExpenseReport(BaseModel):
    """Relatório de receitas vs despesas."""
    start_month: str
    end_month: str
    currency: CurrencyCode
    months: List[IncomeVsExpenseMonth]
    total_income: Decimal
    total_expense: Decimal
    total_balance: Decimal


class AccountBalanceReport(BaseModel):
    """Saldo das contas."""
    account_id: int
    account_name: str
    bank_name: str
    currency: CurrencyCode
    balance: Decimal
    balance_brl: Decimal  # Saldo convertido para BRL


class AccountsBalanceReport(BaseModel):
    """Relatório de saldo de todas as contas."""
    accounts: List[AccountBalanceReport]
    total_brl: Decimal


class ReportFilter(BaseModel):
    """Filtros comuns para relatórios."""
    start_month: Optional[str] = None
    end_month: Optional[str] = None
    currency: CurrencyCode = CurrencyCode.BRL
    account_ids: Optional[List[int]] = None
    category_ids: Optional[List[int]] = None

    @field_validator('start_month', 'end_month')
    @classmethod
    def validate_month(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v


class CategoryMonthlyRow(BaseModel):
    """Uma linha do relatório pivô: categoria com valores por mês."""
    category_id: int
    category_name: str
    category_type: str  # "expense", "income", "transfer"
    category_color: Optional[str] = None
    values: dict[str, Decimal]  # {"2025-01": 1234.56, ...}
    total: Decimal


class CategoryGroupTotals(BaseModel):
    """Totais de um grupo (despesas ou receitas)."""
    values: dict[str, Decimal]
    total: Decimal


class CategoryMonthlyPivotReport(BaseModel):
    """Relatório pivô: categorias × meses, agrupado por tipo."""
    start_month: str
    end_month: str
    currency: CurrencyCode
    months: List[str]
    expense_rows: List[CategoryMonthlyRow]
    expense_totals: CategoryGroupTotals
    income_rows: List[CategoryMonthlyRow]
    income_totals: CategoryGroupTotals
    transfer_rows: List[CategoryMonthlyRow]
    transfer_totals: CategoryGroupTotals
    column_totals: dict[str, Decimal]  # Net total por mês (despesas - receitas)
    grand_total: Decimal


class SavedReportViewSchema(BaseModel):
    """Visão salva de relatório."""
    id: Optional[int] = None
    name: str
    filters_json: str  # JSON string com filtros

    model_config = ConfigDict(from_attributes=True)


class ReportTransactionDetail(BaseModel):
    """Transação individual para exportação detalhada."""
    date: str
    description: str
    category_name: Optional[str] = None
    category_type: Optional[str] = None
    account_name: Optional[str] = None
    original_amount: Decimal
    original_currency: str
    amount_brl: Decimal
    amount_usd: Decimal
    amount_eur: Decimal


# --- Dashboard Summary ---

class DashboardAccountBalance(BaseModel):
    account_id: int
    account_name: str
    bank_name: str
    bank_color: Optional[str] = None
    currency: str
    balance: Decimal
    balance_brl: Decimal
    account_type: str

class DashboardTopCategory(BaseModel):
    category_id: int
    category_name: str
    category_color: Optional[str] = None
    amount: Decimal
    percentage: float

class DashboardMonthEvolution(BaseModel):
    month: str
    income: Decimal
    expense: Decimal
    balance: Decimal

class DashboardSummary(BaseModel):
    total_balance_brl: Decimal
    month_income: Decimal
    month_expenses: Decimal
    pending_count: int
    accounts: List[DashboardAccountBalance]
    top_categories: List[DashboardTopCategory]
    monthly_evolution: List[DashboardMonthEvolution]
