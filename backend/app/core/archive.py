import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from PIL import Image


def encode(image: Image.Image, fmt: str, dpi: int) -> bytes:
    """One zip entry's bytes. Split out so a caller can encode several images
    in parallel and hand build_package the results."""
    page = BytesIO()
    if fmt == 'tiff':
        # LZW: lossless, read by every RIP, and a film unzips to ~0.3 MB
        # instead of 13 MB for a 12-inch design.
        image.save(page, format='TIFF', dpi=(dpi, dpi), compression='tiff_lzw')
    else:
        # keep RGB proofs RGB — an alpha channel nobody uses costs a copy and
        # a quarter more pixels to encode
        img = image if image.mode in ('RGB', 'RGBA', 'L', 'LA') else image.convert('RGBA')
        img.save(page, format='PNG', dpi=(dpi, dpi))
    return page.getvalue()


def _write_image(zf: ZipFile, name: str, image, fmt: str, dpi: int) -> None:
    """`image` is a PIL image, or bytes already produced by `encode`."""
    data = image if isinstance(image, (bytes, bytearray)) else encode(image, fmt, dpi)
    # PNG and LZW-TIFF are already compressed; deflating them again inside the
    # zip spends seconds on a large design to save nothing.
    zf.writestr(name, data, compress_type=ZIP_STORED)


def _safe_name(name: str) -> str:
    """Sanitise a zip entry name, preserving forward-slash folder structure
    (so 'plates/Red Ink' stays in the plates/ folder) while scrubbing every
    path segment to safe filename characters."""
    parts = [re.sub(r'[^A-Za-z0-9_.-]+', '-', part).strip('-') for part in name.split('/')]
    parts = [p for p in parts if p]
    return '/'.join(parts) or 'layer'

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
            _write_image(zf, filename, image, fmt, dpi)
    return buf.getvalue()


def build_package(plates, screens, dpi: int = 300, composite: Image.Image | None = None,
                  readme: str | None = None, svgs=None, combined_svg: str | None = None,
                  job_sheet: Image.Image | None = None) -> bytes:
    """The single production zip a mill downloads.

    plates:  list of (name, RGB colour-proof image) -> plates/<name>.png
    screens: list of (name, print-ready 'L' screen)  -> screens/<name>.tif (300 DPI)
    (a plate or screen may instead be bytes already produced by `encode`)
    composite: optional full-colour proof             -> proof.png
    readme:    optional plain-text contents note      -> README.txt
    svgs:      optional list of (name, svg text)       -> vector/<name>.svg
    combined_svg: optional whole-design SVG            -> vector/design.svg

    Plate/screen/svg lists are index-aligned (one ink each) and share one set
    of de-duplicated stems, so a plate, its screen and its SVG always carry the
    same filename."""
    svgs = svgs or []
    buf = BytesIO()
    with ZipFile(buf, 'w', ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for idx, ((pname, plate_img), (_, screen_img)) in enumerate(zip(plates, screens)):
            base = _safe_name(pname).split('/')[-1]
            stem, i = base, 1
            while stem in used:
                i += 1; stem = f'{base}-{i}'
            used.add(stem)
            _write_image(zf, f'plates/{stem}.png', plate_img, 'png', dpi)
            _write_image(zf, f'screens/{stem}.tif', screen_img, 'tiff', dpi)
            if idx < len(svgs) and svgs[idx][1]:      # '' = no vector for this screen
                zf.writestr(f'vector/{stem}.svg', svgs[idx][1])
        if combined_svg:
            zf.writestr('vector/design.svg', combined_svg)
        if composite is not None:
            _write_image(zf, 'proof.png', composite, 'png', dpi)
        if job_sheet is not None:            # the page pinned up at the press
            zf.writestr('job-sheet.png', encode(job_sheet, 'png', 150), compress_type=ZIP_STORED)
        if readme:
            zf.writestr('README.txt', readme)
    return buf.getvalue()
