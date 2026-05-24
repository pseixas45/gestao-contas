"""Modelo para dados de mercado (CDI, IPCA, etc.) do Banco Central."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Numeric,
    Enum, Index, UniqueConstraint
)
import enum
from app.database import Base


class MarketIndexCode(str, enum.Enum):
    """Índices de mercado rastreados."""
    CDI = "CDI"
    IPCA = "IPCA"
    SELIC = "SELIC"
    IGPM = "IGPM"


class MarketIndexRate(Base):
    """Taxa de índice de mercado numa data específica."""

    __tablename__ = "market_index_rates"

    id = Column(Integer, primary_key=True, index=True)
    index_code = Column(Enum(MarketIndexCode), nullable=False)
    date_ref = Column(Date, nullable=False)
    daily_rate = Column(Numeric(18, 10), nullable=True)   # Taxa diária (CDI, SELIC)
    monthly_rate = Column(Numeric(10, 6), nullable=True)  # Taxa mensal (IPCA, IGPM)
    accumulated_year = Column(Numeric(10, 6), nullable=True)
    source = Column(String(50), default="BCB")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date_ref", "index_code", name="uq_market_date_code"),
        Index("idx_market_date_code", "date_ref", "index_code"),
    )
