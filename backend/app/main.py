from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.registry import agent_registry
from app.api.chat import router as chat_router

app = FastAPI(title="电商多部门 Agent 系统", version="1.0.0")

# V1 简化：允许所有来源，避免前后端联调时的 CORS 问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/")
def root():
    return {"service": "ecommerce-agent-v1-backend", "status": "ok"}


@app.get("/api/departments")
def departments():
    """列出已注册的部门 Agent，方便联调。"""
    return agent_registry.list_agents()
