"""Carrega/atualiza posições Itaú validadas pelo usuário para 28/02/2026 e 31/03/2026.

Dados informados pelo usuário (saldos brutos validados):
    posição                                                    27/02         31/03
    ITAU PRIVILEGE RF REF DI FIFCIC RL                       314.070,26   317.768,01
    ITAU GLOBAL DINAMICO RF LP FIFCIC RL                      26.777,31    26.683,27
    SELECAO MORGAN STANLEY US ADV EQ MULT IE FIFCIC RL        39.994,74    38.773,63
    ITAU INDEX BITCOIN USD FIFCIC MULT RL                     16.807,25    17.505,56
    ITAU CRED BANC RF CRED PRIV FIFCIC RESP LIMITADA          42.043,09    42.550,35
    JANEIRO INFRA FIIF EM INFRA CIC RF CRED PRIV LP RL        11.051,65    10.864,20
    CDB, Renda Fixa e Invest. Estruturados                    24.288,09    24.582,70
    Itau Person Ibiuna Mm Vgbl                                 3.127,08     2.924,46
    Itau Flexprev Global Dinamico Rf Lp Vgbl                 101.385,49   101.029,18
    Itau Person Kinea Acoes Vgbl                              51.462,33    50.216,80
    Itau Global Dinamico Baixa Vol Mm Vgbl                   102.356,06   102.499,84
    Itau Person Sc Vision Rf Pgbl                             19.629,78    19.620,55

Idempotente: substitui snapshots existentes da mesma data.
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


# (nome, classe, valor_27_02, valor_31_03)
POSITIONS = [
    ("ITAU PRIVILEGE RF REF DI FIFCIC RL",                      AssetClassCode.POS_FIXADO,    Decimal("314070.26"), Decimal("317768.01")),
    ("ITAU GLOBAL DINAMICO RF LP FIFCIC RL",                    AssetClassCode.RENDA_FIXA,    Decimal("26777.31"),  Decimal("26683.27")),
    ("SELECAO MORGAN STANLEY US ADV EQ MULT IE FIFCIC RL",      AssetClassCode.RENDA_VARIAVEL, Decimal("39994.74"),  Decimal("38773.63")),
    ("ITAU INDEX BITCOIN USD FIFCIC MULT RL",                   AssetClassCode.CRIPTO,        Decimal("16807.25"),  Decimal("17505.56")),
    ("ITAU CRED BANC RF CRED PRIV FIFCIC RESP LIMITADA",        AssetClassCode.RENDA_FIXA,    Decimal("42043.09"),  Decimal("42550.35")),
    ("JANEIRO INFRA FIIF EM INFRA CIC RF CRED PRIV LP RL",      AssetClassCode.INFLACAO,      Decimal("11051.65"),  Decimal("10864.20")),
    ("CDB, Renda Fixa e Invest. Estruturados",                  AssetClassCode.RENDA_FIXA,    Decimal("24288.09"),  Decimal("24582.70")),
    ("Itau Person Ibiuna Mm Vgbl",                              AssetClassCode.PREVIDENCIA,   Decimal("3127.08"),   Decimal("2924.46")),
    ("Itau Flexprev Global Dinamico Rf Lp Vgbl",                AssetClassCode.PREVIDENCIA,   Decimal("101385.49"), Decimal("101029.18")),
    ("Itau Person Kinea Acoes Vgbl",                            AssetClassCode.PREVIDENCIA,   Decimal("51462.33"),  Decimal("50216.80")),
    ("Itau Global Dinamico Baixa Vol Mm Vgbl",                  AssetClassCode.PREVIDENCIA,   Decimal("102356.06"), Decimal("102499.84")),
    ("Itau Person Sc Vision Rf Pgbl",                           AssetClassCode.PREVIDENCIA,   Decimal("19629.78"),  Decimal("19620.55")),
]


def get_or_create_asset(db, name: str, code: AssetClassCode) -> Asset:
    name_norm = name.strip().upper()
    asset = db.query(Asset).filter(Asset.name_normalized == name_norm).first()
    if asset:
        # Atualizar classe se diferente (caso o usuário tenha reclassificado)
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
    """value_idx: 2 = coluna 27/02, 3 = coluna 31/03"""
    # Remover snapshot anterior
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

    for name, cls_code, v_feb, v_mar in POSITIONS:
        value = v_feb if value_idx == 2 else v_mar
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

        print("=== Itaú 28/02/2026 (saldo bruto 27/02) ===")
        upsert_snapshot(db, acc.id, date(2026, 2, 28), value_idx=2)
        print()
        print("=== Itaú 31/03/2026 (saldo bruto 31/03) ===")
        upsert_snapshot(db, acc.id, date(2026, 3, 31), value_idx=3)

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
