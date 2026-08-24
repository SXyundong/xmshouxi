from fastapi import APIRouter

from app.core.agent_engine import agent_engine
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户请求，路由到对应部门的 Agent 并返回结果。"""
    result = await agent_engine.run(req.department, req.message)
    return ChatResponse(agent=result["agent"], answer=result["answer"])
