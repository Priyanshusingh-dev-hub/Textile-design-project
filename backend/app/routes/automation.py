"""Auto mode, the job dashboard and quotes: design in, package and price out, no operator."""
import hashlib
import json
import time
import numpy as np
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from fastapi.responses import FileResponse
from ..models import *
from ..core import store, joblog
from .. import auto as auto_mode
from ..core import quote as costing
from ..color_engine import engine as colors
from .common import *
from .images import upload
from .palette import reduce
from .plates import separate
from .export import _build_package

router = APIRouter()


@router.post('/api/auto')
def auto(req: AutoRequest):
    """Auto mode: design in, production package out, no operator. The engine
    picks the ink count and texture cleanup, then reduces, separates and
    exports exactly as the app's own steps do (the same handlers), and
    reports every warning with a status: `auto_ok` (safe to print) or
    `needs_review` (an operator should look first). Thresholds come from
    auto-config.json. The zip and this report are kept for the cache's 48 h:
    GET /api/auto/{job_id} and /api/auto/{job_id}/package."""
    try:
        cfg = auto_mode.load_config()
    except ValueError as e:
        raise HTTPException(500, f'Auto mode is misconfigured: {e}')
    t0 = time.perf_counter(); timings = {}

    def lap(name):
        nonlocal t0
        now = time.perf_counter(); timings[name] = round(now - t0, 2); t0 = now

    src = store.load(req.image_id)
    sug = colors.suggest_colors(src); lap('suggest')
    k = req.colors or sug['suggested']
    red = reduce(ReduceRequest(image_id=req.image_id, colors=k, smoothing=sug['smoothing'])); lap('reduce')
    palette = [c.hex for c in red['palette']]
    layers = separate(SeparationRequest(image_id=red['image_id'], palette=palette))['layers']; lap('separate')
    pkg = PackageRequest(layers=[PackageLayer(id=l['id'], name=l['name'], color=l['color']) for l in layers],
                         dpi=req.dpi, width_in=req.width_in, fabric=req.fabric, underbase=req.underbase,
                         trap_px=req.trap_px, vector=req.vector, min_dot_mm=cfg['clean_dots_mm'])
    data, made = _build_package(pkg, dot_check_mm=cfg['tiny_dot_mm']); lap('package')
    size, native, dots = made['size'], made['native'], made['dots']
    dot_share = round(dots['pixels'] / max(dots['inked'], 1) * 100, 2)
    # dots the package cleaned away are no longer a problem on the screens
    small = colors.small_inks(src, store.load(red['image_id']), palette)
    facts = {
        'accuracy': red['accuracy'], 'ceiling': max((c['accuracy'] for c in sug['curve']), default=100.0),
        'inks': len(palette), 'soft_edge': red['soft_edge'], 'soft_edge_limit': colors.SOFT_EDGE_PX,
        'dot_share': None if cfg['clean_dots_mm'] >= cfg['tiny_dot_mm'] else dot_share,
        'similar': red['similar'], 'grain': red['smoothing'],
        'source_ppi': native[0] / (size[0] / req.dpi) if size != native else None,
        'repeat': [axis for axis, on in (('left-right', red['repeat']['x']), ('top-bottom', red['repeat']['y'])) if on],
        'small': [{'hex': i['hex'], 'coverage': i['coverage']} for i in small['inks'] if not i['distinct']],
    }
    warnings, status = auto_mode.review(facts, cfg); lap('review')
    job_id = uuid4().hex
    store.auto_path(job_id, 'zip').write_bytes(data)
    report = {
        'job_id': job_id, 'status': status, 'warnings': warnings,
        'name': req.name, 'client': req.client, 'created_at': datetime.now().isoformat(timespec='seconds'),
        'stage': 'new', 'history': [],
        'accuracy': red['accuracy'], 'delta_e': red['delta_e'],
        'inks': [{'name': l['name'], 'hex': l['color'], 'coverage': l['coverage']} for l in layers],
        'suggested_inks': sug['suggested'], 'texture_cleanup': red['smoothing'], 'grain': sug['grain'],
        'print': {'width_px': size[0], 'height_px': size[1], 'dpi': req.dpi,
                  'width_in': round(size[0] / req.dpi, 2), 'height_in': round(size[1] / req.dpi, 2)},
        'tiny_dots': {'under_mm': cfg['tiny_dot_mm'], 'count': dots['dots'], 'share': dot_share,
                      'cleaned_under_mm': cfg['clean_dots_mm'] or None},
        'source_id': req.image_id, 'reduced_id': red['image_id'], 'layers': layers,
        'package_url': f'/api/auto/{job_id}/package', 'package_bytes': len(data),
        'seconds': timings,
    }
    report['underbase'] = req.underbase
    report['trial'] = req.trial
    # which design this is, whatever upload it came in: a re-run or a change
    # of the same file is the same design (the job log counts designs by it)
    report['design'] = hashlib.sha1(np.ascontiguousarray(np.asarray(src)).tobytes()).hexdigest()[:16]
    # what the package was made with, so it can be made again the same (e.g. with colourways)
    report['settings'] = {'fabric': req.fabric, 'width_in': req.width_in, 'dpi': req.dpi, 'underbase': req.underbase,
                          'trap_px': req.trap_px, 'vector': req.vector, 'min_dot_mm': cfg['clean_dots_mm']}
    if req.meters:
        report['quote'] = _quote(report['inks'], req.meters, underbase=req.underbase,
                                 proof=store.load(red['image_id']), client=req.client)
    store.auto_path(job_id, 'json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    if not req.trial:
        joblog.made(report)
    return report


def _quote(inks, meters, *, fabric_width_in=None, underbase=False, proof=None, client='', design=''):
    """The run's cost from the rate card, and the quote as an image to send."""
    try:
        card = costing.load_card()
    except ValueError as e:
        raise HTTPException(500, f'The rate card is misconfigured: {e}')
    q = costing.calculate(inks, meters, card, fabric_width_in, underbase)
    quote_no = uuid4().hex[:6].upper()
    image = costing.quote_image(q, card, proof=proof, design=design, client=client, quote_no=quote_no)
    image_id = store.save(image)
    return q | {'quote_no': quote_no, 'image_id': image_id, 'image_url': f'/api/image/{image_id}'}


@router.post('/api/quote')
def quote(req: QuoteRequest):
    """What a print run of `meters` costs: ink weighed from each screen's
    coverage, screens, cloth, printing, setup, margin and GST from the rate
    card — plus the quote as one image for WhatsApp/Telegram."""
    if req.job_id:
        job = auto_report(req.job_id)
        inks = job['inks']
        proof = store.load(job['reduced_id']) if store.exists(job['reduced_id']) else None
        underbase = job.get('underbase', False)
    elif req.inks:
        inks = [i.model_dump() for i in req.inks]
        proof = store.load(req.proof_id) if req.proof_id else None
        underbase = req.underbase
    else:
        raise HTTPException(422, 'Send the screens (inks with their coverage) or an auto job id.')
    return _quote(inks, req.meters, fabric_width_in=req.fabric_width_in, underbase=underbase,
                  proof=proof, client=req.client, design=req.design)


@router.get('/api/rate-card')
def rate_card():
    try:
        return costing.load_card()
    except ValueError as e:
        raise HTTPException(500, f'The rate card is misconfigured: {e}')


@router.get('/api/jobs')
def jobs(status: str | None = Query(None, pattern='^(auto_ok|needs_review)$'),
         stage: str | None = Query(None, pattern='^(' + '|'.join(JOB_STAGES) + ')$'),
         limit: int = Query(200, ge=1, le=1000)):
    """Every auto job still in the cache, newest first, as the dashboard
    lists them: `status` / `stage` filter (an operator looks at needs_review
    jobs that nobody has dealt with yet)."""
    out = []
    for path in store.auto_reports():
        try:
            r = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue            # being written, or a stray file
        if r.get('trial') or (status and r['status'] != status) or (stage and r.get('stage', 'new') != stage):
            continue
        out.append({k: r.get(k) for k in ('job_id', 'name', 'client', 'created_at', 'status', 'stage',
                                          'accuracy', 'print', 'reduced_id', 'package_url')}
                   | {'stage': r.get('stage') or 'new', 'name': r.get('name') or '',
                      # reports from before the dashboard carry no time: the file's own
                      'created_at': r.get('created_at') or datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
                      'inks': len(r['inks']), 'warnings': [w for w in r['warnings'] if w['blocking']],
                      'notes': [w['code'] for w in r['warnings'] if not w['blocking']],
                      'total': (r.get('quote') or {}).get('total'), 'meters': (r.get('quote') or {}).get('meters'),
                      'currency': (r.get('quote') or {}).get('currency'),
                      'last': (r.get('history') or [None])[-1]})
    out.sort(key=lambda j: j['created_at'] or '', reverse=True)
    counts = {}
    for j in out:
        counts[j['status']] = counts.get(j['status'], 0) + 1
    # what waits for a person, over every job (not just the rows sent back): the header's count
    attention = sum(1 for j in out if j['status'] == 'needs_review' and j['stage'] == 'new')
    return {'jobs': out[:limit], 'total': len(out), 'counts': counts, 'attention': attention}


@router.post('/api/jobs/{job_id}/stage')
def job_stage(job_id: str, req: JobStageRequest):
    """Record where a job stands (operator on the dashboard, or the bot:
    sent to the client, approved, rejected, changed)."""
    path = store.auto_path(job_id, 'json')
    if not path.exists():
        raise FileNotFoundError('This job is no longer available. Run it again.')
    r = json.loads(path.read_text(encoding='utf-8'))
    r['stage'] = req.stage
    r.setdefault('history', []).append({'stage': req.stage, 'by': req.by, 'note': req.note,
                                        'at': datetime.now().isoformat(timespec='seconds')})
    tmp = path.with_name(path.name + '.part')
    tmp.write_text(json.dumps(r, indent=1), encoding='utf-8')
    tmp.replace(path)
    if not r.get('trial'):
        joblog.record(event='stage', job_id=job_id, name=r.get('name', ''), client=r.get('client', ''),
                      status=r['status'], stage=req.stage, by=req.by, note=req.note)
    return {'job_id': job_id, 'stage': r['stage'], 'history': r['history']}


@router.get('/api/stats')
def job_stats(days: int = Query(30, ge=1, le=366)):
    """The last `days` days from the job log (kept for good, unlike the 48 h
    cache): designs, how many needed nobody, where they ended, what was
    quoted, and the time saved at the mill's own estimates (Settings)."""
    try:
        card = costing.load_card()
    except ValueError as e:
        raise HTTPException(500, f'The rate card is misconfigured: {e}')
    return joblog.stats(days, card)


@router.get('/api/auto/{job_id}')
def auto_report(job_id: str):
    path = store.auto_path(job_id, 'json')
    if not path.exists():
        raise FileNotFoundError('This job is no longer available. Run it again.')
    return json.loads(path.read_text(encoding='utf-8'))


@router.get('/api/auto/{job_id}/package')
def auto_package(job_id: str):
    path = store.auto_path(job_id, 'zip')
    if not path.exists():
        raise FileNotFoundError('This job is no longer available. Run it again.')
    return FileResponse(path, media_type='application/zip', filename=f'loomlab-{job_id[:8]}.zip')


@router.post('/api/auto/upload')
async def auto_upload(file: UploadFile = File(...), width_in: float | None = Form(None), dpi: int = Form(300),
                      colors_: int | None = Form(None, alias='colors'), fabric: str = Form('#FFFFFF'),
                      meters: float | None = Form(None), client: str = Form(''), trial: bool = Form(False)):
    """Auto mode in one request: upload a design file and run it (for the
    Telegram bot and scripts). A pre-separated PSD is refused: its screens are
    already made and go straight to export."""
    up = await upload(file)
    if up.get('layers'):
        raise HTTPException(422, 'This PSD is already separated into screens; export it directly.')
    try:
        req = AutoRequest(image_id=up['image_id'], width_in=width_in, dpi=dpi, colors=colors_, fabric=fabric,
                          meters=meters, client=client, name=(file.filename or '')[:120], trial=trial)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    return await run_in_threadpool(auto, req)
