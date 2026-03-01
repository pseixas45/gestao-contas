from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Bank, User
from app.schemas.bank import BankCreate, BankUpdate, BankResponse
from app.utils.security import get_current_active_user

router = APIRouter()


@router.get("", response_model=List[BankResponse])
def list_banks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar todos os bancos."""
    return db.query(Bank).order_by(Bank.name).all()


@router.get("/{bank_id}", response_model=BankResponse)
def get_bank(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter banco por ID."""
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Banco não encontrado")
    return bank


@router.post("", response_model=BankResponse)
def create_bank(
    bank_data: BankCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Criar novo banco."""
    # Verificar se código já existe
    if bank_data.code:
        if db.query(Bank).filter(Bank.code == bank_data.code).first():
            raise HTTPException(status_code=400, detail="Código de banco já cadastrado")

    bank = Bank(**bank_data.model_dump())
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return bank


@router.put("/{bank_id}", response_model=BankResponse)
def update_bank(
    bank_id: int,
    bank_data: BankUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar banco."""
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Banco não encontrado")

    update_data = bank_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bank, field, value)

    db.commit()
    db.refresh(bank)
    return bank


@router.delete("/{bank_id}")
def delete_bank(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Excluir banco."""
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Banco não encontrado")

    # Verificar se há contas vinculadas
    if bank.accounts:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir banco com contas vinculadas"
        )

    db.delete(bank)
    db.commit()
    return {"message": "Banco excluído com sucesso"}
