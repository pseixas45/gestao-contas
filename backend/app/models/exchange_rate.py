"""
Modelo de taxa de câmbio.

Armazena cotações do Banco Central do Brasil (BCB PTAX).
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Enum, Index
import enum

from app.database import Base


class CurrencyCode(str, enum.Enum):
    """Códigos de moedas suportadas."""
    BRL = "BRL"  # Real Brasileiro
    USD = "USD"  # Dólar Americano
    EUR = "EUR"  # Euro


class ExchangeRate(Base):
    """
    Taxa de câmbio do Banco Central.

    Armazena cotações PTAX do BCB para cache e auditoria.
    Usa a cotação de venda (sell_rate) para conversões.
    """

    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, index=True)

    # Data de referência da cotação
    date_ref = Column(Date, nullable=False)

    # Moeda (USD ou EUR - BRL é a moeda base)
    currency = Column(Enum(CurrencyCode), nullable=False)

    # Cotações
    buy_rate = Column(Numeric(18, 6), nullable=False)   # Cotação de compra
    sell_rate = Column(Numeric(18, 6), nullable=False)  # Cotação de venda (usada para conversão)

    # Metadados do BCB
    bulletin_type = Column(String(20), default="Fechamento")  # Tipo do boletim
    quote_datetime = Column(DateTime, nullable=True)  # dataHoraCotacao do BCB

    # Fonte e auditoria
    source = Column(String(50), default="BCB-PTAX")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Índice único para evitar duplicatas
    __table_args__ = (
        Index('idx_exchange_date_currency', 'date_ref', 'currency', unique=True),
    )

    def __repr__(self):
        return f"<ExchangeRate {self.currency.value} @ {self.date_ref}: {self.sell_rate}>"

    @property
    def rate(self) -> Decimal:
        """Retorna a taxa de venda (usada para conversões)."""
        return self.sell_rate
