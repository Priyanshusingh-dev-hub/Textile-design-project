"""The benchmark: a folder of designs in, a report a mill can read out."""
import csv
import json

import numpy as np
from PIL import Image, ImageDraw

from app import benchmark


def _flat(path, colours=('#F4ECD8', '#8A1C1C', '#1B3A6B'), smooth=True):
    """The design (anti-aliased, as artwork is) or, smooth=False, an operator's
    hand separation of it: the same shapes in flat inks, no in-between pixels."""
    big = Image.new('RGB', (1600, 1000), colours[0]); d = ImageDraw.Draw(big)
    d.ellipse([150, 150, 800, 800], fill=colours[1]); d.rectangle([950, 200, 1450, 800], fill=colours[2])
    big.resize((800, 500), Image.LANCZOS if smooth else Image.NEAREST).save(path)


def test_designs_are_paired_with_the_operators_version(tmp_path):
    for name in ('a.png', 'a.operator.png', 'B.JPG', 'notes.txt', 'c.tif'):
        (tmp_path / name).write_bytes(b'x')
    got = [(d.name, o.name if o else None) for d, o in benchmark.find_designs(tmp_path)]
    assert got == [('B.JPG', None), ('a.png', 'a.operator.png'), ('c.tif', None)]


def test_match_and_ink_count_measure_what_they_say():
    a = Image.new('RGB', (40, 30), '#8A1C1C')
    assert benchmark.image_match(a, a) == (0.0, 100.0)
    b = Image.new('RGB', (80, 60), '#8A1C1C')                  # another size is resized, not failed
    assert benchmark.image_match(a, b)[1] == 100.0
    assert benchmark.image_match(a, Image.new('RGB', (40, 30), '#1B3A6B'))[1] < 20
    two = np.zeros((100, 100, 3), np.uint8); two[:, 50:] = 255; two[0, 0] = (1, 2, 3)   # one stray pixel
    assert benchmark.ink_count(Image.fromarray(two)) == 2


def test_a_folder_runs_end_to_end_into_a_report(tmp_path):
    _flat(tmp_path / 'rose.png')
    _flat(tmp_path / 'rose.operator.png', ('#F4ECD8', '#901818', '#1B3A6B'), smooth=False)   # a shade off
    yy, xx = np.mgrid[0:200, 0:300]
    Image.fromarray(np.stack([xx * .8, yy * 1.2, 255 - xx * .8], -1).clip(0, 255).astype(np.uint8)).save(tmp_path / 'photo.png')
    (tmp_path / 'broken.png').write_bytes(b'not an image')
    out = tmp_path / 'report'
    result = benchmark.run(tmp_path, meters=100, out=out)
    s = result['summary']
    assert s['designs'] == 3 and s['errors'] == 1 and s['auto_ok'] == 1
    assert s['auto_ok_percent'] == 33.3
    assert s['held_by'].get('photographic') == 1
    rose = next(r for r in result['designs'] if r['design'] == 'rose.png')
    assert rose['status'] == 'auto_ok' and rose['operator_inks'] == 3 and rose['quote'] > 0
    assert rose['loomlab_match'] > rose['operator_match'] and s['loomlab_as_good'] == 1
    # the three files a mill opens
    rows = list(csv.DictReader((out / 'report.csv').open(encoding='utf-8-sig')))
    assert [r['design'] for r in rows] == ['broken.png', 'photo.png', 'rose.png']
    assert json.loads((out / 'report.json').read_text())['summary'] == s
    page = (out / 'report.html').read_text(encoding='utf-8')
    assert 'photo-like shading' in page and '1 / 3' in page and 'LoomLab vs operator' in page
