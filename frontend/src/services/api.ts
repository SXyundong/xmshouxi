export interface ChatResponse {
  agent: string;
  answer: string;
}

export interface LogisticsWorkflowResponse {
  status: 'success';
  sku: string;
  product_name: string;
  sales: {
    days_3: number;
    days_7: number;
    days_15: number;
    days_30: number;
  };
  workbook: string;
  sheet: string;
  range: string;
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

export async function runLogisticsSalesWorkflow(): Promise<LogisticsWorkflowResponse> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `工作流执行失败：${res.status}`);
  }
  return body;
}
