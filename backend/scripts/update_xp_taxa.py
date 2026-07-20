"""Atualiza a TAXA contratada dos ativos (rate_index/rate_spread/rate_type) a
partir da coluna RENDIMENTO do arquivo 'XP Carteira Jan25 a Jun26.xlsx' (aba 26_Jun).

Uso:
  python scripts/update_xp_taxa.py            # dry-run (mostra o que faria)
  python scripts/update_xp_taxa.py --commit   # aplica
"""
import sys, os, re, argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8")
from decimal import Decimal, InvalidOperation

import openpyxl
from sqlalchemy import text
from app.database import SessionLocal
from app.models.investment import RateIndex, RateType

FILE = r"C:\Users\paulo\gestao-contas\extratos\XP Carteira Jan25 a Jun26.xlsx"
SHEET = "26_Jun"


def _num(s):
    try:
        return Decimal(str(s).replace(".", "").replace(",", ".")) if ("," in str(s)) else Decimal(str(s).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def parse_taxa(raw):
    """Retorna (RateIndex, spread Decimal, RateType) ou (None,None,None)."""
    if raw is None:
        return (None, None, None)
    # Numérico puro (ex.: 0.1396) => pré-fixado
    if isinstance(raw, (int, float)):
        v = Decimal(str(raw))
        pct = v * 100 if v < 1 else v
        return (RateIndex.PRE, pct.quantize(Decimal("0.0001")), RateType.SPREAD)
    s = str(raw).strip().upper().replace("\xa0", " ")
    s = s.replace("IPC-A", "IPCA").replace("%", "")
    s = re.sub(r"A\.?\s*A\.?$", "", s).strip()
    if not s:
        return (None, None, None)
    # IPCA + X
    m = re.search(r"IPCA\s*\+?\s*([\d.,]+)", s)
    if m:
        return (RateIndex.IPCA, _num(m.group(1)), RateType.SPREAD)
    # IGPM + X
    m = re.search(r"IGP-?M\s*\+\s*([\d.,]+)", s)
    if m:
        return (RateIndex.IGPM, _num(m.group(1)), RateType.SPREAD)
    # SELIC + X
    m = re.search(r"SELIC\s*\+\s*([\d.,]+)", s)
    if m:
        return (RateIndex.SELIC, _num(m.group(1)), RateType.SPREAD)
    # X% CDI (percentual do CDI)
    m = re.search(r"([\d.,]+)\s*(?:CDI|DI)\b", s)
    if m:
        return (RateIndex.CDI, _num(m.group(1)), RateType.PERCENTAGE)
    # CDI + X (spread)
    m = re.search(r"(?:CDI|DI)\s*\+\s*([\d.,]+)", s)
    if m:
        return (RateIndex.CDI, _num(m.group(1)), RateType.SPREAD)
    # CDI puro => 100% CDI
    if s in ("CDI", "DI"):
        return (RateIndex.CDI, Decimal("100"), RateType.PERCENTAGE)
    # TR puro
    if s == "TR":
        return (RateIndex.TR, Decimal("0"), RateType.SPREAD)
    # Numérico puro em string (ex.: "13,96") => pré-fixado
    m = re.match(r"^([\d.,]+)$", s)
    if m:
        return (RateIndex.PRE, _num(m.group(1)), RateType.SPREAD)
    return (None, None, None)


def norm_exact(x):
    return re.sub(r"\s+", " ", str(x or "").strip().upper())


def norm_loose(x):
    return re.sub(r"[^A-Z0-9]", "", str(x or "").upper())


def main(commit):
    db = SessionLocal()
    wb = openpyxl.load_workbook(FILE, read_only=True, data_only=True)
    ws = wb[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    existing = db.execute(text(
        "SELECT id, name, name_normalized, rate_index::text, rate_spread, rate_type::text FROM gestao_contas.assets"
    )).fetchall()
    by_exact, by_loose = {}, {}
    for a in existing:
        by_exact.setdefault(norm_exact(a[1]), a)
        by_loose.setdefault(norm_loose(a[1]), a)

    updates = {}   # asset_id -> (name, idx, spread, rtype, raw)
    unmatched, unparsed = [], []
    for r in rows[1:]:
        if not r or not r[1]:
            continue
        raw = r[2]
        if raw is None or str(raw).strip() == "":
            continue
        idx, spread, rtype = parse_taxa(raw)
        if idx is None:
            unparsed.append((str(r[1]), raw)); continue
        a = by_exact.get(norm_exact(r[1])) or by_loose.get(norm_loose(r[1]))
        if not a:
            unmatched.append((str(r[1]), raw)); continue
        # primeira ocorrência vence (ativos com 2 lotes têm taxas diferentes)
        updates.setdefault(a[0], (a[1], idx, spread, rtype, raw))

    print(f"=== Taxas a atualizar: {len(updates)} ativos ===")
    for aid, (name, idx, spread, rtype, raw) in sorted(updates.items(), key=lambda x: x[1][0]):
        print(f"  id={aid:3d} {name[:40]:42} {raw!s:16} -> {idx.value} {spread} {rtype.value}")
    if unparsed:
        print(f"\n!!! NÃO PARSEADAS ({len(unparsed)}):")
        for n, raw in unparsed: print(f"    {n[:40]:42} {raw!r}")
    if unmatched:
        print(f"\n!!! ATIVO NÃO ENCONTRADO ({len(unmatched)}):")
        for n, raw in unmatched: print(f"    {n[:40]:42} {raw!r}")

    if not commit:
        print("\n[DRY-RUN] Nada gravado. Rode com --commit.")
        db.close(); return

    for aid, (name, idx, spread, rtype, raw) in updates.items():
        db.execute(text(
            "UPDATE gestao_contas.assets SET rate_index=:i, rate_spread=:s, rate_type=:t, updated_at=now() WHERE id=:id"
        ), {"i": idx.name, "s": spread, "t": rtype.name, "id": aid})
    db.commit()
    print(f"\nAtualizados: {len(updates)} ativos.")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    main(ap.parse_args().commit)
