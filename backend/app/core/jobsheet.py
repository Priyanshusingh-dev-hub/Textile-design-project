"""The job sheet: one printable page a mill pins up at the press.

It lists every screen in print order with its ink colour, hex, coverage and a
small picture of what that screen prints, plus the job itself: print size,
cloth colour, and whether a white under-base goes down first. Drawn with PIL
like everything else — offline, no fonts or services beyond the system's.
"""
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


def build_job_sheet(screens, proof, *, title, print_size, cloth, underbase, dpi, trap=None):
    """screens: [(order label, ink name, hex, coverage %, picture)] in print
    order, the picture being that screen's ink on the cloth. proof: the whole
    design as it will print (or None). trap: e.g. '2 px · 0.17 mm' when the
    films carry one."""
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
        fy = y
        for label, value in facts:
            d.text((x0, fy), label, fill=MUTED, font=small)
            d.text((x0 + 190, fy), value, fill=INK_TEXT, font=mid)
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
        for i, (order, name, hx, cov, pic) in enumerate(screens):
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
            if compact:
                d.text((sx, cy + 4), _clip(d, f'{name}  {cov:g}%', detail_font, room), fill=INK_TEXT, font=detail_font)
            else:
                d.text((sx, cy + 4), _clip(d, name, name_font, room), fill=INK_TEXT, font=name_font)
                d.text((sx, cy + (34 if narrow else 44)), _clip(d, detail, detail_font, room), fill=MUTED, font=detail_font)
        foot = 'Every film carries the same registration targets: line them up and the screens register.'
        d.text((x0, PAGE[1] - MARGIN), foot, fill=MUTED, font=small)
    return page
