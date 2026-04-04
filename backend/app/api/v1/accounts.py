from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db
from app.models import BankAccount, Bank, Transaction, User, AccountBalanceLog
from app.models.exchange_rate import CurrencyCode, ExchangeRate
from app.schemas.account import AccountCreate, AccountUpdate, AccountResponse, AccountBalance
from app.utils.security import get_current_active_user
from app.services.balance_log_service import log_balance_change


def _get_amount_column(currency: CurrencyCode):
    """Retorna a coluna de valor correta para a moeda da conta."""
    if currency == CurrencyCode.USD:
        return Transaction.amount_usd
    elif currency == CurrencyCode.EUR:
        return Transaction.amount_eur
    return Transaction.amount_brl


def _get_latest_rate(db: Session, currency: CurrencyCode) -> Decimal:
    """Busca a cotação de venda mais recente para a moeda."""
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.currency == currency
    ).order_by(ExchangeRate.date_ref.desc()).first()
    if rate:
        return rate.sell_rate
    return Decimal("1.00")

router = APIRouter()


@router.get("", response_model=List[AccountResponse])
def list_accounts(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar todas as contas bancárias."""
    query = db.query(BankAccount)
    if active_only:
        query = query.filter(BankAccount.is_active == True)

    accounts = query.order_by(BankAccount.name).all()

    # Buscar cotações mais recentes (uma vez, fora do loop)
    latest_rates = {
        CurrencyCode.USD: _get_latest_rate(db, CurrencyCode.USD),
        CurrencyCode.EUR: _get_latest_rate(db, CurrencyCode.EUR),
    }

    # Adicionar nome do banco e saldo em BRL
    result = []
    for account in accounts:
        account_dict = AccountResponse.model_validate(account).model_dump()
        account_dict["bank_name"] = account.bank.name if account.bank else None

        # Calcular saldo equivalente em BRL usando cotação mais recente
        if account.currency == CurrencyCode.BRL:
            account_dict["balance_brl"] = float(account.current_balance)
        else:
            rate = latest_rates.get(account.currency, Decimal("1.00"))
            account_dict["balance_brl"] = round(float(account.current_balance * rate), 2)

        result.append(AccountResponse(**account_dict))

    return result


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter conta por ID."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    result = AccountResponse.model_validate(account)
    result.bank_name = account.bank.name if account.bank else None
    return result


@router.get("/{account_id}/balance", response_model=AccountBalance)
def get_account_balance(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter saldo da conta (atual vs calculado)."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Calcular saldo na moeda da conta
    amount_col = _get_amount_column(account.currency)
    total = db.query(func.sum(amount_col)).filter(
        Transaction.account_id == account_id
    ).scalar() or Decimal("0.00")

    calculated_balance = account.initial_balance + total

    return AccountBalance(
        account_id=account_id,
        current_balance=account.current_balance,
        calculated_balance=calculated_balance,
        difference=account.current_balance - calculated_balance
    )


@router.post("", response_model=AccountResponse)
def create_account(
    account_data: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Criar nova conta bancária."""
    # Verificar se banco existe
    bank = db.query(Bank).filter(Bank.id == account_data.bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Banco não encontrado")

    account = BankAccount(**account_data.model_dump())
    account.current_balance = account.initial_balance
    db.add(account)
    db.commit()
    db.refresh(account)

    result = AccountResponse.model_validate(account)
    result.bank_name = bank.name
    return result


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    account_data: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar conta bancária."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    update_data = account_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    db.commit()
    db.refresh(account)

    result = AccountResponse.model_validate(account)
    result.bank_name = account.bank.name if account.bank else None
    return result


@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Desativar conta bancária (soft delete)."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    account.is_active = False
    db.commit()
    return {"message": "Conta desativada com sucesso"}


@router.post("/{account_id}/recalculate-balance", response_model=AccountBalance)
def recalculate_balance(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Recalcular e atualizar saldo da conta."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Calcular saldo na moeda da conta
    amount_col = _get_amount_column(account.currency)
    total = db.query(func.sum(amount_col)).filter(
        Transaction.account_id == account_id
    ).scalar() or Decimal("0.00")

    calculated_balance = account.initial_balance + total
    old_balance = account.current_balance

    # Atualizar saldo
    log_balance_change(db, account, calculated_balance,
                       'recalculate', f'Recalculated from {old_balance}')
    db.commit()

    return AccountBalance(
        account_id=account_id,
        current_balance=calculated_balance,
        calculated_balance=calculated_balance,
        difference=old_balance - calculated_balance
    )


@router.get("/{account_id}/balance-log")
def get_balance_log(
    account_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Histórico de alterações de saldo da conta."""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    logs = (
        db.query(AccountBalanceLog)
        .filter(AccountBalanceLog.account_id == account_id)
        .order_by(AccountBalanceLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": log.id,
            "old_balance": float(log.old_balance),
            "new_balance": float(log.new_balance),
            "change_amount": float(log.change_amount),
            "reason": log.reason,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
