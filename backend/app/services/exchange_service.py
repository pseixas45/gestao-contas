"""
Serviço de câmbio.

Busca cotações do Banco Central do Brasil (BCB) via API Olinda OData.
Implementa cache local para evitar requisições repetidas.
"""

import httpx
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict, List
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.exchange_rate import ExchangeRate, CurrencyCode

logger = logging.getLogger(__name__)


class ExchangeService:
    """
    Serviço para busca e conversão de câmbio.

    Usa a API do Banco Central do Brasil (PTAX) via Olinda OData.
    Armazena cache local na tabela exchange_rates.
    """

    # URL base da API do BCB
    BCB_BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"

    # Códigos BCB para moedas
    BCB_CURRENCY_CODES = {
        CurrencyCode.USD: "USD",
        CurrencyCode.EUR: "EUR",
    }

    def __init__(self, db: Session):
        self.db = db

    async def get_rate(
        self,
        date_ref: date,
        currency: CurrencyCode,
        skip_api: bool = True
    ) -> Optional[ExchangeRate]:
        """
        Obtém a taxa de câmbio para uma data e moeda.

        Primeiro verifica o cache local. Se skip_api=False, busca no BCB.

        Args:
            date_ref: Data de referência
            currency: Moeda (USD ou EUR)
            skip_api: Se True, não faz chamadas HTTP (usa apenas cache)

        Returns:
            ExchangeRate ou None se não encontrado
        """
        if currency == CurrencyCode.BRL:
            # BRL é a moeda base, não precisa de conversão
            return None

        # 1. Verificar cache local
        cached = self.db.query(ExchangeRate).filter(
            and_(
                ExchangeRate.date_ref == date_ref,
                ExchangeRate.currency == currency
            )
        ).first()

        if cached:
            return cached

        # 2. Se skip_api=True, ir direto para buscar dia anterior no cache
        if skip_api:
            return await self._get_nearest_rate(date_ref, currency)

        # 3. Buscar no BCB (apenas se skip_api=False)
        rate_data = await self._fetch_from_bcb(date_ref, currency)

        if rate_data:
            # 4. Salvar no cache
            exchange_rate = ExchangeRate(
                date_ref=date_ref,
                currency=currency,
                buy_rate=rate_data["buy_rate"],
                sell_rate=rate_data["sell_rate"],
                bulletin_type=rate_data.get("bulletin_type", "Fechamento"),
                quote_datetime=rate_data.get("quote_datetime"),
                source="BCB-PTAX"
            )
            self.db.add(exchange_rate)
            self.db.commit()
            self.db.refresh(exchange_rate)
            return exchange_rate

        # 5. Se não encontrou, tentar dia anterior (feriados/fins de semana)
        return await self._get_nearest_rate(date_ref, currency)

    async def _fetch_from_bcb(
        self,
        date_ref: date,
        currency: CurrencyCode
    ) -> Optional[Dict]:
        """
        Busca cotação diretamente na API do BCB.

        Args:
            date_ref: Data de referência
            currency: Moeda

        Returns:
            Dict com buy_rate, sell_rate, bulletin_type, quote_datetime ou None
        """
        bcb_code = self.BCB_CURRENCY_CODES.get(currency)
        if not bcb_code:
            return None

        # Formato de data do BCB: MM-DD-YYYY
        date_str = date_ref.strftime("%m-%d-%Y")

        # URL da API
        url = (
            f"{self.BCB_BASE_URL}/CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
            f"?@moeda='{bcb_code}'&@dataCotacao='{date_str}'"
            f"&$format=json"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            values = data.get("value", [])
            if not values:
                logger.info(f"Nenhuma cotação encontrada para {currency.value} em {date_ref}")
                return None

            # Filtrar apenas "Fechamento" e pegar o mais recente
            fechamento = [v for v in values if v.get("tipoBoletim") == "Fechamento"]

            if fechamento:
                # Pegar o mais recente (maior dataHoraCotacao)
                latest = max(fechamento, key=lambda x: x.get("dataHoraCotacao", ""))
            else:
                # Se não tem fechamento, pegar qualquer um (último do dia)
                latest = values[-1]

            # Extrair dados
            buy_rate = Decimal(str(latest.get("cotacaoCompra", 0)))
            sell_rate = Decimal(str(latest.get("cotacaoVenda", 0)))

            # Parse da data/hora da cotação
            quote_datetime = None
            dt_str = latest.get("dataHoraCotacao")
            if dt_str:
                try:
                    quote_datetime = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return {
                "buy_rate": buy_rate,
                "sell_rate": sell_rate,
                "bulletin_type": latest.get("tipoBoletim", "Fechamento"),
                "quote_datetime": quote_datetime
            }

        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar cotação do BCB: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar cotação: {e}")
            return None

    async def _get_nearest_rate(
        self,
        date_ref: date,
        currency: CurrencyCode,
        max_days_back: int = 7
    ) -> Optional[ExchangeRate]:
        """
        Busca a cotação mais próxima (para feriados/fins de semana).

        OTIMIZAÇÃO: Busca apenas no cache local, assumindo que as cotações
        históricas já foram carregadas. Não faz chamadas HTTP.

        Args:
            date_ref: Data de referência
            currency: Moeda
            max_days_back: Máximo de dias para voltar

        Returns:
            ExchangeRate mais recente ou None
        """
        # OTIMIZAÇÃO: Buscar a cotação mais recente anterior à data no cache
        cached = self.db.query(ExchangeRate).filter(
            and_(
                ExchangeRate.date_ref < date_ref,
                ExchangeRate.date_ref >= date_ref - timedelta(days=max_days_back),
                ExchangeRate.currency == currency
            )
        ).order_by(ExchangeRate.date_ref.desc()).first()

        if cached:
            return cached

        logger.warning(f"Nenhuma cotação encontrada para {currency.value} nos últimos {max_days_back} dias")
        return None

    async def convert(
        self,
        amount: Decimal,
        from_currency: CurrencyCode,
        to_currency: CurrencyCode,
        date_ref: date
    ) -> Decimal:
        """
        Converte valor entre moedas usando cotação do dia.

        Args:
            amount: Valor a converter
            from_currency: Moeda de origem
            to_currency: Moeda de destino
            date_ref: Data de referência para a cotação

        Returns:
            Valor convertido (arredondado para 2 casas)

        Raises:
            ValueError: Se não encontrar cotação
        """
        if from_currency == to_currency:
            return amount

        # Caso especial: conversão para/de BRL
        if from_currency == CurrencyCode.BRL:
            # BRL -> USD/EUR: dividir pela cotação
            rate = await self.get_rate(date_ref, to_currency)
            if not rate:
                raise ValueError(f"Cotação não encontrada para {to_currency.value} em {date_ref}")
            result = amount / rate.sell_rate

        elif to_currency == CurrencyCode.BRL:
            # USD/EUR -> BRL: multiplicar pela cotação
            rate = await self.get_rate(date_ref, from_currency)
            if not rate:
                raise ValueError(f"Cotação não encontrada para {from_currency.value} em {date_ref}")
            result = amount * rate.sell_rate

        else:
            # USD <-> EUR: converter via BRL
            # from_currency -> BRL -> to_currency
            rate_from = await self.get_rate(date_ref, from_currency)
            rate_to = await self.get_rate(date_ref, to_currency)

            if not rate_from or not rate_to:
                raise ValueError(f"Cotação não encontrada para conversão {from_currency.value} -> {to_currency.value}")

            # Primeiro converte para BRL, depois para moeda destino
            brl_amount = amount * rate_from.sell_rate
            result = brl_amount / rate_to.sell_rate

        # Arredondar para 2 casas decimais
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def get_all_rates(
        self,
        date_ref: date
    ) -> Dict[CurrencyCode, Optional[ExchangeRate]]:
        """
        Obtém todas as cotações para uma data.

        Args:
            date_ref: Data de referência

        Returns:
            Dict com taxas para USD e EUR
        """
        return {
            CurrencyCode.USD: await self.get_rate(date_ref, CurrencyCode.USD),
            CurrencyCode.EUR: await self.get_rate(date_ref, CurrencyCode.EUR),
        }

    async def _fetch_period_from_bcb(
        self,
        start_date: date,
        end_date: date,
        currency: CurrencyCode
    ) -> List[Dict]:
        """
        Busca cotações de um período via endpoint CotacaoMoedaPeriodo do BCB.
        Uma única chamada HTTP para todo o período.
        """
        bcb_code = self.BCB_CURRENCY_CODES.get(currency)
        if not bcb_code:
            return []

        di = start_date.strftime("%m-%d-%Y")
        df = end_date.strftime("%m-%d-%Y")

        url = (
            f"{self.BCB_BASE_URL}/CotacaoMoedaPeriodo(moeda=@moeda,"
            f"dataInicial=@di,dataFinalCotacao=@df)"
            f"?@moeda='{bcb_code}'&@di='{di}'&@df='{df}'"
            f"&$format=json&$orderby=dataHoraCotacao%20desc"
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
            return data.get("value", [])
        except Exception as e:
            logger.error(f"Erro ao buscar cotações do BCB para {currency.value}: {e}")
            return []

    async def update_rates_for_period(
        self,
        start_date: date,
        end_date: date
    ) -> Dict:
        """
        Atualiza cotações para um período usando busca bulk do BCB.
        Faz apenas 2 chamadas HTTP (uma por moeda) em vez de uma por dia.
        """
        stats = {
            "total_days": (end_date - start_date).days + 1,
            "usd_updated": 0,
            "eur_updated": 0,
            "errors": []
        }

        for currency, stat_key in [
            (CurrencyCode.USD, "usd_updated"),
            (CurrencyCode.EUR, "eur_updated"),
        ]:
            try:
                values = await self._fetch_period_from_bcb(start_date, end_date, currency)

                # Agrupar por data, pegando apenas Fechamento (ou último do dia)
                by_date: Dict[str, Dict] = {}
                for v in values:
                    dt_str = v.get("dataHoraCotacao", "")
                    ref_date = dt_str[:10] if dt_str else None
                    if not ref_date:
                        continue

                    tipo = v.get("tipoBoletim", "")
                    # Preferir Fechamento sobre outros tipos
                    if ref_date not in by_date or tipo == "Fechamento":
                        by_date[ref_date] = v

                for ref_date_str, v in by_date.items():
                    try:
                        ref_date = datetime.fromisoformat(ref_date_str).date()
                    except ValueError:
                        continue

                    # Verificar se já existe no cache
                    existing = self.db.query(ExchangeRate).filter(
                        and_(
                            ExchangeRate.date_ref == ref_date,
                            ExchangeRate.currency == currency
                        )
                    ).first()

                    if existing:
                        continue

                    buy_rate = Decimal(str(v.get("cotacaoCompra", 0)))
                    sell_rate = Decimal(str(v.get("cotacaoVenda", 0)))

                    quote_datetime = None
                    dt_full = v.get("dataHoraCotacao")
                    if dt_full:
                        try:
                            quote_datetime = datetime.fromisoformat(dt_full.replace("Z", "+00:00"))
                        except ValueError:
                            pass

                    rate = ExchangeRate(
                        date_ref=ref_date,
                        currency=currency,
                        buy_rate=buy_rate,
                        sell_rate=sell_rate,
                        bulletin_type=v.get("tipoBoletim", "Fechamento"),
                        quote_datetime=quote_datetime,
                        source="BCB-PTAX"
                    )
                    self.db.add(rate)
                    stats[stat_key] += 1

                self.db.commit()

            except Exception as e:
                stats["errors"].append(f"{currency.value}: {str(e)}")
                self.db.rollback()

        return stats

    def get_cached_rates(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[CurrencyCode] = None
    ) -> List[ExchangeRate]:
        """
        Obtém cotações do cache local.

        Args:
            start_date: Data inicial (opcional)
            end_date: Data final (opcional)
            currency: Moeda específica (opcional)

        Returns:
            Lista de ExchangeRate
        """
        query = self.db.query(ExchangeRate)

        if start_date:
            query = query.filter(ExchangeRate.date_ref >= start_date)
        if end_date:
            query = query.filter(ExchangeRate.date_ref <= end_date)
        if currency:
            query = query.filter(ExchangeRate.currency == currency)

        return query.order_by(ExchangeRate.date_ref.desc()).all()
