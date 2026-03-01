from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Category, User
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.utils.security import get_current_active_user

router = APIRouter()


def build_category_tree(categories: List[Category], parent_id=None) -> List[CategoryResponse]:
    """Constrói árvore de categorias."""
    result = []
    for cat in categories:
        if cat.parent_id == parent_id:
            cat_response = CategoryResponse.model_validate(cat)
            cat_response.children = build_category_tree(categories, cat.id)
            result.append(cat_response)
    return result


@router.get("", response_model=List[CategoryResponse])
def list_categories(
    active_only: bool = True,
    flat: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Listar categorias.

    - flat=False: retorna árvore hierárquica
    - flat=True: retorna lista plana
    """
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.is_active == True)

    categories = query.order_by(Category.name).all()

    if flat:
        return [CategoryResponse.model_validate(cat) for cat in categories]

    # Retornar apenas categorias raiz com filhos aninhados
    return build_category_tree(categories, None)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter categoria por ID."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return CategoryResponse.model_validate(category)


@router.post("", response_model=CategoryResponse)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Criar nova categoria."""
    # Verificar se pai existe (se informado)
    if category_data.parent_id:
        parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Categoria pai não encontrada")

    category = Category(**category_data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar categoria."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    update_data = category_data.model_dump(exclude_unset=True)

    # Verificar se pai existe (se informado)
    if "parent_id" in update_data and update_data["parent_id"]:
        if update_data["parent_id"] == category_id:
            raise HTTPException(status_code=400, detail="Categoria não pode ser pai de si mesma")
        parent = db.query(Category).filter(Category.id == update_data["parent_id"]).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Categoria pai não encontrada")

    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Desativar categoria (soft delete)."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    category.is_active = False
    db.commit()
    return {"message": "Categoria desativada com sucesso"}
