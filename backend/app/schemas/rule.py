from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.rule import MatchType


class RuleBase(BaseModel):
    category_id: int
    pattern: str
    match_type: MatchType = MatchType.CONTAINS
    priority: int = 0


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    category_id: Optional[int] = None
    pattern: Optional[str] = None
    match_type: Optional[MatchType] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class RuleResponse(RuleBase):
    id: int
    is_active: bool
    hit_count: int
    created_at: datetime
    category_name: Optional[str] = None  # Preenchido na API

    class Config:
        from_attributes = True


class RuleTest(BaseModel):
    """Testar uma regra contra um texto."""
    pattern: str
    match_type: MatchType
    test_text: str


class RuleTestResult(BaseModel):
    matches: bool
    matched_text: Optional[str] = None
