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
        rate_index=asset.rate_index.value if asset.rate_index else None,
        rate_spread=float(asset.rate_spread) if asset.rate_spread is not None else None,
        rate_type=asset.rate_type.value if asset.rate_type else None,
        application_date=asset.application_date,
        maturity_date=asset.maturity_date,
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

def _snapshot_to_response(snap: InvestmentSnapshot, banks_by_id: dict = None, pos_count: int = None) -> InvestmentSnapshotResponse:
    acc = snap.account
    bank_name = None
    if acc and acc.bank_id:
        if banks_by_id:
            b = banks_by_id.get(acc.bank_id)
            bank_name = b.name if b else None
        else:
            bank_name = None
    return InvestmentSnapshotResponse(
        id=snap.id,
        account_id=snap.account_id,
        account_name=acc.name if acc else None,
        bank_name=bank_name,
        snapshot_date=snap.snapshot_date,
        total_value=snap.total_value,
        total_invested=snap.total_invested,
        available_balance=snap.available_balance,
        total_gross=snap.total_gross,
        total_net=snap.total_net,
        yield_month_pct=snap.yield_month_pct,
        yield_ytd_pct=snap.yield_ytd_pct,
        yield_total_pct=snap.yield_total_pct,
        yield_month_value=snap.yield_month_value,
        notes=snap.notes,
        positions_count=pos_count if pos_count is not None else 0,
    )


@router.get("/snapshots", response_model=List[InvestmentSnapshotResponse])
def list_snapshots(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista snapshots, opcionalmente filtrando por conta."""
    from sqlalchemy.orm import joinedload, subqueryload
    from sqlalchemy import func as sqlfunc

    query = db.query(InvestmentSnapshot).options(
        joinedload(InvestmentSnapshot.account),
    )
    if account_id:
        query = query.filter(InvestmentSnapshot.account_id == account_id)
    snaps = query.order_by(desc(InvestmentSnapshot.snapshot_date)).all()

    # Contar posições em batch (1 query em vez de N)
    snap_ids = [s.id for s in snaps]
    pos_counts = {}
    if snap_ids:
        rows = db.query(
            InvestmentPosition.snapshot_id, sqlfunc.count(InvestmentPosition.id)
        ).filter(InvestmentPosition.snapshot_id.in_(snap_ids)).group_by(
            InvestmentPosition.snapshot_id
        ).all()
        pos_counts = {r[0]: r[1] for r in rows}

    banks = {b.id: b for b in db.query(Bank).all()}
    return [_snapshot_to_response(s, banks, pos_counts.get(s.id, 0)) for s in snaps]


@router.get("/snapshots/{snapshot_id}", response_model=InvestmentSnapshotDetail)
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from sqlalchemy.orm import joinedload, selectinload
    snap = (
        db.query(InvestmentSnapshot)
        .options(
            joinedload(InvestmentSnapshot.account),
            selectinload(InvestmentSnapshot.positions)
            .joinedload(InvestmentPosition.asset)
            .joinedload(Asset.asset_class),
        )
        .filter(InvestmentSnapshot.id == snapshot_id)
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    banks = {b.id: b for b in db.query(Bank).all()}
    base = _snapshot_to_response(snap, banks, len(snap.positions)).model_dump()
    positions = []
    for p in snap.positions:
        positions.append(InvestmentPositionResponse(
            id=p.id,
            asset_id=p.asset_id,
            asset_name=p.asset.name if p.asset else None,
            asset_class_code=p.asset.asset_class.code.value if p.asset and p.asset.asset_class else None,
            value=p.value,
            value_invested=p.value_invested,
            value_gross=p.value_gross,
            value_net=p.value_net,
            quantity=p.quantity,
            allocation_pct=p.allocation_pct,
            yield_net_pct=p.yield_net_pct,
            yield_gross_pct=p.yield_gross_pct,
            yield_value=p.yield_value,
            yield_month_value=p.yield_month_value,
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
    provider: str = Form("auto"),  # 'xp', 'itau', 'c6', 'auto'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload de arquivo de extrato de investimentos.

    Provider: 'xp' (PDF Posição Consolidada), 'itau' (PDF Extrato Mensal), 'c6' (PDF Relatório), 'auto' (auto-detect)
    """
    import shutil, re as _re
    # Preserva o nome original — os parsers extraem a data dele
    safe_name = _re.sub(r"[^A-Za-z0-9._\- ]", "_", file.filename or "upload")
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, safe_name)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        svc = InvestmentImportService(db)
        prov = None if provider.lower() == "auto" else provider.lower()
        result = svc.import_file(tmp_path, account_id, prov)

        return {
            "success": True,
            "filename": file.filename,
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ===========================================================
# POSITIONS (current — última snapshot por conta)
# ===========================================================

@router.get("/positions/current", response_model=List[InvestmentPositionResponse])
def list_current_positions(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Posições da última snapshot de cada conta de investimento (ou de uma conta específica)."""
    from sqlalchemy.orm import selectinload, joinedload
    from sqlalchemy import func as sqlfunc

    # 1. Buscar contas
    acc_q = db.query(BankAccount)
    if account_id:
        acc_q = acc_q.filter(BankAccount.id == account_id)
    else:
        acc_q = acc_q.filter(BankAccount.account_type == "INVESTMENT", BankAccount.is_active == True)
    accounts = acc_q.all()
    if not accounts:
        return []
    acc_ids = [a.id for a in accounts]
    acc_map = {a.id: a for a in accounts}

    # 2. Buscar último snapshot_date por conta (1 query)
    latest_rows = (
        db.query(InvestmentSnapshot.account_id, sqlfunc.max(InvestmentSnapshot.snapshot_date))
        .filter(InvestmentSnapshot.account_id.in_(acc_ids))
        .group_by(InvestmentSnapshot.account_id)
        .all()
    )
    if not latest_rows:
        return []

    # 3. Buscar esses snapshots com positions eager-loaded (1 query)
    from sqlalchemy import tuple_
    snap_filters = [
        (InvestmentSnapshot.account_id == r[0]) & (InvestmentSnapshot.snapshot_date == r[1])
        for r in latest_rows
    ]
    from sqlalchemy import or_
    snaps = (
        db.query(InvestmentSnapshot)
        .options(
            selectinload(InvestmentSnapshot.positions)
            .joinedload(InvestmentPosition.asset)
            .joinedload(Asset.asset_class),
        )
        .filter(or_(*snap_filters))
        .all()
    )

    result = []
    for snap in snaps:
        acc = acc_map.get(snap.account_id)
        for p in snap.positions:
            result.append(InvestmentPositionResponse(
                id=p.id,
                asset_id=p.asset_id,
                asset_name=p.asset.name if p.asset else None,
                asset_class_code=p.asset.asset_class.code.value if p.asset and p.asset.asset_class else None,
                account_id=snap.account_id,
                account_name=acc.name if acc else None,
                snapshot_date=snap.snapshot_date,
                value=p.value,
                value_invested=p.value_invested,
                value_gross=p.value_gross,
                value_net=p.value_net,
                quantity=p.quantity,
                allocation_pct=p.allocation_pct,
                yield_net_pct=p.yield_net_pct,
                yield_gross_pct=p.yield_gross_pct,
                yield_value=p.yield_value,
                yield_month_value=p.yield_month_value,
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
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Dados consolidados para o dashboard de investimentos.

    Params:
        month: filtro YYYY-MM (ex: 2026-03). Se informado, overview usa o último dia desse mês.
    """
    # Determinar reference_date a partir do filtro de mês
    import calendar
    reference_date = None
    if month:
        try:
            parts = month.split("-")
            y, m = int(parts[0]), int(parts[1])
            last_day = calendar.monthrange(y, m)[1]
            reference_date = date(y, m, last_day)
        except (ValueError, IndexError):
            pass

    cache = analysis._SnapshotCache(db, account_id)
    history = analysis.get_history(db, account_id, cache=cache)

    # Monthly yield calculado in-line (sem query extra)
    monthly_yield = []
    prev = None
    for point in history:
        entry = {"date": point["date"], "total_value": point["total_value"], "yield_value": 0, "yield_pct": 0}
        if prev:
            invested_delta = (point.get("total_invested") or 0) - (prev.get("total_invested") or 0)
            yv = point["total_value"] - prev["total_value"] - max(invested_delta, 0)
            entry["yield_value"] = round(yv, 2)
            entry["yield_pct"] = round(yv / prev["total_value"] * 100, 2) if prev["total_value"] > 0 else 0
        monthly_yield.append(entry)
        prev = point

    # Net value summary (usa posições já carregadas no cache)
    net_summary = None
    try:
        from app.utils.tax_calculator import estimate_net_value as _est_net
        from datetime import date as _date
        today = _date.today()
        total_gross = Decimal("0")
        total_net = Decimal("0")
        pos_count = 0
        for pos in cache.latest_positions:
            asset = pos.asset
            if not asset:
                continue
            v_gross = pos.value_gross or pos.value or Decimal("0")
            v_invested = pos.value_invested
            v_net_ext = pos.value_net
            days = (today - asset.application_date).days if asset.application_date else 999
            if v_net_ext:
                v_net = v_net_ext
            elif v_invested and v_invested > 0:
                v_net = _est_net(v_gross, v_invested, days, asset.name, asset.asset_class.code if asset.asset_class else None)
            else:
                v_net = v_gross
            total_gross += v_gross
            total_net += v_net
            pos_count += 1
        net_summary = {"total_gross": float(total_gross), "total_net": float(total_net), "total_ir": float(total_gross - total_net), "positions_count": pos_count}
    except Exception:
        pass

    return {
        "overview": analysis.get_portfolio_overview(db, account_id, cache=cache, reference_date=reference_date),
        "allocation_by_class": analysis.get_allocation(db, account_id, "class", cache=cache),
        "allocation_by_bank": analysis.get_allocation(db, account_id, "bank", cache=cache),
        "history": history,
        "monthly_yield": monthly_yield,
        "net_summary": net_summary,
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


# ===========================================================
# PROFITABILITY (valor mercado vs curva vs CDI)
# ===========================================================

@router.get("/profitability")
def profitability_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Série temporal de rentabilidade: valor de mercado vs curva vs CDI benchmark."""
    from app.services.curve_value_service import CurveValueService
    from app.services.market_data_service import MarketDataService

    cache = analysis._SnapshotCache(db, account_id)
    history = analysis.get_history(db, account_id, cache=cache)

    if not history:
        return []

    curve_svc = CurveValueService(db)
    market_svc = MarketDataService(db)

    # Calcular CDI benchmark: se tivesse investido tudo em 100% CDI
    first_date = None
    first_value = None

    results = []
    for point in history:
        snap_date = date.fromisoformat(point["date"]) if isinstance(point["date"], str) else point["date"]

        entry = {
            "date": point["date"],
            "market_value": point["total_value"],
            "invested": point.get("total_invested"),
        }

        # CDI benchmark
        if first_date is None and point.get("total_invested"):
            first_date = snap_date
            first_value = Decimal(str(point["total_invested"]))

        if first_date and first_value:
            cdi_factor = market_svc.get_accumulated_cdi(first_date, snap_date)
            entry["cdi_benchmark"] = float(
                (first_value * cdi_factor).quantize(Decimal("0.01"))
            ) if cdi_factor > Decimal("1") else float(first_value)
        else:
            entry["cdi_benchmark"] = None

        results.append(entry)

    return results


@router.get("/net-value")
def net_value_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Breakdown de valor líquido (pós-IR) por posição no snapshot mais recente."""
    from app.utils.tax_calculator import estimate_net_value, get_tax_bracket_info, is_ir_exempt
    from datetime import date as date_type

    cache = analysis._SnapshotCache(db, account_id)
    if not cache.snapshots:
        return {"positions": [], "total_gross": 0, "total_net": 0, "total_ir": 0}

    # Pegar último snapshot de cada conta
    latest_snaps = {}
    for snap in cache.snapshots:
        if snap.account_id not in latest_snaps or snap.snapshot_date > latest_snaps[snap.account_id].snapshot_date:
            latest_snaps[snap.account_id] = snap

    today = date_type.today()
    positions = []
    total_gross = Decimal("0")
    total_net = Decimal("0")

    for snap in latest_snaps.values():
        for pos in snap.positions:
            asset = pos.asset
            if not asset:
                continue

            v_gross = pos.value_gross or pos.value or Decimal("0")
            v_invested = pos.value_invested
            v_net_from_extrato = pos.value_net

            # Calcular dias desde aplicação
            app_date = asset.application_date
            days_held = (today - app_date).days if app_date else 999

            # Se já temos valor líquido do extrato, usar
            if v_net_from_extrato:
                v_net = v_net_from_extrato
            elif v_invested and v_invested > 0:
                v_net = estimate_net_value(
                    v_gross, v_invested, days_held,
                    asset.name, asset.asset_class.code if asset.asset_class else None
                )
            else:
                v_net = v_gross

            tax_info = get_tax_bracket_info(
                days_held, asset.name,
                asset.asset_class.code if asset.asset_class else None
            )

            total_gross += v_gross
            total_net += v_net

            positions.append({
                "asset_name": asset.name,
                "asset_class": asset.asset_class.code.value if asset.asset_class else None,
                "value_gross": float(v_gross),
                "value_invested": float(v_invested) if v_invested else None,
                "value_net": float(v_net),
                "ir_estimated": float(v_gross - v_net),
                "days_held": days_held,
                "tax_info": tax_info,
            })

    return {
        "positions": sorted(positions, key=lambda x: -x["value_gross"]),
        "total_gross": float(total_gross),
        "total_net": float(total_net),
        "total_ir": float(total_gross - total_net),
    }


@router.get("/monthly-yield")
def monthly_yield_endpoint(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Série temporal de rendimento mensal em R$ e %."""
    cache = analysis._SnapshotCache(db, account_id)
    history = analysis.get_history(db, account_id, cache=cache)

    results = []
    prev = None
    for point in history:
        entry = {
            "date": point["date"],
            "total_value": point["total_value"],
        }

        if prev:
            invested_delta = (point.get("total_invested") or 0) - (prev.get("total_invested") or 0)
            yield_value = point["total_value"] - prev["total_value"] - max(invested_delta, 0)
            entry["yield_value"] = round(yield_value, 2)
            if prev["total_value"] > 0:
                entry["yield_pct"] = round(yield_value / prev["total_value"] * 100, 2)
            else:
                entry["yield_pct"] = 0
        else:
            entry["yield_value"] = 0
            entry["yield_pct"] = 0

        results.append(entry)
        prev = point

    return results


@router.post("/market-data/update")
async def update_market_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Trigger manual de atualização dos dados de mercado (CDI, IPCA)."""
    from app.services.market_data_service import MarketDataService
    from app.models.market_data import MarketIndexRate, MarketIndexCode
    from datetime import timedelta

    latest = db.query(MarketIndexRate.date_ref).filter(
        MarketIndexRate.index_code == MarketIndexCode.CDI
    ).order_by(MarketIndexRate.date_ref.desc()).first()

    start = (latest[0] + timedelta(days=1)) if latest else (date.today() - timedelta(days=730))
    end = date.today()

    if start > end:
        return {"message": "Dados já atualizados", "latest": latest[0].isoformat()}

    svc = MarketDataService(db)
    stats = await svc.update_rates_for_period(start, end)

    return {
        "message": f"Atualizado: {stats['total_fetched']} registros",
        "period": f"{start} a {end}",
        **stats,
    }
