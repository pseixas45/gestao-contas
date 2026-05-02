"""Saneamento de conflitos de categorização (parte A).

1. Histórico: para cada description_normalized com >1 categoria,
   manter apenas a com MAIS times_used. Remover as outras entradas.
2. Regras: para cada pattern com >1 categoria, manter a com MAIS hit_count.
3. Reportar quantas regras/históricos foram limpos.
"""
import sqlite3
from collections import defaultdict


def main():
    db = sqlite3.connect(r'c:\Users\paulo\gestao-contas\backend\gestao_contas.db')
    cur = db.cursor()

    # =========================
    # PARTE 1: Limpeza do histórico
    # =========================
    print("=" * 60)
    print("PARTE 1: Histórico de categorização")
    print("=" * 60)

    cur.execute("""
        SELECT description_normalized, category_id, times_used, id
        FROM categorization_history
    """)
    hist_rows = cur.fetchall()
    by_desc = defaultdict(list)
    for desc_norm, cat_id, used, hist_id in hist_rows:
        by_desc[desc_norm].append({
            'id': hist_id, 'category_id': cat_id, 'times_used': used
        })

    conflicts_hist = {d: rows for d, rows in by_desc.items() if len(set(r['category_id'] for r in rows)) > 1}
    print(f"Total descrições no histórico: {len(by_desc)}")
    print(f"Descrições com conflito (>1 categoria): {len(conflicts_hist)}")

    deleted_hist = 0
    examples = []
    for desc, rows in conflicts_hist.items():
        # Escolher categoria com MAX(times_used)
        rows_sorted = sorted(rows, key=lambda x: x['times_used'], reverse=True)
        winner = rows_sorted[0]
        losers = rows_sorted[1:]
        for l in losers:
            cur.execute("DELETE FROM categorization_history WHERE id = ?", (l['id'],))
            deleted_hist += 1
        if len(examples) < 5:
            examples.append((desc, winner, losers))

    print(f"Entradas removidas: {deleted_hist}")
    print(f"\nExemplos de resolução:")
    for desc, w, ls in examples:
        cur.execute("SELECT name FROM categories WHERE id = ?", (w['category_id'],))
        wname = cur.fetchone()[0]
        print(f"\n  '{desc[:50]}'")
        print(f"    MANTIDO: {wname} (times_used={w['times_used']})")
        for l in ls:
            cur.execute("SELECT name FROM categories WHERE id = ?", (l['category_id'],))
            lname = cur.fetchone()[0]
            print(f"    REMOVIDO: {lname} (times_used={l['times_used']})")

    # =========================
    # PARTE 2: Limpeza de regras
    # =========================
    print("\n" + "=" * 60)
    print("PARTE 2: Regras de categorização")
    print("=" * 60)

    cur.execute("""
        SELECT id, pattern, category_id, hit_count
        FROM categorization_rules
        WHERE is_active = 1
    """)
    rules = cur.fetchall()
    by_pattern = defaultdict(list)
    for rid, pattern, cat, hits in rules:
        by_pattern[pattern.lower().strip()].append({
            'id': rid, 'category_id': cat, 'hit_count': hits
        })

    conflicts_rules = {p: rs for p, rs in by_pattern.items() if len(set(r['category_id'] for r in rs)) > 1}
    print(f"Total patterns ativos: {len(by_pattern)}")
    print(f"Patterns com conflito: {len(conflicts_rules)}")

    deactivated = 0
    rule_examples = []
    for pattern, rs in conflicts_rules.items():
        # Escolher regra com MAX(hit_count)
        rs_sorted = sorted(rs, key=lambda x: x['hit_count'], reverse=True)
        winner = rs_sorted[0]
        losers = rs_sorted[1:]
        for l in losers:
            cur.execute("UPDATE categorization_rules SET is_active = 0 WHERE id = ?", (l['id'],))
            deactivated += 1
        if len(rule_examples) < 5:
            rule_examples.append((pattern, winner, losers))

    print(f"Regras desativadas: {deactivated}")
    print(f"\nExemplos de resolução:")
    for pat, w, ls in rule_examples:
        cur.execute("SELECT name FROM categories WHERE id = ?", (w['category_id'],))
        wname = cur.fetchone()[0]
        print(f"\n  pattern='{pat}'")
        print(f"    MANTIDO: id={w['id']} -> {wname} (hits={w['hit_count']})")
        for l in ls:
            cur.execute("SELECT name FROM categories WHERE id = ?", (l['category_id'],))
            lname = cur.fetchone()[0]
            print(f"    DESATIVADO: id={l['id']} -> {lname} (hits={l['hit_count']})")

    db.commit()

    # Stats finais
    cur.execute("SELECT COUNT(*) FROM categorization_history")
    total_hist = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM categorization_rules WHERE is_active = 1")
    total_rules = cur.fetchone()[0]
    print(f"\n{'=' * 60}")
    print(f"RESULTADO FINAL")
    print(f"{'=' * 60}")
    print(f"Histórico: {total_hist} entradas (era {len(hist_rows)})")
    print(f"Regras ativas: {total_rules} (eram {len(rules)})")

    db.close()


if __name__ == '__main__':
    main()
