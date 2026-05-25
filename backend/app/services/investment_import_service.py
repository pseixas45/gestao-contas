"""Serviço de importação de extratos de investimentos.

Usa parsers modulares de backend/app/services/parsers/.
Suporta:
- XP: PDF Posição Consolidada (historico_DD_MM_YYYY.pdf)
- Itaú: PDF Extrato Mensal (Extrato Mensal_MesAAAA.pdf)
- C6: PDF Relatório Mensal (c6 investimentos DDMM.pdf)
"""
from datetime import date
from decimal import Decimal
from typing import Dict, Optional, Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    BankAccount, AssetClass, AssetClassCode, Asset,
    InvestmentSnapshot, InvestmentPosition, ImportBatch,
    RateIndex, RateType,
)
from app.models.import_batch import ImportStatus, FileType
from app.services.parsers import XPPdfParser, ItauExtratoMensalParser, C6PdfParser


class InvestmentImportService:
    def __init__(self, db: Session):
        self.db = db

    def import_file(self, file_path: str, account_id: int, provider: Optional[str] = None) -> Dict[str, Any]:
        """Importa arquivo de investimentos. Auto-detecta provider se não informado."""
        if provider is None:
            provider = self._detect_provider(file_path)

        parser = self._get_parser(provider, file_path)

        # C6 pode ter múltiplos meses num único PDF
        if provider == "c6" and hasattr(parser, "parse_all_months"):
            snapshots = parser.parse_all_months()
            if not snapshots:
                raise ValueError(f"Nenhum snapshot extraído de {Path(file_path).name}")
            result = None
            for snap_data in snapshots:
                result = self._import_single_snapshot(snap_data, file_path, account_id)
            return result  # retorna info do último snapshot

        return self._import_with_parser(parser, file_path, account_id)

    def import_xp_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        return self.import_file(file_path, account_id, "xp")

    def import_itau_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        return self.import_file(file_path, account_id, "itau")

    def import_c6_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        return self.import_file(file_path, account_id, "c6")

    def _detect_provider(self, file_path: str) -> str:
        name = Path(file_path).name.lower()
        if "xp" in name or "historico" in name or "posicao" in name:
            return "xp"
        if "itau" in name or "ita" in name or "extrato mensal" in name:
            return "itau"
        if "c6" in name:
            return "c6"
        raise ValueError(f"Não foi possível detectar provider do arquivo: {Path(file_path).name}")

    def _get_parser(self, provider: str, file_path: str):
        provider = provider.lower()
        if provider == "xp":
            return XPPdfParser(file_path)
        elif provider == "itau":
            return ItauExtratoMensalParser(file_path)
        elif provider == "c6":
            return C6PdfParser(file_path)
        else:
            raise ValueError(f"Provider desconhecido: {provider}")

    def _import_single_snapshot(self, data, file_path: str, account_id: int) -> Dict[str, Any]:
        """Importa um único ParsedSnapshot para o banco."""
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Conta {account_id} não encontrada")
        return self._save_parsed_data(data, file_path, account_id)

    def _import_with_parser(self, parser, file_path: str, account_id: int) -> Dict[str, Any]:
        """Lógica comum para qualquer parser."""
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Conta {account_id} não encontrada")

        # Parse
        data = parser.parse()
        return self._save_parsed_data(data, file_path, account_id)

    def _save_parsed_data(self, data, file_path: str, account_id: int) -> Dict[str, Any]:
        """Salva um ParsedSnapshot no banco (cria batch, snapshot, posições)."""

        # Cache de AssetClass
        class_cache: Dict[AssetClassCode, AssetClass] = {}
        for ac in self.db.query(AssetClass).all():
            class_cache[ac.code] = ac

        # ImportBatch
        ext = Path(file_path).suffix.lower()
        file_type = {".pdf": FileType.PDF, ".csv": FileType.CSV, ".xls": FileType.XLSX, ".xlsx": FileType.XLSX}.get(ext, FileType.PDF)
        batch = ImportBatch(
            account_id=account_id,
            filename=Path(file_path).name,
            file_type=file_type,
            total_records=len(data["positions"]),
            imported_records=0,
            duplicate_records=0,
            error_records=0,
            status=ImportStatus.PROCESSING,
        )
        self.db.add(batch)
        self.db.flush()

        # Snapshot (idempotente: mesmo account+date substitui)
        existing = (
            self.db.query(InvestmentSnapshot)
            .filter(
                InvestmentSnapshot.account_id == account_id,
                InvestmentSnapshot.snapshot_date == data["snapshot_date"],
            )
            .first()
        )
        if existing:
            for p in list(existing.positions):
                self.db.delete(p)
            existing.total_value = data.get("total_value") or Decimal("0")
            existing.total_invested = data.get("total_invested")
            existing.available_balance = data.get("available_balance") or Decimal("0")
            existing.total_gross = data.get("total_gross")
            existing.total_net = data.get("total_net")
            existing.yield_month_value = data.get("yield_month_value")
            existing.import_batch_id = batch.id
            snapshot = existing
            replaced = True
        else:
            snapshot = InvestmentSnapshot(
                account_id=account_id,
                snapshot_date=data["snapshot_date"],
                total_value=data.get("total_value") or Decimal("0"),
                total_invested=data.get("total_invested"),
                available_balance=data.get("available_balance") or Decimal("0"),
                total_gross=data.get("total_gross"),
                total_net=data.get("total_net"),
                yield_month_value=data.get("yield_month_value"),
                import_batch_id=batch.id,
            )
            self.db.add(snapshot)
            replaced = False

        self.db.flush()

        # Criar posições e assets
        imported = 0
        for pos_data in data["positions"]:
            # Buscar/criar Asset
            asset = (
                self.db.query(Asset)
                .filter(Asset.name_normalized == pos_data["name_normalized"])
                .first()
            )
            if not asset:
                cls = class_cache.get(pos_data.get("asset_class"))
                if not cls:
                    continue
                asset = Asset(
                    name=pos_data["name"],
                    name_normalized=pos_data["name_normalized"],
                    asset_class_id=cls.id,
                )
                self.db.add(asset)
                self.db.flush()
            else:
                # Atualizar classe se mudou (ex: corrigido de pos_fixado para inflacao)
                new_cls = class_cache.get(pos_data.get("asset_class"))
                if new_cls and asset.asset_class_id != new_cls.id:
                    asset.asset_class_id = new_cls.id

            # Atualizar dados de taxa no Asset se vieram do parser
            self._update_asset_rate(asset, pos_data)

            # Criar posição com todos os campos
            position = InvestmentPosition(
                snapshot_id=snapshot.id,
                asset_id=asset.id,
                value=pos_data["value"],
                value_invested=pos_data.get("value_invested"),
                value_gross=pos_data.get("value_gross"),
                value_net=pos_data.get("value_net"),
                quantity=pos_data.get("quantity"),
                allocation_pct=pos_data.get("allocation_pct"),
                yield_net_pct=pos_data.get("yield_net_pct"),
                yield_gross_pct=pos_data.get("yield_gross_pct"),
                yield_value=pos_data.get("yield_value"),
                yield_month_value=pos_data.get("yield_month_value"),
                maturity_date=pos_data.get("maturity_date"),
                contracted_rate=pos_data.get("contracted_rate"),
            )
            self.db.add(position)
            imported += 1

        # Atualizar batch
        batch.imported_records = imported
        batch.status = ImportStatus.COMPLETED
        batch.date_start = data["snapshot_date"]
        batch.date_end = data["snapshot_date"]

        self.db.commit()
        self.db.refresh(snapshot)

        return {
            "snapshot_id": snapshot.id,
            "snapshot_date": snapshot.snapshot_date.isoformat(),
            "total_value": float(snapshot.total_value),
            "total_invested": float(snapshot.total_invested) if snapshot.total_invested else None,
            "total_gross": float(snapshot.total_gross) if snapshot.total_gross else None,
            "total_net": float(snapshot.total_net) if snapshot.total_net else None,
            "positions_count": imported,
            "replaced": replaced,
            "batch_id": batch.id,
        }

    def _update_asset_rate(self, asset: Asset, pos_data: dict):
        """Atualiza campos de taxa no Asset se novos dados disponíveis."""
        updated = False

        if pos_data.get("rate_index") and not asset.rate_index:
            asset.rate_index = pos_data["rate_index"]
            updated = True
        if pos_data.get("rate_spread") is not None and asset.rate_spread is None:
            asset.rate_spread = pos_data["rate_spread"]
            updated = True
        if pos_data.get("rate_type") and not asset.rate_type:
            asset.rate_type = pos_data["rate_type"]
            updated = True
        if pos_data.get("application_date") and not asset.application_date:
            asset.application_date = pos_data["application_date"]
            updated = True
        if pos_data.get("maturity_date") and not asset.maturity_date:
            asset.maturity_date = pos_data["maturity_date"]
            updated = True

        if updated:
            self.db.flush()
