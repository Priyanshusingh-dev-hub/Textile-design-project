"""Cost and quote: what a print run costs, from the screens' coverage and the
mill's rate card, as numbers and as one image to send on WhatsApp/Telegram.

Ink is weighed, not guessed: each screen lays down ink only where it prints,
so its ink is coverage x printed area x grams per square metre. The printed
area is the cloth itself (meters x cloth width): a repeat covers the whole
width of the run. The rate card is `rate-card.json` (or the file RATE_CARD
names), read on every quote.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from .jobsheet import _clip
from .regmarks import _TEXT, _font
from ..color_engine.engine import hex_rgb

CARD_PATH = Path(os.environ.get('RATE_CARD') or Path(__file__).resolve().parents[2] / 'rate-card.json')

DEFAULTS = {
    'mill_name': 'LoomLab Mill',
    'currency': '₹',
    'screen_cost': 1500.0,                 # making one screen, per design
    'ink_per_kg': 450.0,                   # any ink not priced below
    'ink_prices': {},                      # per ink name or hex, e.g. {"Rani Pink 12": 620}
    'underbase_ink_per_kg': 380.0,         # white under-base ink
    'ink_g_per_sqm': 80.0,                 # grams of ink per m2 printed at full cover
    'fabric_width_in': 44.0,
    'fabric_per_meter': 0.0,               # 0 = the client supplies the cloth
    'labour_per_meter_per_screen': 6.0,    # printing labour: every screen passes every meter
    'setup_per_job': 500.0,                # table setup, washing, a sample
    'wastage_percent': 5.0,                # extra ink and cloth for setup and rejects
    'margin_percent': 15.0,
    'gst_percent': 5.0,
    'quote_valid_days': 7,
}
_NUMBERS = set(DEFAULTS) - {'mill_name', 'currency', 'ink_prices'}


# upper limits where a typo would make a nonsense quote (or a date past year 9999)
_MOST = {'wastage_percent': 100, 'gst_percent': 100, 'margin_percent': 1000, 'quote_valid_days': 3650}


def _number(v) -> bool:
    """A real, finite number: JSON also carries true/false, NaN and Infinity."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def load_card(path: Path | None = None) -> dict:
    """DEFAULTS overlaid with the rate card. A broken card is an error, never
    a silent fallback: a quote on prices nobody set is worse than none."""
    path = path or CARD_PATH
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except ValueError as e:
            raise ValueError(f'{path.name} is not valid JSON: {e}') from None
    return check_card(data, path.name)


def check_card(data: dict, name: str = 'rate card') -> dict:
    """DEFAULTS overlaid with `data`, or ValueError saying what is wrong."""
    if not isinstance(data, dict):
        raise ValueError(f'{name}: settings must be a set of name: value pairs')
    unknown = set(data) - set(DEFAULTS) - {'_comment'}
    if unknown:
        raise ValueError(f'{name}: unknown setting(s) {", ".join(sorted(unknown))}')
    card = dict(DEFAULTS)
    card.update({k: v for k, v in data.items() if k != '_comment'})
    for k in _NUMBERS:
        if not _number(card[k]) or card[k] < 0:
            raise ValueError(f'{name}: {k} must be a number, 0 or more')
    for k, most in _MOST.items():
        if card[k] > most:
            raise ValueError(f'{name}: {k} must be {most:g} at most')
    if card['quote_valid_days'] != int(card['quote_valid_days']):
        raise ValueError(f'{name}: quote_valid_days must be a whole number')
    for k, most in (('mill_name', 80), ('currency', 6)):
        if not isinstance(card[k], str) or not card[k].strip() or len(card[k]) > most:
            raise ValueError(f'{name}: {k} must be text, 1 to {most} characters')
    if not isinstance(card['ink_prices'], dict) or any(
            not isinstance(k, str) or not k.strip() or len(k) > 60
            or not _number(v) or v < 0
            for k, v in card['ink_prices'].items()):
        raise ValueError(f'{name}: ink_prices must map ink names to prices')
    return card


def save_card(data: dict, path: Path | None = None) -> dict:
    """Check `data` and write it as the rate card (keeping the file's note for
    whoever opens it in Notepad). Returns the card as quotes will read it."""
    path = path or CARD_PATH
    card = check_card(data, path.name)
    _write_json(path, card)
    return card


def _write_json(path: Path, values: dict) -> None:
    """Write settings atomically, keeping an existing `_comment` first."""
    try:
        comment = json.loads(path.read_text(encoding='utf-8-sig')).get('_comment')
    except (OSError, ValueError, AttributeError):
        comment = None
    out = ({'_comment': comment} if comment else {}) | values
    tmp = path.with_name(path.name + '.part')
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def _price(card, name, hx):
    prices = {k.upper(): v for k, v in card['ink_prices'].items()}
    return float(prices.get(name.upper(), prices.get(hx.upper(), card['ink_per_kg'])))


def calculate(inks, meters, card, fabric_width_in=None, underbase=False):
    """The run's cost. inks: [{name, hex, coverage %}] as separated.
    Every figure the mill pays is under `cost`; `lines` are the same with the
    margin spread over them, as the client sees them."""
    width_in = fabric_width_in or card['fabric_width_in']
    area = meters * width_in * 0.0254                           # m2 of cloth printed
    waste = 1 + card['wastage_percent'] / 100
    rows = []
    for ink in inks:
        kg = ink['coverage'] / 100 * area * card['ink_g_per_sqm'] / 1000 * waste
        price = _price(card, ink['name'], ink['hex'])
        rows.append({'name': ink['name'], 'hex': ink['hex'], 'coverage': ink['coverage'],
                     'kg': round(kg, 3), 'per_kg': price, 'cost': round(kg * price, 2)})
    if underbase:
        # the white goes under every ink: its cover is all of theirs together
        cover = min(100.0, sum(i['coverage'] for i in inks))
        kg = cover / 100 * area * card['ink_g_per_sqm'] / 1000 * waste
        rows.insert(0, {'name': 'White under-base', 'hex': '#FFFFFF', 'coverage': round(cover, 2),
                        'kg': round(kg, 3), 'per_kg': card['underbase_ink_per_kg'],
                        'cost': round(kg * card['underbase_ink_per_kg'], 2)})
    screens = len(rows)
    cost = {
        'screens': screens * card['screen_cost'],
        'ink': sum(r['cost'] for r in rows),
        'fabric': meters * waste * card['fabric_per_meter'],
        'printing': meters * screens * card['labour_per_meter_per_screen'],
        'setup': card['setup_per_job'],
    }
    cost = {k: round(v, 2) for k, v in cost.items()}
    subtotal = sum(cost.values())
    margin = subtotal * card['margin_percent'] / 100
    up = 1 + card['margin_percent'] / 100
    lines = {k: round(v * up, 2) for k, v in cost.items()}
    before_tax = round(sum(lines.values()), 2)
    gst = round(before_tax * card['gst_percent'] / 100, 2)
    total = round(before_tax + gst, 2)
    return {
        'meters': meters, 'fabric_width_in': width_in, 'area_sqm': round(area, 2), 'screens': screens,
        'inks': rows, 'ink_kg': round(sum(r['kg'] for r in rows), 3),
        'cost': cost | {'subtotal': round(subtotal, 2), 'margin': round(margin, 2)},
        'lines': lines, 'before_tax': before_tax, 'gst_percent': card['gst_percent'], 'gst': gst,
        'total': total, 'per_meter': round(total / meters, 2) if meters else 0.0,
        'currency': card['currency'],
    }


def money(value, currency='₹'):
    """Indian grouping: 1,23,456."""
    n = int(round(value))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        s = ','.join(([head] if head else []) + groups) + ',' + tail
    return f'{"-" if n < 0 else ""}{currency}{s}'


W = 1080
PAD = 56
DARK = (32, 64, 60)
TEXT = (30, 30, 30)
MUTED = (112, 112, 112)
RULE = (222, 222, 222)
ACCENT = (214, 150, 40)


def quote_image(q, card, *, proof=None, design='', client='', quote_no='', today=None):
    """The quote as one PNG, 1080 px wide: WhatsApp and Telegram show it full
    width on a phone without cropping."""
    today = today or date.today()
    cur = card['currency']
    h = 1400 + 58 * len(q['inks'])
    page = Image.new('RGB', (W, h), 'white')
    d = ImageDraw.Draw(page)
    with _TEXT:
        f_title, f_big, f_mid = _font(46), _font(40), _font(30)
        f_txt, f_small, f_bold = _font(27, bold=False), _font(23, bold=False), _font(27)
        # header band
        d.rectangle([0, 0, W, 170], fill=DARK)
        d.text((PAD, 38), card['mill_name'], fill='white', font=f_title)
        d.text((PAD, 104), 'Print quotation', fill=(205, 225, 220), font=f_mid)
        right = [f'Quote {quote_no}' if quote_no else '', today.strftime('%d %b %Y'),
                 f"Valid till {(today + timedelta(days=int(card['quote_valid_days']))).strftime('%d %b %Y')}"]
        for i, t in enumerate(x for x in right if x):
            d.text((W - PAD, 40 + i * 38), t, fill='white', font=f_small, anchor='ra')
        y = 206

        # the design and the job
        facts_x = PAD
        if proof is not None:
            pic = proof.convert('RGB'); pic.thumbnail((360, 300), Image.LANCZOS)
            page.paste(pic, (PAD, y)); d.rectangle([PAD - 1, y - 1, PAD + pic.width, y + pic.height], outline=RULE)
            facts_x = PAD + pic.width + 40
            block = pic.height
        else:
            block = 230
        facts = [('Client', client), ('Design', design),
                 ('Run', f"{q['meters']:g} m of {q['fabric_width_in']:g}\" cloth ({q['area_sqm']:g} m²)"),
                 ('Screens', f"{q['screens']}"),
                 ('Ink', f"{q['ink_kg']:.2f} kg in all")]
        fy = y
        for label, value in facts:
            if not value:
                continue
            d.text((facts_x, fy), label, fill=MUTED, font=f_small)
            d.text((facts_x + 150, fy), value, fill=TEXT, font=f_txt)
            fy += 46
        y += max(block, fy - y) + 40

        # inks
        d.text((PAD, y), 'Inks', fill=DARK, font=f_mid); y += 50
        cols = (PAD + 60, 620, 770)
        d.text((cols[0], y), 'screen', fill=MUTED, font=f_small)
        d.text((cols[1], y), 'cover', fill=MUTED, font=f_small, anchor='ra')
        d.text((cols[2], y), 'ink', fill=MUTED, font=f_small, anchor='ra')
        y += 38
        for r in q['inks']:
            d.rectangle([PAD, y, PAD + 40, y + 40], fill=tuple(int(v) for v in hex_rgb(r['hex'])), outline=RULE)
            name = _clip(d, r['name'], f_txt, cols[1] - cols[0] - 110)
            d.text((cols[0], y + 4), name, fill=TEXT, font=f_txt)
            d.text((cols[1], y + 4), f"{r['coverage']:.1f}%", fill=TEXT, font=f_txt, anchor='ra')
            d.text((cols[2], y + 4), f"{r['kg']:.2f} kg", fill=TEXT, font=f_txt, anchor='ra')
            y += 58
        y += 20
        d.line([PAD, y, W - PAD, y], fill=RULE, width=2); y += 30

        # the money, margin already inside each line
        rows = [('Screens', f"{q['screens']} screens", q['lines']['screens']),
                ('Ink', f"{q['ink_kg']:.2f} kg", q['lines']['ink']),
                ('Cloth', f"{q['meters']:g} m", q['lines']['fabric']),
                ('Printing', f"{q['meters']:g} m × {q['screens']} screens", q['lines']['printing']),
                ('Setup & sampling', '', q['lines']['setup'])]
        for label, detail, value in rows:
            if not value:
                continue
            d.text((PAD, y), label, fill=TEXT, font=f_txt)
            if detail:
                d.text((PAD + 290, y + 3), detail, fill=MUTED, font=f_small)
            d.text((W - PAD, y), money(value, cur), fill=TEXT, font=f_txt, anchor='ra')
            y += 50
        d.text((PAD, y), f"GST {q['gst_percent']:g}%", fill=TEXT, font=f_txt)
        d.text((W - PAD, y), money(q['gst'], cur), fill=TEXT, font=f_txt, anchor='ra')
        y += 64

        # total
        d.rectangle([PAD - 16, y - 12, W - PAD + 16, y + 118], fill=(248, 243, 232), outline=ACCENT, width=3)
        d.text((PAD, y + 6), 'Total', fill=DARK, font=f_big)
        d.text((W - PAD, y + 6), money(q['total'], cur), fill=DARK, font=f_big, anchor='ra')
        d.text((W - PAD, y + 66), f"{money(q['per_meter'], cur)} per meter", fill=MUTED, font=f_txt, anchor='ra')
        y += 160

        note = ('Ink is weighed from each screen\'s coverage of the design. '
                + ('Cloth supplied by the client. ' if not q['lines']['fabric'] else '')
                + f"Includes {card['wastage_percent']:g}% for setup and rejects.")
        for line in _wrap(d, note, f_small, W - 2 * PAD):
            d.text((PAD, y), line, fill=MUTED, font=f_small); y += 34
    return page.crop((0, 0, W, y + PAD))


def _wrap(d, text, font, width):
    out, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if d.textlength(trial, font=font) <= width:
            line = trial
        else:
            out.append(line); line = word
    return out + ([line] if line else [])
