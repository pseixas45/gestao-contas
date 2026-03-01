from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Numeric, Boolean, Index, Enum
from sqlalchemy.orm import relationship
import hashlib
from app.database import Base
from app.models.exchange_rate import CurrencyCode


class Transaction(Base):
    """
    Modelo de transação/lançamento financeiro.

    Suporta múltiplas moedas com conversão automática.
    Inclui campos para cartão de crédito (data de pagamento, parcelas).
    Hash único para detecção de duplicatas.
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    date = Column(Date, nullable=False)  # Data efetiva (ajustada para mês da fatura em cartões)
    description = Column(String(500), nullable=False)
    original_description = Column(String(500))  # Descrição original do extrato

    # Valor original (na moeda da conta)
    original_currency = Column(Enum(CurrencyCode), default=CurrencyCode.BRL, nullable=False)
    original_amount = Column(Numeric(15, 2), nullable=False)  # Negativo = débito, Positivo = crédito

    # Valores convertidos (sempre preenchidos)
    amount_brl = Column(Numeric(15, 2), nullable=False)  # Valor em Real
    amount_usd = Column(Numeric(15, 2), nullable=False)  # Valor em Dólar
    amount_eur = Column(Numeric(15, 2), nullable=False)  # Valor em Euro

    # Alias para compatibilidade (mantém amount = amount_brl)
    amount = Column(Numeric(15, 2), nullable=False)  # Alias para amount_brl

    balance_after = Column(Numeric(15, 2))  # Saldo após transação (se disponível)

    # Campos de cartão de crédito
    card_payment_date = Column(Date, nullable=True)  # Data de pagamento da fatura
    installment_number = Column(Integer, nullable=True)  # Parcela atual (n em n/m)
    installment_total = Column(Integer, nullable=True)   # Total de parcelas (m em n/m)

    # Campos para controle de importação e duplicatas
    transaction_hash = Column(String(64), unique=True, index=True)
    is_validated = Column(Boolean, default=False)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)

    # Campos de auditoria
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    account = relationship("BankAccount", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    import_batch = relationship("ImportBatch", back_populates="transactions")

    # Índices compostos para queries frequentes
    __table_args__ = (
        Index("idx_transactions_account_date", "account_id", "date"),
        Index("idx_transactions_validated", "is_validated"),
        Index("idx_transactions_card_payment", "card_payment_date"),
    )

    @staticmethod
    def normalize_description(description: str) -> str:
        """
        Normaliza descrição para hash.
        Usa normalização centralizada: remove acentos, pontuação,
        normaliza padrões bancários, colapsa espaços.
        """
        from app.utils.normalization import normalize_for_hash
        return normalize_for_hash(description)

    @staticmethod
    def generate_hash(
        account_id: int,
        trans_date: date,
        description: str,
        amount: Decimal,
        currency: CurrencyCode = CurrencyCode.BRL,
        suffix: int = 0,
        card_payment_date: date = None
    ) -> str:
        """
        Gera hash único para identificar transação e detectar duplicatas.

        Args:
            account_id: ID da conta bancária
            trans_date: Data da transação
            description: Descrição da transação
            amount: Valor original da transação
            currency: Moeda original
            suffix: Sufixo para diferenciar transações idênticas
            card_payment_date: Data de pagamento do cartão (se aplicável)

        Returns:
            Hash SHA-256 da transação
        """
        from app.utils.normalization import normalize_for_hash, format_amount_for_hash

        date_str = trans_date.isoformat() if isinstance(trans_date, date) else str(trans_date)
        amount_str = format_amount_for_hash(amount)
        desc_normalized = normalize_for_hash(description)
        currency_str = currency.value if isinstance(currency, CurrencyCode) else str(currency)

        # Criar string única
        parts = [str(account_id), date_str, desc_normalized, amount_str, currency_str]
        if card_payment_date:
            cpd_str = card_payment_date.isoformat() if isinstance(card_payment_date, date) else str(card_payment_date)
            parts.append(f"cpd:{cpd_str}")
        if suffix > 0:
            parts.append(str(suffix))

        unique_string = "|".join(parts)
        return hashlib.sha256(unique_string.encode()).hexdigest()

    def set_hash(self):
        """Define o hash da transação baseado nos campos atuais."""
        self.transaction_hash = self.generate_hash(
            self.account_id,
            self.date,
            self.description,
            self.original_amount,
            self.original_currency,
            card_payment_date=self.card_payment_date
        )

    @property
    def is_installment(self) -> bool:
        """Verifica se é uma parcela."""
        return self.installment_number is not None and self.installment_total is not None

    @property
    def installment_info(self) -> str:
        """Retorna informação de parcela formatada (ex: '3/10')."""
        if self.is_installment:
            return f"{self.installment_number}/{self.installment_total}"
        return ""
