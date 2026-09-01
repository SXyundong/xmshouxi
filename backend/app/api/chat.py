from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.core.auth import AuthError, current_identity, exchange_sso_ticket, sign_session, workflow_login_url
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationMessageRequest,
    ConversationResponse,
    CurrentUserResponse,
)
from app.services.chat_service import ChatServiceError, chat_service
from app.services.aigc_service import AIGCServiceError, aigc_service

router = APIRouter()


def _conversation_response(item) -> dict:
    return {
        "id": str(item.id),
        "department": item.department,
        "title": item.title,
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
    }


def _message_response(item) -> dict:
    return {
        "id": str(item.id),
        "role": item.role,
        "content": item.content,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "metadata": item.metadata_json,
    }


@router.get("/auth/login")
def login(request: Request) -> RedirectResponse:
    return_to = request.query_params.get("return_to") or request.headers.get("referer") or "/"
    if not return_to.startswith("/") or return_to.startswith("//"):
        return_to = "/"
    return RedirectResponse(workflow_login_url(return_to), status_code=307)


@router.get("/auth/sso/callback")
async def sso_callback(ticket: str) -> Response:
    try:
        identity = await exchange_sso_ticket(ticket)
    except AuthError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=401)
    target_path = identity.get("target_path") or "/"
    if not str(target_path).startswith("/") or str(target_path).startswith("//"):
        target_path = "/"
    response = RedirectResponse(str(target_path), status_code=303)
    response.set_cookie(
        "xmshouxi_session",
        sign_session(identity),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=28800,
    )
    return response


@router.get("/auth/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("xmshouxi_session")
    return response


@router.get("/api/me", response_model=CurrentUserResponse)
def me(request: Request) -> dict:
    return current_identity(request)


@router.get("/api/conversations", response_model=list[ConversationResponse])
def list_conversations(request: Request, department: str | None = Query(default=None)) -> list[dict]:
    identity = current_identity(request)
    return [_conversation_response(item) for item in chat_service.list_conversations(identity["open_id"], department)]


@router.post("/api/conversations", response_model=ConversationResponse)
def create_conversation(request: Request, body: ConversationCreateRequest) -> dict:
    identity = current_identity(request)
    try:
        item = chat_service.create_conversation(identity["open_id"], body.department, body.title)
    except ChatServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _conversation_response(item)


@router.get("/api/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def conversation_detail(request: Request, conversation_id: uuid.UUID) -> dict:
    identity = current_identity(request)
    item = chat_service.get_conversation(identity["open_id"], conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="聊天不存在或无权访问")
    messages = chat_service.get_messages(identity["open_id"], conversation_id)
    return {**_conversation_response(item), "messages": [_message_response(message) for message in messages]}


@router.post("/api/conversations/{conversation_id}/messages")
async def send_conversation_message(request: Request, conversation_id: uuid.UUID, body: ConversationMessageRequest) -> dict:
    identity = current_identity(request)
    try:
        result = await chat_service.send_message(identity["open_id"], conversation_id, body.message)
    except ChatServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "conversation": _conversation_response(result["conversation"]),
        "agent": result["agent"],
        "user_message": _message_response(result["user"]),
        "assistant_message": _message_response(result["assistant"]),
    }


@router.post("/api/conversations/{conversation_id}/aigc/video-prompt")
async def generate_aigc_video_prompt(
    request: Request,
    conversation_id: uuid.UUID,
    brief: str = Form(default=""),
    platform: str = Form(default="TikTok / 短视频"),
    duration_seconds: str = Form(default="10"),
    aspect_ratio: str = Form(default="9:16"),
    style: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Generate a Seedance prompt from product images in the ads department."""
    identity = current_identity(request)
    try:
        result = await aigc_service.generate_video_prompt(
            identity["open_id"], conversation_id, brief, platform, duration_seconds,
            aspect_ratio, style, files,
        )
    except AIGCServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "conversation": _conversation_response(result["conversation"]),
        "agent": "广告Agent",
        "user_message": _message_response(result["user"]),
        "assistant_message": _message_response(result["assistant"]),
    }


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """Legacy compatibility endpoint; new clients should use conversation APIs."""
    identity = current_identity(request)
    try:
        conversation = chat_service.create_conversation(identity["open_id"], req.department, req.message[:42])
        result = await chat_service.send_message(identity["open_id"], conversation.id, req.message)
    except ChatServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatResponse(agent=result["agent"], answer=result["assistant"].content)
