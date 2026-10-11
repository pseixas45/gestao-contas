"""
Normalização e detecção de duplicados para importação de transações.

Funções centralizadas usadas por todos os caminhos de importação
(conta única e bulk) para garantir detecção consistente de duplicados.
"""

import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_


# Padrões bancários que variam entre exports do mesmo banco
BANK_PATTERN_NORMALIZATIONS = [
    (r'\bCOMPRA\s+NO\s+CARTAO\b', 'COMPRA CARTAO'),
    (r'\bCOMPRA\s+CARTAO\s+DEBITO\b', 'COMPRA CARTAO'),
    (r'\bPGTO\s+DEBITO\s+CONTA\b', 'PGTO DEBITO'),
    (r'\bPAGAMENTO\s+DEBITO\b', 'PGTO DEBITO'),
    (r'\bPAGAMENTO\s+DE\s+BOLETO\b', 'PGTO BOLETO'),
    (r'\bPGTO\s+BOLETO\b', 'PGTO BOLETO'),
    (r'\bPIX\s+RECEBIDO\b', 'PIX RECEBIDO'),
    (r'\bPIX\s+REC\b', 'PIX RECEBIDO'),
    (r'\bPIX\s+ENVIADO\b', 'PIX ENVIADO'),
    (r'\bPIX\s+ENV\b', 'PIX ENVIADO'),
    (r'\bPIX\s+TRANSF\b', 'PIX ENVIADO'),
    (r'\bTRANSF\s+RECEB\w*\b', 'TRANSF RECEBIDA'),
    (r'\bTRANSF\s+ENVI\w*\b', 'TRANSF ENVIADA'),
    (r'\bTED\s+RECEB\w*\b', 'TED RECEBIDA'),
    (r'\bTED\s+ENVI\w*\b', 'TED ENVIADA'),
    (r'\bDEB\s+AUTOMATICO\b', 'DEB AUTOMATICO'),
    (r'\bDEBITO\s+AUTOMATICO\b', 'DEB AUTOMATICO'),
    (r'\bDEB\s+AUT\b', 'DEB AUTOMATICO'),
]


def normalize_for_hash(description: str) -> str:
    """
    Normalização canônica para hash de deduplicação.

    Determinística e irreversível - projetada para maximizar colisão
    de transações equivalentes (mesma transação, formatos diferentes).

    Passos:
    1. Uppercase
    2. Remover acentos (NFKD)
    3. Remover pontuação (manter alfanuméricos, espaços, /, -)
    4. Normalizar padrões bancários
    5. Remover números de referência no final (6+ dígitos)
    6. Colapsar espaços
    """
    if not description:
        return ""

    text = description.strip().upper()

    # Remover acentos via decomposição Unicode
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    # Remover pontuação, manter alfanuméricos, espaços, / e -
    text = re.sub(r'[^\w\s/\-]', ' ', text)

    # Normalizar padrões bancários comuns
    for pattern, replacement in BANK_PATTERN_NORMALIZATIONS:
        text = re.sub(pattern, replacement, text)

    # Canonicalizar marcador de parcela no final para casar formatos diferentes
    # do mesmo banco (CSV "01/02" ou "RA01/03" vs XLSX "1 DE 2") preservando o
    # NÚMERO da parcela: parcela 1 e parcela 2 continuam distintas ("1/10" != "2/10").
    def _canon_parc(m):
        return f" {int(m.group(1))}/{int(m.group(2))}"
    text = re.sub(r'(\d{1,2})\s+DE\s+(\d{1,2})\s*$', _canon_parc, text)   # "1 DE 2" -> " 1/2"
    text = re.sub(r'(\d{1,2})\s*/\s*(\d{1,2})\s*$', _canon_parc, text)     # "01/02","RA01/03" -> " 1/2"

    # Remover números de referência longos no final (6+ dígitos)
    text = re.sub(r'\s+\d{6,}\s*$', '', text)

    # Colapsar espaços
    text = ' '.join(text.split())

    return text


def format_amount_for_hash(amount: Decimal) -> str:
    """
    Formata valor para hash usando Decimal (sem erros de float).
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Similaridade baseada em tokens (Jaccard).
    Retorna valor entre 0.0 e 1.0.
    """
    if text1 == text2:
        return 1.0

    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union)


def _core_tokens(normalized: str) -> set:
    """Tokens significativos, ignorando números de referência puros.

    Bancos (ex: débito automático Itaú) anexam o nº do beneficiário/convênio no
    fim da descrição, e esse número varia/é truncado entre exports ("DA CLARO
    CELULAR 52988" vs "DA CLARO CELULAR 5"; "DA ELETROPAULO 08334046" vs
    "DA ELETROPAULO 0833"). Tokens puramente numéricos são descartados para a
    comparação fuzzy — a data (±1), o valor exato e a moeda já ancoram a
    identidade da transação. Marcadores de parcela ("1/2") contêm "/" e NÃO são
    puramente numéricos, então permanecem (parcelas distintas continuam distintas).
    """
    return {t for t in normalized.split() if not t.isdigit()}


def _token_matches(token: str, token_set: set) -> bool:
    """Um token casa com algum do conjunto: igual, OU um é prefixo do outro
    (ambos >= 4 chars). O prefixo cobre truncamento entre formatos do mesmo banco
    (ex: "INTERNACIONA" ~ "INTERNACIONAL", "EDUCACAO" ~ "EDUC"). O piso de 4 chars
    evita casar marcadores curtos/genéricos (parcela "1/3" vs "2/3" não casa).
    """
    for u in token_set:
        if token == u:
            return True
        if len(token) >= 4 and len(u) >= 4 and (u.startswith(token) or token.startswith(u)):
            return True
    return False


def _containment_score(core_a: set, core_b: set) -> float:
    """Fração dos tokens do MENOR conjunto que casam (igual ou prefixo) no maior.

    Robusto a tokens EXTRA em um dos lados — tipicamente o local do
    estabelecimento que a fatura de cartão anexa à descrição em alguns formatos
    ("Netflix.com" vs "Netflix.com Sao Paulo Br"; "Twilio Inc" vs
    "Twilio Inc Www.twilio.co Us"). Como data (±1), valor exato e moeda já ancoram
    a transação, se o nome do estabelecimento (conjunto menor) está contido no
    outro, é a mesma compra.

    Guarda contra falso-positivo: um único token só pontua se for distintivo
    (>= 6 chars) — evita casar descrições genéricas de 1 palavra (ex: "PIX").
    """
    if not core_a or not core_b:
        return 0.0
    small, large = (core_a, core_b) if len(core_a) <= len(core_b) else (core_b, core_a)
    if len(small) == 1 and len(next(iter(small))) < 6:
        return 0.0
    matched = sum(1 for t in small if _token_matches(t, large))
    return matched / len(small)


def description_similarity(desc_a: str, desc_b: str) -> float:
    """Similaridade entre duas descrições para deduplicação fuzzy.

    Retorna o maior entre três sinais (todos robustos a variações de formato do
    mesmo banco, com data/valor/moeda já ancorando a transação):
    - Jaccard sobre a descrição normalizada completa;
    - Jaccard sobre os tokens significativos (sem nº de referência puros,
      ver [_core_tokens]); e
    - Contenção de tokens (ver [_containment_score]) — cobre local do
      estabelecimento anexado e truncamento de palavras entre formatos.
    """
    na = normalize_for_hash(desc_a)
    nb = normalize_for_hash(desc_b)
    raw = calculate_similarity(na, nb)

    core_a = _core_tokens(na)
    core_b = _core_tokens(nb)
    if not core_a or not core_b:
        return raw

    inter = core_a & core_b
    union = core_a | core_b
    core_sim = len(inter) / len(union)
    containment = _containment_score(core_a, core_b)
    return max(raw, core_sim, containment)


def find_near_duplicate(
    db: Session,
    account_id: int,
    trans_date: date,
    amount: Decimal,
    currency_str: str,
    description: str,
    exclude_id: Optional[int] = None,
    card_payment_date: Optional[date] = None,
) -> Optional[object]:
    """
    Layer 2: Busca duplicados fuzzy.

    Procura transações no mesmo conta com:
    - Data dentro de ±1 dia
    - Mesmo valor exato (mesma moeda)
    - Descrição normalizada com similaridade >= 85%
    - card_payment_date compatível (se fornecido)

    Retorna a transação existente ou None.
    """
    # Import local para evitar circular
    from app.models import Transaction
    from app.models.exchange_rate import CurrencyCode

    date_start = trans_date - timedelta(days=1)
    date_end = trans_date + timedelta(days=1)

    # Converter para Decimal para comparação exata
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    # Query por candidatos: mesma conta, data ±1 dia, mesmo valor, mesma moeda
    query = db.query(Transaction).filter(
        Transaction.account_id == account_id,
        Transaction.date.between(date_start, date_end),
        Transaction.original_amount == amount,
        Transaction.original_currency == currency_str,
    )

    if exclude_id:
        query = query.filter(Transaction.id != exclude_id)

    candidates = query.all()

    if not candidates:
        return None

    # Comparar descrições (robusto a nº de referência variáveis entre exports)
    for candidate in candidates:
        similarity = description_similarity(description, candidate.description)
        if similarity >= 0.85:
            # Se ambos têm card_payment_date, devem ser compatíveis (±1 dia)
            if card_payment_date and candidate.card_payment_date:
                cpd_diff = abs((card_payment_date - candidate.card_payment_date).days)
                if cpd_diff > 1:
                    continue  # Datas de pagamento diferentes = transações diferentes
            return candidate

    return None
