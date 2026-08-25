from pydantic import BaseModel


class ChatRequest(BaseModel):
    department: str
    message: str


class ChatResponse(BaseModel):
    agent: str
    answer: str


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


class LogisticsSalesJobResponse(BaseModel):
    status: str
    job_id: str
    progress: int
    message: str
    error: str = ""
    preview: LogisticsSalesPreviewResponse | None = None
