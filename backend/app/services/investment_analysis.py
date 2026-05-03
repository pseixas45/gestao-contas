"""Análises consolidadas de investimentos.

Funções para calcular:
- Rentabilidade (no mês, acumulada, projetada)
- Aportes mensais (calculados via diferença de total_invested)
- Alocação por classe / banco
- Exposição a cenários (inflação, cambial, renda variável)
- Liquidez (distribuição por prazo)
- Risco (média ponderada)
- Progresso de metas
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models import (
    BankAccount, Bank, AssetClass, AssetClassCode, Asset,
    InvestmentSnapshot, InvestmentPosition, InvestmentGoal, GoalType,
)


def _safe_div(num: Decimal, den: Decimal) -> Decimal:
    if not den or den == 0:
        return Decimal("0")
    return num / den


# ============================================================
# Patrimônio + variação
# ============================================================

def get_portfolio_overview(db: Session, account_id: Optional[int] = None) -> Dict[str, Any]:
    """Retorna patrimônio atual, variação no mês, rentabilidade e aporte do mês."""
    snaps = _latest_snapshots_per_account(db, account_id)

    total_value = Decimal("0")
    total_invested = Decimal("0")
    accounts_summary = []
    snapshot_dates = []

    for acc, snap in snaps:
        if snap:
            total_value += snap.total_value or Decimal("0")
            total_invested += snap.total_invested or Decimal("0")
            snapshot_dates.append(snap.snapshot_date)
            accounts_summary.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "snapshot_date": snap.snapshot_date.isoformat(),
                "total_value": float(snap.total_value or 0),
                "total_invested": float(snap.total_invested or 0),
            })

    # Variação no mês (comparar com snapshot anterior)
    monthly_change = None
    monthly_change_pct = None
    monthly_contribution = None
    if snaps:
        # Pegar a data mais recente entre todas as contas
        if snapshot_dates:
            max_date = max(snapshot_dates)
            # Procurar snapshots do mês anterior (até 60 dias antes)
            prev_target = max_date - timedelta(days=35)
            prev_total = _sum_total_at_or_before(db, prev_target, account_id)
            prev_invested = _sum_invested_at_or_before(db, prev_target, account_id)
            if prev_total:
                monthly_change = total_value - prev_total
                monthly_change_pct = float(_safe_div(monthly_change, prev_total) * 100)
            if prev_invested:
                monthly_contribution = float((total_invested or Decimal("0")) - prev_invested)

    return {
        "total_value": float(total_value),
        "total_invested": float(total_invested),
        "yield_value": float((total_value - total_invested) if total_invested else Decimal("0")),
        "yield_pct": float(_safe_div(total_value - total_invested, total_invested) * 100) if total_invested else 0.0,
        "monthly_change": float(monthly_change) if monthly_change is not None else None,
        "monthly_change_pct": monthly_change_pct,
        "monthly_contribution": monthly_contribution,
        "accounts": accounts_summary,
    }


def _latest_snapshots_per_account(
    db: Session, account_id: Optional[int] = None
) -> List[Tuple[BankAccount, Optional[InvestmentSnapshot]]]:
    """Retorna a última snapshot de cada conta de investimento."""
    if account_id:
        accounts = db.query(BankAccount).filter(BankAccount.id == account_id).all()
    else:
        accounts = (
            db.query(BankAccount)
            .filter(BankAccount.account_type == "INVESTMENT")
            .filter(BankAccount.is_active == True)
            .all()
        )
    out = []
    for acc in accounts:
        snap = (
            db.query(InvestmentSnapshot)
            .filter(InvestmentSnapshot.account_id == acc.id)
            .order_by(desc(InvestmentSnapshot.snapshot_date))
            .first()
        )
        out.append((acc, snap))
    return out


def _sum_total_at_or_before(
    db: Session, target_date: date, account_id: Optional[int] = None
) -> Decimal:
    """Soma o total_value de cada conta usando o snapshot <= target_date."""
    if account_id:
        accounts = db.query(BankAccount).filter(BankAccount.id == account_id).all()
    else:
        accounts = (
            db.query(BankAccount)
            .filter(BankAccount.account_type == "INVESTMENT")
            .filter(BankAccount.is_active == True)
            .all()
        )
    total = Decimal("0")
    for acc in accounts:
        snap = (
            db.query(InvestmentSnapshot)
            .filter(
                InvestmentSnapshot.account_id == acc.id,
                InvestmentSnapshot.snapshot_date <= target_date,
            )
            .order_by(desc(InvestmentSnapshot.snapshot_date))
            .first()
        )
        if snap:
            total += snap.total_value or Decimal("0")
    return total


def _sum_invested_at_or_before(
    db: Session, target_date: date, account_id: Optional[int] = None
) -> Decimal:
    if account_id:
        accounts = db.query(BankAccount).filter(BankAccount.id == account_id).all()
    else:
        accounts = (
            db.query(BankAccount)
            .filter(BankAccount.account_type == "INVESTMENT")
            .filter(BankAccount.is_active == True)
            .all()
        )
    total = Decimal("0")
    for acc in accounts:
        snap = (
            db.query(InvestmentSnapshot)
            .filter(
                InvestmentSnapshot.account_id == acc.id,
                InvestmentSnapshot.snapshot_date <= target_date,
            )
            .order_by(desc(InvestmentSnapshot.snapshot_date))
            .first()
        )
        if snap and snap.total_invested:
            total += snap.total_invested
    return total


# ============================================================
# Histórico (série temporal)
# ============================================================

def get_history(db: Session, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Série temporal de patrimônio total (consolidado entre contas).

    Para cada data com snapshot em qualquer conta, soma o último snapshot
    de cada conta até aquela data.
    """
    query = db.query(InvestmentSnapshot.snapshot_date).distinct()
    if account_id:
        query = query.filter(InvestmentSnapshot.account_id == account_id)
    dates = sorted([d[0] for d in query.all()])

    series = []
    prev_total = None
    for d in dates:
        total = _sum_total_at_or_before(db, d, account_id)
        invested = _sum_invested_at_or_before(db, d, account_id)
        change_pct = None
        if prev_total and prev_total > 0:
            change_pct = float(_safe_div(total - prev_total, prev_total) * 100)
        series.append({
            "date": d.isoformat(),
            "total_value": float(total),
            "total_invested": float(invested),
            "yield_value": float(total - invested) if invested else float(total),
            "monthly_change_pct": change_pct,
        })
        prev_total = total
    return series


# ============================================================
# Alocação
# ============================================================

def get_allocation(
    db: Session, account_id: Optional[int] = None, group_by: str = "class"
) -> List[Dict[str, Any]]:
    """Alocação atual agrupada por classe ('class'), banco ('bank') ou ativo ('asset')."""
    snaps = _latest_snapshots_per_account(db, account_id)
    snapshot_ids = [s.id for _, s in snaps if s]
    if not snapshot_ids:
        return []

    positions = (
        db.query(InvestmentPosition)
        .filter(InvestmentPosition.snapshot_id.in_(snapshot_ids))
        .all()
    )
    total_value = sum((p.value or Decimal("0")) for p in positions) or Decimal("1")

    grouped: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {"value": Decimal("0"), "name": "", "color": None})

    for p in positions:
        if group_by == "class":
            ac = p.asset.asset_class if p.asset and p.asset.asset_class else None
            key = ac.code.value if ac else "outros"
            grouped[key]["name"] = ac.name if ac else "Outros"
            grouped[key]["color"] = ac.color if ac else "#6B7280"
        elif group_by == "bank":
            snap = next((s for _, s in snaps if s and s.id == p.snapshot_id), None)
            if snap and snap.account:
                bank = db.query(Bank).filter(Bank.id == snap.account.bank_id).first()
                key = f"bank_{bank.id}" if bank else "unknown"
                grouped[key]["name"] = bank.name if bank else "Desconhecido"
                grouped[key]["color"] = bank.color if bank else "#6B7280"
            else:
                key = "unknown"
                grouped[key]["name"] = "Desconhecido"
        else:  # asset
            key = p.asset_id
            grouped[key]["name"] = p.asset.name if p.asset else "?"
            grouped[key]["color"] = p.asset.asset_class.color if p.asset and p.asset.asset_class else "#6B7280"
        grouped[key]["value"] += p.value or Decimal("0")

    out = []
    for k, v in grouped.items():
        out.append({
            "key": k,
            "name": v["name"],
            "color": v["color"],
            "value": float(v["value"]),
            "allocation_pct": float(_safe_div(v["value"], total_value) * 100),
        })
    out.sort(key=lambda x: -x["value"])
    return out


# ============================================================
# Exposição a cenários
# ============================================================

INFLATION_CLASSES = {AssetClassCode.INFLACAO}
CURRENCY_CLASSES = {AssetClassCode.CAMBIAL}
EQUITY_CLASSES = {AssetClassCode.RENDA_VARIAVEL, AssetClassCode.FII, AssetClassCode.CRIPTO}
FIXED_CLASSES = {
    AssetClassCode.RENDA_FIXA, AssetClassCode.POS_FIXADO, AssetClassCode.PRE_FIXADO,
    AssetClassCode.INFLACAO,
}


def get_exposure(db: Session, account_id: Optional[int] = None) -> Dict[str, float]:
    """Exposição (% do portfólio) a cenários."""
    snaps = _latest_snapshots_per_account(db, account_id)
    snapshot_ids = [s.id for _, s in snaps if s]
    if not snapshot_ids:
        return {}

    positions = (
        db.query(InvestmentPosition)
        .filter(InvestmentPosition.snapshot_id.in_(snapshot_ids))
        .all()
    )
    total = sum((p.value or Decimal("0")) for p in positions) or Decimal("1")

    inflation = Decimal("0")
    currency = Decimal("0")
    equity = Decimal("0")
    fixed = Decimal("0")
    crypto = Decimal("0")
    private_equity = Decimal("0")

    for p in positions:
        if not p.asset or not p.asset.asset_class:
            continue
        code = p.asset.asset_class.code
        v = p.value or Decimal("0")
        if code in INFLATION_CLASSES:
            inflation += v
        if code in CURRENCY_CLASSES:
            currency += v
        if code in EQUITY_CLASSES:
            equity += v
        if code in FIXED_CLASSES:
            fixed += v
        if code == AssetClassCode.CRIPTO:
            crypto += v
        if code == AssetClassCode.ALTERNATIVOS:
            private_equity += v

    return {
        "inflation_pct": float(_safe_div(inflation, total) * 100),
        "currency_pct": float(_safe_div(currency, total) * 100),
        "equity_pct": float(_safe_div(equity, total) * 100),
        "fixed_income_pct": float(_safe_div(fixed, total) * 100),
        "crypto_pct": float(_safe_div(crypto, total) * 100),
        "private_equity_pct": float(_safe_div(private_equity, total) * 100),
    }


# ============================================================
# Liquidez
# ============================================================

LIQUIDITY_BUCKETS = [
    ("imediato", 0, 0),
    ("d1", 1, 1),
    ("ate_30d", 2, 30),
    ("31_a_60d", 31, 60),
    ("61_a_360d", 61, 360),
    ("361_a_720d", 361, 720),
    ("acima_720d", 721, 99999),
]


def get_liquidity(db: Session, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Distribuição da carteira por bucket de liquidez."""
    snaps = _latest_snapshots_per_account(db, account_id)
    snapshot_ids = [s.id for _, s in snaps if s]
    if not snapshot_ids:
        return []

    positions = (
        db.query(InvestmentPosition)
        .filter(InvestmentPosition.snapshot_id.in_(snapshot_ids))
        .all()
    )
    total = sum((p.value or Decimal("0")) for p in positions) or Decimal("1")

    buckets = {key: Decimal("0") for key, _, _ in LIQUIDITY_BUCKETS}
    for p in positions:
        liq = None
        if p.asset:
            liq = p.asset.liquidity_days
            if liq is None and p.asset.asset_class:
                liq = p.asset.asset_class.typical_liquidity_days
        if liq is None:
            liq = 1
        for key, lo, hi in LIQUIDITY_BUCKETS:
            if lo <= liq <= hi:
                buckets[key] += p.value or Decimal("0")
                break

    return [
        {
            "bucket": key,
            "value": float(v),
            "pct": float(_safe_div(v, total) * 100),
        }
        for key, v in buckets.items()
    ]


# ============================================================
# Risco
# ============================================================

def get_risk_summary(db: Session, account_id: Optional[int] = None) -> Dict[str, Any]:
    """Risco médio ponderado (1-5) + distribuição por nível."""
    snaps = _latest_snapshots_per_account(db, account_id)
    snapshot_ids = [s.id for _, s in snaps if s]
    if not snapshot_ids:
        return {"weighted_avg": 0, "distribution": {}}

    positions = (
        db.query(InvestmentPosition)
        .filter(InvestmentPosition.snapshot_id.in_(snapshot_ids))
        .all()
    )
    total = sum((p.value or Decimal("0")) for p in positions) or Decimal("1")

    weighted_sum = Decimal("0")
    dist = defaultdict(lambda: Decimal("0"))
    for p in positions:
        risk = None
        if p.asset:
            risk = p.asset.risk_level
            if risk is None and p.asset.asset_class:
                risk = p.asset.asset_class.risk_level
        if risk is None:
            risk = 1
        weighted_sum += Decimal(risk) * (p.value or Decimal("0"))
        dist[risk] += p.value or Decimal("0")

    return {
        "weighted_avg": float(_safe_div(weighted_sum, total)),
        "distribution": {f"level_{k}": float(_safe_div(v, total) * 100) for k, v in dist.items()},
    }


# ============================================================
# Aportes mensais (volume)
# ============================================================

def get_monthly_contributions(
    db: Session, account_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Aportes mensais calculados via diferença de total_invested entre snapshots.

    aporte_mes = total_invested[N] - total_invested[N-1]
    """
    series = get_history(db, account_id)
    out = []
    prev_invested = None
    for s in series:
        invested = s["total_invested"]
        contribution = None
        if prev_invested is not None:
            contribution = invested - prev_invested
        out.append({
            "date": s["date"],
            "total_invested": invested,
            "contribution": contribution,
        })
        prev_invested = invested
    return out


# ============================================================
# Progresso de metas
# ============================================================

def evaluate_goal_progress(db: Session, goal: InvestmentGoal) -> Dict[str, Any]:
    """Calcula progresso atual de uma meta."""
    overview = get_portfolio_overview(db)
    if goal.type == GoalType.PORTFOLIO_TOTAL:
        current = Decimal(str(overview["total_value"]))
        target = goal.target_value or Decimal("0")
        progress = float(_safe_div(current, target) * 100) if target > 0 else 0
        return {"current": float(current), "progress_pct": progress}

    if goal.type == GoalType.MONTHLY_CONTRIBUTION:
        # Pegar último mês com aporte
        contribs = get_monthly_contributions(db)
        if contribs:
            last = contribs[-1]
            current = Decimal(str(last["contribution"] or 0))
            target = goal.target_value or Decimal("0")
            progress = float(_safe_div(current, target) * 100) if target > 0 else 0
            return {"current": float(current), "progress_pct": progress}
        return {"current": 0.0, "progress_pct": 0.0}

    if goal.type == GoalType.MIN_YIELD:
        target = goal.target_value or Decimal("0")
        current = Decimal(str(overview.get("yield_pct") or 0))
        progress = float(_safe_div(current, target) * 100) if target > 0 else 0
        return {"current": float(current), "progress_pct": progress}

    if goal.type == GoalType.ALLOCATION_BY_CLASS:
        if not goal.target_class_id:
            return {"current": 0.0, "progress_pct": 0.0}
        alloc = get_allocation(db, group_by="class")
        cls = db.query(AssetClass).filter(AssetClass.id == goal.target_class_id).first()
        if not cls:
            return {"current": 0.0, "progress_pct": 0.0}
        for a in alloc:
            if a["key"] == cls.code.value:
                current = Decimal(str(a["allocation_pct"]))
                target = goal.target_value or Decimal("0")
                progress = float(_safe_div(current, target) * 100) if target > 0 else 0
                return {"current": float(current), "progress_pct": progress}
        return {"current": 0.0, "progress_pct": 0.0}

    return {"current": 0.0, "progress_pct": 0.0}
