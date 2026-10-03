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
    assert main(['number', str(tmp_path / 'b.png'), '--out', str(out), '--size', '900', '--line-mm', '0.17',
                 '--bold-scale', '2']) == 0
    bold = np.asarray(Image.open(out / 'b_sketch_bold.png').convert('L'))
    assert bold.shape == (1800, 1800) and (bold < 128).mean() > 0.01      # --bold-scale 2: a 2x canvas, lines there
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
    # the default is the mill's own size: 3535-style grid at 300 DPI, numbers on it, nothing bigger
    out1 = tmp_path / 'o1'
    assert main(['number', str(tmp_path / 'b.png'), '--out', str(out1), '--size', '900', '--line-mm', '0.17']) == 0
    with Image.open(out1 / 'b_sketch_bold.png') as b1, Image.open(out1 / 'b_sketch_bold_numbers.png') as n1:
        assert b1.size == (900, 900) == n1.size and round(b1.info['dpi'][0]) == 300


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


def test_a_nearly_round_outline_becomes_a_true_circle_but_teeth_and_squares_stay():
    import numpy as np
    from textile import curves as cv
    t = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    wobbly = np.stack([100 + 30 * (1 + 0.05 * np.sin(5 * t)) * np.cos(t), 100 + 30 * (1 + 0.05 * np.sin(5 * t)) * np.sin(t)], 1)
    c = cv.circle_of(wobbly, (200, 200))
    assert c is not None and np.ptp(np.hypot(c[:, 0] - c[:, 0].mean(), c[:, 1] - c[:, 1].mean())) < 0.5   # perfectly round
    teeth = np.stack([100 + 30 * (1 + 0.25 * (np.sin(16 * t) > 0)) * np.cos(t),
                      100 + 30 * (1 + 0.25 * (np.sin(16 * t) > 0)) * np.sin(t)], 1)
    assert cv.circle_of(teeth, (200, 200)) is None                         # a toothed ring keeps its teeth
    sq = np.array([[70, 70], [130, 70], [130, 130], [70, 130]], float)
    sq = np.vstack([np.linspace(sq[i], sq[(i + 1) % 4], 20, endpoint=False) for i in range(4)])
    assert cv.circle_of(sq, (200, 200)) is None
    ell = np.stack([100 + 40 * np.cos(t), 100 + 20 * np.sin(t)], 1)
    assert cv.circle_of(ell, (200, 200)) is None
    assert cv.circle_of(wobbly, (200, 200), iou=0) is None                  # --circle 0 = off
    assert cv.circle_of(wobbly + 80, (200, 200)) is None                    # cut by the sheet's edge: never a circle


def test_a_wobbly_triangle_or_rectangle_becomes_clean_but_curved_shapes_are_left_alone():
    import numpy as np
    from textile import curves as cv
    rng = np.random.default_rng(1)

    def dense(v, n=40):
        v = np.array(v, float)
        return np.vstack([np.linspace(v[i], v[(i + 1) % len(v)], n, endpoint=False) for i in range(len(v))])

    def wob(p):
        return p + rng.normal(0, 0.8, p.shape)

    size = (200, 200)
    tri = cv.polygon_of(wob(dense([(60, 150), (140, 150), (100, 80)])), size)
    assert tri is not None and len(tri) == 3
    rect = cv.polygon_of(wob(dense([(60, 60), (150, 60), (150, 110), (60, 110)])), size)
    assert rect is not None and len(rect) == 4
    assert abs(rect[:, 0].max() - rect[:, 0].min() - 90) < 3                # its size is kept
    assert cv.polygon_of(wob(dense([(100, 40), (150, 80), (130, 150), (70, 150), (50, 80)])), size) is not None
    t = np.linspace(0, np.pi, 100)
    assert cv.polygon_of(np.stack([100 + 70 * np.cos(t), 100 - 70 * np.sin(t)], 1), size) is None   # a half circle
    tt = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    assert cv.polygon_of(np.stack([100 + 50 * np.cos(tt), 100 + 25 * np.sin(tt) * np.abs(np.cos(tt)) ** 0.2], 1), size) is None
    bulgy = dense([(60, 150), (140, 150), (100, 80)])
    bulgy[40:80, 1] += 10 * np.sin(np.linspace(0, np.pi, 40))              # one side bowed out: a curve, not a side
    assert cv.polygon_of(bulgy, size) is None
    assert cv.polygon_of(wob(dense([(60, 150), (140, 150), (100, 80)])), size, iou=0) is None   # --polygons 0 = off


def _lens_mask(L=120, W=44, asym=1.0):
    import cv2
    import numpy as np
    t = np.linspace(0, 1, 400)
    x = 40 + t * L
    up = 100 - W / 2 * np.sin(np.pi * t) ** 0.9
    dn = 100 + W / 2 * asym * np.sin(np.pi * t) ** 0.9
    pts = np.vstack([np.stack([x, up], 1), np.stack([x[::-1], dn[::-1]], 1)])
    m = np.zeros((240, 240), np.uint8)
    cv2.fillPoly(m, [np.round(pts * 16).astype(np.int32)], 1, shift=4)
    return m


def test_a_leaf_or_petal_gets_two_clean_arcs_and_an_oval_a_true_ellipse_but_other_shapes_stay():
    import cv2
    import numpy as np
    from textile import curves as cv
    size = (240, 240)
    sym = cv.leaf_of(cv._outlines(_lens_mask())[0], size, 1.0)
    assert sym is not None                                                   # a petal: pointed tips, round sides
    xs, ys = sym[:, 0], sym[:, 1]
    assert abs((xs.max() - xs.min()) - 120) < 3 and abs((ys.max() - ys.min()) - 44) < 3     # its size is kept
    assert abs((ys.max() - 100) - (100 - ys.min())) < 1.5                    # both sides bow out the same: symmetric
    assert cv.leaf_of(cv._outlines(_lens_mask(asym=0.6))[0], size, 1.0) is not None   # a lopsided leaf is still a leaf
    m = np.zeros((240, 240), np.uint8)
    cv2.ellipse(m, (120, 120), (60, 25), 30, 0, 360, 1, -1)
    q = cv._outlines(m)[0]
    assert cv.oval_of(q, size) is not None and cv.leaf_of(q, size, 1.0) is None   # an oval has no tips: not a leaf
    r = np.zeros((240, 240), np.uint8)
    r[60:110, 60:150] = 1
    assert cv.oval_of(cv._outlines(r)[0], size) is None and cv.leaf_of(cv._outlines(r)[0], size, 1.0) is None
    assert cv.leaf_of(cv._outlines(_lens_mask())[0], size, 1.0, iou=0) is None        # --motifs 0 = off


def test_advice_names_each_problem_with_its_fix_and_the_log_remembers_runs_and_feedback(tmp_path, monkeypatch):
    from textile import learn
    monkeypatch.setenv('TEXTILE_LEARN_LOG', str(tmp_path / 'log.jsonl'))
    good = {'name': 'a', 'size_px': [3535, 3535], 'areas': 300, 'missed': 0, 'tiny': 0, 'match': 99.9, 'line_mm': 0.17,
            'tried': [(0.17, 99.9, 300)], 'inks': [('F3E8CA', 'cream', 70.0), ('1A2F4C', 'navy', 30.0)],
            'grain': 0.6, 'woven': False, 'colours_limit': 8, 'detail': 'normal', 'snapped': {}}
    assert learn.advise(good) == []
    bad = dict(good, name='b', areas=2000, missed=3, tiny=40, match=97.0, line_mm=0.5, woven=False, grain=2.5,
               tried=[(0.17, 96.0, 2000), (0.5, 97.0, 1990)], colours_limit=3,
               inks=[('F3E8CA', 'cream', 60.0), ('1A2F4C', 'navy', 30.0), ('172A53', 'navy', 0.08)])
    codes = [c for c, _ in learn.advise(bad)]
    assert {'similar_inks', 'tiny_parts', 'missed_numbers', 'match_low', 'colours_at_limit', 'busy', 'grainy',
            'thick_line_won'} <= set(codes)
    assert all(m for _, m in learn.advise(bad))                      # every problem comes with words (its fix)
    sim = learn.similar_inks(bad['inks'])
    assert len(sim) == 1 and sim[0][0][0] == '172A53' and sim[0][1][0] == '1A2F4C'   # the stray navy next to the real one
    # the log: a run, a verdict on it, a lookalike found, a summary that mentions both
    assert learn.record(good, str(tmp_path / 'nope.png'), {'detail': 'normal'}, [])
    assert learn.record(bad, str(tmp_path / 'nope.png'), {'detail': 'normal'}, learn.advise(bad))
    assert learn.feedback('a', 'good', 'bahut achha') is not None and learn.feedback('zzz', 'bad') is None
    near = learn.similar(dict(good, name='c'), k=2)
    assert near and near[0][1]['name'] == 'a' and near[0][2] == 'good'    # a is the closest, and the user liked it
    text = learn.summary()
    assert '2 run' in text and 'good' in text and 'similar_inks' in text
    with open(tmp_path / 'log.jsonl', 'a') as fh:
        fh.write('{"half a line')                                      # a crash mid-write
    assert len(learn.similar(dict(good, name='c'), k=2)) == 2           # the rest of the log still reads


def test_number_also_makes_the_colour_plates_unless_told_not_to(tmp_path):
    im = Image.new('RGB', (300, 300), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 140, 140], fill=(140, 55, 70))
    d.rectangle([170, 170, 260, 260], fill=(27, 45, 72))
    im.save(tmp_path / 'p.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'p.png'), '--out', str(out), '--size', '900', '--line-mm', '0.17']) == 0
    pkg = out / 'package'
    assert list(pkg.glob('p_colored_channels_*.zip')) and list(pkg.glob('p_final_*.tif'))     # one channel per colour + mill TIF
    import zipfile
    with zipfile.ZipFile(next(pkg.glob('p_colored_channels_*.zip'))) as z:
        assert len([n for n in z.namelist() if n.lower().endswith('.png')]) == 3              # cream, maroon, navy
    out2 = tmp_path / 'o2'
    assert main(['number', str(tmp_path / 'p.png'), '--out', str(out2), '--size', '900', '--line-mm', '0.17',
                 '--no-package']) == 0
    assert not (out2 / 'package').exists()


def test_loose_channel_images_and_stacked_steps_are_full_size_and_the_last_step_is_the_design(tmp_path):
    import numpy as np
    from textile import stack
    im = Image.new('RGB', (300, 300), (242, 232, 204))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 140, 140], fill=(140, 55, 70))
    d.rectangle([170, 170, 260, 260], fill=(27, 45, 72))
    im.save(tmp_path / 'q.png')
    out = tmp_path / 'o'
    assert main(['number', str(tmp_path / 'q.png'), '--out', str(out), '--size', '900', '--line-mm', '0.17']) == 0
    pkg = out / 'package'
    chans = sorted((pkg / 'channels').glob('*.png'))
    steps = sorted((pkg / 'stacked').glob('*.png'))
    assert len(chans) == 3 and len(steps) == 3
    for f in chans + steps:
        with Image.open(f) as x:
            assert x.size == (900, 900) and round(x.info['dpi'][0]) == 300      # each one a full-size image, not a sheet
    final = np.asarray(Image.open(next(pkg.glob('q_final_*.png'))).convert('RGB'))
    assert (np.asarray(Image.open(steps[-1]).convert('RGB')) == final).all()    # all plates stacked = the design
    assert not (np.asarray(Image.open(steps[0]).convert('RGB')) == final).all()
