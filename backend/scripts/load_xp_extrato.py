import sys
sys.stdout.reconfigure(encoding="utf-8")
from decimal import Decimal
from collections import defaultdict
import argparse

from sqlalchemy import text
from app.database import SessionLocal
from app.models import Transaction, CurrencyCode
from app.services.parsers.xp_extrato_conta_parser import parse_xp_extrato_conta

ACCOUNT_ID = 9  # XP conta corrente (oculta do dashboard)
PATH = r"C:\Users\paulo\gestao-contas\extratos\XP Extrato 4065643 JAN. 2025 a JUL. 2026.xlsx"

CAT_NAMES = {1: "Aplicação", 12: "Impostos", 21: "Rendimento", 22: "Resgate", 30: "Transferência"}


def load_rate_lookup(db):
    """Retorna função nearest_rate(currency, date) usando cache exchange_rates."""
    rows = db.execute(text("""
        SELECT currency::text, date_ref, sell_rate FROM gestao_contas.exchange_rates
        WHERE currency IN ('USD','EUR') AND sell_rate IS NOT NULL
        ORDER BY date_ref
    """)).fetchall()
    by_cur = defaultdict(list)
    for cur, d, rate in rows:
        by_cur[cur].append((d, Decimal(str(rate))))

    def nearest(currency, dt):
        lst = by_cur.get(currency, [])
        if not lst:
            return None
        chosen = None
        for d, rate in lst:
            if d <= dt:
                chosen = rate
            else:
                break
        return chosen or lst[-1][1]  # se dt antes do 1o, usa o 1o
    return nearest


def main(commit: bool):
    db = SessionLocal()
    movements = parse_xp_extrato_conta(PATH)
    print(f"Movimentações parseadas: {len(movements)}")
    if movements:
        print(f"Período: {movements[-1]['date']} .. {movements[0]['date']}")

    # Resumo por kind -> (count, soma)
    by_kind = defaultdict(lambda: [0, Decimal("0")])
    by_cat = defaultdict(lambda: [0, Decimal("0")])
    by_flow = defaultdict(lambda: [0, Decimal("0")])
    for m in movements:
        by_kind[m["kind"]][0] += 1
        by_kind[m["kind"]][1] += m["amount"]
        by_cat[m["category_id"]][0] += 1
        by_cat[m["category_id"]][1] += m["amount"]
        by_flow[m["flow"]][0] += 1
        by_flow[m["flow"]][1] += m["amount"]

    print("\n=== Por tipo (kind) ===")
    for k, (c, s) in sorted(by_kind.items(), key=lambda x: -x[1][0]):
        print(f"  {c:4d}  {s:>15,.2f}  {k}")
    print("\n=== Por categoria sugerida ===")
    for k, (c, s) in sorted(by_cat.items(), key=lambda x: -x[1][0]):
        print(f"  {c:4d}  {s:>15,.2f}  {CAT_NAMES.get(k, k)}")
    print("\n=== Por flow (semântica da análise) ===")
    for k, (c, s) in sorted(by_flow.items(), key=lambda x: -x[1][0]):
        print(f"  {c:4d}  {s:>15,.2f}  {k}")

    # Fluxo externo (aporte/resgate reais)
    ext_aporte = sum(m["amount"] for m in movements if m["external"] and m["amount"] > 0)
    ext_resgate = sum(m["amount"] for m in movements if m["external"] and m["amount"] < 0)
    print(f"\nFluxo externo: aportes={ext_aporte:,.2f}  resgates={ext_resgate:,.2f}  líquido={ext_aporte+ext_resgate:,.2f}")

    if not commit:
        print("\n[DRY-RUN] Nada inserido. Rode com --commit para gravar.")
        db.close()
        return

    # Idempotência: remover carga anterior deste extrato (conta 9, datas >= 2025-01-01).
    # Os 36 lançamentos legados são de 2024 e ficam preservados.
    from datetime import date as _date
    cutoff = _date(2025, 1, 1)
    del_count = db.query(Transaction).filter(
        Transaction.account_id == ACCOUNT_ID,
        Transaction.date >= cutoff,
    ).delete(synchronize_session=False)
    db.commit()
    print(f"\nRemovidos (carga anterior >= {cutoff}): {del_count}")

    # Inserção
    nearest = load_rate_lookup(db)
    inserted = 0
    skipped = 0
    # hashes já existentes no banco (contas legadas) + os atribuídos nesta carga
    used = {h[0] for h in db.query(Transaction.transaction_hash).all() if h[0]}
    for m in movements:
        amt = m["amount"]
        # hash com sufixo p/ evitar colisão em movimentos idênticos no mesmo dia
        # (verifica tanto o banco quanto o que já foi atribuído nesta carga)
        suffix = 0
        thash = Transaction.generate_hash(ACCOUNT_ID, m["date"], m["description"], amt, CurrencyCode.BRL)
        while thash in used:
            suffix += 1
            thash = Transaction.generate_hash(ACCOUNT_ID, m["date"], m["description"], amt, CurrencyCode.BRL, suffix=suffix)
            if suffix > 50:
                break
        if suffix > 50:
            skipped += 1
            continue
        used.add(thash)
        usd_rate = nearest("USD", m["date"]) or Decimal("5.5")
        eur_rate = nearest("EUR", m["date"]) or Decimal("6.0")
        amount_usd = (amt / usd_rate).quantize(Decimal("0.01")) if usd_rate else Decimal("0.00")
        amount_eur = (amt / eur_rate).quantize(Decimal("0.01")) if eur_rate else Decimal("0.00")

        t = Transaction(
            account_id=ACCOUNT_ID,
            category_id=m["category_id"],
            date=m["date"],
            description=m["description"],
            original_description=m["description"],
            original_currency=CurrencyCode.BRL,
            original_amount=amt,
            amount_brl=amt,
            amount_usd=amount_usd,
            amount_eur=amount_eur,
            amount=amt,
            balance_after=m.get("saldo"),
            transaction_hash=thash,
            is_validated=True,
        )
        db.add(t)
        inserted += 1
    db.commit()
    print(f"\nInseridos: {inserted}  |  Pulados: {skipped}")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    main(args.commit)
