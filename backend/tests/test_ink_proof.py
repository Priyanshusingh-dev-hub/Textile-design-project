"""The proof, the TIFF films and the SVG agree on where ink goes (R-0009).

LoomLab's own hard-edged screens come out exactly as before; a bureau's
tinted or soft PSD channels are drawn in the proof at their real coverage,
kept in the film as they are, and judged for the SVG / counts by the one
ink threshold, with a (non-blocking) warning to the operator."""
import struct
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.color_engine.engine import analyze, hex_rgb, reduce
from app.main import app
from app.separation_engine import engine as separation
from app.separation_engine import ink_proof
from app.separation_engine.engine import create as separation_create, print_preview, to_print_ready
from app.vector_engine import engine as vector


def _mask(alpha):
    a = np.asarray(alpha, np.uint8)
    rgba = np.zeros((*a.shape, 4), np.uint8); rgba[:, :, 3] = a
    return Image.fromarray(rgba)


def _legacy_preview(layers, size, fabric='#FFFFFF'):
    """print_preview as it was before this change: any alpha > 0 = solid ink."""
    base = np.zeros((size[1], size[0], 3), np.uint8); base[:, :] = hex_rgb(fabric)
    for mask, color in layers:
        base[np.asarray(mask.convert('RGBA'))[:, :, 3] > 0] = hex_rgb(color)
    return Image.fromarray(base)


def _three_color():           # the fixture test_package.py uses
    a = np.zeros((60, 60, 3), dtype=np.uint8)
    a[:, :20] = (216, 72, 118); a[:, 20:40] = (40, 64, 96); a[:, 40:] = (217, 164, 62)
    return Image.fromarray(a)


def _multichannel_psd(planes, names):
    """A minimal 8-bit Multichannel PSD: each plane is a film (0 = ink)."""
    h, w = planes[0].shape
    head = b'8BPS' + struct.pack('>H6xHIIHH', 1, len(planes), h, w, 8, 7)   # mode 7 = Multichannel
    pas = b''.join(bytes([len(n)]) + n.encode() for n in names)
    if len(pas) % 2:
        pas += b'\0'
    res = b'8BIM' + struct.pack('>H', 0x03EE) + b'\0\0' + struct.pack('>I', len(pas)) + pas
    body = head + struct.pack('>I', 0) + struct.pack('>I', len(res)) + res + struct.pack('>I', 0)
    return body + struct.pack('>H', 0) + b''.join(np.asarray(p, np.uint8).tobytes() for p in planes)


# 1 -------------------------------------------------------------------------
@pytest.mark.parametrize('fabric', ['#FFFFFF', '#1E2A4A', '#F4E8CC'])
def test_binary_masks_are_byte_identical_in_proof_tiff_and_svg(fabric):
    img = _three_color()
    pal = [p.hex for p in analyze(img, 3)]
    layers = separation_create(reduce(img, 3), pal, cleanup=0)
    pairs = [(m, hx) for hx, m, _ in layers]
    alphas = [ink_proof.alpha_of(m) for m, _ in pairs]
    assert all(set(np.unique(a)) <= {0, 255} for a in alphas)
    # proof: identical bytes to the old solid-paint proof
    assert print_preview(pairs, img.size, fabric).tobytes() == _legacy_preview(pairs, img.size, fabric).tobytes()
    # TIFF film: still 255 - alpha
    for m, a in zip([m for m, _ in pairs], alphas):
        assert to_print_ready(m).tobytes() == (255 - a).astype(np.uint8).tobytes()
    # SVG: the threshold mask is the old alpha > 127 mask, so the SVG text is the same
    new = [(hx, ink_proof.is_ink(a)) for (_, hx), a in zip(pairs, alphas)]
    old = [(hx, a > 127) for (_, hx), a in zip(pairs, alphas)]
    assert vector.build_svg(new, img.size) == vector.build_svg(old, img.size)
    assert ink_proof.tint_warning([m for m, _ in pairs]) is None


def test_binary_export_package_proof_matches_the_old_proof():
    """The sample floral through the real API: the package's proof.png is
    the old proof pixel for pixel, on a dark cloth with an under-base."""
    c = TestClient(app)
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 5}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    body = {'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers],
            'fabric': '#1E2A4A', 'underbase': True, 'vector': True}
    z = c.post('/api/export/package', json=body)
    assert z.status_code == 200
    from app.core import store
    ordered = sorted(layers, key=lambda l: -separation.press_lightness(l['color']))
    masks = [store.load(l['id']) for l in ordered]
    want = _legacy_preview(list(zip(masks, [l['color'] for l in ordered])), masks[0].size, '#1E2A4A')
    with ZipFile(BytesIO(z.content)) as zf:
        got = Image.open(BytesIO(zf.read('proof.png'))).convert('RGB')
    assert np.array_equal(np.asarray(got), np.asarray(want))


# 2 -------------------------------------------------------------------------
def test_half_tint_is_a_tint_in_the_proof_kept_on_film_and_in_the_svg():
    ink, fabric = '#C0392B', '#FFFFFF'
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 128
    m = _mask(a)
    px = np.asarray(print_preview([(m, ink)], m.size, fabric))[10, 10].astype(float)
    f, c, v = np.array(hex_rgb(fabric), float), np.array(hex_rgb(ink), float), 128 / 255
    # the linear blend (1 - v) * cloth + v * ink, exact within rounding
    assert np.abs(px - ((1 - v) * f + v * c)).max() <= 0.5
    # "about halfway between fabric and ink (within 2 per channel)" (R-0009 test 2)
    assert np.abs(px - (f + c) / 2).max() <= 2
    # a tint: strictly between the cloth and the ink on every channel that differs, not solid ink
    for j in range(3):
        if f[j] != c[j]:
            assert min(f[j], c[j]) < px[j] < max(f[j], c[j])
    # and the same on a coloured cloth
    dark = np.asarray(print_preview([(m, ink)], m.size, '#1E2A4A'))[10, 10].astype(float)
    assert np.abs(dark - (np.array(hex_rgb('#1E2A4A'), float) + c) / 2).max() <= 2
    # TIFF keeps the tint
    assert int(np.asarray(to_print_ready(m))[10, 10]) in (127, 128)
    # SVG includes the region at threshold >= 128
    assert ink_proof.INK_THRESHOLD == 128
    assert vector.path_data(ink_proof.is_ink(a))


# 3 -------------------------------------------------------------------------
def test_light_tint_is_light_in_the_proof_kept_on_film_left_out_of_svg_and_warned():
    ink, fabric = '#1A1A1A', '#FFFFFF'
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 60
    m = _mask(a)
    px = np.asarray(print_preview([(m, ink)], m.size, fabric))[10, 10].astype(float)
    f, c = np.array(hex_rgb(fabric), float), np.array(hex_rgb(ink), float)
    assert np.abs(px - f).sum() < np.abs(px - c).sum()       # nearer the cloth than the ink: a light tint
    assert not np.array_equal(px, c)                         # and certainly not solid ink (the old proof)
    assert int(np.asarray(to_print_ready(m))[10, 10]) == 195
    assert not ink_proof.is_ink(a).any() and vector.path_data(ink_proof.is_ink(a)) == ''
    w = ink_proof.tint_warning([m])
    assert w and not w['blocking'] and w['screens'] == 1 and w['of'] == 1
    assert w['tint_pct'] == 100.0 and w['below_threshold_pct'] == 100.0
    assert '1 of 1 screens contain tints/soft edges' in w['message'] and 'SVG' in w['message']


# 4 -------------------------------------------------------------------------
def test_overlapping_screens_composite_in_order_without_a_hard_jump():
    ramp = np.tile(np.arange(256, dtype=np.uint8), (2, 1))
    yellow, blue = '#FFFF00', '#0000FF'
    m1, m2 = _mask(ramp), _mask(ramp)
    out = np.asarray(print_preview([(m1, yellow), (m2, blue)], m1.size, '#FFFFFF')).astype(int)[0]
    # in order: the linear blend applied screen after screen, rounded after each
    p = np.full((256, 3), 255.0); a = np.arange(256)[:, None]
    for col in (yellow, blue):
        p = np.floor(((255 - a) * p + a * np.array(hex_rgb(col), float)) / 255 + 0.5)
    assert np.array_equal(out, p.astype(int))
    # no jump: alpha 1 is (almost) cloth, and no step between neighbouring alphas is big
    assert (out[1] >= 250).all()
    assert np.abs(np.diff(out, axis=0)).max() <= 8
    # order matters: blue on top ends blue, yellow on top ends yellow
    top_yellow = np.asarray(print_preview([(m2, blue), (m1, yellow)], m1.size, '#FFFFFF'))[0, 255]
    assert tuple(out[255]) == tuple(hex_rgb(blue)) and tuple(top_yellow) == tuple(hex_rgb(yellow))


# 5 -------------------------------------------------------------------------
def test_upload_preview_matches_export_proof_for_a_tinted_psd():
    c = TestClient(app)
    h, w = 24, 32
    film1 = np.full((h, w), 255, np.uint8); film1[:, :16] = 0; film1[:, 16:20] = 127   # solid + 50% rim
    film2 = np.full((h, w), 255, np.uint8); film2[8:20, 10:28] = 195                   # a light tint, overlapping
    up = c.post('/api/image/upload', files={'file': ('b.psd', _multichannel_psd([film1, film2], ['1 RED', '2 NAVY']),
                                                     'image/vnd.adobe.photoshop')})
    assert up.status_code == 200, up.text
    meta = up.json()
    assert len(meta['layers']) == 2
    warn = meta['tint_warning']
    assert warn and warn['screens'] == 2 and not warn['blocking']
    uploaded = np.asarray(Image.open(BytesIO(c.get(meta['url']).content)).convert('RGB'))
    body = {'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in meta['layers']]}
    pv = c.post('/api/separation/preview', json={'layers': [{'id': l['id'], 'color': l['color']} for l in meta['layers']]}).json()
    shown = np.asarray(Image.open(BytesIO(c.get(pv['url']).content)).convert('RGB'))
    z = c.post('/api/export/package', json=body)
    assert z.status_code == 200
    # the package orders screens lightest first; the upload stacks them in file order.
    # Same order here (red is lighter than navy), so all three must be the same pixels.
    with ZipFile(BytesIO(z.content)) as zf:
        exported = np.asarray(Image.open(BytesIO(zf.read('proof.png'))).convert('RGB'))
    assert np.array_equal(uploaded, exported)
    assert np.array_equal(shown, exported)
    # and a tint is drawn as a tint, not as solid ink
    assert tuple(exported[2, 17]) != tuple(hex_rgb(meta["layers"][0]["color"]))


# 6 -------------------------------------------------------------------------
def test_one_threshold_drives_svg_counts_and_warning_together(monkeypatch):
    import inspect
    from app.routes import export as export_routes, images as image_routes
    # nothing in the export / upload paths keeps its own cut-off any more
    for mod in (export_routes, image_routes):
        src = inspect.getsource(mod)
        assert '> 127' not in src and '>127' not in src and '> 0).mean' not in src
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 128
    m = _mask(a)
    layer = [('A', '#000000', m, None, 0)]
    assert vector.path_data(ink_proof.is_ink(a)) and ink_proof.tint_warning([m])['below_threshold_pct'] == 0.0
    assert image_routes._overlap(layer) == 0.0
    monkeypatch.setattr(ink_proof, 'INK_THRESHOLD', 129)
    assert vector.path_data(ink_proof.is_ink(a)) == ''               # the SVG drops it ...
    w = ink_proof.tint_warning([m])
    assert w['below_threshold_pct'] == 100.0 and w['threshold'] == 129   # ... and the warning says so
    assert image_routes._overlap(layer) == 0.0                     # nothing counted as ink at all


def test_threshold_is_configurable_from_the_environment(monkeypatch):
    import importlib
    monkeypatch.setenv('LOOMLAB_INK_THRESHOLD', '200')
    mod = importlib.reload(ink_proof)
    try:
        assert mod.INK_THRESHOLD == 200
        assert not mod.is_ink(np.array([199])).any() and mod.is_ink(np.array([200])).all()
    finally:
        monkeypatch.delenv('LOOMLAB_INK_THRESHOLD')
        importlib.reload(ink_proof)
    assert ink_proof.INK_THRESHOLD == 128


# R-0009 addendum: plates, thumbnails, job sheet and README ---------------
def test_plates_and_thumbnails_match_the_proof_for_tinted_screens():
    """The per-plate PNG and the job-sheet / chip thumbnails use the proof's
    own blend, so for a bureau's tinted screens they show the same pixels."""
    ramp = np.tile(np.arange(256, dtype=np.uint8), (8, 1))
    m1, m2 = _mask(ramp), _mask(ramp[:, ::-1].copy())
    for fabric in ('#FFFFFF', '#1E2A4A'):
        assert separation.plate(m1, '#C0392B', fabric).tobytes() == \
            ink_proof.proof([(m1, '#C0392B')], m1.size, fabric).tobytes()
        stack = [(m1, '#FFD400'), (m2, '#1E2A4A')]
        # at or under thumbnail size nothing is shrunk: the thumbnail IS the proof
        assert separation.preview_thumb(stack, fabric, max_side=512).tobytes() == \
            print_preview(stack, m1.size, fabric).tobytes()
    # shrunk, it is the proof of the shrunk screens
    big = _mask(np.tile(np.arange(256, dtype=np.uint8), (64, 4)))
    small = separation.thumb(big, 100)
    assert separation.preview_thumb([(big, '#C0392B')], '#FFFFFF', 100).tobytes() == \
        ink_proof.proof([(small, '#C0392B')], small.size, '#FFFFFF').tobytes()


def test_tint_line_names_each_tinted_screen_and_its_share():
    hard = np.zeros((10, 10), np.uint8); hard[:, :5] = 255
    soft = np.zeros((10, 10), np.uint8); soft[:, :4] = 255; soft[:, 4] = 128       # 10 of 50 ink px tinted
    light = np.zeros((10, 10), np.uint8); light[2:8, 2:8] = 60                     # all tinted
    named = [('1 RED', _mask(soft)), ('2 GOLD', _mask(hard)), ('3 NAVY', _mask(light))]
    assert ink_proof.screen_tints(named) == [('1 RED', 20.0), ('3 NAVY', 100.0)]
    line = ink_proof.tint_line(named)
    assert '\n' not in line
    assert '1 RED (20%)' in line and '3 NAVY (100%)' in line and 'GOLD' not in line
    assert ink_proof.tint_line([('1 GOLD', _mask(hard))]) is None


def _psd_package(c, films, names, **extra):
    up = c.post('/api/image/upload', files={'file': ('b.psd', _multichannel_psd(films, names),
                                                     'image/vnd.adobe.photoshop')})
    assert up.status_code == 200, up.text
    layers = up.json()['layers']
    z = c.post('/api/export/package', json={'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']}
                                                       for l in layers]} | extra)
    assert z.status_code == 200, z.text
    return ZipFile(BytesIO(z.content))


def test_tinted_package_names_the_tinted_screens_in_readme_and_job_sheet(monkeypatch):
    from app.routes import export as export_routes
    seen = []
    real = export_routes.build_job_sheet
    monkeypatch.setattr(export_routes, 'build_job_sheet', lambda *a, **k: seen.append(k.get('tints')) or real(*a, **k))
    c = TestClient(app)
    h, w = 24, 32
    film1 = np.full((h, w), 255, np.uint8); film1[:, :16] = 0; film1[:, 16:20] = 127   # 64 of 320 tinted = 20%
    film2 = np.full((h, w), 255, np.uint8); film2[:, 24:] = 0                          # hard
    with _psd_package(c, [film1, film2], ['1 RED', '2 NAVY']) as zf:
        readme = zf.read('README.txt').decode()
        assert 'job-sheet.png' in zf.namelist()
    lines = [ln for ln in readme.splitlines() if 'Tints/soft edges' in ln]
    assert len(lines) == 1                                   # ONE line
    assert 'RED (20%)' in lines[0] and 'NAVY' not in lines[0]
    assert seen == [lines[0]]          # the same line goes to the job sheet (drawn: see the next tests)


def test_hard_edged_job_sheet_and_readme_carry_no_tint_line():
    c = TestClient(app)
    film1 = np.full((24, 32), 255, np.uint8); film1[:, :16] = 0
    with _psd_package(c, [film1], ['1 RED']) as zf:
        assert 'Tints' not in zf.read('README.txt').decode()


def test_job_sheet_draws_the_tint_line_and_nothing_without_it():
    from app.core.jobsheet import build_job_sheet
    kw = dict(title='t', print_size='1 x 1 in', cloth='#FFFFFF', underbase=False, dpi=300)
    rows = [(1, 'RED', '#C0392B', 50.0, None)]
    plain = np.asarray(build_job_sheet(rows, None, **kw))
    none = np.asarray(build_job_sheet(rows, None, tints=None, **kw))
    warned = np.asarray(build_job_sheet(rows, None, tints='Tints/soft edges on 1 RED (20%) of each ...', **kw))
    assert np.array_equal(plain, none)
    assert not np.array_equal(plain, warned)
    red = (warned[:, :, 0] > 150) & (warned[:, :, 1] < 100) & (warned[:, :, 2] < 80)
    assert red.any()                                         # drawn in the warning colour


# R-0015 #1: figures that weigh ink use the real ink amount ----------------
def test_coverage_is_the_real_ink_amount_not_a_threshold():
    for alpha, want in ((64, 25.1), (125, 49.0), (128, 50.2), (153, 60.0), (191, 74.9), (255, 100.0)):
        assert ink_proof.coverage_pct(np.full((10, 10), alpha, np.uint8)) == want
    hard = np.zeros((10, 10), np.uint8); hard[:3] = 255
    assert ink_proof.coverage_pct(hard) == round(float((hard > 127).mean() * 100), 1) == 30.0


def test_tinted_psd_coverage_and_quote_follow_the_ink_on_the_film(monkeypatch):
    """A flat 25% / 50% / 60% tint screen counts as about that much ink at
    upload (what the quote is priced from) and in the package's job sheet and
    film labels; never 0 for a screen that prints, never solid for a tint."""
    from app.routes import export as export_routes
    c = TestClient(app)
    h, w = 20, 40
    films = [np.full((h, w), 255 - a, np.uint8) for a in (64, 128, 153)]       # full-page tints
    hard = np.full((h, w), 255, np.uint8); hard[:, :10] = 0                      # 25% hard
    up = c.post('/api/image/upload', files={'file': ('t.psd', _multichannel_psd(films + [hard], ['A', 'B', 'C', 'D']),
                                                     'image/vnd.adobe.photoshop')})
    assert up.status_code == 200, up.text
    layers = up.json()['layers']
    cov = [l['coverage'] for l in layers]
    assert cov == [25.1, 50.2, 60.0, 25.0]
    # the quote: a 25% tint costs about the ink of a 25% hard screen, and a 50% tint half of a solid one
    def ink(cv):
        return c.post('/api/quote', json={'meters': 100, 'inks': [{'hex': '#C0392B', 'coverage': cv}]}).json()['ink_kg']
    assert ink(cov[0]) > 0 and abs(ink(cov[0]) - ink(cov[3])) / ink(cov[3]) < 0.01
    assert abs(ink(cov[1]) - ink(100) / 2) / ink(100) < 0.01
    # the package: job-sheet rows carry the same coverage
    rows = []
    real = export_routes.build_job_sheet
    monkeypatch.setattr(export_routes, 'build_job_sheet', lambda r, *a, **k: rows.append(r) or real(r, *a, **k))
    z = c.post('/api/export/package', json={'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']}
                                                       for l in layers]})
    assert z.status_code == 200, z.text
    got = {name: cv for _, name, _, cv, _ in rows[0]}
    assert got == {'A': 25.1, 'B': 50.2, 'C': 60.0, 'D': 25.0}


# R-0015 #3: hard overlapping PSD screens stay hard at a print width --------
def test_hard_overlapping_psd_stays_hard_when_resized_and_raises_no_tint_line():
    c = TestClient(app)
    h, w = 40, 60
    film1 = np.full((h, w), 255, np.uint8); film1[5:30, 5:40] = 0
    film2 = np.full((h, w), 255, np.uint8); film2[15:35, 30:55] = 0              # overlaps film1 (a trap)
    with _psd_package(c, [film1, film2], ['1 RED', '2 NAVY'], width_in=1.0, dpi=300) as zf:
        tiffs = [n for n in zf.namelist() if n.startswith('screens/')]
        assert len(tiffs) == 2
        for n in tiffs:
            film = np.asarray(Image.open(BytesIO(zf.read(n))).convert('L'))
            assert film.shape[1] >= 300
            # the film area (away from the label box in the corner) is pure black and white
            body = film[: film.shape[0] * 2 // 3]
            assert set(np.unique(body)) <= {0, 255}, n
        assert 'Tints' not in zf.read('README.txt').decode()


def test_resize_keeps_hard_channels_hard_and_soft_channels_soft():
    a = np.zeros((20, 30), np.uint8); a[4:16, 4:20] = 255
    b = np.zeros((20, 30), np.uint8); b[8:18, 15:28] = 255                       # overlap: not exclusive
    s = np.zeros((20, 30), np.uint8); s[2:18, 2:28] = 100                         # a bureau's tint
    out = separation.resize_masks([_mask(a), _mask(b), _mask(s)], (90, 60))
    oa, ob, os_ = (ink_proof.alpha_of(m) for m in out)
    assert set(np.unique(oa)) == {0, 255} and set(np.unique(ob)) == {0, 255}
    assert abs(oa.mean() / 255 - a.mean() / 255) < 0.02                          # same shape, 3x
    assert ((os_ > 0) & (os_ < 255)).any()                                        # the tint stays a tint


# R-0015 #4: the operator warning in Hinglish too ------------------------------
def test_tint_warning_carries_hinglish():
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 60
    w = ink_proof.tint_warning([_mask(a)])
    assert w['hi'].startswith('1 me se 1 screens me tint/soft edge hai')
    assert 'Engraver' in w['hi'] and 'SVG outline me nahi' in w['hi']
    assert 'coverage figures' not in w['message']            # coverage now counts tints


# R-0022 N1 / R-0023 b: the white under-base is priced from its own film -----
def _upload_psd(c, films, names):
    up = c.post('/api/image/upload', files={'file': ('u.psd', _multichannel_psd(films, names),
                                                     'image/vnd.adobe.photoshop')})
    assert up.status_code == 200, up.text
    return up.json()['layers']


def test_underbase_quote_follows_the_film_for_a_tinted_psd(monkeypatch):
    from app.routes import export as export_routes
    c = TestClient(app)
    h, w = 40, 60
    tint = np.full((h, w), 255 - 64, np.uint8)                                   # full-page 25% tint
    hard = np.full((h, w), 255, np.uint8); hard[:, :15] = 0                       # 25% hard
    layers = _upload_psd(c, [tint, hard], ['1 TINT', '2 NAVY'])
    inks = [{'id': l['id'], 'name': l['name'], 'hex': l['color'], 'coverage': l['coverage']} for l in layers]
    q = c.post('/api/quote', json={'meters': 1000, 'underbase': True, 'inks': inks}).json()
    ub_row = q['inks'][0]
    assert ub_row['name'] == 'White under-base'
    # what the package's under-base film prints (its job-sheet row) ...
    rows = []
    real = export_routes.build_job_sheet
    monkeypatch.setattr(export_routes, 'build_job_sheet', lambda r, *a, **k: rows.append(r) or real(r, *a, **k))
    z = c.post('/api/export/package', json={'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']}
                                                       for l in layers], 'fabric': '#1E2A4A', 'underbase': True})
    assert z.status_code == 200, z.text
    film_cov = next(cv for order, _, _, cv, _ in rows[0] if order == 0)
    with ZipFile(BytesIO(z.content)) as zf:
        ub_film = np.asarray(Image.open(BytesIO(zf.read(next(n for n in zf.namelist()
                                                              if n.startswith('screens/0'))))).convert('L'))
    assert film_cov > 90                                      # solid white under the whole tint
    # ... is what the quote charges, not the inks' sum (25.1 + 25 = 50.1)
    assert abs(ub_row['coverage'] - film_cov) < 0.06
    assert sum(i['coverage'] for i in inks) < 51
    assert (ub_film[: h // 2] == 0).any()                     # the film itself: still a hard white base
    # without the ids (an old job, an auto job) the quote falls back to the sum
    q_old = c.post('/api/quote', json={'meters': 1000, 'underbase': True,
                                       'inks': [{k: v for k, v in i.items() if k != 'id'} for i in inks]}).json()
    assert q_old['inks'][0]['coverage'] == round(sum(i['coverage'] for i in inks), 2)
    assert q['total'] > q_old['total']


def test_underbase_quote_from_ids_matches_the_film_on_a_hard_design():
    from app.separation_engine.engine import underbase
    c = TestClient(app)
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 4}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    inks = [{'id': l['id'], 'name': l['name'], 'hex': l['color'], 'coverage': l['coverage']} for l in layers]
    q = c.post('/api/quote', json={'meters': 100, 'underbase': True, 'inks': inks}).json()
    from app.core import store
    film = underbase([store.load(l['id']) for l in layers], 1)
    assert q['inks'][0]['coverage'] == ink_proof.underbase_coverage(film)
    assert q['inks'][0]['coverage'] <= min(100, sum(i['coverage'] for i in inks)) + 0.01


# R-0022 N2: the tint line is never cut off on the job sheet ----------------
def test_job_sheet_tint_line_wraps_instead_of_being_cut():
    from PIL import ImageDraw
    from app.core.jobsheet import PAGE, MARGIN, _fit_lines, build_job_sheet
    named = [(f'{i} {n}', None) for i, n in enumerate(['RED', 'NAVY', 'GOLD', 'LEAF GREEN', 'ROSE', 'SKY'], 1)]
    text = ('Tints/soft edges on ' + ', '.join(f'{lab} (37.5%)' for lab, _ in named)
            + " of each screen's ink pixels: confirm with your engraver that they will hold, or flatten to hard edges. "
            + ink_proof.DARK_CLOTH_NOTE)
    d = ImageDraw.Draw(Image.new('RGB', PAGE, 'white'))
    width = PAGE[0] - 2 * MARGIN
    font, size, lines = _fit_lines(d, text, width)
    assert 1 < len(lines) <= 3
    assert ' '.join(lines) == text                                  # every word is there
    assert all(d.textlength(ln, font=font) <= width for ln in lines)
    kw = dict(title='t', print_size='1 x 1 in', cloth='#1E2A4A', underbase=True, dpi=300)
    rows = [(1, 'RED', '#C0392B', 50.0, None)]
    one = np.asarray(build_job_sheet(rows, None, tints='Tints/soft edges on 1 RED (20%).', **kw))
    many = np.asarray(build_job_sheet(rows, None, tints=text, **kw))
    red = lambda a: np.where(((a[:, :, 0] > 150) & (a[:, :, 1] < 100) & (a[:, :, 2] < 80)).any(1))[0]
    # the wrapped block takes more rows of red text than the one-line one
    assert red(many).max() - red(many).min() > red(one).max() - red(one).min() + 40


# R-0023 a/d: on dark cloth with an under-base the inks sit on white ---------
@pytest.mark.parametrize('alpha', [128, 64])
def test_dark_cloth_tint_with_underbase_proofs_over_white(alpha):
    c = TestClient(app)
    h, w = 40, 60
    ink, navy = '#C0392B', '#1E2A4A'
    tint = np.full((h, w), 255, np.uint8); tint[5:35, 10:50] = 255 - alpha     # a tinted patch on bare cloth
    layers = _upload_psd(c, [tint], ['1 RED'])
    lay = [{'id': l['id'], 'name': l['name'], 'color': ink} for l in layers]
    v = alpha / 255
    on_white = (1 - v) * np.array(hex_rgb(ink_proof.UNDERBASE_WHITE), float) + v * np.array(hex_rgb(ink), float)
    on_cloth = (1 - v) * np.array(hex_rgb(navy), float) + v * np.array(hex_rgb(ink), float)
    z = c.post('/api/export/package', json={'layers': lay, 'fabric': navy, 'underbase': True})
    assert z.status_code == 200, z.text
    with ZipFile(BytesIO(z.content)) as zf:
        pr = np.asarray(Image.open(BytesIO(zf.read('proof.png'))).convert('RGB')).astype(float)
        film = np.asarray(Image.open(BytesIO(zf.read(next(n for n in zf.namelist() if 'RED' in n and n.endswith('.tif'))))).convert('L'))
        readme = zf.read('README.txt').decode()
    mid = pr[h // 2, w // 2]                                   # inside the (1 px choked) base
    assert np.abs(mid - on_white).max() <= 2                    # (1-v)*white + v*ink: 50% is halfway
    assert np.abs(pr[5, 30] - on_cloth).max() <= 2             # the 1 px choked rim (top edge): no base, on the cloth
    assert tuple(pr[0, 0]) == tuple(hex_rgb(navy))              # bare cloth stays the cloth
    # the film is unchanged: 255 - alpha on the patch
    assert (film == 255 - alpha).sum() >= 30 * 40             # (the TIFF also carries its reg-mark margin)
    z0 = c.post('/api/export/package', json={'layers': lay, 'fabric': navy})
    with ZipFile(BytesIO(z0.content)) as zf:
        film0 = np.asarray(Image.open(BytesIO(zf.read(next(n for n in zf.namelist() if 'RED' in n and n.endswith('.tif'))))).convert('L'))
    assert np.array_equal(film, film0)                         # the base changes the proof, never the ink's film
    # the screen preview draws the same, and without the base it is on the cloth
    body = {'layers': [{'id': l['id'], 'color': ink} for l in layers], 'fabric': navy}
    shown = c.post('/api/separation/preview', json=body | {'underbase': True}).json()
    plain = c.post('/api/separation/preview', json=body).json()
    s = np.asarray(Image.open(BytesIO(c.get(shown['url']).content)).convert('RGB')).astype(float)
    p = np.asarray(Image.open(BytesIO(c.get(plain['url']).content)).convert('RGB')).astype(float)
    assert np.array_equal(s, pr)
    assert np.abs(p[h // 2, w // 2] - on_cloth).max() <= 2
    # R-0023 c: the dark-cloth line, in the README (and the job sheet's tint block)
    assert ink_proof.DARK_CLOTH_NOTE in readme.splitlines()


def test_hard_design_proof_is_unchanged_by_the_underbase():
    from app.separation_engine.engine import underbase
    img = _three_color()
    pal = [p.hex for p in analyze(img, 3)]
    pairs = [(m, hx) for hx, m, _ in separation_create(reduce(img, 3), pal, cleanup=0)]
    for choke in (0, 1, 2):
        ub = underbase([m for m, _ in pairs], choke)
        assert print_preview(pairs, img.size, '#1E2A4A', ub).tobytes() == \
            print_preview(pairs, img.size, '#1E2A4A').tobytes()


def test_dark_cloth_note_in_warning_and_only_with_an_underbase_in_the_readme():
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 128
    w = ink_proof.tint_warning([_mask(a)])
    assert ink_proof.DARK_CLOTH_NOTE in w['message'] and ink_proof.DARK_CLOTH_NOTE_HI in w['hi']
    c = TestClient(app)
    layers = _upload_psd(c, [np.full((20, 30), 127, np.uint8)], ['1 RED'])
    lay = [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers]
    z = c.post('/api/export/package', json={'layers': lay})
    with ZipFile(BytesIO(z.content)) as zf:
        readme = zf.read('README.txt').decode()
    assert 'Tints/soft edges' in readme and ink_proof.DARK_CLOTH_NOTE not in readme
