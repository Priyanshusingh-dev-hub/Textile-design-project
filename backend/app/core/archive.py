import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image

def _safe_name(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', name).strip('-') or 'layer'

def build_zip(entries: list[tuple[str, Image.Image]], fmt: str = 'png', dpi: int = 300) -> bytes:
    """entries: list of (name, image) pairs, already prepared by the caller
    in whatever mode makes sense for fmt (e.g. print-ready grayscale for
    'tiff'). Names are de-duplicated and sanitized to safe filenames."""
    ext = 'tif' if fmt == 'tiff' else 'png'
    buf = BytesIO()
    used: set[str] = set()
    with ZipFile(buf, 'w', ZIP_DEFLATED) as zf:
        for name, image in entries:
            base = _safe_name(name)
            filename, i = f'{base}.{ext}', 1
            while filename in used:
                i += 1; filename = f'{base}-{i}.{ext}'
            used.add(filename)
            page = BytesIO()
            if fmt == 'tiff':
                image.save(page, format='TIFF', dpi=(dpi, dpi))
            else:
                image.convert('RGBA').save(page, format='PNG', dpi=(dpi, dpi))
            page.seek(0)
            zf.writestr(filename, page.read())
    return buf.getvalue()
