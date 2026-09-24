const BASE = (import.meta.env.VITE_API_URL || '');
export const API = BASE + '/api';
// Backend image URLs already include the '/api' prefix, so resolve them
// against the backend origin (empty in dev, where Vite proxies '/api').
export const imageUrl = (path: string) => (path ? BASE + path : '');

/** FastAPI reports a plain string for our own errors but an array of
 * {loc, msg} objects for request-validation failures. Render either as one
 * readable line so the UI never shows "[object Object]". */
export function errorText(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: (string | number)[] };
    if (first?.msg) {
      const field = first.loc?.filter(p => p !== 'body').join('.');
      return field ? `${first.msg} (${field})` : first.msg;
    }
  }
  return fallback;
}

/** What the operator sees when the engine can't be reached at all. The
 *  browser's own words for this ("Failed to fetch", "NetworkError when
 *  attempting to fetch resource") mean nothing to them; at a mill the cause is
 *  almost always that the LoomLab engine window was closed. */
export const OFFLINE_TEXT =
  "Can't reach the LoomLab engine. If you started it with run-windows.bat, check its "
  + 'black window is still open (start it again if not), then retry. Your work so far is kept.';

/** fetch, with a network failure turned into words the operator can act on. */
export async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new Error(OFFLINE_TEXT);
  }
}

async function failure(r: Response, fallback: string): Promise<Error> {
  const body = await r.json().catch(() => null);
  return new Error(errorText(body?.detail, fallback || r.statusText));
}

export async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await request(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await failure(r, 'That request failed.');
  return r.json();
}

export async function uploadFile<T>(file: File): Promise<T> {
  const data = new FormData();
  data.append('file', file);
  const r = await request(API + '/image/upload', { method: 'POST', body: data });
  if (!r.ok) throw await failure(r, 'Unable to import this image.');
  return r.json();
}

async function downloadFrom(path: string, payload: unknown, filename: string): Promise<void> {
  const r = await request(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw await failure(r, 'Export failed.');
  const blob = await r.blob();
  const u = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = u; a.download = filename; a.click();
  URL.revokeObjectURL(u);
}

export const downloadPackage = (payload: unknown, filename: string) => downloadFrom('/export/package', payload, filename);
export const downloadSvg = (payload: unknown, filename: string) => downloadFrom('/export/svg', payload, filename);
