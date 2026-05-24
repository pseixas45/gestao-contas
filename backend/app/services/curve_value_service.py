"""Serviço de cálculo de valor na curva (valor teórico) de investimentos.

O valor na curva é o que o investimento valeria se carregado até o vencimento
com a taxa contratada, sem considerar marcação a mercado.

Calculado on-demand a partir dos dados de mercado (CDI/IPCA) do BCB.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any
import logging

from sqlalchemy.orm import Session

from app.models.investment import (
    Asset, InvestmentPosition, InvestmentSnapshot,
    RateIndex, RateType, AssetClassCode,
)
from app.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

# 252 dias úteis por ano (padrão brasileiro)
BUSINESS_DAYS_YEAR = 252


class CurveValueService:
    """Calcula valor na curva para investimentos com taxa contratada."""

    def __init__(self, db: Session):
        self.db = db
        self.market = MarketDataService(db)

    def calculate_curve_value(
        self,
        value_invested: Decimal,
        application_date: date,
        reference_date: date,
        rate_index: RateIndex,
        rate_spread: Decimal,
        rate_type: RateType,
    ) -> Optional[Decimal]:
        """Calcula o valor teórico na curva.

        Fórmulas:
        - 100% CDI: invested × Π(1 + cdi_diario)
        - 97% CDI:  invested × Π(1 + 0.97 × cdi_diario)
        - CDI + 4.6%: invested × Π(1 + cdi_diario) × (1 + 4.6/100)^(du/252)
        - IPCA + 7%: invested × IPCA_acum × (1 + 7/100)^(du/252)
        - PRE 12.5%: invested × (1 + 12.5/100)^(du/252)

        Args:
            value_invested: Valor aplicado (capital)
            application_date: Data da aplicação
            reference_date: Data de referência para o cálculo
            rate_index: Índice (CDI, IPCA, PRE, etc.)
            rate_spread: Valor numérico da taxa
            rate_type: Tipo (PERCENTAGE ou SPREAD)

        Returns:
            Valor na curva ou None se dados insuficientes
        """
        if not value_invested or value_invested <= 0:
            return None
        if application_date >= reference_date:
            return value_invested

        try:
            if rate_index == RateIndex.CDI:
                return self._calc_cdi(value_invested, application_date, reference_date, rate_spread, rate_type)
            elif rate_index == RateIndex.IPCA:
                return self._calc_ipca(value_invested, application_date, reference_date, rate_spread)
            elif rate_index == RateIndex.PRE:
                return self._calc_pre(value_invested, application_date, reference_date, rate_spread)
            elif rate_index == RateIndex.SELIC:
                # SELIC ≈ CDI na prática
                return self._calc_cdi(value_invested, application_date, reference_date, rate_spread, rate_type)
            else:
                return None
        except Exception as e:
            logger.warning(f"Erro ao calcular valor na curva: {e}")
            return None

    def _calc_cdi(self, invested: Decimal, start: date, end: date,
                  spread: Decimal, rate_type: RateType) -> Optional[Decimal]:
        """Calcula valor para investimentos indexados ao CDI."""
        cdi_factor = self.market.get_accumulated_cdi(start, end)
        if cdi_factor <= Decimal("1"):
            # Sem dados de CDI
            return None

        if rate_type == RateType.PERCENTAGE:
            # X% do CDI: ajustar o fator
            # Se CDI acumulou F, então X% CDI acumulou F^(X/100) (aproximação)
            # Fórmula exata: Π(1 + X/100 * cdi_diario_i)
            # Aproximação simples: fator_cdi^(spread/100) para spread próximo de 100
            pct = spread / Decimal("100")
            # Para percentuais do CDI, a fórmula correta é aplicar o percentual dia a dia
            # Mas como só temos o fator acumulado, usamos: (fator - 1) * pct + 1
            cdi_yield = cdi_factor - Decimal("1")
            adjusted_factor = Decimal("1") + cdi_yield * pct
            result = invested * adjusted_factor
        else:
            # CDI + X% a.a.
            # Valor = invested × fator_cdi × (1 + X/100)^(du/252)
            du = self.market.get_cdi_business_days(start, end)
            if du == 0:
                return None
            spread_annual = spread / Decimal("100")
            spread_factor = (Decimal("1") + spread_annual) ** (Decimal(str(du)) / Decimal(str(BUSINESS_DAYS_YEAR)))
            result = invested * cdi_factor * spread_factor

        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_ipca(self, invested: Decimal, start: date, end: date,
                   spread: Decimal) -> Optional[Decimal]:
        """Calcula valor para IPCA + X%."""
        ipca_factor = self.market.get_accumulated_ipca(start, end)
        du = self.market.get_cdi_business_days(start, end)

        if du == 0:
            return None

        # Valor = invested × IPCA_acum × (1 + spread/100)^(du/252)
        spread_annual = spread / Decimal("100")
        spread_factor = (Decimal("1") + spread_annual) ** (Decimal(str(du)) / Decimal(str(BUSINESS_DAYS_YEAR)))

        result = invested * ipca_factor * spread_factor
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_pre(self, invested: Decimal, start: date, end: date,
                  spread: Decimal) -> Optional[Decimal]:
        """Calcula valor para pré-fixado X% a.a."""
        du = self.market.get_cdi_business_days(start, end)
        if du == 0:
            # Estimar dias úteis como ~dias corridos × 252/365
            dc = (end - start).days
            du = int(dc * 252 / 365)

        # Valor = invested × (1 + taxa/100)^(du/252)
        rate_annual = spread / Decimal("100")
        factor = (Decimal("1") + rate_annual) ** (Decimal(str(du)) / Decimal(str(BUSINESS_DAYS_YEAR)))

        result = invested * factor
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def enrich_positions_with_curve(
        self,
        positions: List[Dict[str, Any]],
        reference_date: date,
    ) -> List[Dict[str, Any]]:
        """Adiciona curve_value a uma lista de posições (formato de resposta API).

        Args:
            positions: Lista de dicts com asset_id, value, value_invested, etc.
            reference_date: Data de referência

        Returns:
            Mesma lista com campo 'curve_value' adicionado
        """
        # Carregar assets necessários
        asset_ids = [p.get("asset_id") for p in positions if p.get("asset_id")]
        if not asset_ids:
            return positions

        assets = {a.id: a for a in self.db.query(Asset).filter(Asset.id.in_(asset_ids)).all()}

        for pos in positions:
            asset = assets.get(pos.get("asset_id"))
            if not asset or not asset.rate_index or not asset.application_date:
                pos["curve_value"] = None
                continue

            invested = pos.get("value_invested")
            if not invested:
                pos["curve_value"] = None
                continue

            curve = self.calculate_curve_value(
                value_invested=Decimal(str(invested)),
                application_date=asset.application_date,
                reference_date=reference_date,
                rate_index=asset.rate_index,
                rate_spread=asset.rate_spread or Decimal("0"),
                rate_type=asset.rate_type or RateType.PERCENTAGE,
            )
            pos["curve_value"] = float(curve) if curve else None

        return positions
