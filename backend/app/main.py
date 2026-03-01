"""
Gestão de Contas - API Backend

Sistema de gestão de contas bancárias pessoais com:
- Importação de extratos (CSV, Excel, PDF)
- Categorização automática
- Projeção de saldos
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.api.v1.router import api_router

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)

# Criar tabelas no banco
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description="Sistema de Gestão de Contas Bancárias",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003", "http://localhost:3004", "http://localhost:3005", "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3002", "http://127.0.0.1:3003", "http://127.0.0.1:3004", "http://127.0.0.1:3005"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir rotas da API
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    """Endpoint raiz - verificação de saúde."""
    return {
        "message": "Gestão de Contas API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Verificação de saúde da aplicação."""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """Evento de inicialização - criar dados iniciais."""
    from sqlalchemy.orm import Session
    from app.database import SessionLocal
    from app.models import Bank, Category, CategoryType

    db: Session = SessionLocal()

    try:
        # Criar bancos padrão se não existirem
        if db.query(Bank).count() == 0:
            banks = [
                Bank(name="Itaú", code="341", color="#FF6600"),
                Bank(name="Bradesco", code="237", color="#CC092F"),
                Bank(name="Nubank", code="260", color="#820AD1"),
                Bank(name="Banco do Brasil", code="001", color="#FFCC00"),
                Bank(name="Santander", code="033", color="#EC0000"),
                Bank(name="Caixa Econômica", code="104", color="#005CA9"),
                Bank(name="Inter", code="077", color="#FF7A00"),
                Bank(name="C6 Bank", code="336", color="#1A1A1A"),
                Bank(name="BTG Pactual", code="208", color="#000F9F"),
                Bank(name="XP Investimentos", code="102", color="#FFD500"),
            ]
            for bank in banks:
                db.add(bank)
            db.commit()

        # Criar categorias padrão se não existirem
        if db.query(Category).count() == 0:
            categories = [
                # Despesas
                Category(name="Alimentação", type=CategoryType.EXPENSE, color="#EF4444", icon="utensils"),
                Category(name="Transporte", type=CategoryType.EXPENSE, color="#F59E0B", icon="car"),
                Category(name="Moradia", type=CategoryType.EXPENSE, color="#10B981", icon="home"),
                Category(name="Saúde", type=CategoryType.EXPENSE, color="#EC4899", icon="heart"),
                Category(name="Educação", type=CategoryType.EXPENSE, color="#8B5CF6", icon="book"),
                Category(name="Lazer", type=CategoryType.EXPENSE, color="#06B6D4", icon="gamepad"),
                Category(name="Compras", type=CategoryType.EXPENSE, color="#F97316", icon="shopping-bag"),
                Category(name="Serviços", type=CategoryType.EXPENSE, color="#6366F1", icon="settings"),
                Category(name="Impostos", type=CategoryType.EXPENSE, color="#DC2626", icon="file-text"),
                Category(name="Outros Gastos", type=CategoryType.EXPENSE, color="#6B7280", icon="more-horizontal"),
                # Receitas
                Category(name="Salário", type=CategoryType.INCOME, color="#22C55E", icon="briefcase"),
                Category(name="Investimentos", type=CategoryType.INCOME, color="#3B82F6", icon="trending-up"),
                Category(name="Freelance", type=CategoryType.INCOME, color="#A855F7", icon="laptop"),
                Category(name="Outras Receitas", type=CategoryType.INCOME, color="#14B8A6", icon="plus-circle"),
                # Transferências
                Category(name="Transferência", type=CategoryType.TRANSFER, color="#64748B", icon="repeat"),
            ]
            for cat in categories:
                db.add(cat)
            db.commit()

        # Migração: adicionar colunas date_start/date_end em import_batches
        _run_migrations(db)

        # Atualizar cotações de câmbio
        await _update_exchange_rates(db)

    finally:
        db.close()


def _run_migrations(db):
    """Executa migrações manuais (ALTER TABLE) se necessário."""
    from sqlalchemy import text, inspect
    logger = logging.getLogger("migrations")

    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("import_batches")]

    if "date_start" not in columns:
        logger.info("Migrando import_batches: adicionando date_start, date_end...")
        db.execute(text("ALTER TABLE import_batches ADD COLUMN date_start DATE"))
        db.execute(text("ALTER TABLE import_batches ADD COLUMN date_end DATE"))
        db.commit()
        logger.info("Migração concluída.")

    # Backfill: preencher date_start/date_end de batches que não têm
    unfilled = db.execute(text(
        "SELECT id FROM import_batches WHERE date_start IS NULL AND imported_records > 0"
    )).fetchall()

    if unfilled:
        logger.info(f"Backfill: preenchendo datas de {len(unfilled)} batches...")
        for (batch_id,) in unfilled:
            result = db.execute(text(
                "SELECT MIN(date), MAX(date) FROM transactions WHERE import_batch_id = :bid"
            ), {"bid": batch_id}).fetchone()
            if result and result[0]:
                db.execute(text(
                    "UPDATE import_batches SET date_start = :ds, date_end = :de WHERE id = :bid"
                ), {"ds": result[0], "de": result[1], "bid": batch_id})
        db.commit()
        logger.info("Backfill concluído.")


async def _update_exchange_rates(db):
    """Atualiza cotações do BCB desde a última disponível até hoje."""
    from datetime import date, timedelta
    from app.models.exchange_rate import ExchangeRate, CurrencyCode
    from app.services.exchange_service import ExchangeService

    logger = logging.getLogger("exchange_update")

    try:
        # Descobrir última cotação no banco
        latest = db.query(ExchangeRate.date_ref).order_by(
            ExchangeRate.date_ref.desc()
        ).first()

        if latest:
            start_date = latest[0] + timedelta(days=1)
        else:
            # Se não tem nenhuma, buscar últimos 30 dias
            start_date = date.today() - timedelta(days=30)

        end_date = date.today()

        if start_date > end_date:
            logger.info(f"Cotações já atualizadas (última: {latest[0]})")
            return

        logger.info(f"Atualizando cotações de {start_date} até {end_date}...")

        exchange_service = ExchangeService(db)
        stats = await exchange_service.update_rates_for_period(start_date, end_date)

        logger.info(
            f"Cotações atualizadas: {stats['usd_updated']} USD, "
            f"{stats['eur_updated']} EUR "
            f"({stats['total_days']} dias verificados)"
        )

        if stats.get("errors"):
            for err in stats["errors"][:5]:
                logger.warning(f"  Erro: {err}")

    except Exception as e:
        logger.error(f"Erro ao atualizar cotações: {e}")
