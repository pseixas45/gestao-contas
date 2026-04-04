from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from app.models.import_batch import ImportStatus, FileType


class ColumnMapping(BaseModel):
    """Mapeamento de colunas do arquivo para campos do sistema."""
    date_column: str
    description_column: str

    # Valores multi-moeda (pode usar um ou múltiplos)
    amount_column: Optional[str] = None  # Coluna única de valor (compatibilidade)
    valor_brl_column: Optional[str] = None  # Valor R$
    valor_usd_column: Optional[str] = None  # Valor US$
    valor_eur_column: Optional[str] = None  # Valor EUR

    balance_column: Optional[str] = None

    # Para carga histórica com banco e conta no arquivo
    bank_column: Optional[str] = None
    account_column: Optional[str] = None
    category_column: Optional[str] = None

    # Campo de data de pagamento (cartão de crédito)
    card_payment_date_column: Optional[str] = None

    # Campo de parcela (ex: "7 de 10")
    installment_column: Optional[str] = None


class ImportPreview(BaseModel):
    """Preview dos dados antes da importação."""
    batch_id: int
    total_rows: int
    columns: List[str]  # Colunas encontradas no arquivo
    detected_mapping: ColumnMapping  # Mapeamento detectado automaticamente
    preview_rows: List[Dict[str, Any]]  # Primeiras 20 linhas
    temp_file_path: str
    has_template: bool = False  # Se usou template salvo da conta


class ValidationError(BaseModel):
    """Erro de validação em uma linha."""
    row: int
    field: Optional[str]
    message: str


class DuplicateTransaction(BaseModel):
    """Transação duplicada encontrada."""
    row: int
    date: str
    description: str
    amount: Decimal
    existing_id: int  # ID da transação existente no sistema


class ImportProcess(BaseModel):
    """Parâmetros para processar importação."""
    batch_id: int
    column_mapping: ColumnMapping
    account_id: int  # Conta destino (se não vier do arquivo)
    validate_balance: bool = True
    expected_final_balance: Optional[Decimal] = None
    skip_duplicates: bool = True  # Se deve pular duplicatas automaticamente

    # Parâmetros específicos de cartão de crédito
    card_payment_date: Optional[date] = None  # Data de pagamento da fatura (obrigatório para cartão)


class ImportResult(BaseModel):
    """Resultado da importação."""
    batch_id: int
    success: bool
    imported_count: int
    duplicate_count: int
    error_count: int
    errors: List[ValidationError]
    duplicates: List[DuplicateTransaction]
    balance_validated: bool
    balance_matches: bool
    balance_difference: Optional[Decimal] = None

    # Estatísticas adicionais
    installments_detected: int = 0  # Parcelas detectadas
    categories_assigned: int = 0  # Transações com categoria atribuída


class ImportBatchResponse(BaseModel):
    """Resposta de lote de importação."""
    id: int
    account_id: int
    filename: str
    file_type: FileType
    total_records: int
    imported_records: int
    duplicate_records: int
    error_records: int
    status: ImportStatus
    error_message: Optional[str]
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UncertainRow(BaseModel):
    """Linha com duplicado incerto (similaridade entre 65-85%)."""
    row: int
    date: str
    description: str
    amount: Decimal
    similar_to_id: int
    similar_to_description: str
    similarity: float


class TransactionPreviewRow(BaseModel):
    """Preview de transação na análise (para revisão de saldo)."""
    row: int
    date: str
    description: str
    amount: Decimal
    status: str  # "new", "duplicate", "uncertain"
    is_installment: bool = False
    adjusted_date: Optional[str] = None  # Data ajustada (parcelas em cartão)
    running_balance: Optional[Decimal] = None  # Saldo acumulado para validação
    file_balance: Optional[Decimal] = None  # Saldo do arquivo (se tiver coluna saldo)
    balance_ok: Optional[bool] = None  # Se running_balance == file_balance


class ImportAnalysis(BaseModel):
    """Resultado da análise prévia (dry-run) de importação."""
    batch_id: int
    total_rows: int
    new_count: int
    duplicate_count: int
    fuzzy_duplicate_count: int
    uncertain_count: int
    error_count: int
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    overlap_info: Optional[str] = None
    uncertain_rows: List[UncertainRow] = []

    # Totais calculados para validação de saldo
    calculated_total: Optional[Decimal] = None      # Soma de todas as novas transações
    positive_total: Optional[Decimal] = None         # Soma das positivas (débitos/compras)
    negative_total: Optional[Decimal] = None         # Soma das negativas (créditos/pagamentos)
    positive_count: int = 0
    negative_count: int = 0

    # Running balance
    running_balance_final: Optional[Decimal] = None
    first_balance_divergence_row: Optional[int] = None

    # Lista completa de transações para revisão
    transactions_preview: List[TransactionPreviewRow] = []


class OverlapCheckResponse(BaseModel):
    """Resultado da verificação de sobreposição."""
    has_overlap: bool
    existing_transaction_count: int
    overlapping_batches: List[dict] = []
    message: str


class ImportTemplateSchema(BaseModel):
    """Template de importação salvo por conta."""
    id: Optional[int] = None
    account_id: int
    column_mapping: ColumnMapping
    file_format_hints: Optional[Dict[str, Any]] = None
    last_used_at: Optional[datetime] = None
    success_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class HistoricalImportProcess(BaseModel):
    """
    Parâmetros para importação histórica (múltiplas contas).

    Layout esperado:
    Banco|Conta|Data|Descrição|Data Pagto Cartao|Valor R$|Valor US$|Valor EUR|Categoria
    """
    batch_id: int
    column_mapping: ColumnMapping
    create_missing_accounts: bool = True
    create_missing_categories: bool = True
    skip_duplicates: bool = True
