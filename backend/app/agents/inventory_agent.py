from app.agents.base_agent import BaseAgent


class InventoryAgent(BaseAgent):
    name = "库存Agent"
    department = "inventory"
    description = "库存查询与管理"
    tools = []
