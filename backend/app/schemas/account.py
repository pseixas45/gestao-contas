from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal
from typing import Optional
from app.models.account import AccountType
from app.models.exchange_rate import CurrencyCode


class AccountBase(BaseModel):
    bank_id: int
    name: str
    account_number: Optional[str] = None
    account_type: AccountType = AccountType.BANK
    currency: CurrencyCode = CurrencyCode.BRL
    initial_balance: Decimal = Decimal("0.00")


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[AccountType] = None
    currency: Optional[CurrencyCode] = None
    is_active: Optional[bool] = None


class AccountResponse(AccountBase):
    id: int
    current_balance: Decimal
    is_active: bool
    created_at: datetime
    bank_name: Optional[str] = None  # Preenchido na API
    balance_brl: Optional[float] = None  # Saldo equivalente em BRL (para contas não-BRL)

    model_config = ConfigDict(from_attributes=True)


class AccountBalance(BaseModel):
    account_id: int
    current_balance: Decimal
    calculated_balance: Decimal  # Saldo calculado a partir das transações
    difference: Decimal  # Diferença entre os dois
