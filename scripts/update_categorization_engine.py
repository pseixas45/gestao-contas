"""Atualiza o motor de categorização com base nos ajustes manuais recentes.

1. Limpa conflitos do histórico (mantém a categoria com mais usos)
2. Para cada descrição "forte" (5+ usos, 1 categoria), garante regra explícita
3. Desativa regras conflitantes (mesmo padrão apontando para categoria diferente)
"""
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))
from app.services.categorization_service import TextProcessor

# Stopwords bancárias — não viram regra (genéricas demais)
RULE_STOPWORDS = {
    'pix', 'pag', 'pagamento', 'pagamentos', 'transferencia', 'transf',
    'boleto', 'ted', 'doc', 'tit', 'titulo', 'int', 'sispag', 'cred',
    'deb', 'debito', 'credito', 'deposito', 'banco', 'resg', 'resgate',
    'qrs', 'parcela', 'parc', 'compra', 'venda', 'pgto', 'receb',
    'recebimento', 'lanc', 'lancamento', 'mov', 'movimentacao', 'tarifa',
    'taxa', 'envio', 'recebido', 'enviado', 'estorno', 'devolucao',
    'aut', 'autoriz', 'co', 'pg', 'op', 'rec',
}

MIN_USES_FOR_RULE = 5  # mínimo de usos para virar regra


def extract_keyword(desc_normalized: str) -> str:
    """Pega a primeira palavra significativa (3+ chars, não stopword)."""
    words = [w for w in desc_normalized.split() if len(w) >= 3]
    for w in words:
        if w not in RULE_STOPWORDS:
            return w
    return ""


def main():
    db = sqlite3.connect(r'c:\Users\paulo\gestao-contas\backend\gestao_contas.db')
    cur = db.cursor()

    # ===== PARTE 1: Limpar conflitos do histórico =====
    print('=' * 60)
    print('PARTE 1: Limpar conflitos no histórico')
    print('=' * 60)

    cur.execute('SELECT id, description_normalized, category_id, times_used FROM categorization_history')
    hist_rows = cur.fetchall()
    by_desc = defaultdict(list)
    for hid, desc, cat, used in hist_rows:
        by_desc[desc].append({'id': hid, 'cat': cat, 'used': used})

    conflicts = {d: rs for d, rs in by_desc.items() if len(set(r['cat'] for r in rs)) > 1}
    print(f'Descrições em conflito: {len(conflicts)}')

    deleted_hist = 0
    for desc, rows in conflicts.items():
        rows_sorted = sorted(rows, key=lambda x: x['used'], reverse=True)
        for loser in rows_sorted[1:]:
            cur.execute('DELETE FROM categorization_history WHERE id = ?', (loser['id'],))
            deleted_hist += 1
    print(f'Entradas conflitantes removidas: {deleted_hist}')

    # ===== PARTE 2: Recarregar histórico e criar regras =====
    print()
    print('=' * 60)
    print('PARTE 2: Criar regras a partir do histórico forte')
    print('=' * 60)

    cur.execute('SELECT description_normalized, category_id, times_used FROM categorization_history')
    by_desc = defaultdict(list)
    for d, c, u in cur.fetchall():
        by_desc[d].append((c, u))

    # Descrições fortes: 1 categoria, 5+ usos
    strong = []
    for d, rs in by_desc.items():
        cats = set(r[0] for r in rs)
        if len(cats) == 1 and rs[0][1] >= MIN_USES_FOR_RULE:
            strong.append((d, rs[0][0], rs[0][1]))

    print(f'Descrições "fortes" (>={MIN_USES_FOR_RULE} usos, 1 cat): {len(strong)}')

    # Para cada uma, extrair keyword e criar/atualizar regra
    rules_created = 0
    rules_skipped_stopword = 0
    rules_skipped_existing = 0
    conflicts_deactivated = 0

    for desc, cat_id, uses in strong:
        keyword = extract_keyword(desc)
        if not keyword:
            rules_skipped_stopword += 1
            continue

        # Verificar regra existente para este (keyword, cat_id)
        cur.execute(
            'SELECT id FROM categorization_rules WHERE LOWER(pattern)=? AND category_id=? AND is_active=1',
            (keyword, cat_id)
        )
        existing = cur.fetchone()

        # Desativar regras conflitantes (mesmo keyword, categoria DIFERENTE)
        cur.execute(
            'SELECT id FROM categorization_rules WHERE LOWER(pattern)=? AND category_id != ? AND is_active=1',
            (keyword, cat_id)
        )
        for (cid,) in cur.fetchall():
            cur.execute('UPDATE categorization_rules SET is_active=0 WHERE id=?', (cid,))
            conflicts_deactivated += 1

        if existing:
            rules_skipped_existing += 1
            continue

        # Criar nova regra
        cur.execute("""
            INSERT INTO categorization_rules
            (category_id, pattern, match_type, priority, is_active, hit_count, created_at, updated_at)
            VALUES (?, ?, 'CONTAINS', 50, 1, ?, datetime('now'), datetime('now'))
        """, (cat_id, keyword, uses))
        rules_created += 1

    print(f'Regras criadas: {rules_created}')
    print(f'Regras já existentes (puladas): {rules_skipped_existing}')
    print(f'Descrições sem keyword (só stopwords): {rules_skipped_stopword}')
    print(f'Regras conflitantes desativadas: {conflicts_deactivated}')

    db.commit()

    # ===== Resumo final =====
    print()
    print('=' * 60)
    print('RESUMO FINAL')
    print('=' * 60)
    cur.execute('SELECT COUNT(*) FROM categorization_history')
    print(f'Histórico: {cur.fetchone()[0]} entradas')
    cur.execute('SELECT COUNT(*) FROM categorization_rules WHERE is_active=1')
    print(f'Regras ativas: {cur.fetchone()[0]}')

    db.close()


if __name__ == '__main__':
    main()
