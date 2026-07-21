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


def _compute_yield_and_contribution(
    curr_snapshot: "InvestmentSnapshot",
    prev_snapshot: Optional["InvestmentSnapshot"],
    positions_by_snapshot: Dict[int, List["InvestmentPosition"]],
) -> Tuple[Decimal, Decimal]:
    """Calcula rendimento e aporte entre dois snapshots da mesma conta.

    Estratégia:
    - Compara posições por asset_id para detectar novas/removidas
    - Posições que se mantêm: Δ valor = rendimento
    - Posições novas com value_invested: rendimento = valor - invested, aporte = invested
    - Posições novas sem value_invested: trata como aporte
    - Posições removidas com value_invested: resgate do invested
    - Posições removidas sem value_invested: resgate do valor

    Se não há snapshot anterior (conta nova): todo valor = aporte, rendimento = 0.

    Retorna (rendimento, aporte).
    """
    curr_val = curr_snapshot.total_value or Decimal("0")

    if not prev_snapshot:
        # Conta nova: todo valor é aporte
        return Decimal("0"), curr_val

    prev_val = prev_snapshot.total_value or Decimal("0")

    # Posições dos dois snapshots (pré-carregadas no cache — sem query por chamada)
    curr_positions = positions_by_snapshot.get(curr_snapshot.id, [])
    prev_positions = positions_by_snapshot.get(prev_snapshot.id, [])

    # Se algum snapshot não tem posições, usar delta de total como rendimento
    if not curr_positions or not prev_positions:
        return curr_val - prev_val, Decimal("0")

    # Agrupar por asset_id (pode haver duplicatas — ex: 2 CDBs do mesmo emissor)
    from collections import defaultdict
    prev_by_asset: Dict[int, List] = defaultdict(list)
    for p in prev_positions:
        prev_by_asset[p.asset_id].append(p)

    rendimento = Decimal("0")
    aporte = Decimal("0")
    # Track consumed prev positions
    consumed_prev: Dict[int, int] = defaultdict(int)  # asset_id -> count consumed

    # Sort curr positions by value (match larger first for duplicate assets)
    for pos in sorted(curr_positions, key=lambda p: -(p.value or Decimal("0"))):
        pos_val = pos.value or Decimal("0")
        prev_list = prev_by_asset.get(pos.asset_id, [])
        idx = consumed_prev[pos.asset_id]

        if idx < len(prev_list):
            # Match with prev position (by order)
            prev_pos = sorted(prev_list, key=lambda p: -(p.value or Decimal("0")))[idx]
            consumed_prev[pos.asset_id] += 1
            rendimento += pos_val - (prev_pos.value or Decimal("0"))
        else:
            # Posição nova (ou duplicata extra)
            if pos.value_invested is not None:
                rendimento += pos_val - pos.value_invested
                aporte += pos.value_invested
            else:
                aporte += pos_val

    # Posições prev não consumidas (resgatadas)
    for asset_id, prev_list in prev_by_asset.items():
        remaining = len(prev_list) - consumed_prev[asset_id]
        if remaining > 0:
            sorted_prev = sorted(prev_list, key=lambda p: -(p.value or Decimal("0")))
            for prev_pos in sorted_prev[consumed_prev[asset_id]:]:
                if prev_pos.value_invested is not None:
                    aporte -= prev_pos.value_invested
                else:
                    aporte -= prev_pos.value or Decimal("0")

    # Detectar possíveis renomeações: se novas posições sem value_invested
    # e posições removidas sem value_invested somam valores similares,
    # provavelmente são o mesmo fundo com nome diferente.
    # Nesse caso, reclassificar essas entradas/saídas como rendimento.
    new_no_inv = Decimal("0")  # valor de posições novas sem value_invested
    gone_no_inv = Decimal("0")  # valor de posições removidas sem value_invested
    all_prev_aids = set(prev_by_asset.keys())
    for pos in curr_positions:
        if pos.asset_id not in all_prev_aids and pos.value_invested is None:
            new_no_inv += pos.value or Decimal("0")
    for asset_id, prev_list in prev_by_asset.items():
        remaining = len(prev_list) - consumed_prev.get(asset_id, 0)
        if remaining > 0:
            sorted_prev = sorted(prev_list, key=lambda p: -(p.value or Decimal("0")))
            for prev_pos in sorted_prev[consumed_prev.get(asset_id, 0):]:
                if prev_pos.value_invested is None:
                    gone_no_inv += prev_pos.value or Decimal("0")

    if new_no_inv > 0 and gone_no_inv > 0:
        # Provavelmente renomeações — cancelar essas entradas/saídas
        # e redistribuir como rendimento (delta entre valores novos e antigos)
        rendimento += new_no_inv - gone_no_inv
        aporte -= new_no_inv  # remover do aporte
        aporte += gone_no_inv  # remover resgate

    # Sanity check final: se ainda diverge muito, fallback para delta total
    sum_curr = sum((p.value or Decimal("0")) for p in curr_positions)
    sum_prev = sum((p.value or Decimal("0")) for p in prev_positions)
    delta_positions = sum_curr - sum_prev
    computed_total = rendimento + aporte
    divergencia = abs(computed_total - delta_positions)
    if sum_prev > 0 and divergencia > sum_prev * Decimal("0.01"):
        return curr_val - prev_val, Decimal("0")

    return rendimento, aporte


# ============================================================
# Cache de dados (uma carga consolidada por chamada)
# ============================================================

class _SnapshotCache:
    """Carrega snapshots e posições uma única vez e expõe consultas em memória."""

    def __init__(self, db: Session, account_id: Optional[int] = None,
                 account_ids: Optional[List[int]] = None):
        self.db = db
        self.account_id = account_id

        # Contas
        accs_q = db.query(BankAccount).filter(BankAccount.is_active == True)  # noqa: E712
        if account_id:
            accs_q = accs_q.filter(BankAccount.id == account_id)
        elif account_ids is not None:
            accs_q = accs_q.filter(BankAccount.id.in_(account_ids or [-1]))
        else:
            accs_q = accs_q.filter(BankAccount.account_type == "INVESTMENT")
        self.accounts: List[BankAccount] = accs_q.all()
        self.account_ids = {a.id for a in self.accounts}
        self.accounts_by_id = {a.id: a for a in self.accounts}

        # Bancos
        self.banks_by_id = {b.id: b for b in db.query(Bank).all()}

        # Snapshots (todas, ordenadas; apenas colunas escalares, sem lazy-load de positions)
        if not self.account_ids:
            self.snapshots: List[InvestmentSnapshot] = []
        else:
            from sqlalchemy.orm import noload
            self.snapshots = (
                db.query(InvestmentSnapshot)
                .options(noload(InvestmentSnapshot.positions))
                .filter(InvestmentSnapshot.account_id.in_(self.account_ids))
                .order_by(InvestmentSnapshot.snapshot_date)
                .all()
            )

        # Snapshots agrupados por conta (já ordenados por data asc)
        self._snaps_by_account: Dict[int, List[InvestmentSnapshot]] = defaultdict(list)
        for s in self.snapshots:
            self._snaps_by_account[s.account_id].append(s)

        # Preencher total_invested para contas que não têm:
        # Regra: primeiro snapshot da conta define o capital base (total_invested = total_value).
        # Snapshots seguintes herdam o anterior se não têm valor próprio.
        for acc_id, snaps in self._snaps_by_account.items():
            if not snaps:
                continue
            first = snaps[0]
            if not first.total_invested:
                # Capital base = patrimônio do primeiro snapshot
                first.total_invested = first.total_value
            prev_invested = first.total_invested
            for s in snaps[1:]:
                if not s.total_invested:
                    s.total_invested = prev_invested
                prev_invested = s.total_invested

        # Última snapshot por conta
        self._latest_by_account: Dict[int, InvestmentSnapshot] = {
            acc_id: snaps[-1] for acc_id, snaps in self._snaps_by_account.items() if snaps
        }
        self.latest_snapshot_ids = {s.id for s in self._latest_by_account.values()}

        # Posições de TODAS as snapshots carregadas de uma vez (eager load
        # asset + asset_class), agrupadas por snapshot_id. Evita 2 queries por
        # par de snapshots no cálculo de rendimento/aporte (get_history/overview).
        all_snapshot_ids = [s.id for s in self.snapshots]
        self.positions_by_snapshot: Dict[int, List[InvestmentPosition]] = defaultdict(list)
        if all_snapshot_ids:
            all_positions = (
                db.query(InvestmentPosition)
                .options(
                    selectinload(InvestmentPosition.asset).selectinload(Asset.asset_class),
                )
                .filter(InvestmentPosition.snapshot_id.in_(all_snapshot_ids))
                .all()
            )
            for p in all_positions:
                self.positions_by_snapshot[p.snapshot_id].append(p)

        # Posições das últimas snapshots (reaproveitando o que já foi carregado)
        self.latest_positions: List[InvestmentPosition] = [
            p for sid in self.latest_snapshot_ids
            for p in self.positions_by_snapshot.get(sid, [])
        ]

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
# Fluxos mensais (aporte / rendimento a partir das categorias)
# ============================================================
# Categorias de fluxo (selecionadas pelo CAMPO CATEGORIA, em qualquer conta):
CAT_APLICACAO = 1
CAT_JUROS = 14        # despesas de juros (ex.: juros de cartão)
CAT_RENDIMENTO = 21
CAT_RESGATE = 22


def _monthly_flows(db: Session) -> Dict[str, Dict[str, Decimal]]:
    """Soma, por mês (YYYY-MM), os fluxos a partir do CAMPO CATEGORIA em TODAS
    as contas.

    Retorna {ym: {aplic_abs, resg_net, aporte, rend, juros}}.
    - aporte = |Aplicação(1)| − Resgate_líquido(22)  (dinheiro novo líquido)
    - resg_net = Σ Resgate(22) COM SINAL — taxas (IRRF/IOF, negativas) reduzem
      o valor resgatado.
    - rend   = Σ Rendimento(21)  (proventos de investimento; inclui cupons)
    - juros  = Σ Juros(14)  (despesas de juros; normalmente negativo)
    """
    from app.models import Transaction
    flows: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"aplic_abs": Decimal("0"), "resg_net": Decimal("0"),
                 "rend": Decimal("0"), "juros": Decimal("0")}
    )
    rows = (
        db.query(Transaction.date, Transaction.category_id, Transaction.amount_brl)
        .filter(Transaction.category_id.in_(
            [CAT_APLICACAO, CAT_JUROS, CAT_RENDIMENTO, CAT_RESGATE]))
        .all()
    )
    for d, cat, amt in rows:
        amt = amt or Decimal("0")
        f = flows[d.strftime("%Y-%m")]
        if cat == CAT_APLICACAO:
            f["aplic_abs"] += abs(amt)
        elif cat == CAT_RESGATE:
            f["resg_net"] += amt          # com sinal: taxas negativas reduzem
        elif cat == CAT_RENDIMENTO:
            f["rend"] += amt
        elif cat == CAT_JUROS:
            f["juros"] += amt
    for f in flows.values():
        f["aporte"] = f["aplic_abs"] - f["resg_net"]
    return flows


def get_investment_series(
    db: Session, cache: Optional[_SnapshotCache] = None
) -> List[Dict[str, Any]]:
    """Série mensal consolidada do dashboard de investimentos.

    Por mês (data = fim do mês de cada snapshot):
      - total_value: patrimônio (contas Carteira + XP Global)
      - variacao:    total_value(m) − total_value(m−1)
      - aporte:      |Aplicação| − Resgate_líquido do mês  (item 2; taxas reduzem o resgate)
      - yield_value: variacao − aporte + Rendimento(21) − |Juros(14)|  (item 3)
      - yield_pct:   yield_value / total_value(m−1)  (rentab. do mês)
      - total_invested: capital acumulado ("Aportado") = base + Σ aportes (item 6)
    """
    cache = cache or _SnapshotCache(db)
    flows = _monthly_flows(db)

    series: List[Dict[str, Any]] = []
    prev_v: Optional[Decimal] = None
    aportado_cum = Decimal("0")
    for d in cache.distinct_dates:
        ym = d.strftime("%Y-%m")
        v = cache.sum_total_at_or_before(d)
        f = flows.get(ym)
        aporte = f["aporte"] if f else Decimal("0")
        rend_cat = f["rend"] if f else Decimal("0")
        juros = f["juros"] if f else Decimal("0")

        if prev_v is None:
            variacao = Decimal("0")
            yield_value = Decimal("0")
            yield_ratio = 0.0
            aportado_cum = v  # base = patrimônio inicial
        else:
            variacao = v - prev_v
            # Juros (cat 14) é despesa lançada negativa → subtrai o módulo
            yield_value = variacao - aporte + rend_cat - abs(juros)
            yield_ratio = float(yield_value / prev_v) if prev_v else 0.0
            aportado_cum = aportado_cum + aporte

        series.append({
            "date": d.isoformat(),
            "total_value": float(v),
            "total_invested": float(aportado_cum),  # linha "Aportado"
            "variacao": float(variacao),
            "aporte": float(aporte),
            "yield_value": float(yield_value),
            "yield_pct": round(yield_ratio * 100, 2),
            "yield_ratio": yield_ratio,  # sem arredondar (p/ acumulado)
        })
        prev_v = v
    return series


def _ytd_return_pct(series: List[Dict[str, Any]], target_ym: str) -> float:
    """Rentabilidade acumulada no ano até target_ym (encadeada / time-weighted)."""
    year = target_ym[:4]
    acc = 1.0
    for s in series:
        sym = s["date"][:7]
        if sym[:4] == year and sym <= target_ym:
            acc *= (1 + s.get("yield_ratio", 0.0))
    return round((acc - 1) * 100, 2)


# ============================================================
# Patrimônio + variação
# ============================================================

def get_portfolio_overview(
    db: Session, account_id: Optional[int] = None,
    cache: Optional[_SnapshotCache] = None,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Retorna patrimônio, variação no mês, rentabilidade e aporte.

    Se reference_date for informado, calcula para aquela data (em vez do último snapshot).
    """
    cache = cache or _SnapshotCache(db, account_id)
    series = get_investment_series(db, cache)

    if not series:
        return {
            "total_value": 0.0, "total_invested": 0.0,
            "monthly_change": None, "monthly_contribution": None,
            "monthly_yield_value": None, "monthly_yield_pct": None,
            "ytd_yield_pct": None, "yield_value": 0.0, "yield_pct": 0.0,
            "reference_date": (reference_date or date.today()).isoformat(),
            "accounts": [],
        }

    # Ponto de referência: mês selecionado (<=) ou último disponível
    if reference_date:
        target_ym = reference_date.strftime("%Y-%m")
        point = None
        for s in series:
            if s["date"][:7] <= target_ym:
                point = s
        point = point or series[0]
    else:
        point = series[-1]
    target_ym = point["date"][:7]
    target_date = date.fromisoformat(point["date"])

    # Composição das contas nesse mês (patrimônio por conta)
    accounts_summary = []
    for acc_id, snaps in cache._snaps_by_account.items():
        chosen = None
        for s in snaps:
            if s.snapshot_date <= target_date:
                chosen = s
            else:
                break
        if chosen:
            acc = cache.accounts_by_id.get(acc_id)
            accounts_summary.append({
                "account_id": acc_id,
                "account_name": acc.name if acc else str(acc_id),
                "snapshot_date": chosen.snapshot_date.isoformat(),
                "total_value": float(chosen.total_value or 0),
            })

    ytd = _ytd_return_pct(series, target_ym)
    return {
        "total_value": point["total_value"],
        "total_invested": point["total_invested"],           # capital aportado acumulado
        "monthly_change": point["variacao"],                 # (1) Variação no mês
        "monthly_contribution": point["aporte"],             # (2) Aporte do mês
        "monthly_yield_value": point["yield_value"],         # (3) Rendimento do mês (R$)
        "monthly_yield_pct": point["yield_pct"],             # (3) Rentabilidade do mês (%)
        "ytd_yield_pct": ytd,                                # (5) Rentabilidade acumulada no ano
        # compat: rentabilidade "total" agora reflete o acumulado do ano
        "yield_value": point["yield_value"],
        "yield_pct": ytd,
        "reference_date": target_date.isoformat(),
        "accounts": accounts_summary,
    }


# ============================================================
# Histórico (série temporal)
# ============================================================

def get_history(db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None) -> List[Dict[str, Any]]:
    """Série mensal consolidada (patrimônio, aportado, aporte e rendimento)."""
    cache = cache or _SnapshotCache(db, account_id)
    return get_investment_series(db, cache)


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
    db: Session, account_id: Optional[int] = None, cache: Optional[_SnapshotCache] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Aportes mensais (diferença de total_invested entre snapshots).

    Aceita `history` já calculado para evitar recomputar a série (custoso).
    """
    series = history if history is not None else get_history(db, account_id, cache=cache)
    # (8) Aportes mensais = item 2 (|Aplicação| − |Resgate|) por mês
    return [
        {
            "date": s["date"],
            "total_invested": s["total_invested"],
            "contribution": s.get("aporte"),
        }
        for s in series
    ]


# ============================================================
# Progresso de metas
# ============================================================

# ============================================================
# Rentabilidade por ATIVO (mês a mês + acumulado)
# ============================================================
# Fluxos por ativo vêm das transações que foram vinculadas (asset_id) na conta
# corrente da corretora. Categorias:
#   Aplicação(1)  -> dinheiro que entrou no ativo (negativo no extrato)
#   Resgate(22)   -> dinheiro que saiu do ativo  (positivo; taxas negativas reduzem)
#   Rendimento(21)-> cupom/amortização/provento pago em caixa (positivo)


def _asset_flows_by_month(db: Session) -> Dict[int, Dict[str, Dict[str, Decimal]]]:
    """{asset_id: {ym: {aplic_abs, resg_net, cupom}}} a partir de transactions.asset_id."""
    from app.models import Transaction
    out: Dict[int, Dict[str, Dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {
            "aplic_abs": Decimal("0"), "resg_net": Decimal("0"), "cupom": Decimal("0")})
    )
    rows = (
        db.query(Transaction.asset_id, Transaction.date,
                 Transaction.category_id, Transaction.amount_brl)
        .filter(Transaction.asset_id.isnot(None),
                Transaction.category_id.in_([CAT_APLICACAO, CAT_RENDIMENTO, CAT_RESGATE]))
        .all()
    )
    for aid, d, cat, amt in rows:
        amt = amt or Decimal("0")
        f = out[aid][d.strftime("%Y-%m")]
        if cat == CAT_APLICACAO:
            f["aplic_abs"] += abs(amt)
        elif cat == CAT_RESGATE:
            f["resg_net"] += amt
        elif cat == CAT_RENDIMENTO:
            f["cupom"] += amt
    return out


def get_asset_yield_series(
    db: Session, carteira_account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Rentabilidade por ativo, mês a mês e acumulada.

    Cobre TODAS as carteiras de investimento por padrão (XP/Itaú/C6...); se
    `carteira_account_id` for informado, restringe a essa conta.

    Para cada ativo:
      valor(m)        = marcação a mercado no fim do mês m (soma de posições do ativo)
      aporte(m)       = fluxo vinculado (|Aplicação| − Resgate_líquido) quando o
                        ativo tem lançamentos com asset_id (XP); senão, Δvalue_invested
                        da posição (Itaú, quando disponível); senão 0 (só marcação).
      cupom(m)        = Σ Rendimento pago em caixa do ativo no mês (só XP vinculado)
      rendimento(m)   = (valor(m) − valor(m−1)) − aporte(m) + cupom(m)
      rentab(m) %     = rendimento(m) / base, base = valor(m−1) ou custo se novo
      acumulada %     = Π(1 + rentab(m)) − 1  (encadeada)

    Nota: Itaú/C6 não têm aporte/cupom vinculados por ativo; a rentabilidade
    deles sai da marcação a mercado (ok p/ fundos que reinvestem).
    """
    # Contas de carteira (investment) + mapa de banco
    acc_q = db.query(BankAccount).filter(
        BankAccount.account_type == "INVESTMENT", BankAccount.is_active == True)  # noqa: E712
    if carteira_account_id:
        acc_q = acc_q.filter(BankAccount.id == carteira_account_id)
    accounts = acc_q.all()
    if not accounts:
        return {"assets": [], "months": [], "reconciliation": [], "banks": []}
    acc_ids = [a.id for a in accounts]
    banks_by_id = {b.id: b for b in db.query(Bank).all()}
    acc_bank = {
        a.id: (a.bank_id, banks_by_id[a.bank_id].name if a.bank_id in banks_by_id else a.name)
        for a in accounts
    }

    # Snapshots das carteiras (ordenados) + posições
    snaps = (
        db.query(InvestmentSnapshot)
        .filter(InvestmentSnapshot.account_id.in_(acc_ids))
        .order_by(InvestmentSnapshot.snapshot_date)
        .all()
    )
    if not snaps:
        return {"assets": [], "months": [], "reconciliation": [], "banks": []}

    snap_acc = {s.id: s.account_id for s in snaps}
    snap_ids = [s.id for s in snaps]
    positions = (
        db.query(InvestmentPosition)
        .options(selectinload(InvestmentPosition.asset).selectinload(Asset.asset_class))
        .filter(InvestmentPosition.snapshot_id.in_(snap_ids))
        .all()
    )

    # valor por (asset_id, ym): soma de posições do ativo no snapshot do mês
    ym_of_snap = {s.id: s.snapshot_date.strftime("%Y-%m") for s in snaps}
    months = sorted({ym for ym in ym_of_snap.values()})
    asset_meta: Dict[int, Dict[str, Any]] = {}
    value_by_asset_ym: Dict[int, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    vinv_by_asset_ym: Dict[int, Dict[str, Decimal]] = defaultdict(dict)  # value_invested por (asset, ym)
    for p in positions:
        aid = p.asset_id
        ym = ym_of_snap[p.snapshot_id]
        value_by_asset_ym[aid][ym] += p.value or Decimal("0")
        if p.value_invested is not None:
            vinv_by_asset_ym[aid][ym] = vinv_by_asset_ym[aid].get(ym, Decimal("0")) + p.value_invested
        if aid not in asset_meta and p.asset:
            ac = p.asset.asset_class
            bank_id, bank_name = acc_bank.get(snap_acc[p.snapshot_id], (None, None))
            asset_meta[aid] = {
                "asset_id": aid,
                "asset_name": p.asset.name,
                "ticker": p.asset.ticker,
                "asset_class": ac.name if ac else None,
                "color": ac.color if ac else "#6B7280",
                "bank_id": bank_id,
                "bank": bank_name,
            }

    flows = _asset_flows_by_month(db)
    # ativos sem posição mas com fluxo (ex.: resgatados) — incluir também
    for aid in flows:
        if aid not in asset_meta:
            a = db.get(Asset, aid)
            if a:
                asset_meta[aid] = {
                    "asset_id": aid, "asset_name": a.name, "ticker": a.ticker,
                    "asset_class": a.asset_class.name if a.asset_class else None,
                    "color": a.asset_class.color if a.asset_class else "#6B7280",
                    "bank_id": None, "bank": None,
                }

    # Reconciliação mensal (soma dos ativos)
    recon_by_ym: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    base_month = months[0] if months else None

    assets_out: List[Dict[str, Any]] = []
    for aid, meta in asset_meta.items():
        vseries = value_by_asset_ym.get(aid, {})
        fseries = flows.get(aid, {})
        vinvseries = vinv_by_asset_ym.get(aid, {})
        has_flows = aid in flows          # XP: fluxos vinculados são a fonte
        month_rows: List[Dict[str, Any]] = []
        prev_val: Optional[Decimal] = None
        prev_vinv: Optional[Decimal] = None
        accum = Decimal("1")
        total_yield = Decimal("0")
        for ym in months:
            val = vseries.get(ym)
            if has_flows:
                f = fseries.get(ym)
                aplic = f["aplic_abs"] if f else Decimal("0")
                resg = f["resg_net"] if f else Decimal("0")
                cupom = f["cupom"] if f else Decimal("0")
                aporte = aplic - resg
            else:
                # Sem fluxo vinculado (Itaú/C6): aporte = Δvalue_invested se houver.
                f = None
                cupom = Decimal("0")
                cur_vinv = vinvseries.get(ym)
                if cur_vinv is not None and prev_vinv is not None:
                    aporte = cur_vinv - prev_vinv
                else:
                    aporte = Decimal("0")
                if cur_vinv is not None:
                    prev_vinv = cur_vinv
            # valor corrente: se não há posição no mês mas houve antes, usa 0
            # (ativo resgatado); se nunca houve, pula até aparecer.
            if val is None and prev_val is None and not f and aporte == 0:
                continue
            cur_val = val if val is not None else Decimal("0")
            # Posição sumiu (valor 0) sem resgate vinculado explicando a saída:
            # assume capital devolvido (resgate/vencimento), não perda de −100%.
            if cur_val == 0 and prev_val and prev_val > 0 and aporte == 0:
                aporte = -prev_val
            if prev_val is None:
                if ym == base_month:
                    # 1º snapshot da série: baseline, sem base de custo anterior
                    base = Decimal("0")
                    rendimento = Decimal("0")
                else:
                    # Ativo novo (1ª aparição mid-série): o mês de entrada é
                    # baseline — não medimos valorização (não sabemos o preço
                    # exato de entrada dentro do mês), só o cupom. Evita tanto
                    # contar a compra como ~100% de rendimento quanto artefatos
                    # de lote (aporte num lote, valor no outro).
                    base = aporte if aporte > 0 else cur_val
                    rendimento = cupom
            else:
                base = prev_val if prev_val > 0 else (aporte if aporte > 0 else Decimal("0"))
                rendimento = (cur_val - prev_val) - aporte + cupom
            ratio = float(rendimento / base) if base and base != 0 else 0.0
            accum *= Decimal(str(1 + ratio))
            total_yield += rendimento
            recon_by_ym[ym] += rendimento
            month_rows.append({
                "date": ym,
                "value": float(cur_val),
                "aporte": float(aporte),
                "cupom": float(cupom),
                "yield_value": float(rendimento),
                "yield_pct": round(ratio * 100, 2),
                "yield_ratio": ratio,  # sem arredondar (p/ acumular 12m/ano no front)
            })
            prev_val = cur_val

        if not month_rows:
            continue
        last_val = month_rows[-1]["value"]
        assets_out.append({
            **meta,
            "current_value": last_val,
            "yield_total_value": float(total_yield),
            "yield_accum_pct": round(float(accum - 1) * 100, 2),
            "months": month_rows,
        })

    assets_out.sort(key=lambda a: -a["current_value"])

    # Reconciliação: rendimento total por ativo por mês + magnitude de fluxos
    # NÃO atribuídos (asset_id NULL) na conta corrente da corretora. Um mês com
    # `unlinked_flow` alto sinaliza que a rentabilidade por ativo pode estar
    # distorcida até esses lançamentos serem vinculados na tela de ajuste.
    from app.models import Transaction
    unlinked_ym: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    urows = (
        db.query(Transaction.date, Transaction.amount_brl)
        .filter(Transaction.account_id == 9, Transaction.asset_id.is_(None),
                Transaction.category_id.in_([CAT_APLICACAO, CAT_RENDIMENTO, CAT_RESGATE]))
        .all()
    )
    for d, amt in urows:
        unlinked_ym[d.strftime("%Y-%m")] += abs(amt or Decimal("0"))

    reconciliation = [
        {
            "date": ym,
            "sum_assets_yield": float(recon_by_ym.get(ym, Decimal("0"))),
            "unlinked_flow": float(unlinked_ym.get(ym, Decimal("0"))),
        }
        for ym in months
    ]

    # Bancos presentes (para o filtro no front)
    banks_present: List[Dict[str, Any]] = []
    seen_banks = set()
    for a in assets_out:
        bid = a.get("bank_id")
        if bid is not None and bid not in seen_banks:
            seen_banks.add(bid)
            banks_present.append({"bank_id": bid, "bank": a.get("bank")})
    banks_present.sort(key=lambda b: b["bank"] or "")

    return {
        "assets": assets_out, "months": months,
        "reconciliation": reconciliation, "banks": banks_present,
    }


def evaluate_goal_progress(
    db: Session, goal: InvestmentGoal,
    cache: Optional[_SnapshotCache] = None,
    overview: Optional[Dict[str, Any]] = None,
    contributions: Optional[List[Dict[str, Any]]] = None,
    allocation: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Calcula progresso atual de uma meta.

    Aceita cache/overview/contributions/allocation já calculados para avaliar
    várias metas sem recomputar (evita N caches para N metas).
    """
    cache = cache or _SnapshotCache(db)
    if overview is None:
        overview = get_portfolio_overview(db, cache=cache)
    if goal.type == GoalType.PORTFOLIO_TOTAL:
        current = Decimal(str(overview["total_value"]))
        target = goal.target_value or Decimal("0")
        progress = float(_safe_div(current, target) * 100) if target > 0 else 0
        return {"current": float(current), "progress_pct": progress}

    if goal.type == GoalType.MONTHLY_CONTRIBUTION:
        # Pegar último mês com aporte
        contribs = contributions if contributions is not None else get_monthly_contributions(db, cache=cache)
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
        alloc = allocation if allocation is not None else get_allocation(db, group_by="class", cache=cache)
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
