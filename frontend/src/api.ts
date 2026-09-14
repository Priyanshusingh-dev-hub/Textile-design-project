const BASE=(import.meta.env.VITE_API_URL || '');
export const API=BASE + '/api';
// Backend image URLs already include the '/api' prefix, so resolve them
// against the backend origin (empty in dev, where Vite proxies '/api').
export const imageUrl=(path:string)=>path?BASE+path:'';
export async function downloadZip(payload:unknown, filename:string):Promise<boolean>{
  const r=await fetch(API+'/export/zip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok)return false;
  const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=filename;a.click();URL.revokeObjectURL(u);
  return true;
}
export async function post<T>(url:string, body:unknown):Promise<T>{const r=await fetch(API+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail);return r.json()}
