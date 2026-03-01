from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict
import statistics

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.api.deps import get_db
from app.models import Transaction, BankAccount, User
from app.utils.security import get_current_active_user
from app.services.cash_projection_service import CashProjectionService
from app.schemas.cash_projection import (
    CashProjectionItemCreate,
    CashProjectionItemUpdate,
    CashProjectionItemResponse,
    CashProjectionSummary,
    CopyMonthRequest,
    BulkProjectionCreate
)

router = APIRouter()


@router.get("/{account_id}")
def get_projection(
    account_id: int,
    months_ahead: int = Query(3, ge=1, le=12),
    method: str = Query("average", regex="^(average|trend|recurring)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Obter projeção de saldo para os próximos meses.

    Métodos:
    - average: Média simples dos últimos 6 meses
    - trend: Considera tendência de crescimento/decrescimento
    - recurring: Detecta e projeta transações recorrentes
    """
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    if method == "average":
        projections = _project_by_average(db, account, months_ahead)
    elif method == "trend":
        projections = _project_by_trend(db, account, months_ahead)
    elif method == "recurring":
        projections = _project_by_recurring(db, account, months_ahead)
    else:
        projections = _project_by_average(db, account, months_ahead)

    return {
        "account_id": account_id,
        "account_name": account.name,
        "current_balance": float(account.current_balance),
        "method": method,
        "projections": projections
    }


@router.get("/{account_id}/recurring")
def get_recurring_transactions(
    account_id: int,
    min_occurrences: int = Query(3, ge=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> List[Dict[str, Any]]:
    """Detectar transações recorrentes."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    return _detect_recurring_transactions(db, account_id, min_occurrences)


def _project_by_average(
    db: Session,
    account: BankAccount,
    months_ahead: int
) -> List[Dict]:
    """Projeção baseada em média dos últimos 6 meses."""
    six_months_ago = datetime.now() - timedelta(days=180)

    # Buscar totais mensais
    monthly_totals = (
        db.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total')
        )
        .filter(
            Transaction.account_id == account.id,
            Transaction.date >= six_months_ago
        )
        .group_by('year', 'month')
        .order_by('year', 'month')
        .all()
    )

    if not monthly_totals:
        return _generate_flat_projection(account, months_ahead)

    # Calcular média mensal
    totals = [float(m.total) for m in monthly_totals]
    avg_monthly_change = statistics.mean(totals)

    # Gerar projeções
    projections = []
    current_balance = float(account.current_balance)
    current_date = datetime.now()

    for i in range(1, months_ahead + 1):
        projection_date = current_date + timedelta(days=30 * i)
        projected_balance = current_balance + (avg_monthly_change * i)

        projections.append({
            'date': projection_date.strftime('%Y-%m-%d'),
            'month': projection_date.strftime('%B %Y'),
            'projected_balance': round(projected_balance, 2),
            'expected_change': round(avg_monthly_change, 2),
            'method': 'average'
        })

    return projections


def _project_by_trend(
    db: Session,
    account: BankAccount,
    months_ahead: int
) -> List[Dict]:
    """Projeção considerando tendência."""
    twelve_months_ago = datetime.now() - timedelta(days=365)

    monthly_totals = (
        db.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total')
        )
        .filter(
            Transaction.account_id == account.id,
            Transaction.date >= twelve_months_ago
        )
        .group_by('year', 'month')
        .order_by('year', 'month')
        .all()
    )

    if len(monthly_totals) < 3:
        return _project_by_average(db, account, months_ahead)

    totals = [float(m.total) for m in monthly_totals]

    # Calcular tendência (regressão linear simples)
    n = len(totals)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(totals)

    numerator = sum((i - x_mean) * (totals[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    slope = numerator / denominator if denominator != 0 else 0
    intercept = y_mean - slope * x_mean

    # Gerar projeções
    projections = []
    current_balance = float(account.current_balance)
    current_date = datetime.now()

    for i in range(1, months_ahead + 1):
        projection_date = current_date + timedelta(days=30 * i)
        expected_change = intercept + slope * (n + i - 1)
        projected_balance = current_balance + sum(
            intercept + slope * (n + j - 1) for j in range(1, i + 1)
        )

        projections.append({
            'date': projection_date.strftime('%Y-%m-%d'),
            'month': projection_date.strftime('%B %Y'),
            'projected_balance': round(projected_balance, 2),
            'expected_change': round(expected_change, 2),
            'trend_slope': round(slope, 2),
            'method': 'trend'
        })

    return projections


def _project_by_recurring(
    db: Session,
    account: BankAccount,
    months_ahead: int
) -> List[Dict]:
    """Projeção baseada em transações recorrentes."""
    recurring = _detect_recurring_transactions(db, account.id)

    if not recurring:
        return _project_by_average(db, account, months_ahead)

    # Calcular impacto mensal das recorrentes
    monthly_recurring = sum(r['amount'] for r in recurring)

    # Gerar projeções
    projections = []
    current_balance = float(account.current_balance)
    current_date = datetime.now()

    for i in range(1, months_ahead + 1):
        projection_date = current_date + timedelta(days=30 * i)
        projected_balance = current_balance + (monthly_recurring * i)

        projections.append({
            'date': projection_date.strftime('%Y-%m-%d'),
            'month': projection_date.strftime('%B %Y'),
            'projected_balance': round(projected_balance, 2),
            'recurring_impact': round(monthly_recurring, 2),
            'recurring_count': len(recurring),
            'method': 'recurring'
        })

    return projections


def _detect_recurring_transactions(
    db: Session,
    account_id: int,
    min_occurrences: int = 3
) -> List[Dict]:
    """Detecta transações recorrentes."""
    import re

    six_months_ago = datetime.now() - timedelta(days=180)

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.date >= six_months_ago
        )
        .all()
    )

    # Agrupar por descrição normalizada + valor aproximado
    groups = defaultdict(list)

    for t in transactions:
        # Normalizar descrição
        normalized_desc = re.sub(r'\d+', '#', t.description.lower())
        # Arredondar valor
        rounded_amount = round(float(t.amount) / 10) * 10

        key = (normalized_desc, rounded_amount)
        groups[key].append(t)

    # Filtrar grupos com ocorrências suficientes
    recurring = []
    for (desc, amount), trans_list in groups.items():
        if len(trans_list) >= min_occurrences:
            # Calcular dia médio do mês
            days = [t.date.day for t in trans_list]
            avg_day = round(statistics.mean(days))

            # Calcular valor médio exato
            avg_amount = statistics.mean([float(t.amount) for t in trans_list])

            recurring.append({
                'description': trans_list[0].description,
                'amount': round(avg_amount, 2),
                'typical_day': avg_day,
                'occurrences': len(trans_list),
                'category_id': trans_list[0].category_id,
                'category_name': trans_list[0].category.name if trans_list[0].category else None
            })

    # Ordenar por valor absoluto
    recurring.sort(key=lambda x: abs(x['amount']), reverse=True)

    return recurring


def _generate_flat_projection(
    account: BankAccount,
    months_ahead: int
) -> List[Dict]:
    """Projeção plana (sem mudança)."""
    projections = []
    current_date = datetime.now()

    for i in range(1, months_ahead + 1):
        projection_date = current_date + timedelta(days=30 * i)
        projections.append({
            'date': projection_date.strftime('%Y-%m-%d'),
            'month': projection_date.strftime('%B %Y'),
            'projected_balance': float(account.current_balance),
            'expected_change': 0,
            'method': 'flat',
            'note': 'Histórico insuficiente para projeção'
        })

    return projections


# ============================================================================
# ENDPOINTS DE PROJEÇÃO DE CAIXA MANUAL
# ============================================================================

@router.post("/cash/items", response_model=CashProjectionItemResponse)
def create_cash_projection_item(
    item_data: CashProjectionItemCreate,
    db: Session = Depends(get_db)
):
    """Cria um item de projeção de caixa."""
    service = CashProjectionService(db)
    item = service.create(item_data)
    return service._item_to_response(item)


@router.post("/cash/items/bulk")
def create_cash_projection_items_bulk(
    data: BulkProjectionCreate,
    db: Session = Depends(get_db)
):
    """Cria múltiplos itens de projeção de uma vez."""
    service = CashProjectionService(db)
    created_ids = []

    for item_data in data.items:
        item = service.create(item_data)
        created_ids.append(item.id)

    return {"created_count": len(created_ids), "item_ids": created_ids}


@router.get("/cash/items/{item_id}", response_model=CashProjectionItemResponse)
def get_cash_projection_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    """Obtém um item de projeção por ID."""
    service = CashProjectionService(db)
    item = service.get_by_id(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    return item


@router.put("/cash/items/{item_id}", response_model=CashProjectionItemResponse)
def update_cash_projection_item(
    item_id: int,
    item_data: CashProjectionItemUpdate,
    db: Session = Depends(get_db)
):
    """Atualiza um item de projeção."""
    service = CashProjectionService(db)
    item = service.update(item_id, item_data)

    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    return service._item_to_response(item)


@router.delete("/cash/items/{item_id}")
def delete_cash_projection_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    """Remove um item de projeção."""
    service = CashProjectionService(db)
    success = service.delete(item_id)

    if not success:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    return {"success": True}


@router.get("/cash/month/{month}", response_model=List[CashProjectionItemResponse])
def list_cash_projection_items_by_month(
    month: str,
    account_id: Optional[int] = Query(None, description="Filtrar por conta"),
    db: Session = Depends(get_db)
):
    """
    Lista itens de projeção de um mês.

    Args:
        month: Mês no formato YYYY-MM
        account_id: Filtrar por conta específica
    """
    service = CashProjectionService(db)
    return service.list_by_month(month, account_id)


@router.get("/cash/summary", response_model=CashProjectionSummary)
def get_cash_projection_summary(
    start_date: date = Query(..., description="Data inicial"),
    end_date: date = Query(..., description="Data final"),
    account_id: Optional[int] = Query(None, description="Conta específica"),
    db: Session = Depends(get_db)
):
    """
    Obtém resumo de projeção de caixa para um período.

    Inclui:
    - Saldo inicial (baseado em transações reais)
    - Saldos diários projetados
    - Total de entradas e saídas
    - Menor saldo no período

    Args:
        start_date: Data inicial
        end_date: Data final
        account_id: Conta específica (None = todas)
    """
    service = CashProjectionService(db)
    return service.get_projection_summary(start_date, end_date, account_id)


@router.post("/cash/copy-month")
def copy_cash_projection_month(
    data: CopyMonthRequest,
    db: Session = Depends(get_db)
):
    """
    Copia itens de projeção de um mês para outro.

    Útil para criar projeções baseadas em meses anteriores.

    Args:
        source_month: Mês de origem (YYYY-MM)
        target_month: Mês de destino (YYYY-MM)
        account_id: Conta específica (None = todas)
    """
    service = CashProjectionService(db)
    created = service.copy_month(
        data.source_month,
        data.target_month,
        data.account_id
    )

    return {
        "success": True,
        "copied_count": len(created),
        "source_month": data.source_month,
        "target_month": data.target_month
    }


@router.delete("/cash/month/{month}")
def delete_cash_projection_month(
    month: str,
    account_id: Optional[int] = Query(None, description="Conta específica"),
    db: Session = Depends(get_db)
):
    """
    Remove todos os itens de projeção de um mês.

    Args:
        month: Mês (YYYY-MM)
        account_id: Conta específica (None = todas)
    """
    service = CashProjectionService(db)
    count = service.delete_by_month(month, account_id)

    return {
        "success": True,
        "deleted_count": count,
        "month": month
    }


@router.get("/cash/initial-balance")
def get_initial_balance(
    reference_date: date = Query(..., description="Data de referência"),
    account_id: Optional[int] = Query(None, description="Conta específica"),
    db: Session = Depends(get_db)
):
    """
    Obtém saldo inicial até uma data de referência.

    O saldo é calculado como a soma de todas as transações reais
    até o dia anterior à data de referência + saldo inicial das contas.

    Args:
        reference_date: Data de referência
        account_id: Conta específica (None = todas)

    Returns:
        Saldo acumulado em BRL
    """
    service = CashProjectionService(db)
    balance = service.get_initial_balance(reference_date, account_id)

    return {
        "reference_date": reference_date.isoformat(),
        "account_id": account_id,
        "balance_brl": float(balance)
    }
