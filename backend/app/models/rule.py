from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class MatchType(str, enum.Enum):
    CONTAINS = "contains"  # Descrição contém o padrão
    STARTS_WITH = "starts_with"  # Descrição começa com
    ENDS_WITH = "ends_with"  # Descrição termina com
    EXACT = "exact"  # Correspondência exata
    REGEX = "regex"  # Expressão regular


class CategorizationRule(Base):
    """
    Modelo de regra de categorização automática.

    Permite criar regras como: "Se descrição contém 'UBER', categoria = Transporte"
    """

    __tablename__ = "categorization_rules"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    pattern = Column(String(255), nullable=False)  # Padrão a ser buscado
    match_type = Column(Enum(MatchType), default=MatchType.CONTAINS)
    priority = Column(Integer, default=0)  # Maior prioridade = aplicada primeiro
    is_active = Column(Boolean, default=True)
    hit_count = Column(Integer, default=0)  # Contador de vezes que a regra foi aplicada
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    category = relationship("Category", back_populates="rules")
