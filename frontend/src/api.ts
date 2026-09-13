export const API='/api';
export type Palette={hex:string;rgb:number[];pixels:number;coverage:number};
export type Layer={id:string;name:string;color:string;coverage:number;url:string;mask_url?:string;visible?:boolean;opacity?:number};
export async function post<T>(url:string, body:unknown):Promise<T>{const r=await fetch(API+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail);return r.json()}
