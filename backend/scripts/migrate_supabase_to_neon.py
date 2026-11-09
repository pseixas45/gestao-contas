"""
Migração de dados Supabase -> Neon (ou qualquer Postgres de destino).

NÃO altera o banco de origem (Supabase). Apenas LÊ da origem e ESCREVE no destino,
então o rollback é trivial: é só não apontar a aplicação para o Neon.

Uso (PowerShell):
    $env:NEON_DATABASE_URL = "postgresql+psycopg2://neondb_owner:SENHA@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require"
    python scripts/migrate_supabase_to_neon.py            # migra (apaga e recarrega o destino)
    python scripts/migrate_supabase_to_neon.py --verify   # só compara contagens origem x destino

A ORIGEM vem de app.config.settings.DATABASE_URL (o backend/.env, hoje = Supabase).
O DESTINO vem de NEON_DATABASE_URL.

Etapas:
  1. Cria o schema + todas as tabelas no destino a partir dos MODELOS do app
     (garante schema idêntico ao que a aplicação espera).
  2. Copia os dados tabela a tabela, na ordem de dependência de FK, com as FKs
     desabilitadas durante a carga (session_replication_role=replica; se o destino
     não permitir, cai para carga em duas passagens nas tabelas auto-referenciadas).
  3. Reseta as sequências (IDs) no destino para não colidir com novos inserts.
  4. Verifica: compara a contagem de linhas de cada tabela origem x destino.
"""
import importlib
import os
import pkgutil
import sys

# Garantir que o diretório backend/ (pai de scripts/) esteja no path para
# importar o pacote `app` quando o script é executado diretamente.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

# Registrar TODOS os modelos no Base.metadata (sem disparar o startup do main)
import app.models as _models_pkg
for _m in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.config import settings
from app.database import Base

SCHEMA = settings.DB_SCHEMA or "public"
CHUNK = 1000


def _make_engine(url: str):
    kwargs = {}
    connect_args = {}
    if SCHEMA:
        connect_args["options"] = f"-csearch_path={SCHEMA},public"
    # Pooler do Supabase (pgbouncer) não aceita prepared statements
    if "pooler.supabase.com" in url or "pgbouncer" in url:
        connect_args["prepare_threshold"] = None
    if connect_args:
        kwargs["connect_args"] = connect_args
    return create_engine(url, **kwargs)


def _self_ref_columns(table):
    """Colunas cuja FK aponta para a PRÓPRIA tabela (ex.: categories.parent_id)."""
    cols = []
    for fk in table.foreign_keys:
        if fk.column.table is table:
            cols.append(fk.parent.name)
    return cols


def copy_data(source_engine, target_engine):
    tables = list(Base.metadata.sorted_tables)  # ordem FK-safe (pais antes de filhos)

    with source_engine.connect() as src, target_engine.begin() as tgt:
        # Carga em ordem topológica de FK (pais antes de filhos). FKs NÃO são
        # desligadas (o Neon não permite session_replication_role a não-superuser):
        # a ordem de sorted_tables satisfaz as FKs entre tabelas, e as tabelas
        # auto-referenciadas (ex.: categories.parent_id) usam duas passagens.
        replica = False

        # Limpar destino (permite re-rodar a migração sem lixo)
        for t in reversed(tables):
            tgt.execute(text(f'TRUNCATE TABLE {SCHEMA}."{t.name}" RESTART IDENTITY CASCADE'))

        for t in tables:
            rows = [dict(r._mapping) for r in src.execute(t.select())]
            if not rows:
                print(f"  {t.name:35s} 0")
                continue

            self_refs = _self_ref_columns(t)
            deferred = []  # (pk_dict, {col: valor}) para 2ª passagem

            if self_refs and not replica:
                # 1ª passagem: inserir com a coluna auto-ref = NULL
                pk_cols = [c.name for c in t.primary_key.columns]
                clean = []
                for row in rows:
                    saved = {c: row[c] for c in self_refs if row.get(c) is not None}
                    if saved:
                        deferred.append(({k: row[k] for k in pk_cols}, saved))
                        row = dict(row)
                        for c in saved:
                            row[c] = None
                    clean.append(row)
                rows = clean

            for i in range(0, len(rows), CHUNK):
                tgt.execute(t.insert(), rows[i:i + CHUNK])

            # 2ª passagem: restaurar os valores auto-referenciados
            for pk, vals in deferred:
                tgt.execute(
                    t.update().where(
                        *[t.c[k] == v for k, v in pk.items()]
                    ).values(**vals)
                )

            print(f"  {t.name:35s} {len(rows)}")

        # Resetar sequências para max(id) de cada tabela
        print("[destino] resetando sequências...")
        for t in tables:
            for col in t.primary_key.columns:
                seq = tgt.execute(
                    text("SELECT pg_get_serial_sequence(:tbl, :col)"),
                    {"tbl": f"{SCHEMA}.{t.name}", "col": col.name},
                ).scalar()
                if seq:
                    tgt.execute(text(
                        f'SELECT setval(:seq, COALESCE((SELECT MAX("{col.name}") '
                        f'FROM {SCHEMA}."{t.name}"), 1))'
                    ), {"seq": seq})


def verify(source_engine, target_engine):
    print("\n=== VERIFICAÇÃO (origem x destino) ===")
    ok = True
    with source_engine.connect() as src, target_engine.connect() as tgt:
        for t in Base.metadata.sorted_tables:
            ns = src.execute(text(f'SELECT count(*) FROM {SCHEMA}."{t.name}"')).scalar()
            try:
                nt = tgt.execute(text(f'SELECT count(*) FROM {SCHEMA}."{t.name}"')).scalar()
            except Exception:
                nt = "FALTA"
            flag = "OK" if ns == nt else "DIVERGENTE <<<"
            if ns != nt:
                ok = False
            print(f"  {t.name:35s} origem={ns:>8} destino={str(nt):>8}  {flag}")
    print("=== RESULTADO:", "TUDO BATE" if ok else "HÁ DIVERGÊNCIAS", "===")
    return ok


def main():
    target_url = os.getenv("NEON_DATABASE_URL")
    if not target_url:
        sys.exit("ERRO: defina a env var NEON_DATABASE_URL com a connection string do Neon.")

    source_url = settings.DATABASE_URL
    if target_url == source_url:
        sys.exit("ERRO: destino == origem. Abortando.")

    print(f"ORIGEM : {source_url.split('@')[-1]}")
    print(f"DESTINO: {target_url.split('@')[-1]}")
    print(f"SCHEMA : {SCHEMA}\n")

    source_engine = _make_engine(source_url)
    target_engine = _make_engine(target_url)

    if "--verify" in sys.argv:
        verify(source_engine, target_engine)
        return

    # 1. Criar schema + tabelas no destino a partir dos modelos
    print("[destino] criando schema e tabelas a partir dos modelos...")
    with target_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    Base.metadata.create_all(target_engine)

    # 2 + 3. Copiar dados e resetar sequências
    print("[carga] copiando dados...")
    copy_data(source_engine, target_engine)

    # 4. Verificar
    verify(source_engine, target_engine)


if __name__ == "__main__":
    main()
