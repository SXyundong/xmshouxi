"""Minimal Streamable HTTP MCP client used by backend workflows."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx


class McpError(RuntimeError):
    def __init__(self, message: Any = None):
        # Some MCP error envelopes contain a null `message`. Never expose
        # Python's stringified "None" to the UI.
        super().__init__(message or "领星 MCP 调用失败")


logger = logging.getLogger(__name__)


class StreamableHttpMcpClient:
    def __init__(self, url: str, api_key: str, timeout: float = 60.0):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        if "text/event-stream" not in response.headers.get("content-type", ""):
            return response.json()
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise McpError("领星 MCP 返回了空事件流")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self.api_key:
            raise McpError("未配置 LINGXING_MCP_KEY")

        headers = {
            "X-Mcp-Key": self.api_key,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            init = await client.post(
                self.url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "ecommerce-agent-v1",
                            "version": "1.0.0",
                        },
                    },
                },
            )
            init.raise_for_status()
            session_id = init.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            initialized = await client.post(
                self.url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
            )
            initialized.raise_for_status()

            response = await client.post(
                self.url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            response.raise_for_status()
            payload = self._decode_response(response)

        if payload.get("error"):
            error = payload["error"]
            logger.warning(
                "LingXing MCP JSON-RPC error: code=%r message=%r data=%s",
                error.get("code"),
                error.get("message"),
                repr(error.get("data"))[:500],
            )
            raise McpError(error.get("message") or error.get("data") or "领星 MCP 调用失败")
        result = payload.get("result", {})
        tool_error = result.get("isError")
        for content in result.get("content", []):
            if content.get("type") != "text":
                continue
            text = content.get("text", "")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = text
            if tool_error:
                if isinstance(parsed, dict):
                    detail = (
                        parsed.get("message")
                        or parsed.get("msg")
                        or parsed.get("error")
                    )
                else:
                    detail = parsed
                logger.warning(
                    "LingXing MCP tool error: detail=%s",
                    repr(detail or text)[:500],
                )
                raise McpError(detail or "领星 MCP 工具执行失败")
            return parsed
        if tool_error:
            logger.warning("LingXing MCP tool error: response had no text content")
            raise McpError("领星 MCP 工具执行失败")
        raise McpError("领星 MCP 没有返回可解析的数据")
