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
MISSING = 'This image is no longer available. Please import it again.'

# Image ids are always uuid4().hex. Anything else (e.g. "../../somewhere")
# is rejected before it can be turned into a path outside ROOT.
_ID_RE = re.compile(r'[0-9a-f]{32}')

def path_for(image_id: str) -> Path:
    if not isinstance(image_id, str) or not _ID_RE.fullmatch(image_id):
        raise FileNotFoundError(MISSING)
    return ROOT / f'{image_id}.png'

def existing_path(image_id: str) -> Path:
    """Path of a stored image, refreshing its mtime so an image that is still
    in use is never swept by cleanup_expired() just because it was imported
    long ago -- expiry counts from last use, not from creation."""
    path = path_for(image_id)
    try:
        os.utime(path)
    except FileNotFoundError:
        raise FileNotFoundError(MISSING)
    except OSError:
        if not path.exists(): raise FileNotFoundError(MISSING)
    return path

def save(image: Image.Image) -> str:
    image_id = uuid4().hex
    # These are working files, not deliverables: a light compression level
    # saves several times faster on mill-sized images for a modestly bigger file.
    image.convert('RGBA').save(path_for(image_id), compress_level=1)
    return image_id

def load(image_id: str) -> Image.Image:
    return Image.open(existing_path(image_id)).convert('RGBA')

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
