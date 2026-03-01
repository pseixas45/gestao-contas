"""
Schemas Pydantic para câmbio.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from app.models.exchange_rate import CurrencyCode


class ExchangeRateResponse(BaseModel):
    """Resposta com taxa de câmbio."""
    id: int
    date_ref: date
    currency: CurrencyCode
    buy_rate: Decimal
    sell_rate: Decimal
    bulletin_type: str
    quote_datetime: Optional[datetime] = None
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExchangeRateQuery(BaseModel):
    """Query para buscar taxa de câmbio."""
    date: date
    currency: CurrencyCode


class ConversionRequest(BaseModel):
    """Request para conversão de moeda."""
    amount: Decimal
    from_currency: CurrencyCode
    to_currency: CurrencyCode
    date_ref: date


class ConversionResponse(BaseModel):
    """Resposta de conversão de moeda."""
    original_amount: Decimal
    original_currency: CurrencyCode
    converted_amount: Decimal
    converted_currency: CurrencyCode
    date_ref: date
    rate_used: Optional[Decimal] = None


class UpdateRatesRequest(BaseModel):
    """Request para atualizar cotações em lote."""
    start_date: date
    end_date: date


class UpdateRatesResponse(BaseModel):
    """Resposta de atualização em lote."""
    total_days: int
    usd_updated: int
    eur_updated: int
    errors: List[str]


class AllRatesResponse(BaseModel):
    """Resposta com todas as cotações de um dia."""
    date_ref: date
    usd: Optional[ExchangeRateResponse] = None
    eur: Optional[ExchangeRateResponse] = None
