"""Extrai estratégia de remuneração estruturada a partir de strings de taxa."""
import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from app.models.investment import RateIndex, RateType


def extract_rate(rate_str: str) -> Tuple[Optional[RateIndex], Optional[Decimal], Optional[RateType]]:
    """Converte string de taxa para dados estruturados.

    Exemplos:
        "IPCA + 7,0000%"     -> (IPCA, 7.0, SPREAD)
        "100% CDI"           -> (CDI, 100, PERCENTAGE)
        "100,00% CDI"        -> (CDI, 100, PERCENTAGE)
        "CDI + 2,50%"        -> (CDI, 2.5, SPREAD)
        "CDI + 4,60% a.a."   -> (CDI, 4.6, SPREAD)
        "97% CDI"            -> (CDI, 97, PERCENTAGE)
        "100% DI"            -> (CDI, 100, PERCENTAGE)
        "PRE 12,50%"         -> (PRE, 12.5, SPREAD)
        "12,50% a.a."        -> (PRE, 12.5, SPREAD)  # taxa pré sem índice
        "TR + 2%"            -> (TR, 2, SPREAD)
        "IGPM + 6%"          -> (IGPM, 6, SPREAD)

    Returns:
        (rate_index, rate_spread, rate_type) ou (None, None, None) se não identificado.
    """
    if not rate_str:
        return None, None, None

    s = str(rate_str).strip().upper()
    # Normalizar separadores
    s = s.replace("\xa0", " ")

    # Padrão 1: "X% CDI" ou "X% DI" (percentage do CDI)
    m = re.search(r"(\d{1,3}[,.]?\d*)\s*%\s*(?:CDI|DI)\b", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.CDI, val, RateType.PERCENTAGE

    # Padrão 2: "CDI + X%" ou "DI + X%" (spread sobre CDI)
    m = re.search(r"(?:CDI|DI)\s*\+\s*(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.CDI, val, RateType.SPREAD

    # Padrão 3: "IPCA + X%" (spread sobre IPCA)
    m = re.search(r"IPCA\s*\+?\s*(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.IPCA, val, RateType.SPREAD

    # Padrão 4: "TR + X%"
    m = re.search(r"TR\s*\+\s*(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.TR, val, RateType.SPREAD

    # Padrão 5: "IGPM + X%" ou "IGP-M + X%"
    m = re.search(r"IGP[-]?M\s*\+\s*(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.IGPM, val, RateType.SPREAD

    # Padrão 6: "SELIC + X%"
    m = re.search(r"SELIC\s*\+\s*(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.SELIC, val, RateType.SPREAD

    # Padrão 7: "PRE X%" ou "PREFIXADO X%"
    m = re.search(r"(?:PRE|PREFIXADO|PR[EÉ])\s+(\d{1,3}[,.]?\d*)\s*%", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.PRE, val, RateType.SPREAD

    # Padrão 8: "X% a.a." sem índice → provável pré-fixado
    m = re.search(r"(\d{1,3}[,.]?\d*)\s*%\s*(?:A\.?A\.?|AO\s*ANO)", s)
    if m:
        val = _parse_num(m.group(1))
        if val is not None:
            return RateIndex.PRE, val, RateType.SPREAD

    return None, None, None


def format_rate(rate_index: Optional[RateIndex], rate_spread: Optional[Decimal],
                rate_type: Optional[RateType]) -> str:
    """Formata dados estruturados de volta para string legível."""
    if not rate_index or rate_spread is None:
        return ""
    spread_str = f"{float(rate_spread):.2f}".rstrip("0").rstrip(".")
    if rate_type == RateType.PERCENTAGE:
        return f"{spread_str}% {rate_index.value}"
    else:
        return f"{rate_index.value} + {spread_str}%"


def _parse_num(s: str) -> Optional[Decimal]:
    """Parse número com vírgula ou ponto decimal."""
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None
