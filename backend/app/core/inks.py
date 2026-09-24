"""The mill's ink library: the inks already mixed and on the shelf.

A mill prints with inks it has — named recipes like "Rani Pink 12" — not a
fresh mix for every hex a reduction happens to produce. The library is a plain
JSON file beside the image cache, so it survives restarts and browsers, and
the cache cleanup (which only removes .png files) never touches it.
"""
import json
import os
from pathlib import Path

from .store import ROOT

LIBRARY = Path(os.environ.get('INK_LIBRARY') or (ROOT / 'inks.json'))
MAX_INKS = 500


def load() -> list[dict]:
    """[{name, hex}] — empty when the mill hasn't added any yet."""
    try:
        data = json.loads(LIBRARY.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return []
    return [{'name': str(i['name']), 'hex': str(i['hex']).upper()} for i in data.get('inks', [])
            if isinstance(i, dict) and 'name' in i and 'hex' in i][:MAX_INKS]


def save(inks: list[dict]) -> list[dict]:
    """Replace the library. Written to a temp file and moved into place, so a
    crash mid-write can never leave a half-written library behind."""
    clean = []
    for i in inks[:MAX_INKS]:
        hx = i['hex'].upper()
        clean.append({'name': i['name'].strip(), 'hex': hx if hx.startswith('#') else '#' + hx})
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIBRARY.with_suffix('.json.tmp')
    tmp.write_text(json.dumps({'inks': clean}, indent=1, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, LIBRARY)
    return clean
