"""统一 LLM 调用客户端。所有 Agent 必须通过 LLMClient.chat() 调用 LLM，禁止直接调用 OpenAI。"""

from __future__ import annotations

from dataclasses import dataclass
import time

import httpx

from app.config import settings


@dataclass
class LLMResult:
    content: str
    model: str
    request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """调用 LLM 并返回文本。"""
        return (await self.complete(messages, temperature=temperature)).content

    async def complete(self, messages: list[dict], temperature: float = 0.7) -> LLMResult:
        """调用兼容 OpenAI 格式的模型并保留可审计的调用元数据。"""
        if not self.api_key:
            if not settings.LLM_MOCK_ENABLED:
                raise RuntimeError("未配置 LLM_API_KEY，真实聊天服务不可用")
            return LLMResult(content=self._mock_reply(messages), model=self.model)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        }

        started_at = time.perf_counter()
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        message = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        return LLMResult(
            content=str(message.get("content") or "").strip(),
            model=str(data.get("model") or self.model),
            request_id=data.get("id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=round((time.perf_counter() - started_at) * 1000),
        )

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
            "【本地模拟回复】已启用 LLM_MOCK_ENABLED，以下为演示结果。",
            f"你的问题：{user_msg}",
        ]
        if tool_block:
            lines.append("工具数据：" + tool_block.replace("工具返回数据:", "").strip())
        return "\n".join(lines)


# 全局单例，Agent 默认使用该实例
llm_client = LLMClient()
vision_llm_client = LLMClient(model=settings.LLM_VISION_MODEL)
