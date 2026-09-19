const BASE = (import.meta.env.VITE_API_URL || '');
export const API = BASE + '/api';
// Backend image URLs already include the '/api' prefix, so resolve them
// against the backend origin (empty in dev, where Vite proxies '/api').
export const imageUrl = (path: string) => (path ? BASE + path : '');

export async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail);
  return r.json();
}

export async function uploadFile<T>(file: File): Promise<T> {
  const data = new FormData();
  data.append('file', file);
  const r = await fetch(API + '/image/upload', { method: 'POST', body: data });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: 'Unable to import this image.' }))).detail);
  return r.json();
}

async function downloadFrom(path: string, payload: unknown, filename: string): Promise<void> {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: 'Export failed.' }))).detail);
  const blob = await r.blob();
  const u = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = u; a.download = filename; a.click();
  URL.revokeObjectURL(u);
}

export const downloadPackage = (payload: unknown, filename: string) => downloadFrom('/export/package', payload, filename);
export const downloadSvg = (payload: unknown, filename: string) => downloadFrom('/export/svg', payload, filename);
