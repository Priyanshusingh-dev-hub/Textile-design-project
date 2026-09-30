"""The design library: every approved job, kept for good.

The working cache forgets a job after 48 hours, but a mill's best business is
the repeat order — "the same design, 500 m more" — and for that the screens
already exist. So when a job is approved its report, a proof and its
production zip (the films, if a screen has to be burnt again) are copied to
`library/<job id>/` in the data folder, which the cache cleanup never touches.
A repeat order is then priced from the stored ink coverage with no new screens,
and each one taken is recorded on the design.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import store

_ID = re.compile(r'^[0-9a-f]{32}$')
PROOF_SIDE = 1200


def root() -> Path:
    return store.ROOT / 'library'


def folder(entry_id: str) -> Path:
    if not _ID.match(entry_id or ''):
        raise FileNotFoundError('No such design in the library.')
    return root() / entry_id


def valid(r) -> bool:
    """A library report LoomLab can list and price: its inks and print size are
    all there. A damaged one (a hand-edited or restored file) is skipped."""
    try:
        return (isinstance(r, dict) and bool(_ID.match(r.get('job_id') or '')) and isinstance(r.get('inks'), list)
                and all(isinstance(i, dict) and isinstance(i.get('name'), str) and isinstance(i.get('hex'), str)
                        and isinstance(i.get('coverage'), (int, float)) for i in r['inks'])
                and all(isinstance(r['print'].get(k), (int, float)) for k in ('width_in', 'height_in')))
    except (AttributeError, KeyError, TypeError):
        return False


def _proof(report: dict):
    """A <= PROOF_SIDE proof on white, from the screen-size copy when the app
    already made one (a 30-inch design is 61 MP: no need to decode it all)."""
    rid = report.get('reduced_id') or ''
    try:
        small = store.screen_path(rid, 2400)
        image = Image.open(small) if small.exists() else store.load(rid)
        image.load()
    except (FileNotFoundError, OSError, ValueError):
        return None
    image = image.convert('RGBA')
    image.thumbnail((PROOF_SIDE, PROOF_SIDE), Image.LANCZOS)
    ground = Image.new('RGBA', image.size, (255, 255, 255, 255))   # transparent = cloth, not black
    return Image.alpha_composite(ground, image).convert('RGB')


def keep(report: dict) -> Path:
    """Copy an approved job into the library (again on a second approval: the
    latest wins, keeping the repeat orders already taken). Built beside the
    entry and swapped in; if the old entry cannot be moved (a film open in
    another program on Windows) the error is raised and the old entry stays."""
    out = folder(report['job_id'])
    work = out.with_name(out.name + '.part')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        entry = dict(report) | {'kept_at': datetime.now().isoformat(timespec='seconds')}
        if out.exists():
            try:
                entry['repeat_orders'] = get(report['job_id']).get('repeat_orders', [])
            except FileNotFoundError:
                pass
        proof = _proof(report)
        if proof is not None:
            proof.save(work / 'proof.png', optimize=False, compress_level=6)
            entry['has_proof'] = True
        zip_path = store.auto_path(report['job_id'], 'zip')
        if zip_path.exists():
            shutil.copyfile(zip_path, work / 'package.zip')
            entry['has_package'] = True
        (work / 'report.json').write_text(json.dumps(entry, indent=1), encoding='utf-8')
        old = out.with_name(out.name + '.old')
        shutil.rmtree(old, ignore_errors=True)
        if out.exists():
            out.rename(old)
        try:
            work.rename(out)
        except OSError:
            if old.exists():
                old.rename(out)                  # the entry as it was, not none at all
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def get(entry_id: str) -> dict:
    path = folder(entry_id) / 'report.json'
    if not path.exists():
        raise FileNotFoundError('No such design in the library.')
    try:
        r = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        r = None
    if not valid(r):
        raise FileNotFoundError('This library design is damaged. Approve the job again, or restore a backup.')
    return r


def add_repeat(entry_id: str, order: dict) -> tuple[dict, bool]:
    """Record a repeat order taken for a library design, once per `token`
    (a retried confirmation is not a second order). Returns the order kept
    and whether it is new."""
    path = folder(entry_id) / 'report.json'
    r = get(entry_id)
    orders = r.setdefault('repeat_orders', [])
    for o in orders:
        if order.get('token') and o.get('token') == order['token']:
            return o, False
    kept = order | {'at': datetime.now().isoformat(timespec='seconds')}
    orders.append(kept)
    tmp = path.with_name('report.json.part')
    tmp.write_text(json.dumps(r, indent=1), encoding='utf-8')
    tmp.replace(path)
    return kept, True


def entries(query: str = '', limit: int = 100) -> tuple[list[dict], int]:
    """Kept designs, newest first, matching `query` in the design or client
    name; and how many match in all. A damaged entry is left out, not an error."""
    q = query.strip().lower()
    out = []
    if root().exists():
        for p in root().glob('*/report.json'):
            if not _ID.match(p.parent.name):
                continue
            try:
                r = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if not valid(r) or r['job_id'] != p.parent.name:
                continue
            if q and q not in f"{r.get('name', '')} {r.get('client', '')}".lower():
                continue
            # a hand-edited or restored file may carry anything here: only whole orders count
            repeats = [o for o in r.get('repeat_orders') or [] if isinstance(o, dict)
                       and isinstance(o.get('at'), str) and isinstance(o.get('meters'), (int, float))] \
                if isinstance(r.get('repeat_orders'), list) else []
            out.append({'id': r['job_id'], 'name': r.get('name') or '', 'client': r.get('client') or '',
                        'kept_at': r.get('kept_at', ''), 'inks': [{'name': i['name'], 'hex': i['hex'],
                                                                    'coverage': i['coverage']} for i in r['inks']],
                        'print': r['print'], 'underbase': bool(r.get('underbase')),
                        'fabric': (r.get('settings') or {}).get('fabric', '#FFFFFF'),
                        'last_meters': (r.get('quote') or {}).get('meters'),
                        'repeats': len(repeats),
                        'last_repeat': {'meters': repeats[-1]['meters'], 'at': repeats[-1]['at']} if repeats else None,
                        'has_proof': bool(r.get('has_proof')), 'has_package': bool(r.get('has_package'))})
    out.sort(key=lambda e: e['kept_at'], reverse=True)
    return out[:limit], len(out)
