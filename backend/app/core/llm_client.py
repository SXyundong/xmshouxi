"""统一 LLM 调用客户端。所有 Agent 必须通过 LLMClient.chat() 调用 LLM，禁止直接调用 OpenAI。"""

from __future__ import annotations

import httpx

from app.config import settings


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = (base_url or settings.OPENAI_BASE_URL).rstrip("/")
        self.model = model or settings.MODEL

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """调用 LLM 并返回文本。未配置 API Key 时返回本地 mock，保证项目开箱可运行。"""
        if not self.api_key:
            return self._mock_reply(messages)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _mock_reply(messages: list[dict]) -> str:
        user_msg = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        tool_block = next(
            (
                m["content"]
                for m in messages
                if m["role"] == "system" and m["content"].startswith("工具返回数据")
            ),
            None,
        )
        lines = [
            "【本地模拟回复】未配置 OPENAI_API_KEY，以下为演示结果。",
            f"你的问题：{user_msg}",
        ]
        if tool_block:
            lines.append("工具数据：" + tool_block.replace("工具返回数据:", "").strip())
        return "\n".join(lines)


# 全局单例，Agent 默认使用该实例
llm_client = LLMClient()
