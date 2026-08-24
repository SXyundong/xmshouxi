from pydantic import BaseModel


class ChatRequest(BaseModel):
    department: str
    message: str


class ChatResponse(BaseModel):
    agent: str
    answer: str


class LogisticsSalesValues(BaseModel):
    days_3: int
    days_7: int
    days_15: int
    days_30: int


class LogisticsSalesWorkflowResponse(BaseModel):
    status: str
    sku: str
    product_name: str
    sales: LogisticsSalesValues
    workbook: str
    sheet: str
    range: str
    updated_at: str
