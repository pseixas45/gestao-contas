"""Endpoints REST para gestão de investimentos."""
from typing import List, Optional
from datetime import date
from decimal import Decimal
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.api.deps import get_db
from app.models import (
    User, BankAccount, Bank,
    AssetClass, Asset, InvestmentSnapshot, InvestmentPosition, InvestmentGoal,
)
from app.schemas.investment import (
    AssetClassResponse,
    AssetCreate, AssetUpdate, AssetResponse,
    InvestmentSnapshotCreate, InvestmentSnapshotResponse, InvestmentSnapshotDetail,
    InvestmentPositionResponse,
    InvestmentGoalCreate, InvestmentGoalUpdate, InvestmentGoalResponse,
)
from app.services.investment_import_service import InvestmentImportService
from app.services import investment_analysis as analysis
from app.utils.security import get_current_active_user

router = APIRouter()


# ===========================================================
# ASSET CLASSES
# ===========================================================

@router.get("/asset-classes", response_model=List[AssetClassResponse])
def list_asset_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todas as classes de ativos disponíveis."""
    return db.query(AssetClass).order_by(AssetClass.name).all()


# ===========================================================
# ASSETS
# ===========================================================

def _asset_to_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        code=asset.code,
        name=asset.name,
        asset_class_id=asset.asset_class_id,
        asset_class_name=asset.asset_class.name if asset.asset_class else None,
        asset_class_code=asset.asset_class.code.value if asset.asset_class else None,
        issuer=asset.issuer,
        sector=asset.sector,
        isin=asset.isin,
        liquidity_days=asset.liquidity_days,
        risk_level=asset.risk_level,
        is_active=asset.is_active,
    )


@router.get("/assets", response_model=List[AssetResponse])
def list_assets(
    asset_class_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Asset)
    if asset_class_id:
        query = query.filter(Asset.asset_class_id == asset_class_id)
    if active_only:
        query = query.filter(Asset.is_active == True)
    assets = query.order_by(Asset.name).all()
    return [_asset_to_response(a) for a in assets]


@router.post("/assets", response_model=AssetResponse)
def create_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cls = db.query(AssetClass).filter(AssetClass.id == data.asset_class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Asset class não encontrada")
    name_norm = (data.name or "").strip().upper()
    asset = Asset(
        code=data.code,
        name=data.name,
        name_normalized=name_norm,
        asset_class_id=data.asset_class_id,
        issuer=data.issuer,
        sector=data.sector,
        isin=data.isin,
        liquidity_days=data.liquidity_days,
        risk_level=data.risk_level,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_to_response(asset)


@router.put("/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int,
    data: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset não encontrado")
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"]:
        update_data["name_normalized"] = update_data["name"].strip().upper()
    for k, v in update_data.items():
        setattr(asset, k, v)
    db.commit()
    db.refresh(asset)
    return _asset_to_response(asset)


# ===========================================================
# SNAPSHOTS
# ===========================================================

def _snapshot_to_response(snap: InvestmentSnapshot, db: Session) -> InvestmentSnapshotResponse:
    acc = snap.account
    bank_name = None
    if acc and acc.bank_id:
        b = db.query(Bank).filter(Bank.id == acc.bank_id).first()
        bank_name = b.name if b else None
    return InvestmentSnapshotResponse(
        id=snap.id,
        account_id=snap.account_id,
        account_name=acc.name if acc else None,
        bank_name=bank_name,
        snapshot_date=snap.snapshot_date,
        total_value=snap.total_value,
        total_invested=snap.total_invested,
        available_balance=snap.available_balance,
        yield_month_pct=snap.yield_month_pct,
        yield_ytd_pct=snap.yield_ytd_pct,
        yield_total_pct=snap.yield_total_pct,
        notes=snap.notes,
        positions_count=len(snap.positions) if snap.positions is not None else 0,
    )


@router.get("/snapshots", response_model=List[InvestmentSnapshotResponse])
def list_snapshots(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista snapshots, opcionalmente filtrando por conta."""
    query = db.query(InvestmentSnapshot)
    if account_id:
        query = query.filter(InvestmentSnapshot.account_id == account_id)
    snaps = query.order_by(desc(InvestmentSnapshot.snapshot_date)).all()
    return [_snapshot_to_response(s, db) for s in snaps]


@router.get("/snapshots/{snapshot_id}", response_model=InvestmentSnapshotDetail)
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    snap = db.query(InvestmentSnapshot).filter(InvestmentSnapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    base = _snapshot_to_response(snap, db).model_dump()
    positions = []
    for p in snap.positions:
        positions.append(InvestmentPositionResponse(
            id=p.id,
            asset_id=p.asset_id,
            asset_name=p.asset.name if p.asset else None,
            asset_class_code=p.asset.asset_class.code.value if p.asset and p.asset.asset_class else None,
            value=p.value,
            value_invested=p.value_invested,
            quantity=p.quantity,
            allocation_pct=p.allocation_pct,
            yield_net_pct=p.yield_net_pct,
            yield_gross_pct=p.yield_gross_pct,
            yield_value=p.yield_value,
            maturity_date=p.maturity_date,
            contracted_rate=p.contracted_rate,
        ))
    base["positions"] = positions
    return InvestmentSnapshotDetail(**base)


@router.post("/snapshots", response_model=InvestmentSnapshotResponse)
def create_snapshot(
    data: InvestmentSnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cria snapshot manualmente. Geralmente usado pelo importador, mas útil para teste/ajuste."""
    acc = db.query(BankAccount).filter(BankAccount.id == data.account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    # Verificar duplicata por (account_id, snapshot_date)
    existing = db.query(InvestmentSnapshot).filter(
        InvestmentSnapshot.account_id == data.account_id,
        InvestmentSnapshot.snapshot_date == data.snapshot_date,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe snapshot para esta conta na data {data.snapshot_date}"
        )
    snap = InvestmentSnapshot(**data.model_dump())
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return _snapshot_to_response(snap, db)


@router.delete("/snapshots/{snapshot_id}")
def delete_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    snap = db.query(InvestmentSnapshot).filter(InvestmentSnapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    db.delete(snap)
    db.commit()
    return {"message": "Snapshot removido"}


# ===========================================================
# UPLOAD (importação de arquivos)
# ===========================================================

@router.post("/upload")
async def upload_investment_file(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    provider: str = Form("xp"),  # 'xp', 'itau', 'c6'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload de arquivo de extrato de investimentos.

    Provider: 'xp' (xlsx PosicaoDetalhada), 'itau' (pdf — TBD), 'c6' (TBD)
    """
    # Salvar arquivo temporário
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        svc = InvestmentImportService(db)
        if provider.lower() == "xp":
            result = svc.import_xp_file(tmp.name, account_id)
        elif provider.lower() == "itau":
            result = svc.import_itau_file(tmp.name, account_id)
        elif provider.lower() == "c6":
            raise HTTPException(status_code=501, detail="Parser C6 em implementação")
        else:
            raise HTTPException(status_code=400, detail=f"Provider desconhecido: {provider}")

        return {
            "success": True,
            "filename": file.filename,
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ===========================================================
# POSITIONS (current — última snapshot por conta)
# ===========================================================

@router.get("/positions/current", response_model=List[InvestmentPositionResponse])
def list_current_positions(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Posições da última snapshot disponível (por conta ou agregada)."""
    snaps_query = db.query(InvestmentSnapshot)
    if account_id:
        snaps_query = snaps_query.filter(InvestmentSnapshot.account_id == account_id)
    # Pegar última snapshot de cada conta
    accounts = db.query(BankAccount).filter(
        BankAccount.account_type == "INVESTMENT"
    ).all() if not account_id else [db.query(BankAccount).filter(BankAccount.id == account_id).first()]

    result = []
    for acc in accounts:
        if not acc:
            continue
        last = (
            db.query(InvestmentSnapshot)
            .filter(InvestmentSnapshot.account_id == acc.id)
            .order_by(desc(InvestmentSnapshot.snapshot_date))
            .first()
        )
        if not last:
            continue
        for p in last.positions:
            result.append(InvestmentPositionResponse(
                id=p.id,
                asset_id=p.asset_id,
                asset_name=p.asset.name if p.asset else None,
                asset_class_code=p.asset.asset_class.code.value if p.asset and p.asset.asset_class else None,
                value=p.value,
                value_invested=p.value_invested,
                quantity=p.quantity,
                allocation_pct=p.allocation_pct,
                yield_net_pct=p.yield_net_pct,
                yield_gross_pct=p.yield_gross_pct,
                yield_value=p.yield_value,
                maturity_date=p.maturity_date,
                contracted_rate=p.contracted_rate,
            ))
    return result


# ===========================================================
# GOALS
# ===========================================================

def _goal_to_response(goal: InvestmentGoal, db: Session) -> InvestmentGoalResponse:
    target_class_name = None
    if goal.target_class:
        target_class_name = goal.target_class.name
    # Cálculo de progresso é feito posteriormente (Fase 4 — Análises).
    # Por enquanto retorna estrutura básica.
    return InvestmentGoalResponse(
        id=goal.id,
        type=goal.type,
        name=goal.name,
        description=goal.description,
        target_value=goal.target_value,
        target_class_id=goal.target_class_id,
        target_class_name=target_class_name,
        period_start=goal.period_start,
        period_end=goal.period_end,
        is_active=goal.is_active,
    )


@router.get("/goals", response_model=List[InvestmentGoalResponse])
def list_goals(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(InvestmentGoal).filter(InvestmentGoal.user_id == current_user.id)
    if active_only:
        query = query.filter(InvestmentGoal.is_active == True)
    goals = query.order_by(InvestmentGoal.created_at).all()
    return [_goal_to_response(g, db) for g in goals]


@router.post("/goals", response_model=InvestmentGoalResponse)
def create_goal(
    data: InvestmentGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if data.target_class_id:
        cls = db.query(AssetClass).filter(AssetClass.id == data.target_class_id).first()
        if not cls:
            raise HTTPException(status_code=404, detail="Asset class não encontrada")
    goal = InvestmentGoal(
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_to_response(goal, db)


@router.put("/goals/{goal_id}", response_model=InvestmentGoalResponse)
def update_goal(
    goal_id: int,
    data: InvestmentGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    goal = db.query(InvestmentGoal).filter(
        InvestmentGoal.id == goal_id,
        InvestmentGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta não encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(goal, k, v)
    db.commit()
    db.refresh(goal)
    return _goal_to_response(goal, db)


@router.delete("/goals/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    goal = db.query(InvestmentGoal).filter(
        InvestmentGoal.id == goal_id,
        InvestmentGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta não encontrada")
    db.delete(goal)
    db.commit()
    return {"message": "Meta removida"}


@router.get("/goals/progress")
def goals_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Progresso de todas as metas ativas do usuário."""
    goals = db.query(InvestmentGoal).filter(
        InvestmentGoal.user_id == current_user.id,
        InvestmentGoal.is_active == True,
    ).all()
    out = []
    for g in goals:
        prog = analysis.evaluate_goal_progress(db, g)
        target_class_name = g.target_class.name if g.target_class else None
        out.append({
            "id": g.id,
            "name": g.name,
            "type": g.type.value if hasattr(g.type, "value") else str(g.type),
            "target_value": float(g.target_value) if g.target_value is not None else None,
            "target_class_id": g.target_class_id,
            "target_class_name": target_class_name,
            "current": prog.get("current", 0.0),
            "progress_pct": prog.get("progress_pct", 0.0),
        })
    return out


# ===========================================================
# ANÁLISES (dashboard, alocação, exposição, etc.)
# ===========================================================

@router.get("/dashboard")
def get_dashboard(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Dados consolidados para o dashboard de investimentos.

    Usa um único cache de snapshots/posições para evitar N+1.
    """
    cache = analysis._SnapshotCache(db, account_id)
    return {
        "overview": analysis.get_portfolio_overview(db, account_id, cache=cache),
        "allocation_by_class": analysis.get_allocation(db, account_id, "class", cache=cache),
        "allocation_by_bank": analysis.get_allocation(db, account_id, "bank", cache=cache),
        "history": analysis.get_history(db, account_id, cache=cache),
        "exposure": analysis.get_exposure(db, account_id, cache=cache),
        "risk": analysis.get_risk_summary(db, account_id, cache=cache),
        "liquidity": analysis.get_liquidity(db, account_id, cache=cache),
        "contributions": analysis.get_monthly_contributions(db, account_id, cache=cache),
    }


@router.get("/overview")
def overview_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_portfolio_overview(db, account_id)


@router.get("/history")
def history_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_history(db, account_id)


@router.get("/allocation")
def allocation_endpoint(
    group_by: str = "class",
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_allocation(db, account_id, group_by)


@router.get("/exposure")
def exposure_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_exposure(db, account_id)


@router.get("/liquidity")
def liquidity_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_liquidity(db, account_id)


@router.get("/risk")
def risk_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_risk_summary(db, account_id)


@router.get("/contributions")
def contributions_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return analysis.get_monthly_contributions(db, account_id)


@router.get("/contributions/month")
def contribution_for_month(
    month: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Aporte de um mês específico (YYYY-MM). Usado pelo dashboard principal."""
    contribs = analysis.get_monthly_contributions(db)
    target_prefix = month[:7] if month else ""
    for c in contribs:
        if c["date"].startswith(target_prefix):
            return {
                "month": target_prefix,
                "contribution": c["contribution"],
                "total_invested": c["total_invested"],
                "snapshot_date": c["date"],
            }
    return {
        "month": target_prefix,
        "contribution": None,
        "total_invested": None,
        "snapshot_date": None,
    }
