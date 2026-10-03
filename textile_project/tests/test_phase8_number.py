"""textile number: a coloured design, every patch of one colour numbered."""
import csv

import numpy as np
from PIL import Image, ImageDraw

from textile.cli import main


def test_every_colour_patch_gets_a_number_and_its_colour(tmp_path):
    im = Image.new('RGB', (600, 600), (20, 15, 12))                       # black ground
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 240, 240], fill=(170, 55, 70))                     # pink flower
    d.ellipse([360, 60, 540, 240], fill=(170, 55, 70))                    # another one
    d.rectangle([100, 360, 500, 480], fill=(214, 189, 95))                # yellow band
    d.point([(300, 300)], fill=(255, 255, 255))                           # one speck of grain
    im.save(tmp_path / 'd.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'd.png'), '--out', str(out), '--size', '600']) == 0
    rows = list(csv.DictReader(open(out / 'd_colors.csv')))
    assert len(rows) == 4                                                  # ground, 2 flowers, band; the speck melted
    hexes = sorted(r['HEX'] for r in rows)
    assert hexes.count('#AA3746') == 2 or sum(h[1:3] in ('A9', 'AA', 'AB') for h in hexes) == 2
    for f in ('d_numbers.png', 'd_flat.png'):
        assert (out / f).exists()
    flat = np.asarray(Image.open(out / 'd_flat.png').convert('RGB'))
    assert len(np.unique(flat.reshape(-1, 3), axis=0)) == 3                # three inks


def test_a_clean_design_keeps_its_thin_outline_and_drops_the_edge_blend(tmp_path):
    from textile import number as nb
    im = Image.new('RGB', (300, 300), (242, 232, 204))                    # cream
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 240, 240], fill=(140, 55, 70), outline=(15, 10, 10), width=2)   # maroon, thin black outline
    for k in range(6):                                                    # small cream dots inside: design
        d.ellipse([100 + 18 * k, 145, 106 + 18 * k, 151], fill=(242, 232, 204))
    im = im.resize((900, 900), Image.BICUBIC)                             # soft edges: a blend between black and cream
    im.save(tmp_path / 'c.png')
    rgb = np.asarray(im)
    assert nb.grain(rgb) < nb.WOVEN_GRAIN
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'c.png'), '--out', str(out), '--size', '900']) == 0
    flat = np.asarray(Image.open(out / 'c_flat.png').convert('RGB'))
    inks = np.unique(flat.reshape(-1, 3), axis=0)
    assert len(inks) == 3                                                 # cream, maroon, black: no blend ink
    assert (flat[450, 180:200] < 60).all(axis=1).any()                    # the black outline is still there (left edge)
    rows = list(csv.DictReader(open(out / 'c_colors.csv')))
    assert len(rows) >= 1 + 1 + 1 + 6                                     # ground, disc, outline, the six dots
