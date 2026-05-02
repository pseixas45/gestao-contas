"""Migração de dados SQLite -> PostgreSQL (Supabase).

Pré-requisitos:
1. .env do backend configurado com DATABASE_URL apontando para Postgres
   e DB_SCHEMA definido (ex: 'gestao_contas')
2. psycopg2-binary instalado (pip install -r backend/requirements.txt)

O que faz:
1. Conecta ao SQLite local (gestao_contas.db)
2. Conecta ao Postgres via DATABASE_URL
3. Cria schema (se DB_SCHEMA setado) e tabelas
4. Copia todos os dados tabela por tabela, na ordem de dependência
5. Reseta sequences do Postgres para o próximo ID após o maior existente

Uso:
    cd backend
    python ../scripts/migrate_sqlite_to_postgres.py [--dry-run]
"""
import os
import sys
import sqlite3
import argparse
from pathlib import Path

# Garantir que o backend está no path
BACKEND_DIR = Path(__file__).parent.parent / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

# Path do SQLite local
SQLITE_PATH = BACKEND_DIR / 'gestao_contas.db'

# Ordem de cópia respeitando foreign keys (filhos depois dos pais)
TABLE_ORDER = [
    'users',
    'banks',
    'categories',
    'bank_accounts',
    'exchange_rates',
    'categorization_rules',
    'categorization_history',
    'import_batches',
    'transactions',
    'budgets',
    'cash_projection_items',
    'saved_report_views',
    'import_templates',
    'account_balance_logs',
    'categorization_history_log',  # se existir
]


def get_sqlite_tables():
    """Lista as tabelas reais do SQLite."""
    conn = sqlite3.connect(str(SQLITE_PATH))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return tables


def get_boolean_columns(pg_session, table_name):
    """Lista colunas booleanas no Postgres para conversão de tipo."""
    from sqlalchemy import text
    r = pg_session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = :t AND data_type = 'boolean'
    """), {'t': table_name})
    return {row[0] for row in r}


def coerce_value(val, col_name, bool_cols):
    """Converte valores do SQLite para tipos compatíveis com Postgres."""
    if val is None:
        return None
    # SQLite armazena boolean como 0/1; converter para bool real
    if col_name in bool_cols and isinstance(val, int):
        return bool(val)
    return val


def copy_table(sqlite_conn, pg_session, table_name, dry_run=False):
    """Copia todos os registros de uma tabela do SQLite para o Postgres."""
    cur = sqlite_conn.cursor()
    cur.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()
    if not rows:
        print(f"  [{table_name}] vazio, pulando")
        return 0

    # Pegar nomes das colunas
    cols = [d[0] for d in cur.description]
    cols_quoted = ', '.join(f'"{c}"' for c in cols)
    placeholders = ', '.join(f':{c}' for c in cols)

    if dry_run:
        print(f"  [{table_name}] DRY-RUN: copiaria {len(rows)} registros")
        return len(rows)

    from sqlalchemy import text

    # Detectar colunas booleanas para coerção
    bool_cols = get_boolean_columns(pg_session, table_name)

    # Inserir em batch com ON CONFLICT DO NOTHING (idempotente)
    sql = text(f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders}) ON CONFLICT DO NOTHING')

    inserted = 0
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        params = [
            {c: coerce_value(v, c, bool_cols) for c, v in zip(cols, row)}
            for row in batch
        ]
        try:
            result = pg_session.execute(sql, params)
            pg_session.commit()
            inserted += result.rowcount if result.rowcount and result.rowcount > 0 else len(batch)
        except Exception as e:
            pg_session.rollback()
            print(f"  [{table_name}] ERRO no batch {i}: {str(e)[:120]}")
            # Tentar registro a registro
            for p in params:
                try:
                    pg_session.execute(sql, p)
                    pg_session.commit()
                    inserted += 1
                except Exception as e2:
                    pg_session.rollback()
                    print(f"    skip 1 reg: {str(e2)[:120]}")
    print(f"  [{table_name}] {inserted}/{len(rows)} registros copiados")
    return inserted


def reset_sequences(pg_session, schema):
    """Reseta sequences do Postgres para MAX(id)+1 de cada tabela."""
    from sqlalchemy import text
    schema_qual = f'"{schema}".' if schema else ''
    print("\n=== Resetando sequences ===")
    for table in TABLE_ORDER:
        try:
            r = pg_session.execute(text(f'SELECT MAX(id) FROM {schema_qual}"{table}"'))
            max_id = r.scalar()
            if max_id:
                # Nome típico de sequence: <schema>.<table>_id_seq
                seq = f'{schema_qual}"{table}_id_seq"' if schema else f'"{table}_id_seq"'
                pg_session.execute(text(f"SELECT setval('{seq}', {max_id})"))
                pg_session.commit()
                print(f"  [{table}] sequence -> {max_id}")
        except Exception as e:
            print(f"  [{table}] skip sequence: {str(e)[:80]}")
            pg_session.rollback()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Simula sem inserir')
    args = parser.parse_args()

    if not SQLITE_PATH.exists():
        print(f"ERRO: SQLite não encontrado em {SQLITE_PATH}")
        return 1

    # Importar config DEPOIS de garantir cwd
    os.chdir(str(BACKEND_DIR))
    from app.config import settings
    from app.database import engine, Base, ensure_schema, SessionLocal

    if settings.DATABASE_URL.startswith('sqlite'):
        print("ERRO: DATABASE_URL ainda é SQLite. Configure .env com DATABASE_URL=postgresql+psycopg2://...")
        return 1

    print(f"Origem: {SQLITE_PATH}")
    print(f"Destino: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    print(f"Schema: {settings.DB_SCHEMA or '(public)'}")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'EXECUÇÃO REAL'}")
    print()

    # 1. Garantir schema e criar tabelas no Postgres
    if not args.dry_run:
        print("=== Criando schema e tabelas no Postgres ===")
        ensure_schema()
        # Importar TODOS os modelos para registrar no Base.metadata
        # (basta importar app.models que executa __init__.py)
        from app import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        print("  OK")

    # 2. Copiar dados
    print("\n=== Copiando dados ===")
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    pg_session = SessionLocal()

    try:
        existing_tables = get_sqlite_tables()
        for table in TABLE_ORDER:
            if table not in existing_tables:
                print(f"  [{table}] não existe no SQLite, pulando")
                continue
            copy_table(sqlite_conn, pg_session, table, dry_run=args.dry_run)

        # 3. Reset sequences
        if not args.dry_run:
            reset_sequences(pg_session, settings.DB_SCHEMA)

    finally:
        sqlite_conn.close()
        pg_session.close()

    print("\n=== Migração concluída ===")
    if args.dry_run:
        print("Use sem --dry-run para aplicar de verdade.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
