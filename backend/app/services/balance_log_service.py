"""Helper para registrar alterações de saldo."""

from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.balance_log import AccountBalanceLog
from app.models.account import BankAccount


def log_balance_change(
    db: Session,
    account: BankAccount,
    new_balance: Decimal,
    reason: str,
    detail: str = None
):
    """
    Registra alteração de saldo e atualiza current_balance.

    Args:
        db: Session do banco
        account: Conta sendo alterada
        new_balance: Novo valor de current_balance
        reason: 'import', 'transaction_create', 'transaction_update',
                'transaction_delete', 'recalculate', 'revert_import', 'manual'
        detail: Informação adicional (ex: "Transaction 1234")
    """
    old_balance = account.current_balance or Decimal("0")
    change = new_balance - old_balance

    if change == 0:
        return

    log = AccountBalanceLog(
        account_id=account.id,
        old_balance=old_balance,
        new_balance=new_balance,
        change_amount=change,
        reason=reason,
        detail=detail,
    )
    db.add(log)
    account.current_balance = new_balance
