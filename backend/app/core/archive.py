import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image

def _safe_name(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', name).strip('-') or 'layer'

def build_zip(entries: list[tuple[str, Image.Image]]) -> bytes:
    """entries: list of (name, image) pairs. Names are de-duplicated and
    sanitized to safe filenames; each image is written as a PNG."""
    buf = BytesIO()
    used: set[str] = set()
    with ZipFile(buf, 'w', ZIP_DEFLATED) as zf:
        for name, image in entries:
            base = _safe_name(name)
            filename, i = f'{base}.png', 1
            while filename in used:
                i += 1; filename = f'{base}-{i}.png'
            used.add(filename)
            page = BytesIO(); image.convert('RGBA').save(page, format='PNG'); page.seek(0)
            zf.writestr(filename, page.read())
    return buf.getvalue()
