"""Registration (alignment) marks for print-ready screens.

A screen-printing job prints one screen per ink, one on top of the next.
The screens only line up if every film carries the *same* alignment target
at the *same* place, so the press operator can superimpose them. This adds a
white margin around each screen and draws an identical crosshair-in-circle
target in every corner of that margin -- because the marks share coordinates
across all screens, they overlay exactly when the screens are aligned, and
because they sit in the added margin they never touch the artwork.
"""
from PIL import Image, ImageDraw, ImageFont


def _draw_target(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, width: int, fill: int = 0):
    ext = int(r * 1.7)  # crosshair reaches past the circle, the classic reg target
    draw.line([(cx - ext, cy), (cx + ext, cy)], fill=fill, width=width)
    draw.line([(cx, cy - ext), (cx, cy + ext)], fill=fill, width=width)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fill, width=width)


def _font(size: int):
    for name in ('DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'Arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def add_registration_marks(gray: Image.Image, dpi: int = 300, label: str | None = None) -> Image.Image:
    """gray: an 8-bit 'L' print-ready screen (black = ink prints). Returns a
    new, larger 'L' image with a white margin and four corner registration
    targets. Mark geometry is derived from the margin (which scales with dpi)
    so the target stays a sensible physical size regardless of resolution. When
    `label` is given it is printed in the bottom margin so a press operator can
    tell the films apart without holding them to the light."""
    gray = gray.convert('L')
    w, h = gray.size
    margin = max(40, int(dpi * 0.4))  # ~0.4 inch of white border for the marks
    canvas = Image.new('L', (w + 2 * margin, h + 2 * margin), 255)
    canvas.paste(gray, (margin, margin))
    draw = ImageDraw.Draw(canvas)
    r = max(10, margin // 4)
    line_w = max(1, margin // 40)
    off = margin // 2
    cw, ch = canvas.size
    for cx, cy in [(off, off), (cw - off, off), (off, ch - off), (cw - off, ch - off)]:
        _draw_target(draw, cx, cy, r, line_w)
    if label:
        font = _font(max(12, int(margin * 0.42)))
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((cw - tw) // 2, ch - margin + (margin - (bbox[3] - bbox[1])) // 2 - bbox[1]),
                  label, fill=0, font=font)
    return canvas


def caption_plate(plate: Image.Image, text: str, swatch_hex: str | None = None, dpi: int = 300) -> Image.Image:
    """Add a labelled caption bar under a colour plate proof (ink swatch + name
    + coverage), so each plate names the ink it carries."""
    from ..color_engine.engine import hex_rgb
    import numpy as np
    plate = plate.convert('RGB')
    w, h = plate.size
    bar = max(28, int(dpi * 0.16))
    canvas = Image.new('RGB', (w, h + bar), (255, 255, 255))
    canvas.paste(plate, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line([(0, h), (w, h)], fill=(210, 210, 210), width=1)
    font = _font(max(11, int(bar * 0.5)))
    x = int(bar * 0.35)
    if swatch_hex:
        sw = int(bar * 0.5)
        y0 = h + (bar - sw) // 2
        draw.rectangle([x, y0, x + sw, y0 + sw], fill=tuple(int(v) for v in hex_rgb(swatch_hex)), outline=(150, 150, 150))
        x += sw + int(bar * 0.3)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((x, h + (bar - (bbox[3] - bbox[1])) // 2 - bbox[1]), text, fill=(30, 30, 30), font=font)
    return canvas
