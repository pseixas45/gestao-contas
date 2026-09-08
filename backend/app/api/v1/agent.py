"""Endpoint do agente de carga conversacional."""
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.models import User
from app.services.agent_service import run_chat
from app.utils.security import get_current_active_user

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/chat")
def agent_chat(
    data: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """Um turno do agente. As ferramentas rodam com o token do usuário."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Token ausente")
    if not data.messages:
        raise HTTPException(status_code=400, detail="Envie ao menos uma mensagem")
    result = run_chat([m.model_dump() for m in data.messages], token=token)
    return result
