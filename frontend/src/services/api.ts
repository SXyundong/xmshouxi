export interface ChatResponse {
  agent: string;
  answer: string;
}

export interface LogisticsWorkflowWarning {
  level: 'warning';
  code: string;
  message: string;
  rows: number[];
  identity?: {
    sku: string;
    amazon_sku: string;
    product_name: string;
    category: string;
    store: string;
    country: string;
  };
}

export interface LogisticsWorkflowPreview {
  status: 'preview';
  preview_id: string;
  workbook: string;
  sheet: string;
  target_columns: string;
  total_rows: number;
  unique_products: number;
  matched_rows: number;
  missing_rows: number;
  duplicate_groups: number;
  warnings: LogisticsWorkflowWarning[];
  can_execute: boolean;
  expires_at: string;
}

export interface LogisticsWorkflowResult {
  status: 'success';
  workbook: string;
  sheet: string;
  target_columns: string;
  updated_rows: number;
  skipped_rows: number;
  duplicate_groups: number;
  warnings: LogisticsWorkflowWarning[];
  updated_at: string;
}

export async function sendChat(
  department: string,
  message: string,
): Promise<ChatResponse> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, message }),
  });

  if (!res.ok) {
    throw new Error(`请求失败：${res.status}`);
  }

  return res.json();
}

async function parseWorkflowResponse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `工作流执行失败：${res.status}`);
  }
  return body;
}

export async function previewLogisticsSalesWorkflow(): Promise<LogisticsWorkflowPreview> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return parseWorkflowResponse<LogisticsWorkflowPreview>(res);
}

export async function executeLogisticsSalesWorkflow(
  previewId: string,
): Promise<LogisticsWorkflowResult> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preview_id: previewId }),
  });
  return parseWorkflowResponse<LogisticsWorkflowResult>(res);
}
