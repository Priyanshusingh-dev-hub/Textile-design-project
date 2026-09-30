"""What a person helping a mill needs to see, in one report: the versions,
the PC's space, what the engine holds, whether the settings and licence are
sound, and the last errors the engine hit (also kept in a file beside the
data, `loomlab-errors.log`, so a closed window loses nothing).

Settings -> Help shows it and copies or downloads it, so an operator can send
it on WhatsApp without knowing what any of it means. It holds no designs,
prices or client names: only facts about the engine.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

from .core import store

STARTED = time.time()
MAX_ERRORS = 50
LOG_MAX_BYTES = 1_000_000          # then the log is kept as .1 and a new one started
_errors: deque = deque(maxlen=MAX_ERRORS)
_lock = threading.Lock()


def log_path() -> Path:
    return store.ROOT / 'loomlab-errors.log'


def record(method: str, path: str, exc: BaseException) -> dict:
    """Keep an error the engine hit (a 500): in memory for the report, and in
    the log file. Best effort: writing it never raises."""
    tb = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in tb if 'app' in Path(f.filename).parts] or tb
    where = f'{Path(ours[-1].filename).name}:{ours[-1].lineno} in {ours[-1].name}' if ours else ''
    item = {'at': datetime.now().isoformat(timespec='seconds'), 'method': method, 'path': path,
            'error': f'{type(exc).__name__}: {exc}'[:300], 'where': where}
    with _lock:
        _errors.append(item)
        try:
            log = log_path()
            if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
                log.replace(log.with_name(log.name + '.1'))
            with log.open('a', encoding='utf-8') as f:
                f.write(f"{item['at']} {method} {path}\n{''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}\n")
        except OSError:
            pass
    return item


def recent_errors() -> list[dict]:
    with _lock:
        return list(reversed(_errors))


def _version(module: str) -> str:
    try:
        return getattr(__import__(module), '__version__', '?')
    except ImportError:
        return 'missing'


def _commit() -> str:
    """The source's git commit, read from .git without git itself (a mill PC
    may have a zip, no .git at all: then 'unknown')."""
    root = Path(__file__).resolve().parents[2] / '.git'
    try:
        head = (root / 'HEAD').read_text(encoding='utf-8').strip()
        if head.startswith('ref: '):
            ref = head[5:]
            p = root / ref
            if p.exists():
                return p.read_text(encoding='utf-8').strip()[:10]
            packed = (root / 'packed-refs').read_text(encoding='utf-8')
            return next((l.split()[0][:10] for l in packed.splitlines() if l.endswith(' ' + ref)), 'unknown')
        return head[:10]
    except OSError:
        return 'unknown'


def _folder(path: Path) -> tuple[int, float]:
    n = size = 0
    try:
        for p in path.iterdir():
            if p.is_file():
                n += 1
                size += p.stat().st_size
    except OSError:
        pass
    return n, round(size / 1024 ** 2, 1)


def report(app_dist: Path | None = None) -> dict:
    from . import auto as auto_mode
    from . import licence
    from .core import inks, joblog, library
    from .core import quote as costing
    files, mb = _folder(store.ROOT)
    try:
        disk = shutil.disk_usage(store.ROOT)
        free_gb = round(disk.free / 1024 ** 3, 1)
    except OSError:
        free_gb = None

    def check(load):
        try:
            load()
            return 'ok'
        except (ValueError, OSError) as e:
            return f'problem: {e}'[:200]

    st = licence.status()
    index = (app_dist / 'index.html') if app_dist else None
    return {
        'made_at': datetime.now().isoformat(timespec='seconds'),
        'loomlab': {'commit': _commit(), 'up_for_minutes': round((time.time() - STARTED) / 60),
                    'app_built': datetime.fromtimestamp(index.stat().st_mtime).isoformat(timespec='minutes')
                    if index and index.exists() else 'not built'},
        'system': {'os': platform.platform(), 'python': sys.version.split()[0], 'cpus': os.cpu_count(),
                   'numpy': _version('numpy'), 'pillow': _version('PIL'), 'scipy': _version('scipy'),
                   'fastapi': _version('fastapi')},
        'data': {'folder': str(store.ROOT), 'files_in_cache': files, 'cache_mb': mb, 'disk_free_gb': free_gb,
                 'library_designs': library.entries('', 1)[1], 'job_log_lines': len(joblog.read()),
                 'shelf_inks': len(inks.load())},
        'settings': {'rate_card': check(costing.load_card), 'auto_limits': check(auto_mode.load_config)},
        'licence': {'required': st['required'], 'valid': st['valid'],
                    **({'reason': st['reason']} if st.get('reason') and not st['valid'] else {})},
        'errors': recent_errors()[:20],
    }


def as_text(r: dict) -> str:
    """The report as plain text, to paste into a message."""
    lines = [f"LoomLab report {r['made_at']}"]
    for section in ('loomlab', 'system', 'data', 'settings', 'licence'):
        lines.append(f'\n[{section}]')
        lines += [f'  {k}: {v}' for k, v in r[section].items()]
    lines.append(f"\n[last errors: {len(r['errors'])}]")
    for e in r['errors']:
        lines.append(f"  {e['at']} {e['method']} {e['path']}\n    {e['error']}\n    at {e['where']}")
    return '\n'.join(lines) + '\n'
