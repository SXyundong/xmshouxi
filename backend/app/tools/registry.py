"""Tool 注册中心：tool name -> Tool 实例。新增 Tool 时在此注册即可。"""

from __future__ import annotations

from app.tools.base_tool import BaseTool
from app.tools.lingxing_tool import LingxingSalesTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)


tool_registry = ToolRegistry()
tool_registry.register(LingxingSalesTool())
