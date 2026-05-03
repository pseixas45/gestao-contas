"""Carga única de snapshots de março/2026 para XP e C6.

Os PDFs têm formato diferente dos parsers existentes:
- XP: Posição Consolidada (PDF) — antes era PosicaoDetalhadaHistorica (xlsx)
- C6: Posição por produto (PDF) — primeiro carregamento
- Itaú: NÃO carregar (extrato de conta corrente, não traz detalhe da carteira)

Idempotente: substitui snapshots existentes para a mesma (account_id, snapshot_date).
"""
import sys
import re
from pathlib import Path
from datetime import date
from decimal import Decimal

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import os
os.chdir(str(BACKEND_DIR))

import pdfplumber
from app.database import SessionLocal
from app.models import (
    BankAccount, AssetClass, AssetClassCode, Asset,
    InvestmentSnapshot, InvestmentPosition,
)

EXTRATOS_DIR = BACKEND_DIR.parent / "extratos"
SNAPSHOT_DATE = date(2026, 3, 31)


def parse_brl(text: str) -> Decimal:
    """Converte '1.234,56' em Decimal('1234.56')."""
    if not text:
        return Decimal("0")
    s = text.strip().replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _parse_xp_rf_row(row_text: str, subclass: str | None):
    """Parse uma linha de Renda Fixa do XP.

    Formato: "[RATE_PREFIX] NOME [DATA1] [DATA2] [DATA3] [counters] R$ VAL_APLIC R$ X R$ VAL_ORIG R$ VAL_LIQ [RATE_SUFFIX]"
    """
    text = row_text.strip()
    if not text:
        return None
    rs_values = re.findall(r"R\$\s*([\d.][\d.,]*)", text)
    if len(rs_values) < 4:
        return None
    val_aplicado = parse_brl(rs_values[0])
    val_orig = parse_brl(rs_values[-2])
    val_liq = parse_brl(rs_values[-1])
    if val_liq <= 0:
        return None

    # Datas
    all_dates = re.findall(r"\d{2}/\d{2}/\d{4}", text)
    maturity = all_dates[2] if len(all_dates) >= 3 else (all_dates[1] if len(all_dates) >= 2 else None)

    # Rate prefix antes do nome (CDI, IPC-A +, +X,XX%, TR, etc.) e sufixo após último R$
    rate_parts = []
    leading = re.split(r"\d{2}/\d{2}/\d{4}", text, 1)[0].strip()
    name = leading
    rate_prefix_m = re.match(r"^(IPC-?A\s*\+|CDI\s*\+|TR|\+\s*\d+[\.,]\d+%?|IGPM\s*\+|SELIC\s*\+|\d+[\.,]\d+%\s*CDI)\s+", leading)
    if rate_prefix_m:
        rate_parts.append(rate_prefix_m.group(1).strip())
        name = leading[rate_prefix_m.end():].strip()
    # Rate sufixo: depois do último R$ value
    last_rs_pos = text.rfind("R$")
    after_last_rs = text[last_rs_pos:]
    after_last_rs = re.sub(r"R\$\s*[\d.,]+", "", after_last_rs, count=1).strip()
    if after_last_rs:
        # ex: "JUN/2045 6,84%"
        m_rate = re.search(r"(\d+[\.,]\d+%)", after_last_rs)
        if m_rate:
            rate_parts.append(m_rate.group(1))
    rate = " ".join(rate_parts) if rate_parts else None

    if not name or "ativo" in name.lower() or len(name) < 3:
        return None

    return {
        "name": name,
        "classe": "Renda Fixa",
        "subclasse": subclass,
        "value": val_liq,
        "value_invested": val_aplicado if val_aplicado > 0 else val_orig,
        "maturity_date": maturity,
        "contracted_rate": rate,
    }


def _parse_xp_fund_row(row_text: str, subclass: str | None):
    """Parse uma linha de Fundo do XP.

    Formato: "NOME 31/03/2026 VALOR_COTA QTD_COTAS R$ EM_COTIZACAO R$ POSICAO R$ VALOR_LIQ"
    """
    text = row_text.strip()
    rs_values = re.findall(r"R\$\s*([\d.][\d.,]*)", text)
    if len(rs_values) < 3:
        return None
    val_pos = parse_brl(rs_values[-2])
    val_liq = parse_brl(rs_values[-1])
    if val_liq <= 0:
        return None
    # Nome = antes do primeiro 31/03/2026
    name_m = re.match(r"^(.+?)\s+\d{2}/\d{2}/\d{4}", text)
    if not name_m:
        return None
    name = name_m.group(1).strip()
    if not name or "ativo" in name.lower():
        return None
    return {
        "name": name,
        "classe": "Fundos de investimento",
        "subclasse": subclass,
        "value": val_liq,
        "value_invested": val_pos,
        "maturity_date": None,
        "contracted_rate": None,
    }


def parse_xp_pdf(path: Path):
    """Extrai patrimônio total e posições do PDF de Posição Consolidada XP."""
    positions = []
    total_patrimony = None
    saldo_disponivel = None
    current_subclass = None
    current_classe = None  # 'Renda Fixa' ou 'Fundos de investimento'

    def normalize(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            # Detectar mudança de classe na página
            m = re.search(r"(\d+[\.,]\d+)%\s+(Renda Fixa|Fundos de investimento|Saldo projetado)", text)
            if m:
                current_classe = m.group(2)

            # Patrimônio total
            m = re.search(r"PATRIM\S*NIO TOTAL\s+R\$\s*([\d.,]+)", text)
            if m:
                total_patrimony = parse_brl(m.group(1))
            m = re.search(r"SALDO DISPON\S*VEL\s+R\$\s*([\d.,]+)", text)
            if m:
                saldo_disponivel = parse_brl(m.group(1))

            tables = page.extract_tables() or []
            for tbl in tables:
                if not tbl:
                    continue
                # Header pode ser sub-class ("2.5% | Pós-Fixada") ou cabeçalho de colunas
                first_cell = normalize(tbl[0][0] or "")
                m_sub = re.match(r"^(\d+[\.,]\d+)%\s*\|\s*(.+)$", first_cell)
                if m_sub:
                    current_subclass = m_sub.group(2).strip()
                    rows = tbl[1:]
                else:
                    # Pode ser cabeçalho direto ("Fundos Listados")
                    if "fundos listados" in first_cell.lower():
                        current_subclass = "Fundos Listados"
                        rows = tbl[1:]
                    else:
                        rows = tbl

                # Pular linha de cabeçalho de colunas se houver
                if rows and rows[0] and rows[0][0]:
                    fc = normalize(rows[0][0])
                    if fc.lower().startswith("ativo") or "valor l" in fc.lower() or "data cota" in fc.lower() or "taxa de" in fc.lower():
                        rows = rows[1:]

                # Decidir classe e parser por sub-classe atual
                is_fund = False
                if current_classe == "Fundos de investimento" or "Fundos" in (current_subclass or ""):
                    is_fund = True

                for row in rows:
                    if not row or not row[0]:
                        continue
                    txt = normalize(row[0])
                    parser = _parse_xp_fund_row if is_fund else _parse_xp_rf_row
                    pos = parser(txt, current_subclass)
                    if pos:
                        positions.append(pos)

    return {
        "total_patrimony": total_patrimony,
        "available_balance": saldo_disponivel or Decimal("0"),
        "positions": positions,
    }


def parse_c6_pdf(path: Path):
    """Extrai posições do PDF C6 via extract_tables (tabela 'Posição por produto')."""
    positions = []
    total_patrimony = None

    def normalize(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()

    with pdfplumber.open(path) as pdf:
        # Patrimônio final fica na pg 4 normalmente
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = re.search(r"Patrim\S*nio final:\s*R\$\s*([\d.,]+)", text)
            if m and not total_patrimony:
                total_patrimony = parse_brl(m.group(1))

            # Tabelas: procurar a que tem cabeçalho com colunas mensais (ABR/25 ... MAR/26)
            tables = page.extract_tables() or []
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                header = [normalize(c or "").upper() for c in tbl[0]]
                if "MAR/26" not in " ".join(header):
                    continue
                # Coluna MAR/26 (a última de meses)
                try:
                    mar_idx = header.index("MAR/26")
                except ValueError:
                    mar_idx = -1
                for row in tbl[1:]:
                    if not row or not row[0]:
                        continue
                    name = normalize(row[0])
                    if not name or name.lower() in ("renda fixa", "total", "renda variavel", "renda variável"):
                        continue
                    cell = normalize(row[mar_idx] or "")
                    # Cell: "R$ 53.364,53\n(34,33%)"
                    m_val = re.search(r"R\$\s*([\d.][\d.,]*)", cell)
                    if not m_val:
                        continue
                    val = parse_brl(m_val.group(1))
                    if val <= 0:
                        continue
                    positions.append({
                        "name": name,
                        "classe": "Renda Fixa",
                        "subclasse": "Pós-Fixada" if "Pós" in name or "IPCA" in name else "Prefixada" if "Prefixado" in name or "Prefixada" in name else None,
                        "value": val,
                        "value_invested": None,
                        "maturity_date": None,
                        "contracted_rate": None,
                    })

    return {
        "total_patrimony": total_patrimony,
        "available_balance": Decimal("0"),
        "positions": positions,
    }


def map_to_asset_class(classe: str, subclasse: str | None) -> AssetClassCode:
    """Mapeia classe/subclasse extraídas do PDF para AssetClassCode."""
    if classe == "Saldo projetado":
        return AssetClassCode.CAIXA
    if classe == "Fundos de investimento":
        if subclasse and "Inflação" in subclasse:
            return AssetClassCode.INFLACAO
        if subclasse and ("Alternativos" in subclasse or "Privado" in subclasse):
            return AssetClassCode.ALTERNATIVOS
        if subclasse and "Pós-Fixado" in subclasse:
            return AssetClassCode.POS_FIXADO
        if subclasse and ("Listados" in subclasse or "FII" in subclasse):
            return AssetClassCode.FII
        return AssetClassCode.MULTIMERCADO
    # Renda Fixa
    if subclasse == "Prefixada":
        return AssetClassCode.PRE_FIXADO
    if subclasse and "Pós" in subclasse:
        return AssetClassCode.POS_FIXADO
    if subclasse == "Inflação":
        return AssetClassCode.INFLACAO
    return AssetClassCode.RENDA_FIXA


def get_or_create_asset(db, name: str, code: AssetClassCode) -> Asset:
    name_norm = name.strip().upper()
    asset = db.query(Asset).filter(Asset.name_normalized == name_norm).first()
    if asset:
        return asset
    cls = db.query(AssetClass).filter(AssetClass.code == code).first()
    if not cls:
        # fallback: pegar Renda Fixa
        cls = db.query(AssetClass).filter(AssetClass.code == AssetClassCode.RENDA_FIXA).first()
    asset = Asset(
        code=name_norm[:50],
        name=name.strip(),
        name_normalized=name_norm,
        asset_class_id=cls.id,
    )
    db.add(asset)
    db.flush()
    return asset


def upsert_snapshot(db, account_name: str, parsed: dict):
    acc = db.query(BankAccount).filter(BankAccount.name == account_name).first()
    if not acc:
        print(f"!! Conta '{account_name}' não encontrada — abortando")
        return None

    # Remover snapshot anterior para idempotência
    existing = db.query(InvestmentSnapshot).filter(
        InvestmentSnapshot.account_id == acc.id,
        InvestmentSnapshot.snapshot_date == SNAPSHOT_DATE,
    ).first()
    if existing:
        # Remover positions antes
        db.query(InvestmentPosition).filter(InvestmentPosition.snapshot_id == existing.id).delete()
        db.delete(existing)
        db.flush()
        print(f"  -> Snapshot {SNAPSHOT_DATE} de {account_name} removido para reprocesso")

    total = parsed["total_patrimony"] or sum((p["value"] for p in parsed["positions"]), Decimal("0"))
    invested = sum(((p["value_invested"] or Decimal("0")) for p in parsed["positions"]), Decimal("0"))

    snap = InvestmentSnapshot(
        account_id=acc.id,
        snapshot_date=SNAPSHOT_DATE,
        total_value=total,
        total_invested=invested if invested > 0 else None,
        available_balance=parsed["available_balance"] or Decimal("0"),
    )
    db.add(snap)
    db.flush()

    for p in parsed["positions"]:
        cls_code = map_to_asset_class(p["classe"], p.get("subclasse"))
        asset = get_or_create_asset(db, p["name"], cls_code)
        # parse maturity if present
        mat = None
        if p.get("maturity_date"):
            try:
                d, m, y = p["maturity_date"].split("/")
                mat = date(int(y), int(m), int(d))
            except Exception:
                pass
        pos = InvestmentPosition(
            snapshot_id=snap.id,
            asset_id=asset.id,
            value=p["value"] or Decimal("0"),
            value_invested=p.get("value_invested"),
            allocation_pct=(p["value"] / total * 100).quantize(Decimal("0.01")) if total > 0 else None,
            maturity_date=mat,
            contracted_rate=p.get("contracted_rate"),
        )
        db.add(pos)

    db.flush()
    print(f"  -> {account_name}: total=R${total} | positions={len(parsed['positions'])}")
    return snap


def main():
    db = SessionLocal()
    try:
        # XP
        print("=== XP ===")
        parsed_xp = parse_xp_pdf(EXTRATOS_DIR / "XP_historico_31_03_2026.pdf")
        print(f"  Total patrimônio: R${parsed_xp['total_patrimony']}")
        print(f"  Disponível: R${parsed_xp['available_balance']}")
        print(f"  Posições extraídas: {len(parsed_xp['positions'])}")
        for p in parsed_xp["positions"][:5]:
            print(f"    - {p['name']} ({p['classe']}/{p['subclasse']}): R${p['value']}")
        upsert_snapshot(db, "XP Carteira", parsed_xp)

        # C6
        print()
        print("=== C6 ===")
        parsed_c6 = parse_c6_pdf(EXTRATOS_DIR / "C6-31-03-2026.pdf")
        print(f"  Total patrimônio: R${parsed_c6['total_patrimony']}")
        print(f"  Posições extraídas: {len(parsed_c6['positions'])}")
        for p in parsed_c6["positions"]:
            print(f"    - {p['name']}: R${p['value']}")
        upsert_snapshot(db, "C6 Carteira", parsed_c6)

        db.commit()
        print()
        print("OK — snapshots de 2026-03-31 inseridos para XP e C6")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
