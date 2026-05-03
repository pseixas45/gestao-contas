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

from sqlalchemy.orm import Session, selectinload
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
# Cache de dados (uma carga consolidada por chamada)
# ============================================================

class _SnapshotCache:
    """Carrega snapshots e posições uma única vez e expõe consultas em memória."""

    def __init__(self, db: Session, account_id: Optional[int] = None):
        self.db = db
        self.account_id = account_id

        # Contas
        accs_q = db.query(BankAccount).filter(BankAccount.is_active == True)
        if account_id:
            accs_q = accs_q.filter(BankAccount.id == account_id)
        else:
            accs_q = accs_q.filter(BankAccount.account_type == "INVESTMENT")
        self.accounts: List[BankAccount] = accs_q.all()
        self.account_ids = {a.id for a in self.accounts}
        self.accounts_by_id = {a.id: a for a in self.accounts}

        # Bancos
        self.banks_by_id = {b.id: b for b in db.query(Bank).all()}

        # Snapshots (todas, ordenadas; ainda só para as contas relevantes)
        if not self.account_ids:
            self.snapshots: List[InvestmentSnapshot] = []
        else:
            self.snapshots = (
                db.query(InvestmentSnapshot)
                .filter(InvestmentSnapshot.account_id.in_(self.account_ids))
                .order_by(InvestmentSnapshot.snapshot_date)
                .all()
            )

        # Snapshots agrupados por conta (já ordenados por data asc)
        self._snaps_by_account: Dict[int, List[InvestmentSnapshot]] = defaultdict(list)
        for s in self.snapshots:
            self._snaps_by_account[s.account_id].append(s)

        # Última snapshot por conta
        self._latest_by_account: Dict[int, InvestmentSnapshot] = {
            acc_id: snaps[-1] for acc_id, snaps in self._snaps_by_account.items() if snaps
        }
        self.latest_snapshot_ids = {s.id for s in self._latest_by_account.values()}

        # Posições (eager load asset + asset_class) das últimas snapshots
        if self.latest_snapshot_ids:
            self.latest_positions: List[InvestmentPosition] = (
                db.query(InvestmentPosition)
                .options(
                    selectinload(InvestmentPosition.asset).selectinload(Asset.asset_class),
                )
                .filter(InvestmentPosition.snapshot_id.in_(self.latest_snapshot_ids))
                .all()
            )
        else:
            self.latest_positions = []

        # Datas distintas em que houve snapshot (qualquer conta)
        self.distinct_dates: List[date] = sorted({s.snapshot_date for s in self.snapshots})

    def latest_per_account(self) -> List[Tuple[BankAccount, Optional[InvestmentSnapshot]]]:
        return [(acc, self._latest_by_account.get(acc.id)) for acc in self.accounts]

    def sum_total_at_or_before(self, target_date: date) -> Decimal:
        total = Decimal("0")
        for acc_id, snaps in self._snaps_by_account.items():
            # snaps já está ordenado asc; pega o último <= target
            chosen = None
            for s in snaps:
                if s.snapshot_date <= target_date:
                    chosen = s
                else:
                    break
            if chosen and chosen.total_value:
                total += chosen.total_value
        return total

    def sum_invested_at_or_before(self, target_date: date) -> Decimal:
        total = Decimal("0")
        for acc_id, snaps in self._snaps_by_account.items():
            chosen = None
            for s in snaps:
                if s.snapshot_date <= target_date:
                    chosen = s
                else:
                    break
            if chosen and chosen.total_invested:
                total += chosen.total_invested
        return total


# ============================================================
# Patrimônio + variação
# ============================================================

def get_portfolio_overview(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> Dict[str, Any]:
    """Retorna patrimônio atual, variação no mês, rentabilidade e aporte do mês."""
    cache = cache or _SnapshotCache(db, account_id)
    snaps = cache.latest_per_account()

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

    monthly_change = None
    monthly_change_pct = None
    monthly_contribution = None
    if snapshot_dates:
        max_date = max(snapshot_dates)
        prev_target = max_date - timedelta(days=35)
        prev_total = cache.sum_total_at_or_before(prev_target)
        prev_invested = cache.sum_invested_at_or_before(prev_target)
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


# ============================================================
# Histórico (série temporal)
# ============================================================

def get_history(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> List[Dict[str, Any]]:
    """Série temporal de patrimônio total (consolidado entre contas)."""
    cache = cache or _SnapshotCache(db, account_id)

    series = []
    prev_total: Optional[Decimal] = None
    for d in cache.distinct_dates:
        total = cache.sum_total_at_or_before(d)
        invested = cache.sum_invested_at_or_before(d)
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
    db: Session, account_id: Optional[int] = None, group_by: str = "class",
    cache: Optional[_SnapshotCache] = None,
) -> List[Dict[str, Any]]:
    """Alocação atual agrupada por classe ('class'), banco ('bank') ou ativo ('asset')."""
    cache = cache or _SnapshotCache(db, account_id)
    positions = cache.latest_positions
    if not positions:
        return []

    # Mapa snapshot_id -> account_id (para agrupar por banco)
    snap_to_acc: Dict[int, int] = {}
    for snap in cache.snapshots:
        if snap.id in cache.latest_snapshot_ids:
            snap_to_acc[snap.id] = snap.account_id

    total_value = sum((p.value or Decimal("0")) for p in positions) or Decimal("1")

    grouped: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {"value": Decimal("0"), "name": "", "color": None})

    for p in positions:
        if group_by == "class":
            ac = p.asset.asset_class if p.asset and p.asset.asset_class else None
            key = ac.code.value if ac else "outros"
            grouped[key]["name"] = ac.name if ac else "Outros"
            grouped[key]["color"] = ac.color if ac else "#6B7280"
        elif group_by == "bank":
            acc_id = snap_to_acc.get(p.snapshot_id)
            acc = cache.accounts_by_id.get(acc_id) if acc_id else None
            bank = cache.banks_by_id.get(acc.bank_id) if acc and acc.bank_id else None
            key = f"bank_{bank.id}" if bank else "unknown"
            grouped[key]["name"] = bank.name if bank else "Desconhecido"
            grouped[key]["color"] = bank.color if bank else "#6B7280"
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


def get_exposure(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> Dict[str, float]:
    """Exposição (% do portfólio) a cenários."""
    cache = cache or _SnapshotCache(db, account_id)
    positions = cache.latest_positions
    if not positions:
        return {}

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


def get_liquidity(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> List[Dict[str, Any]]:
    """Distribuição da carteira por bucket de liquidez."""
    cache = cache or _SnapshotCache(db, account_id)
    positions = cache.latest_positions
    if not positions:
        return []

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

def get_risk_summary(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> Dict[str, Any]:
    """Risco médio ponderado (1-5) + distribuição por nível."""
    cache = cache or _SnapshotCache(db, account_id)
    positions = cache.latest_positions
    if not positions:
        return {"weighted_avg": 0, "distribution": {}}

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
    db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None
) -> List[Dict[str, Any]]:
    """Aportes mensais (diferença de total_invested entre snapshots)."""
    series = get_history(db, account_id, cache=cache)
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
