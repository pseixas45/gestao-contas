"""
Import Template - salva mapeamento de colunas por conta para reutilização.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class ImportTemplate(Base):
    __tablename__ = "import_templates"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False, unique=True)
    column_mapping = Column(Text, nullable=False)  # JSON string
    file_format_hints = Column(Text, nullable=True)  # JSON: {delimiter, encoding, skip_rows}
    last_used_at = Column(DateTime, default=datetime.utcnow)
    success_count = Column(Integer, default=0)

    account = relationship("BankAccount")
