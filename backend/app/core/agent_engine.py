"""Agent 运行引擎：按部门路由到对应 Agent 并执行，业务逻辑不允许写死在 API 里。"""

from app.agents.registry import agent_registry
from app.core.llm_client import LLMResult


class AgentEngine:
    def __init__(self, registry=None):
        self.registry = registry or agent_registry

    async def run(self, department: str, message: str) -> dict:
        agent = self.registry.get(department)
        if agent is None:
            return {
                "agent": "未知部门",
                "answer": f"未找到部门「{department}」，请从首页选择已有部门。",
            }
        answer = await agent.run(message)
        return {"agent": agent.name, "answer": answer}

    async def run_with_result(self, department: str, message: str, history: list[dict] | None = None) -> dict:
        agent = self.registry.get(department)
        if agent is None:
            return {
                "agent": "未知部门",
                "answer": f"未找到部门「{department}」，请从首页选择已有部门。",
                "result": LLMResult(content="", model="unknown"),
            }
        result = await agent.run_with_result(message, history)
        return {"agent": agent.name, "answer": result.content, "result": result}


agent_engine = AgentEngine()
