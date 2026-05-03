"""Schemas Pydantic para investimentos."""
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from app.models.investment import AssetClassCode, GoalType


# ===== AssetClass =====

class AssetClassResponse(BaseModel):
    id: int
    code: AssetClassCode
    name: str
    color: str
    typical_liquidity_days: int
    risk_level: int
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ===== Asset =====

class AssetCreate(BaseModel):
    code: Optional[str] = None
    name: str
    asset_class_id: int
    issuer: Optional[str] = None
    sector: Optional[str] = None
    isin: Optional[str] = None
    liquidity_days: Optional[int] = None
    risk_level: Optional[int] = None


class AssetUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    asset_class_id: Optional[int] = None
    issuer: Optional[str] = None
    sector: Optional[str] = None
    isin: Optional[str] = None
    liquidity_days: Optional[int] = None
    risk_level: Optional[int] = None
    is_active: Optional[bool] = None


class AssetResponse(BaseModel):
    id: int
    code: Optional[str] = None
    name: str
    asset_class_id: int
    asset_class_name: Optional[str] = None
    asset_class_code: Optional[str] = None
    issuer: Optional[str] = None
    sector: Optional[str] = None
    isin: Optional[str] = None
    liquidity_days: Optional[int] = None
    risk_level: Optional[int] = None
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


# ===== InvestmentPosition =====

class InvestmentPositionResponse(BaseModel):
    id: int
    asset_id: int
    asset_name: Optional[str] = None
    asset_class_code: Optional[str] = None
    value: Decimal
    value_invested: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    allocation_pct: Optional[Decimal] = None
    yield_net_pct: Optional[Decimal] = None
    yield_gross_pct: Optional[Decimal] = None
    yield_value: Optional[Decimal] = None
    maturity_date: Optional[date] = None
    contracted_rate: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ===== InvestmentSnapshot =====

class InvestmentSnapshotCreate(BaseModel):
    account_id: int
    snapshot_date: date
    total_value: Decimal
    total_invested: Optional[Decimal] = None
    available_balance: Optional[Decimal] = Decimal("0")
    yield_month_pct: Optional[Decimal] = None
    yield_ytd_pct: Optional[Decimal] = None
    yield_total_pct: Optional[Decimal] = None
    notes: Optional[str] = None


class InvestmentSnapshotResponse(BaseModel):
    id: int
    account_id: int
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    snapshot_date: date
    total_value: Decimal
    total_invested: Optional[Decimal] = None
    available_balance: Optional[Decimal] = None
    yield_month_pct: Optional[Decimal] = None
    yield_ytd_pct: Optional[Decimal] = None
    yield_total_pct: Optional[Decimal] = None
    notes: Optional[str] = None
    positions_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class InvestmentSnapshotDetail(InvestmentSnapshotResponse):
    """Snapshot com lista de posições."""
    positions: List[InvestmentPositionResponse] = []


# ===== InvestmentGoal =====

class InvestmentGoalCreate(BaseModel):
    type: GoalType
    name: str
    description: Optional[str] = None
    target_value: Optional[Decimal] = None
    target_class_id: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class InvestmentGoalUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_value: Optional[Decimal] = None
    target_class_id: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    is_active: Optional[bool] = None


class InvestmentGoalResponse(BaseModel):
    id: int
    type: GoalType
    name: str
    description: Optional[str] = None
    target_value: Optional[Decimal] = None
    target_class_id: Optional[int] = None
    target_class_name: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    is_active: bool
    # Cálculo de progresso (preenchido pelo backend ao listar)
    current_value: Optional[Decimal] = None
    progress_pct: Optional[Decimal] = None
    model_config = ConfigDict(from_attributes=True)
