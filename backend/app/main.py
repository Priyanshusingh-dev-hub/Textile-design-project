import asyncio
import math
import os
import re
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from .models import *
from .core import store
from .core import regmarks
from .region_engine import engine as region
from .core.archive import build_zip, _safe_name
from .core.psd_import import is_psd, open_psd_any
from .core.psd_export import multichannel_psd
from .color_engine import engine as colors
from .separation_engine import engine as separation
from .repeat_engine import engine as repeat
from .project_engine import engine as projects
from .halftone_engine import engine as halftone
from .design_ai import analyzer as design_analyzer, instructions as design_instructions
from .vector_engine import engine as vector
from zipfile import ZipFile, ZIP_DEFLATED

CLEANUP_INTERVAL_SECONDS = float(os.environ.get('CLEANUP_INTERVAL_SECONDS', 3600))
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_PROJECT_BYTES = 1024 * 1024 * 1024

async def _cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try: store.cleanup_expired()
        except Exception: pass

@asynccontextmanager
async def lifespan(_app):
    store.cleanup_expired()  # run once immediately so stale files don't linger between restarts
    task=asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()

app=FastAPI(title='LoomLab API', version='0.1.0', lifespan=lifespan)
_origins=[o.strip() for o in os.environ.get('ALLOWED_ORIGINS','http://localhost:5173').split(',') if o.strip()]
app.add_middleware(CORSMiddleware,allow_origins=_origins,allow_methods=['*'],allow_headers=['*'])

@app.exception_handler(FileNotFoundError)
async def _missing_image(_request, exc):
    # Working images expire (store.cleanup_expired); say so instead of a bare 500.
    return JSONResponse(status_code=404, content={'detail': str(exc) or store.MISSING})

def image_response(image, name='design.png', fmt='PNG', dpi=300, download=False):
    b=BytesIO(); image.save(b,format=fmt, dpi=(dpi,dpi)); b.seek(0)
    headers={'Content-Disposition':f'attachment; filename="{name}"'} if download else {}
    return StreamingResponse(b,media_type=f'image/{fmt.lower()}',headers=headers)
def psd_response(image, name='loomlab.psd'):
    """Write a baseline RGB PSD that Photoshop, Affinity and Photopea can open."""
    rgb=colors.to_rgb(image); w,h=rgb.size; raw=np.asarray(rgb)
    payload=b'8BPS'+(1).to_bytes(2,'big')+(b'\0'*6)+(3).to_bytes(2,'big')+h.to_bytes(4,'big')+w.to_bytes(4,'big')+(8).to_bytes(2,'big')+(3).to_bytes(2,'big')+(0).to_bytes(4,'big')+(0).to_bytes(4,'big')+(0).to_bytes(4,'big')+(0).to_bytes(2,'big')
    payload+=raw[:,:,0].tobytes()+raw[:,:,1].tobytes()+raw[:,:,2].tobytes()
    return StreamingResponse(BytesIO(payload),media_type='image/vnd.adobe.photoshop',headers={'Content-Disposition':f'attachment; filename="{name}"'})
def image_meta(image_id, image):
    w,h=image.size; return {'image_id':image_id,'width':w,'height':h,'aspect_ratio':round(w/h,3),'url':f'/api/image/{image_id}'}
def layer_meta(layer_id, name, color, coverage, layer):
    """Store a layer's print-ready mask and colour plate next to it and
    describe all three the way the Layers / Plates panels expect."""
    mask_id=store.save(separation.to_print_ready(layer)); plate_id=store.save(separation.plate(layer,color))
    return {'id':layer_id,'name':name,'color':color,'coverage':coverage,'url':f'/api/image/{layer_id}','mask_url':f'/api/image/{mask_id}','plate_url':f'/api/image/{plate_id}'}
def _normalize_upload(img):
    """Bring any decoded upload into a form the engines read correctly:
    - honour the EXIF orientation flag, so a phone photo or scan of a fabric
      isn't analysed and separated sideways;
    - scale 16-bit / 32-bit greyscale (common from flatbed scanners) down to
      8-bit -- Pillow's own conversion clips it, turning almost the whole
      design white."""
    img=ImageOps.exif_transpose(img)
    if img.mode in ('I;16','I;16L','I;16B','I;16N','I','F'):
      a=np.asarray(img,dtype=np.float64); peak=float(a.max()) if a.size else 0.0
      if img.mode.startswith('I;16') or peak>255: top=65535.0
      elif img.mode=='F' and peak<=1.0: top=1.0
      else: top=255.0
      img=Image.fromarray((np.clip(a,0,top)/top*255).round().astype(np.uint8))
    return img
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
    if len(raw)>MAX_UPLOAD_BYTES: raise HTTPException(413,'Image is larger than the 80 MB import limit.')
    if is_psd(raw):
      try: kind,data=open_psd_any(raw)
      except ValueError as e: raise HTTPException(422,str(e))
      if kind=='channels':
        built=_channels_to_layers(data)
        if not built: raise HTTPException(422,'This multichannel PSD has no channels to import.')
        layers=[]
        for name,hx,layer,display,coverage in built:
          lid=store.save(layer); did=store.save(display); pid=store.save(separation.plate(layer,hx))
          layers.append({'id':lid,'name':name,'color':hx,'coverage':coverage,'url':f'/api/image/{lid}','mask_url':f'/api/image/{did}','plate_url':f'/api/image/{pid}'})
        preview=separation.composite_masks([(layer,hx,100) for _,hx,layer,_,_ in built],built[0][2].size)
        image_id=store.save(preview)
        return image_meta(image_id,preview)|{'file_name':file.filename,'file_size':len(raw),'layers':layers}
      img=data
    else:
      # Decide by content, not the browser's MIME guess: TIFFs and some WEBPs
      # routinely arrive as application/octet-stream or with no type at all.
      try: img=Image.open(BytesIO(raw)); img.load()
      except Image.DecompressionBombError: raise HTTPException(413,'This image has too many pixels to process safely.')
      except (UnidentifiedImageError, OSError, ValueError, SyntaxError): raise HTTPException(415,'Please choose a PNG, JPG, WEBP, TIFF, or PSD image.')
      img=_normalize_upload(img)
    image_id=store.save(img)
    return image_meta(image_id,img)|{'file_name':file.filename,'file_size':len(raw)}
@app.post('/api/image/sample')
def sample():
    """A small floral pattern for immediately exploring the workflow."""
    size=720; image=Image.new('RGBA',(size,size),'#F4E8CC'); d=ImageDraw.Draw(image)
    for y in range(-40,size+80,120):
      for x in range(-40,size+80,120):
        # leaves sit in the gaps between flowers (under a flower they'd be hidden)
        d.ellipse((x+60-40,y+60-11,x+60+40,y+60+11),fill='#477052')
        d.ellipse((x+60-11,y+60-30,x+60+11,y+60+30),fill='#477052')
        for angle in range(0,360,45):
          dx=math.cos(math.radians(angle))*31; dy=math.sin(math.radians(angle))*31
          d.ellipse((x+dx-23,y+dy-15,x+dx+23,y+dy+15),fill='#C95368')
        d.ellipse((x-12,y-12,x+12,y+12),fill='#D9A43E')
    image_id=store.save(image); return image_meta(image_id,image)|{'file_name':'loomlab-sample-floral.png','file_size':0}
@app.get('/api/image/{image_id}')
def get_image(image_id:str):
    # Stored images never change after they are written (every edit gets a new
    # id), so serve the file as-is and let the browser cache it for good
    # instead of decoding and re-encoding the PNG on every view.
    return FileResponse(store.existing_path(image_id),media_type='image/png',headers={'Cache-Control':'private, max-age=31536000, immutable'})
@app.post('/api/colors/analyze')
def analyze(req:AnalyzeRequest):
    image=store.load(req.image_id); pal=colors.analyze(image,req.colors)
    de,acc=colors.reconstruction_accuracy(image,[c.hex for c in pal])
    return {'palette':pal,'accuracy':acc,'delta_e':de}
@app.post('/api/colors/reduce')
def reduce(req:ReduceRequest):
    src=store.load(req.image_id)
    pal=colors.analyze(src,req.colors); hexes=[c.hex for c in pal]
    if req.region:
      image,_,_=region.region_flatten(src,hexes,req.edge_strength,req.min_region)
    else:
      image=colors.reduce(src,req.colors)
    image_id=store.save(image)
    de,acc=colors.reconstruction_accuracy(src,hexes)
    return image_meta(image_id,image)|{'palette':pal,'accuracy':acc,'delta_e':de}
@app.post('/api/colors/map')
def map_(req:MapRequest):
    image,changed=colors.map_colors(store.load(req.image_id),req.mappings,req.threshold); image_id=store.save(image)
    return image_meta(image_id,image)|{'changed_pixels':changed,'changed_percent':round(changed/(image.width*image.height)*100,2)}
@app.post('/api/colors/merge')
def merge(req:MergeRequest):
    image=colors.merge(store.load(req.image_id),req.sources,req.target,req.threshold); image_id=store.save(image); return image_meta(image_id,image)
@app.post('/api/separation/create')
def separate(req:SeparationRequest):
    image=store.load(req.image_id); layers=[]
    if req.mode=='gradient':
      built=separation.soft_create(image,req.palette)
    elif req.mode=='region':
      flat,_,_=region.region_flatten(image,req.palette,req.edge_strength,req.min_region)
      built=separation.create(flat,req.palette,cleanup=0)
    else:
      built=separation.create(image,req.palette,req.cleanup)
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
      image=separation.composite_masks([(first if i==0 else store.load(item.id),item.color,item.opacity) for i,item in enumerate(req.layers) if item.opacity>0],first.size)
    image_id=store.save(image); return image_meta(image_id,image)
_SPREAD_MAGENTA=(255,0,200); _SPREAD_CYAN=(0,215,255)
def _spread_colour(ink_hex):
    """Highlight for an ink's trap spread: magenta, or cyan when the ink
    itself is too close to magenta for the highlight to stand out."""
    lab=colors.rgb_lab(np.array([colors.hex_rgb(ink_hex),np.array(_SPREAD_MAGENTA,dtype=np.uint8)]))
    return _SPREAD_CYAN if float(colors.delta_e2000(lab[0],lab[1]))<35 else _SPREAD_MAGENTA
def _highlight(mask, rgb):
    out=np.zeros((*mask.shape,4),dtype=np.uint8); out[mask]=(*rgb,255)
    return Image.fromarray(out)
@app.post('/api/separation/trap-preview')
def trap_preview(req:TrapPreviewRequest):
    """What trapping will actually export, for the Plates view: per ink the
    trapped colour plate and film, plus a transparent overlay marking only
    the spread it gained; and for the whole design the as-printed
    composite plus an overlay of every pixel where two or more inks now
    overlap."""
    originals=[store.load(item.id) for item in req.layers]
    if len({m.size for m in originals})>1: raise HTTPException(422,'Trapping needs every ink layer to be the same size.')
    inks=[item.color or '#000000' for item in req.layers]
    trapped=separation.trap(originals,inks,req.trap)
    w,h=originals[0].size; total=w*h
    inked=np.zeros((h,w),dtype=np.uint8); out=[]
    for item,ink,orig,tr in zip(req.layers,inks,originals,trapped):
      before=np.asarray(orig)[:,:,3]>=128; after=np.asarray(tr)[:,:,3]>=128
      spread=after&~before; inked+=after
      plate_id=store.save(separation.plate(tr,ink)); film_id=store.save(separation.to_print_ready(tr))
      spread_id=store.save(_highlight(spread,_spread_colour(ink)))
      out.append({'id':item.id,'plate_url':f'/api/image/{plate_id}','film_url':f'/api/image/{film_id}','spread_url':f'/api/image/{spread_id}',
                  'spread_percent':round(float(spread.sum())/total*100,2)})
    # as printed: lightest ink first so each darker ink lands on top of the spread under it
    order=sorted(range(len(inks)),key=lambda i:-float(colors.rgb_lab(colors.hex_rgb(inks[i]))[0]))
    composite=separation.composite_masks([(trapped[i],inks[i],100) for i in order],(w,h))
    overlap=inked>=2
    composite_id=store.save(composite); overlap_id=store.save(_highlight(overlap,_SPREAD_MAGENTA))
    return {'trap':req.trap,'layers':out,'composite_url':f'/api/image/{composite_id}','overlap_url':f'/api/image/{overlap_id}',
            'overlap_percent':round(float(overlap.sum())/total*100,2)}
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
    # JPEG has no alpha: flatten onto white (unprinted fabric), not black
    if req.format=='jpg': image=colors.to_rgb(image)
    return image_response(image,f'loomlab-export.{req.format}',fmts[req.format],req.dpi,True)
def _load_inks(items, trap_px):
    """[(item, ink mask)] for an export, with trapping applied across the
    whole set when trap_px > 0 (trapping needs every ink to know which
    neighbours are darker, so it can't be done one layer at a time)."""
    masks=[store.load(item.id) for item in items]
    if trap_px>0:
      if len({m.size for m in masks})>1: raise HTTPException(422,'Trapping needs every ink layer to be the same size.')
      masks=separation.trap(masks,[item.color or '#000000' for item in items],trap_px)
    return list(zip(items,masks))
@app.post('/api/export/zip')
def export_zip(req:ZipExportRequest):
    loaded=_load_inks(req.layers,req.trap)
    if req.content=='film':
      entries=[(it.name, separation.to_print_ready(img)) for it,img in loaded]
      if req.reg_marks:
        entries=[(name, regmarks.add_registration_marks(scr, req.dpi)) for name,scr in entries]
    elif req.content=='plate':
      entries=[(it.name, separation.plate(img, it.color or '#000000')) for it,img in loaded]
    else:
      entries=[(it.name, img) for it,img in loaded]
      if req.composite_image_id: entries.append(('composite', store.load(req.composite_image_id)))
    if not entries: raise HTTPException(400,'Nothing to export — no layers or composite were provided.')
    data=build_zip(entries,fmt=req.format,dpi=req.dpi)
    filename={'film':'loomlab-screens','plate':'loomlab-plates','mask':'loomlab-layers'}[req.content]+'.zip'
    return StreamingResponse(BytesIO(data),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
@app.post('/api/export/svg')
def export_svg(req:SvgExportRequest):
    if not req.layers: raise HTTPException(400,'No layers provided.')
    size=None; layer_masks=[]
    for item,img in _load_inks(req.layers,req.trap):
      size=img.size
      alpha=np.asarray(img.convert('RGBA'))[:,:,3]
      binary=(alpha>127).astype(np.uint8)*255
      layer_masks.append((item.name,item.color or '#000000',binary))
    if req.per_layer:
      buf=BytesIO(); used=set()
      with ZipFile(buf,'w',ZIP_DEFLATED) as zf:
        for name,color,mask in layer_masks:
          d=vector.mask_to_path_d(mask,req.blur,req.simplify,req.corner_angle,req.min_area)
          path_tag=f'<path d="{d}" fill="{color}" fill-rule="evenodd"/>' if d else ''
          svg=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size[0]} {size[1]}" '
               f'width="{size[0]}" height="{size[1]}">{path_tag}</svg>')
          base=_safe_name(name); filename,i=f'{base}.svg',1
          while filename in used: i+=1; filename=f'{base}-{i}.svg'
          used.add(filename)
          zf.writestr(filename,svg)
      return StreamingResponse(BytesIO(buf.getvalue()),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="loomlab-vectors.zip"'})
    if req.trap>0:
      # trapped inks overlap: paint in print order, lightest first, so each
      # darker ink covers the spread of the lighter one under it
      layer_masks.sort(key=lambda t:-float(colors.rgb_lab(colors.hex_rgb(t[1]))[0]))
    svg=vector.build_svg([(color,mask) for _,color,mask in layer_masks],size,req.blur,req.simplify,req.corner_angle,req.min_area)
    return StreamingResponse(BytesIO(svg.encode()),media_type='image/svg+xml',headers={'Content-Disposition':'attachment; filename="loomlab-design.svg"'})
@app.post('/api/export/psd-multichannel')
def export_psd_multichannel(req:PsdExportRequest):
    """One Multichannel PSD, one named spot channel per ink -- the format
    mills exchange separations in (and the one LoomLab imports)."""
    channels=[]
    for item,mask in _load_inks(req.layers,req.trap):
      screen=separation.to_print_ready(mask)
      if req.reg_marks: screen=regmarks.add_registration_marks(screen,req.dpi)
      channels.append((item.name,item.color or '#000000',screen))
    try: data=multichannel_psd(channels,req.dpi)
    except ValueError as e: raise HTTPException(422,str(e))
    return StreamingResponse(BytesIO(data),media_type='image/vnd.adobe.photoshop',headers={'Content-Disposition':'attachment; filename="loomlab-separation.psd"'})
@app.post('/api/design/dna')
def design_dna(req:DnaRequest):
    return design_analyzer.build_dna(store.load(req.image_id), req.description)
@app.post('/api/design/instructions')
def design_instr(req:InstructionRequest):
    dna=design_analyzer.build_dna(store.load(req.image_id), req.description)
    out=design_instructions.generate(dna, req.intent, req.fidelity, req.user_request, req.description, req.target_colors)
    return {'dna':dna}|out
@app.post('/api/project/export')
def export_project(req:ProjectExportRequest):
    """Bundle the workspace into a self-contained .textileproj download."""
    original=store.load(req.original_id) if req.original_id else None
    current=store.load(req.image_id) if req.image_id else None
    layer_images=[store.load(l.id) for l in req.layers]
    meta={'name':req.name,'palette':[c.model_dump() for c in req.palette],'settings':req.settings,
          'layers':[l.model_dump(exclude={'id'}) for l in req.layers]}
    data=projects.pack(meta,original,current,layer_images)
    filename=(re.sub(r'[^A-Za-z0-9_.-]+','-',req.name).strip('-.') or 'loomlab-project')+'.textileproj'
    return StreamingResponse(BytesIO(data),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
def _number(value, default, lo, hi):
    return min(hi,max(lo,float(value))) if isinstance(value,(int,float)) and math.isfinite(value) else default
def _valid_palette(items):
    out=[]
    for item in items if isinstance(items,list) else []:
      try: out.append(Color.model_validate(item).model_dump())
      except Exception: continue
    return out
@app.post('/api/project/import')
async def import_project(file:UploadFile=File(...)):
    raw=await file.read()
    if len(raw)>MAX_PROJECT_BYTES: raise HTTPException(413,'Project file is larger than the 1 GB limit.')
    try: meta,original,current,layer_images=projects.unpack(raw)
    except ValueError as e: raise HTTPException(422,str(e))
    if current is None and original is None: raise HTTPException(422,'This project has no image in it.')
    if current is None: current=original
    settings=meta.get('settings')
    out={'name':str(meta.get('name') or 'loomlab-project'),'palette':_valid_palette(meta.get('palette')),'settings':settings if isinstance(settings,dict) else {}}
    if original is not None:
      original_id=store.save(original); out['original']=image_meta(original_id,original)|{'file_name':out['name']}
    image_id=store.save(current); out['image']=image_meta(image_id,current)|{'file_name':out['name']}
    out.setdefault('original',out['image'])
    layers=[]
    for i,(info,img) in enumerate(layer_images):
      color=str(info.get('color') or '#000000')
      if not re.fullmatch(r'#[0-9A-Fa-f]{6}',color): color='#000000'
      lid=store.save(img)
      layers.append(layer_meta(lid,str(info.get('name') or f'Ink {i+1}'),color,_number(info.get('coverage'),0,0,100),img)|
                    {'visible':info.get('visible',True) is not False,'opacity':_number(info.get('opacity'),100,0,100)})
    out['layers']=layers
    return out
@app.get('/api/health')
def health(): return {'ok':True}

def ui_dir() -> Path | None:
    """Where a built frontend (index.html + assets) lives, if anywhere:
    LOOMLAB_UI_DIR, else the bundle of a packaged app, else frontend/dist
    after `npm run build`. None in plain development, where Vite serves the
    UI and proxies /api here."""
    candidates=[os.environ.get('LOOMLAB_UI_DIR')]
    if getattr(sys,'frozen',False): candidates.append(str(Path(getattr(sys,'_MEIPASS','.'))/'ui'))
    candidates.append(str(Path(__file__).resolve().parents[2]/'frontend'/'dist'))
    for c in candidates:
      if c and (Path(c)/'index.html').is_file(): return Path(c)
    return None
def mount_ui(target, directory):
    """Serve the built UI from this same server, so LoomLab runs as one
    program on one port. Mounted last: every /api route keeps priority."""
    target.mount('/',StaticFiles(directory=str(directory),html=True),name='ui')
if (_ui:=ui_dir()) is not None: mount_ui(app,_ui)
