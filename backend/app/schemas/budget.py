"""
Schemas para orçamento mensal.
"""

from pydantic import BaseModel, ConfigDict, field_validator
from decimal import Decimal
from typing import Optional, List
from datetime import date
import re


class BudgetBase(BaseModel):
    """Base para orçamento."""
    month: str  # YYYY-MM
    category_id: int
    amount_brl: Decimal

    @field_validator('month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        """Valida formato YYYY-MM."""
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v


class BudgetCreate(BudgetBase):
    """Schema para criar orçamento."""
    pass


class BudgetUpdate(BaseModel):
    """Schema para atualizar orçamento."""
    amount_brl: Decimal


class BudgetResponse(BudgetBase):
    """Schema de resposta com dados do orçamento."""
    id: int
    category_name: Optional[str] = None
    category_color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BudgetSuggestion(BaseModel):
    """Sugestão de orçamento baseada em histórico."""
    category_id: int
    category_name: str
    suggested_amount: Decimal
    average_last_3_months: Decimal
    month_1_amount: Optional[Decimal] = None  # Mês mais recente
    month_2_amount: Optional[Decimal] = None
    month_3_amount: Optional[Decimal] = None


class BudgetComparison(BaseModel):
    """Comparação orçado vs realizado."""
    category_id: int
    category_name: str
    category_color: Optional[str] = None
    budgeted: Decimal
    actual: Decimal
    difference: Decimal  # Positivo = abaixo do orçamento, Negativo = acima
    percentage: float  # Percentual utilizado (actual/budgeted * 100)


class BudgetMonthSummary(BaseModel):
    """Resumo do orçamento de um mês."""
    month: str
    total_budgeted: Decimal
    total_actual: Decimal
    total_difference: Decimal
    overall_percentage: float
    categories: List[BudgetComparison]


class BulkBudgetCreate(BaseModel):
    """Criar múltiplos orçamentos de uma vez."""
    month: str
    budgets: List[dict]  # Lista de {category_id: int, amount_brl: Decimal}

    @field_validator('month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v


class CopyBudgetRequest(BaseModel):
    """Requisição para copiar orçamento de um mês para outro."""
    source_month: str
    target_month: str

    @field_validator('source_month', 'target_month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v


# --- Grid (pivot) schemas ---

class BudgetGridRow(BaseModel):
    """Uma linha do grid de orçamento: categoria com valores por mês."""
    category_id: int
    category_name: str
    category_type: str
    category_color: Optional[str] = None
    values: dict[str, Decimal]  # {"2026-01": 1500.00, ...}
    total: Decimal


class BudgetGridResponse(BaseModel):
    """Resposta do grid de orçamento (formato pivô)."""
    months: List[str]
    currency: str
    expense_rows: List[BudgetGridRow]
    expense_total: Decimal
    income_rows: List[BudgetGridRow]
    income_total: Decimal
    transfer_rows: List[BudgetGridRow]
    transfer_total: Decimal
    grand_total: Decimal


class BudgetCellUpdate(BaseModel):
    """Atualizar uma célula do grid de orçamento."""
    month: str
    category_id: int
    amount: Decimal
    currency: str = "BRL"

    @field_validator('month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v
