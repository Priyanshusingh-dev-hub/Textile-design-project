"""The design library: every approved job, kept for good.

The working cache forgets a job after 48 hours, but a mill's best business is
the repeat order — "the same design, 500 m more" — and for that the screens
already exist. So when a job is approved its report, a proof and its
production zip (the films, if a screen has to be burnt again) are copied to
`library/<job id>/` in the data folder, which the cache cleanup never touches.
A repeat order is then priced from the stored ink coverage with no new screens.
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


def keep(report: dict) -> Path:
    """Copy an approved job into the library (again on a second approval: the
    latest wins). Best kept even if the cache already lost the proof or zip."""
    out = folder(report['job_id'])
    work = out.with_name(out.name + '.part')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    entry = dict(report) | {'kept_at': datetime.now().isoformat(timespec='seconds')}
    try:
        proof = store.load(report.get('reduced_id', '')).convert('RGB')
    except FileNotFoundError:
        proof = None
    if proof is not None:
        proof.thumbnail((PROOF_SIDE, PROOF_SIDE), Image.LANCZOS)
        proof.save(work / 'proof.png', optimize=False, compress_level=6)
        entry['has_proof'] = True
    zip_path = store.auto_path(report['job_id'], 'zip')
    if zip_path.exists():
        shutil.copyfile(zip_path, work / 'package.zip')
        entry['has_package'] = True
    (work / 'report.json').write_text(json.dumps(entry, indent=1), encoding='utf-8')
    shutil.rmtree(out, ignore_errors=True)
    work.rename(out)
    return out


def get(entry_id: str) -> dict:
    path = folder(entry_id) / 'report.json'
    if not path.exists():
        raise FileNotFoundError('No such design in the library.')
    return json.loads(path.read_text(encoding='utf-8'))


def entries(query: str = '', limit: int = 100) -> tuple[list[dict], int]:
    """Kept designs, newest first, matching `query` in the design or client
    name; and how many match in all."""
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
            if q and q not in f"{r.get('name', '')} {r.get('client', '')}".lower():
                continue
            out.append({'id': r['job_id'], 'name': r.get('name') or '', 'client': r.get('client') or '',
                        'kept_at': r.get('kept_at', ''), 'inks': [{'name': i['name'], 'hex': i['hex'],
                                                                    'coverage': i['coverage']} for i in r['inks']],
                        'print': r['print'], 'underbase': bool(r.get('underbase')),
                        'fabric': (r.get('settings') or {}).get('fabric', '#FFFFFF'),
                        'last_meters': (r.get('quote') or {}).get('meters'),
                        'has_proof': bool(r.get('has_proof')), 'has_package': bool(r.get('has_package'))})
    out.sort(key=lambda e: e['kept_at'], reverse=True)
    return out[:limit], len(out)
