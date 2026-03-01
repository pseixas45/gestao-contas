from pydantic import BaseModel, ConfigDict
import datetime
from decimal import Decimal
from typing import Optional, List

from app.models.exchange_rate import CurrencyCode


class TransactionBase(BaseModel):
    account_id: int
    category_id: Optional[int] = None
    date: datetime.date
    description: str
    amount: Decimal  # Mantido para compatibilidade (alias para amount_brl)


class TransactionCreate(TransactionBase):
    original_description: Optional[str] = None
    balance_after: Optional[Decimal] = None

    # Campos multi-moeda (opcionais na criação manual)
    original_currency: Optional[CurrencyCode] = CurrencyCode.BRL
    original_amount: Optional[Decimal] = None  # Se não informado, usa 'amount'
    amount_brl: Optional[Decimal] = None
    amount_usd: Optional[Decimal] = None
    amount_eur: Optional[Decimal] = None

    # Campos de cartão de crédito
    card_payment_date: Optional[datetime.date] = None
    installment_number: Optional[int] = None
    installment_total: Optional[int] = None


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    date: Optional[datetime.date] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    is_validated: Optional[bool] = None

    # Campos multi-moeda
    original_currency: Optional[CurrencyCode] = None
    original_amount: Optional[Decimal] = None
    amount_brl: Optional[Decimal] = None
    amount_usd: Optional[Decimal] = None
    amount_eur: Optional[Decimal] = None

    # Campos de cartão
    card_payment_date: Optional[datetime.date] = None
    installment_number: Optional[int] = None
    installment_total: Optional[int] = None


class TransactionResponse(TransactionBase):
    id: int
    original_description: Optional[str] = None
    balance_after: Optional[Decimal] = None
    transaction_hash: Optional[str] = None
    is_validated: bool
    import_batch_id: Optional[int] = None
    created_at: datetime.datetime

    # Campos multi-moeda
    original_currency: CurrencyCode = CurrencyCode.BRL
    original_amount: Decimal
    amount_brl: Decimal
    amount_usd: Decimal
    amount_eur: Decimal

    # Campos de cartão de crédito
    card_payment_date: Optional[datetime.date] = None
    installment_number: Optional[int] = None
    installment_total: Optional[int] = None

    # Dados relacionados (preenchidos na API)
    account_name: Optional[str] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None

    # Computed fields
    installment_info: Optional[str] = None  # Ex: "3/10"

    model_config = ConfigDict(from_attributes=True)


class TransactionFilter(BaseModel):
    """Filtros para listagem de transações."""
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    search: Optional[str] = None
    is_validated: Optional[bool] = None
    currency: Optional[CurrencyCode] = None  # Filtrar por moeda
    has_installments: Optional[bool] = None  # Filtrar parcelas
    page: int = 1
    limit: int = 50


class BulkCategorize(BaseModel):
    """Categorização em lote."""
    transaction_ids: List[int]
    category_id: int
    create_rule: bool = False  # Se deve criar regra automática


class TransactionSuggestion(BaseModel):
    """Sugestão de categorização automática."""
    transaction_id: int
    suggested_category_id: Optional[int]
    suggested_category_name: Optional[str]
    confidence: float  # 0.0 a 1.0
    method: str  # 'rule', 'history', 'ml'


class TransactionImportData(BaseModel):
    """Dados de transação para importação."""
    date: datetime.date
    description: str
    original_description: Optional[str] = None

    # Valores (pelo menos um deve estar preenchido)
    valor_brl: Optional[Decimal] = None
    valor_usd: Optional[Decimal] = None
    valor_eur: Optional[Decimal] = None

    # Campos de cartão
    card_payment_date: Optional[datetime.date] = None

    # Categoria (opcional)
    category_name: Optional[str] = None
