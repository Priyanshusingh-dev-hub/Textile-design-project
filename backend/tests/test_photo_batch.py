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
    res = photo_batch.run(tmp_path, tmp_path / 'out', size=600)
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
    photo_batch.run(tmp_path, tmp_path / 'out', size=450)
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
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450)['rows'][0]
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
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450)['rows'][0]
    assert 'dots_folder' not in r


def test_a_flat_picture_gets_no_dots_version(tmp_path):
    _single(tmp_path)
    r = photo_batch.run(tmp_path, tmp_path / 'out', size=450)['rows'][0]
    assert 'dots_folder' not in r and not (tmp_path / 'out' / 'flower' / 'dots').exists()
