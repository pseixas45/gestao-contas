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

    # Comparar descrições normalizadas
    normalized_new = normalize_for_hash(description)

    for candidate in candidates:
        normalized_existing = normalize_for_hash(candidate.description)
        similarity = calculate_similarity(normalized_new, normalized_existing)
        if similarity >= 0.85:
            # Se ambos têm card_payment_date, devem ser compatíveis (±1 dia)
            if card_payment_date and candidate.card_payment_date:
                cpd_diff = abs((card_payment_date - candidate.card_payment_date).days)
                if cpd_diff > 1:
                    continue  # Datas de pagamento diferentes = transações diferentes
            return candidate

    return None
