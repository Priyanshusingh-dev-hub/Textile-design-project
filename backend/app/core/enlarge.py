"""Enlarge a design on this PC to a print-size, high-resolution file, and
measure that the design did not change on the way.

Two ways, both local (no upload, no internet):
- `lanczos`: two Lanczos steps and a light unsharp mask. Smooth edges, no
  invented detail. Always available.
- `realesrgan`: the Real-ESRGAN upscaler, if its portable program
  (realesrgan-ncnn-vulkan, from its GitHub releases) is unzipped into
  tools/realesrgan/ or the REALESRGAN environment variable points at it. It
  sharpens more, and like any AI upscaler it can redraw fine detail, which
  the match score below catches.

The match score shrinks the enlargement back to the original's size and
compares them pixel by pixel (the Reduce step's 0-100 scale). Anything that
changed the design, rather than just making it bigger, lowers it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter

from ..color_engine.engine import pixel_match

ROOT = Path(__file__).resolve().parents[3]
# below this the enlargement no longer shows the same design: say so
MIN_MATCH = 95.0
MODEL = 'realesrgan-x4plus'


def realesrgan_path() -> Path | None:
    """The Real-ESRGAN program, if one is installed."""
    env = os.environ.get('REALESRGAN')
    candidates = [Path(env)] if env else []
    for name in ('realesrgan-ncnn-vulkan.exe', 'realesrgan-ncnn-vulkan'):
        candidates.append(ROOT / 'tools' / 'realesrgan' / name)
    for c in candidates:
        if c.is_file():
            return c
    found = shutil.which('realesrgan-ncnn-vulkan')
    return Path(found) if found else None


def _lanczos(rgb: Image.Image, size) -> Image.Image:
    w, h = rgb.size
    if size[0] > 2 * w:   # two steps keep edges cleaner than one big jump
        rgb = rgb.resize((w * 2, h * 2), Image.LANCZOS)
    big = rgb.resize(size, Image.LANCZOS)
    return big.filter(ImageFilter.UnsharpMask(radius=2.5, percent=60, threshold=2)) if size[0] > w else big


def _realesrgan(rgb: Image.Image, size, exe: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / 'in.png', Path(tmp) / 'out.png'
        rgb.save(src)
        cmd = [str(exe), '-i', str(src), '-o', str(dst), '-s', '4', '-n', MODEL]
        done = subprocess.run(cmd, cwd=exe.parent, capture_output=True, timeout=1800)
        if done.returncode != 0 or not dst.exists():
            msg = (done.stderr or done.stdout).decode(errors='replace').strip().splitlines()
            raise RuntimeError(msg[-1] if msg else f'exit code {done.returncode}')
        out = Image.open(dst).convert('RGB')
        out.load()
    # Real-ESRGAN makes it 4x; the print size is whatever was asked
    return out if out.size == tuple(size) else out.resize(size, Image.LANCZOS)


def enlarge(image: Image.Image, size, method: str = 'auto') -> dict:
    """The design at `size` (w, h) px. Returns {image, method, note, delta_e,
    match, ok}. `method`: auto (Real-ESRGAN if installed, else lanczos),
    lanczos or realesrgan. A transparent design keeps its transparency."""
    rgba = image.convert('RGBA')
    has_alpha = rgba.getchannel('A').getextrema()[0] < 255
    rgb = rgba.convert('RGB')
    exe = realesrgan_path()
    note = ''
    used = 'lanczos'
    if method in ('auto', 'realesrgan') and size[0] > image.width:
        if exe is None:
            if method == 'realesrgan':
                note = 'Real-ESRGAN is not installed (tools/realesrgan/); used Lanczos.'
        else:
            try:
                big = _realesrgan(rgb, size, exe)
                used = 'realesrgan'
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                note = f'Real-ESRGAN did not run ({e}); used Lanczos.'
    if used == 'lanczos':
        big = _lanczos(rgb, size)
    if has_alpha:
        big = big.convert('RGBA')
        big.putalpha(rgba.getchannel('A').resize(size, Image.LANCZOS))
    # back to the original's size: what is left of the difference is change,
    # not size (area averaging, so the enlargement's extra sharpness evens out)
    back = big.convert('RGB').resize(image.size, Image.BOX)
    de, match = pixel_match(image, back)
    return {'image': big, 'method': used, 'note': note, 'delta_e': de, 'match': match,
            'ok': match >= MIN_MATCH}
