from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def history_alternates(self):
        expected = ['user', 'assistant'] * (len(self.history) // 2)
        if [turn.role for turn in self.history] != expected:
            raise ValueError('history must alternate user/assistant turns, starting with user and ending with assistant')
        return self


class Citation(BaseModel):
    document_id: str
    title: str
    version: str | None
    page: int
    heading: str | None
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    mode: str
    sources: list[Citation]
