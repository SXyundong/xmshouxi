from pydantic import BaseModel


class ChatRequest(BaseModel):
    department: str
    message: str


class ChatResponse(BaseModel):
    agent: str
    answer: str
