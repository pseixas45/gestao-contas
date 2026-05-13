"""
Serviço de Relatórios Multi-Moeda.

Gera relatórios de despesas, tendências e comparações.
Suporta múltiplas moedas (BRL, USD, EUR).
"""

from typing import List, Optional
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, extract, case

from app.models.transaction import Transaction
from app.models.category import Category
from app.models.budget import Budget
from app.models.account import BankAccount
from app.models.bank import Bank
from app.models.exchange_rate import CurrencyCode
from app.schemas.report import (
    MonthlyExpense,
    MonthlyExpenseReport,
    CategoryTrend,
    ExpenseTrend,
    ExpenseTrendReport,
    BudgetVsActualItem,
    BudgetVsActualReport,
    ProjectedExpense,
    RealPlusProjectedReport,
    IncomeVsExpenseMonth,
    IncomeVsExpenseReport,
    AccountBalanceReport,
    AccountsBalanceReport,
    CategoryMonthlyRow,
    CategoryGroupTotals,
    CategoryMonthlyPivotReport,
    ReportTransactionDetail,
)


class ReportService:
    """Serviço para geração de relatórios."""

    def __init__(self, db: Session):
        self.db = db

    def _get_amount_column(self, currency: CurrencyCode):
        """Retorna a coluna de amount correta para a moeda."""
        if currency == CurrencyCode.USD:
            return Transaction.amount_usd
        elif currency == CurrencyCode.EUR:
            return Transaction.amount_eur
        return Transaction.amount_brl

    def get_monthly_expenses(
        self,
        month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        account_ids: Optional[List[int]] = None
    ) -> MonthlyExpenseReport:
        """
        Obtém relatório de despesas por categoria em um mês.

        Args:
            month: Mês no formato YYYY-MM
            currency: Moeda para exibição
            account_ids: Filtrar por contas específicas

        Returns:
            Relatório com despesas por categoria
        """
        year, month_num = map(int, month.split('-'))
        amount_col = self._get_amount_column(currency)

        # Query base
        query = self.db.query(
            Transaction.category_id,
            func.sum(amount_col).label('total')
        ).filter(
            and_(
                extract('year', Transaction.date) == year,
                extract('month', Transaction.date) == month_num,
                amount_col < 0  # Apenas despesas
            )
        )

        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))

        # Agrupar por categoria
        results = query.group_by(Transaction.category_id).all()

        # Buscar categorias
        categories = {
            c.id: c for c in self.db.query(Category).all()
        }

        # Calcular total
        total = sum(abs(r.total) for r in results if r.total)

        # Montar resposta
        items = []
        for r in results:
            if r.category_id and r.total:
                cat = categories.get(r.category_id)
                amount = abs(r.total)
                percentage = float(amount / total * 100) if total > 0 else 0

                items.append(MonthlyExpense(
                    category_id=r.category_id,
                    category_name=cat.name if cat else "Sem categoria",
                    category_color=cat.color if cat else None,
                    amount=amount.quantize(Decimal("0.01")),
                    percentage=round(percentage, 1)
                ))

        # Ordenar por valor
        items.sort(key=lambda x: x.amount, reverse=True)

        return MonthlyExpenseReport(
            month=month,
            currency=currency,
            total=total.quantize(Decimal("0.01")) if total else Decimal("0.00"),
            categories=items
        )

    def get_expense_trend(
        self,
        start_month: str,
        end_month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        category_ids: Optional[List[int]] = None
    ) -> ExpenseTrendReport:
        """Tendência de despesas por categoria via GROUP BY único."""
        amount_col = self._get_amount_column(currency)

        start_year, start_m = map(int, start_month.split('-'))
        end_year, end_m = map(int, end_month.split('-'))
        start_date = date(start_year, start_m, 1)
        if end_m == 12:
            end_date_real = date(end_year + 1, 1, 1) - relativedelta(days=1)
        else:
            end_date_real = date(end_year, end_m + 1, 1) - relativedelta(days=1)

        months = []
        current = start_date
        while current <= date(end_year, end_m, 1):
            months.append(current.strftime('%Y-%m'))
            current += relativedelta(months=1)

        if category_ids:
            categories = self.db.query(Category).filter(Category.id.in_(category_ids)).all()
        else:
            categories = self.db.query(Category).filter(Category.is_active == True).all()
        cat_ids = {c.id for c in categories}

        rows = self.db.query(
            Transaction.category_id,
            extract('year', Transaction.date).label('yr'),
            extract('month', Transaction.date).label('mo'),
            func.sum(amount_col).label('total'),
        ).filter(
            Transaction.date >= start_date,
            Transaction.date <= end_date_real,
            amount_col < 0,
        ).group_by(
            Transaction.category_id,
            extract('year', Transaction.date),
            extract('month', Transaction.date),
        ).all()

        bucket: dict[int, dict[str, Decimal]] = {}
        for cat_id, yr, mo, total in rows:
            if cat_id is None or cat_id not in cat_ids or total is None:
                continue
            m_str = f"{int(yr):04d}-{int(mo):02d}"
            bucket.setdefault(cat_id, {})[m_str] = abs(total)

        category_trends = []
        for cat in categories:
            month_amounts = bucket.get(cat.id, {})
            cat_months = [
                ExpenseTrend(month=m, amount=month_amounts.get(m, Decimal("0.00")).quantize(Decimal("0.01")))
                for m in months
            ]
            total = sum(month_amounts.values(), Decimal("0.00"))
            average = (total / len(months)).quantize(Decimal("0.01")) if months else Decimal("0.00")
            category_trends.append(CategoryTrend(
                category_id=cat.id,
                category_name=cat.name,
                category_color=cat.color,
                months=cat_months,
                average=average,
            ))

        category_trends.sort(key=lambda x: x.average, reverse=True)
        return ExpenseTrendReport(
            start_month=start_month,
            end_month=end_month,
            currency=currency,
            categories=category_trends,
        )

    def get_budget_vs_actual(
        self,
        month: str,
        currency: CurrencyCode = CurrencyCode.BRL
    ) -> BudgetVsActualReport:
        """
        Compara orçado vs realizado (Versão 2 do relatório).

        Args:
            month: Mês (YYYY-MM)
            currency: Moeda

        Returns:
            Comparação detalhada
        """
        year, month_num = map(int, month.split('-'))
        amount_col = self._get_amount_column(currency)

        # Buscar orçamentos
        budgets = {
            b.category_id: b.amount_brl
            for b in self.db.query(Budget).filter(Budget.month == month).all()
        }

        # Buscar categorias
        categories = self.db.query(Category).filter(Category.is_active == True).all()

        # Realizados em uma única query agregada
        first_day = date(year, month_num, 1)
        if month_num == 12:
            last_day = date(year + 1, 1, 1) - relativedelta(days=1)
        else:
            last_day = date(year, month_num + 1, 1) - relativedelta(days=1)
        actual_rows = self.db.query(
            Transaction.category_id,
            func.sum(amount_col).label('total'),
        ).filter(
            Transaction.date >= first_day,
            Transaction.date <= last_day,
            amount_col < 0,
        ).group_by(Transaction.category_id).all()
        actuals_by_cat = {row.category_id: abs(row.total or Decimal("0.00")) for row in actual_rows}

        items = []
        total_budgeted = Decimal("0.00")
        total_actual = Decimal("0.00")

        for cat in categories:
            budgeted = budgets.get(cat.id, Decimal("0.00"))
            actual = actuals_by_cat.get(cat.id, Decimal("0.00"))
            difference = budgeted - actual
            percentage = float(actual / budgeted * 100) if budgeted > 0 else 0

            # Determinar status
            if budgeted == 0:
                status = "ok"
            elif percentage > 100:
                status = "over"
            elif percentage > 80:
                status = "warning"
            else:
                status = "ok"

            total_budgeted += budgeted
            total_actual += actual

            items.append(BudgetVsActualItem(
                category_id=cat.id,
                category_name=cat.name,
                category_color=cat.color,
                budgeted=budgeted,
                actual=actual.quantize(Decimal("0.01")),
                difference=difference.quantize(Decimal("0.01")),
                percentage=round(percentage, 1),
                status=status
            ))

        # Ordenar por percentual
        items.sort(key=lambda x: x.percentage, reverse=True)

        total_difference = total_budgeted - total_actual
        overall_percentage = (
            float(total_actual / total_budgeted * 100)
            if total_budgeted > 0 else 0
        )

        return BudgetVsActualReport(
            month=month,
            currency=currency,
            total_budgeted=total_budgeted,
            total_actual=total_actual.quantize(Decimal("0.01")),
            total_difference=total_difference.quantize(Decimal("0.01")),
            overall_percentage=round(overall_percentage, 1),
            items=items
        )

    def get_real_plus_projected(
        self,
        month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        reference_date: Optional[date] = None
    ) -> RealPlusProjectedReport:
        """
        Relatório Versão 1: Real + Projetado.

        Mostra gastos reais + projeção proporcional ao orçamento.

        Args:
            month: Mês (YYYY-MM)
            currency: Moeda
            reference_date: Data de referência (padrão: hoje)

        Returns:
            Relatório com projeções
        """
        year, month_num = map(int, month.split('-'))
        amount_col = self._get_amount_column(currency)

        if reference_date is None:
            reference_date = date.today()

        # Verificar se estamos no mês de referência
        is_current_month = (
            reference_date.year == year and
            reference_date.month == month_num
        )

        # Calcular dias passados e total do mês
        first_day = date(year, month_num, 1)
        if month_num == 12:
            last_day = date(year + 1, 1, 1) - relativedelta(days=1)
        else:
            last_day = date(year, month_num + 1, 1) - relativedelta(days=1)

        total_days = (last_day - first_day).days + 1

        if is_current_month:
            days_passed = (reference_date - first_day).days + 1
        else:
            days_passed = total_days

        day_ratio = days_passed / total_days

        # Buscar orçamentos
        budgets = {
            b.category_id: b.amount_brl
            for b in self.db.query(Budget).filter(Budget.month == month).all()
        }

        # Buscar categorias
        categories = self.db.query(Category).filter(Category.is_active == True).all()

        # Realizados (todas categorias) em UMA query agregada
        actual_rows = self.db.query(
            Transaction.category_id,
            func.sum(amount_col).label('total'),
        ).filter(
            Transaction.date >= first_day,
            Transaction.date <= reference_date,
            amount_col < 0,
        ).group_by(Transaction.category_id).all()
        actuals_by_cat = {row.category_id: abs(row.total or Decimal("0.00")) for row in actual_rows}

        items = []
        total_actual = Decimal("0.00")
        total_projected = Decimal("0.00")
        total_expected = Decimal("0.00")

        for cat in categories:
            projected = budgets.get(cat.id, Decimal("0.00"))
            actual = actuals_by_cat.get(cat.id, Decimal("0.00"))

            # Projeção esperada para o final do mês
            if is_current_month and day_ratio > 0:
                # Projetar baseado no ritmo atual
                expected_total = actual / Decimal(str(day_ratio))
            else:
                expected_total = actual

            total_actual += actual
            total_projected += projected
            total_expected += expected_total

            items.append(ProjectedExpense(
                category_id=cat.id,
                category_name=cat.name,
                projected=projected,
                actual=actual.quantize(Decimal("0.01")),
                expected_total=expected_total.quantize(Decimal("0.01"))
            ))

        # Ordenar por valor esperado
        items.sort(key=lambda x: x.expected_total, reverse=True)

        return RealPlusProjectedReport(
            month=month,
            currency=currency,
            reference_date=reference_date,
            total_actual=total_actual.quantize(Decimal("0.01")),
            total_projected=total_projected,
            total_expected=total_expected.quantize(Decimal("0.01")),
            items=items
        )

    def get_income_vs_expense(
        self,
        start_month: str,
        end_month: str,
        currency: CurrencyCode = CurrencyCode.BRL
    ) -> IncomeVsExpenseReport:
        """
        Relatório de receitas vs despesas.

        Args:
            start_month: Mês inicial
            end_month: Mês final
            currency: Moeda

        Returns:
            Comparação por mês
        """
        amount_col = self._get_amount_column(currency)

        start_year, start_m = map(int, start_month.split('-'))
        end_year, end_m = map(int, end_month.split('-'))
        start_date = date(start_year, start_m, 1)
        if end_m == 12:
            end_date_real = date(end_year + 1, 1, 1) - relativedelta(days=1)
        else:
            end_date_real = date(end_year, end_m + 1, 1) - relativedelta(days=1)

        months = []
        cur = start_date
        while cur <= date(end_year, end_m, 1):
            months.append(cur.strftime('%Y-%m'))
            cur += relativedelta(months=1)

        # Categorias de transferência (1 query, fora do loop)
        transfer_cat_ids = [
            r[0] for r in self.db.query(Category.id).filter(Category.type == "transfer").all()
        ]

        base_filter = [
            Transaction.date >= start_date,
            Transaction.date <= end_date_real,
        ]
        if transfer_cat_ids:
            base_filter.append(or_(
                ~Transaction.category_id.in_(transfer_cat_ids),
                Transaction.category_id.is_(None),
            ))

        # Receitas e despesas em UMA query agregada por (ano, mês, sinal)
        rows = self.db.query(
            extract('year', Transaction.date).label('yr'),
            extract('month', Transaction.date).label('mo'),
            func.sum(case((amount_col > 0, amount_col), else_=Decimal("0"))).label('income'),
            func.sum(case((amount_col < 0, amount_col), else_=Decimal("0"))).label('expense'),
        ).filter(*base_filter).group_by(
            extract('year', Transaction.date),
            extract('month', Transaction.date),
        ).all()

        bucket: dict[str, dict[str, Decimal]] = {}
        for yr, mo, inc, exp in rows:
            m_str = f"{int(yr):04d}-{int(mo):02d}"
            bucket[m_str] = {
                "income": inc or Decimal("0.00"),
                "expense": abs(exp or Decimal("0.00")),
            }

        months_data = []
        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")
        for m_str in months:
            b = bucket.get(m_str, {"income": Decimal("0.00"), "expense": Decimal("0.00")})
            income = b["income"]
            expense = b["expense"]
            total_income += income
            total_expense += expense
            months_data.append(IncomeVsExpenseMonth(
                month=m_str,
                income=income.quantize(Decimal("0.01")),
                expense=expense.quantize(Decimal("0.01")),
                balance=(income - expense).quantize(Decimal("0.01")),
            ))

        return IncomeVsExpenseReport(
            start_month=start_month,
            end_month=end_month,
            currency=currency,
            months=months_data,
            total_income=total_income.quantize(Decimal("0.01")),
            total_expense=total_expense.quantize(Decimal("0.01")),
            total_balance=(total_income - total_expense).quantize(Decimal("0.01"))
        )

    def get_accounts_balance(self) -> AccountsBalanceReport:
        """
        Obtém saldo de todas as contas.

        Returns:
            Saldos por conta
        """
        accounts = self.db.query(BankAccount).filter(
            BankAccount.is_active == True
        ).all()

        # Pré-carregar bancos (evitar N+1)
        bank_by_id = {b.id: b for b in self.db.query(Bank).all()}

        items = []
        total_brl = Decimal("0.00")

        for acc in accounts:
            bank = bank_by_id.get(acc.bank_id)
            balance_brl = acc.current_balance
            total_brl += balance_brl
            items.append(AccountBalanceReport(
                account_id=acc.id,
                account_name=acc.name,
                bank_name=bank.name if bank else "",
                currency=acc.currency,
                balance=acc.current_balance,
                balance_brl=balance_brl
            ))

        return AccountsBalanceReport(
            accounts=items,
            total_brl=total_brl
        )

    def _build_month_list(self, start_month: str, end_month: str):
        """Gera lista de meses e datas de início/fim."""
        start_year, start_m = map(int, start_month.split('-'))
        end_year, end_m = map(int, end_month.split('-'))
        start_date = date(start_year, start_m, 1)
        end_last = date(end_year, end_m, 1)

        months = []
        current = start_date
        while current <= end_last:
            months.append(current.strftime('%Y-%m'))
            current += relativedelta(months=1)

        if end_m == 12:
            end_date_real = date(end_year + 1, 1, 1) - relativedelta(days=1)
        else:
            end_date_real = date(end_year, end_m + 1, 1) - relativedelta(days=1)

        return months, start_date, end_date_real

    def _group_totals(self, rows: List[CategoryMonthlyRow], months: List[str]) -> CategoryGroupTotals:
        """Calcula totais de um grupo de linhas."""
        values = {}
        total = Decimal("0.00")
        for m in months:
            col_sum = sum(row.values.get(m, Decimal("0.00")) for row in rows)
            values[m] = col_sum
            total += col_sum
        return CategoryGroupTotals(values=values, total=total)

    def get_category_monthly_pivot(
        self,
        start_month: str,
        end_month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        account_ids: Optional[List[int]] = None,
        category_ids: Optional[List[int]] = None,
    ) -> CategoryMonthlyPivotReport:
        """
        Relatório pivô: categorias nas linhas, meses nas colunas.
        Inclui despesas, receitas e transferências, agrupadas por tipo.
        Valores exibidos como positivos (abs).
        """
        amount_col = self._get_amount_column(currency)
        months, start_date, end_date_real = self._build_month_list(start_month, end_month)

        # Query: agrupar por categoria e mês (sem filtro de sinal)
        query = self.db.query(
            Transaction.category_id,
            extract('year', Transaction.date).label('yr'),
            extract('month', Transaction.date).label('mo'),
            func.sum(amount_col).label('total')
        ).filter(
            and_(
                Transaction.date >= start_date,
                Transaction.date <= end_date_real,
            )
        )

        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
        if category_ids:
            # Suporte a category_id=0 para "Pendente (sem categoria)"
            include_uncategorized = 0 in category_ids
            real_cat_ids = [c for c in category_ids if c != 0]
            if include_uncategorized and real_cat_ids:
                query = query.filter(
                    or_(Transaction.category_id.in_(real_cat_ids), Transaction.category_id.is_(None))
                )
            elif include_uncategorized:
                query = query.filter(Transaction.category_id.is_(None))
            else:
                query = query.filter(Transaction.category_id.in_(real_cat_ids))

        results = query.group_by(
            Transaction.category_id,
            extract('year', Transaction.date),
            extract('month', Transaction.date)
        ).all()

        # Buscar categorias
        all_categories = {c.id: c for c in self.db.query(Category).all()}

        # Organizar dados: {category_id: {month: amount}}
        # category_id=None → usar 0 como chave para "Pendente"
        data = {}
        for r in results:
            if r.category_id is None:
                if not (category_ids and 0 in category_ids):
                    continue
            cat_id = r.category_id if r.category_id is not None else 0
            month_key = f"{int(r.yr):04d}-{int(r.mo):02d}"
            if cat_id not in data:
                data[cat_id] = {}
            data[cat_id][month_key] = r.total.quantize(Decimal("0.01"))

        # Montar linhas com tipo
        all_rows = []
        for cat_id, month_values in data.items():
            cat = all_categories.get(cat_id)
            values = {}
            total = Decimal("0.00")
            for m in months:
                val = month_values.get(m, Decimal("0.00"))
                values[m] = val
                total += val
            cat_type = cat.type.value if cat and cat.type else "expense"
            all_rows.append(CategoryMonthlyRow(
                category_id=cat_id,
                category_name=cat.name if cat else "Sem categoria",
                category_type=cat_type,
                category_color=cat.color if cat else None,
                values=values,
                total=total,
            ))

        # Separar por tipo e ordenar alfabeticamente
        expense_rows = sorted(
            [r for r in all_rows if r.category_type == "expense"],
            key=lambda x: x.category_name.lower()
        )
        income_rows = sorted(
            [r for r in all_rows if r.category_type == "income"],
            key=lambda x: x.category_name.lower()
        )
        transfer_rows = sorted(
            [r for r in all_rows if r.category_type == "transfer"],
            key=lambda x: x.category_name.lower()
        )

        expense_totals = self._group_totals(expense_rows, months)
        income_totals = self._group_totals(income_rows, months)
        transfer_totals = self._group_totals(transfer_rows, months)

        # Total líquido por coluna (despesas + receitas + transferências)
        column_totals = {}
        grand_total = Decimal("0.00")
        for m in months:
            net = (expense_totals.values.get(m, Decimal("0.00"))
                   + income_totals.values.get(m, Decimal("0.00"))
                   + transfer_totals.values.get(m, Decimal("0.00")))
            column_totals[m] = net
            grand_total += net

        return CategoryMonthlyPivotReport(
            start_month=start_month,
            end_month=end_month,
            currency=currency,
            months=months,
            expense_rows=expense_rows,
            expense_totals=expense_totals,
            income_rows=income_rows,
            income_totals=income_totals,
            transfer_rows=transfer_rows,
            transfer_totals=transfer_totals,
            column_totals=column_totals,
            grand_total=grand_total,
        )

    def get_category_monthly_pivot_budget(
        self,
        start_month: str,
        end_month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        category_ids: Optional[List[int]] = None,
    ) -> CategoryMonthlyPivotReport:
        """
        Relatório pivô baseado em orçamento (budget).
        Mesma estrutura do pivot de transações, mas usando dados do orçamento.
        """
        amount_col_name = f"amount_{currency.value.lower()}"
        amount_col = getattr(Budget, amount_col_name)
        months, _, _ = self._build_month_list(start_month, end_month)

        query = self.db.query(
            Budget.category_id,
            Budget.month,
            amount_col.label('total')
        ).filter(
            Budget.month >= start_month,
            Budget.month <= end_month,
        )

        if category_ids:
            real_cat_ids = [c for c in category_ids if c != 0]
            if real_cat_ids:
                query = query.filter(Budget.category_id.in_(real_cat_ids))

        results = query.all()

        all_categories = {c.id: c for c in self.db.query(Category).all()}

        data = {}
        for r in results:
            cat_id = r.category_id
            if cat_id not in data:
                data[cat_id] = {}
            data[cat_id][r.month] = r.total.quantize(Decimal("0.01")) if r.total else Decimal("0.00")

        all_rows = []
        for cat_id, month_values in data.items():
            cat = all_categories.get(cat_id)
            values = {}
            total = Decimal("0.00")
            for m in months:
                val = month_values.get(m, Decimal("0.00"))
                values[m] = val
                total += val
            cat_type = cat.type.value if cat and cat.type else "expense"
            all_rows.append(CategoryMonthlyRow(
                category_id=cat_id,
                category_name=cat.name if cat else "Sem categoria",
                category_type=cat_type,
                category_color=cat.color if cat else None,
                values=values,
                total=total,
            ))

        expense_rows = sorted([r for r in all_rows if r.category_type == "expense"], key=lambda x: x.category_name.lower())
        income_rows = sorted([r for r in all_rows if r.category_type == "income"], key=lambda x: x.category_name.lower())
        transfer_rows = sorted([r for r in all_rows if r.category_type == "transfer"], key=lambda x: x.category_name.lower())

        expense_totals = self._group_totals(expense_rows, months)
        income_totals = self._group_totals(income_rows, months)
        transfer_totals = self._group_totals(transfer_rows, months)

        column_totals = {}
        grand_total = Decimal("0.00")
        for m in months:
            net = (expense_totals.values.get(m, Decimal("0.00"))
                   + income_totals.values.get(m, Decimal("0.00"))
                   + transfer_totals.values.get(m, Decimal("0.00")))
            column_totals[m] = net
            grand_total += net

        return CategoryMonthlyPivotReport(
            start_month=start_month,
            end_month=end_month,
            currency=currency,
            months=months,
            expense_rows=expense_rows,
            expense_totals=expense_totals,
            income_rows=income_rows,
            income_totals=income_totals,
            transfer_rows=transfer_rows,
            transfer_totals=transfer_totals,
            column_totals=column_totals,
            grand_total=grand_total,
        )

    def get_transaction_details(
        self,
        start_month: str,
        end_month: str,
        currency: CurrencyCode = CurrencyCode.BRL,
        account_ids: Optional[List[int]] = None,
        category_ids: Optional[List[int]] = None,
    ) -> List[ReportTransactionDetail]:
        """Retorna transações individuais via JOIN único (sem N+1)."""
        months, start_date, end_date_real = self._build_month_list(start_month, end_month)

        query = self.db.query(
            Transaction.date,
            Transaction.description,
            Category.name.label('cat_name'),
            Category.type.label('cat_type'),
            BankAccount.name.label('acc_name'),
            Transaction.original_amount,
            Transaction.original_currency,
            Transaction.amount_brl,
            Transaction.amount_usd,
            Transaction.amount_eur,
            Transaction.id,
        ).outerjoin(Category, Transaction.category_id == Category.id) \
         .outerjoin(BankAccount, Transaction.account_id == BankAccount.id) \
         .filter(
            Transaction.date >= start_date,
            Transaction.date <= end_date_real,
         )

        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
        if category_ids:
            include_uncategorized = 0 in category_ids
            real_cat_ids = [c for c in category_ids if c != 0]
            if include_uncategorized and real_cat_ids:
                query = query.filter(
                    or_(Transaction.category_id.in_(real_cat_ids), Transaction.category_id.is_(None))
                )
            elif include_uncategorized:
                query = query.filter(Transaction.category_id.is_(None))
            else:
                query = query.filter(Transaction.category_id.in_(real_cat_ids))

        rows = query.order_by(Transaction.date, Transaction.id).all()

        items = []
        for r in rows:
            items.append(ReportTransactionDetail(
                date=r.date.strftime('%Y-%m-%d'),
                description=r.description,
                category_name=r.cat_name,
                category_type=r.cat_type.value if r.cat_type else None,
                account_name=r.acc_name,
                original_amount=r.original_amount,
                original_currency=r.original_currency.value if r.original_currency else "BRL",
                amount_brl=r.amount_brl,
                amount_usd=r.amount_usd,
                amount_eur=r.amount_eur,
            ))
        return items
