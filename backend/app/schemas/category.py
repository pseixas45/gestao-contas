from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.category import CategoryType


class CategoryBase(BaseModel):
    name: str
    type: CategoryType
    color: Optional[str] = "#6B7280"
    icon: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[CategoryType] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: int
    is_active: bool
    created_at: datetime
    children: List["CategoryResponse"] = []

    class Config:
        from_attributes = True


# Para resolver referência circular
CategoryResponse.model_rebuild()
