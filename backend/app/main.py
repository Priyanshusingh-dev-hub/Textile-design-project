import asyncio
import os
from io import BytesIO
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, UnidentifiedImageError
from .models import *
from .core import store
from .core.archive import build_zip
from .core.psd_import import is_psd, open_psd_any
from .color_engine import engine as colors
from .separation_engine import engine as separation
from .repeat_engine import engine as repeat
from .project_engine import engine as projects
from .halftone_engine import engine as halftone
from .design_ai import analyzer as design_analyzer, instructions as design_instructions

app=FastAPI(title='LoomLab API', version='0.1.0')
_origins=[o.strip() for o in os.environ.get('ALLOWED_ORIGINS','http://localhost:5173').split(',') if o.strip()]
app.add_middleware(CORSMiddleware,allow_origins=_origins,allow_methods=['*'],allow_headers=['*'])

CLEANUP_INTERVAL_SECONDS = float(os.environ.get('CLEANUP_INTERVAL_SECONDS', 3600))

async def _cleanup_loop():
    while True:
        try: store.cleanup_expired()
        except Exception: pass
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

@app.on_event('startup')
async def _on_startup():
    store.cleanup_expired()  # run once immediately so stale files don't linger between restarts
    asyncio.create_task(_cleanup_loop())
def image_response(image, name='design.png', fmt='PNG', dpi=300, download=False):
    b=BytesIO(); image.save(b,format=fmt, dpi=(dpi,dpi)); b.seek(0)
    headers={'Content-Disposition':f'attachment; filename="{name}"'} if download else {}
    return StreamingResponse(b,media_type=f'image/{fmt.lower()}',headers=headers)
def psd_response(image, name='loomlab.psd'):
    """Write a baseline RGB PSD that Photoshop, Affinity and Photopea can open."""
    rgb=image.convert('RGB'); w,h=rgb.size; raw=__import__('numpy').asarray(rgb)
    payload=b'8BPS'+(1).to_bytes(2,'big')+(b'\0'*6)+(3).to_bytes(2,'big')+h.to_bytes(4,'big')+w.to_bytes(4,'big')+(8).to_bytes(2,'big')+(3).to_bytes(2,'big')+(0).to_bytes(4,'big')+(0).to_bytes(4,'big')+(0).to_bytes(4,'big')+(0).to_bytes(2,'big')
    payload+=raw[:,:,0].tobytes()+raw[:,:,1].tobytes()+raw[:,:,2].tobytes()
    return StreamingResponse(BytesIO(payload),media_type='image/vnd.adobe.photoshop',headers={'Content-Disposition':f'attachment; filename="{name}"'})
def image_meta(image_id, image):
    w,h=image.size; return {'image_id':image_id,'width':w,'height':h,'aspect_ratio':round(w/h,3),'url':f'/api/image/{image_id}'}
_MULTICHANNEL_PALETTE=['#E63946','#457B9D','#2A9D8F','#E9C46A','#F4A261','#8338EC','#3A86FF','#FF006E','#06D6A0','#FFD166','#118AB2','#073B4C']
def _channels_to_layers(channels):
    """channels: [(name, grayscale mask)] where black=ink, white=blank (the
    print-ready convention). Returns [(name, color_hex, ink_layer, display, coverage)]
    in the same shape separation.create() produces, so a Multichannel PSD's
    already-separated screens plug straight into the Layers panel."""
    out=[]
    for i,(name,gray) in enumerate(channels):
      hx=_MULTICHANNEL_PALETTE[i % len(_MULTICHANNEL_PALETTE)]
      alpha=255-np.asarray(gray)
      rgba=np.zeros((*alpha.shape,4),dtype=np.uint8); rgba[:,:,3]=alpha
      out.append((name,hx,Image.fromarray(rgba),gray,round(float((alpha>0).mean()*100),2)))
    return out
@app.post('/api/image/upload')
async def upload(file:UploadFile=File(...)):
    raw=await file.read()
    if len(raw)>80*1024*1024: raise HTTPException(413,'Image is larger than the 80 MB import limit.')
    if is_psd(raw):
      try: kind,data=open_psd_any(raw)
      except ValueError as e: raise HTTPException(422,str(e))
      if kind=='channels':
        built=_channels_to_layers(data)
        layers=[]
        for name,hx,layer,display,coverage in built:
          lid=store.save(layer); did=store.save(display); pid=store.save(separation.plate(layer,hx))
          layers.append({'id':lid,'name':name,'color':hx,'coverage':coverage,'url':f'/api/image/{lid}','mask_url':f'/api/image/{did}','plate_url':f'/api/image/{pid}'})
        preview=separation.composite_masks([(layer,hx,100) for _,hx,layer,_,_ in built],built[0][2].size)
        image_id=store.save(preview)
        return image_meta(image_id,preview)|{'file_name':file.filename,'file_size':len(raw),'layers':layers}
      img=data
    else:
      if not file.content_type or not file.content_type.startswith('image/'): raise HTTPException(415,'Please choose a PNG, JPG, WEBP, TIFF, or PSD image.')
      try: img=Image.open(BytesIO(raw)); img.load()
      except UnidentifiedImageError: raise HTTPException(422,'The selected file is not a valid image.')
    image_id=store.save(img)
    return image_meta(image_id,img)|{'file_name':file.filename,'file_size':len(raw)}
@app.post('/api/image/sample')
def sample():
    """A small floral pattern for immediately exploring the workflow."""
    size=720; image=Image.new('RGBA',(size,size),'#F4E8CC'); d=ImageDraw.Draw(image)
    for y in range(-40,size+80,120):
      for x in range(-40,size+80,120):
        d.ellipse((x-48,y-13,x+48,y+13),fill='#477052')
        for angle in range(0,360,45):
          import math; dx=math.cos(math.radians(angle))*31; dy=math.sin(math.radians(angle))*31
          d.ellipse((x+dx-23,y+dy-15,x+dx+23,y+dy+15),fill='#C95368')
        d.ellipse((x-12,y-12,x+12,y+12),fill='#D9A43E')
    image_id=store.save(image); return image_meta(image_id,image)|{'file_name':'loomlab-sample-floral.png','file_size':0}
@app.get('/api/image/{image_id}')
def get_image(image_id:str): return image_response(store.load(image_id))
@app.post('/api/colors/analyze')
def analyze(req:AnalyzeRequest): return {'palette':colors.analyze(store.load(req.image_id),req.colors)}
@app.post('/api/colors/reduce')
def reduce(req:ReduceRequest):
    image=colors.reduce(store.load(req.image_id),req.colors); image_id=store.save(image)
    return image_meta(image_id,image)|{'palette':colors.analyze(image,req.colors)}
@app.post('/api/colors/map')
def map_(req:MapRequest):
    image=colors.map_colors(store.load(req.image_id),req.mappings); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/colors/merge')
def merge(req:MergeRequest):
    image=colors.merge(store.load(req.image_id),req.sources,req.target,req.threshold); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/separation/create')
def separate(req:SeparationRequest):
    image=store.load(req.image_id); layers=[]
    built=separation.soft_create(image,req.palette) if req.mode=='gradient' else separation.create(image,req.palette,req.cleanup)
    for i,(hx,layer,display,coverage) in enumerate(built):
      lid=store.save(layer); display_id=store.save(display); plate_id=store.save(separation.plate(layer,hx))
      layers.append({'id':lid,'name':f'Ink {i+1}','color':hx,'coverage':coverage,'url':f'/api/image/{lid}','mask_url':f'/api/image/{display_id}','plate_url':f'/api/image/{plate_id}'})
    return {'layers':layers}
@app.post('/api/halftone/preview')
def halftone_preview(req:HalftoneRequest):
    image=halftone.apply(store.load(req.image_id),req.cell_size,req.angle); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/separation/composite')
def composite(req:CompositeRequest):
    image=separation.composite(store.load(req.image_id),req.palette); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/separation/composite-layers')
def composite_layers(req:LayerCompositeRequest):
    if not req.layers: image=Image.new('RGBA',(1,1),(0,0,0,0))
    else:
      first=store.load(req.layers[0].id)
      image=separation.composite_masks([(store.load(item.id),item.color,item.opacity) for item in req.layers],first.size)
    image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/repeat/create')
def make_repeat(req:RepeatRequest):
    image=repeat.create(store.load(req.image_id),req.columns,req.rows,req.mode,req.offset_x,req.offset_y); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/repeat/check-seam')
def check_seam(req:AnalyzeRequest): return repeat.seam_score(store.load(req.image_id))
@app.post('/api/export')
def export(req:ExportRequest):
    image=store.load(req.image_id)
    if req.format=='psd': return psd_response(image)
    fmts={'png':'PNG','jpg':'JPEG','webp':'WEBP'}
    if req.format=='jpg': image=image.convert('RGB')
    return image_response(image,f'loomlab-export.{req.format}',fmts[req.format],req.dpi,True)
@app.post('/api/export/zip')
def export_zip(req:ZipExportRequest):
    loaded=[(item, store.load(item.id)) for item in req.layers]
    if req.content=='film':
      entries=[(it.name, separation.to_print_ready(img)) for it,img in loaded]
    elif req.content=='plate':
      entries=[(it.name, separation.plate(img, it.color or '#000000')) for it,img in loaded]
    else:
      entries=[(it.name, img) for it,img in loaded]
      if req.composite_image_id: entries.append(('composite', store.load(req.composite_image_id)))
    if not entries: raise HTTPException(400,'Nothing to export — no layers or composite were provided.')
    data=build_zip(entries,fmt=req.format,dpi=req.dpi)
    filename={'film':'loomlab-screens','plate':'loomlab-plates','mask':'loomlab-layers'}[req.content]+'.zip'
    return StreamingResponse(BytesIO(data),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
@app.post('/api/design/dna')
def design_dna(req:DnaRequest):
    return design_analyzer.build_dna(store.load(req.image_id), req.description)
@app.post('/api/design/instructions')
def design_instr(req:InstructionRequest):
    dna=design_analyzer.build_dna(store.load(req.image_id), req.description)
    out=design_instructions.generate(dna, req.intent, req.fidelity, req.user_request, req.description, req.target_colors)
    return {'dna':dna}|out
@app.post('/api/project/save')
def save_project(req:ProjectData): return {'project':projects.save(req.model_dump()).name}
@app.post('/api/project/load')
def load_project(req:ProjectLoadRequest):
    try: return projects.load(req.image_id)
    except FileNotFoundError as e: raise HTTPException(404,str(e))
    except ValueError as e: raise HTTPException(422,str(e))
@app.get('/api/health')
def health(): return {'ok':True}
