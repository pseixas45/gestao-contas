"""
Modelo de Orçamento Mensal.

Permite definir limites de gastos por categoria para cada mês.
Suporta sugestão automática baseada na média dos últimos 3 meses.
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Budget(Base):
    """
    Modelo de orçamento mensal por categoria.

    Attributes:
        month: Mês de referência no formato YYYY-MM
        category_id: ID da categoria
        amount_brl: Valor orçado em BRL
    """

    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(7), nullable=False)  # YYYY-MM
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    amount_brl = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    amount_usd = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    amount_eur = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    input_currency = Column(String(3), nullable=False, default="BRL")

    # Campos de auditoria
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    category = relationship("Category", backref="budgets")

    # Índices e constraints
    __table_args__ = (
        UniqueConstraint('month', 'category_id', name='uq_budget_month_category'),
        Index('idx_budget_month', 'month'),
    )

    def __repr__(self):
        return f"<Budget {self.month} - {self.category_id}: {self.amount_brl}>"
