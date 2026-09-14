const BASE=(import.meta.env.VITE_API_URL || '');
export const API=BASE + '/api';
// Backend image URLs already include the '/api' prefix, so resolve them
// against the backend origin (empty in dev, where Vite proxies '/api').
export const imageUrl=(path:string)=>path?BASE+path:'';
export async function post<T>(url:string, body:unknown):Promise<T>{const r=await fetch(API+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail);return r.json()}
