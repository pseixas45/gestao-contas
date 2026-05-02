"""Backfill de datas para parcelas do Master nos batches 82 e 83.

Regra:
- Para cada parcela, busca parcela anterior (N-1) no banco
- Se acha: nova data = data_anterior + 1 mes (mesmo dia)
- Se nao acha: fallback = adjust_date_for_credit_card(date_atual, card_payment_date)

Apos atualizar a date, regenera o transaction_hash (que depende da date).
"""
import sys
import sqlite3
from datetime import date as date_cls, datetime
import calendar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.services.import_service import (
    find_previous_installment,
    get_installment_base_description,
    adjust_date_for_credit_card,
)
from app.database import SessionLocal
from app.models import Transaction
from sqlalchemy.orm import Session


def calc_new_date(parc: Transaction, db: Session) -> date_cls:
    """Calcula a data ajustada para uma parcela."""
    desc_base = get_installment_base_description(parc.description)
    prev_installment = find_previous_installment(
        db, parc.account_id, desc_base, parc.installment_number, parc.installment_total
    )
    if prev_installment and prev_installment.id != parc.id:
        prev_date = prev_installment.date
        next_month = prev_date.month + 1
        next_year = prev_date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        try:
            return date_cls(next_year, next_month, prev_date.day)
        except ValueError:
            last_day = calendar.monthrange(next_year, next_month)[1]
            return date_cls(next_year, next_month, last_day)
    else:
        # Fallback: usa o card_payment_date para definir o mes da fatura
        return adjust_date_for_credit_card(parc.date, parc.card_payment_date)


def main():
    import logging
    logging.disable(logging.CRITICAL)

    db = SessionLocal()
    try:
        # Pegar todas as parcelas dos batches 82 e 83
        parcelas = (
            db.query(Transaction)
            .filter(Transaction.import_batch_id.in_([82, 83]))
            .filter(Transaction.installment_number.isnot(None))
            .order_by(Transaction.installment_number)  # processar 1, 2, 3... em ordem
            .all()
        )
        print(f'Total parcelas a processar: {len(parcelas)}')

        # Estado antes
        from app.models import BankAccount
        master = db.query(BankAccount).filter(BankAccount.id == 6).first()
        print(f'Saldo Master antes: R$ {float(master.current_balance):,.2f}')

        # Calcular novas datas (sem aplicar ainda)
        updates = []
        for p in parcelas:
            new_date = calc_new_date(p, db)
            if new_date != p.date:
                updates.append((p, new_date))

        print(f'Updates necessarios: {len(updates)}')
        if not updates:
            print('Nada a fazer.')
            return 0

        # Mostrar preview
        print()
        print('Preview (primeiros 10):')
        for p, nd in updates[:10]:
            print(f'  id={p.id} | parc {p.installment_number}/{p.installment_total} | {p.description[:35]:37} | {p.date} -> {nd}')

        # Aplicar e regenerar hash — commit incremental para evitar conflitos cruzados
        applied = 0
        hash_conflicts = 0
        for p, new_date in updates:
            # Limpar hash antes pra evitar self-conflict no flush
            old_hash = p.transaction_hash
            p.transaction_hash = None
            db.flush()

            # Atualizar data
            p.date = new_date
            # Regenerar hash
            new_hash = Transaction.generate_hash(
                p.account_id, p.date, p.description,
                p.original_amount, p.original_currency,
                card_payment_date=p.card_payment_date
            )
            # Verificar conflito (com suffix se necessario)
            suffix = 0
            while True:
                conflict = db.query(Transaction).filter(
                    Transaction.transaction_hash == new_hash,
                    Transaction.id != p.id
                ).first()
                if not conflict:
                    break
                suffix += 1
                new_hash = Transaction.generate_hash(
                    p.account_id, p.date, p.description,
                    p.original_amount, p.original_currency,
                    suffix=suffix,
                    card_payment_date=p.card_payment_date
                )
                if suffix > 10:
                    print(f'    AVISO: conflito de hash em id={p.id}, mantendo hash antigo')
                    new_hash = old_hash
                    hash_conflicts += 1
                    break
            p.transaction_hash = new_hash
            db.commit()
            applied += 1

        print(f'\n{applied} datas atualizadas')
        if hash_conflicts:
            print(f'{hash_conflicts} conflitos de hash (mantido antigo)')

        # Validacao
        db.refresh(master)
        print()
        print('=== VALIDACAO ===')
        print(f'Saldo Master: R$ {float(master.current_balance):,.2f}')

        # Soma da fatura aberta
        from sqlalchemy import func
        soma = db.query(func.sum(Transaction.amount_brl)).filter(
            Transaction.account_id == 6,
            Transaction.card_payment_date == date_cls(2026, 5, 20)
        ).scalar()
        print(f'Soma fatura cpd=2026-05-20: R$ {float(soma or 0):,.2f}')

        # Mostrar exemplos de parcelas atualizadas
        print()
        print('Exemplos finais (parcelas Positivo Tecno 9/10):')
        rows = db.query(Transaction).filter(
            Transaction.account_id == 6,
            Transaction.description.like('%positivo Tecno%'),
            Transaction.installment_number == 9
        ).all()
        for r in rows:
            print(f'  id={r.id} | date={r.date} | cpd={r.card_payment_date} | val={r.amount_brl}')

    finally:
        db.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
