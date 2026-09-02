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
        events: list[dict[str, Any]] = []
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                # A stream may contain progress/notification events before the
                # JSON-RPC result. Prefer the first actual result or error.
                if "result" in event or "error" in event:
                    return event
                events.append(event)
        if events:
            return events[-1]
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
                json=self._rpc_request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "ecommerce-agent-v1",
                            "version": "1.0.0",
                        },
                    },
                ),
            )
            init.raise_for_status()
            session_id = init.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            initialized = await client.post(
                self.url,
                headers=headers,
                json=self._rpc_request(None, "notifications/initialized", {}),
            )
            initialized.raise_for_status()

            try:
                payload = await self._call_mcp_tool(
                    client,
                    headers,
                    name,
                    arguments,
                    request_id=2,
                )
                return self._parse_tool_result(payload)
            except McpError as exc:
                # LingXing's current public server exposes a tool gateway
                # (help/search/action) instead of the business tool names in
                # tools/list. Fall back only for an unknown-tool response so
                # real permission and parameter errors remain visible.
                if not self._is_unknown_tool_error(exc):
                    raise
                logger.info(
                    "LingXing MCP tool %s is behind the help/search/action gateway",
                    name,
                )
                return await self._call_via_gateway(
                    client,
                    headers,
                    name,
                    arguments,
                    request_id=10,
                )

    async def _call_via_gateway(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        name: str,
        arguments: dict[str, Any],
        request_id: int,
    ) -> Any:
        help_payload = await self._call_mcp_tool(
            client,
            headers,
            "help",
            {"query": name, "limit": 50, "offset": 0},
            request_id=request_id,
        )
        help_result = self._parse_tool_result(help_payload)
        tool = self._find_gateway_tool(help_result, name)
        if tool is None:
            raise McpError(f"领星 MCP 未找到业务工具：{name}")
        tool_id = str(tool.get("toolId") or name)

        search_payload = await self._call_mcp_tool(
            client,
            headers,
            "search",
            {"toolId": tool_id},
            request_id=request_id + 1,
        )
        search_result = self._parse_tool_result(search_payload)
        search_data = search_result.get("data") if isinstance(search_result, dict) else None
        if not isinstance(search_data, dict):
            raise McpError("领星 MCP search 没有返回业务工具 Schema")
        catalog_version = search_data.get("catalogVersion")
        schema_version = search_data.get("schemaVersion")
        if not catalog_version or not schema_version:
            raise McpError("领星 MCP search 返回的版本信息不完整")

        action_payload = await self._call_mcp_tool(
            client,
            headers,
            "action",
            {
                "toolId": tool_id,
                "catalogVersion": catalog_version,
                "schemaVersion": schema_version,
                "paramsJson": json.dumps(
                    arguments,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
            request_id=request_id + 2,
        )
        return self._parse_tool_result(action_payload)

    async def _call_mcp_tool(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        name: str,
        arguments: dict[str, Any],
        request_id: int,
    ) -> dict[str, Any]:
        response = await client.post(
            self.url,
            headers=headers,
            json=self._rpc_request(
                request_id,
                "tools/call",
                {"name": name, "arguments": arguments},
            ),
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
        return payload

    @staticmethod
    def _rpc_request(
        request_id: int | None,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            request["id"] = request_id
        request["params"] = params
        return request

    @staticmethod
    def _parse_tool_result(payload: dict[str, Any]) -> Any:
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise McpError("领星 MCP 返回结果格式异常")
        tool_error = result.get("isError")
        structured = result.get("structuredContent")
        if structured is not None:
            if tool_error:
                detail = (
                    structured.get("message")
                    or structured.get("msg")
                    or structured.get("error")
                    if isinstance(structured, dict)
                    else structured
                )
                raise McpError(detail or "领星 MCP 工具执行失败")
            return structured

        content_blocks = result.get("content", [])
        if isinstance(content_blocks, dict):
            content_blocks = [content_blocks]
        for content in content_blocks if isinstance(content_blocks, list) else []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "json":
                value = content.get("json", content.get("data"))
                if value is not None:
                    if tool_error:
                        raise McpError("领星 MCP 工具执行失败")
                    return value
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
        # Some MCP gateways return the tool envelope directly in `result`
        # without either content or structuredContent.
        if any(key in result for key in ("code", "data", "success", "msg", "message")):
            return result
        raise McpError("领星 MCP 没有返回可解析的数据")

    @staticmethod
    def _find_gateway_tool(result: Any, name: str) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if not isinstance(data, dict):
            return None
        tools = data.get("tools")
        if not isinstance(tools, list):
            return None
        for tool in tools:
            if isinstance(tool, dict) and tool.get("toolId") == name:
                return tool
        return None

    @staticmethod
    def _is_unknown_tool_error(error: McpError) -> bool:
        message = str(error).lower()
        return "unknown tool" in message or "tool not found" in message or "not found" in message
