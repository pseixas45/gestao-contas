"""Passo 1 (exploratório): medir cobertura de match transacao->ativo.

Casa as transacoes das categorias Aplicacao(1) / Rendimento(21) / Resgate(22)
da conta XP corrente (id=9) contra os ativos que ja apareceram na carteira XP
(conta 11), usando o nome do ativo embutido na descricao.

NAO grava nada. Apenas relata matched/ambiguo/nao-casado por categoria.
"""
import sys
import re
import unicodedata
from decimal import Decimal
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.models import Asset, InvestmentPosition, InvestmentSnapshot, Transaction

CAT_NAMES = {1: "APLICACAO", 21: "RENDIMENTO", 22: "RESGATE"}


ABBREV = {"ADV": "ADVISORY", "CORPORA": "CORPORATIVAS", "IMOBI": "IMOBILIARIA"}


def norm(s: str) -> str:
    """Uppercase, sem acento, sem pontuacao (exceto espaco), espacos colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [ABBREV.get(t, t) for t in s.split()]
    return " ".join(toks)


# Ticker B3 (FII/acao): 4 letras + 1-2 digitos (ex: JGPI11, MCCE11, PETR38, TRPLB7)
TICKER_RE = re.compile(r"\b([A-Z]{4}\d{1,2})\b")

# Aliases ticker->asset_id p/ renda fixa cujo ticker NAO aparece no nome do ativo
# (mapeado manualmente a partir dos nao-casados; candidato a virar coluna Asset.ticker)
TICKER_ALIAS = {
    "PETR38": 36,   # DEB PETROBRAS - JUN/2045
    "TRPLB7": 41,   # DEB ISA ENERGIA (CTEEP) - OUT/2039
    "SIMH16": 29,   # DEB SIMPAR - DEZ/2032
    "ENAT32": 26,   # DEB ENAUTA - SET/2029
}


# Prefixos a remover da descricao para isolar o nome do ativo
PREFIXES = [
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

# Codigos/tickers a remover (aparecem antes do '|' ou logo apos prefixo)
CODE_RE = re.compile(r"\b([A-Z]{2,6}\d[A-Z0-9]*|\d{6,})\b")


def extract_candidate(desc: str) -> str:
    """Extrai a string do nome do ativo a partir da descricao."""
    raw = desc or ""
    # Caso "PREFIXO CODE | NOME": o nome limpo esta apos o '|'
    if "|" in raw:
        cand = raw.split("|", 1)[1]
        return norm(cand)
    u = norm(raw)
    # Caso "TED ... APLICACAO FUNDOS <nome>": nome fica no fim
    if "APLICACAO FUNDOS" in u:
        return u.split("APLICACAO FUNDOS", 1)[1].strip()
    # remover prefixo conhecido
    for p in PREFIXES:
        if u.startswith(p):
            u = u[len(p):].strip()
            break
    # remover codigo/ticker residual no inicio
    u = CODE_RE.sub(" ", u, count=1).strip() if CODE_RE.match(u) else u
    # remover numeros de conta no fim (ex: 4065643, 1912633)
    u = re.sub(r"\b\d{5,}\b", " ", u).strip()
    u = re.sub(r"\s+", " ", u).strip()
    return u


def score(cand: str, asset: str) -> float:
    """Score de similaridade cand x nome-do-ativo (ambos normalizados)."""
    if not cand or not asset:
        return 0.0
    if cand == asset:
        return 1000.0
    # prefixo (cobre nomes truncados no extrato)
    if asset.startswith(cand):
        return 500.0 + len(cand) / len(asset) * 100
    if cand.startswith(asset):
        return 500.0 + len(asset) / len(cand) * 100
    # overlap de tokens (Jaccard sobre tokens significativos)
    ct = set(cand.split())
    at = set(asset.split())
    if not ct or not at:
        return 0.0
    inter = ct & at
    return len(inter) / len(ct | at) * 100


def main():
    db = SessionLocal()
    # universo de ativos XP
    rows = (
        db.query(Asset.id, Asset.name)
        .join(InvestmentPosition, InvestmentPosition.asset_id == Asset.id)
        .join(InvestmentSnapshot, InvestmentSnapshot.id == InvestmentPosition.snapshot_id)
        .filter(InvestmentSnapshot.account_id == 11)
        .distinct()
        .all()
    )
    assets = [(aid, name, norm(name)) for aid, name in rows]

    # indice ticker -> asset_id (ticker embutido no nome, ex: JGPI11, MCCE11)
    ticker_idx = dict(TICKER_ALIAS)
    for aid, name, an in assets:
        m = TICKER_RE.search(an)
        if m:
            ticker_idx.setdefault(m.group(1), aid)
    asset_by_id = {aid: name for aid, name, _ in assets}

    def resolve(desc):
        """Retorna ('matched'|'ambiguo'|'nao', asset_name|opcoes, score/via)."""
        # 1) ticker explicito na descricao
        for tk in TICKER_RE.findall(norm(desc)):
            if tk in ticker_idx:
                return "matched", asset_by_id.get(ticker_idx[tk]), f"ticker:{tk}"
        # 2) nome
        cand = extract_candidate(desc)
        scored = sorted(((score(cand, an), aid, name) for aid, name, an in assets), reverse=True)
        top = scored[0] if scored else (0, None, None)
        ties = [s for s in scored if s[0] == top[0]]
        # aceita: prefixo forte (>=500) unico, OU token-overlap alto (>=50) unico
        if top[0] >= 500 and len(ties) == 1:
            return "matched", top[2], f"nome:{round(top[0],1)}"
        if len(ties) > 1 and top[0] >= 500:
            return "ambiguo", [t[2] for t in ties], cand
        if top[0] >= 50 and len(ties) == 1:
            return "matched", top[2], f"token:{round(top[0],1)}"
        return "nao", top[2], f"best={round(top[0],1)} cand={cand[:30]!r}"

    for cat in (1, 21, 22):
        txns = (
            db.query(Transaction.id, Transaction.date, Transaction.description, Transaction.amount_brl)
            .filter(Transaction.account_id == 9, Transaction.category_id == cat)
            .order_by(Transaction.date)
            .all()
        )
        matched = ambiguous = unmatched = 0
        val_matched = val_amb = val_unm = Decimal("0")
        unmatched_list = []
        ambiguous_list = []
        for tid, d, desc, amt in txns:
            amt = amt or Decimal("0")
            status, info, via = resolve(desc)
            if status == "matched":
                matched += 1
                val_matched += abs(amt)
            elif status == "ambiguo":
                ambiguous += 1
                val_amb += abs(amt)
                ambiguous_list.append((d, desc, via, info))
            else:
                unmatched += 1
                val_unm += abs(amt)
                unmatched_list.append((d, desc, via, "", info))

        tot = len(txns)
        print("=" * 70)
        print(f"CATEGORIA {cat} {CAT_NAMES[cat]} — {tot} transacoes")
        print(f"  matched : {matched:3d}  (R$ {val_matched:,.2f})")
        print(f"  ambiguo : {ambiguous:3d}  (R$ {val_amb:,.2f})")
        print(f"  NAO-cas.: {unmatched:3d}  (R$ {val_unm:,.2f})")
        if ambiguous_list:
            print("  --- AMBIGUOS ---")
            for d, desc, cand, opts in ambiguous_list[:20]:
                print(f"   {d} | {desc[:55]!r} -> cand={cand[:35]!r} :: {opts}")
        if unmatched_list:
            print("  --- NAO-CASADOS ---")
            for d, desc, cand, sc, best in unmatched_list[:40]:
                print(f"   {d} | {desc[:60]!r} -> cand={cand[:30]!r} (best={sc} {best!r})")
    db.close()


if __name__ == "__main__":
    main()
