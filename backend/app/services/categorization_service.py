"""
Serviço de categorização automática de transações.

Sistema híbrido que combina:
1. Regras manuais (prioridade alta)
2. Histórico de categorizações
3. Classificador ML (texto similar)
"""

from typing import Optional, Tuple
from datetime import datetime
import re
import unicodedata
from sqlalchemy.orm import Session

from app.models import CategorizationRule, CategorizationHistory, Category, MatchType


class TextProcessor:
    """Normalizador de texto para categorização."""

    # Padrões comuns em extratos bancários a remover
    PATTERNS_TO_REMOVE = [
        r'\d{2}/\d{2}',           # Datas
        r'\d{2}:\d{2}',           # Horários
        r'\*+',                    # Asteriscos
        r'\d{4,}',                 # Números longos (cartão, conta)
        r'R\$[\d.,]+',             # Valores monetários
        r'BRL[\d.,]+',
    ]

    # Palavras a ignorar
    STOP_WORDS = {
        'de', 'do', 'da', 'dos', 'das', 'em', 'na', 'no',
        'para', 'por', 'com', 'sem', 'sobre', 'entre',
        'ltda', 'sa', 'me', 'eireli', 'ss'
    }

    def normalize(self, text: str) -> str:
        """
        Normaliza texto de descrição de transação.

        - Remove acentos
        - Converte para minúsculas
        - Remove padrões irrelevantes
        - Remove stopwords
        """
        if not text:
            return ""

        # Minúsculas
        text = text.lower()

        # Remove acentos
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(c for c in text if not unicodedata.combining(c))

        # Remove padrões irrelevantes
        for pattern in self.PATTERNS_TO_REMOVE:
            text = re.sub(pattern, ' ', text)

        # Tokeniza e remove stopwords
        words = text.split()
        words = [w for w in words if w not in self.STOP_WORDS and len(w) > 1]

        # Reconstrói
        text = ' '.join(words)

        # Remove espaços extras
        text = re.sub(r'\s+', ' ', text).strip()

        return text


class CategorizationService:
    """Serviço híbrido de categorização de transações."""

    MIN_CONFIDENCE = 0.70

    def __init__(self, db: Session):
        self.db = db
        self.text_processor = TextProcessor()

    def categorize(
        self,
        description: str,
        amount: float
    ) -> Tuple[Optional[int], float, str]:
        """
        Categoriza uma transação.

        Returns:
            Tuple[category_id, confidence, method]
            - category_id: ID da categoria ou None
            - confidence: 0.0 a 1.0
            - method: 'rule', 'history', 'history_prefix', 'history_similar', 'none'
        """
        normalized = self.text_processor.normalize(description)

        # 1. Tentar regras manuais (prioridade mais alta)
        category_id = self._match_rules(description)
        if category_id:
            return category_id, 1.0, 'rule'

        # 2. Tentar histórico exato
        category_id, confidence = self._match_history_exact(normalized)
        if category_id and confidence >= self.MIN_CONFIDENCE:
            return category_id, confidence, 'history'

        # 3. Tentar matching por prefixo (primeiras 2 palavras significativas)
        category_id, confidence = self._match_by_prefix(normalized)
        if category_id and confidence >= self.MIN_CONFIDENCE:
            return category_id, confidence, 'history_prefix'

        # 4. Tentar histórico similar (Jaccard token similarity)
        category_id, confidence = self._match_history_similar(normalized)
        if category_id and confidence >= 0.50:
            return category_id, confidence, 'history_similar'

        return None, 0.0, 'none'

    def _match_rules(self, text: str) -> Optional[int]:
        """Aplica regras manuais em ordem de prioridade."""
        rules = (
            self.db.query(CategorizationRule)
            .filter(CategorizationRule.is_active == True)
            .order_by(CategorizationRule.priority.desc())
            .all()
        )

        for rule in rules:
            if self._rule_matches(rule, text):
                # Incrementar contador de uso (flush, não commit — caller controla)
                rule.hit_count += 1
                self.db.flush()
                return rule.category_id

        return None

    def _rule_matches(self, rule: CategorizationRule, text: str) -> bool:
        """Verifica se uma regra corresponde ao texto."""
        text_lower = text.lower()
        pattern_lower = rule.pattern.lower()

        if rule.match_type == MatchType.CONTAINS:
            return pattern_lower in text_lower
        elif rule.match_type == MatchType.STARTS_WITH:
            return text_lower.startswith(pattern_lower)
        elif rule.match_type == MatchType.ENDS_WITH:
            return text_lower.endswith(pattern_lower)
        elif rule.match_type == MatchType.EXACT:
            return text_lower == pattern_lower
        elif rule.match_type == MatchType.REGEX:
            try:
                return bool(re.search(rule.pattern, text, re.IGNORECASE))
            except re.error:
                return False

        return False

    def _match_history_exact(
        self,
        normalized_text: str
    ) -> Tuple[Optional[int], float]:
        """Busca correspondência exata no histórico. Prefere mais recente em caso de empate."""
        history = (
            self.db.query(CategorizationHistory)
            .filter(CategorizationHistory.description_normalized == normalized_text)
            .order_by(
                CategorizationHistory.times_used.desc(),
                CategorizationHistory.last_used_at.desc()
            )
            .first()
        )

        if history:
            # Confiança baseada no número de vezes usado
            confidence = min(0.95, 0.7 + (history.times_used * 0.05))
            return history.category_id, confidence

        return None, 0.0

    def _match_by_prefix(
        self,
        normalized_text: str
    ) -> Tuple[Optional[int], float]:
        """
        Matching por prefixo: extrai as 2 primeiras palavras significativas
        e busca no histórico todas as entradas que começam com esse prefixo.
        Se >=80% mapeiam para mesma categoria, retorna essa categoria.
        """
        if not normalized_text:
            return None, 0.0

        # Extrair palavras significativas (3+ chars)
        words = [w for w in normalized_text.split() if len(w) >= 3]
        if len(words) < 2:
            return None, 0.0

        prefix = ' '.join(words[:2])

        # Buscar todos os históricos que começam com esse prefixo
        histories = (
            self.db.query(CategorizationHistory)
            .filter(CategorizationHistory.description_normalized.like(f"{prefix}%"))
            .all()
        )

        if not histories or len(histories) < 2:
            return None, 0.0

        # Agrupar por categoria, somando times_used como peso
        from collections import Counter
        category_counts = Counter()
        total_weight = 0
        for h in histories:
            category_counts[h.category_id] += h.times_used
            total_weight += h.times_used

        if total_weight == 0:
            return None, 0.0

        # Encontrar categoria dominante
        best_category, best_count = category_counts.most_common(1)[0]
        agreement = best_count / total_weight

        if agreement >= 0.80:
            # Confiança baseada na porcentagem de concordância
            confidence = min(0.90, 0.75 + (agreement - 0.80) * 0.75)
            return best_category, confidence

        return None, 0.0

    def _match_history_similar(
        self,
        normalized_text: str
    ) -> Tuple[Optional[int], float]:
        """
        Busca correspondência similar no histórico usando Jaccard token similarity.
        Busca candidatos que compartilhem pelo menos um token significativo,
        depois calcula similaridade Jaccard e retorna o melhor match.
        """
        if not normalized_text or len(normalized_text) < 3:
            return None, 0.0

        # Extrair tokens significativos (3+ chars)
        tokens_new = set(w for w in normalized_text.split() if len(w) >= 3)
        if not tokens_new:
            return None, 0.0

        # Buscar candidatos: históricos que contenham pelo menos um dos tokens
        from sqlalchemy import or_
        filters = [
            CategorizationHistory.description_normalized.contains(token)
            for token in list(tokens_new)[:5]  # Limitar a 5 tokens para performance
        ]

        candidates = (
            self.db.query(CategorizationHistory)
            .filter(or_(*filters))
            .all()
        )

        if not candidates:
            return None, 0.0

        # Calcular Jaccard similarity para cada candidato
        best_category = None
        best_similarity = 0.0

        for candidate in candidates:
            tokens_candidate = set(w for w in candidate.description_normalized.split() if len(w) >= 3)
            if not tokens_candidate:
                continue

            intersection = tokens_new & tokens_candidate
            union = tokens_new | tokens_candidate

            if not union:
                continue

            similarity = len(intersection) / len(union)

            if similarity > best_similarity:
                best_similarity = similarity
                best_category = candidate.category_id

        if best_category and best_similarity >= 0.50:
            # Confiança escalada pela similaridade
            confidence = best_similarity * 0.90
            return best_category, confidence

        return None, 0.0

    def learn_from_categorization(
        self,
        description: str,
        category_id: int,
        old_category_id: int = None
    ):
        """
        Aprende com uma categorização.
        Se old_category_id fornecido, decrementa o histórico da categoria anterior.
        Nota: NÃO faz commit - o caller é responsável pelo commit.
        """
        normalized = self.text_processor.normalize(description)

        if not normalized:
            return

        # Se re-categorizando, decrementar a categoria anterior
        if old_category_id and old_category_id != category_id:
            old_entry = (
                self.db.query(CategorizationHistory)
                .filter(
                    CategorizationHistory.description_normalized == normalized,
                    CategorizationHistory.category_id == old_category_id
                )
                .first()
            )
            if old_entry:
                old_entry.times_used = max(0, old_entry.times_used - 1)
                if old_entry.times_used == 0:
                    self.db.delete(old_entry)

        # Incrementar/criar entrada para a nova categoria
        # Flush first to ensure any pending adds are visible
        self.db.flush()

        existing = (
            self.db.query(CategorizationHistory)
            .filter(
                CategorizationHistory.description_normalized == normalized,
                CategorizationHistory.category_id == category_id
            )
            .first()
        )

        if existing:
            existing.times_used += 1
            existing.last_used_at = datetime.utcnow()
        else:
            new_history = CategorizationHistory(
                description_normalized=normalized,
                category_id=category_id,
                times_used=1
            )
            self.db.add(new_history)
            self.db.flush()
