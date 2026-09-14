import os
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

def path_for(image_id: str) -> Path: return ROOT / f'{image_id}.png'
def save(image: Image.Image) -> str:
    image_id = uuid4().hex
    image.convert('RGBA').save(path_for(image_id))
    return image_id
def load(image_id: str) -> Image.Image:
    path = path_for(image_id)
    if not path.exists(): raise FileNotFoundError('This image is no longer available. Please import it again.')
    return Image.open(path).convert('RGBA')

def cleanup_expired(expiry_hours: float = None) -> int:
    """Delete generated images (.png) older than expiry_hours. Saved
    projects (.textileproj) are never touched by this, so saved work
    is preserved regardless of age."""
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
