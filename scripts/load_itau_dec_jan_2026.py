"""Reprocessa snapshots Itaú de dez/2025 e jan/2026 com as 12 posições corretas.

Dados extraídos da página 4 ('Carteira detalhada') dos PDFs ITAU EXTRATO-CARTEIRA-2025-12.pdf
e ITAU EXTRATO-CARTEIRA-2026-01.pdf. As 4 linhas CDB-DI são consolidadas em
'CDB, Renda Fixa e Invest. Estruturados' para manter consistência com o padrão
validado pelo usuário em fev/2026 e mar/2026.

Total bate com 'Total da Carteira' do próprio PDF.
"""
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import os
os.chdir(str(BACKEND_DIR))

from app.database import SessionLocal
from app.models import (
    BankAccount, AssetClass, AssetClassCode, Asset,
    InvestmentSnapshot, InvestmentPosition,
)


# (nome, classe, valor_dez_2025, valor_jan_2026)
POSITIONS = [
    ("ITAU PRIVILEGE RF REF DI FIFCIC RL",                      AssetClassCode.POS_FIXADO,    Decimal("277970.89"), Decimal("310608.18")),
    ("ITAU GLOBAL DINAMICO RF LP FIFCIC RL",                    AssetClassCode.RENDA_FIXA,    Decimal("26006.57"),  Decimal("26389.36")),
    ("SELECAO MORGAN STANLEY US ADV EQ MULT IE FIFCIC RL",      AssetClassCode.RENDA_VARIAVEL, Decimal("47555.35"),  Decimal("42751.40")),
    ("ITAU INDEX BITCOIN USD FIFCIC MULT RL",                   AssetClassCode.CRIPTO,        Decimal("24134.02"),  Decimal("22007.03")),
    ("ITAU CRED BANC RF CRED PRIV FIFCIC RESP LIMITADA",        AssetClassCode.RENDA_FIXA,    Decimal("40888.70"),  Decimal("41272.28")),
    ("JANEIRO INFRA FIIF EM INFRA CIC RF CRED PRIV LP RL",      AssetClassCode.INFLACAO,      Decimal("10674.49"),  Decimal("10971.11")),
    # 4 CDB-DI consolidados:
    # Dez: 1141.09 + 7209.23 + 8276.93 + 6595.04 = 23222.29
    # Jan: 1155.96 + 7302.33 + 8355.83 + 6657.84 = 23471.96
    ("CDB, Renda Fixa e Invest. Estruturados",                  AssetClassCode.RENDA_FIXA,    Decimal("23222.29"),  Decimal("23471.96")),
    ("Itau Person Ibiuna Mm Vgbl",                              AssetClassCode.PREVIDENCIA,   Decimal("2989.73"),   Decimal("3080.88")),
    ("Itau Flexprev Global Dinamico Rf Lp Vgbl",                AssetClassCode.PREVIDENCIA,   Decimal("98546.57"),  Decimal("100346.13")),
    ("Itau Person Kinea Acoes Vgbl",                            AssetClassCode.PREVIDENCIA,   Decimal("44330.55"),  Decimal("49884.52")),
    ("Itau Global Dinamico Baixa Vol Mm Vgbl",                  AssetClassCode.PREVIDENCIA,   Decimal("99734.62"),  Decimal("101444.27")),
    ("Itau Person Sc Vision Rf Pgbl",                           AssetClassCode.PREVIDENCIA,   Decimal("19162.82"),  Decimal("19440.06")),
]


def get_or_create_asset(db, name: str, code: AssetClassCode) -> Asset:
    name_norm = name.strip().upper()
    asset = db.query(Asset).filter(Asset.name_normalized == name_norm).first()
    if asset:
        cls = db.query(AssetClass).filter(AssetClass.code == code).first()
        if cls and asset.asset_class_id != cls.id:
            asset.asset_class_id = cls.id
        return asset
    cls = db.query(AssetClass).filter(AssetClass.code == code).first()
    if not cls:
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


def upsert_snapshot(db, account_id: int, snapshot_date: date, value_idx: int):
    existing = db.query(InvestmentSnapshot).filter(
        InvestmentSnapshot.account_id == account_id,
        InvestmentSnapshot.snapshot_date == snapshot_date,
    ).first()
    if existing:
        db.query(InvestmentPosition).filter(InvestmentPosition.snapshot_id == existing.id).delete()
        db.delete(existing)
        db.flush()
        print(f"  -> Snapshot {snapshot_date} removido para reprocesso")

    total = sum((p[value_idx] for p in POSITIONS), Decimal("0"))
    snap = InvestmentSnapshot(
        account_id=account_id,
        snapshot_date=snapshot_date,
        total_value=total,
        total_invested=None,
        available_balance=Decimal("0"),
    )
    db.add(snap)
    db.flush()

    for name, cls_code, v_dec, v_jan in POSITIONS:
        value = v_dec if value_idx == 2 else v_jan
        asset = get_or_create_asset(db, name, cls_code)
        pos = InvestmentPosition(
            snapshot_id=snap.id,
            asset_id=asset.id,
            value=value,
            allocation_pct=(value / total * 100).quantize(Decimal("0.01")) if total > 0 else None,
        )
        db.add(pos)

    db.flush()
    print(f"  -> Snapshot {snapshot_date}: total=R${total:,.2f} | positions={len(POSITIONS)}")


def main():
    db = SessionLocal()
    try:
        acc = db.query(BankAccount).filter(BankAccount.name == "Itau Carteira").first()
        if not acc:
            print("!! Conta 'Itau Carteira' não encontrada"); return

        print("=== Itaú 31/12/2025 ===")
        upsert_snapshot(db, acc.id, date(2025, 12, 31), value_idx=2)
        print()
        print("=== Itaú 31/01/2026 ===")
        upsert_snapshot(db, acc.id, date(2026, 1, 31), value_idx=3)

        db.commit()
        print()
        print("OK")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
