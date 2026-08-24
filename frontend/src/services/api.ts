export interface ChatResponse {
  agent: string;
  answer: string;
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
