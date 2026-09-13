export const API=(import.meta.env.VITE_API_URL || '') + '/api';
export async function post<T>(url:string, body:unknown):Promise<T>{const r=await fetch(API+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail);return r.json()}
