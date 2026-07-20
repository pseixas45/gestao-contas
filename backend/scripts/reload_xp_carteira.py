"""Recarrega a carteira XP (account_id=11) a partir do arquivo consolidado
'XP Carteira Jan25 a Jun26.xlsx', aba '26_Jun'.

Formato do arquivo (matriz ativo x mes):
  Classe | Ativo | Rendimento | Data Investimento | Valor Investido | Conta | Jan/25 ... Jun/26 | Var | Apl/Res | Data

Cria 18 snapshots mensais (Jan/25..Jun/26) para a conta 11, com posicoes por
ativo (value = valor do mes), salvando value_invested (Valor Investido) e
application_date (Data Investimento).

Uso:
  python scripts/reload_xp_carteira.py            # dry-run (mostra plano)
  python scripts/reload_xp_carteira.py --commit   # backup + delete + insert
"""
import sys, os, json, argparse, calendar, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8")
from datetime import date, datetime
from decimal import Decimal
from collections import defaultdict

import openpyxl
from sqlalchemy import text
from app.database import SessionLocal
from app.models import Asset, InvestmentSnapshot, InvestmentPosition

ACCOUNT_ID = 11
FILE = r"C:\Users\paulo\gestao-contas\extratos\XP Carteira Jan25 a Jun26.xlsx"
SHEET = "26_Jun"

PT_MONTH = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
            "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

# Classe do arquivo (AssetClass.name) -> asset_class_id
CLASS_NAME_TO_ID = {
    "Renda Fixa": 1, "Pós-fixado": 2, "Pré-fixado": 3, "Inflação": 4,
    "Multimercado": 5, "Renda Variável": 6, "Fundos Imobiliários (FII)": 7,
    "Cripto": 8, "Cambial": 9, "Previdência": 10, "Alternativos": 11, "Caixa": 12,
}


def norm_exact(s):
    """Igual ao Asset.name_normalized: upper + colapsa espacos."""
    return re.sub(r"\s+", " ", str(s or "").strip().upper())


def norm_loose(s):
    """Chave alfanumerica (ignora hifen/pontuacao/espacos)."""
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def parse_month_label(lbl):
    """'Jan/25' -> (2025, 1)."""
    m = re.match(r"([A-Za-zç]+)/(\d{2})", str(lbl).strip())
    if not m:
        return None
    mon = PT_MONTH.get(m.group(1)[:3].lower())
    if not mon:
        return None
    return (2000 + int(m.group(2)), mon)


def to_dec(v):
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    return None


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def main(commit):
    db = SessionLocal()
    wb = openpyxl.load_workbook(FILE, read_only=True, data_only=True)
    ws = wb[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    hdr = rows[0]
    # colunas de mes: indices 6.. onde o label parseia como mes
    month_cols = []  # (col_idx, (year, month), date_end)
    for i in range(6, len(hdr)):
        ym = parse_month_label(hdr[i])
        if ym:
            y, m = ym
            month_cols.append((i, ym, date(y, m, calendar.monthrange(y, m)[1])))
    print(f"Meses detectados: {len(month_cols)}  ({month_cols[0][1]} .. {month_cols[-1][1]})")

    # Ativos existentes (para matching) — todos
    existing = db.execute(text(
        "SELECT id, name, name_normalized, asset_class_id, application_date FROM gestao_contas.assets"
    )).fetchall()
    by_exact = {}
    by_loose = {}
    for a in existing:
        by_exact.setdefault(norm_exact(a[1]), a)
        by_loose.setdefault(norm_loose(a[1]), a)

    # Parse linhas de ativo
    data_rows = [r for r in rows[1:] if r and r[1]]
    plan_assets = []   # dicts: {classe, ativo, rate, data_inv, valor_inv, month->value, asset_id, match}
    created = 0
    matched = 0
    unmatched_info = []

    for r in data_rows:
        classe = str(r[0]).strip() if r[0] else None
        ativo = str(r[1]).strip()
        rate = str(r[2]).strip() if r[2] else None
        data_inv = to_date(r[3])
        valor_inv = to_dec(r[4])
        month_vals = {}
        for ci, ym, dend in month_cols:
            v = to_dec(r[ci])
            if v is not None:
                month_vals[ym] = v
        if not month_vals:
            continue  # ativo sem nenhum valor no periodo -> ignora

        ne, nl = norm_exact(ativo), norm_loose(ativo)
        match = by_exact.get(ne) or by_loose.get(nl)
        asset_id = match[0] if match else None
        method = "exato" if by_exact.get(ne) else ("loose" if match else "NOVO")
        if match:
            matched += 1
        else:
            created += 1
            unmatched_info.append((classe, ativo))

        plan_assets.append({
            "classe": classe, "ativo": ativo, "rate": rate,
            "data_inv": data_inv, "valor_inv": valor_inv,
            "month_vals": month_vals, "asset_id": asset_id,
            "asset_class_id": CLASS_NAME_TO_ID.get(classe), "method": method,
        })

    # Totais por mes
    print("\n=== Totais por mes (arquivo) ===")
    for ci, ym, dend in month_cols:
        s = sum((pa["month_vals"].get(ym, Decimal("0")) for pa in plan_assets), Decimal("0"))
        n = sum(1 for pa in plan_assets if ym in pa["month_vals"])
        print(f"  {ym[0]}-{ym[1]:02d}  {s:>15,.2f}  ({n} ativos)")

    print(f"\n=== Matching de ativos: {matched} encontrados, {created} novos ===")
    for pa in plan_assets:
        flag = "" if pa["method"] != "NOVO" else "  <-- CRIAR NOVO"
        inv = f" inv={pa['valor_inv']}" if pa["valor_inv"] else ""
        dt = f" data={pa['data_inv']}" if pa["data_inv"] else ""
        print(f"  [{pa['method']:5}] id={pa['asset_id']}  [{pa['classe']}] {pa['ativo']}{inv}{dt}{flag}")

    # checar classes nao mapeadas
    badcls = {pa["classe"] for pa in plan_assets if pa["asset_class_id"] is None}
    if badcls:
        print(f"\n!!! CLASSES NAO MAPEADAS: {badcls}")

    if not commit:
        print("\n[DRY-RUN] Nada alterado. Rode com --commit para aplicar.")
        db.close()
        return

    # ---------------- COMMIT ----------------
    # 1) Backup da conta 11 (snapshots + posicoes) em JSON
    snaps = db.execute(text(
        "SELECT id, snapshot_date, total_value, total_invested FROM gestao_contas.investment_snapshots WHERE account_id=:a"
    ), {"a": ACCOUNT_ID}).fetchall()
    snap_ids = [s[0] for s in snaps]
    poss = []
    if snap_ids:
        poss = db.execute(text(
            "SELECT snapshot_id, asset_id, value, value_invested FROM gestao_contas.investment_positions WHERE snapshot_id = ANY(:ids)"
        ), {"ids": snap_ids}).fetchall()
    backup = {
        "account_id": ACCOUNT_ID,
        "snapshots": [{"id": s[0], "date": str(s[1]), "total_value": str(s[2]), "total_invested": str(s[3])} for s in snaps],
        "positions": [{"snapshot_id": p[0], "asset_id": p[1], "value": str(p[2]), "value_invested": str(p[3])} for p in poss],
    }
    bkp_path = os.path.join(os.path.dirname(__file__), "backup_xp_carteira_pre_reload.json")
    with open(bkp_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=1)
    print(f"\nBackup salvo: {bkp_path} ({len(snaps)} snapshots, {len(poss)} posicoes)")

    # 2) Criar ativos novos + atualizar application_date onde veio no arquivo
    name_to_newasset = {}
    for pa in plan_assets:
        if pa["asset_id"] is None:
            a = Asset(
                code=None, name=pa["ativo"], name_normalized=norm_exact(pa["ativo"]),
                asset_class_id=pa["asset_class_id"], application_date=pa["data_inv"], is_active=True,
            )
            db.add(a)
            db.flush()
            pa["asset_id"] = a.id
            name_to_newasset[pa["ativo"]] = a.id
        elif pa["data_inv"]:
            db.execute(text(
                "UPDATE gestao_contas.assets SET application_date=:d WHERE id=:i AND application_date IS NULL"
            ), {"d": pa["data_inv"], "i": pa["asset_id"]})
    db.commit()

    # 3) Deletar snapshots+posicoes atuais da conta 11
    if snap_ids:
        db.execute(text("DELETE FROM gestao_contas.investment_positions WHERE snapshot_id = ANY(:ids)"), {"ids": snap_ids})
        db.execute(text("DELETE FROM gestao_contas.investment_snapshots WHERE account_id=:a"), {"a": ACCOUNT_ID})
        db.commit()
    print(f"Removidos: {len(snap_ids)} snapshots + {len(poss)} posicoes antigas.")

    # 4) Inserir novos snapshots + posicoes
    n_snap = n_pos = 0
    for ci, ym, dend in month_cols:
        month_assets = [pa for pa in plan_assets if ym in pa["month_vals"]]
        if not month_assets:
            continue
        total = sum((pa["month_vals"][ym] for pa in month_assets), Decimal("0"))
        snap = InvestmentSnapshot(
            account_id=ACCOUNT_ID, snapshot_date=dend,
            total_value=total, total_invested=None,
        )
        db.add(snap)
        db.flush()
        n_snap += 1
        for pa in month_assets:
            db.add(InvestmentPosition(
                snapshot_id=snap.id, asset_id=pa["asset_id"],
                value=pa["month_vals"][ym],
                value_invested=pa["valor_inv"],
                contracted_rate=pa["rate"],
            ))
            n_pos += 1
    db.commit()
    print(f"Inseridos: {n_snap} snapshots + {n_pos} posicoes.")

    # 5) Conferencia
    print("\n=== Conferencia (conta 11 apos reload) ===")
    for r in db.execute(text(
        "SELECT snapshot_date, total_value, (SELECT count(*) FROM gestao_contas.investment_positions p WHERE p.snapshot_id=s.id) FROM gestao_contas.investment_snapshots s WHERE account_id=:a ORDER BY snapshot_date"
    ), {"a": ACCOUNT_ID}).fetchall():
        print(f"  {r[0]}  {r[1]:>15,.2f}  pos={r[2]}")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    main(ap.parse_args().commit)
