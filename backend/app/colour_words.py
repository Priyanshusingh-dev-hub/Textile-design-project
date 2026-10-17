"""Colours as a client writes them: "pink ko neela", "1 navy", "kapda kala".

For the Telegram bot's colourway preview. Standard library only (the bot runs
without numpy/PIL). A colour is a name in English or Hinglish, optionally
light/halka or dark/gehra, or a #RRGGBB code. An ink is found by number (as
the bot lists them) or by the colour it is now ("pink" = the design's ink
nearest to pink). Nothing here decides colours for the client: it only reads
what they asked for.
"""
from __future__ import annotations

import re

# (name shown to the client, #hex, other ways to write it)
COLOURS = [
    ('white', '#FFFFFF', ('safed', 'safaid', 'sufaid', 'shwet')),
    ('off-white', '#F4F0E6', ('off white', 'offwhite')),
    ('cream', '#F2E8CF', ('kreem', 'kora', 'ivory')),
    ('beige', '#E3D3B0', ('baige',)),
    ('black', '#141414', ('kala', 'kaala', 'kaali', 'kali', 'kale', 'kaale')),
    ('grey', '#808080', ('gray', 'sleti', 'slate', 'dhoosar', 'grey color')),
    ('charcoal', '#3A3A3A', ('dark grey', 'dark gray')),
    ('silver', '#C0C2C4', ('chandi', 'chaandi', 'light grey', 'light gray')),
    ('red', '#C8102E', ('laal', 'lal', 'lall')),
    ('maroon', '#7A1F2B', ('mehroon', 'mahroon', 'marun', 'wine', 'dark red')),
    ('rani pink', '#D0167A', ('rani', 'magenta', 'hot pink')),
    ('pink', '#F08DB0', ('gulabi', 'gulaabi')),
    ('baby pink', '#F8CFDD', ('light pink',)),
    ('peach', '#F6B993', ('aadu',)),
    ('orange', '#F07022', ('narangi', 'naarangi', 'santri', 'kesariya', 'kesari', 'saffron')),
    ('rust', '#A8461A', ('jung',)),
    ('yellow', '#F6D10F', ('peela', 'pila', 'peeli', 'pili', 'peele')),
    ('mustard', '#D1A11A', ('sarson', 'sarso', 'haldi')),
    ('gold', '#C9A43A', ('golden', 'sunehra', 'sunehri', 'sona')),
    ('green', '#2E8B3A', ('hara', 'hari', 'hare', 'haraa')),
    ('bottle green', '#0F4A2A', ('dark green',)),
    ('parrot green', '#7CC242', ('tota', 'tota hara', 'light green', 'parrot')),
    ('olive', '#6B7A2A', ('mehendi', 'mehndi', 'mehandi', 'olive green')),
    ('mint', '#A7DFC1', ('mint green', 'pista')),
    ('teal', '#177E83', ('mor', 'mor pankhi', 'peacock')),
    ('turquoise', '#33BFC4', ('firozi', 'ferozi', 'phirozi', 'aqua')),
    ('blue', '#1F5FBF', ('neela', 'nila', 'neeli', 'nili', 'neele')),
    ('navy', '#1B2A4A', ('navy blue', 'dark blue')),
    ('royal blue', '#2442A6', ('royal',)),
    ('sky blue', '#86C7EA', ('aasmani', 'asmani', 'aasmaani', 'light blue', 'sky')),
    ('purple', '#6A2C8E', ('baingani', 'baigani', 'jamuni', 'jamni')),
    ('lavender', '#B9A3D9', ('lilac', 'light purple')),
    ('brown', '#6B4226', ('bhura', 'bhoora', 'bhoore', 'bhuri')),
    ('coffee', '#4A2E1E', ('chocolate', 'dark brown', 'kathai', 'kaththai')),
    ('khaki', '#BFA46E', ('tan', 'camel', 'khakhi')),
]

_LIGHT = {'light', 'halka', 'halki', 'halke', 'pale', 'faint'}
_DARK = {'dark', 'gehra', 'gehri', 'gehre', 'gaadha', 'gadha', 'deep'}
# words that carry no colour: "neela kar do", "1 wala rang navy chahiye"
_FILLER = {'karo', 'kar', 'do', 'dijiye', 'dena', 'kardo', 'kr', 'chahiye', 'chahie', 'banao', 'bana', 'please',
           'pls', 'plz', 'rang', 'colour', 'color', 'me', 'mein', 'main', 'wala', 'wali', 'wale', 'ka', 'ki', 'ke',
           'the', 'a', 'to', 'into', 'ink', 'sa', 'si', 'se', 'hona', 'ho', 'ye', 'yeh', 'is', 'ise', 'isko', 'jaisa',
           'jaise', 'shade', 'bhi', 'ab', 'aur', 'and', 'ko', 'it', 'make', 'change', 'badlo', 'badal', 'ek', 'no',
           'number', 'nambar', 'nmbr'}

_BY_WORDS: dict[str, str] = {}
for _name, _hex, _aliases in COLOURS:
    for _w in (_name, *_aliases):
        _BY_WORDS[_w] = _hex

_HEX = re.compile(r'#?\b([0-9a-f]{6})\b')
_CLOTH = re.compile(r'\b(kapda|kapde|kapra|kapre|kapde\s+ka|cloth|fabric|kapdaa)\b')
_CANCEL = re.compile(r'^\s*(bas|cancel|rehne\s+do|rahne\s+do|chhodo|chodo|stop|nahi|no)\s*[.!]*\s*$', re.I)


def _rgb(hx: str):
    return tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))


def _lab(hx: str):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(hx))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def distance(a: str, b: str) -> float:
    """CIE76 difference between two #RRGGBB colours: coarse, ample for naming."""
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b))) ** 0.5


def _mix(hx: str, towards: int, share: float) -> str:
    return '#' + ''.join(f'{round(c + (towards - c) * share):02X}' for c in _rgb(hx))


def lookup(phrase: str) -> str | None:
    """#RRGGBB for a colour as written ("halka neela", "navy", "#1b2a4a"), or None."""
    text = phrase.lower().strip()
    m = _HEX.search(text)
    if m:
        return '#' + m.group(1).upper()
    words = [w for w in re.findall(r"[a-z]+(?:-[a-z]+)?", text) if w not in _FILLER]
    if not words:
        return None
    whole = ' '.join(words)
    if whole in _BY_WORDS:                        # "dark green", "sky blue": named on their own
        return _BY_WORDS[whole]
    light = any(w in _LIGHT for w in words)
    dark = any(w in _DARK for w in words)
    rest = ' '.join(w for w in words if w not in _LIGHT and w not in _DARK)
    base = _BY_WORDS.get(rest)
    if base is None:
        return None
    if light:
        return _mix(base, 255, 0.45)
    if dark:
        return _mix(base, 0, 0.4)
    return base


def name_of(hx: str) -> str:
    """The nearest colour name, to list a design's inks for a client."""
    return min(COLOURS, key=lambda c: distance(hx, c[1]))[0]


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r'[,;\n]+|\s+(?:aur|and|&|phir)\s+', text.lower()) if c.strip()]


# "pink ko neela", "pink ki jagah neela", "pink -> navy", "pink to navy"
_SWAP = re.compile(r'^(.+?)\s*(?:\bki\s+jagah\b|\bke\s+jagah\b|\bko\b|->|→|=>|\bto\b|\bse\b)\s*(.+)$')
# "1 navy", "ink 2 = #1b2a4a", "3 wala neela", "rang 2: cream"
_NUMBERED = re.compile(r'^(?:ink|rang|colour|color|no\.?|number)?\s*(\d{1,2})\s*(?:\)|\.|=|:|-|->|→|wala|wali|ko|ka|ki)?\s*(.+)$')


def parse(text: str, inks: list[str]) -> tuple[dict[int, str], str | None, list[str]]:
    """What the client asked for: {ink index (0-based): new #hex}, the cloth
    colour if they named one, and the parts that could not be read.
    `inks` are the design's inks as they are now (#hex, in the bot's order)."""
    changes: dict[int, str] = {}
    cloth = None
    unread = []
    for clause in _clauses(text):
        if _CLOTH.search(clause):
            colour = lookup(_CLOTH.sub(' ', clause))
            if colour:
                cloth = colour
            else:
                unread.append(clause)
            continue
        m = _NUMBERED.match(clause)
        if m and not _HEX.fullmatch(clause.strip()):
            n, colour = int(m.group(1)), lookup(m.group(2))
            if 1 <= n <= len(inks) and colour:
                changes[n - 1] = colour
            else:
                unread.append(clause)
            continue
        m = _SWAP.match(clause)
        if m:
            old, new = lookup(m.group(1)), lookup(m.group(2))
            if old and new and inks:
                i = min(range(len(inks)), key=lambda k: distance(inks[k], old))
                if distance(inks[i], old) <= 45:          # the design has a colour like it
                    changes[i] = new
                    continue
            unread.append(clause)
            continue
        unread.append(clause)
    return changes, cloth, unread


def is_cancel(text: str) -> bool:
    return bool(_CANCEL.match(text or ''))
