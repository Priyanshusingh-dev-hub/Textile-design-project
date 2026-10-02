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
