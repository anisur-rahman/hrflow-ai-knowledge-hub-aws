from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.security import Principal, current_principal
from app.services import rag_service

router = APIRouter(prefix='/api/chat', tags=['chat'])


@router.post('', response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    return rag_service.ask(db, principal, req.question, [turn.model_dump() for turn in req.history])
