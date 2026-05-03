"""Popula a tabela asset_classes com classes padrão.

Executar uma vez após criar a tabela. Idempotente: pula classes já existentes.
"""
import sys
from pathlib import Path

# Adicionar backend ao path
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import os
os.chdir(str(BACKEND_DIR))

from app.database import SessionLocal, engine, Base, ensure_schema
from app.models.investment import AssetClass, AssetClassCode


# Definições padrão das classes de ativos
DEFAULT_CLASSES = [
    {
        "code": AssetClassCode.RENDA_FIXA,
        "name": "Renda Fixa",
        "color": "#3B82F6",
        "typical_liquidity_days": 30,
        "risk_level": 1,
        "description": "CDBs, LCIs, LCAs, Tesouro Direto e títulos privados em geral.",
    },
    {
        "code": AssetClassCode.POS_FIXADO,
        "name": "Pós-fixado",
        "color": "#1D4ED8",
        "typical_liquidity_days": 1,
        "risk_level": 1,
        "description": "Atrelados ao CDI/Selic. Ex: CDB-DI, fundos DI.",
    },
    {
        "code": AssetClassCode.PRE_FIXADO,
        "name": "Pré-fixado",
        "color": "#2563EB",
        "typical_liquidity_days": 30,
        "risk_level": 2,
        "description": "Taxa contratada na compra (ex: Tesouro Prefixado 2030).",
    },
    {
        "code": AssetClassCode.INFLACAO,
        "name": "Inflação",
        "color": "#0EA5E9",
        "typical_liquidity_days": 90,
        "risk_level": 2,
        "description": "Atrelados a IPCA/IGPM. Tesouro IPCA, debêntures IPCA+.",
    },
    {
        "code": AssetClassCode.MULTIMERCADO,
        "name": "Multimercado",
        "color": "#8B5CF6",
        "typical_liquidity_days": 30,
        "risk_level": 3,
        "description": "Fundos com mandatos diversos (juros, câmbio, ações).",
    },
    {
        "code": AssetClassCode.RENDA_VARIAVEL,
        "name": "Renda Variável",
        "color": "#EC4899",
        "typical_liquidity_days": 1,
        "risk_level": 4,
        "description": "Ações, ETFs, fundos de ações.",
    },
    {
        "code": AssetClassCode.FII,
        "name": "Fundos Imobiliários (FII)",
        "color": "#F59E0B",
        "typical_liquidity_days": 1,
        "risk_level": 3,
        "description": "Fundos de tijolo, papel, híbridos.",
    },
    {
        "code": AssetClassCode.CRIPTO,
        "name": "Cripto",
        "color": "#F97316",
        "typical_liquidity_days": 1,
        "risk_level": 5,
        "description": "Bitcoin, Ethereum, ETFs cripto.",
    },
    {
        "code": AssetClassCode.CAMBIAL,
        "name": "Cambial",
        "color": "#10B981",
        "typical_liquidity_days": 1,
        "risk_level": 3,
        "description": "Atrelados ao dólar/euro (fundos cambiais, ETFs).",
    },
    {
        "code": AssetClassCode.PREVIDENCIA,
        "name": "Previdência",
        "color": "#14B8A6",
        "typical_liquidity_days": 60,
        "risk_level": 2,
        "description": "PGBL, VGBL e similares.",
    },
    {
        "code": AssetClassCode.ALTERNATIVOS,
        "name": "Alternativos",
        "color": "#A855F7",
        "typical_liquidity_days": 365,
        "risk_level": 4,
        "description": "FIPs, Private Equity, fundos estruturados (baixa liquidez).",
    },
    {
        "code": AssetClassCode.CAIXA,
        "name": "Caixa",
        "color": "#64748B",
        "typical_liquidity_days": 0,
        "risk_level": 1,
        "description": "Saldo em conta corretora, conta corrente atrelada.",
    },
]


def main():
    # Garantir schema (Postgres) antes de criar tabelas
    ensure_schema()
    # Criar tabelas que não existirem
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing_codes = {ac.code for ac in db.query(AssetClass).all()}
        created = 0
        for entry in DEFAULT_CLASSES:
            if entry["code"] in existing_codes:
                continue
            db.add(AssetClass(**entry))
            created += 1
        db.commit()
        total = db.query(AssetClass).count()
        print(f"Asset classes inseridas: {created}")
        print(f"Total na tabela: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
