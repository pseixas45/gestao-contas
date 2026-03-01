from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class CategoryType(str, enum.Enum):
    INCOME = "income"  # Receita
    EXPENSE = "expense"  # Despesa
    TRANSFER = "transfer"  # Transferência


class Category(Base):
    """Modelo de categoria de transação (despesas/receitas)."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(Enum(CategoryType), nullable=False)
    color = Column(String(7), default="#6B7280")  # Cor para identificação visual
    icon = Column(String(50))  # Nome do ícone (lucide-react)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # Subcategorias
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category")
    rules = relationship("CategorizationRule", back_populates="category")
