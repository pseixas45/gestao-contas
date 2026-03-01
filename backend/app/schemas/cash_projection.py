"""
Schemas para projeção de caixa.
"""

from pydantic import BaseModel, ConfigDict, field_validator
from decimal import Decimal
from typing import Optional, List
from datetime import date
import re


class CashProjectionItemBase(BaseModel):
    """Base para item de projeção."""
    account_id: int
    date: date
    description: str
    amount_brl: Decimal
    category_id: Optional[int] = None
    is_recurring: bool = False
    recurring_day: Optional[int] = None


class CashProjectionItemCreate(CashProjectionItemBase):
    """Schema para criar item de projeção."""
    pass


class CashProjectionItemUpdate(BaseModel):
    """Schema para atualizar item de projeção."""
    date: Optional[date] = None
    description: Optional[str] = None
    amount_brl: Optional[Decimal] = None
    category_id: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurring_day: Optional[int] = None
    is_confirmed: Optional[bool] = None


class CashProjectionItemResponse(CashProjectionItemBase):
    """Schema de resposta para item de projeção."""
    id: int
    is_confirmed: bool = False
    account_name: Optional[str] = None
    category_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CashProjectionDayBalance(BaseModel):
    """Saldo de um dia específico."""
    date: date
    opening_balance: Decimal  # Saldo no início do dia
    entries: Decimal          # Total de entradas (positivo)
    exits: Decimal            # Total de saídas (negativo)
    closing_balance: Decimal  # Saldo no final do dia


class CashProjectionSummary(BaseModel):
    """Resumo de projeção de caixa para um período."""
    account_id: Optional[int] = None  # None = todas as contas
    account_name: Optional[str] = None
    start_date: date
    end_date: date
    initial_balance: Decimal  # Saldo real até start_date
    total_entries: Decimal
    total_exits: Decimal
    final_balance: Decimal
    min_balance: Decimal      # Menor saldo no período
    min_balance_date: date    # Data do menor saldo
    daily_balances: List[CashProjectionDayBalance]


class CopyMonthRequest(BaseModel):
    """Requisição para copiar itens de um mês para outro."""
    source_month: str  # YYYY-MM
    target_month: str  # YYYY-MM
    account_id: Optional[int] = None  # None = todas as contas

    @field_validator('source_month', 'target_month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('Mês deve estar no formato YYYY-MM')
        return v


class BulkProjectionCreate(BaseModel):
    """Criar múltiplos itens de uma vez."""
    items: List[CashProjectionItemCreate]
