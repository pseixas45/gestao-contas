"""
Endpoints de câmbio.

Permite:
- Consultar cotações do BCB
- Converter valores entre moedas
- Atualizar cache de cotações
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import User
from app.models.exchange_rate import CurrencyCode, ExchangeRate
from app.schemas.exchange import (
    ExchangeRateResponse,
    ConversionRequest,
    ConversionResponse,
    UpdateRatesRequest,
    UpdateRatesResponse,
    AllRatesResponse
)
from app.services.exchange_service import ExchangeService
from app.utils.security import get_current_active_user

router = APIRouter()


@router.get("/rate", response_model=ExchangeRateResponse)
async def get_exchange_rate(
    date_ref: date = Query(..., alias="date", description="Data de referência (YYYY-MM-DD)"),
    currency: CurrencyCode = Query(..., description="Moeda (USD ou EUR)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtém a cotação de uma moeda para uma data específica.

    Busca primeiro no cache local, depois na API do BCB se necessário.
    Se a data for feriado/fim de semana, retorna a cotação do dia útil anterior.
    """
    if currency == CurrencyCode.BRL:
        raise HTTPException(
            status_code=400,
            detail="BRL é a moeda base, não precisa de cotação"
        )

    service = ExchangeService(db)
    rate = await service.get_rate(date_ref, currency)

    if not rate:
        raise HTTPException(
            status_code=404,
            detail=f"Cotação não encontrada para {currency.value} em {date_ref}"
        )

    return rate


@router.get("/rates", response_model=AllRatesResponse)
async def get_all_rates(
    date_ref: date = Query(..., alias="date", description="Data de referência"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtém todas as cotações (USD e EUR) para uma data.
    """
    service = ExchangeService(db)
    rates = await service.get_all_rates(date_ref)

    return AllRatesResponse(
        date_ref=date_ref,
        usd=rates.get(CurrencyCode.USD),
        eur=rates.get(CurrencyCode.EUR)
    )


@router.post("/convert", response_model=ConversionResponse)
async def convert_currency(
    request: ConversionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Converte um valor entre moedas usando a cotação do dia especificado.
    """
    service = ExchangeService(db)

    try:
        converted = await service.convert(
            amount=request.amount,
            from_currency=request.from_currency,
            to_currency=request.to_currency,
            date_ref=request.date_ref
        )

        # Obter a taxa usada para referência
        rate_used = None
        if request.from_currency != request.to_currency:
            if request.from_currency == CurrencyCode.BRL:
                rate = await service.get_rate(request.date_ref, request.to_currency)
                rate_used = rate.sell_rate if rate else None
            elif request.to_currency == CurrencyCode.BRL:
                rate = await service.get_rate(request.date_ref, request.from_currency)
                rate_used = rate.sell_rate if rate else None

        return ConversionResponse(
            original_amount=request.amount,
            original_currency=request.from_currency,
            converted_amount=converted,
            converted_currency=request.to_currency,
            date_ref=request.date_ref,
            rate_used=rate_used
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/update-rates", response_model=UpdateRatesResponse)
async def update_rates(
    request: UpdateRatesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Atualiza o cache de cotações para um período.

    Útil para pré-carregar cotações antes de uma importação em lote.
    """
    if request.end_date < request.start_date:
        raise HTTPException(
            status_code=400,
            detail="Data final deve ser maior ou igual à data inicial"
        )

    # Limitar período para evitar sobrecarga (máximo 2 anos por chamada)
    days_diff = (request.end_date - request.start_date).days
    if days_diff > 730:
        raise HTTPException(
            status_code=400,
            detail="Período máximo permitido é de 730 dias (2 anos). Para períodos maiores, use /load-historical"
        )

    service = ExchangeService(db)
    stats = await service.update_rates_for_period(
        start_date=request.start_date,
        end_date=request.end_date
    )

    return UpdateRatesResponse(**stats)


@router.post("/load-historical")
async def load_historical_rates(
    start_date: date = Query(date(2020, 8, 1), description="Data inicial"),
    end_date: date = Query(None, description="Data final (default: hoje)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Carrega histórico completo de cotações desde uma data inicial.

    Processa em lotes de 180 dias para não sobrecarregar a API do BCB.
    Este endpoint pode demorar vários minutos para períodos longos.
    """
    from datetime import timedelta

    if end_date is None:
        end_date = date.today()

    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="Data final deve ser maior ou igual à data inicial"
        )

    service = ExchangeService(db)

    total_stats = {
        "total_days": 0,
        "usd_loaded": 0,
        "eur_loaded": 0,
        "errors": [],
        "batches_processed": 0
    }

    # Processar em lotes de 180 dias
    batch_size = 180
    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=batch_size - 1), end_date)

        try:
            stats = await service.update_rates_for_period(
                start_date=current_start,
                end_date=current_end
            )

            total_stats["total_days"] += stats.get("total_days", 0)
            total_stats["usd_loaded"] += stats.get("usd_updated", 0)
            total_stats["eur_loaded"] += stats.get("eur_updated", 0)
            total_stats["errors"].extend(stats.get("errors", []))
            total_stats["batches_processed"] += 1

        except Exception as e:
            total_stats["errors"].append(f"Erro no lote {current_start} a {current_end}: {str(e)}")

        current_start = current_end + timedelta(days=1)

    return {
        "message": f"Histórico carregado de {start_date} a {end_date}",
        "stats": total_stats
    }


@router.get("/cache", response_model=List[ExchangeRateResponse])
def list_cached_rates(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    currency: Optional[CurrencyCode] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista cotações armazenadas no cache local.
    """
    service = ExchangeService(db)
    rates = service.get_cached_rates(
        start_date=start_date,
        end_date=end_date,
        currency=currency
    )

    return rates[:limit]
