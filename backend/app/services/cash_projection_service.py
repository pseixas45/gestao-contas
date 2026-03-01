"""
Serviço de Projeção de Caixa.

Gerencia itens de projeção e calcula saldos futuros.
Sempre em BRL para simplificar consolidação.
"""

from typing import List, Optional
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract

from app.models.cash_projection import CashProjectionItem
from app.models.transaction import Transaction
from app.models.account import BankAccount
from app.models.category import Category
from app.schemas.cash_projection import (
    CashProjectionItemCreate,
    CashProjectionItemUpdate,
    CashProjectionItemResponse,
    CashProjectionDayBalance,
    CashProjectionSummary
)


class CashProjectionService:
    """Serviço para projeção de caixa."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, item_data: CashProjectionItemCreate) -> CashProjectionItem:
        """Cria um item de projeção."""
        item = CashProjectionItem(
            account_id=item_data.account_id,
            date=item_data.date,
            description=item_data.description,
            amount_brl=item_data.amount_brl,
            category_id=item_data.category_id,
            is_recurring=item_data.is_recurring,
            recurring_day=item_data.recurring_day
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(
        self,
        item_id: int,
        item_data: CashProjectionItemUpdate
    ) -> Optional[CashProjectionItem]:
        """Atualiza um item de projeção."""
        item = self.db.query(CashProjectionItem).filter(
            CashProjectionItem.id == item_id
        ).first()

        if not item:
            return None

        update_data = item_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> bool:
        """Remove um item de projeção."""
        item = self.db.query(CashProjectionItem).filter(
            CashProjectionItem.id == item_id
        ).first()

        if not item:
            return False

        self.db.delete(item)
        self.db.commit()
        return True

    def get_by_id(self, item_id: int) -> Optional[CashProjectionItemResponse]:
        """Obtém um item por ID."""
        item = self.db.query(CashProjectionItem).filter(
            CashProjectionItem.id == item_id
        ).first()

        if not item:
            return None

        return self._item_to_response(item)

    def list_by_period(
        self,
        start_date: date,
        end_date: date,
        account_id: Optional[int] = None
    ) -> List[CashProjectionItemResponse]:
        """Lista itens de projeção em um período."""
        query = self.db.query(CashProjectionItem).filter(
            and_(
                CashProjectionItem.date >= start_date,
                CashProjectionItem.date <= end_date
            )
        )

        if account_id:
            query = query.filter(CashProjectionItem.account_id == account_id)

        items = query.order_by(CashProjectionItem.date).all()

        return [self._item_to_response(item) for item in items]

    def list_by_month(
        self,
        month: str,
        account_id: Optional[int] = None
    ) -> List[CashProjectionItemResponse]:
        """Lista itens de projeção de um mês."""
        year, month_num = map(int, month.split('-'))

        query = self.db.query(CashProjectionItem).filter(
            and_(
                extract('year', CashProjectionItem.date) == year,
                extract('month', CashProjectionItem.date) == month_num
            )
        )

        if account_id:
            query = query.filter(CashProjectionItem.account_id == account_id)

        items = query.order_by(CashProjectionItem.date).all()

        return [self._item_to_response(item) for item in items]

    def get_initial_balance(
        self,
        reference_date: date,
        account_id: Optional[int] = None
    ) -> Decimal:
        """
        Calcula saldo inicial até uma data de referência.

        O saldo inicial é a soma de todas as transações reais
        até o último dia antes da data de referência.

        Args:
            reference_date: Data de referência
            account_id: Conta específica (None = todas)

        Returns:
            Saldo acumulado em BRL
        """
        query = self.db.query(func.sum(Transaction.amount_brl)).filter(
            Transaction.date < reference_date
        )

        if account_id:
            query = query.filter(Transaction.account_id == account_id)

        total = query.scalar() or Decimal("0.00")

        # Adicionar saldo inicial das contas
        acc_query = self.db.query(func.sum(BankAccount.initial_balance))
        if account_id:
            acc_query = acc_query.filter(BankAccount.id == account_id)
        else:
            acc_query = acc_query.filter(BankAccount.is_active == True)

        initial = acc_query.scalar() or Decimal("0.00")

        return total + initial

    def get_projection_summary(
        self,
        start_date: date,
        end_date: date,
        account_id: Optional[int] = None
    ) -> CashProjectionSummary:
        """
        Gera resumo de projeção de caixa para um período.

        Args:
            start_date: Data inicial
            end_date: Data final
            account_id: Conta específica (None = todas)

        Returns:
            Resumo com saldos diários
        """
        # Calcular saldo inicial
        initial_balance = self.get_initial_balance(start_date, account_id)

        # Buscar itens de projeção
        items = self.list_by_period(start_date, end_date, account_id)

        # Agrupar por data
        daily_items = {}
        for item in items:
            d = item.date
            if d not in daily_items:
                daily_items[d] = []
            daily_items[d].append(item)

        # Calcular saldos diários
        daily_balances = []
        running_balance = initial_balance
        total_entries = Decimal("0.00")
        total_exits = Decimal("0.00")
        min_balance = initial_balance
        min_balance_date = start_date

        current = start_date
        while current <= end_date:
            entries = Decimal("0.00")
            exits = Decimal("0.00")

            if current in daily_items:
                for item in daily_items[current]:
                    if item.amount_brl > 0:
                        entries += item.amount_brl
                    else:
                        exits += item.amount_brl

            closing_balance = running_balance + entries + exits

            daily_balances.append(CashProjectionDayBalance(
                date=current,
                opening_balance=running_balance,
                entries=entries,
                exits=abs(exits),
                closing_balance=closing_balance
            ))

            total_entries += entries
            total_exits += exits

            if closing_balance < min_balance:
                min_balance = closing_balance
                min_balance_date = current

            running_balance = closing_balance
            current += timedelta(days=1)

        # Obter nome da conta
        account_name = None
        if account_id:
            account = self.db.query(BankAccount).filter(
                BankAccount.id == account_id
            ).first()
            if account:
                account_name = account.name

        return CashProjectionSummary(
            account_id=account_id,
            account_name=account_name,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            total_entries=total_entries,
            total_exits=abs(total_exits),
            final_balance=running_balance,
            min_balance=min_balance,
            min_balance_date=min_balance_date,
            daily_balances=daily_balances
        )

    def copy_month(
        self,
        source_month: str,
        target_month: str,
        account_id: Optional[int] = None
    ) -> List[CashProjectionItem]:
        """
        Copia itens de projeção de um mês para outro.

        Args:
            source_month: Mês de origem (YYYY-MM)
            target_month: Mês de destino (YYYY-MM)
            account_id: Conta específica (None = todas)

        Returns:
            Lista de itens criados
        """
        source_year, source_m = map(int, source_month.split('-'))
        target_year, target_m = map(int, target_month.split('-'))

        # Buscar itens do mês de origem
        query = self.db.query(CashProjectionItem).filter(
            and_(
                extract('year', CashProjectionItem.date) == source_year,
                extract('month', CashProjectionItem.date) == source_m
            )
        )

        if account_id:
            query = query.filter(CashProjectionItem.account_id == account_id)

        source_items = query.all()

        created = []
        for item in source_items:
            # Calcular nova data mantendo o dia
            try:
                new_date = date(target_year, target_m, item.date.day)
            except ValueError:
                # Dia não existe no mês destino
                import calendar
                last_day = calendar.monthrange(target_year, target_m)[1]
                new_date = date(target_year, target_m, last_day)

            new_item = CashProjectionItem(
                account_id=item.account_id,
                date=new_date,
                description=item.description,
                amount_brl=item.amount_brl,
                category_id=item.category_id,
                is_recurring=item.is_recurring,
                recurring_day=item.recurring_day,
                is_confirmed=False
            )
            self.db.add(new_item)
            created.append(new_item)

        self.db.commit()

        for item in created:
            self.db.refresh(item)

        return created

    def delete_by_month(
        self,
        month: str,
        account_id: Optional[int] = None
    ) -> int:
        """
        Remove todos os itens de projeção de um mês.

        Args:
            month: Mês (YYYY-MM)
            account_id: Conta específica (None = todas)

        Returns:
            Quantidade de itens removidos
        """
        year, month_num = map(int, month.split('-'))

        query = self.db.query(CashProjectionItem).filter(
            and_(
                extract('year', CashProjectionItem.date) == year,
                extract('month', CashProjectionItem.date) == month_num
            )
        )

        if account_id:
            query = query.filter(CashProjectionItem.account_id == account_id)

        count = query.count()
        query.delete(synchronize_session=False)
        self.db.commit()

        return count

    def _item_to_response(self, item: CashProjectionItem) -> CashProjectionItemResponse:
        """Converte item para response."""
        account = self.db.query(BankAccount).filter(
            BankAccount.id == item.account_id
        ).first()

        category = None
        if item.category_id:
            category = self.db.query(Category).filter(
                Category.id == item.category_id
            ).first()

        return CashProjectionItemResponse(
            id=item.id,
            account_id=item.account_id,
            date=item.date,
            description=item.description,
            amount_brl=item.amount_brl,
            category_id=item.category_id,
            is_recurring=item.is_recurring,
            recurring_day=item.recurring_day,
            is_confirmed=item.is_confirmed,
            account_name=account.name if account else None,
            category_name=category.name if category else None
        )
