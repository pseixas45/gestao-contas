"""Calculadora de impostos sobre investimentos (IR, IOF).

Regras fixas definidas pela legislação brasileira.
Módulo puro, sem acesso ao banco de dados.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.models.investment import AssetClassCode


# Tabela IOF regressiva: dia 1 = 96%, dia 2 = 93%, ..., dia 29 = 3%, dia 30+ = 0%
IOF_TABLE = [
    96, 93, 90, 86, 83, 80, 76, 73, 70, 66,
    63, 60, 56, 53, 50, 46, 43, 40, 36, 33,
    30, 26, 23, 20, 16, 13, 10, 6, 3, 0,
]

# IR regressivo para renda fixa
IR_BRACKETS = [
    (180, Decimal("0.225")),   # até 180 dias: 22.5%
    (360, Decimal("0.20")),    # 181-360 dias: 20%
    (720, Decimal("0.175")),   # 361-720 dias: 17.5%
    (None, Decimal("0.15")),   # acima de 720 dias: 15%
]

# IR regressivo para previdência (VGBL/PGBL tabela regressiva)
PREV_IR_BRACKETS = [
    (2, Decimal("0.35")),      # até 2 anos: 35%
    (4, Decimal("0.30")),      # 2-4 anos: 30%
    (6, Decimal("0.25")),      # 4-6 anos: 25%
    (8, Decimal("0.20")),      # 6-8 anos: 20%
    (10, Decimal("0.15")),     # 8-10 anos: 15%
    (None, Decimal("0.10")),   # acima de 10 anos: 10%
]


def get_ir_rate_renda_fixa(days_held: int) -> Decimal:
    """Retorna a alíquota de IR para renda fixa com base nos dias corridos."""
    for max_days, rate in IR_BRACKETS:
        if max_days is None or days_held <= max_days:
            return rate
    return Decimal("0.15")


def get_ir_rate_previdencia(years_held: int) -> Decimal:
    """Retorna a alíquota de IR para previdência (tabela regressiva)."""
    for max_years, rate in PREV_IR_BRACKETS:
        if max_years is None or years_held <= max_years:
            return rate
    return Decimal("0.10")


def calculate_iof(days_held: int, gross_yield: Decimal) -> Decimal:
    """Calcula IOF sobre rendimento bruto.

    IOF incide apenas sobre o rendimento (não sobre o principal).
    Após 30 dias, IOF = 0.
    """
    if days_held >= 30 or gross_yield <= 0:
        return Decimal("0")
    if days_held < 1:
        days_held = 1

    pct = Decimal(str(IOF_TABLE[days_held - 1])) / Decimal("100")
    return (gross_yield * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_ir_renda_fixa(days_held: int, gross_yield: Decimal, iof: Optional[Decimal] = None) -> Decimal:
    """Calcula IR sobre rendimento de renda fixa.

    IR incide sobre (rendimento bruto - IOF).
    """
    if gross_yield <= 0:
        return Decimal("0")

    base = gross_yield
    if iof:
        base = gross_yield - iof

    rate = get_ir_rate_renda_fixa(days_held)
    return (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_ir_exempt(asset_name: str, asset_class: Optional[AssetClassCode] = None) -> bool:
    """Verifica se o investimento é isento de IR.

    Isentos: LCA, LCI, debêntures incentivadas, FII (dividendos para PF).
    """
    name_upper = (asset_name or "").upper()

    # LCA / LCI
    if "LCA " in name_upper or "LCI " in name_upper or name_upper.startswith("LCA") or name_upper.startswith("LCI"):
        return True

    # Debêntures incentivadas (infraestrutura) - marcadas como "DEB FLU"
    # Na XP, debêntures incentivadas aparecem como "DEB FLU U"
    if "DEB FLU" in name_upper:
        return True

    # CRA e CRI são isentos para PF
    if name_upper.startswith("CRA ") or name_upper.startswith("CRI "):
        return True

    # FII dividendos (nota: ganho de capital em FII tem 20% IR)
    # Para simplificar, consideramos FII como isento (dividendos)

    return False


def estimate_net_value(
    value_gross: Decimal,
    value_invested: Decimal,
    days_held: int,
    asset_name: str = "",
    asset_class: Optional[AssetClassCode] = None,
) -> Decimal:
    """Estima valor líquido após IR e IOF.

    Args:
        value_gross: Valor bruto atual
        value_invested: Valor originalmente aplicado
        days_held: Dias corridos desde a aplicação
        asset_name: Nome do ativo (para verificar isenção)
        asset_class: Classe do ativo

    Returns:
        Valor líquido estimado
    """
    if value_gross <= 0 or value_invested <= 0:
        return value_gross

    gross_yield = value_gross - value_invested
    if gross_yield <= 0:
        return value_gross  # Sem rendimento, sem imposto

    # Verificar isenção
    if is_ir_exempt(asset_name, asset_class):
        return value_gross  # Isento de IR

    # Previdência
    if asset_class == AssetClassCode.PREVIDENCIA:
        years = days_held // 365
        ir_rate = get_ir_rate_previdencia(years)
        # Na previdência VGBL, IR incide sobre o rendimento
        # Na PGBL, IR incide sobre o valor total do resgate
        # Simplificação: usar rendimento para ambos
        ir = (gross_yield * ir_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return value_gross - ir

    # Renda fixa padrão
    iof = calculate_iof(days_held, gross_yield)
    ir = calculate_ir_renda_fixa(days_held, gross_yield, iof)

    return value_gross - iof - ir


def get_tax_bracket_info(days_held: int, asset_name: str = "",
                         asset_class: Optional[AssetClassCode] = None) -> dict:
    """Retorna informações sobre a faixa de tributação."""
    if is_ir_exempt(asset_name, asset_class):
        return {"ir_rate": 0, "iof_rate": 0, "exempt": True, "description": "Isento de IR"}

    if asset_class == AssetClassCode.PREVIDENCIA:
        years = days_held // 365
        rate = get_ir_rate_previdencia(years)
        return {"ir_rate": float(rate * 100), "iof_rate": 0, "exempt": False,
                "description": f"Previdência regressiva ({float(rate*100):.0f}%)"}

    ir_rate = get_ir_rate_renda_fixa(days_held)
    iof_rate = 0
    if days_held < 30:
        iof_rate = IOF_TABLE[max(0, days_held - 1)]

    return {
        "ir_rate": float(ir_rate * 100),
        "iof_rate": iof_rate,
        "exempt": False,
        "description": f"RF regressivo ({float(ir_rate*100):.1f}% IR, {days_held}d)",
    }
