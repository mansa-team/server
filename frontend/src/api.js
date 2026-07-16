const BASE = '';  // ponytail: proxy handles routing in dev; use env var for production

function authHeaders() {
  const token = localStorage.getItem('token');
  const h = { 'Content-Type': 'application/json' };
  if (token) h['X-Access-Token'] = token;
  return h;
}

export async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { ...authHeaders(), ...opts.headers },
    credentials: 'include',
  });
  return res;
}

export async function login(email, password) {
  const res = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: email, password }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'Login failed');
  }
  return res.json();
}

export async function register(email, password, username) {
  const res = await apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, username: username || email.split('@')[0] }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'Registration failed');
  }
  return res.json();
}

export async function logout() {
  await apiFetch('/auth/logout', { method: 'POST' }).catch(() => {});
  localStorage.removeItem('token');
}

export async function fetchMe() {
  const token = localStorage.getItem('token');
  if (token) {
    try {
      const res = await fetch(BASE + '/user/me', {
        headers: { Authorization: 'Bearer ' + token },
        credentials: 'include',
      });
      if (res.ok) return res.json();
      localStorage.removeItem('token');
    } catch {
      localStorage.removeItem('token');
    }
  }
  // Cookie-only fallback
  try {
    const res = await fetch(BASE + '/user/me', { credentials: 'include' });
    if (res.ok) return res.json();
  } catch {}
  return null;
}

export function extractHashToken() {
  const hashToken = new URLSearchParams(window.location.hash.slice(1)).get('token');
  if (hashToken) {
    localStorage.setItem('token', hashToken);
    history.replaceState(null, '', window.location.pathname + window.location.search);
    return hashToken;
  }
  return null;
}

export function googleAuthUrl() {
  return BASE + '/auth/google?redirect_url=' + encodeURIComponent(location.href);
}

export async function fetchSessions() {
  const res = await apiFetch('/prometheus/sessions');
  if (!res.ok) throw new Error('Failed to load sessions');
  const data = await res.json();
  return data.sessions || data || [];
}

export async function createSession() {
  const res = await apiFetch('/prometheus/sessions', {
    method: 'POST',
    body: JSON.stringify({ title: 'New chat' }),
  });
  if (!res.ok) throw new Error('Failed to create session');
  return res.json();
}

export async function deleteSession(sessionId) {
  await apiFetch('/prometheus/sessions/' + sessionId, { method: 'DELETE' });
}

export async function fetchHistory(sessionId) {
  const res = await apiFetch('/prometheus/history/' + sessionId);
  if (!res.ok) throw new Error('Failed to load history');
  const data = await res.json();
  return data.history || data || [];
}

export async function streamChat(query, sessionId, onChunk, onDone, onError) {
  const res = await apiFetch('/prometheus/chat/stream', {
    method: 'POST',
    body: JSON.stringify({ query, sessionId }),
  });
  if (!res.ok) {
    onError('Could not get response');
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete last line in buffer
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6);
      if (data === '[DONE]') {
        onDone();
        return;
      }
      try {
        const event = JSON.parse(data);
        if (event.type === 'text') {
          onChunk(event.text);
        } else if (event.type === 'error') {
          onError(event.message);
        }
      } catch {}
    }
  }
  onDone();
}
