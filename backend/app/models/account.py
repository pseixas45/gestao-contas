from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base
from app.models.exchange_rate import CurrencyCode


class AccountType(str, enum.Enum):
    """Tipo de conta bancária."""
    BANK = "bank"         # Conta bancária (CC, Poupança, Investimento)
    CREDIT = "credit"     # Cartão de Crédito

    # Manter compatibilidade com valores antigos
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"


class BankAccount(Base):
    """
    Modelo de conta bancária.

    Suporta múltiplas moedas (BRL, USD, EUR).
    O tipo de conta determina se é cartão de crédito (regras especiais de fatura).
    """

    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    name = Column(String(100), nullable=False)  # Nome amigável (ex: "Itaú CC Principal")
    account_number = Column(String(50))
    account_type = Column(Enum(AccountType), default=AccountType.BANK)

    # Moeda da conta
    currency = Column(Enum(CurrencyCode), default=CurrencyCode.BRL, nullable=False)

    # Saldos (na moeda da conta)
    initial_balance = Column(Numeric(15, 2), default=Decimal("0.00"))
    current_balance = Column(Numeric(15, 2), default=Decimal("0.00"))

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    bank = relationship("Bank", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
    import_batches = relationship("ImportBatch", back_populates="account")

    @property
    def is_credit_card(self) -> bool:
        """Verifica se é conta de cartão de crédito."""
        return self.account_type in (AccountType.CREDIT, AccountType.CREDIT_CARD)
