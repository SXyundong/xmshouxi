from app.agents.base_agent import BaseAgent


class ProductAgent(BaseAgent):
    name = "选品Agent"
    department = "product"
    description = "选品分析与建议"
    tools = []
