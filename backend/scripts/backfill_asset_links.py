"""Backfill: vincula transações (Rendimento/Aplicação/Resgate) da conta XP
corrente (id=9) ao ativo de investimento, gravando transactions.asset_id.

- Universo de ativos = os que já apareceram na carteira XP (conta 11).
- Só grava matches de confiança "high" (ticker ou prefixo forte de nome).
  Confiança "low"/"ambiguous"/"none" ficam com asset_id NULL para revisão manual.
- Só preenche onde asset_id É NULL (preserva ajustes manuais).
- Também popula assets.ticker a partir do índice do matcher.

Uso:
    python -m scripts.backfill_asset_links          # dry-run (relatório)
    python -m scripts.backfill_asset_links --commit # grava
"""
import sys
from decimal import Decimal
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.models import Asset, InvestmentPosition, InvestmentSnapshot, Transaction
from app.services.asset_matcher import AssetMatcher

XP_CONTA = 9
XP_CARTEIRA = 11
CATEGORIES = {1: "APLICACAO", 21: "RENDIMENTO", 22: "RESGATE"}


def main(commit: bool):
    db = SessionLocal()

    rows = (
        db.query(Asset.id, Asset.name)
        .join(InvestmentPosition, InvestmentPosition.asset_id == Asset.id)
        .join(InvestmentSnapshot, InvestmentSnapshot.id == InvestmentPosition.snapshot_id)
        .filter(InvestmentSnapshot.account_id == XP_CARTEIRA)
        .distinct()
        .all()
    )
    matcher = AssetMatcher([(aid, name) for aid, name in rows])

    # 1) popular assets.ticker a partir do índice
    ticker_updates = 0
    inv_ticker = defaultdict(list)  # asset_id -> [tickers]
    for tk, aid in matcher.ticker_idx.items():
        inv_ticker[aid].append(tk)
    for aid, tks in inv_ticker.items():
        asset = db.get(Asset, aid)
        if asset and not asset.ticker:
            asset.ticker = sorted(tks)[0]
            ticker_updates += 1
    print(f"assets.ticker a preencher: {ticker_updates}")

    # 2) casar transações
    total_set = 0
    for cat, cat_name in CATEGORIES.items():
        txns = (
            db.query(Transaction)
            .filter(Transaction.account_id == XP_CONTA, Transaction.category_id == cat)
            .order_by(Transaction.date)
            .all()
        )
        by_conf = defaultdict(lambda: {"n": 0, "val": Decimal("0")})
        set_here = 0
        for t in txns:
            r = matcher.match(t.description)
            by_conf[r.confidence]["n"] += 1
            by_conf[r.confidence]["val"] += abs(t.amount_brl or Decimal("0"))
            if r.confidence == "high" and t.asset_id is None:
                t.asset_id = r.asset_id
                set_here += 1
        total_set += set_here
        print("=" * 60)
        print(f"{cat} {cat_name} — {len(txns)} txns | asset_id a gravar: {set_here}")
        for conf in ("high", "low", "ambiguous", "none"):
            if conf in by_conf:
                d = by_conf[conf]
                print(f"   {conf:10s}: {d['n']:3d}  (R$ {d['val']:,.2f})")

    print("=" * 60)
    print(f"TOTAL asset_id a gravar: {total_set} | tickers: {ticker_updates}")
    if commit:
        db.commit()
        print(">>> COMMIT feito.")
    else:
        db.rollback()
        print(">>> DRY-RUN (use --commit para gravar).")
    db.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
