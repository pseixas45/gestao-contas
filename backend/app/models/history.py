from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from app.database import Base


class CategorizationHistory(Base):
    """
    Histórico de categorizações para aprendizado automático.

    Armazena descrições normalizadas e suas categorias para usar
    em categorizações futuras de transações similares.
    """

    __tablename__ = "categorization_history"

    id = Column(Integer, primary_key=True, index=True)
    description_normalized = Column(String(500), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    confidence_score = Column(Numeric(5, 4), default=1.0)  # 0.0000 a 1.0000
    times_used = Column(Integer, default=1)  # Quantas vezes esta categorização foi usada
    last_used_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    category = relationship("Category")

    # Índice único para evitar duplicatas
    __table_args__ = (
        Index("idx_history_desc_cat", "description_normalized", "category_id", unique=True),
    )
