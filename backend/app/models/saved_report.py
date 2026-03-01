from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class SavedReportView(Base):
    """Visão salva de relatório com filtros."""

    __tablename__ = "saved_report_views"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    filters_json = Column(Text, nullable=False)  # JSON com os filtros
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
