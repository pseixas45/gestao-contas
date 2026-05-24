"""
Serviço de dados de mercado (CDI, IPCA) do Banco Central do Brasil.

Busca séries temporais via API SGS do BCB.
Implementa cache local na tabela market_index_rates.
"""
import httpx
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.market_data import MarketIndexCode, MarketIndexRate

logger = logging.getLogger(__name__)


# Séries do BCB (Sistema Gerenciador de Séries Temporais)
BCB_SERIES = {
    MarketIndexCode.CDI: 12,     # Taxa CDI diária (% a.d.)
    MarketIndexCode.SELIC: 432,  # Taxa SELIC diária (% a.d.)
    MarketIndexCode.IPCA: 433,   # IPCA mensal (% a.m.)
    MarketIndexCode.IGPM: 189,   # IGP-M mensal (% a.m.)
}


class MarketDataService:
    """Serviço para busca e cálculo com dados de mercado do BCB."""

    BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

    def __init__(self, db: Session):
        self.db = db

    async def update_rates_for_period(
        self,
        start_date: date,
        end_date: date,
        indices: Optional[List[MarketIndexCode]] = None,
    ) -> Dict:
        """Atualiza taxas do BCB para um período. Busca bulk."""
        if indices is None:
            indices = [MarketIndexCode.CDI, MarketIndexCode.IPCA]

        stats = {"total_fetched": 0, "errors": []}

        for index_code in indices:
            series_code = BCB_SERIES.get(index_code)
            if not series_code:
                continue

            try:
                records = await self._fetch_series(series_code, start_date, end_date)
                inserted = 0

                for record in records:
                    dt_str = record.get("data")
                    val_str = record.get("valor")
                    if not dt_str or val_str is None:
                        continue

                    # Parse data dd/mm/yyyy
                    try:
                        parts = dt_str.split("/")
                        ref_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
                    except (ValueError, IndexError):
                        continue

                    value = Decimal(str(val_str))

                    # Verificar se já existe
                    existing = self.db.query(MarketIndexRate).filter(
                        and_(
                            MarketIndexRate.date_ref == ref_date,
                            MarketIndexRate.index_code == index_code,
                        )
                    ).first()
                    if existing:
                        continue

                    # CDI/SELIC são diários, IPCA/IGPM são mensais
                    is_daily = index_code in (MarketIndexCode.CDI, MarketIndexCode.SELIC)

                    rate = MarketIndexRate(
                        index_code=index_code,
                        date_ref=ref_date,
                        daily_rate=value if is_daily else None,
                        monthly_rate=value if not is_daily else None,
                        source="BCB",
                    )
                    self.db.add(rate)
                    inserted += 1

                self.db.commit()
                stats["total_fetched"] += inserted
                logger.info(f"{index_code.value}: {inserted} registros inseridos ({start_date} a {end_date})")

            except Exception as e:
                stats["errors"].append(f"{index_code.value}: {str(e)}")
                self.db.rollback()
                logger.error(f"Erro ao buscar {index_code.value}: {e}")

        return stats

    async def _fetch_series(self, series_code: int, start_date: date, end_date: date) -> List[Dict]:
        """Busca série temporal do BCB via SGS API."""
        di = start_date.strftime("%d/%m/%Y")
        df = end_date.strftime("%d/%m/%Y")

        url = self.BCB_SGS_URL.format(code=series_code)
        params = {"formato": "json", "dataInicial": di, "dataFinal": df}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Erro ao buscar série {series_code} do BCB: {e}")
            return []

    def _ensure_cdi_cache(self):
        """Carrega todos os CDI em memória (1 query) para evitar N+1."""
        if hasattr(self, '_cdi_cache'):
            return
        rates = (
            self.db.query(MarketIndexRate.date_ref, MarketIndexRate.daily_rate)
            .filter(
                MarketIndexRate.index_code == MarketIndexCode.CDI,
                MarketIndexRate.daily_rate.isnot(None),
            )
            .order_by(MarketIndexRate.date_ref)
            .all()
        )
        self._cdi_cache = [(r[0], r[1]) for r in rates]

    def _ensure_ipca_cache(self):
        """Carrega todos os IPCA em memória (1 query)."""
        if hasattr(self, '_ipca_cache'):
            return
        rates = (
            self.db.query(MarketIndexRate.date_ref, MarketIndexRate.monthly_rate)
            .filter(
                MarketIndexRate.index_code == MarketIndexCode.IPCA,
                MarketIndexRate.monthly_rate.isnot(None),
            )
            .order_by(MarketIndexRate.date_ref)
            .all()
        )
        self._ipca_cache = [(r[0], r[1]) for r in rates]

    def get_accumulated_cdi(self, start_date: date, end_date: date) -> Decimal:
        """Calcula CDI acumulado no período: Π(1 + taxa_diaria/100).

        Returns:
            Fator acumulado (ex: 1.0523 = 5.23% no período)
        """
        self._ensure_cdi_cache()
        factor = Decimal("1")
        for dt, rate in self._cdi_cache:
            if dt < start_date:
                continue
            if dt > end_date:
                break
            factor *= (Decimal("1") + rate / Decimal("100"))
        return factor

    def get_accumulated_ipca(self, start_date: date, end_date: date) -> Decimal:
        """Calcula IPCA acumulado no período: Π(1 + taxa_mensal/100).

        Returns:
            Fator acumulado (ex: 1.045 = 4.5% no período)
        """
        self._ensure_ipca_cache()
        factor = Decimal("1")
        for dt, rate in self._ipca_cache:
            if dt < start_date:
                continue
            if dt > end_date:
                break
            factor *= (Decimal("1") + rate / Decimal("100"))
        return factor

    def get_cdi_business_days(self, start_date: date, end_date: date) -> int:
        """Retorna número de dias úteis (dias com CDI) no período."""
        self._ensure_cdi_cache()
        return sum(1 for dt, _ in self._cdi_cache if start_date <= dt <= end_date)

    def get_latest_date(self, index_code: MarketIndexCode) -> Optional[date]:
        """Retorna a data mais recente disponível para um índice."""
        result = (
            self.db.query(MarketIndexRate.date_ref)
            .filter(MarketIndexRate.index_code == index_code)
            .order_by(MarketIndexRate.date_ref.desc())
            .first()
        )
        return result[0] if result else None
