from io import BytesIO
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.psd import PSD as RawPSD
from psd_tools.constants import ColorMode, Resource

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

def open_psd_any(raw: bytes):
    """Returns ('image', Image) for a normal PSD, flattened via open_psd();
    or ('channels', [(name, Image), ...]) for a Multichannel-mode PSD.

    Mills commonly export production files as Multichannel PSDs where every
    channel *is* one pre-separated spot-ink screen (channel names like
    "1 FOIL 80 JALI", "2 BROWN 120") -- there is no RGB composite to flatten
    to, and doing so would silently discard the real per-ink data the file
    exists to carry. Detecting that case needs the color mode from the raw
    header, so this parses once with the low-level reader and only falls
    back to PSDImage.open()/composite() for the ordinary case."""
    try:
        parsed = RawPSD.read(BytesIO(raw))
    except Exception as e:
        raise ValueError(f'Could not read this PSD file: {e}')
    if parsed.header.color_mode == ColorMode.MULTICHANNEL:
        return 'channels', _extract_channels(parsed)
    return 'image', open_psd(raw)

def _extract_channels(parsed):
    header = parsed.header
    if header.depth != 8:
        raise ValueError(f'Multichannel PSDs with {header.depth}-bit channels are not supported yet (only 8-bit).')
    try:
        names = parsed.image_resources.get_data(Resource.ALPHA_NAMES_PASCAL) or []
    except Exception:
        names = []
    planes = parsed.image_data.get_data(header)
    channels = []
    for i, plane in enumerate(planes):
        arr = np.frombuffer(plane, dtype=np.uint8).reshape(header.height, header.width)
        name = names[i] if i < len(names) else f'Screen {i + 1}'
        channels.append((name, Image.fromarray(arr)))
    return channels
