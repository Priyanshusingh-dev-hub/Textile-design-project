"""The proof of an ink stack, drawn at each screen's real coverage, and the
one rule for "does this pixel count as ink".

The client approves the proof, so the proof, the TIFF films and the SVG must
agree on where ink goes. LoomLab's own separations are hard-edged (alpha 0 or
255) and come out exactly as before. A bureau's imported PSD may carry soft
edges or tints; those used to be painted as solid ink in the proof (any
alpha > 0) while the SVG kept only alpha > 127. Now:

* the proof lays each screen over the cloth at its actual coverage with a
  plain linear blend (`proof`, below): a 50% tint, printed as dots covering
  about half the area, reads about halfway between cloth and ink;
* the per-plate PNGs and the thumbnails (`engine.plate`, `engine.preview_thumb`)
  are drawn by the same function, so they match proof.png pixel for pixel;
* the TIFF film keeps the tint as it is (`255 - alpha`, unchanged);
* every yes/no question (SVG outlines, coverage %, overlap) asks `is_ink`,
  which reads the single `INK_THRESHOLD`;
* `tint_warning` tells the operator, before the proof goes out, how many
  screens carry tints and how much of them falls below the threshold, and
  `tint_line` names the tinted screens for the job sheet and the README.
"""
import os

import numpy as np
from PIL import Image

from ..color_engine.engine import hex_rgb


def _env_int(name, default, lo, hi):
    try:
        return min(hi, max(lo, int(os.environ.get(name, default))))
    except ValueError:
        return default


# A pixel counts as ink when its alpha (= 255 - the film's grey) is at least
# this: 128 = coverage of 50% or more. The ONE place this is decided; set
# LOOMLAB_INK_THRESHOLD (1-255) to change it. alpha >= 128 is exactly the old
# SVG rule (alpha > 127), so hard-edged separations are unaffected.
INK_THRESHOLD = _env_int('LOOMLAB_INK_THRESHOLD', 128, 1, 255)


def is_ink(alpha):
    """Boolean array: where this alpha (uint8 array) counts as ink. Every
    yes/no ink question in the backend goes through here."""
    return np.asarray(alpha) >= INK_THRESHOLD


def alpha_of(mask):
    """A mask's alpha channel as a uint8 array."""
    return np.asarray(mask.getchannel('A') if mask.mode == 'RGBA' else mask.convert('RGBA').getchannel('A'))


# The white of the under-base, as the proof shows it under the inks. Pure white
# by default; a mill's real base white is often a little off-white
# (LOOMLAB_UNDERBASE_WHITE, e.g. #F4F2EC).
def _env_hex(name, default):
    v = os.environ.get(name, default).strip()
    return v.upper() if len(v) == 7 and v[0] == '#' and all(c in '0123456789abcdefABCDEF' for c in v[1:]) else default


UNDERBASE_WHITE = _env_hex('LOOMLAB_UNDERBASE_WHITE', '#FFFFFF')

# One extra line for the tint warning when a white under-base prints (R-0023 c).
DARK_CLOTH_NOTE = ('On dark cloth the white under-base is solid under tints and soft edges; '
                   'they will print paler than on screen.')
DARK_CLOTH_NOTE_HI = ('Gehre kapde par white under-base tint aur soft edge ke neeche poora solid hota hai; '
                      'isliye ye screen par dikhne se halke print honge.')


def coverage_pct(alpha, ndigits=1):
    """How much of the design this screen inks, in %, weighted by the real
    ink amount: alpha.mean() / 255. A 50% tint over the whole design is 50%,
    a 25% tint 25% (not 0 or 100 as a yes/no threshold would say). For a hard
    (0/255) mask this is exactly the share of inked pixels, as before. Every
    figure that weighs ink (the quote's coverage, film labels, the job sheet)
    uses this; `is_ink` is for yes/no questions only (SVG, overlap)."""
    a = np.asarray(alpha)
    if not a.size:
        return 0.0
    return round(int(a.sum(dtype=np.int64)) / (255 * a.size) * 100, ndigits)


def _rgb(hx):
    return tuple(int(v) for v in hex_rgb(hx))


def proof(layers, size, fabric='#FFFFFF', underbase=None):
    """RGB proof of (mask, ink hex) screens stacked in order over the cloth,
    each at its real coverage v = alpha / 255:

        proof = (1 - v) * below + v * ink

    rounded to the nearest 8-bit value after each screen (PIL's composite does
    exactly this, in C; the browser's lib/inkProof.ts uses the same integer
    rule). Hard (0/255) masks give exactly the old result: alpha 0 leaves the
    pixel alone, alpha 255 is the ink itself.

    `underbase`: the white under-base film (engine.underbase), when one
    prints. Where it is on, the inks are laid over the base white instead of
    the cloth (R-0023): it goes down first, as one more screen of
    UNDERBASE_WHITE, then the same blend. A hard design is unchanged, since
    solid ink covers the base wherever the base is."""
    base = Image.new('RGB', tuple(size), _rgb(fabric))
    if underbase is not None:
        layers = [(underbase, UNDERBASE_WHITE)] + list(layers)
    for mask, color in layers:
        a = mask.getchannel('A') if mask.mode == 'RGBA' else mask.convert('RGBA').getchannel('A')
        base = Image.composite(Image.new('RGB', a.size, _rgb(color)), base, a)
    return base


def screen_tints(named_masks):
    """[(label, % of that screen's ink pixels that are tints)] for every screen
    with any pixel 0 < alpha < 255, in the order given. `named_masks` is
    [(label, mask)]; 'ink pixels' are alpha > 0."""
    out = []
    for label, m in named_masks:
        a = alpha_of(m)
        inked = int((a > 0).sum())
        part = int(((a > 0) & (a < 255)).sum())
        if part:
            out.append((label, round(part / inked * 100, 1)))
    return out


def underbase_coverage(film):
    """% of the design the white under-base film prints (its alpha > 0
    union, choked, as engine.underbase builds it): what the quote charges
    white ink for. None when there is no film."""
    return None if film is None else coverage_pct(alpha_of(film), 2)


def tint_line(named_masks):
    """ONE line for the job sheet and the package README naming each screen
    with tints and its % of tinted pixels, or None when all are hard-edged."""
    tints = screen_tints(named_masks)
    if not tints:
        return None
    return ('Tints/soft edges on ' + ', '.join(f'{label} ({pct:g}%)' for label, pct in tints)
            + ' of each screen\'s ink pixels: confirm with your engraver that they will hold, or flatten to hard edges.')


def tint_report(masks):
    """How soft the screens are: (screens with tints, screens, % of ink
    pixels that are tints (alpha 1-254), % of ink pixels under the ink
    threshold, i.e. printed on the film but left out of the SVG and counts)."""
    tinted = inked = soft = below = 0
    for m in masks:
        a = alpha_of(m)
        any_ink = a > 0
        part = any_ink & (a < 255)
        n_part = int(part.sum())
        tinted += n_part > 0
        inked += int(any_ink.sum())
        soft += n_part
        below += int((any_ink & ~is_ink(a)).sum())
    pct = lambda n: round(n / inked * 100, 1) if inked else 0.0
    return tinted, len(masks), pct(soft), pct(below)


def tint_warning(masks):
    """The operator's warning for screens with tints or soft edges, or None
    when every screen is hard-edged. Never blocks the job."""
    tinted, total, soft_pct, below_pct = tint_report(masks)
    if not tinted:
        return None
    text = (f'{tinted} of {total} screens contain tints/soft edges ({soft_pct}% of ink pixels between 1 and 254). '
            'Confirm with your engraver that these tints will hold, or flatten to hard edges.')
    hi = (f'{total} me se {tinted} screens me tint/soft edge hai (ink pixels ka {soft_pct}% 1 aur 254 ke beech). '
          'Engraver se pakka kar lo ki ye tint screen par tikega, warna hard edge kar do.')
    text += ' ' + DARK_CLOTH_NOTE
    hi += ' ' + DARK_CLOTH_NOTE_HI
    if below_pct:
        text += (f' {below_pct}% of ink pixels are lighter than the ink threshold ({INK_THRESHOLD}/255): '
                 'the films and the proof show them, the SVG outlines do not.')
        hi += (f' Ink pixels ka {below_pct}% ink threshold ({INK_THRESHOLD}/255) se halka hai: '
               'films aur proof me dikhega, SVG outline me nahi.')
    return {'code': 'tints', 'blocking': False, 'message': text, 'hi': hi, 'screens': tinted, 'of': total,
            'tint_pct': soft_pct, 'below_threshold_pct': below_pct, 'threshold': INK_THRESHOLD}
