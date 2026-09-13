from io import BytesIO
from PIL import Image
from psd_tools import PSDImage

PSD_MAGIC = b'8BPS'

def is_psd(raw: bytes) -> bool:
    return raw[:4] == PSD_MAGIC

def open_psd(raw: bytes) -> Image.Image:
    """Flatten a layered PSD's merged composite into a single RGBA image
    using the actual layer stack (not just the low-fidelity thumbnail
    Pillow itself can sometimes read from a PSD's merged-image resource)."""
    try:
        psd = PSDImage.open(BytesIO(raw))
        composite = psd.composite()
    except Exception as e:
        raise ValueError(f'Could not read this PSD file: {e}')
    if composite is None:
        raise ValueError('This PSD has no visible layers to import.')
    return composite.convert('RGBA')
