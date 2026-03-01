"""
Serviço de Orçamento Mensal.

Gerencia orçamentos por categoria e mês.
Calcula sugestões baseadas na média dos últimos 3 meses.
Compara orçado vs realizado.
"""

from typing import List, Optional, Dict
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract

from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.budget import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetSuggestion,
    BudgetComparison,
    BudgetMonthSummary
)


class BudgetService:
    """Serviço para gerenciamento de orçamentos."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, budget_data: BudgetCreate) -> Budget:
        """Cria um novo orçamento."""
        # Verificar se já existe
        existing = self.db.query(Budget).filter(
            and_(
                Budget.month == budget_data.month,
                Budget.category_id == budget_data.category_id
            )
        ).first()

        if existing:
            # Atualizar existente
            existing.amount_brl = budget_data.amount_brl
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        # Criar novo
        budget = Budget(
            month=budget_data.month,
            category_id=budget_data.category_id,
            amount_brl=budget_data.amount_brl
        )
        self.db.add(budget)
        self.db.commit()
        self.db.refresh(budget)
        return budget

    def update(self, budget_id: int, budget_data: BudgetUpdate) -> Optional[Budget]:
        """Atualiza um orçamento existente."""
        budget = self.db.query(Budget).filter(Budget.id == budget_id).first()
        if not budget:
            return None

        budget.amount_brl = budget_data.amount_brl
        budget.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(budget)
        return budget

    def delete(self, budget_id: int) -> bool:
        """Remove um orçamento."""
        budget = self.db.query(Budget).filter(Budget.id == budget_id).first()
        if not budget:
            return False

        self.db.delete(budget)
        self.db.commit()
        return True

    def get_by_month(self, month: str) -> List[BudgetResponse]:
        """Obtém todos os orçamentos de um mês."""
        budgets = self.db.query(Budget).filter(Budget.month == month).all()

        result = []
        for budget in budgets:
            category = self.db.query(Category).filter(
                Category.id == budget.category_id
            ).first()

            result.append(BudgetResponse(
                id=budget.id,
                month=budget.month,
                category_id=budget.category_id,
                amount_brl=budget.amount_brl,
                category_name=category.name if category else None,
                category_color=category.color if category else None
            ))

        return result

    def get_suggestions(self, month: str) -> List[BudgetSuggestion]:
        """
        Gera sugestões de orçamento baseadas na média dos últimos 3 meses.

        Args:
            month: Mês de referência (YYYY-MM)

        Returns:
            Lista de sugestões por categoria
        """
        # Calcular os 3 meses anteriores
        year, month_num = map(int, month.split('-'))
        ref_date = date(year, month_num, 1)

        month_1 = (ref_date - relativedelta(months=1)).strftime('%Y-%m')
        month_2 = (ref_date - relativedelta(months=2)).strftime('%Y-%m')
        month_3 = (ref_date - relativedelta(months=3)).strftime('%Y-%m')

        # Buscar todas as categorias
        categories = self.db.query(Category).filter(Category.is_active == True).all()

        suggestions = []
        for category in categories:
            # Calcular gastos por mês (apenas despesas - valores negativos)
            amounts = {}
            for m in [month_1, month_2, month_3]:
                m_year, m_month = map(int, m.split('-'))
                total = self.db.query(func.sum(Transaction.amount_brl)).filter(
                    and_(
                        Transaction.category_id == category.id,
                        extract('year', Transaction.date) == m_year,
                        extract('month', Transaction.date) == m_month,
                        Transaction.amount_brl < 0  # Apenas despesas
                    )
                ).scalar() or Decimal("0.00")

                # Converter para positivo para exibição
                amounts[m] = abs(total)

            # Calcular média
            values = [amounts[month_1], amounts[month_2], amounts[month_3]]
            non_zero = [v for v in values if v > 0]

            if non_zero:
                average = sum(non_zero) / len(non_zero)
                suggested = average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                average = Decimal("0.00")
                suggested = Decimal("0.00")

            suggestions.append(BudgetSuggestion(
                category_id=category.id,
                category_name=category.name,
                suggested_amount=suggested,
                average_last_3_months=average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                month_1_amount=amounts[month_1],
                month_2_amount=amounts[month_2],
                month_3_amount=amounts[month_3]
            ))

        # Ordenar por valor sugerido (maior primeiro)
        suggestions.sort(key=lambda x: x.suggested_amount, reverse=True)

        return suggestions

    def get_comparison(self, month: str) -> BudgetMonthSummary:
        """
        Compara orçado vs realizado para um mês.

        Args:
            month: Mês de referência (YYYY-MM)

        Returns:
            Resumo com comparação por categoria
        """
        year, month_num = map(int, month.split('-'))

        # Buscar orçamentos do mês
        budgets = {
            b.category_id: b.amount_brl
            for b in self.db.query(Budget).filter(Budget.month == month).all()
        }

        # Buscar categorias
        categories = self.db.query(Category).filter(Category.is_active == True).all()

        comparisons = []
        total_budgeted = Decimal("0.00")
        total_actual = Decimal("0.00")

        for category in categories:
            # Valor orçado
            budgeted = budgets.get(category.id, Decimal("0.00"))

            # Valor real (soma das despesas - valores negativos)
            actual = self.db.query(func.sum(Transaction.amount_brl)).filter(
                and_(
                    Transaction.category_id == category.id,
                    extract('year', Transaction.date) == year,
                    extract('month', Transaction.date) == month_num,
                    Transaction.amount_brl < 0  # Apenas despesas
                )
            ).scalar() or Decimal("0.00")

            # Converter para positivo
            actual = abs(actual)

            # Calcular diferença e percentual
            difference = budgeted - actual
            percentage = (float(actual) / float(budgeted) * 100) if budgeted > 0 else 0.0

            total_budgeted += budgeted
            total_actual += actual

            comparisons.append(BudgetComparison(
                category_id=category.id,
                category_name=category.name,
                category_color=category.color,
                budgeted=budgeted,
                actual=actual,
                difference=difference,
                percentage=round(percentage, 1)
            ))

        # Ordenar por percentual (maior primeiro - mais preocupante)
        comparisons.sort(key=lambda x: x.percentage, reverse=True)

        # Totais
        total_difference = total_budgeted - total_actual
        overall_percentage = (
            (float(total_actual) / float(total_budgeted) * 100)
            if total_budgeted > 0 else 0.0
        )

        return BudgetMonthSummary(
            month=month,
            total_budgeted=total_budgeted,
            total_actual=total_actual,
            total_difference=total_difference,
            overall_percentage=round(overall_percentage, 1),
            categories=comparisons
        )

    def copy_month(self, source_month: str, target_month: str) -> List[Budget]:
        """
        Copia orçamentos de um mês para outro.

        Args:
            source_month: Mês de origem (YYYY-MM)
            target_month: Mês de destino (YYYY-MM)

        Returns:
            Lista de orçamentos criados
        """
        source_budgets = self.db.query(Budget).filter(
            Budget.month == source_month
        ).all()

        created = []
        for source in source_budgets:
            # Verificar se já existe no destino
            existing = self.db.query(Budget).filter(
                and_(
                    Budget.month == target_month,
                    Budget.category_id == source.category_id
                )
            ).first()

            if existing:
                # Atualizar
                existing.amount_brl = source.amount_brl
                existing.updated_at = datetime.utcnow()
                created.append(existing)
            else:
                # Criar novo
                new_budget = Budget(
                    month=target_month,
                    category_id=source.category_id,
                    amount_brl=source.amount_brl
                )
                self.db.add(new_budget)
                created.append(new_budget)

        self.db.commit()

        for b in created:
            self.db.refresh(b)

        return created

    def create_from_suggestions(self, month: str) -> List[Budget]:
        """
        Cria orçamentos a partir das sugestões automáticas.

        Args:
            month: Mês de destino (YYYY-MM)

        Returns:
            Lista de orçamentos criados
        """
        suggestions = self.get_suggestions(month)

        created = []
        for suggestion in suggestions:
            if suggestion.suggested_amount > 0:
                budget = self.create(BudgetCreate(
                    month=month,
                    category_id=suggestion.category_id,
                    amount_brl=suggestion.suggested_amount
                ))
                created.append(budget)

        return created
