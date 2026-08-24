"""BaseTool：所有 Tool 的基类。"""


class BaseTool:
    name: str = "base_tool"
    description: str = ""

    async def execute(self, *args, **kwargs):
        """执行工具并返回结果，子类必须实现。"""
        raise NotImplementedError
