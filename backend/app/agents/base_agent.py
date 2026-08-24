"""BaseAgent：所有 Agent 的基类，负责接收用户输入、管理工具、调用 LLM、返回结果。"""

from __future__ import annotations

import json

from app.core.llm_client import llm_client
from app.tools.registry import tool_registry


class BaseAgent:
    name: str = "BaseAgent"
    department: str = ""
    description: str = ""
    tools: list[str] = []

    def __init__(self, llm=None):
        self.llm = llm or llm_client

    async def run(self, message: str) -> str:
        """执行 Agent：先调用工具收集数据，再交给 LLM 生成回答。"""
        tool_results = await self._run_tools(message)
        messages = self._build_messages(message, tool_results)
        return await self.llm.chat(messages)

    async def _run_tools(self, message: str) -> str:
        if not self.tools:
            return ""
        lines = []
        for tool_name in self.tools:
            tool = tool_registry.get(tool_name)
            if tool is None:
                continue
            result = await tool.execute(message)
            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False)
            lines.append(f"- {tool.name}: {result}")
        return "\n".join(lines)

    def _build_messages(self, message: str, tool_results: str) -> list[dict]:
        system_prompt = (
            f"你是{self.name}，服务于「{self.department}」部门。"
            f"职责：{self.description}。"
            "请基于工具返回的数据与用户问题，用中文给出简洁、准确的回答。"
        )
        messages = [{"role": "system", "content": system_prompt}]
        if tool_results:
            messages.append(
                {"role": "system", "content": f"工具返回数据:\n{tool_results}"}
            )
        messages.append({"role": "user", "content": message})
        return messages
