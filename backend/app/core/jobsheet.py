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


def _fit_lines(d, text, width, max_lines=3, sizes=(21, 18, MIN_TEXT_PX)):
    """(font, its size, lines): `text` wrapped to at most `max_lines` lines, in the
    largest of `sizes` that holds all of it; at the smallest size, whatever
    still does not fit ends in an ellipsis on the last line."""
    for size in sizes:
        font = _font(size)
        lines = _wrap(d, text, font, width)
        if len(lines) <= max_lines:
            return font, size, lines
    rest = ' '.join(lines[max_lines - 1:])
    return font, size, lines[:max_lines - 1] + [_clip(d, rest, font, width)]


def _plan(d, screens, space, cols, small, mid, tight=False):
    """The screen rows laid out in `cols` columns: sizes, and each row's text
    lines (`_row_lines`). `text_h` is the tallest row's text, which must fit
    in `row_h` so a wrapped row never runs into the next one."""
    rows = -(-len(screens) // cols)
    row_h = min(150, space // max(rows, 1))
    col_w = (PAGE[0] - 2 * MARGIN - (cols - 1) * 30) // cols
    narrow = cols >= 3                       # every pixel of width goes to the words
    thumb = max(min(row_h - 16, col_w // 4 if narrow else 150), 8)
    compact = tight or row_h < 84            # too tight for two lines: the small sizes
    name_font = small if narrow else mid
    detail_font = _font(17) if narrow else small
    num_w = 40 if narrow else 48
    if tight:                                # long names: a small picture, no swatch, more room
        thumb = min(thumb, 48)
    swatch = not (narrow or tight)
    text_x = num_w + thumb + (12 if narrow else 18) + (48 if swatch else 0)
    room = col_w - text_x - 10               # text never runs into the next column
    lines = []
    for order, name, hx, cov, pic, *more in screens:
        detail = (f'{hx.upper()}  ·  {cov:g}% of the design' if cols == 1
                  else f'{hx.upper()} {cov:g}%' if narrow else f'{hx.upper()}  ·  {cov:g}%')
        lines.append(_row_lines(d, name, more[0] if more else None, detail,
                                MIN_TEXT_PX if compact else getattr(name_font, 'size', 21),
                                getattr(detail_font, 'size', MIN_TEXT_PX), room))
    text_h = max((4 + sum(f.size + 3 for _, f, _ in ls) for ls in lines), default=0)
    return {'rows': rows, 'row_h': row_h, 'col_w': col_w, 'narrow': narrow, 'thumb': thumb,
            'name_font': name_font, 'num_w': num_w, 'swatch': swatch, 'text_x': text_x, 'lines': lines, 'text_h': text_h}


def build_job_sheet(screens, proof, *, title, print_size, cloth, underbase, dpi, trap=None, dots=None, seam=None,
                    tints=None):
    """screens: [(order label, file name, hex, coverage %, picture[, the ink's
    own name])] in print
    order, the picture being that screen's ink on the cloth. proof: the whole
    design as it will print (or None). trap: e.g. '2 px · 0.17 mm' when the
    films carry one. seam: the repeat seam check on the films, e.g.
    'L-R OK · T-B FAIL' (None: not a repeat, no line). tints: the line naming
    tinted screens (`ink_proof.tint_line`), wrapped, or None."""
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
        if tints:                            # full width, under the proof: the engraver must see it all
            font, size, lines = _fit_lines(d, tints, PAGE[0] - 2 * MARGIN)
            step = size + 7
            for i, ln in enumerate(lines):
                d.text((x0, y - 10 + i * step), ln, fill=(180, 60, 40), font=font)
            y += step * len(lines) + 6
        d.line([(x0, y), (PAGE[0] - MARGIN, y)], fill=RULE, width=2)
        y += 24
        d.text((x0, y), 'Print in this order', fill=INK_TEXT, font=mid)
        y += 50

        # one row per screen: as few columns as keep a row tall enough for
        # its picture and two lines of text (a bureau PSD can bring dozens)
        space = PAGE[1] - y - MARGIN - 40
        for cols, tight in ((c, t) for c in (1, 2, 3, 4) for t in (False, True)):
            plan = _plan(d, screens, space, cols, small, mid, tight)
            # a row must hold its wrapped name and detail lines, not run into the next
            if plan['text_h'] <= plan['row_h'] and (
                    (cols == 1 and len(screens) <= 6) or plan['row_h'] >= 84 or cols == 4):
                break
        else:                                # nothing fits: grow the rows, in the shortest layout
            def height(ct):
                p = _plan(d, screens, space, ct[0], small, mid, ct[1])
                return p['rows'] * max(p['row_h'], p['text_h'])
            cols, tight = min(((c, t) for c in (1, 2, 3, 4) for t in (False, True)), key=height)
            plan = _plan(d, screens, space, cols, small, mid, tight)
            plan['row_h'] = max(plan['row_h'], plan['text_h'])
        rows, row_h, col_w, narrow, thumb = (plan[k] for k in ('rows', 'row_h', 'col_w', 'narrow', 'thumb'))
        name_font, num_w = plan['name_font'], plan['num_w']
        for i, (order, name, hx, cov, pic, *more) in enumerate(screens):
            cx = x0 + (i // rows) * (col_w + 30)
            cy = y + (i % rows) * row_h
            d.text((cx, cy + thumb // 2 - 14), str(order), fill=INK_TEXT, font=name_font if narrow else mid)
            tx = cx + num_w
            if pic is not None:
                t = _fit(pic, (thumb, thumb))
                page.paste(t, (tx, cy))
                d.rectangle([tx - 1, cy - 1, tx + t.width, cy + t.height], outline=RULE)
            sx = cx + plan['text_x']
            if plan['swatch']:               # the picture already shows the ink when space is short
                sw = min(34, thumb)
                d.rectangle([sx - 48, cy + 4, sx - 48 + sw, cy + 4 + sw], fill=_rgb(hx), outline=MUTED)
            ny = cy + 4
            for text, f, is_name in plan['lines'][i]:
                d.text((sx, ny), text, fill=INK_TEXT if is_name else MUTED, font=f)
                ny += f.size + 3
        foot = 'Every film carries the same registration targets: line them up and the screens register.'
        d.text((x0, PAGE[1] - MARGIN), foot, fill=MUTED, font=small)
    return page
