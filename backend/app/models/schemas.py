from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    department: str
    message: str


class ChatResponse(BaseModel):
    agent: str
    answer: str


class CurrentUserResponse(BaseModel):
    open_id: str
    display_name: str
    department_names: list[str] = []
    roles: list[str] = []


class ConversationCreateRequest(BaseModel):
    department: str
    title: str = "新聊天"


class ConversationResponse(BaseModel):
    id: str
    department: str
    title: str
    created_at: str
    updated_at: str


class ConversationMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    status: str
    created_at: str
    metadata: dict[str, Any] | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[ConversationMessageResponse] = []


class ConversationMessageRequest(BaseModel):
    message: str


class LogisticsWorkflowWarning(BaseModel):
    level: str
    code: str
    message: str
    rows: list[int]
    identity: dict[str, str] | None = None


class LogisticsSalesPreviewResponse(BaseModel):
    status: str
    preview_id: str
    workbook: str
    sheet: str
    target_columns: str
    total_rows: int
    unique_products: int
    matched_rows: int
    missing_rows: int
    duplicate_groups: int
    warnings: list[LogisticsWorkflowWarning]
    can_execute: bool
    expires_at: str


class LogisticsSalesPreviewRequest(BaseModel):
    force_refresh: bool = False


class LogisticsSalesExecuteRequest(BaseModel):
    preview_id: str


class LogisticsSalesExecuteResponse(BaseModel):
    status: str
    workbook: str
    sheet: str
    target_columns: str
    updated_rows: int
    skipped_rows: int
    duplicate_groups: int
    warnings: list[LogisticsWorkflowWarning]
    updated_at: str


class LogisticsSalesExportResponse(BaseModel):
    """A short-lived workbook generated from PostgreSQL data."""

    status: str
    filename: str
    download_url: str
    sheet: str
    target_columns: str
    total_rows: int
    matched_rows: int
    missing_rows: int
    duplicate_groups: int
    warnings: list[LogisticsWorkflowWarning]
    expires_at: str


class LogisticsSalesJobResponse(BaseModel):
    status: str
    job_id: str
    progress: int
    message: str
    error: str = ""
    preview: LogisticsSalesPreviewResponse | None = None
    result: LogisticsSalesExecuteResponse | None = None
    export: LogisticsSalesExportResponse | None = None
