from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Configurar engine baseado no tipo de banco
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={
            "check_same_thread": False,  # Necessário para SQLite
            "timeout": 30  # Espera até 30s se banco estiver locked
        },
        echo=settings.DEBUG
    )
elif settings.DATABASE_URL.startswith("postgresql") or settings.DATABASE_URL.startswith("postgres"):
    # PostgreSQL (Supabase, Render, etc.)
    # Detectar pooler do Supabase (pgbouncer) — precisa config especial:
    #   - Sem prepared statement cache
    #   - NullPool (deixa pgbouncer fazer pooling, não SQLAlchemy)
    is_pgbouncer = "pooler.supabase.com" in settings.DATABASE_URL or "pgbouncer" in settings.DATABASE_URL

    pg_kwargs = {
        "echo": settings.DEBUG,
    }

    if is_pgbouncer:
        # pgbouncer transaction mode: cada query pode pegar conexão diferente.
        # Desabilitar prepared statements e deixar pgbouncer cuidar do pool.
        from sqlalchemy.pool import NullPool
        pg_kwargs["poolclass"] = NullPool
    else:
        pg_kwargs["pool_pre_ping"] = True
        pg_kwargs["pool_recycle"] = 300

    # Connect args — search_path do schema + opções pgbouncer-friendly
    connect_args = {}
    if settings.DB_SCHEMA:
        connect_args["options"] = f"-csearch_path={settings.DB_SCHEMA},public"
    if is_pgbouncer:
        # Desabilitar prepared statements (incompatível com pgbouncer transaction)
        connect_args["prepare_threshold"] = None
    if connect_args:
        pg_kwargs["connect_args"] = connect_args

    engine = create_engine(settings.DATABASE_URL, **pg_kwargs)
else:
    # Fallback genérico (MySQL, etc.)
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=settings.DEBUG
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency para obter sessão do banco."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Cria o schema configurado se não existir (Postgres only)."""
    if not settings.DB_SCHEMA:
        return
    if not (settings.DATABASE_URL.startswith("postgresql") or settings.DATABASE_URL.startswith("postgres")):
        return
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"'))
        conn.commit()
