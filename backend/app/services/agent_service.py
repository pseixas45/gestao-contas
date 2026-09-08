"""Loop conversacional do agente de carga (Claude + tool use).

Histórico trafega como texto simples (stateless-friendly). Dentro de um turno,
o agente encadeia ferramentas via loop manual. O mapping detectado fica em cache
server-side (agent_tools._MAPPING_CACHE), então a confirmação em turno seguinte
funciona desde que o agente cite o batch_id no texto.
"""
import json
from typing import Any, Dict, List

from app.config import settings
from app.services import agent_tools as T
from app.services.agent_tools import ToolContext

# ============================================================
# Definição das ferramentas expostas ao modelo
# ============================================================

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "listar_contas",
        "description": "Lista todas as contas (id, nome, tipo, moeda, saldo atual).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "achar_arquivo",
        "description": "Procura arquivos de extrato na pasta de extratos por parte do nome.",
        "input_schema": {
            "type": "object",
            "properties": {"nome": {"type": "string", "description": "Parte do nome do arquivo, ex: 'Itau 260706'"}},
            "required": ["nome"],
        },
    },
    {
        "name": "saldo_conta",
        "description": "Retorna o saldo atual de uma conta pelo id.",
        "input_schema": {
            "type": "object",
            "properties": {"account_id": {"type": "integer"}},
            "required": ["account_id"],
        },
    },
    {
        "name": "buscar_transacoes",
        "description": "Busca transações de uma conta (filtra por data e/ou valor) para reconciliar/achar duplicatas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer"},
                "data": {"type": "string", "description": "AAAA-MM-DD (opcional)"},
                "valor": {"type": "number", "description": "valor exato em original_amount (opcional)"},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "analisar_extrato",
        "description": "Dry-run: sobe o arquivo e analisa (novas/duplicatas/erros, período, validação de saldo). NÃO grava. Retorna batch_id para o processar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "arquivo": {"type": "string"},
                "account_id": {"type": "integer"},
                "card_payment_date": {"type": "string", "description": "AAAA-MM-DD, só para cartão quando aplicável"},
                "coluna_valor": {"type": "string", "description": "override da coluna de valor (ex: 'Valor (em R$)' no C6 Master)"},
            },
            "required": ["arquivo", "account_id"],
        },
    },
    {
        "name": "processar_extrato",
        "description": "GRAVA o import de um batch já analisado. Use o batch_id retornado pela última analisar_extrato. ESCRITA — só com confirmado=true após o usuário confirmar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "account_id": {"type": "integer"},
                "confirmado": {"type": "boolean"},
                "card_payment_date": {"type": "string"},
            },
            "required": ["batch_id", "account_id", "confirmado"],
        },
    },
    {
        "name": "upload_investimento",
        "description": "Sobe snapshot de investimento (PDF/xlsx de posição) para uma conta investment. Idempotente por data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "arquivo": {"type": "string"},
                "account_id": {"type": "integer"},
                "provider": {"type": "string", "enum": ["auto", "xp", "itau", "c6"]},
            },
            "required": ["arquivo", "account_id"],
        },
    },
    {
        "name": "remover_transacao",
        "description": "Remove UMA transação pelo id (ex: duplicata na reconciliação). ESCRITA — só com confirmado=true após o usuário confirmar.",
        "input_schema": {
            "type": "object",
            "properties": {"transaction_id": {"type": "integer"}, "confirmado": {"type": "boolean"}},
            "required": ["transaction_id", "confirmado"],
        },
    },
]

_DISPATCH = {
    "listar_contas": T.listar_contas,
    "achar_arquivo": T.achar_arquivo,
    "saldo_conta": T.saldo_conta,
    "buscar_transacoes": T.buscar_transacoes,
    "analisar_extrato": T.analisar_extrato,
    "processar_extrato": T.processar_extrato,
    "upload_investimento": T.upload_investimento,
    "remover_transacao": T.remover_transacao,
}

SYSTEM = """Você é o agente de carga do sistema Gestão de Contas. Você conversa em português e carrega extratos/faturas/investimentos conforme o usuário pede, reconciliando o saldo.

Fluxo padrão para extratos e faturas:
1. Identifique a conta (use listar_contas) e o arquivo (use achar_arquivo).
2. Rode analisar_extrato (dry-run) — mostra novas/duplicatas/erros, período e validação de saldo. NÃO grava.
3. Apresente o resultado ao usuário e, se ele informou um saldo-alvo, compare com o projetado.
4. Só depois que o usuário CONFIRMAR explicitamente ("sim", "confirmo", "pode gravar"), chame processar_extrato com confirmado=true, usando o batch_id da última análise. SEMPRE cite o batch_id no seu texto ao propor, para poder retomá-lo.
5. Após gravar, informe o saldo final e compare com o alvo.

Regras de domínio:
- Conta corrente: o extrato traz saldo por linha; a validação (saldo_bate/detalhe_saldo) reconcilia sozinha.
- Cartão de crédito: o saldo do cartão = total da fatura aberta; o sinal é invertido automaticamente na importação; parcela cai no mês da compra.
- Investimentos (contas do tipo investment): NÃO use analisar/processar — use upload_investimento (o total vem do próprio arquivo/snapshot).
- C6 Master (.xlsx): a auto-detecção pega a coluna errada; passe coluna_valor="Valor (em R$)".
- XP Visa: não use card_payment_date.
- Se o saldo divergir do alvo, investigue com buscar_transacoes (mesma data+valor) para achar duplicata; proponha remover_transacao e só remova com confirmado=true após o usuário aprovar.

NUNCA chame ferramentas de escrita (processar_extrato, remover_transacao) com confirmado=true sem o usuário ter confirmado na mensagem mais recente. Seja conciso e direto; mostre números (saldo antes/depois, novas, duplicatas)."""


def run_chat(history: List[Dict[str, str]], token: str, max_steps: int = 12) -> Dict[str, Any]:
    """Roda um turno do agente. history = [{role:'user'|'assistant', content: str}]."""
    import anthropic

    if not settings.ANTHROPIC_API_KEY:
        return {"reply": "⚠️ ANTHROPIC_API_KEY não configurada no backend. Configure no .env para usar o agente.",
                "tool_log": []}

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    ctx = ToolContext(token=token)

    messages: List[Dict[str, Any]] = [{"role": m["role"], "content": m["content"]} for m in history]
    tool_log: List[Dict[str, Any]] = []

    steps = 0
    resp = None
    while steps < max_steps:
        steps += 1
        resp = client.messages.create(
            model=settings.AGENT_MODEL,
            max_tokens=8000,
            system=SYSTEM,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            func = _DISPATCH.get(block.name)
            try:
                out = func(ctx, **block.input) if func else {"erro": f"ferramenta desconhecida: {block.name}"}
            except Exception as e:  # noqa: BLE001
                out = {"erro": f"{type(e).__name__}: {e}"}
            tool_log.append({"ferramenta": block.name, "args": block.input, "resultado": out})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(out, ensure_ascii=False, default=str),
            })
        messages.append({"role": "user", "content": results})

    reply = "".join(b.text for b in (resp.content if resp else []) if getattr(b, "type", None) == "text")
    return {"reply": reply or "(sem resposta)", "tool_log": tool_log}
