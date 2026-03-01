"""
Modelo de Projeção de Caixa.

Permite criar itens de projeção para visualizar saldo futuro.
Suporta cópia de mês para mês.
Valores sempre em BRL.
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Numeric, Boolean, Index
from sqlalchemy.orm import relationship
from app.database import Base


class CashProjectionItem(Base):
    """
    Item de projeção de caixa.

    Representa uma entrada ou saída projetada para uma data específica.
    Valores sempre em BRL para simplificar a consolidação.
    """

    __tablename__ = "cash_projection_items"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String(500), nullable=False)
    amount_brl = Column(Numeric(15, 2), nullable=False)  # Positivo = entrada, Negativo = saída
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Campos de controle
    is_recurring = Column(Boolean, default=False)  # Se é item recorrente
    recurring_day = Column(Integer, nullable=True)  # Dia do mês para recorrência
    is_confirmed = Column(Boolean, default=False)  # Se já foi confirmado/realizado

    # Campos de auditoria
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    account = relationship("BankAccount")
    category = relationship("Category")

    # Índices
    __table_args__ = (
        Index('idx_cash_projection_date', 'date'),
        Index('idx_cash_projection_account_date', 'account_id', 'date'),
    )

    def __repr__(self):
        return f"<CashProjectionItem {self.date} {self.description}: {self.amount_brl}>"
