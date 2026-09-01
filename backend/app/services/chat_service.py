"""Persistence and bounded-context orchestration for department chats."""

from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import agent_registry
from app.core.agent_engine import agent_engine
from app.core.llm_client import LLMResult
from app.db.models import ChatConversation, ChatMessage
from app.db.session import SessionLocal


class ChatServiceError(RuntimeError):
    pass


class ChatService:
    def list_conversations(self, owner_open_id: str, department: str | None = None) -> list[ChatConversation]:
        with SessionLocal() as db:
            query = select(ChatConversation).where(
                ChatConversation.owner_open_id == owner_open_id,
                ChatConversation.status == "active",
            )
            if department:
                query = query.where(ChatConversation.department == department)
            query = query.order_by(ChatConversation.updated_at.desc(), ChatConversation.created_at.desc())
            return list(db.scalars(query).all())

    def create_conversation(self, owner_open_id: str, department: str, title: str = "新聊天") -> ChatConversation:
        self._validate_department(department)
        conversation = ChatConversation(
            id=uuid.uuid4(), owner_open_id=owner_open_id, department=department, title=(title or "新聊天")[:255]
        )
        with SessionLocal() as db:
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            return conversation

    def get_conversation(self, owner_open_id: str, conversation_id: uuid.UUID) -> ChatConversation | None:
        with SessionLocal() as db:
            return db.scalar(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                )
            )

    def get_messages(self, owner_open_id: str, conversation_id: uuid.UUID) -> list[ChatMessage]:
        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation.id).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                )
            )
            if conversation is None:
                raise ChatServiceError("聊天不存在或无权访问")
            query = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.sequence_no)
            return list(db.scalars(query).all())

    async def send_message(self, owner_open_id: str, conversation_id: uuid.UUID, content: str) -> dict:
        content = content.strip()
        if not content:
            raise ChatServiceError("消息不能为空")
        if len(content) > 8000:
            raise ChatServiceError("单条消息不能超过 8000 个字符")

        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.owner_open_id == owner_open_id,
                    ChatConversation.status == "active",
                )
                .with_for_update()
            )
            if conversation is None:
                raise ChatServiceError("聊天不存在或无权访问")
            previous_messages = list(
                db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation.id, ChatMessage.status == "completed")
                    .order_by(ChatMessage.sequence_no.desc())
                    .limit(30)
                ).all()
            )
            previous_messages.reverse()
            next_sequence = db.scalar(
                select(ChatMessage.sequence_no)
                .where(ChatMessage.conversation_id == conversation.id)
                .order_by(ChatMessage.sequence_no.desc())
                .limit(1)
            ) or 0
            user_message = ChatMessage(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                sequence_no=next_sequence + 1,
                role="user",
                content=content,
                status="completed",
            )
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            if conversation.title == "新聊天":
                conversation.title = content[:42] + ("…" if len(content) > 42 else "")
            db.add(user_message)
            db.commit()
            department = conversation.department
            history = [{"role": item.role, "content": item.content} for item in previous_messages]

        started_at = time.perf_counter()
        try:
            result = await agent_engine.run_with_result(department, content, history)
            llm_result = result["result"]
            assistant_content = result["answer"]
            status = "completed"
            error_code = None
        except Exception as exc:
            llm_result = LLMResult(content="", model="unknown")
            assistant_content = "模型暂时不可用，请稍后重试。你的问题已经保存，可以点击重试。"
            status = "failed"
            error_code = type(exc).__name__[:64]

        with SessionLocal() as db:
            conversation = db.scalar(
                select(ChatConversation)
                .where(ChatConversation.id == conversation_id, ChatConversation.owner_open_id == owner_open_id)
                .with_for_update()
            )
            if conversation is None:
                raise ChatServiceError("聊天不存在或无权访问")
            next_sequence = db.scalar(
                select(ChatMessage.sequence_no)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.sequence_no.desc())
                .limit(1)
            ) or 0
            assistant_message = ChatMessage(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                sequence_no=next_sequence + 1,
                role="assistant",
                content=assistant_content,
                status=status,
                model=llm_result.model,
                prompt_tokens=llm_result.prompt_tokens,
                completion_tokens=llm_result.completion_tokens,
                total_tokens=llm_result.total_tokens,
                provider_request_id=llm_result.request_id,
                latency_ms=llm_result.latency_ms or round((time.perf_counter() - started_at) * 1000),
                error_code=error_code,
            )
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            db.add(assistant_message)
            db.commit()
            return {"agent": agent_registry.get(department).name, "user": user_message, "assistant": assistant_message, "conversation": conversation}

    @staticmethod
    def _validate_department(department: str) -> None:
        if agent_registry.get(department) is None:
            raise ChatServiceError(f"未找到部门「{department}」")


chat_service = ChatService()
