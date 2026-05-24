"""Helpers compartilhados e tipos para parsers de investimentos."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, TypedDict

from app.models.investment import AssetClassCode, RateIndex, RateType


class ParsedPosition(TypedDict, total=False):
    """Posição parseada de um extrato."""
    name: str
    name_normalized: str
    asset_class: AssetClassCode
    value: Decimal
    value_invested: Optional[Decimal]
    value_gross: Optional[Decimal]
    value_net: Optional[Decimal]
    quantity: Optional[Decimal]
    allocation_pct: Optional[Decimal]
    yield_net_pct: Optional[Decimal]
    yield_gross_pct: Optional[Decimal]
    yield_value: Optional[Decimal]
    yield_month_value: Optional[Decimal]
    maturity_date: Optional[date]
    contracted_rate: Optional[str]
    rate_index: Optional[RateIndex]
    rate_spread: Optional[Decimal]
    rate_type: Optional[RateType]
    application_date: Optional[date]


class ParsedSnapshot(TypedDict, total=False):
    """Resultado completo do parse de um extrato."""
    snapshot_date: date
    total_value: Optional[Decimal]
    total_invested: Optional[Decimal]
    available_balance: Decimal
    total_gross: Optional[Decimal]
    total_net: Optional[Decimal]
    yield_month_value: Optional[Decimal]
    positions: List[ParsedPosition]


# ============================================================
# Helpers de parsing
# ============================================================

def parse_money(value: Any) -> Optional[Decimal]:
    """'R$ 154.250,73' -> Decimal('154250.73'). Aceita float/int."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("R$", "").replace("R\\$", "").strip()
    # Remover espaços no meio (ex: "154 250,73")
    s = s.replace("\xa0", "").replace(" ", "")
    # Detectar negativo
    negative = False
    if s.endswith("-") or s.startswith("-"):
        negative = True
        s = s.strip("-")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        val = Decimal(s)
        return -val if negative else val
    except (InvalidOperation, ValueError):
        return None


def parse_pct(value: Any) -> Optional[Decimal]:
    """'9,18%' -> Decimal('9.18')."""
    if value is None or value == "":
        return None
    s = str(value).strip().replace("%", "").strip()
    if not s or s == "-":
        return None
    negative = False
    if s.startswith("-"):
        negative = True
        s = s[1:]
    s = s.replace(",", ".")
    try:
        val = Decimal(s)
        return -val if negative else val
    except (InvalidOperation, ValueError):
        return None


def parse_date_br(value: Any) -> Optional[date]:
    """'31/12/2025' -> date(2025,12,31). Aceita datetime/date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s == "-" or s == "--":
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Ano com 2 dígitos
    m = re.match(r"(\d{2})/(\d{2})/(\d{2})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + y if y < 50 else 1900 + y
        try:
            return date(y, mo, d)
        except ValueError:
            pass
    return None


def normalize_name(name: str) -> str:
    """Normaliza nome de ativo para matching entre snapshots."""
    if not name:
        return ""
    s = str(name).strip().upper()
    s = re.sub(r"\s+", " ", s)
    # Tratar mojibake (latin-1 → utf-8)
    try:
        s = s.encode("latin-1").decode("utf-8").upper()
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return s


# Mapeamento de subcategorias → AssetClassCode
SUBCATEGORY_MAP = {
    "alternativos": AssetClassCode.ALTERNATIVOS,
    "inflacao": AssetClassCode.INFLACAO,
    "inflação": AssetClassCode.INFLACAO,
    "pre-fixado": AssetClassCode.PRE_FIXADO,
    "prefixado": AssetClassCode.PRE_FIXADO,
    "prefixada": AssetClassCode.PRE_FIXADO,
    "pré-fixado": AssetClassCode.PRE_FIXADO,
    "pos-fixado": AssetClassCode.POS_FIXADO,
    "pós-fixado": AssetClassCode.POS_FIXADO,
    "pos-fixada": AssetClassCode.POS_FIXADO,
    "pós-fixada": AssetClassCode.POS_FIXADO,
    "fundos listados": AssetClassCode.FII,
    "fii": AssetClassCode.FII,
    "fundos imobiliarios": AssetClassCode.FII,
    "fundos imobiliários": AssetClassCode.FII,
    "renda variavel": AssetClassCode.RENDA_VARIAVEL,
    "renda variável": AssetClassCode.RENDA_VARIAVEL,
    "acoes": AssetClassCode.RENDA_VARIAVEL,
    "ações": AssetClassCode.RENDA_VARIAVEL,
    "multimercado": AssetClassCode.MULTIMERCADO,
    "multimercados": AssetClassCode.MULTIMERCADO,
    "cripto": AssetClassCode.CRIPTO,
    "crypto": AssetClassCode.CRIPTO,
    "bitcoin": AssetClassCode.CRIPTO,
    "cambial": AssetClassCode.CAMBIAL,
    "previdencia": AssetClassCode.PREVIDENCIA,
    "previdência": AssetClassCode.PREVIDENCIA,
    "vgbl": AssetClassCode.PREVIDENCIA,
    "pgbl": AssetClassCode.PREVIDENCIA,
}


def detect_asset_class(label: str) -> Optional[AssetClassCode]:
    """Detecta classe do ativo a partir de um label/nome de seção."""
    if not label:
        return None
    # Tratar mojibake
    try:
        label = label.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    s = str(label).lower().strip()
    # Padrão "X% | Subcategoria"
    parts = s.split("|")
    if len(parts) > 1:
        s = parts[-1].strip()
    for k, v in SUBCATEGORY_MAP.items():
        if k in s:
            return v
    return None
