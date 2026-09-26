import os
import re
import time
from pathlib import Path
from uuid import uuid4
from PIL import Image

# Real mill production files run well past Pillow's default 178-megapixel
# decompression-bomb guard (a 10200x19200 screen is ~196 megapixels) -- this
# app only ever processes files the user explicitly uploads, so raise the
# ceiling instead of rejecting legitimate large designs. Still bounded (not
# disabled) so a corrupt/malicious header can't claim unlimited dimensions.
Image.MAX_IMAGE_PIXELS = int(os.environ.get('MAX_IMAGE_PIXELS', 400_000_000))

ROOT = Path(os.environ.get('DATA_DIR') or (Path(__file__).resolve().parents[2] / 'data'))
ROOT.mkdir(parents=True, exist_ok=True)
CLEANUP_EXPIRY_HOURS = float(os.environ.get('CLEANUP_EXPIRY_HOURS', 48))

_ID_RE = re.compile(r'^[0-9a-f]{32}$')
def path_for(image_id: str) -> Path:
    # image_id comes from a URL/JSON field; only accept the exact id format we
    # mint (uuid4 hex) so a crafted value like '../../etc/passwd' can never
    # traverse out of the data directory.
    if not isinstance(image_id, str) or not _ID_RE.match(image_id):
        raise FileNotFoundError('This image is no longer available. Please import it again.')
    return ROOT / f'{image_id}.png'
def save(image: Image.Image) -> str:
    image_id = uuid4().hex
    # A working copy that ages out in CLEANUP_EXPIRY_HOURS, so favour speed
    # over size. Measured at 13 MP: a painterly upload saves in 1.5s instead of
    # 7s for 18% more bytes; flat designs and masks gain less (0.97 -> 0.61s,
    # 0.70 -> 0.56s). Nothing the mill keeps is written here.
    img = image if image.mode == 'RGBA' else image.convert('RGBA')
    img.save(path_for(image_id), compress_level=1)
    return image_id
def screen_path(image_id: str, max_side: int) -> Path:
    """Where the screen-sized copy of an image is kept. It is a working file
    like any other (*.png), so it ages out with the rest."""
    return path_for(image_id).with_name(f'{image_id}.s{int(max_side)}.png')
def exists(image_id: str) -> bool:
    return path_for(image_id).exists()
def load(image_id: str) -> Image.Image:
    path = path_for(image_id)
    if not path.exists(): raise FileNotFoundError('This image is no longer available. Please import it again.')
    return Image.open(path).convert('RGBA')

def cleanup_expired(expiry_hours: float = None) -> int:
    """Delete working images older than expiry_hours. Everything this app
    stores is a working image — an upload, a reduced design, a mask or a
    proof — so the whole cache ages out together."""
    expiry_hours = CLEANUP_EXPIRY_HOURS if expiry_hours is None else expiry_hours
    cutoff = time.time() - expiry_hours * 3600
    removed = 0
    for path in ROOT.glob('*.png'):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
