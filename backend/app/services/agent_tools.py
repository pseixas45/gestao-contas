"""Ferramentas do agente de carga.

Cada ferramenta reusa os endpoints já testados via HTTP interno autenticado
(mesmo backend, com o token do usuário). Assim o agente executa exatamente o
mesmo fluxo de import/analyze/process/investimentos que foi validado.

Ferramentas de ESCRITA (processar_extrato, remover_transacao) exigem
`confirmado=True` — o agente deve analisar e propor primeiro, e só gravar após
o usuário confirmar explicitamente.
"""
import os
import re
from datetime import date
from typing import Any, Dict, Optional

import httpx

from app.config import settings


# Cache do column_mapping detectado por batch, preenchido em analisar_extrato e
# consumido em processar_extrato (mesmo processo). Evita trafegar o mapping
# (com acentos) pelo modelo.
_MAPPING_CACHE: Dict[int, Dict[str, Any]] = {}


def _account_is_credit_card(ctx: "ToolContext", account_id: int) -> bool:
    """True se a conta é cartão de crédito (exige data da fatura no import)."""
    for a in listar_contas(ctx):
        if a["id"] == account_id:
            return "credit" in str(a.get("tipo") or "").lower()
    return False


def _infer_fatura_date(filename: str) -> Optional[str]:
    """Infere a data da fatura a partir do nome do arquivo (ISO yyyy-mm-dd).

    Os extratos de cartão trazem a data no nome: "Visa 260906" (YYMMDD →
    2026-09-06), "XPVisa 260905", "C6 Master 261010", "Master 261020 - 261007"
    (usa o 1º token, o vencimento → 2026-10-20), "Visa fatura-20260606"
    (YYYYMMDD). Retorna None se não achar um token de data plausível — nesse caso
    o agente deve pedir/confirmar a data com o usuário.
    """
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", filename)  # YYYYMMDD
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"\b(\d{2})(\d{2})(\d{2})\b", filename)  # YYMMDD
        if not m:
            return None
        y, mo, d = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


class ToolContext:
    """Contexto de execução: token do usuário + URLs."""

    def __init__(self, token: str, base_url: Optional[str] = None, extratos_dir: Optional[str] = None):
        self.token = token
        base = (base_url or settings.INTERNAL_BASE_URL).rstrip("/")
        self.api = base + "/api/v1"
        self.extratos_dir = extratos_dir or settings.EXTRATOS_DIR

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=180,
        )

    def resolve(self, arquivo: str) -> Optional[str]:
        if not self.extratos_dir:
            return None
        p = os.path.join(self.extratos_dir, arquivo)
        return p if os.path.isfile(p) else None


# ============================================================
# Ferramentas (leitura)
# ============================================================

def listar_contas(ctx: ToolContext) -> Any:
    with ctx.client() as c:
        r = c.get("/accounts")
        r.raise_for_status()
        return [
            {
                "id": a["id"], "nome": a["name"], "tipo": a.get("account_type"),
                "moeda": a.get("currency"), "saldo": a.get("current_balance"),
            }
            for a in r.json()
        ]


def achar_arquivo(ctx: ToolContext, nome: str) -> Any:
    d = ctx.extratos_dir
    if not d or not os.path.isdir(d):
        return {"erro": f"Pasta de extratos não configurada ou inexistente (EXTRATOS_DIR={d!r})"}
    matches = sorted(f for f in os.listdir(d) if nome.lower() in f.lower() and not f.startswith("~$"))
    return {"pasta": d, "encontrados": matches}


def saldo_conta(ctx: ToolContext, account_id: int) -> Any:
    for a in listar_contas(ctx):
        if a["id"] == account_id:
            return {"account_id": account_id, "nome": a["nome"], "saldo": a["saldo"]}
    return {"erro": f"Conta {account_id} não encontrada"}


def buscar_transacoes(ctx: ToolContext, account_id: int, data: Optional[str] = None,
                      valor: Optional[float] = None) -> Any:
    """Busca transações de uma conta (para reconciliação/achar duplicatas)."""
    params: Dict[str, Any] = {"account_id": account_id, "limit": 100}
    if data:
        params["start_date"] = data
        params["end_date"] = data
    if valor is not None:
        params["min_amount"] = valor
        params["max_amount"] = valor
    with ctx.client() as c:
        r = c.get("/transactions", params=params)
        r.raise_for_status()
        body = r.json()
        items = body.get("transactions", body) if isinstance(body, dict) else body
        return [
            {"id": t["id"], "data": t["date"], "valor": t.get("original_amount", t.get("amount")),
             "descricao": t.get("description"), "batch": t.get("import_batch_id")}
            for t in (items or [])
        ]


# ============================================================
# Ferramentas (extratos)
# ============================================================

def analisar_extrato(ctx: ToolContext, arquivo: str, account_id: int,
                     card_payment_date: Optional[str] = None,
                     coluna_valor: Optional[str] = None) -> Any:
    """Dry-run: sobe o arquivo e analisa (novas/duplicatas/erros + validação de saldo). NÃO grava."""
    path = ctx.resolve(arquivo)
    if not path:
        return {"erro": f"Arquivo não encontrado em {ctx.extratos_dir!r}: {arquivo}"}

    # Cartão de crédito EXIGE a data da fatura (card_payment_date). Nenhum extrato
    # de cartão traz essa data como coluna, então ou o agente a informa, ou nós a
    # inferimos do nome do arquivo. Sem ela, a transação fica sem fatura.
    is_card = _account_is_credit_card(ctx, account_id)
    cpd_inferida = None
    if is_card and not card_payment_date:
        card_payment_date = cpd_inferida = _infer_fatura_date(arquivo)

    with ctx.client() as c:
        with open(path, "rb") as fh:
            up = c.post("/imports/upload", files={"file": (arquivo, fh, "application/octet-stream")},
                        data={"account_id": str(account_id)})
        if up.status_code != 200:
            return {"erro": f"upload falhou ({up.status_code}): {up.text[:300]}"}
        preview = up.json()
        m = preview["detected_mapping"]
        if coluna_valor:  # override (ex: C6 Master -> 'Valor (em R$)')
            m["amount_column"] = coluna_valor
            m["valor_brl_column"] = None
            m["valor_usd_column"] = None
        body: Dict[str, Any] = {
            "batch_id": preview["batch_id"], "column_mapping": m, "account_id": account_id,
            "validate_balance": False, "skip_duplicates": True,
        }
        if card_payment_date:
            body["card_payment_date"] = card_payment_date
        an = c.post("/imports/analyze", json=body)
        if an.status_code != 200:
            return {"erro": f"analyze falhou ({an.status_code}): {an.text[:300]}"}
        d = an.json()
        _MAPPING_CACHE[preview["batch_id"]] = {
            "mapping": m, "card_payment_date": card_payment_date, "is_card": is_card,
        }
        out = {
            "batch_id": preview["batch_id"],
            "coluna_valor_usada": m.get("amount_column"),
            "novas": d["new_count"], "duplicatas": d["duplicate_count"], "erros": d["error_count"],
            "periodo": [d.get("date_range_start"), d.get("date_range_end")],
            "soma_novas": d.get("calculated_total"),
            "saldo_bate": d.get("balance_will_match"),
            "detalhe_saldo": d.get("balance_check_detail"),
            "saldo_final_extrato": d.get("statement_final_balance"),
        }
        if is_card:
            out["cartao"] = True
            out["data_fatura"] = card_payment_date
            if cpd_inferida:
                out["data_fatura_origem"] = "inferida do nome do arquivo"
            if not card_payment_date:
                out["aviso"] = ("CARTÃO SEM DATA DA FATURA: não consegui inferir do nome do "
                                "arquivo. Confirme com o usuário e rode de novo com "
                                "card_payment_date=YYYY-MM-DD antes de processar.")
        return out


def processar_extrato(ctx: ToolContext, batch_id: int, account_id: int,
                      confirmado: bool = False, card_payment_date: Optional[str] = None) -> Any:
    """GRAVA o import de um batch já analisado (use o batch_id da última analisar_extrato). Requer confirmado=True."""
    if not confirmado:
        return {"status": "confirmacao_necessaria",
                "aviso": "Ferramenta de escrita — só chame com confirmado=true após o usuário confirmar."}
    cached = _MAPPING_CACHE.get(batch_id)
    if not cached:
        return {"erro": f"Sem análise em cache para o batch {batch_id}. "
                        "Rode analisar_extrato imediatamente antes de processar."}
    mapping = dict(cached["mapping"])
    cpd = card_payment_date or cached.get("card_payment_date")
    # Guardrail: cartão de crédito não pode ser gravado sem a data da fatura.
    if cached.get("is_card") and not cpd:
        return {"erro": "Cartão de crédito exige a data da fatura. Rode analisar_extrato "
                        "novamente com card_payment_date=YYYY-MM-DD (infira do nome do "
                        "arquivo, ex: 'Visa 260906' → 2026-09-06, ou pergunte ao usuário)."}
    with ctx.client() as c:
        body: Dict[str, Any] = {
            "batch_id": batch_id, "column_mapping": mapping, "account_id": account_id,
            "validate_balance": False, "skip_duplicates": True,
        }
        if cpd:
            body["card_payment_date"] = cpd
        pr = c.post("/imports/process", json=body)
        if pr.status_code != 200:
            return {"erro": f"process falhou ({pr.status_code}): {pr.text[:300]}"}
        res = pr.json()
        novo_saldo = saldo_conta(ctx, account_id).get("saldo")
        return {"importadas": res.get("imported_count"), "duplicatas": res.get("duplicate_count"),
                "erros": res.get("error_count"), "novo_saldo": novo_saldo}


def upload_investimento(ctx: ToolContext, arquivo: str, account_id: int, provider: str = "auto") -> Any:
    """Sobe snapshot de investimento (PDF/xlsx de posição). Grava direto (idempotente por data)."""
    path = ctx.resolve(arquivo)
    if not path:
        return {"erro": f"Arquivo não encontrado em {ctx.extratos_dir!r}: {arquivo}"}
    with ctx.client() as c:
        with open(path, "rb") as fh:
            r = c.post("/investments/upload",
                       files={"file": (arquivo, fh, "application/octet-stream")},
                       data={"account_id": str(account_id), "provider": provider})
        if r.status_code != 200:
            return {"erro": f"upload investimento falhou ({r.status_code}): {r.text[:300]}"}
        d = r.json()
        return {"data": d.get("snapshot_date"), "posicoes": d.get("positions_count"),
                "total": d.get("total_value")}


def remover_transacao(ctx: ToolContext, transaction_id: int, confirmado: bool = False) -> Any:
    """Remove UMA transação (ex: duplicata na reconciliação). Requer confirmado=True."""
    if not confirmado:
        return {"status": "confirmacao_necessaria",
                "aviso": "Ferramenta de escrita — só chame com confirmado=true após o usuário confirmar."}
    with ctx.client() as c:
        r = c.delete(f"/transactions/{transaction_id}")
        if r.status_code not in (200, 204):
            return {"erro": f"delete falhou ({r.status_code}): {r.text[:200]}"}
        return {"removida": transaction_id, "ok": True}
