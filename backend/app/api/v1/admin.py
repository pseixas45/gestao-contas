"""
Endpoints administrativos.

Inclui:
- Reset de dados
- Reset de categorias com lista oficial
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import (
    Transaction, Category, CategoryType, CategorizationRule,
    CategorizationHistory, ImportBatch, User
)
from app.utils.security import get_current_active_user

router = APIRouter()

# Lista oficial de categorias
OFFICIAL_CATEGORIES = [
    # Despesas
    ("Aplicação", "expense", "#3B82F6"),
    ("Casamento", "expense", "#EC4899"),
    ("Compras", "expense", "#F97316"),
    ("Contas residenciais", "expense", "#10B981"),
    ("Cuidado Pessoal", "expense", "#A855F7"),
    ("Desp Conj Renata", "expense", "#F59E0B"),
    ("Despesas Trabalho", "expense", "#6366F1"),
    ("Divórcio", "expense", "#DC2626"),
    ("Educação", "expense", "#8B5CF6"),
    ("Familia", "expense", "#14B8A6"),
    ("Ginástica", "expense", "#06B6D4"),
    ("Impostos", "expense", "#DC2626"),
    ("Joceline", "expense", "#EC4899"),
    ("Juros", "expense", "#EF4444"),
    ("Lazer", "expense", "#06B6D4"),
    ("Meninos", "expense", "#3B82F6"),
    ("Moradia", "expense", "#10B981"),
    ("Reembolso Despesas", "expense", "#22C55E"),
    ("Renata", "expense", "#EC4899"),
    # Receitas
    ("Renata Reembolsos", "income", "#22C55E"),
    ("Rendimento", "income", "#22C55E"),
    ("Resgate", "income", "#3B82F6"),
    # Despesas (cont.)
    ("Restaurante", "expense", "#EF4444"),
    ("Restaurante Paulo", "expense", "#F97316"),
    # Receitas
    ("Salário", "income", "#22C55E"),
    # Despesas (cont.)
    ("Saúde", "expense", "#EC4899"),
    ("Seguros", "expense", "#6366F1"),
    ("Supermercado", "expense", "#EF4444"),
    ("Tarifas Bancárias", "expense", "#6B7280"),
    # Transferências
    ("Transferência", "transfer", "#64748B"),
    # Despesas (cont.)
    ("Transportes", "expense", "#F59E0B"),
    # Receitas
    ("Variável", "income", "#3B82F6"),
    # Despesas (cont.)
    ("Viagens", "expense", "#06B6D4"),
]


@router.post("/reset-data")
def reset_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reset completo dos dados transacionais.

    Deleta:
    - Todas as transações
    - Histórico de categorização
    - Regras de categorização
    - Lotes de importação
    - Todas as categorias

    Mantém:
    - Bancos
    - Contas bancárias (zera saldos)
    - Usuários
    """
    try:
        # Ordem de deleção respeitando FKs
        deleted_transactions = db.query(Transaction).delete()
        deleted_history = db.query(CategorizationHistory).delete()
        deleted_rules = db.query(CategorizationRule).delete()
        deleted_batches = db.query(ImportBatch).delete()
        deleted_categories = db.query(Category).delete()

        # Zerar saldos das contas
        from app.models import BankAccount
        from decimal import Decimal
        accounts = db.query(BankAccount).all()
        for account in accounts:
            account.current_balance = Decimal("0.00")

        db.commit()

        return {
            "message": "Dados resetados com sucesso",
            "deleted": {
                "transactions": deleted_transactions,
                "categorization_history": deleted_history,
                "categorization_rules": deleted_rules,
                "import_batches": deleted_batches,
                "categories": deleted_categories,
            },
            "accounts_reset": len(accounts)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao resetar dados: {str(e)}")


@router.post("/reset-categories")
def reset_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reset das categorias com lista oficial.

    ATENÇÃO: Isso irá:
    1. Remover todas as categorias existentes
    2. Remover transações (devido à FK)
    3. Remover regras de categorização
    4. Remover histórico de categorização
    5. Criar as 32 categorias oficiais
    """
    try:
        # Primeiro deletar dados dependentes
        deleted_transactions = db.query(Transaction).delete()
        deleted_history = db.query(CategorizationHistory).delete()
        deleted_rules = db.query(CategorizationRule).delete()
        deleted_categories = db.query(Category).delete()

        # Criar categorias oficiais
        for name, cat_type, color in OFFICIAL_CATEGORIES:
            category = Category(
                name=name,
                type=CategoryType(cat_type),
                color=color,
                is_active=True
            )
            db.add(category)

        db.commit()

        return {
            "message": "Categorias resetadas com sucesso",
            "deleted": {
                "transactions": deleted_transactions,
                "categorization_history": deleted_history,
                "categorization_rules": deleted_rules,
                "categories": deleted_categories,
            },
            "created_categories": len(OFFICIAL_CATEGORIES)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao resetar categorias: {str(e)}")


@router.get("/categories/official")
def get_official_categories(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna a lista oficial de categorias (sem modificar o banco).
    """
    return {
        "total": len(OFFICIAL_CATEGORIES),
        "categories": [
            {"name": name, "type": cat_type, "color": color}
            for name, cat_type, color in OFFICIAL_CATEGORIES
        ]
    }


@router.post("/reset-all")
def reset_all_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reset COMPLETO do sistema:
    1. Deleta todas as transações
    2. Deleta histórico e regras de categorização
    3. Deleta lotes de importação
    4. Deleta categorias e recria com lista oficial
    5. Zera saldos das contas
    6. Mantém: bancos, contas, usuários, taxas de câmbio
    """
    from decimal import Decimal

    try:
        # 1. Deletar transações
        deleted_transactions = db.query(Transaction).delete()

        # 2. Deletar histórico e regras
        deleted_history = db.query(CategorizationHistory).delete()
        deleted_rules = db.query(CategorizationRule).delete()

        # 3. Deletar lotes de importação
        deleted_batches = db.query(ImportBatch).delete()

        # 4. Deletar e recriar categorias
        deleted_categories = db.query(Category).delete()

        # Criar categorias oficiais
        for name, cat_type, color in OFFICIAL_CATEGORIES:
            category = Category(
                name=name,
                type=CategoryType(cat_type),
                color=color,
                is_active=True
            )
            db.add(category)

        # 5. Zerar saldos das contas
        from app.models import BankAccount
        accounts = db.query(BankAccount).all()
        for account in accounts:
            account.current_balance = Decimal("0.00")

        db.commit()

        return {
            "message": "Sistema resetado com sucesso! Categorias oficiais criadas.",
            "deleted": {
                "transactions": deleted_transactions,
                "categorization_history": deleted_history,
                "categorization_rules": deleted_rules,
                "import_batches": deleted_batches,
                "categories": deleted_categories,
            },
            "created_categories": len(OFFICIAL_CATEGORIES),
            "accounts_reset": len(accounts)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao resetar sistema: {str(e)}")
