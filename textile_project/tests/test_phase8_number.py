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
