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
    # PostgreSQL (Supabase, Render, etc.) com pool pre-ping para reconexões
    pg_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "echo": settings.DEBUG,
    }

    # Se DB_SCHEMA configurado, setar search_path via connect_args
    # (mais robusto que event listener — aplica em TODA nova conexão do pool).
    if settings.DB_SCHEMA:
        pg_kwargs["connect_args"] = {
            "options": f"-csearch_path={settings.DB_SCHEMA},public"
        }

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
