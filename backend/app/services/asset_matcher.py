"""Casa lançamentos (transações) a ativos de investimento pelo texto da descrição.

Usado para vincular pagamentos de Rendimento (cupons/amortizações), Aplicações e
Resgates ao ativo específico que os originou — base da análise de rentabilidade
por ativo.

Estratégia (em ordem de confiança):
  1. Ticker B3 na descrição (JGPI11, MCCE11, PETR38...) casando com o ticker do
     ativo (embutido no nome ou via TICKER_ALIAS).
  2. Nome do ativo: quando a descrição traz "PREFIXO CODE | NOME", o nome limpo
     está após o '|'; senão, remove-se o prefixo conhecido. Casa por prefixo forte.
  3. Sobreposição de tokens (fallback de baixa confiança) — NÃO auto-atribuído.

Confiança:
  - "high": ticker ou prefixo forte único  -> pode ser gravado automaticamente.
  - "low" : só sobreposição de tokens       -> vira sugestão p/ revisão manual.
  - "ambiguous": empate no topo (ex.: 2 lotes NTN-B) -> revisão manual.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Abreviações que aparecem no extrato vs nome cadastrado do ativo
ABBREV = {"ADV": "ADVISORY", "CORPORA": "CORPORATIVAS", "IMOBI": "IMOBILIARIA"}

# Ticker B3 (FII/ação): 4 letras + 1-2 dígitos (JGPI11, MCCE11, PETR38, TRPLB7)
TICKER_RE = re.compile(r"\b([A-Z]{4}\d{1,2})\b")

# Aliases ticker -> asset_id para renda fixa cujo ticker NÃO aparece no nome.
# Ponto de manutenção: acrescente aqui quando surgir um papel novo com ticker
# próprio no extrato mas nome sem o código.
TICKER_ALIAS: Dict[str, int] = {
    "PETR38": 36,   # DEB PETROBRAS - JUN/2045
    "TRPLB7": 41,   # DEB ISA ENERGIA (CTEEP) - OUT/2039
    "SIMH16": 29,   # DEB SIMPAR - DEZ/2032
    "ENAT32": 26,   # DEB ENAUTA - SET/2029
}

# Prefixos a remover da descrição para isolar o nome do ativo
_PREFIXES = [
    "RENDIMENTO FUNDO FECHADO BALCAO",
    "AMORTIZACAO DE FUNDO",
    "PGTO AMORTIZACAO",
    "PGTO JUROS",
    "COMPRA DE CESSAO DE COTAS",
    "INTEGRALIZACAO DE COTAS CETIP",
    "IRRF S RESGATE FUNDOS",
    "IOF S RESGATE FUNDOS",
    "ADIANTAMENTO RESGATE",
    "COMPRA",
    "RESGATE",
]

_CODE_RE = re.compile(r"\b([A-Z]{2,6}\d[A-Z0-9]*|\d{6,})\b")


def normalize(s: str) -> str:
    """Uppercase, sem acento, sem pontuação, espaços colapsados, abreviações expandidas."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(ABBREV.get(t, t) for t in s.split())


def _extract_name_candidate(desc: str) -> str:
    """Extrai a parte da descrição que representa o nome do ativo."""
    raw = desc or ""
    if "|" in raw:
        return normalize(raw.split("|", 1)[1])
    u = normalize(raw)
    if "APLICACAO FUNDOS" in u:                      # "TED ... APLICACAO FUNDOS <nome>"
        return u.split("APLICACAO FUNDOS", 1)[1].strip()
    for p in _PREFIXES:
        if u.startswith(p):
            u = u[len(p):].strip()
            break
    if _CODE_RE.match(u):
        u = _CODE_RE.sub(" ", u, count=1).strip()
    u = re.sub(r"\b\d{5,}\b", " ", u).strip()        # nº de conta residual
    return re.sub(r"\s+", " ", u).strip()


def _score(cand: str, asset_norm: str) -> float:
    if not cand or not asset_norm:
        return 0.0
    if cand == asset_norm:
        return 1000.0
    if asset_norm.startswith(cand):
        return 500.0 + len(cand) / len(asset_norm) * 100
    if cand.startswith(asset_norm):
        return 500.0 + len(asset_norm) / len(cand) * 100
    ct, at = set(cand.split()), set(asset_norm.split())
    if not ct or not at:
        return 0.0
    return len(ct & at) / len(ct | at) * 100


@dataclass
class MatchResult:
    asset_id: Optional[int]
    asset_name: Optional[str]
    confidence: str   # "high" | "low" | "ambiguous" | "none"
    method: str       # "ticker:XXX" | "name:score" | "token:score" | "none"
    candidates: Optional[List[int]] = None  # em caso de ambiguidade


class AssetMatcher:
    """Constrói índices a partir de um universo de ativos e casa descrições."""

    # limiares
    PREFIX_MIN = 500.0
    TOKEN_MIN = 50.0

    def __init__(self, assets: List[Tuple[int, str]]):
        # assets: lista de (asset_id, name)
        self.assets = [(aid, name, normalize(name)) for aid, name in assets]
        self.name_by_id = {aid: name for aid, name, _ in self.assets}
        # índice ticker -> asset_id (ticker embutido no nome + aliases)
        self.ticker_idx: Dict[int, int] = {}
        self.ticker_idx = dict(TICKER_ALIAS)
        for aid, name, an in self.assets:
            m = TICKER_RE.search(an)
            if m:
                self.ticker_idx.setdefault(m.group(1), aid)

    def match(self, description: str) -> MatchResult:
        # 1) ticker explícito na descrição
        for tk in TICKER_RE.findall(normalize(description)):
            if tk in self.ticker_idx:
                aid = self.ticker_idx[tk]
                return MatchResult(aid, self.name_by_id.get(aid), "high", f"ticker:{tk}")
        # 2/3) nome
        cand = _extract_name_candidate(description)
        scored = sorted(
            ((_score(cand, an), aid, name) for aid, name, an in self.assets),
            key=lambda t: t[0], reverse=True,
        )
        if not scored:
            return MatchResult(None, None, "none", "none")
        top = scored[0]
        ties = [s for s in scored if s[0] == top[0]]
        if top[0] >= self.PREFIX_MIN:
            if len(ties) == 1:
                return MatchResult(top[1], top[2], "high", f"name:{round(top[0],1)}")
            return MatchResult(None, None, "ambiguous", f"name:{round(top[0],1)}",
                               candidates=[t[1] for t in ties])
        if top[0] >= self.TOKEN_MIN and len(ties) == 1:
            return MatchResult(top[1], top[2], "low", f"token:{round(top[0],1)}")
        return MatchResult(None, None, "none", f"best:{round(top[0],1)}")
