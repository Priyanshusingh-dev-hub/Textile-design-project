"""One command for every picture in a folder: pairs through the fill judge,
singles through Reduce, then clean edges + the mill package for all of them.
One bad picture is a row, not the end."""
import csv
import json

import cv2
import numpy as np
from PIL import Image

from app import photo_batch


def _pair(folder, name='star'):
    n = 200
    line = np.full((n, n), 255, np.uint8)
    ref = np.zeros((n, n, 3), np.uint8)
    cols = [(200, 40, 40), (40, 150, 60), (40, 60, 190), (235, 225, 205)]
    for k, c in enumerate(cols):
        ref[(k // 2) * n // 2:(k // 2 + 1) * n // 2, (k % 2) * n // 2:(k % 2 + 1) * n // 2] = c
    for a in (line, ref):
        a[n // 2 - 3:n // 2 + 3] = 0
        a[:, n // 2 - 3:n // 2 + 3] = 0
        a[:4] = a[-4:] = 0
        a[:, :4] = a[:, -4:] = 0
    Image.fromarray(line).save(folder / f'{name}_lineart.png')
    Image.fromarray(ref).save(folder / f'{name}_ref.png')


def _single(folder, name='flower'):
    img = np.full((240, 300, 3), (235, 225, 205), np.uint8)
    cv2.circle(img, (110, 120), 60, (190, 50, 60), -1)
    cv2.circle(img, (200, 120), 40, (40, 90, 150), -1)
    cv2.line(img, (20, 30), (280, 40), (30, 30, 30), 2)
    Image.fromarray(img).save(folder / f'{name}.png')


def test_every_picture_gets_the_same_treatment(tmp_path):
    _pair(tmp_path)
    _single(tmp_path)
    (tmp_path / 'broken.png').write_bytes(b'not an image')
    res = photo_batch.run(tmp_path, tmp_path / 'out', size=600, versions=False)
    rows = {r['design']: r for r in res['rows']}
    assert set(rows) == {'star', 'flower', 'broken'}            # the line art is not a design of its own
    assert rows['broken']['status'] == 'error'                  # said, and the others still ran
    for name in ('star', 'flower'):
        r = rows[name]
        assert r['status'] == 'ok' and r['verify'] == 'PASS' and r['dpi'] == 300 and r['size_px'].startswith('600x')
        d = tmp_path / 'out' / name
        assert list(d.glob(f'{name}_final_600*_300dpi.tif')) and list(d.glob(f'{name}_final_600*_300dpi.png'))
        assert (d / f'{name}_compare.png').exists() and (d / f'{name}_report.json').exists()
    assert rows['star']['route'].startswith(('method', 'reduce')) and 'vs Reduce' in rows['star']['why']
    assert rows['flower']['route'] == 'reduce' and rows['flower']['inks'] >= 3
    assert {r['design'] for r in csv.DictReader(open(tmp_path / 'out' / 'summary.csv', encoding='utf-8-sig'))} == set(rows)
    assert json.load(open(tmp_path / 'out' / 'summary.json'))


def test_the_result_is_flat_inks_only(tmp_path):
    _single(tmp_path)
    photo_batch.run(tmp_path, tmp_path / 'out', size=450, versions=False)
    png = next((tmp_path / 'out' / 'flower').glob('flower_final_*.png'))
    a = np.asarray(Image.open(png).convert('RGB'))
    assert len(np.unique(a.reshape(-1, 3), axis=0)) <= 8        # no blended colour from the enlarging


def test_a_photo_like_picture_also_gets_a_dots_version_flat_stays_main(tmp_path):
    import colorsys
    h, w = 220, 300
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.stack(np.vectorize(colorsys.hsv_to_rgb)(xx / w, 0.4 + 0.6 * np.sin(np.pi * yy / h),
                                                     0.35 + 0.65 * yy / h), -1) * 255
    Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).save(tmp_path / 'sky.png')
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450, versions=False)['rows'][0]
    assert r['status'] == 'ok' and r['ceiling'] < 80 and r['dots_seen'] > r['flat_seen']
    assert r['dots_verify'] == 'PASS' and r['dots_note'] in ('ok', 'pattern will show', 'too fine for most mesh')
    assert list((tmp_path / 'out' / 'sky').glob('sky_final_450*_300dpi.tif'))           # flat: the main file
    assert list((tmp_path / 'out' / 'sky' / 'dots').glob('sky_dots_final_450*_300dpi.tif'))


def test_a_smooth_two_colour_shading_is_not_photographic(tmp_path):
    """The app's own rule: a gradient flat inks band acceptably (ceiling >= 80) gets no dots."""
    h, w = 220, 300
    x = np.linspace(0, 1, w)[None, :, None]
    y = np.linspace(0, 1, h)[:, None, None]
    img = (np.array([230, 90, 60]) * (1 - x) + np.array([40, 60, 160]) * x) * (0.6 + 0.4 * y)
    Image.fromarray(img.clip(0, 255).astype(np.uint8)).save(tmp_path / 'band.png')
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450, versions=False)['rows'][0]
    assert 'dots_folder' not in r


def test_a_flat_picture_gets_no_dots_version(tmp_path):
    _single(tmp_path)
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450, versions=False)['rows'][0]
    assert 'dots_folder' not in r and not (tmp_path / 'out' / 'flower' / 'dots').exists()


def test_the_ink_count_can_be_written_in_the_file_name(tmp_path):
    assert photo_batch.inks_in_name('teal_ikat_4inks') == 4 and photo_batch.inks_in_name('rose 6 inks') == 6
    assert photo_batch.inks_in_name('flower') is None and photo_batch.inks_in_name('design2024') is None
    _single(tmp_path, 'flower_2inks')
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=300, versions=False)['rows'][0]
    assert r['inks'] == 2 and 'file name' in r['why']


def test_versions_are_made_side_by_side_to_choose_from(tmp_path):
    _single(tmp_path)
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450)['rows'][0]
    modes = {v['mode'] for v in r['versions']}
    assert {'more', 'distinct'} <= modes and all(v.get('verify') == 'PASS' for v in r['versions'])
    d = tmp_path / 'out' / 'flower'
    assert (d / 'flower_versions.png').exists()
    assert list((d / 'versions' / 'more').glob('flower_more_final_450*_300dpi.tif'))
    assert next(v for v in r['versions'] if v['mode'] == 'more')['inks'] >= r['inks']


def test_the_lattice_version_paints_the_line_arts_lines_on_open_ground_only(tmp_path):
    """A faint cream lattice in the colour image, crisp in the line art: the lattice
    version draws it whole in cream, and the motif's own outline is not painted."""
    from PIL import ImageDraw
    n = 300
    ref = Image.new('RGB', (n, n), (210, 196, 168))
    d = ImageDraw.Draw(ref)
    for x in range(0, n, 60):
        d.line([(x, 0), (x, n)], fill=(234, 229, 211), width=3)          # faint (dE ~9), the AI's lattice
    d.ellipse((110, 110, 190, 190), fill=(178, 28, 41))
    line = Image.new('L', (n, n), 255)
    dl = ImageDraw.Draw(line)
    for x in range(0, n, 60):
        dl.line([(x, 0), (x, n)], fill=0, width=3)
    dl.ellipse((110, 110, 190, 190), outline=0, width=3)
    flat = Image.new('RGB', (n, n), (210, 196, 168))                     # a Reduce that lost the lattice...
    ImageDraw.Draw(flat).ellipse((110, 110, 190, 190), fill=(178, 28, 41))
    flat.putpixel((5, 5), (232, 226, 207))                               # ...but kept one crumb of its colour
    lp = tmp_path / 'line.png'
    line.save(lp)
    out = np.asarray(photo_batch.lattice_from_lineart(flat, ref, lp))
    cream = (out == (232, 226, 207)).all(-1)
    assert cream[:, 59:62].mean() > 0.6                                  # a lattice line, drawn
    import cv2
    red = (out == (178, 28, 41)).all(-1).astype(np.uint8)
    near_motif = cv2.dilate(red, np.ones((7, 7), np.uint8)) > 0
    assert not (cream & near_motif).any()                                # never the motif's outline
