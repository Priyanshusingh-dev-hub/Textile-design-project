"""Which way to fill a line art + reference pair, decided by measurement, and
the experiment log of every decision.

The line art is only worth using when it carries the design: its areas take
the reference's colours and its lines are the clean edges. When the AI drew
the line art and the colour image separately, they disagree (an elephant's
red saddle, a flower's fine stripes), and the fill loses the design. So the
fill is not trusted, it is TRIED, against the plain alternative:

  reduce    the reference itself through LoomLab's Reduce (its suggested inks)
  method1   the user's approved fill: each closed area takes the reference's
            majority colour
  method4   Method 1 with the gaps in the line art sealed
  method3   the reference laid onto the line art first (a drifted reference)
  method2   two colours (ground, motif) from the line art's structure

Every candidate is run at the reference's own size (at most TRIAL_PX wide), so
all of them are drawn on the same pixel grid, and each is scored against the
reference with the Reduce step's own match (`pixel_match`, CIEDE2000 pixel by
pixel). The fills use the reduced reference as their colour source, so they
carry the same few inks Reduce found, not the shading's dozens.

Decision, written down with its numbers: the best fill wins when it trails
the plain Reduce by no more than TOLERANCE match points (the line art's
clean edges are worth that much); otherwise Reduce wins and the line art is
set aside. Only the winner is then made at full size.

Each run is one JSON line in `fill-trials.jsonl`, never aged out: the data to
tune TOLERANCE and the candidates on, and the start of the feedback set
(a later rating or correction can be joined on `design`).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from . import store
from ..color_engine import engine as colors

_TEXTILE = Path(__file__).resolve().parents[3] / 'textile_project'
if str(_TEXTILE) not in sys.path:
    sys.path.insert(0, str(_TEXTILE))
from textile import fill_method1 as m1  # noqa: E402
from textile import fill_method2 as m2  # noqa: E402
from textile import fill_method3 as m3  # noqa: E402
from textile import fill_method4 as m4  # noqa: E402
from textile import palette as tpal  # noqa: E402

TRIAL_PX = 1200          # candidates are drawn at the reference's size, at most this wide
TOLERANCE = 15.0         # match points a fill may trail the plain Reduce and still win. Calibrated on six
#   pairs (fill minus Reduce, best fill): the user's approved floral -7 and star -12, an AI floral -12
#   (all fill), an AI star -23, an elephant -39 (Reduce). Tree is a pair whose line art is a different
#   drawing on purpose: no match can pick it, so the operator can (the app lists every trial).
FILLS = ('method1', 'method4', 'method3', 'method2')
_LOCK = threading.Lock()


@dataclass
class Decision:
    chosen: str                       # 'reduce' or a fill name
    reason: str                       # a code the app words: fill_close | fill_far | no_fill
    trials: list = field(default_factory=list)
    inks: int = 0                     # Reduce's suggested count, the ink budget of every candidate
    tolerance: float = TOLERANCE
    margin: float | None = None       # best fill's match minus Reduce's
    trial_px: int = 0
    seconds: float = 0.0


def log_path() -> Path:
    return store.ROOT / 'fill-trials.jsonl'


def record(entry: dict) -> None:
    """Append one run. Best effort: a full disk never fails the job."""
    try:
        with _LOCK, open(log_path(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        pass


def read_log(limit: int = 200) -> list[dict]:
    try:
        lines = log_path().read_text(encoding='utf-8').splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def design_hash(image: Image.Image) -> str:
    """The same design, however it was saved: a hash of its pixels."""
    return hashlib.sha256(np.asarray(image.convert('RGB')).tobytes()).hexdigest()[:16]


def edge_share(rgb: np.ndarray) -> float:
    """Percent of pixels with a different colour next to them: the staircase
    and speckle a noisy edge has make it higher for the same design."""
    d = np.zeros(rgb.shape[:2], bool)
    d[:, 1:] |= (rgb[:, 1:] != rgb[:, :-1]).any(-1)
    d[1:, :] |= (rgb[1:, :] != rgb[:-1, :]).any(-1)
    return float(d.mean() * 100)


def _metrics(original: Image.Image, rgb: np.ndarray) -> dict:
    img = Image.fromarray(rgb)
    de, match = colors.pixel_match(original, img)
    return {'match': round(float(match), 1), 'delta_e': round(float(de), 2),
            'inks': int(len(np.unique(rgb.reshape(-1, 3), axis=0))),
            'edge_share': round(edge_share(rgb), 2)}


def _flat(fill) -> np.ndarray:
    index, pal, _ = tpal.merge_stray(fill.index, fill.pal)
    return pal[index]


def trial_size(ref_width: int) -> int:
    return max(256, min(ref_width, TRIAL_PX))


def decide(trials: list[dict], tolerance: float = TOLERANCE) -> tuple[str, str, float | None]:
    """(chosen, reason, margin): the rule alone, so it can be tested and tuned."""
    reduce = next(t for t in trials if t['name'] == 'reduce')
    fills = [t for t in trials if t['name'] in FILLS and t['status'] == 'ok']
    if not fills:
        return 'reduce', 'no_fill', None
    best = max(fills, key=lambda t: t['match'])
    margin = round(best['match'] - reduce['match'], 1)
    if margin >= -tolerance:
        return best['name'], 'fill_close', margin
    return 'reduce', 'fill_far', margin


def run(line_path: str, ref_path: str, original: Image.Image, line_color: str = 'auto',
        only: tuple[str, ...] | None = None, log=lambda *_: None) -> Decision:
    """Try every candidate on the pair and decide. `original` is the reference
    as an 8-bit image. `only` limits the fills tried (for tests)."""
    t0 = time.time()
    px = trial_size(original.size[0])
    work = original.convert('RGB')
    if work.size[0] != px:
        work = work.resize((px, max(1, round(work.size[1] * px / work.size[0]))), Image.LANCZOS)

    trials = []
    t = time.time()
    k = int(colors.suggest_colors(work)['suggested'])
    red_img = colors.quantize_full(work, k)[0].convert('RGB')
    red_rgb = np.asarray(red_img)
    trials.append({'name': 'reduce', 'status': 'ok', 'seconds': round(time.time() - t, 1), 'inks_asked': k,
                   **_metrics(work, red_rgb)})
    log(f'[trial] reduce: {k} inks, match {trials[-1]["match"]}')

    with tempfile.TemporaryDirectory() as d:
        flat_ref = os.path.join(d, 'flat_ref.png')
        red_img.save(flat_ref)               # the fills take their colours from Reduce's inks
        lc = line_color.lstrip('#')
        runners = {
            'method1': lambda: m1.fill(line_path, flat_ref, px, k, line_color=lc, force=True, log=lambda *_: None),
            'method4': lambda: m4.fill(line_path, flat_ref, px, k, line_color=lc, force=True, log=lambda *_: None),
            'method3': lambda: m3.fill(line_path, flat_ref, px, k, line_color=lc, log=lambda *_: None),
            'method2': lambda: m2.fill(line_path, ref_path, px, log=lambda *_: None),
        }
        for name in FILLS:
            if only and name not in only:
                continue
            t = time.time()
            try:
                f = runners[name]()
                rgb = _flat(f) if name != 'method2' else f.pal[f.index]
                row = {'name': name, 'status': 'ok', **_metrics(work, rgb)}
                if name != 'method2':
                    row['alignment'] = round(float(f.alignment_score), 3)
                if name == 'method3':
                    row['alignment_before'] = round(float(f.alignment_before), 3)
            except (m1.FillError, ValueError) as e:
                row = {'name': name, 'status': 'failed', 'why': str(e)[:160]}
            row['seconds'] = round(time.time() - t, 1)
            trials.append(row)
            log(f'[trial] {name}: ' + (f'match {row["match"]}, inks {row["inks"]}' if row['status'] == 'ok'
                                       else 'failed'))
    chosen, reason, margin = decide(trials)
    for row in trials:
        row['chosen'] = row['name'] == chosen
    return Decision(chosen, reason, trials, k, TOLERANCE, margin, px, round(time.time() - t0, 1))


def entry(decision: Decision, original: Image.Image, **extra) -> dict:
    """The log line for a finished run."""
    return {'time': datetime.now().isoformat(timespec='seconds'), 'design': design_hash(original),
            'reference_px': list(original.size), 'chosen': decision.chosen, 'reason': decision.reason,
            'margin': decision.margin, 'tolerance': decision.tolerance, 'inks': decision.inks,
            'trial_px': decision.trial_px, 'seconds': decision.seconds, 'trials': decision.trials, **extra}
