"""Identifica candidatos a duplicata no banco Itaú em 2026.

Para cada par (data, valor) com 2+ transações no banco,
verifica quantas o arquivo do extrato esperava.
Se sistema tem mais que arquivo, é duplicata.
"""
import sqlite3
import openpyxl
import xlrd
from datetime import date, datetime
from collections import defaultdict
import unicodedata
import re


def parse_br_date(s):
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    try:
        return datetime.strptime(str(s).strip(), '%d/%m/%Y').date()
    except (ValueError, TypeError):
        return None


def normalize_desc(s):
    if not s:
        return ''
    s = str(s).strip()
    try:
        s = s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    s = s.upper()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_amount(v):
    if v is None or v == '':
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def read_file(path):
    if path.endswith('.xls'):
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        rows = [[sh.cell_value(i, c) for c in range(sh.ncols)] for i in range(sh.nrows)]
    else:
        wb = openpyxl.load_workbook(path, read_only=True)
        sh = wb.active
        rows = list(sh.iter_rows(values_only=True))

    txns = []
    for i, row in enumerate(rows):
        if i < 9:
            continue
        if not row or len(row) < 4:
            continue
        d = parse_br_date(row[0])
        if not d:
            continue
        desc = row[1]
        if desc and 'SALDO' in str(desc).upper():
            continue
        amt = normalize_amount(row[3])
        if amt is None:
            continue
        txns.append({'date': d, 'desc': normalize_desc(desc), 'amount': amt, 'src': path, 'line': i})
    return txns


def main():
    files = [
        r'c:\Users\paulo\gestao-contas\extratos\Itau 260307 90 dias.xlsx',
        r'c:\Users\paulo\gestao-contas\extratos\Itau 260403.xls',
    ]

    # Construir contagem esperada por (date, amount) — pegando o MAX entre os arquivos
    counts_per_file = []
    for f in files:
        txns = read_file(f)
        c = defaultdict(int)
        for t in txns:
            if t['date'].year == 2026:
                c[(t['date'], t['amount'])] += 1
        counts_per_file.append(c)

    # Esperado = max entre arquivos (uniao)
    expected = {}
    all_keys = set()
    for c in counts_per_file:
        all_keys.update(c.keys())
    for k in all_keys:
        expected[k] = max(c.get(k, 0) for c in counts_per_file)

    # Banco
    db = sqlite3.connect(r'c:\Users\paulo\gestao-contas\backend\gestao_contas.db')
    cur = db.cursor()
    cur.execute("""
        SELECT id, date, description, amount_brl
        FROM transactions
        WHERE account_id = 5 AND date >= '2026-01-01' AND date <= '2026-04-30'
        ORDER BY date, id
    """)
    bank_txns = defaultdict(list)
    for r in cur.fetchall():
        tid, dstr, desc, amt = r
        d = datetime.strptime(dstr, '%Y-%m-%d').date()
        na = round(float(amt), 2)
        bank_txns[(d, na)].append((tid, desc))

    # Achar duplicatas: banco tem mais que esperado
    print(f"=== Candidatos a duplicata (banco tem mais ocorrencias que arquivo) ===")
    print(f"Formato: data, valor: ARQUIVO esperava X, BANCO tem Y, transacoes:\n")
    total_dup_value = 0
    total_dup_count = 0
    to_remove = []  # ids para remover

    for (d, amt), bank_list in sorted(bank_txns.items()):
        if len(bank_list) <= 1:
            continue
        exp = expected.get((d, amt), 0)
        if len(bank_list) > exp:
            extra = len(bank_list) - exp
            total_dup_count += extra
            total_dup_value += amt * extra
            print(f"  {d} | R$ {amt:>11,.2f} | esperado={exp}, banco={len(bank_list)}, extras={extra}")
            for tid, desc in bank_list:
                print(f"     id={tid} | {desc}")
            # Remover os IDs MAIS RECENTES (preserva o batch original)
            ids_sorted = sorted(bank_list, key=lambda x: x[0], reverse=True)
            for i in range(extra):
                to_remove.append((ids_sorted[i][0], d, amt, ids_sorted[i][1]))
            print()

    print(f"\n=== RESUMO ===")
    print(f"Total duplicatas a remover: {total_dup_count}")
    print(f"Valor total duplicado: R$ {total_dup_value:,.2f}")

    # Salvar lista de IDs para remover
    import json
    with open(r'c:\tmp\itau_duplicates.json', 'w', encoding='utf-8') as f:
        json.dump([{
            'id': tid,
            'date': str(d),
            'amount': amt,
            'description': desc,
        } for tid, d, amt, desc in to_remove], f, ensure_ascii=False, indent=2)
    print(f"\nLista de IDs salva em c:\\tmp\\itau_duplicates.json")

    db.close()


if __name__ == '__main__':
    main()
