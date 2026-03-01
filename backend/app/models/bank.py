from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class Bank(Base):
    """Modelo de banco (Itaú, Bradesco, Nubank, etc.)."""

    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(10), unique=True, index=True)  # Código do banco (341, 237, etc.)
    color = Column(String(7), default="#000000")  # Cor para identificação visual
    logo_url = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    accounts = relationship("BankAccount", back_populates="bank")
