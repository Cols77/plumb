export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export function takeCapability(): string {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (location.hash) history.replaceState(history.state, '', location.pathname + location.search);
  if (token) { try { sessionStorage.setItem('plumb.capability', token); } catch { /* In-memory launch still works. */ } }
  if (token) return token;
  try { return sessionStorage.getItem('plumb.capability') ?? ''; } catch { return ''; }
}
export async function api<T>(path: string, capability: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {
    Authorization: `Bearer ${capability}`, ...(body === undefined ? {} : {'Content-Type':'application/json'}),
  }, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new ApiError(data.error || `Request failed (${response.status})`, response.status);
  return data as T;
}
