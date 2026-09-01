"""First-phase product-image to Seedance prompt workflow."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import time
from pathlib import PurePath
import uuid

from fastapi import UploadFile
from sqlalchemy import select

from app.config import settings
from app.core.llm_client import LLMResult, vision_llm_client
from app.db.models import ChatConversation, ChatMessage
from app.db.session import SessionLocal
from app.prompts.seedance_prompt_zh import SEEDANCE_VIDEO_PROMPT_SYSTEM


class AIGCServiceError(RuntimeError):
    pass


_IMAGE_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
    "image/webp": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
}


async def _read_image(file: UploadFile) -> tuple[str, bytes]:
    content = await file.read(settings.AIGC_MAX_IMAGE_BYTES + 1)
    if not content:
        raise AIGCServiceError(f"图片「{file.filename or '未命名文件'}」为空")
    if len(content) > settings.AIGC_MAX_IMAGE_BYTES:
        raise AIGCServiceError(
            f"图片「{file.filename or '未命名文件'}」超过 {settings.AIGC_MAX_IMAGE_BYTES // 1024 // 1024} MB 限制"
        )
    for mime, matches in _IMAGE_SIGNATURES.items():
        if matches(content):
            return mime, content
    raise AIGCServiceError(f"图片「{file.filename or '未命名文件'}」格式不受支持，请使用 JPG、PNG、GIF 或 WebP")


def _image_label(index: int) -> str:
    return f"图片{index}"


class AIGCService:
    async def generate_video_prompt(
        self,
        owner_open_id: str,
        conversation_id: uuid.UUID,
        brief: str,
        platform: str,
        duration_seconds: str,
        aspect_ratio: str,
        style: str,
        files: list[UploadFile],
    ) -> dict:
        if len(files) == 0:
            raise AIGCServiceError("请至少上传一张商品图片")
        if len(files) > settings.AIGC_MAX_IMAGE_COUNT:
            raise AIGCServiceError(f"最多上传 {settings.AIGC_MAX_IMAGE_COUNT} 张商品图片")

        images: list[tuple[str, bytes, str]] = []
        total_bytes = 0
        for index, file in enumerate(files, start=1):
            mime, content = await _read_image(file)
            total_bytes += len(content)
            if total_bytes > settings.AIGC_MAX_TOTAL_IMAGE_BYTES:
                raise AIGCServiceError(
                    f"商品图片总大小不能超过 {settings.AIGC_MAX_TOTAL_IMAGE_BYTES // 1024 // 1024} MB"
                )
            images.append((mime, content, PurePath(file.filename or f"image-{index}").name))

        conversation = self._get_conversation(owner_open_id, conversation_id)
        if conversation.department != "ads":
            raise AIGCServiceError("AIGC 视频提示词目前仅支持广告部门")

        image_metadata = [
            {"name": filename, "content_type": mime, "size": len(content), "label": _image_label(index)}
            for index, (mime, content, filename) in enumerate(images, start=1)
        ]
        user_content = self._build_user_brief(brief, platform, duration_seconds, aspect_ratio, style, image_metadata)
        started_at = time.perf_counter()
        self._save_user_message(owner_open_id, conversation_id, user_content, image_metadata)

        message_content: list[dict] = [{"type": "text", "text": user_content}]
        for index, (mime, content, _) in enumerate(images, start=1):
            encoded = base64.b64encode(content).decode("ascii")
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{encoded}",
                        "detail": "original",
                    },
                }
            )

        try:
            result = await vision_llm_client.complete(
                [
                    {"role": "system", "content": SEEDANCE_VIDEO_PROMPT_SYSTEM},
                    {"role": "user", "content": message_content},
                ],
                temperature=0.7,
            )
            answer = result.content or "模型没有返回提示词，请稍后重试。"
            status = "completed"
            error_code = None
        except Exception as exc:
            result = LLMResult(content="", model=settings.LLM_VISION_MODEL)
            answer = "商品图已收到，但视觉模型暂时不可用，请稍后重试。"
            status = "failed"
            error_code = type(exc).__name__[:64]

        assistant = self._save_assistant_message(
            owner_open_id,
            conversation_id,
            answer,
            image_metadata,
            result,
            status,
            error_code,
            round((time.perf_counter() - started_at) * 1000),
        )
        return {
            "conversation": self._get_conversation(owner_open_id, conversation_id),
            "user": self._get_latest_user_message(owner_open_id, conversation_id),
            "assistant": assistant,
        }

    @staticmethod
    def _build_user_brief(brief: str, platform: str, duration: str, ratio: str, style: str, images: list[dict]) -> str:
        image_labels = ", ".join(f"{item['label']}={item['name']}" for item in images)
        lines = [
            "请根据下面的商品参考图，为广告部门生成一份 AIGC 视频提示词。",
            f"商品图片：{image_labels}",
            f"用户需求：{brief.strip() or '请基于商品特点设计一支简洁、有购买吸引力的电商短视频。'}",
            f"投放平台：{platform.strip() or '未指定'}",
            f"视频时长：{duration.strip() or '10'} 秒",
            f"画面比例：{ratio.strip() or '9:16'}",
            f"风格偏好：{style.strip() or '明亮、干净、商业广告感'}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _get_conversation(owner_open_id: str, conversation_id: uuid.UUID) -> ChatConversation:
        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                )
            )
            if conversation is None:
                raise AIGCServiceError("聊天不存在或无权访问")
            return conversation

    @staticmethod
    def _save_user_message(owner_open_id: str, conversation_id: uuid.UUID, content: str, images: list[dict]) -> None:
        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                ).with_for_update()
            )
            if conversation is None:
                raise AIGCServiceError("聊天不存在或无权访问")
            next_sequence = db.scalar(
                select(ChatMessage.sequence_no).where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.sequence_no.desc()).limit(1)
            ) or 0
            db.add(ChatMessage(
                id=uuid.uuid4(), conversation_id=conversation_id, sequence_no=next_sequence + 1,
                role="user", content=content, status="completed",
                metadata_json={"mode": "aigc_video_prompt", "attachments": images},
            ))
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            if conversation.title == "新聊天":
                conversation.title = "AIGC 视频提示词"
            db.commit()

    @staticmethod
    def _save_assistant_message(
        owner_open_id: str,
        conversation_id: uuid.UUID,
        content: str,
        images: list[dict],
        result: LLMResult,
        status: str,
        error_code: str | None,
        latency_ms: int,
    ) -> ChatMessage:
        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                ).with_for_update()
            )
            if conversation is None:
                raise AIGCServiceError("聊天不存在或无权访问")
            next_sequence = db.scalar(
                select(ChatMessage.sequence_no).where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.sequence_no.desc()).limit(1)
            ) or 0
            assistant = ChatMessage(
                id=uuid.uuid4(), conversation_id=conversation_id, sequence_no=next_sequence + 1,
                role="assistant", content=content, status=status, model=result.model,
                prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens, provider_request_id=result.request_id,
                latency_ms=result.latency_ms or latency_ms, error_code=error_code,
                metadata_json={"mode": "aigc_video_prompt", "attachments": images},
            )
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            db.add(assistant)
            db.commit()
            db.refresh(assistant)
            return assistant

    def _get_latest_user_message(self, owner_open_id: str, conversation_id: uuid.UUID) -> ChatMessage:
        with SessionLocal() as db:
            message = db.scalar(
                select(ChatMessage).join(ChatConversation).where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatMessage.role == "user",
                ).order_by(ChatMessage.sequence_no.desc()).limit(1)
            )
            if message is None:
                raise AIGCServiceError("AIGC 请求已完成，但没有找到用户消息")
            return message


aigc_service = AIGCService()
