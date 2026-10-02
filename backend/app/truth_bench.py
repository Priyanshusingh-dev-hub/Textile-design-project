"""Truth benchmark for colour separation: score a method against the TRUTH.

The Reduce step's match is taken against the noisy input, so it under-reports
a good separation by ~10 points (a flat design degraded like an AI image is
recovered at 96-98% against its truth while the app shows 84-90%). This
builds flat designs whose truth is known (textile's `make` examples, plus any
flat PNGs in --truth-dir), degrades each like an AI picture / photo (soft
edges, low-frequency shading and tint, mottling, grain, JPEG), runs a method
on the degraded one with the true ink count, and scores:

  truth match   `pixel_match` of the separation against the truth (0-100)
  agreement     % of pixels whose ink is the truth's own colour
  input match   the Reduce step's own number (against the noisy input)
  extra edge    edge share minus the truth's (noisy staircase edges)

    python -m app.truth_bench [--methods engine,pillow_mediancut,...] [--levels mild,heavy]
                              [--truth-dir DIR] [--size 700]

A method is `f(PIL image, k) -> PIL image`; add one to METHODS to compare it.
See CLAUDE.md ("Measuring colour separation") for what has been tried.
"""
from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .core import filltrial          # puts ../textile_project on sys.path
from .color_engine import engine as colors
from textile import make as tmake

EXAMPLES = Path(__file__).resolve().parents[2] / 'textile_project' / 'examples'
AMPLITUDE = {'mild': (0.06, 4, 0.8, 70), 'heavy': (0.14, 9, 1.6, 55)}     # shading, mottle/grain, blur px, JPEG q


def _smooth_noise(shape, sigma, rng):
    import cv2
    n = cv2.GaussianBlur(rng.standard_normal(shape).astype(np.float32), (0, 0), sigma)
    return n / (n.std() + 1e-9)


def degrade(truth_rgb: np.ndarray, level: str, seed: int = 1) -> np.ndarray:
    """A flat design made to look like an AI/photo version of itself."""
    import cv2
    rng = np.random.default_rng(seed)
    shade_a, grain_a, blur, quality = AMPLITUDE[level]
    h, w = truth_rgb.shape[:2]
    img = cv2.GaussianBlur(truth_rgb.astype(np.float32), (0, 0), blur)
    shade = 1 + shade_a * _smooth_noise((h, w), 70, rng)[..., None]
    tint = shade_a * 25 * np.stack([_smooth_noise((h, w), 90, rng) for _ in range(3)], -1)
    mottle = grain_a * _smooth_noise((h, w), 3, rng)[..., None] * np.array([1, 0.8, 0.9])
    grain = rng.standard_normal((h, w, 3)).astype(np.float32) * grain_a * 0.35
    out = np.clip(img * shade + tint + mottle + grain, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, 'JPEG', quality=quality)
    return np.asarray(Image.open(buf).convert('RGB'))


def truths(size: int = 700, truth_dir: Path | None = None):
    """(name, flat RGB) from textile's examples (made at `size` px) and any PNGs in truth_dir."""
    for p in sorted(EXAMPLES.glob('*.json')):
        cfg = json.loads(p.read_text())
        cfg.pop('size_inch', None)
        cfg['size_px'] = [size, size // 2 if 'panel' in p.stem else size]
        index, pal, _ = tmake.make(cfg, log=lambda *_: None)
        yield p.stem, np.asarray(pal, np.uint8)[index]
    for p in sorted(truth_dir.glob('*.png')) if truth_dir else []:
        im = Image.open(p).convert('RGB')
        if im.size[0] > size:
            im = im.resize((size, round(im.size[1] * size / im.size[0])), Image.NEAREST)
        yield p.stem, np.asarray(im)


def agreement(sep_rgb: np.ndarray, truth_rgb: np.ndarray) -> float:
    """% of pixels whose separated ink, mapped to the nearest truth colour, is the truth's colour."""
    tcols = np.unique(truth_rgb.reshape(-1, 3), axis=0)
    scols, inv = np.unique(sep_rgb.reshape(-1, 3), axis=0, return_inverse=True)
    near = ((scols[:, None].astype(int) - tcols[None].astype(int)) ** 2).sum(-1).argmin(1)
    return float((tcols[near][inv].reshape(truth_rgb.shape) == truth_rgb).all(-1).mean() * 100)


def edge_share(a: np.ndarray) -> float:
    d = np.zeros(a.shape[:2], bool)
    d[:, 1:] |= (a[:, 1:] != a[:, :-1]).any(-1)
    d[1:, :] |= (a[1:, :] != a[:-1, :]).any(-1)
    return float(d.mean() * 100)


# ---- methods: f(PIL image, k) -> flat PIL image ------------------------------------------------

def engine(img, k):
    """LoomLab's Reduce (smoothing off), what the app does."""
    return colors.quantize_full(img, k, 0)[0].convert('RGB')


def pillow_mediancut(img, k):
    return img.quantize(k, Image.Quantize.MEDIANCUT).convert('RGB')


def pillow_octree(img, k):
    return img.quantize(k, Image.Quantize.FASTOCTREE).convert('RGB')


def kmeans_lab(img, k):
    """Plain k-means on the pixels in CIELAB (what most tools do)."""
    import cv2
    from sklearn.cluster import MiniBatchKMeans
    a = np.asarray(img)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    km = MiniBatchKMeans(k, n_init=3, random_state=0, batch_size=4096).fit(lab[::7])
    cols = np.stack([a.reshape(-1, 3)[km.predict(lab) == i].mean(0) if (km.predict(lab[::50]) == i).any() else (0, 0, 0)
                     for i in range(k)]).astype(np.uint8)
    return Image.fromarray(cols[km.predict(lab)].reshape(a.shape))


METHODS = {'engine': engine, 'pillow_mediancut': pillow_mediancut, 'pillow_octree': pillow_octree,
           'kmeans_lab': kmeans_lab}


def score(method, levels=('mild', 'heavy'), size=700, truth_dir=None, verbose=True):
    """Mean of the four measures over every truth x level: a dict."""
    rows = []
    for name, truth in truths(size, truth_dir):
        k = len(np.unique(truth.reshape(-1, 3), axis=0))
        for level in levels:
            noisy = degrade(truth, level)
            t0 = time.time()
            sep = np.asarray(method(Image.fromarray(noisy), k).convert('RGB'))
            sec = time.time() - t0
            tm = colors.pixel_match(Image.fromarray(truth), Image.fromarray(sep))[1]
            im = colors.pixel_match(Image.fromarray(noisy), Image.fromarray(sep))[1]
            rows.append(dict(design=name, level=level, k=k, truth_match=tm, agreement=agreement(sep, truth),
                             input_match=im, extra_edge=edge_share(sep) - edge_share(truth), seconds=sec))
            if verbose:
                r = rows[-1]
                print(f"  {name:16s} {level:5s} k={k}  truth {r['truth_match']:5.1f}  agree {r['agreement']:5.1f}%  "
                      f"input {r['input_match']:5.1f}  edge {r['extra_edge']:+5.2f}  {sec:4.1f}s", flush=True)
    mean = {m: float(np.mean([r[m] for r in rows])) for m in ('truth_match', 'agreement', 'input_match', 'extra_edge')}
    return mean | {'rows': rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Score colour separation methods against a known truth')
    ap.add_argument('--methods', default=','.join(METHODS))
    ap.add_argument('--levels', default='mild,heavy')
    ap.add_argument('--size', type=int, default=700)
    ap.add_argument('--truth-dir', default=None, help='more flat PNG designs to use as truth')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args(argv)
    for name in a.methods.split(','):
        r = score(METHODS[name], tuple(a.levels.split(',')), a.size, Path(a.truth_dir) if a.truth_dir else None,
                  verbose=not a.quiet)
        print(f"{name:18s} truth {r['truth_match']:5.1f}  agreement {r['agreement']:5.1f}%  "
              f"input {r['input_match']:5.1f}  extra edge {r['extra_edge']:+5.2f}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
