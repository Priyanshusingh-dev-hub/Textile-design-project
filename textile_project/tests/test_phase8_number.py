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
    rows = [r for r in csv.DictReader(open(out / 'd_colors.csv')) if r['Number'] not in ('lines', 'separators')]
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
    rows = [r for r in csv.DictReader(open(out / 'c_colors.csv')) if r['Number'] not in ('lines', 'separators')]
    assert len(rows) >= 1 + 1 + 1 + 6                                     # ground, disc, outline, the six dots


def test_the_sketch_paints_back_to_the_design_with_its_own_csv(tmp_path):
    im = Image.new('RGB', (600, 600), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([80, 80, 300, 300], fill=(140, 55, 70), outline=(15, 10, 10), width=6)   # maroon, black outline
    d.rectangle([350, 350, 550, 500], fill=(27, 45, 72))                                # navy block
    im.save(tmp_path / 'p.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'p.png'), '--out', str(out), '--size', '600']) == 0
    sk = out / 'p_sketch_seal0.png'
    assert sk.exists() and (out / 'p_sketch_numbers.png').exists()
    g = np.asarray(Image.open(sk).convert('L'))
    assert set(np.unique(g)) <= {0, 60, 255}                              # black outlines, grey separators, white
    kb = np.asarray(Image.open(out / 'p_sketch_black.png').convert('L'))
    assert set(np.unique(kb)) <= {0, 255}                                 # the one to show: all black on white
    back = tmp_path / 'b'
    assert main(['paint', str(sk), '--colors', str(out / 'p_colors.csv'), '--out', str(back), '--size', '600']) == 0
    a = np.asarray(Image.open(out / 'p_flat.png').convert('RGB')).astype(int)
    b = np.asarray(Image.open(back / 'p_sketch_seal0_final_600px_300dpi.png').convert('RGB')).astype(int)
    assert (np.abs(a - b).sum(-1) < 30).mean() > 0.97                     # the same design, area for area


def test_detail_and_the_round_trip_score(tmp_path):
    from textile import number as nb
    im = Image.new('RGB', (400, 400), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([50, 50, 350, 350], fill=(27, 45, 72))                      # a navy disc, no outline
    for k in range(5):
        d.ellipse([100 + 40 * k, 195, 104 + 40 * k, 199], fill=(242, 232, 204))   # five 5 px cream specks
    im.save(tmp_path / 'd.png')
    r_hi = nb.number(str(tmp_path / 'd.png'), str(tmp_path / 'hi'), size=1200, detail='zyada', log=lambda m: None)
    r_lo = nb.number(str(tmp_path / 'd.png'), str(tmp_path / 'lo'), size=1200, detail='kam', log=lambda m: None)
    assert r_lo['areas'] < r_hi['areas']                                  # 'kam' melts the specks, 'zyada' keeps them
    assert r_hi['match'] > 97 and r_lo['match'] > 97                      # the sketch paints back to the design


def test_hd_doubles_the_pixels_at_300_dpi(tmp_path):
    im = Image.new('RGB', (200, 200), (242, 232, 204))
    ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill=(27, 45, 72))
    im.save(tmp_path / 'r_hd.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'r_hd.png'), '--out', str(out), '--size', '400']) == 0
    with Image.open(out / 'r_hd_sketch_black.png') as sk:
        assert sk.size == (800, 800) and round(sk.info['dpi'][0]) == 300
    with Image.open(out / 'r_hd_sketch_numbers.png') as nu:
        assert nu.size == (800, 800)                                       # numbers at full size too


def test_thick_lines_never_swallow_a_thin_part(tmp_path):
    from textile import number as nb
    im = Image.new('RGB', (600, 600), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 500, 500], fill=(27, 45, 72))                  # a big navy block
    d.rectangle([100, 296, 500, 303], fill=(140, 55, 70))                 # an 8 px maroon stripe across it
    im.save(tmp_path / 's.png')
    r = nb.number(str(tmp_path / 's.png'), str(tmp_path / 'o'), size=600, line_mm=0.6, log=lambda m: None)
    sk = np.asarray(Image.open(r['sketch']).convert('L'))
    assert (sk[200, 150:450] == 255).all()                                # the block's middle stays white
    assert (sk[286:300, 300] < 255).sum() >= 4                            # a thick line along the stripe's side
    assert (sk[299:301, 150:450] == 255).any(axis=0).all()                # ...but the stripe keeps its middle
    assert r['match'] > 97


def test_auto_line_width_tries_three_and_keeps_the_closest(tmp_path):
    from textile import number as nb
    im = Image.new('RGB', (400, 400), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 340, 340], fill=(27, 45, 72))
    d.rectangle([180, 100, 220, 300], fill=(140, 55, 70))
    im.save(tmp_path / 'a.png')
    r = nb.number(str(tmp_path / 'a.png'), str(tmp_path / 'o'), size=800, log=lambda m: None)
    assert [t[0] for t in r['tried']] == list(nb.LINE_AUTO)
    best = max(m for _, m, _ in r['tried'])
    assert r['line_mm'] in nb.LINE_AUTO and dict((t[0], t[1]) for t in r['tried'])[r['line_mm']] >= best - 0.05
    assert (tmp_path / 'o' / 'a_rangeen.png').exists()
    one = nb.number(str(tmp_path / 'a.png'), str(tmp_path / 'p'), size=800, line_mm=0.35, log=lambda m: None)
    assert [t[0] for t in one['tried']] == [0.35]                         # a width given: only that one


def test_bold_sketch_keeps_circles_round_and_corners_sharp_and_writes_an_svg(tmp_path):
    im = Image.new('RGB', (300, 300), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 140, 140], fill=(140, 55, 70))                     # a circle
    d.rectangle([170, 170, 260, 260], fill=(27, 45, 72))                  # a square
    im.save(tmp_path / 'b.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'b.png'), '--out', str(out), '--size', '900', '--line-mm', '0.17']) == 0
    bold = np.asarray(Image.open(out / 'b_sketch_bold.png').convert('L'))
    assert bold.shape == (1800, 1800) and (bold < 128).mean() > 0.01      # drawn on a 2x canvas (default), lines there
    with Image.open(out / 'b_sketch_bold.png') as bi:
        assert round(bi.info['dpi'][0]) == 600                              # same inches, twice the pixels
    # the circle's stroke stays on a circle: every dark px within 12 px of the true radius (150 px at this size)
    ys, xs = np.nonzero(bold[120:960, 120:960] < 128)
    r = np.hypot(xs + 120 - 540, ys + 120 - 540)
    r = r[r < 460]                                                        # the circle's own stroke, not the sheet edge
    assert len(r) > 500 and np.percentile(np.abs(r - 300), 95) < 24
    # the square's corner is still a corner: its outer corner point (780,780) is inked, not rounded away
    assert bold[1540:1572, 1540:1572].min() < 128
    svg = (out / 'b_sketch_bold.svg').read_text()
    assert svg.startswith('<svg') and '<path' in svg


def test_colour_fill_keeps_only_the_given_colours_and_rounds_edges():
    import numpy as np
    from textile import curves as cv
    rgb = np.zeros((60, 60, 3), np.uint8)
    rgb[:] = (240, 230, 200)
    rgb[20:40, 20:40] = (140, 50, 70)
    big = cv.colour_fill(rgb, 3)
    assert big.shape == (180, 180, 3)
    got = {tuple(c) for c in big.reshape(-1, 3)}
    assert got == {(240, 230, 200), (140, 50, 70)}          # no blended colour, one colour per pixel
    assert tuple(big[90, 90]) == (140, 50, 70) and tuple(big[5, 5]) == (240, 230, 200)
    over = cv.colour_sketch(big, np.full((180, 180), 255, np.uint8))
    assert (over == big).all()                              # white line = colour untouched
