export interface ChatResponse {
  agent: string;
  answer: string;
}

export interface CurrentUser {
  open_id: string;
  display_name: string;
  department_names: string[];
  roles: string[];
}

export interface Conversation {
  id: string;
  department: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  status: 'completed' | 'failed' | 'pending' | 'interrupted';
  created_at: string;
  metadata?: {
    mode?: string;
    attachments?: Array<{ name: string; content_type: string; size: number; label?: string }>;
    [key: string]: unknown;
  } | null;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export interface ConversationTurnResponse {
  conversation: Conversation;
  agent: string;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}

export interface AigcVideoPromptResponse extends ConversationTurnResponse {}

export interface LogisticsWorkflowWarning {
  level: 'warning';
  code: string;
  message: string;
  rows: number[];
  identity?: {
    sku: string;
    lingxing_sku?: string;
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

export interface LogisticsWorkflowExport {
  status: 'success';
  filename: string;
  download_url: string;
  sheet: string;
  target_columns: string;
  total_rows: number;
  matched_rows: number;
  missing_rows: number;
  duplicate_groups: number;
  warnings: LogisticsWorkflowWarning[];
  expires_at: string;
}

export interface LogisticsWorkflowJob {
  status: 'queued' | 'running' | 'complete' | 'failed';
  job_id: string;
  progress: number;
  message: string;
  error: string;
  preview: LogisticsWorkflowPreview | null;
  result: LogisticsWorkflowResult | null;
  export: LogisticsWorkflowExport | null;
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

export async function getCurrentUser(): Promise<CurrentUser> {
  const res = await fetch('/api/me', { cache: 'no-store' });
  if (!res.ok) throw new Error(`身份验证失败：${res.status}`);
  return res.json();
}

export async function downloadInboundPlacementFeeWorkbook(file: File): Promise<Blob> {
  const form = new FormData();
  form.append('file', file, file.name);
  const res = await fetch('/api/workflows/sales/inbound-placement-fee', { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `入库配置费测算失败：${res.status}`);
  }
  return res.blob();
}

export async function listConversations(department?: string): Promise<Conversation[]> {
  const query = department ? `?department=${encodeURIComponent(department)}` : '';
  const res = await fetch(`/api/conversations${query}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`加载聊天列表失败：${res.status}`);
  return res.json();
}

export async function createConversation(department: string): Promise<Conversation> {
  const res = await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, title: '新聊天' }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `创建聊天失败：${res.status}`);
  return body;
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`加载聊天失败：${res.status}`);
  return res.json();
}

export async function sendConversationMessage(id: string, message: string): Promise<ConversationTurnResponse> {
  const res = await fetch(`/api/conversations/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `发送失败：${res.status}`);
  return body;
}

export async function generateAigcVideoPrompt(
  id: string,
  payload: {
    files: File[];
    brief: string;
    platform: string;
    durationSeconds: string;
    aspectRatio: string;
    style: string;
  },
): Promise<AigcVideoPromptResponse> {
  const form = new FormData();
  form.append('brief', payload.brief);
  form.append('platform', payload.platform);
  form.append('duration_seconds', payload.durationSeconds);
  form.append('aspect_ratio', payload.aspectRatio);
  form.append('style', payload.style);
  payload.files.forEach((file) => form.append('files', file, file.name));
  const res = await fetch(`/api/conversations/${encodeURIComponent(id)}/aigc/video-prompt`, {
    method: 'POST',
    body: form,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `提示词生成失败：${res.status}`);
  return body;
}

async function parseWorkflowResponse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `工作流执行失败：${res.status}`);
  }
  return body;
}

export async function previewLogisticsSalesWorkflow(
  forceRefresh = false,
): Promise<LogisticsWorkflowPreview> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
  const job = await parseWorkflowResponse<LogisticsWorkflowJob>(res);
  return waitForLogisticsSalesPreview(job.job_id);
}

export async function startLogisticsSalesPreview(
  forceRefresh = false,
): Promise<LogisticsWorkflowJob> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function getLogisticsSalesPreviewStatus(jobId: string): Promise<LogisticsWorkflowJob> {
  const res = await fetch(`/api/workflows/logistics/sales-to-stock-sheet/preview/${jobId}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function waitForLogisticsSalesPreview(jobId: string): Promise<LogisticsWorkflowPreview> {
  for (;;) {
    const job = await getLogisticsSalesPreviewStatus(jobId);
    if (job.status === 'complete' && job.preview) return job.preview;
    if (job.status === 'failed') throw new Error(job.error || '物流销量预览失败');
    await new Promise((resolve) => setTimeout(resolve, 1800));
  }
}

export async function executeLogisticsSalesWorkflow(
  previewId: string,
): Promise<LogisticsWorkflowJob> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preview_id: previewId }),
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function getLogisticsSalesExecuteStatus(jobId: string): Promise<LogisticsWorkflowJob> {
  const res = await fetch(`/api/workflows/logistics/sales-to-stock-sheet/execute/${jobId}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function waitForLogisticsSalesExecute(jobId: string): Promise<LogisticsWorkflowResult> {
  for (;;) {
    const job = await getLogisticsSalesExecuteStatus(jobId);
    if (job.status === 'complete' && job.result) return job.result;
    if (job.status === 'failed') throw new Error(job.error || '物流销量写入失败');
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

export async function startLogisticsSalesExport(
  forceRefresh = false,
): Promise<LogisticsWorkflowJob> {
  const res = await fetch('/api/workflows/logistics/sales-to-stock-sheet/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function getLogisticsSalesExportStatus(jobId: string): Promise<LogisticsWorkflowJob> {
  const res = await fetch(`/api/workflows/logistics/sales-to-stock-sheet/export/${jobId}`, {
    method: 'GET',
    cache: 'no-store',
  });
  return parseWorkflowResponse<LogisticsWorkflowJob>(res);
}

export async function waitForLogisticsSalesExport(jobId: string): Promise<LogisticsWorkflowExport> {
  for (;;) {
    const job = await getLogisticsSalesExportStatus(jobId);
    if (job.status === 'complete' && job.export) return job.export;
    if (job.status === 'failed') throw new Error(job.error || '物流销量 Excel 导出失败');
    await new Promise((resolve) => setTimeout(resolve, 1800));
  }
}
