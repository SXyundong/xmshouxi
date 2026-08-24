"""Agent 注册中心：department -> Agent 实例。新增 Agent 时在此注册即可。"""

from __future__ import annotations

from app.agents.ads_agent import AdsAgent
from app.agents.base_agent import BaseAgent
from app.agents.design_agent import DesignAgent
from app.agents.finance_agent import FinanceAgent
from app.agents.hr_agent import HrAgent
from app.agents.inventory_agent import InventoryAgent
from app.agents.logistics_agent import LogisticsAgent
from app.agents.operation_agent import OperationAgent
from app.agents.product_agent import ProductAgent
from app.agents.sales_agent import SalesAgent


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.department] = agent

    def get(self, department: str) -> BaseAgent | None:
        return self._agents.get(department)

    def list_agents(self) -> list[dict]:
        return [
            {"department": a.department, "name": a.name, "description": a.description}
            for a in self._agents.values()
        ]


agent_registry = AgentRegistry()

_AGENTS = [
    SalesAgent(),
    InventoryAgent(),
    LogisticsAgent(),
    ProductAgent(),
    AdsAgent(),
    OperationAgent(),
    FinanceAgent(),
    DesignAgent(),
    HrAgent(),
]

for _agent in _AGENTS:
    agent_registry.register(_agent)
