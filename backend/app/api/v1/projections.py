from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict
import statistics
import re

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

from app.models.cash_projection import CashProjectionItem
from app.models.category import Category
from dateutil.relativedelta import relativedelta

router = APIRouter()


@router.get("/{account_id}/monthly")
def get_monthly_projection(
    account_id: int,
    month: str = Query(..., description="Mes no formato YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Projecao mensal: combina transacoes reais + itens projetados.
    Retorna timeline dia a dia com saldo acumulado.
    """
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")

    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Mes invalido (YYYY-MM)")

    month_start = date(year, mon, 1)
    if mon == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, mon + 1, 1) - timedelta(days=1)

    today = date.today()

    # 1. Determine real_cutoff = last transaction date for this account in the month
    #    (última data de carga), not necessarily today
    last_real_date = (
        db.query(func.max(Transaction.date))
        .filter(
            Transaction.account_id == account_id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
        )
        .scalar()
    )
    # Use last real transaction date if available, otherwise month_start - 1 day (no real data)
    if last_real_date and last_real_date >= month_start:
        real_cutoff = min(last_real_date, month_end)
    else:
        real_cutoff = month_start - timedelta(days=1)  # No real data in this month

    real_transactions = []
    if real_cutoff >= month_start:
        real_transactions = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == account_id,
                Transaction.date >= month_start,
                Transaction.date <= real_cutoff,
            )
            .order_by(Transaction.date)
            .all()
        )

    # 2. ALL projected items for the month (to match against real)
    all_projected = (
        db.query(CashProjectionItem)
        .filter(
            CashProjectionItem.account_id == account_id,
            CashProjectionItem.is_active == True,
            CashProjectionItem.is_confirmed == False,
            CashProjectionItem.date >= month_start,
            CashProjectionItem.date <= month_end,
        )
        .order_by(CashProjectionItem.date)
        .all()
    )

    # Also get ALL real transactions in the month for matching
    all_real_in_month = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
        )
        .all()
    )

    # 3. Match projected items against real transactions
    matched_projections = []  # (projected_item, matched_transaction, confidence)
    used_real_ids = set()

    for p in all_projected:
        best_match = None
        best_score = 0.0

        for t in all_real_in_month:
            if t.id in used_real_ids:
                continue
            score = _match_score(p, t)
            if score > best_score:
                best_score = score
                best_match = t

        if best_score >= 0.5:
            matched_projections.append((p, best_match, best_score))
            if best_match:
                used_real_ids.add(best_match.id)
        else:
            matched_projections.append((p, None, 0.0))

    # Classify: realized (>=85%), uncertain (50-85%), pending (no match)
    realized_ids = set()
    uncertain_items = []
    pending_items = []

    for p, match, score in matched_projections:
        if score >= 0.85:
            realized_ids.add(p.id)
        elif score >= 0.50:
            uncertain_items.append({
                "projected_id": p.id,
                "projected_description": p.description,
                "projected_amount": float(p.amount_brl),
                "projected_date": p.date.isoformat(),
                "matched_transaction_id": match.id if match else None,
                "matched_description": match.description if match else None,
                "matched_amount": float(match.amount) if match else None,
                "matched_date": match.date.isoformat() if match else None,
                "confidence": round(score * 100),
            })
            pending_items.append(p)  # Still show in timeline until confirmed
        else:
            pending_items.append(p)

    # Only include non-realized projected items after real_cutoff in the timeline
    projected_for_timeline = [
        p for p in pending_items if p.date > real_cutoff
    ]

    # 4. Build timeline entries
    entries = []
    for t in real_transactions:
        cat = db.query(Category).filter(Category.id == t.category_id).first() if t.category_id else None
        entries.append({
            "date": t.date.isoformat(),
            "description": t.description,
            "amount": float(t.amount),
            "category_name": cat.name if cat else None,
            "category_color": cat.color if cat else None,
            "type": "real",
            "id": t.id,
        })

    uncertain_ids = {item["projected_id"] for item in uncertain_items}
    for p in projected_for_timeline:
        cat = db.query(Category).filter(Category.id == p.category_id).first() if p.category_id else None
        entries.append({
            "date": p.date.isoformat(),
            "description": p.description,
            "amount": float(p.amount_brl),
            "category_name": cat.name if cat else None,
            "category_color": cat.color if cat else None,
            "type": "projected" if p.id not in uncertain_ids else "uncertain",
            "id": p.id,
            "is_recurring": p.is_recurring,
        })

    entries.sort(key=lambda e: e["date"])

    # 4. Calculate daily balances
    sum_month_to_cutoff = sum(float(t.amount) for t in real_transactions)
    balance_at_month_start = float(account.current_balance or 0) - sum_month_to_cutoff

    daily_balances = []
    running = balance_at_month_start
    current_day = month_start
    entry_idx = 0

    while current_day <= month_end:
        day_str = current_day.isoformat()
        day_amount = Decimal("0")

        while entry_idx < len(entries) and entries[entry_idx]["date"] == day_str:
            day_amount += Decimal(str(entries[entry_idx]["amount"]))
            entry_idx += 1

        running += float(day_amount)
        daily_balances.append({
            "date": day_str,
            "balance": round(running, 2),
            "is_past": current_day <= real_cutoff,
        })
        current_day += timedelta(days=1)

    projected_final = daily_balances[-1]["balance"] if daily_balances else float(account.current_balance or 0)

    return {
        "account_id": account_id,
        "account_name": account.name,
        "month": month,
        "current_balance": float(account.current_balance or 0),
        "balance_at_month_start": round(balance_at_month_start, 2),
        "projected_final_balance": projected_final,
        "entries": entries,
        "daily_balances": daily_balances,
        "real_count": len(real_transactions),
        "projected_count": len(projected_for_timeline),
        "realized_count": len(realized_ids),
        "uncertain_matches": uncertain_items,
    }


@router.post("/detect-recurring")
def detect_and_suggest_recurring(
    account_id: int = Query(...),
    min_occurrences: int = Query(3, ge=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> List[Dict[str, Any]]:
    """
    Detecta transacoes recorrentes com algoritmo melhorado.
    """
    import re
    import statistics as stats_module

    six_months_ago = datetime.now() - timedelta(days=180)

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.date >= six_months_ago,
        )
        .all()
    )

    groups: Dict[str, list] = defaultdict(list)
    for t in transactions:
        desc = t.description.lower().strip()
        desc = re.sub(r'\d+/\d+', '', desc)
        desc = re.sub(r'parcela\s+\d+\s+de\s+\d+', '', desc)
        desc = re.sub(r'\s+\d{2}/\d{2}(/\d{2,4})?', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        if len(desc) >= 3:
            groups[desc].append(t)

    results = []
    for desc, trans_list in groups.items():
        if len(trans_list) < min_occurrences:
            continue

        amounts = [float(t.amount) for t in trans_list]
        days = [t.date.day for t in trans_list]

        avg_amount = stats_module.mean(amounts)
        std_amount = stats_module.stdev(amounts) if len(amounts) > 1 else 0
        cv = abs(std_amount / avg_amount) if avg_amount != 0 else float('inf')

        avg_day = round(stats_module.mean(days))
        std_day = stats_module.stdev(days) if len(days) > 1 else 0

        if cv > 0.20:
            continue

        cat = trans_list[0].category
        total_months = 6
        occurrence_rate = len(trans_list) / total_months

        results.append({
            "description": trans_list[0].description,
            "normalized_description": desc,
            "avg_amount": round(avg_amount, 2),
            "std_amount": round(std_amount, 2),
            "cv": round(cv, 3),
            "avg_day": avg_day,
            "std_day": round(std_day, 1),
            "day_is_fixed": std_day < 3,
            "occurrences": len(trans_list),
            "occurrence_rate": round(occurrence_rate, 2),
            "category_id": trans_list[0].category_id,
            "category_name": cat.name if cat else None,
        })

    results.sort(key=lambda x: abs(x["avg_amount"]), reverse=True)
    return results


@router.post("/confirm-recurring")
def confirm_recurring_items(
    items: List[Dict[str, Any]],
    account_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Confirma itens recorrentes detectados, criando CashProjectionItems.
    """
    created = []
    today = date.today()

    for item in items:
        day = item.get("recurring_day", 1)
        amount = item.get("amount", 0)
        description = item.get("description", "")
        category_id = item.get("category_id")

        for month_offset in range(0, 3):
            target_date = today.replace(day=1) + relativedelta(months=month_offset)
            try:
                target_date = target_date.replace(day=min(day, 28))
            except ValueError:
                target_date = target_date.replace(day=28)

            if target_date < today and month_offset == 0:
                continue

            existing = db.query(CashProjectionItem).filter(
                CashProjectionItem.account_id == account_id,
                CashProjectionItem.description == description,
                CashProjectionItem.date == target_date,
            ).first()
            if existing:
                continue

            proj_item = CashProjectionItem(
                account_id=account_id,
                date=target_date,
                description=description,
                amount_brl=Decimal(str(amount)),
                category_id=category_id,
                is_recurring=True,
                recurring_day=day,
                source='auto_detected',
                is_active=True,
            )
            db.add(proj_item)
            created.append(proj_item)

    db.commit()
    return {"created_count": len(created)}


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


_STOPWORDS = {
    'pix', 'transf', 'transferencia', 'pag', 'pagamento', 'boleto',
    'tit', 'titulo', 'int', 'sispag', 'da', 'de', 'do', 'em', 'para',
    'banco', 'qrs', 'ted', 'doc', 'cred', 'deb',
}


def _normalize_desc(desc: str) -> str:
    """Normaliza descrição para comparação, removendo acentos."""
    import unicodedata
    s = desc.strip()
    # Fix double-encoded UTF-8 (e.g. "Ã´" → "ô") — must happen before lowercasing
    try:
        s = s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    s = s.lower()
    # Remove accents
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\d{2}/\d{2}(/\d{2,4})?', '', s)  # Remove datas inline
    s = re.sub(r'\d+\s*de\s*\d+', '', s)  # Remove parcelas
    s = re.sub(r'[^a-z\s]', '', s)  # Keep only ascii letters
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _meaningful_words(desc: str) -> set:
    """Extrai palavras significativas (sem stopwords bancárias)."""
    words = set(_normalize_desc(desc).split())
    return words - _STOPWORDS


def _match_score(projected: 'CashProjectionItem', real: 'Transaction') -> float:
    """
    Calculate match score between a projected item and a real transaction.
    Returns 0.0-1.0: >=0.85 = realized, 0.50-0.85 = uncertain, <0.50 = no match.

    Key rule: description similarity is required. If descriptions share no
    common words, the score is capped below 0.50 (no match).
    """
    # Same sign check first
    p_sign = 1 if float(projected.amount_brl) >= 0 else -1
    r_sign = 1 if float(real.amount) >= 0 else -1
    if p_sign != r_sign:
        return 0.0

    # 1. Amount similarity (0-0.40)
    p_amt = abs(float(projected.amount_brl))
    r_amt = abs(float(real.amount))
    amt_score = 0.0
    if p_amt == 0 and r_amt == 0:
        amt_score = 0.40
    elif max(p_amt, r_amt) > 0:
        ratio = min(p_amt, r_amt) / max(p_amt, r_amt)
        if ratio >= 0.98:
            amt_score = 0.40
        elif ratio >= 0.95:
            amt_score = 0.35
        elif ratio >= 0.85:
            amt_score = 0.25
        elif ratio >= 0.70:
            amt_score = 0.15
        else:
            return 0.0  # Too different in amount

    # 2. Description similarity (0-0.45)
    # Use meaningful words (excluding banking stopwords like "pix", "transf", "boleto")
    p_words = _meaningful_words(projected.description)
    r_words = _meaningful_words(real.description)
    desc_score = 0.0

    if p_words and r_words:
        common = p_words & r_words
        if common:
            p_ratio = len(common) / len(p_words)
            r_ratio = len(common) / len(r_words)
            desc_score = max(p_ratio, r_ratio) * 0.45

    # 3. Date proximity (0-0.15)
    day_diff = abs((projected.date - real.date).days)
    date_score = 0.0
    if day_diff == 0:
        date_score = 0.15
    elif day_diff <= 2:
        date_score = 0.12
    elif day_diff <= 5:
        date_score = 0.08
    elif day_diff <= 10:
        date_score = 0.03

    total = amt_score + desc_score + date_score

    # KEY RULE: no description overlap → cap below threshold
    # Exception: very high amount match (>=98%) + close date → allow as uncertain
    if desc_score == 0:
        if amt_score >= 0.40 and date_score >= 0.12:
            # Near-exact amount + close date: allow as uncertain (50-84%)
            total = min(total, 0.55)
        else:
            total = min(total, 0.45)

    return total


@router.post("/confirm-match")
def confirm_projection_match(
    projected_id: int = Query(...),
    action: str = Query(..., description="'confirm' or 'reject'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Confirm or reject a match between a projected item and a real transaction.
    - confirm: marks the projected item as confirmed (won't appear in projections)
    - reject: keeps the projected item active (will appear in future projections)
    """
    item = db.query(CashProjectionItem).filter(CashProjectionItem.id == projected_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item projetado não encontrado")

    if action == "confirm":
        item.is_confirmed = True
        db.commit()
        return {"message": "Item marcado como realizado", "id": projected_id}
    elif action == "reject":
        # Just return OK — the item stays active and will be shown as projected
        return {"message": "Match rejeitado, item mantido na projeção", "id": projected_id}
    else:
        raise HTTPException(status_code=400, detail="Ação deve ser 'confirm' ou 'reject'")


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
