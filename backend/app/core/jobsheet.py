"""The job sheet: one printable page a mill pins up at the press.

It lists every screen in print order with its ink colour, hex, coverage and a
small picture of what that screen prints, plus the job itself: print size,
cloth colour, and whether a white under-base goes down first. Drawn with PIL
like everything else — offline, no fonts or services beyond the system's.
"""
from functools import lru_cache

from PIL import Image, ImageDraw

from .regmarks import _TEXT, _font
from ..color_engine.engine import hex_rgb

# A4 portrait at 150 DPI: prints on any office printer at the mill.
PAGE = (1240, 1754)
MARGIN = 70
INK_TEXT = (28, 28, 28)
MUTED = (110, 110, 110)
RULE = (205, 205, 205)


def _rgb(hx):
    return tuple(int(v) for v in hex_rgb(hx))


def _fit(img, box):
    """`img` scaled to fit inside (w, h), aspect kept."""
    im = img.convert('RGB')
    im.thumbnail(box, Image.LANCZOS)
    return im


def _clip(d, text, font, width):
    """`text`, shortened with an ellipsis to fit `width` pixels."""
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + '…', font=font) > width:
        text = text[:-1]
    return text + '…'


# Nothing on the sheet is smaller than 8 pt: at 150 DPI that is 17 px. A name
# too long for its column wraps onto the next line instead of shrinking.
MIN_TEXT_PX = 17
# Ink names a bureau or the mill typed in their own script (e.g. 'लाल'): drawn
# with a font that has the glyphs, where the PC has one.
_SCRIPT_FONTS = ('NotoSansDevanagari-Regular.ttf', 'NotoSansDevanagari-VariableFont_wdth,wght.ttf',
                 'Nirmala.ttf', 'Mangal.ttf')


@lru_cache(maxsize=64)
def _text_font(size, script=False):
    size = max(MIN_TEXT_PX, size)
    if script:
        from PIL import ImageFont
        for name in _SCRIPT_FONTS:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
    return _font(size)


def _wrap(d, text, font, width):
    """`text` as lines that each fit `width` px: broken after '_', ' ' or '·'
    where it can, otherwise between characters. Nothing is cut off."""
    fits = lambda t: d.textlength(t, font=font) <= width
    lines, cur = [], ''
    for piece in [p for p in __import__('re').split(r'(?<=[_ ·])', text) if p]:
        if fits(cur + piece):
            cur += piece
        elif fits(piece.rstrip()) and cur:     # the piece fits a line of its own
            lines.append(cur.rstrip()); cur = piece
        else:                                  # too long for any line: fill by character
            for ch in piece:
                if cur and not fits(cur + ch):
                    lines.append(cur.rstrip()); cur = ''
                cur += ch
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or ['']


def _row_lines(d, name, label, detail, name_size, detail_size, width):
    """[(text, font, is_name)] for one screen's row: the file name whole
    (wrapped), then the detail line, led by the ink's own name when the file
    name had to change it (a Devanagari name becomes 'Ink' in the file). A
    row that needs wrapping uses the sheet's small sizes (21 / 17 px, never
    under 8 pt) so it stays inside its row."""
    if label and label not in name:
        detail = f'{label}  ·  {detail}'
    script = any(ord(ch) > 0x24F for ch in detail)
    nf = _text_font(name_size)
    if d.textlength(name, font=nf) > width:
        nf, detail_size = _text_font(min(name_size, 21)), MIN_TEXT_PX
    df = _text_font(detail_size, script)
    return ([(line, nf, True) for line in _wrap(d, name, nf, width)]
            + [(line, df, False) for line in _wrap(d, detail, df, width)])


def build_job_sheet(screens, proof, *, title, print_size, cloth, underbase, dpi, trap=None, dots=None, seam=None):
    """screens: [(order label, file name, hex, coverage %, picture[, the ink's
    own name])] in print
    order, the picture being that screen's ink on the cloth. proof: the whole
    design as it will print (or None). trap: e.g. '2 px · 0.17 mm' when the
    films carry one. seam: the repeat seam check on the films, e.g.
    'L-R OK · T-B FAIL' (None: not a repeat, no line)."""
    page = Image.new('RGB', PAGE, 'white')
    d = ImageDraw.Draw(page)
    x0, y = MARGIN, MARGIN
    with _TEXT:
        big, mid, small = _font(46), _font(26), _font(21)
        d.text((x0, y), 'LoomLab job sheet', fill=INK_TEXT, font=big)
        y += 70
        d.text((x0, y), title, fill=MUTED, font=small)
        y += 44

        # the job at a glance, proof on the right
        pw = 360
        if proof is not None:
            pic = _fit(proof, (pw, pw))
            page.paste(pic, (PAGE[0] - MARGIN - pic.width, y))
            d.rectangle([PAGE[0] - MARGIN - pic.width - 1, y - 1, PAGE[0] - MARGIN, y + pic.height],
                        outline=RULE)
        facts = [('Print size', print_size), ('Resolution', f'{dpi} DPI films'),
                 ('Screens', str(len(screens))), ('Cloth', cloth.upper())]
        if trap:
            facts.append(('Trap', trap))
        if dots:
            facts.append(('Tiny dots', dots))
        if seam:
            facts.append(('Repeat seam', seam))
        fy = y
        for label, value in facts:
            d.text((x0, fy), label, fill=MUTED, font=small)
            bad = label == 'Repeat seam' and 'FAIL' in value
            d.text((x0 + 190, fy), value, fill=(180, 60, 40) if bad else INK_TEXT, font=mid)
            if label == 'Cloth':
                tw = d.textlength(value, font=mid)
                d.rectangle([x0 + 200 + tw, fy + 2, x0 + 232 + tw, fy + 30], fill=_rgb(cloth), outline=MUTED)
            fy += 46
        if underbase:
            d.text((x0, fy + 6), 'Print the white UNDER-BASE first.', fill=(180, 60, 40), font=mid)
        y = max(y + pw, fy + 60) + 30
        d.line([(x0, y), (PAGE[0] - MARGIN, y)], fill=RULE, width=2)
        y += 24
        d.text((x0, y), 'Print in this order', fill=INK_TEXT, font=mid)
        y += 50

        # one row per screen: as few columns as keep a row tall enough for
        # its picture and two lines of text (a bureau PSD can bring dozens)
        space = PAGE[1] - y - MARGIN - 40
        for cols in (1, 2, 3, 4):
            rows = -(-len(screens) // cols)
            row_h = min(150, space // max(rows, 1))
            if (cols == 1 and len(screens) <= 6) or row_h >= 84 or cols == 4:
                break
        col_w = (PAGE[0] - 2 * MARGIN - (cols - 1) * 30) // cols
        narrow = cols >= 3                   # every pixel of width goes to the words
        thumb = max(min(row_h - 16, col_w // 4 if narrow else 150), 8)
        compact = row_h < 84                 # too tight for two lines: one line each
        name_font = small if narrow else mid
        detail_font = _font(17) if narrow else small
        num_w = 40 if narrow else 48
        for i, (order, name, hx, cov, pic, *more) in enumerate(screens):
            label = more[0] if more else None
            cx = x0 + (i // rows) * (col_w + 30)
            cy = y + (i % rows) * row_h
            d.text((cx, cy + thumb // 2 - 14), str(order), fill=INK_TEXT, font=name_font if narrow else mid)
            tx = cx + num_w
            if pic is not None:
                t = _fit(pic, (thumb, thumb))
                page.paste(t, (tx, cy))
                d.rectangle([tx - 1, cy - 1, tx + t.width, cy + t.height], outline=RULE)
            sx = tx + thumb + (12 if narrow else 18)
            if not narrow:                   # the picture already shows the ink when space is short
                sw = min(34, thumb)
                d.rectangle([sx, cy + 4, sx + sw, cy + 4 + sw], fill=_rgb(hx), outline=MUTED)
                sx += 48
            room = cx + col_w - sx - 10          # text never runs into the next column
            detail = (f'{hx.upper()}  ·  {cov:g}% of the design' if cols == 1
                      else f'{hx.upper()} {cov:g}%' if narrow else f'{hx.upper()}  ·  {cov:g}%')
            ny = cy + 4
            for text, f, is_name in _row_lines(d, name, label, detail,
                                               MIN_TEXT_PX if compact else getattr(name_font, 'size', 21),
                                               getattr(detail_font, 'size', MIN_TEXT_PX), room):
                d.text((sx, ny), text, fill=INK_TEXT if is_name else MUTED, font=f)
                ny += f.size + 3
        foot = 'Every film carries the same registration targets: line them up and the screens register.'
        d.text((x0, PAGE[1] - MARGIN), foot, fill=MUTED, font=small)
    return page
