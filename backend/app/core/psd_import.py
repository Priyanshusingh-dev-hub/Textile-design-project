import struct
from io import BytesIO
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.psd import PSD as RawPSD
from psd_tools.constants import ColorMode, Resource
from . import pixels
from .intake import DAMAGED, DamagedFile

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
        # the file parsed (open_psd_any read it whole first), so this is more
        # likely a Photoshop feature psd-tools cannot draw than a damaged file
        raise ValueError(f'Could not read this PSD file ({e}). If it opens in Photoshop, save it again '
                         'with "Maximize compatibility" on, or export it as PNG or TIFF.') from e
    if composite is None:
        raise ValueError('This PSD has no visible layers to import.')
    return composite.convert('RGBA')

def is_complete(raw: bytes) -> bool:
    """Is every byte the PSD's own header and section lengths promise there?
    psd-tools reads a cut-off file without a word (a half-downloaded design
    imports with its bottom half blank), so the lengths are checked here: the
    three length-prefixed sections, then the merged image (raw or RLE: its
    row byte counts say exactly how long it is). ZIP-compressed image data is
    left to psd-tools."""
    try:
        psb = struct.unpack('>H', raw[4:6])[0] == 2
        channels, height, width, depth = struct.unpack('>HIIH', raw[12:24])
        o = 26
        for section in range(3):                 # colour mode data, image resources, layer and mask info
            size = 8 if (psb and section == 2) else 4
            if o + size > len(raw):
                return False
            o += size + int.from_bytes(raw[o:o + size], 'big')
            if o > len(raw):
                return False
        if o + 2 > len(raw):
            return False
        compression = struct.unpack('>H', raw[o:o + 2])[0]
        o += 2
        if compression == 0:
            need = channels * height * ((width * depth + 7) // 8)
        elif compression == 1:
            rows, wide = channels * height, 4 if psb else 2
            if o + rows * wide > len(raw):
                return False
            need = sum(struct.unpack(f'>{rows}{"I" if psb else "H"}', raw[o:o + rows * wide]))
            o += rows * wide
        else:
            return True
        return o + need <= len(raw)
    except struct.error:
        return False


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
    if len(raw) < 26:
        raise DamagedFile(DAMAGED)
    height, width = struct.unpack('>II', raw[14:22])   # the size from the 26-byte header, before anything is parsed
    pixels.check((width, height))
    if not is_complete(raw):
        raise DamagedFile(DAMAGED)
    try:
        parsed = RawPSD.read(BytesIO(raw))
    except Exception as e:
        raise DamagedFile(DAMAGED) from e
    if parsed.header.color_mode == ColorMode.MULTICHANNEL:
        try:
            return 'channels', _extract_channels(parsed)
        except DamagedFile:
            raise
        except ValueError as e:
            if 'not supported' in str(e):            # a readable file LoomLab cannot use yet: its own words
                raise
            raise DamagedFile(DAMAGED) from e        # planes shorter than the header says
        except Exception as e:
            raise DamagedFile(DAMAGED) from e
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
