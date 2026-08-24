"""Minimal Streamable HTTP MCP client used by backend workflows."""

from __future__ import annotations

import json
from typing import Any

import httpx


class McpError(RuntimeError):
    pass


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
            raise McpError(payload["error"].get("message", "领星 MCP 调用失败"))
        result = payload.get("result", {})
        if result.get("isError"):
            raise McpError("领星 MCP 工具执行失败")
        for content in result.get("content", []):
            if content.get("type") != "text":
                continue
            text = content.get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        raise McpError("领星 MCP 没有返回可解析的数据")
