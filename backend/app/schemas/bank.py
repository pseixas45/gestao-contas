from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BankBase(BaseModel):
    name: str
    code: Optional[str] = None
    color: Optional[str] = "#000000"
    logo_url: Optional[str] = None


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    color: Optional[str] = None
    logo_url: Optional[str] = None


class BankResponse(BankBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
