const BASE=(import.meta.env.VITE_API_URL || '');
export const API=BASE + '/api';
// Backend image URLs already include the '/api' prefix, so resolve them
// against the backend origin (empty in dev, where Vite proxies '/api').
export const imageUrl=(path:string)=>path?BASE+path:'';

// FastAPI reports errors as {detail: string} or, for validation failures,
// {detail: [{msg, loc}, ...]} -- turn either into a readable message.
async function errorFrom(r:Response, fallback:string):Promise<Error>{
  const body=await r.json().catch(()=>null);
  const d=body?.detail;
  const msg=typeof d==='string'?d:Array.isArray(d)?d.map((x:any)=>x?.msg).filter(Boolean).join('; '):'';
  return new Error(msg || (r.status===404?'Not found.':'') || fallback);
}

// fetch() only rejects when the server can't be reached at all -- usually the
// backend window was closed or crashed -- so say that instead of "Failed to fetch".
async function send(url:string, init:RequestInit):Promise<Response>{
  try{return await fetch(API+url,init);}
  catch{throw new Error('Cannot reach the LoomLab backend — make sure it is running (port 8003), then try again.');}
}

export function saveBlob(blob:Blob, filename:string){
  const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=filename;
  document.body.appendChild(a);a.click();a.remove();
  // revoking synchronously can cancel the download in Firefox/Safari
  setTimeout(()=>URL.revokeObjectURL(u),2000);
}

export async function post<T>(url:string, body:unknown):Promise<T>{
  const r=await send(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok)throw await errorFrom(r,'The request failed.');
  return r.json();
}

export async function postFile<T>(url:string, file:File):Promise<T>{
  const data=new FormData();data.append('file',file);
  const r=await send(url,{method:'POST',body:data});
  if(!r.ok)throw await errorFrom(r,'Unable to import this file.');
  return r.json();
}

export async function download(url:string, payload:unknown, filename:string):Promise<void>{
  const r=await send(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok)throw await errorFrom(r,'Export failed.');
  saveBlob(await r.blob(),filename);
}
