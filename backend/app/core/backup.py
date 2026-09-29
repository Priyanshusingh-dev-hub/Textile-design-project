"""Backup and restore: everything the mill has built up, in one zip.

The design library (approved jobs and their films), the job log, the shelf
inks, the rate card and auto mode's limits live on one PC. A dead disk or a
new PC should cost nothing: Settings -> Backup downloads them as one zip,
and Restore puts them back on another LoomLab. The working cache (48 h of
images) is not in it: it rebuilds itself.

Restore trusts nothing in the zip: only the known files are read, each is
checked like the app's own saves (rate card and limits validated, inks
cleaned, library entries named by a job id), sizes are capped, and nothing is
written until every part has been checked.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import inks as ink_library
from . import joblog, library, store
from . import quote as costing
from .. import auto as auto_mode

FORMAT = 1
_LIB_FILE = re.compile(r'^library/([0-9a-f]{32})/(report\.json|proof\.png|package\.zip)$')
MAX_FILE = 4 * 1024 ** 3              # one library zip of films; make() and restore() share it
MAX_TOTAL = 64 * 1024 ** 3


def make(dest: Path) -> dict:
    """Write the backup zip to `dest`; returns what is in it. A file bigger
    than restore takes is left out and named in the manifest, so every backup
    this makes can be restored."""
    counts = {'library': 0, 'job_log_rows': 0, 'inks': 0}
    skipped = []
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for name, path in (('settings/rate-card.json', costing.CARD_PATH),
                           ('settings/auto-config.json', auto_mode.CONFIG_PATH)):
            if path.exists():
                z.write(path, name)
        if ink_library.LIBRARY.exists():
            z.write(ink_library.LIBRARY, 'inks.json')
            counts['inks'] = len(ink_library.load())
        log = joblog.log_path()
        if log.exists():
            z.write(log, 'job-log.csv')
            counts['job_log_rows'] = len(joblog.read())
        if library.root().exists():
            for entry in sorted(library.root().iterdir()):
                if not re.fullmatch(r'[0-9a-f]{32}', entry.name) or not (entry / 'report.json').exists():
                    continue
                for f in ('report.json', 'proof.png', 'package.zip'):
                    if (entry / f).exists() and (entry / f).stat().st_size > MAX_FILE:
                        skipped.append(f'library/{entry.name}/{f}')
                    elif (entry / f).exists():
                        # pictures and zips are already compressed: store them
                        z.write(entry / f, f'library/{entry.name}/{f}',
                                compress_type=zipfile.ZIP_DEFLATED if f.endswith('.json') else zipfile.ZIP_STORED)
                counts['library'] += 1
        manifest = {'loomlab_backup': FORMAT, 'made_at': datetime.now().isoformat(timespec='seconds'), **counts,
                    'skipped_too_big': skipped}
        z.writestr('manifest.json', json.dumps(manifest, indent=1))
    return manifest


def restore(src) -> dict:
    """Put a backup back. `src` is a path or a binary file object. Raises
    ValueError (with a reason a person can act on) before writing anything
    if the zip is not a LoomLab backup or any part of it is broken."""
    try:
        z = zipfile.ZipFile(src)
    except zipfile.BadZipFile:
        raise ValueError('This is not a zip file. Choose the loomlab-backup-….zip that Backup downloaded.')
    with z:
        names = {i.filename: i for i in z.infolist() if not i.is_dir()}
        try:
            manifest = json.loads(z.read('manifest.json'))
        except (KeyError, ValueError):
            raise ValueError('This zip is not a LoomLab backup (it has no manifest.json).')
        if manifest.get('loomlab_backup') != FORMAT:
            raise ValueError('This backup was made by a different LoomLab version and cannot be read here.')
        if sum(i.file_size for i in names.values()) > MAX_TOTAL or any(i.file_size > MAX_FILE for i in names.values()):
            raise ValueError('This backup is larger than LoomLab restores.')

        # -- check every part first -------------------------------------------------
        card = config = shelf = None
        if 'settings/rate-card.json' in names:
            card = _json(z, 'settings/rate-card.json')
            costing.check_card(card, 'rate card in the backup')
        if 'settings/auto-config.json' in names:
            config = _json(z, 'settings/auto-config.json')
            auto_mode.check_config(config, 'auto mode settings in the backup')
        if 'inks.json' in names:
            data = _json(z, 'inks.json')
            if not isinstance(data, dict) or not isinstance(data.get('inks'), list):
                raise ValueError('The ink list in the backup is damaged.')
            shelf = [{'name': str(i['name'])[:60], 'hex': str(i['hex'])} for i in data['inks']
                     if isinstance(i, dict) and re.fullmatch(r'#?[0-9A-Fa-f]{6}', str(i.get('hex', '')))
                     and str(i.get('name', '')).strip()]
        log_rows = []
        if 'job-log.csv' in names:
            text = z.read('job-log.csv').decode('utf-8-sig', errors='replace')
            log_rows = list(csv.DictReader(io.StringIO(text)))
        entries = {}
        for name in names:
            m = _LIB_FILE.match(name)
            if m:
                entries.setdefault(m.group(1), []).append(m.group(2))
        for entry_id, files in entries.items():
            if 'report.json' not in files:
                raise ValueError(f'Library entry {entry_id[:8]} in the backup has no report.')
            rep = _json(z, f'library/{entry_id}/report.json')
            if not library.valid(rep) or rep.get('job_id') != entry_id:
                raise ValueError(f'Library entry {entry_id[:8]} in the backup is damaged.')

        # -- then write -------------------------------------------------------------------
        if card is not None:
            costing.save_card(card)
        if config is not None:
            auto_mode.save_config(config)
        if shelf is not None:
            ink_library.save(shelf)
        added_rows = _merge_log(log_rows)
        root = library.root()
        root.mkdir(parents=True, exist_ok=True)
        for entry_id, files in entries.items():
            work = root / f'{entry_id}.part'
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir()
            for f in files:
                with z.open(f'library/{entry_id}/{f}') as fin, open(work / f, 'wb') as fout:
                    shutil.copyfileobj(fin, fout, 1 << 20)
            shutil.rmtree(root / entry_id, ignore_errors=True)
            work.rename(root / entry_id)
    return {'library': len(entries), 'job_log_rows_added': added_rows, 'inks': len(shelf or []),
            'rate_card': card is not None, 'auto_limits': config is not None,
            'made_at': manifest.get('made_at', '')}


def _json(z, name):
    try:
        return json.loads(z.read(name).decode('utf-8-sig'))
    except ValueError:
        raise ValueError(f'{name} in the backup is damaged.')


def _merge_log(rows) -> int:
    """Add the backup's log lines this PC doesn't have yet (same time, event,
    job and stage = the same line)."""
    if not rows:
        return 0
    key = lambda r: (r.get('time', ''), r.get('event', ''), r.get('job_id', ''), r.get('stage', ''))
    have = {key(r) for r in joblog.read()}
    new = [r for r in rows if key(r) not in have and r.get('event') in ('made', 'stage', 'repeat')]
    for r in sorted(new, key=lambda r: r.get('time', '')):
        joblog.record(**{k: r.get(k, '') for k in joblog.FIELDS})
    return len(new)


def temp_path() -> Path:
    fd, name = tempfile.mkstemp(prefix='loomlab-backup-', suffix='.zip')
    os.close(fd)
    return Path(name)
