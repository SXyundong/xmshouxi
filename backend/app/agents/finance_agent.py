from app.agents.base_agent import BaseAgent


class FinanceAgent(BaseAgent):
    name = "财务Agent"
    department = "finance"
    description = "财务数据与报表"
    tools = []
