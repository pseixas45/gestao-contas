"""
Schemas para relatórios de reembolso de despesas.
"""

import re
from decimal import Decimal
from typing import Optional, List
from datetime import datetime, date as date_type
from pydantic import BaseModel, ConfigDict, field_validator


class ExpenseReportCreate(BaseModel):
    reference_month: str  # YYYY-MM
    transaction_ids: List[int]
    notes: Optional[str] = None

    @field_validator('reference_month')
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            raise ValueError('reference_month deve estar no formato YYYY-MM')
        return v


class ExpenseReportUpdate(BaseModel):
    add_transaction_ids: Optional[List[int]] = None
    remove_transaction_ids: Optional[List[int]] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ExpenseReportTransactionItem(BaseModel):
    transaction_id: int
    date: date_type
    description: str
    amount_brl: Decimal
    original_amount: Decimal
    original_currency: str
    installment_info: Optional[str] = None
    account_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseReportSummary(BaseModel):
    id: int
    reference_month: str
    status: str
    total_brl: Decimal
    item_count: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseReportDetail(ExpenseReportSummary):
    items: List[ExpenseReportTransactionItem]


class UnreportedTransaction(BaseModel):
    id: int
    date: date_type
    description: str
    amount_brl: Decimal
    original_amount: Decimal
    original_currency: str
    installment_info: Optional[str] = None
    account_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExpectedItem(BaseModel):
    """Item recorrente esperado no relatório."""
    pattern: str  # descrição normalizada
    sample_description: str  # exemplo real mais recente
    frequency: int  # em quantos dos últimos N relatórios apareceu
    total_reports: int  # N (total de relatórios analisados)
    avg_amount: Decimal
    found: bool  # se existe nas transações não reportadas
    matched_transaction_ids: List[int]  # IDs das transações que deram match


class ExpectedItemsResponse(BaseModel):
    expected: List[ExpectedItem]
    found_count: int
    missing_count: int
