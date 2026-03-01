from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class ImportStatus(str, enum.Enum):
    PENDING = "pending"  # Aguardando processamento
    PROCESSING = "processing"  # Em processamento
    COMPLETED = "completed"  # Concluído com sucesso
    COMPLETED_WITH_DUPLICATES = "completed_with_duplicates"  # Concluído, mas havia duplicatas
    FAILED = "failed"  # Falhou


class FileType(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class ImportBatch(Base):
    """
    Modelo de lote de importação.

    Registra cada importação de arquivo com estatísticas
    de sucesso, duplicatas encontradas, etc.
    """

    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)

    # Estatísticas
    total_records = Column(Integer, default=0)  # Total de linhas no arquivo
    imported_records = Column(Integer, default=0)  # Linhas importadas com sucesso
    duplicate_records = Column(Integer, default=0)  # Linhas ignoradas por serem duplicatas
    error_records = Column(Integer, default=0)  # Linhas com erro

    # Período coberto pela importação
    date_start = Column(Date, nullable=True)  # Data mais antiga no lote
    date_end = Column(Date, nullable=True)    # Data mais recente no lote

    status = Column(Enum(ImportStatus), default=ImportStatus.PENDING)
    error_message = Column(Text)  # Mensagem de erro detalhada

    # Dados temporários (caminho do arquivo durante processamento)
    temp_file_path = Column(String(500))

    imported_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    account = relationship("BankAccount", back_populates="import_batches")
    transactions = relationship("Transaction", back_populates="import_batch")
