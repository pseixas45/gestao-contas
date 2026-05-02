"""Reconciliação detalhada das transações do Itaú em 2026.

Lê os arquivos de extrato + as transações do banco e identifica:
- Transações no arquivo mas NÃO no banco (faltando)
- Transações no banco mas NÃO no arquivo (sobrando/duplicadas)
- Linhas de saldo de referência para validar
"""
import sqlite3
import openpyxl
import xlrd
from datetime import date, datetime
from collections import defaultdict
from decimal import Decimal


def parse_br_date(s):
    """Converte '01/02/2026' para date(2026,2,1)"""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    try:
        return datetime.strptime(str(s).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError):
        return None


def normalize_desc(s):
    """Normaliza descrição para comparação — remove acentos, mojibake, pontuação."""
    if not s:
        return ''
    import unicodedata
    s = str(s).strip()
    # Tentar corrigir double-encoded UTF-8
    try:
        s = s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    s = s.upper()
    # Remover acentos
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Remover caracteres não-alfanuméricos (deixar só letras, números e espaço)
    import re
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_amount(v):
    """Converte valor para float"""
    if v is None or v == '':
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def read_xlsx(path):
    """Lê arquivo .xlsx do Itaú e extrai transações + saldos"""
    wb = openpyxl.load_workbook(path, read_only=True)
    sh = wb.active
    txns = []
    saldos = []  # (date, balance)
    for i, row in enumerate(sh.iter_rows(values_only=True)):
        if i < 9:  # cabeçalho
            continue
        if not row or len(row) < 4:
            continue
        d = parse_br_date(row[0])
        if not d:
            continue
        desc = row[1]
        val_d = row[3] if len(row) > 3 else None
        val_e = row[4] if len(row) > 4 else None

        # Linha de saldo (descrição contém SALDO)
        if desc and 'SALDO' in str(desc).upper():
            bal = normalize_amount(val_e)
            if bal is not None:
                saldos.append((d, normalize_desc(desc), bal))
            continue

        # Linha de transação (valor em D)
        amt = normalize_amount(val_d)
        if amt is not None:
            txns.append({
                'date': d,
                'desc': normalize_desc(desc),
                'amount': amt,
                'line': i,
            })
    return txns, saldos


def read_xls(path):
    """Lê arquivo .xls (formato antigo) do Itaú"""
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    txns = []
    saldos = []
    for i in range(sh.nrows):
        if i < 9:
            continue
        row = [sh.cell_value(i, c) for c in range(sh.ncols)]
        if not row or len(row) < 4:
            continue
        d = parse_br_date(row[0])
        if not d:
            continue
        desc = row[1]
        val_d = row[3] if len(row) > 3 else None
        val_e = row[4] if len(row) > 4 else None

        if desc and 'SALDO' in str(desc).upper():
            bal = normalize_amount(val_e)
            if bal is not None:
                saldos.append((d, normalize_desc(desc), bal))
            continue

        amt = normalize_amount(val_d)
        if amt is not None:
            txns.append({
                'date': d,
                'desc': normalize_desc(desc),
                'amount': amt,
                'line': i,
            })
    return txns, saldos


def main():
    # Lê os dois arquivos relevantes
    file_90d = r'c:\Users\paulo\gestao-contas\extratos\Itau 260307 90 dias.xlsx'
    file_403 = r'c:\Users\paulo\gestao-contas\extratos\Itau 260403.xls'

    print(f"Lendo {file_90d}...")
    txns_90d, saldos_90d = read_xlsx(file_90d)
    print(f"  {len(txns_90d)} transações, {len(saldos_90d)} saldos")

    print(f"Lendo {file_403}...")
    txns_403, saldos_403 = read_xls(file_403)
    print(f"  {len(txns_403)} transações, {len(saldos_403)} saldos")

    # Período 2026 do arquivo 90d (até 06/03) + arquivo 403 (de 02/04 em diante)
    # Mas há sobreposição parcial. Vou usar UNIÃO de ambos, com chave (data, desc, valor)

    # Construir set de todas as transações esperadas em 2026
    file_txns = {}  # key=(date, desc, amount, occurrence) → arquivo
    counts_by_key = defaultdict(int)

    for t in txns_90d:
        if t['date'].year != 2026:
            continue
        # numerar ocorrências (mesma chave pode aparecer várias vezes)
        base = (t['date'], t['desc'], t['amount'])
        counts_by_key[base] += 1
        n = counts_by_key[base]
        file_txns[(t['date'], t['desc'], t['amount'], n)] = ('90d', t['line'])

    # Aplicar 403 — preservando contagem (não duplicar com 90d)
    counts_403 = defaultdict(int)
    for t in txns_403:
        if t['date'].year != 2026:
            continue
        base = (t['date'], t['desc'], t['amount'])
        counts_403[base] += 1

    # Usar o MÁXIMO de ocorrências entre os dois arquivos para cada chave
    for base, c403 in counts_403.items():
        c90 = counts_by_key.get(base, 0)
        if c403 > c90:
            # adicionar ocorrências extras
            for n in range(c90 + 1, c403 + 1):
                # achar a linha no 403
                line_num = None
                seen = 0
                for t in txns_403:
                    if (t['date'], t['desc'], t['amount']) == base:
                        seen += 1
                        if seen == n:
                            line_num = t['line']
                            break
                file_txns[(*base, n)] = ('403', line_num)

    print(f"\nTotal esperado em 2026 (união dos arquivos): {len(file_txns)}")

    # Buscar do banco
    db = sqlite3.connect(r'c:\Users\paulo\gestao-contas\backend\gestao_contas.db')
    cur = db.cursor()
    cur.execute("""
        SELECT id, date, description, amount_brl
        FROM transactions
        WHERE account_id = 5 AND date >= '2026-01-01' AND date <= '2026-04-30'
        ORDER BY date, id
    """)

    db_txns = {}  # key=(date, desc, amount, occurrence) → id
    counts_db = defaultdict(int)
    for r in cur.fetchall():
        tid, dstr, desc, amt = r
        d = datetime.strptime(dstr, '%Y-%m-%d').date()
        nd = normalize_desc(desc)
        na = round(float(amt), 2)
        base = (d, nd, na)
        counts_db[base] += 1
        n = counts_db[base]
        db_txns[(d, nd, na, n)] = tid

    print(f"Total no banco em 2026 (jan-abr): {len(db_txns)}")

    # Comparar
    file_keys = set(file_txns.keys())
    db_keys = set(db_txns.keys())

    only_in_file = file_keys - db_keys  # FALTANDO no banco
    only_in_db = db_keys - file_keys     # SOBRANDO no banco

    # Resumo financeiro
    sum_only_file = sum(k[2] for k in only_in_file)
    sum_only_db = sum(k[2] for k in only_in_db)

    print(f"\n{'='*70}")
    print(f"=== RESULTADO DA RECONCILIAÇÃO ===")
    print(f"{'='*70}")
    print(f"Transações faltando no banco (estão no arquivo): {len(only_in_file)}")
    print(f"  Soma valores: R$ {sum_only_file:,.2f}")
    print(f"Transações sobrando no banco (não estão no arquivo): {len(only_in_db)}")
    print(f"  Soma valores: R$ {sum_only_db:,.2f}")
    print(f"\nDivergência líquida: R$ {sum_only_file - sum_only_db:,.2f}")
    print(f"  (positivo = sistema deveria ter MAIS valor)")

    # Detalhe das faltantes — agrupar por (data, valor) para encontrar matches por descrição parcial
    print(f"\n{'='*70}")
    print(f"=== TRANSAÇÕES FALTANDO NO BANCO ({len(only_in_file)}) ===")
    print(f"{'='*70}")
    # Para cada faltante, procurar candidato no banco com mesmo (data, valor) mas desc diferente
    db_by_date_amt = defaultdict(list)
    for k, tid in db_txns.items():
        d, desc, amt, _ = k
        db_by_date_amt[(d, amt)].append((desc, tid))

    real_missing = []
    for k in sorted(only_in_file):
        d, desc, amt, occ = k
        src, line = file_txns[k]
        candidates = db_by_date_amt.get((d, amt), [])
        # Há candidato com data e valor iguais mas descrição diferente?
        possible_match = None
        for cdesc, ctid in candidates:
            # match parcial: prefixo comum de 10+ caracteres
            common_len = 0
            for a, b in zip(desc, cdesc):
                if a == b:
                    common_len += 1
                else:
                    break
            if common_len >= 10:
                possible_match = (cdesc, ctid, common_len)
                break

        if possible_match:
            print(f"  [MATCH] {d} | {desc[:40]:40} | R$ {amt:>11,.2f}")
            print(f"            => banco tem: {possible_match[0][:40]:40} (id={possible_match[1]}, prefixo {possible_match[2]} chars)")
        else:
            real_missing.append(k)
            print(f"  [FALTA] {d} | {desc[:50]:50} | R$ {amt:>11,.2f} (#{occ}) [{src} L{line}]")

    # Detalhe das sobrando
    print(f"\n{'='*70}")
    print(f"=== TRANSAÇÕES SOBRANDO NO BANCO ({len(only_in_db)}) ===")
    print(f"{'='*70}")
    file_by_date_amt = defaultdict(list)
    for k, info in file_txns.items():
        d, desc, amt, _ = k
        file_by_date_amt[(d, amt)].append((desc, info))

    real_extra = []
    for k in sorted(only_in_db):
        d, desc, amt, occ = k
        tid = db_txns[k]
        candidates = file_by_date_amt.get((d, amt), [])
        possible_match = None
        for fdesc, finfo in candidates:
            common_len = 0
            for a, b in zip(desc, fdesc):
                if a == b:
                    common_len += 1
                else:
                    break
            if common_len >= 10:
                possible_match = (fdesc, finfo, common_len)
                break

        if possible_match:
            print(f"  [MATCH] {d} | {desc[:40]:40} | R$ {amt:>11,.2f} | id={tid}")
            print(f"            => arquivo tem: {possible_match[0][:40]:40} ({possible_match[1][0]} L{possible_match[1][1]})")
        else:
            real_extra.append(k)
            print(f"  [EXTRA] {d} | {desc[:50]:50} | R$ {amt:>11,.2f} (#{occ}) [id={tid}]")

    print(f"\n{'='*70}")
    print(f"=== SUMÁRIO REAL ===")
    print(f"{'='*70}")
    sum_missing = sum(k[2] for k in real_missing)
    sum_extra = sum(k[2] for k in real_extra)
    print(f"Realmente FALTANDO no banco: {len(real_missing)} (R$ {sum_missing:,.2f})")
    print(f"Realmente SOBRANDO no banco: {len(real_extra)} (R$ {sum_extra:,.2f})")
    print(f"Divergência líquida real: R$ {sum_missing - sum_extra:,.2f}")

    # Validar saldos — TODOS os pontos
    print(f"\n{'='*70}")
    print(f"=== SALDOS DE REFERENCIA: TODOS OS PONTOS DOS DOIS ARQUIVOS ===")
    print(f"{'='*70}")
    print(f"  {'Data':10} | {'sistema':>12} | {'extrato':>12} | {'diff':>12}")
    print(f"  " + "-"*66)
    cur.execute("SELECT initial_balance FROM bank_accounts WHERE id=5")
    ini = float(cur.fetchone()[0])

    # Combinar saldos dos 2 arquivos, ordenar por data, deduplicar
    all_saldos = []
    for d, desc, bal in saldos_90d:
        all_saldos.append((d, '90d', bal))
    for d, desc, bal in saldos_403:
        all_saldos.append((d, '403', bal))

    # Filtrar 2026 e ordenar
    all_saldos = [s for s in all_saldos if s[0].year == 2026]
    # Pegar ÚLTIMO saldo de cada data (saldo de fim do dia)
    seen = {}
    for d, src, bal in all_saldos:
        seen[d] = (src, bal)
    all_saldos_dedup = sorted([(d, s, b) for d, (s, b) in seen.items()])

    # Análise por delta dia-a-dia
    print(f"\n  ANALISE POR DELTA DIARIO (compara variacao do saldo)")
    print(f"  {'data':10} | {'extrato_var':>12} | {'sistema_var':>12} | {'desv_dia':>12} | {'movs sistema':>5}")
    print(f"  " + "-"*70)
    prev_bal_extrato = None
    prev_d = None
    total_desv = 0
    big_devs = []

    for d, src, bal in all_saldos_dedup:
        if prev_bal_extrato is None:
            prev_bal_extrato = bal
            prev_d = d
            continue
        # Variação extrato
        var_extrato = bal - prev_bal_extrato
        # Variação sistema = soma das transações ENTRE prev_d (exclusive) e d (inclusive)
        cur.execute("""
            SELECT COALESCE(SUM(amount_brl), 0), COUNT(*)
            FROM transactions
            WHERE account_id = 5 AND date > ? AND date <= ?
        """, (prev_d.isoformat(), d.isoformat()))
        var_sis, n_movs = cur.fetchone()
        var_sis = float(var_sis)
        desv = var_extrato - var_sis
        marker = ''
        if abs(desv) > 0.01:
            marker = ' ***'
            total_desv += desv
            big_devs.append((d, desv, var_extrato, var_sis, n_movs))
        print(f"  {d} | {var_extrato:>12,.2f} | {var_sis:>12,.2f} | {desv:>12,.2f} | {n_movs:>5}{marker}")
        prev_bal_extrato = bal
        prev_d = d

    print(f"\n  Total desvio acumulado: R$ {total_desv:,.2f}")
    print(f"\n  DIAS COM DIVERGENCIA (>R$0,01):")
    for d, desv, ve, vs, n in big_devs:
        # detalhar transações do dia no sistema
        cur.execute("""
            SELECT id, substr(description,1,40), amount_brl
            FROM transactions
            WHERE account_id = 5 AND date = ?
            ORDER BY id
        """, (d.isoformat(),))
        txs = cur.fetchall()
        print(f"\n  {d} | desvio={desv:+,.2f} | extrato={ve:+,.2f} | sistema={vs:+,.2f} | {n} txns no sistema:")
        for t in txs:
            print(f"    id={t[0]} | {t[1]:40} | R$ {t[2]:>11}")

    db.close()


if __name__ == '__main__':
    main()
