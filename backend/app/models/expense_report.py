"""
Modelos para relatórios de reembolso de despesas de trabalho.
"""

import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class ExpenseReportStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    reimbursed = "reimbursed"


class ExpenseReport(Base):
    __tablename__ = "expense_reports"

    id = Column(Integer, primary_key=True, index=True)
    reference_month = Column(String(7), nullable=False)  # YYYY-MM
    status = Column(Enum(ExpenseReportStatus), default=ExpenseReportStatus.draft, nullable=False)
    notes = Column(String(500), nullable=True)
    total_brl = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("ExpenseReportItem", back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_expense_report_month", "reference_month"),
        Index("idx_expense_report_status", "status"),
    )


class ExpenseReportItem(Base):
    __tablename__ = "expense_report_items"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)

    report = relationship("ExpenseReport", back_populates="items")
    transaction = relationship("Transaction")

    __table_args__ = (
        UniqueConstraint("report_id", "transaction_id", name="uq_report_transaction"),
        Index("idx_report_item_transaction", "transaction_id"),
    )
