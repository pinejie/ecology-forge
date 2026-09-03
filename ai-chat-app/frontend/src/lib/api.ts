const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

let token = '';

export function setToken(t: string) {
  token = t;
  if (typeof window !== 'undefined') {
    localStorage.setItem('token', t);
  }
}

export function getToken(): string {
  if (token) return token;
  if (typeof window !== 'undefined') {
    token = localStorage.getItem('token') || '';
  }
  return token;
}

export function clearToken() {
  token = '';
  if (typeof window !== 'undefined') {
    localStorage.removeItem('token');
  }
}

async function request(path: string, options: RequestInit = {}) {
  const t = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (t) {
    headers['Authorization'] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    throw new Error('未登录或登录已过期');
  }
  return res;
}

// Auth
export async function login(username: string, password: string) {
  const res = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || '登录失败');
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function register(username: string, password: string) {
  const res = await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || '注册失败');
  const data = await res.json();
  setToken(data.token);
  return data;
}

// Sessions
export async function listSessions() {
  const res = await request('/sessions');
  if (!res.ok) throw new Error('获取会话列表失败');
  return res.json();
}

export async function createSession(title = '新对话', systemPrompt = '') {
  const res = await request('/sessions', {
    method: 'POST',
    body: JSON.stringify({ title, system_prompt: systemPrompt }),
  });
  if (!res.ok) throw new Error('创建会话失败');
  return res.json();
}

export async function deleteSession(id: string) {
  const res = await request(`/sessions/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('删除会话失败');
  return res.json();
}

export async function getMessages(sessionId: string) {
  const res = await request(`/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error('获取消息失败');
  return res.json();
}

export async function updateSession(id: string, data: { title?: string; system_prompt?: string }) {
  const res = await request(`/sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('更新会话失败');
  return res.json();
}

// Chat - direct to backend, no proxy
export async function chatCompletions(sessionId: string, message: string) {
  const t = getToken();
  const res = await fetch(`${API_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${t}`,
    },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return res;
}

// AI Config
export async function getAIConfig() {
  const res = await request('/config/ai');
  if (!res.ok) throw new Error('获取配置失败');
  return res.json();
}

export async function updateAIConfig(apiBaseUrl: string, apiKey: string, model: string) {
  const res = await request('/config/ai', {
    method: 'PUT',
    body: JSON.stringify({ api_base_url: apiBaseUrl, api_key: apiKey, model }),
  });
  if (!res.ok) throw new Error('更新配置失败');
  return res.json();
}
