"""
Log de auditoria de alterações de saldo das contas.
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from app.database import Base


class AccountBalanceLog(Base):
    """Registra toda alteração de current_balance em bank_accounts."""

    __tablename__ = "account_balance_logs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    old_balance = Column(Numeric(15, 2), nullable=False)
    new_balance = Column(Numeric(15, 2), nullable=False)
    change_amount = Column(Numeric(15, 2), nullable=False)
    reason = Column(String(50), nullable=False)  # 'import', 'transaction_create', 'transaction_update', 'transaction_delete', 'recalculate', 'manual'
    detail = Column(String(500), nullable=True)  # Ex: "Import batch 42", "Transaction 1234 created"
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("BankAccount")

    __table_args__ = (
        Index('idx_balance_log_account', 'account_id'),
        Index('idx_balance_log_created', 'created_at'),
    )

    def __repr__(self):
        return f"<BalanceLog {self.account_id} {self.old_balance}->{self.new_balance} ({self.reason})>"
