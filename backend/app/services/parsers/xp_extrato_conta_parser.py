"""Parser do Extrato da Conta Corrente XP (movimentações de caixa da corretora).

Arquivo: "XP Extrato <conta> <periodo>.xlsx"
Aba única (Planilha1). Cabeçalho na linha 13 (0-based):
    Movimentação | Liquidação | Lançamento | (vazio) | Valor (R$) | Saldo (R$)
As colunas úteis (0-based na linha): 1=Movimentação, 2=Liquidação,
3=Lançamento(descrição), 5=Valor, 6=Saldo.

Ao contrário dos outros parsers XP (que geram snapshots de posição), este
gera uma lista de MOVIMENTAÇÕES para virar transações na conta XP corrente,
usada como fonte de dados para a análise de aplicações/resgates/rendimentos.
"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import openpyxl


# ------------------------------------------------------------------
# Classificação de movimentações -> categoria
# ------------------------------------------------------------------
# IDs de categoria (schema gestao_contas)
CAT_APLICACAO = 1
CAT_IMPOSTOS = 12
CAT_RENDIMENTO = 21
CAT_RESGATE = 22
CAT_TRANSFERENCIA = 30


def classify_movement(desc: str, valor: Decimal) -> Dict[str, Any]:
    """Classifica uma movimentação da conta XP.

    Retorna dict com:
      - kind: rótulo bruto do tipo (COMPRA, RESGATE, TED_APORTE, ...)
      - category_id: categoria sugerida
      - external: True se é fluxo que cruza a fronteira da corretora
                  (TED recebido/retirado) — usado no cálculo de rendimento.
      - flow: 'aporte' | 'resgate' | 'aplicacao' | 'rendimento' |
              'imposto' | 'outros'  (semântica para a análise)
    """
    d = (desc or "").strip().upper()
    pos = valor is not None and valor > 0

    def r(kind, cat, flow, external=False):
        return {"kind": kind, "category_id": cat, "flow": flow, "external": external}

    # --- TEDs (distinguir pelos sufixos) ---
    if d.startswith("TED"):
        if "RECEBIMENTO DE TED" in d:
            return r("TED_APORTE", CAT_TRANSFERENCIA, "aporte", external=True)
        if "RETIRADA EM C/C" in d:
            return r("TED_RETIRADA", CAT_TRANSFERENCIA, "resgate", external=True)
        if "APLICA" in d:  # TED ... APLICAÇÃO FUNDOS <nome> (saída p/ fundo externo)
            return r("TED_APLIC_FUNDO", CAT_APLICACAO, "aplicacao")
        # TED genérico
        return r("TED", CAT_TRANSFERENCIA, "aporte" if pos else "resgate", external=True)

    # --- Impostos ---
    if d.startswith("IRRF") or d.startswith("IOF") or d.startswith("IR -") or d.startswith("IR-"):
        return r("IMPOSTO", CAT_IMPOSTOS, "imposto")

    # --- Aplicações (saída de caixa p/ ativo) ---
    if d.startswith("COMPRA"):
        return r("COMPRA", CAT_APLICACAO, "aplicacao")
    if d.startswith("INTEGRALIZA"):
        return r("INTEGRALIZACAO", CAT_APLICACAO, "aplicacao")

    # --- Resgates (entrada de caixa vinda de ativo) ---
    if d.startswith("ADIANTAMENTO RESGATE"):
        return r("ADIANT_RESGATE", CAT_RESGATE, "resgate")
    if d.startswith("RESGATE"):
        return r("RESGATE", CAT_RESGATE, "resgate")

    # --- Rendimentos / proventos ---
    if d.startswith("RENDIMENTO"):
        return r("RENDIMENTO", CAT_RENDIMENTO, "rendimento")
    if d.startswith("PGTO JUROS") or d.startswith("PGTO AMORTIZA") or d.startswith("PGTO"):
        return r("PGTO_JUROS", CAT_RENDIMENTO, "rendimento")
    if d.startswith("AMORTIZA"):
        return r("AMORTIZACAO", CAT_RENDIMENTO, "rendimento")
    if d.startswith("INVESTBACK"):
        return r("INVESTBACK", CAT_RENDIMENTO, "rendimento")

    # --- Câmbio ---
    if d.startswith("CAMBIO") or d.startswith("CÂMBIO"):
        return r("CAMBIO", CAT_TRANSFERENCIA, "outros")

    # Fallback
    return r("OUTROS", CAT_TRANSFERENCIA, "outros")


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
    # formato brasileiro possível
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def parse_xp_extrato_conta(path: str) -> List[Dict[str, Any]]:
    """Lê o xlsx e retorna a lista de movimentações classificadas.

    Cada item: {date, liquidation_date, description, amount(Decimal, com sinal),
                saldo, kind, category_id, flow, external}
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # localizar linha de cabeçalho (contém "Movimentação" e "Lançamento")
    header_idx = None
    for i, row in enumerate(rows[:40]):
        joined = "|".join("" if c is None else str(c) for c in row).lower()
        if "movimenta" in joined and "lançamento" in joined.replace("ç", "ç"):
            header_idx = i
            break
        if "movimenta" in joined and "lancamento" in joined:
            header_idx = i
            break
    if header_idx is None:
        header_idx = 13  # fallback conhecido

    movements: List[Dict[str, Any]] = []
    for row in rows[header_idx + 1:]:
        if row is None:
            continue
        mov = _to_date(row[1]) if len(row) > 1 else None
        liq = _to_date(row[2]) if len(row) > 2 else None
        desc = row[3] if len(row) > 3 else None
        valor = _to_decimal(row[5]) if len(row) > 5 else None
        saldo = _to_decimal(row[6]) if len(row) > 6 else None

        # linha válida requer data de movimentação, descrição e valor numérico
        if mov is None or desc is None or valor is None:
            continue
        desc = str(desc).strip()
        if not desc:
            continue

        cls = classify_movement(desc, valor)
        movements.append({
            "date": mov,
            "liquidation_date": liq,
            "description": desc,
            "amount": valor,
            "saldo": saldo,
            **cls,
        })

    return movements
