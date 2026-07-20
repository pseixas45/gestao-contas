"""Parser do Extrato da Conta Corrente XP (movimentações de caixa da corretora).

Arquivo: "XP Extrato <conta> <periodo>.xlsx".
O layout pode variar; o parser localiza a aba e a linha de cabeçalho que
contêm "Movimentação" e "Lançamento", e mapeia as colunas pelo nome:
    Movimentação | Liquidação | Lançamento | MOV | Valor (R$) | Saldo (R$)

**Categoria vem da coluna MOV** (fonte autoritativa definida pelo usuário):
    RESG → Resgate, APLIC → Aplicação, REND → Rendimento, TRANSF → Transferência
Se não houver coluna MOV (arquivos antigos), cai no classificador por prefixo
da descrição (classify_movement).

Gera uma lista de MOVIMENTAÇÕES para virar transações na conta XP corrente,
usada como fonte de dados para a análise de aplicações/resgates/rendimentos.
"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import openpyxl


# IDs de categoria (schema gestao_contas)
CAT_APLICACAO = 1
CAT_IMPOSTOS = 12
CAT_RENDIMENTO = 21
CAT_RESGATE = 22
CAT_TRANSFERENCIA = 30

# Coluna MOV -> categoria (autoritativo)
MOV_TO_CATEGORY = {
    "RESG": CAT_RESGATE,
    "APLIC": CAT_APLICACAO,
    "REND": CAT_RENDIMENTO,
    "TRANSF": CAT_TRANSFERENCIA,
}


def classify_movement(desc: str, valor: Decimal) -> Dict[str, Any]:
    """Deriva a categoria a partir do texto do Lançamento.

    Regras validadas com o usuário (avaliadas nesta PRECEDÊNCIA, que resolve
    conflitos como "IOF Cambio" ou o fundo "Trend Investback"):
        Resgate > Aplicação > Rendimento > Transferência

    - Resgate: contém "RESGATE" ou "IOF"; ou "RECEBIMENTO DE TED" da própria
      conta (CTA 4065643 — resgate interno, exceção do TED BCO 348).
    - Aplicação: contém "APLICA", "INTEGRALIZA", "COMPRA" ou "CAMBIO".
    - Rendimento: contém "JUROS", "RENDIMENTO", "AMORTIZA", "INVESTBACK" ou "PRÊMIO".
    - Transferência: contém "TED BCO 341" (aportes/retiradas do titular).

    Retorna dict com kind, category_id, flow e external.
    """
    u = (desc or "").strip().upper()

    if ("RESGATE" in u) or ("IOF" in u) or ("RECEBIMENTO DE TED" in u and "CTA 4065643" in u):
        cat, kind = CAT_RESGATE, "resgate"
    elif any(k in u for k in ("APLICA", "INTEGRALIZA", "COMPRA", "CAMBIO", "CÂMBIO")):
        cat, kind = CAT_APLICACAO, "aplicacao"
    elif any(k in u for k in ("JUROS", "RENDIMENTO", "AMORTIZA", "INVESTBACK", "PREMIO", "PRÊMIO", "PRÉMIO")):
        cat, kind = CAT_RENDIMENTO, "rendimento"
    elif "TED BCO 341" in u:
        cat, kind = CAT_TRANSFERENCIA, "transferencia"
    else:
        cat, kind = None, "outros"

    # Fluxo externo (cruza a corretora) — informativo p/ análise
    external = ("RECEBIMENTO DE TED" in u) or ("RETIRADA EM C/C" in u)
    return {"kind": kind, "category_id": cat, "flow": kind, "external": external}


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_decimal(v: Any) -> Optional[Decimal]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def _find_sheet_and_header(wb):
    """Localiza (rows, header_idx, colmap) da aba com o extrato de movimentações."""
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for i, row in enumerate(rows[:40]):
            labels = {}
            for k, c in enumerate(row):
                if c is not None:
                    labels[str(c).strip().lower()] = k
            has_mov = any("movimenta" in l for l in labels)
            has_lanc = any(("lançamento" in l or "lancamento" in l) for l in labels)
            if has_mov and has_lanc:
                colmap = {}
                for label, k in labels.items():
                    if "movimenta" in label:
                        colmap.setdefault("date", k)
                    elif "liquida" in label:
                        colmap.setdefault("liq", k)
                    elif "lança" in label or "lanca" in label:
                        colmap.setdefault("desc", k)
                    elif label == "mov":
                        colmap.setdefault("mov", k)
                    elif "valor" in label:
                        colmap.setdefault("valor", k)
                    elif "saldo" in label:
                        colmap.setdefault("saldo", k)
                return rows, i, colmap
    return None, None, None


def parse_xp_extrato_conta(path: str) -> List[Dict[str, Any]]:
    """Lê o xlsx e retorna a lista de movimentações classificadas.

    Cada item: {date, liquidation_date, description, amount(Decimal, com sinal),
                saldo, mov, kind, category_id, flow, external}
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows, header_idx, colmap = _find_sheet_and_header(wb)
    wb.close()
    if rows is None:
        return []

    ci_date = colmap.get("date")
    ci_desc = colmap.get("desc")
    ci_val = colmap.get("valor")
    ci_saldo = colmap.get("saldo")
    ci_liq = colmap.get("liq")
    ci_mov = colmap.get("mov")

    def cell(row, idx):
        return row[idx] if (idx is not None and idx < len(row)) else None

    movements: List[Dict[str, Any]] = []
    for row in rows[header_idx + 1:]:
        if row is None:
            continue
        mov_date = _to_date(cell(row, ci_date))
        desc = cell(row, ci_desc)
        valor = _to_decimal(cell(row, ci_val))
        if mov_date is None or desc is None or valor is None:
            continue
        desc = str(desc).strip()
        if not desc:
            continue

        cls = classify_movement(desc, valor)
        mov_code = cell(row, ci_mov)
        mov_code = str(mov_code).strip().upper() if mov_code is not None else None
        # Categoria DERIVADA do Lançamento (regra validada); MOV só como fallback
        # para eventuais lançamentos que a regra não cubra.
        category_id = cls["category_id"] or (MOV_TO_CATEGORY.get(mov_code) if mov_code else None)

        movements.append({
            "date": mov_date,
            "liquidation_date": _to_date(cell(row, ci_liq)),
            "description": desc,
            "amount": valor,
            "saldo": _to_decimal(cell(row, ci_saldo)),
            "mov": mov_code,
            **cls,
            "category_id": category_id,  # sobrescreve o do classify com o do MOV
        })

    return movements
