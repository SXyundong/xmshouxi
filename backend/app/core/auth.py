"""Feishu session helpers and the cross-service SSO client."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request

from app.config import settings


class AuthError(RuntimeError):
    pass


def _safe_path(path: str) -> str:
    return path if path.startswith("/") and not path.startswith("//") else "/"


def sign_session(identity: dict) -> str:
    payload = {
        "open_id": str(identity["open_id"]),
        "display_name": str(identity.get("display_name") or "当前员工"),
        "department_names": list(identity.get("department_names") or []),
        "roles": list(identity.get("roles") or []),
        "exp": int(time.time()) + settings.FEISHU_SESSION_MAX_AGE,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        settings.FEISHU_SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def read_session(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    encoded, signature = value.rsplit(".", 1)
    expected = hmac.new(
        settings.FEISHU_SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, json.JSONDecodeError, binascii.Error):
        return None
    if payload.get("exp", 0) < time.time() or not payload.get("open_id"):
        return None
    return payload


def current_identity(request: Request) -> dict | None:
    identity = read_session(request.cookies.get("xmshouxi_session"))
    if identity:
        return identity
    if settings.FEISHU_SSO_REQUIRED:
        raise HTTPException(status_code=401, detail="请先通过飞书登录")
    return {"open_id": "local-demo", "display_name": "本地用户", "department_names": [], "roles": []}


async def exchange_sso_ticket(ticket: str) -> dict:
    if not settings.WORKFLOW_AUTH_URL or not settings.AGENT_SSO_SHARED_SECRET:
        raise AuthError("未配置工作流登录地址或 Agent 共享服务密钥")
    url = f"{settings.WORKFLOW_AUTH_URL.rstrip('/')}/api/internal/agent/sso/exchange"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json={"ticket": ticket},
                headers={"X-Agent-SSO-Secret": settings.AGENT_SSO_SHARED_SECRET},
            )
    except httpx.HTTPError as exc:
        raise AuthError("无法连接飞书工作流登录服务") from exc
    if response.status_code != 200:
        detail = response.json().get("detail", "登录票据无效") if response.content else "登录票据无效"
        raise AuthError(str(detail))
    return response.json()


def workflow_login_url(return_to: str) -> str:
    query = urlencode({"return_to": _safe_path(return_to)})
    return f"{settings.WORKFLOW_AUTH_URL.rstrip('/')}/auth/agent/start?{query}"
