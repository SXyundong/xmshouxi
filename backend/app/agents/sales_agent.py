from app.agents.base_agent import BaseAgent


class SalesAgent(BaseAgent):
    name = "销售分析Agent"
    department = "sales"
    description = "销售数据分析与业绩查询"
    tools = ["lingxing_sales"]
