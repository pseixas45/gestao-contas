"""Modelos de gestão de investimentos.

Estrutura:
- AssetClass: classe de ativo (Renda Fixa, Renda Variável, FII, etc.)
- Asset: ativo individual (CDB Banco X, PETR4, FIP Y...)
- InvestmentSnapshot: foto da carteira numa data (1 por mês por conta)
- InvestmentPosition: posição de um ativo num snapshot
- InvestmentGoal: meta configurável (aporte, rentabilidade, alocação)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, Numeric,
    Boolean, Enum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class AssetClassCode(str, enum.Enum):
    """Códigos padronizados de classes de ativos."""
    RENDA_FIXA = "renda_fixa"
    INFLACAO = "inflacao"          # Atrelados a IPCA/IGPM
    PRE_FIXADO = "pre_fixado"
    POS_FIXADO = "pos_fixado"
    MULTIMERCADO = "multimercado"
    RENDA_VARIAVEL = "renda_variavel"  # Ações
    FII = "fii"                    # Fundos imobiliários
    CRIPTO = "cripto"
    CAMBIAL = "cambial"
    PREVIDENCIA = "previdencia"
    ALTERNATIVOS = "alternativos"  # FIP, Private Equity
    CAIXA = "caixa"                # Saldo em conta corretora


class GoalType(str, enum.Enum):
    """Tipos de metas de investimento."""
    PORTFOLIO_TOTAL = "portfolio_total"        # Patrimônio total alvo
    MONTHLY_CONTRIBUTION = "monthly_contribution"  # Aporte mensal mínimo
    MIN_YIELD = "min_yield"                    # Rentabilidade mínima esperada
    ALLOCATION_BY_CLASS = "allocation_by_class"  # % alvo por classe


class AssetClass(Base):
    """Classe de ativo. Seedado com os valores padrão (~10 classes)."""

    __tablename__ = "asset_classes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(Enum(AssetClassCode), unique=True, nullable=False)
    name = Column(String(80), nullable=False)
    color = Column(String(7), default="#6B7280")
    typical_liquidity_days = Column(Integer, default=1)  # D+1 default
    risk_level = Column(Integer, default=1)  # 1 (baixo) a 5 (alto)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    assets = relationship("Asset", back_populates="asset_class")


class Asset(Base):
    """Ativo individual (produto financeiro)."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), index=True)  # Ticker ou código interno
    name = Column(String(200), nullable=False)
    name_normalized = Column(String(200), index=True)  # Para matching entre snapshots
    asset_class_id = Column(Integer, ForeignKey("asset_classes.id"), nullable=False)
    issuer = Column(String(120))  # Banco/empresa emissora (Itaú, Petrobras, etc.)
    sector = Column(String(80))  # Setor econômico (opcional, para análise de exposição)
    isin = Column(String(20))  # Código internacional, opcional
    # Override do AssetClass — preenchido se o ativo específico tem liquidez/risco diferente
    liquidity_days = Column(Integer)
    risk_level = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    asset_class = relationship("AssetClass", back_populates="assets")
    positions = relationship("InvestmentPosition", back_populates="asset")


class InvestmentSnapshot(Base):
    """Foto do portfólio numa data específica (geralmente 1 por mês por conta)."""

    __tablename__ = "investment_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    snapshot_date = Column(Date, nullable=False)

    # Totais consolidados
    total_value = Column(Numeric(15, 2), nullable=False)  # Patrimônio total (R$)
    total_invested = Column(Numeric(15, 2))  # Capital aplicado (sem rendimentos)
    available_balance = Column(Numeric(15, 2), default=0)  # Saldo em caixa/conta

    # Rentabilidades agregadas (vindas do extrato, opcionais)
    yield_month_pct = Column(Numeric(8, 4))  # Rentabilidade do mês
    yield_ytd_pct = Column(Numeric(8, 4))    # Year-to-date
    yield_total_pct = Column(Numeric(8, 4))  # Acumulada

    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)
    notes = Column(String(500))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_snapshot_account_date"),
        Index("idx_snapshot_date", "snapshot_date"),
    )

    # Relacionamentos
    account = relationship("BankAccount")
    positions = relationship("InvestmentPosition", back_populates="snapshot", cascade="all, delete-orphan")


class InvestmentPosition(Base):
    """Posição de um ativo numa snapshot."""

    __tablename__ = "investment_positions"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("investment_snapshots.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)

    # Valores
    value = Column(Numeric(15, 2), nullable=False)  # Valor atual (R$)
    value_invested = Column(Numeric(15, 2))         # Valor aplicado (capital)
    quantity = Column(Numeric(20, 8))               # Quantidade (cotas/ações)
    allocation_pct = Column(Numeric(8, 4))          # % do portfólio

    # Rentabilidades
    yield_net_pct = Column(Numeric(8, 4))           # Líquida (%)
    yield_gross_pct = Column(Numeric(8, 4))         # Bruta (%)
    yield_value = Column(Numeric(15, 2))            # Ganho R$ acumulado

    # Específicos de renda fixa
    maturity_date = Column(Date)                    # Vencimento
    contracted_rate = Column(String(50))            # Taxa contratada (ex: "100% CDI", "IPCA+5%")

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_position_snapshot_asset", "snapshot_id", "asset_id"),
    )

    # Relacionamentos
    snapshot = relationship("InvestmentSnapshot", back_populates="positions")
    asset = relationship("Asset", back_populates="positions")


class InvestmentGoal(Base):
    """Meta de investimento configurável."""

    __tablename__ = "investment_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    type = Column(Enum(GoalType), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(String(500))

    target_value = Column(Numeric(15, 2))           # Valor alvo (R$ ou %)
    target_class_id = Column(Integer, ForeignKey("asset_classes.id"), nullable=True)

    # Período de aplicação da meta (NULL = indefinido)
    period_start = Column(Date)
    period_end = Column(Date)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    target_class = relationship("AssetClass")
