"""Importa Master 260520.xls extraindo só a tabela de lançamentos.

O arquivo do Itaú tem cabeçalho com várias linhas de metadados (logo, conta,
fatura aberta, etc.) antes da tabela de transações real. Detectamos onde
começa a tabela e geramos um xlsx limpo para o ImportService processar.
"""
import xlrd
import openpyxl
import requests
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

API = 'http://localhost:8002'
SOURCE = r'c:\Users\paulo\gestao-contas\extratos\Master 260520.xls'
ACCOUNT_ID = 6


def parse_dt(s):
    if isinstance(s, (datetime, date)):
        return s if not isinstance(s, datetime) else s.date()
    s = str(s).strip()
    for fmt in ['%d/%m/%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def transform():
    """Lê o .xls original e gera xlsx só com transações.

    Não usa header como divisor — itera TODAS as linhas e mantém aquelas
    que têm uma data válida na coluna 0 + valor numérico em alguma coluna.
    Isso captura o pagamento da fatura anterior (que aparece antes do
    header da tabela de lançamentos).
    """
    wb = xlrd.open_workbook(SOURCE)
    sh = wb.sheet_by_index(0)

    wb_out = openpyxl.Workbook()
    sh_out = wb_out.active
    sh_out.append(['data', 'lancamento', 'valor'])

    kept = 0
    skipped = 0
    for i in range(sh.nrows):
        cells = [sh.cell_value(i, c) for c in range(sh.ncols)]
        # Pular linhas separadoras / vazias
        if all(str(c).strip() == '' for c in cells):
            continue
        d = parse_dt(cells[0])
        if not d:
            # Pular cabeçalhos / texto sem data
            skipped += 1
            continue
        desc = str(cells[1]).strip() if len(cells) > 1 else ''
        # Valor: última coluna não-vazia com número
        val = None
        for c in range(len(cells) - 1, -1, -1):
            v = cells[c]
            if isinstance(v, (int, float)) and v != 0:
                val = v
                break
        if val is None or not desc:
            skipped += 1
            continue
        # Pular linhas-totalizador (ex: "total da fatura anterior")
        desc_lower = desc.lower()
        if any(kw in desc_lower for kw in ['total da fatura', 'total (', 'total nacional', 'total internacional']):
            skipped += 1
            continue
        sh_out.append([d.strftime('%d/%m/%Y'), desc, val])
        kept += 1

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp_path = tmp.name
    tmp.close()
    wb_out.save(tmp_path)
    print(f"  Linhas mantidas: {kept}")
    print(f"  Linhas puladas:  {skipped}")
    return tmp_path


def main():
    print("=== Transformando arquivo ===")
    tmp = transform()
    if not tmp:
        return 1

    print("\n=== Login ===")
    token = requests.post(
        f'{API}/api/v1/auth/login',
        data={'username': 'pseixas', 'password': 'pseixas123'},
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    ).json()['access_token']
    H = {'Authorization': f'Bearer {token}'}

    bal_before = float(requests.get(f'{API}/api/v1/accounts/{ACCOUNT_ID}', headers=H).json()['current_balance'])
    print(f"Saldo antes: R$ {bal_before:,.2f}")

    print("\n=== Upload ===")
    with open(tmp, 'rb') as f:
        r = requests.post(
            f'{API}/api/v1/imports/upload',
            files={'file': ('Master_260520_processado.xlsx', f)},
            data={'account_id': ACCOUNT_ID},
            headers=H,
        )
    data = r.json()
    batch_id = data['batch_id']
    mapping = data['detected_mapping']
    print(f"  batch_id: {batch_id}")
    print(f"  mapping: date={mapping.get('date_column')} desc={mapping.get('description_column')} amount={mapping.get('amount_column')}")

    print("\n=== Processando ===")
    r = requests.post(
        f'{API}/api/v1/imports/process',
        json={
            'batch_id': batch_id,
            'account_id': ACCOUNT_ID,
            'column_mapping': mapping,
            'validate_balance': False,
            'skip_duplicates': True,
        },
        headers=H,
    )
    res = r.json()
    print(f"  imp={res.get('imported_count')} dup={res.get('duplicate_count')} err={res.get('error_count')}")

    bal = float(requests.get(f'{API}/api/v1/accounts/{ACCOUNT_ID}', headers=H).json()['current_balance'])
    expected = -19418.73
    print(f"\n=== VALIDACAO ===")
    print(f"  saldo: R$ {bal:,.2f}")
    print(f"  esperado: R$ {expected:,.2f}")
    print(f"  diff: R$ {bal - expected:,.2f}")
    ok = abs(bal - expected) < 0.01
    print(f"  {'BATEU!' if ok else 'DIVERGENCIA'}")

    Path(tmp).unlink(missing_ok=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
