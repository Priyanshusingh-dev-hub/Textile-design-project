"""Registration (alignment) marks for print-ready screens.

A screen-printing job prints one screen per ink, one on top of the next.
The screens only line up if every film carries the *same* alignment target
at the *same* place, so the press operator can superimpose them. This adds a
white margin around each screen and draws an identical crosshair-in-circle
target in every corner of that margin -- because the marks share coordinates
across all screens, they overlay exactly when the screens are aligned, and
because they sit in the added margin they never touch the artwork.
"""
from PIL import Image, ImageDraw


def _draw_target(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, width: int, fill: int = 0):
    ext = int(r * 1.7)  # crosshair reaches past the circle, the classic reg target
    draw.line([(cx - ext, cy), (cx + ext, cy)], fill=fill, width=width)
    draw.line([(cx, cy - ext), (cx, cy + ext)], fill=fill, width=width)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fill, width=width)


def add_registration_marks(gray: Image.Image, dpi: int = 300) -> Image.Image:
    """gray: an 8-bit 'L' print-ready screen (black = ink prints). Returns a
    new, larger 'L' image with a white margin and four corner registration
    targets. Mark geometry is derived from the margin (which scales with dpi)
    so the target stays a sensible physical size regardless of resolution."""
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
    return canvas
