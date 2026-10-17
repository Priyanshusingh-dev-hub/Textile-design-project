"""Tests for edge geometry quality: verifying uniform small staircase steps (no large 2x2, 2x3, 3x5 blocks),
recombination of plates, exact dimensions, and flat palette colours."""
import json
import os
import cv2
import numpy as np
from PIL import Image
import pytest

from textile import cli, edges, number


def test_45_degree_diagonal_staircase_steps_bounded_and_uniform():
    """A 45-degree diagonal cleaned at scale 2.44 should produce uniform 1-pixel steps,
    with max step <= 2 and no large 3+ pixel staircase runs."""
    y, x = np.mgrid[:100, :100]
    idx = (y >= x).astype(np.uint8)
    out, rep = edges.clean(idx, scale=2.44, strength=2)

    xs = []
    for r in range(out.shape[0]):
        row_trans = np.where(out[r, :-1] != out[r, 1:])[0]
        xs.append(row_trans[0] if len(row_trans) == 1 else None)
    valid = [x for x in xs if x is not None]
    assert len(valid) > 200

    diffs = [abs(valid[i + 1] - valid[i]) for i in range(len(valid) - 1)]
    # Along 45 degrees, step size must never exceed 2 pixels, and >= 95% should be 1 pixel
    assert max(diffs) <= 2
    one_ratio = sum(1 for d in diffs if d == 1) / len(diffs)
    assert one_ratio >= 0.95


def test_slanted_diagonal_staircase_steps_bounded():
    """A slanted diagonal (slope 0.5: x = 2y) at scale 2.44 should produce uniform 2-pixel steps,
    with max step <= 2 and no large blocks."""
    y, x = np.mgrid[:100, :100]
    idx = (y >= 0.5 * x).astype(np.uint8)
    out, rep = edges.clean(idx, scale=2.44, strength=2)

    xs = []
    # Hypotenuse runs from y=0 to y=50 in 1x space, so y=0 to y=122 in output space
    for r in range(int(10 * 2.44), int(48 * 2.44)):
        row_trans = np.where(out[r, :-1] != out[r, 1:])[0]
        xs.append(row_trans[0] if len(row_trans) == 1 else None)
    valid = [x for x in xs if x is not None]
    assert len(valid) > 80

    diffs = [abs(valid[i + 1] - valid[i]) for i in range(len(valid) - 1)]
    assert max(diffs) <= 2
    two_ratio = sum(1 for d in diffs if d == 2) / len(diffs)
    assert two_ratio >= 0.95


def test_raw_contours_scale_smoothly_without_nearest_neighbor_blocks():
    """Contours categorized as raw (area < 24) should scale directly at output resolution
    without stamping nearest-neighbor 2x2 or 3x3 blocks."""
    idx = np.zeros((40, 40), np.uint8)
    # A small triangle with area ~18
    cv2.fillPoly(idx, [np.array([[5, 5], [11, 5], [5, 13]], np.int32)], 1)
    scale = 2.44
    out, rep = edges.clean(idx, scale=scale, strength=2)
    assert rep['kept_as_is'] >= 1

    # Check right boundary of the triangle: hypotenuse should not have vertical walls of 4+ rows
    r_start = int(round(5 * scale))
    r_end = int(round(13 * scale))
    xs = []
    for r in range(r_start + 1, r_end - 1):
        pixels = np.where(out[r] == 1)[0]
        if len(pixels):
            xs.append(pixels[-1])
    diffs = [abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
    assert max(diffs) <= 2


def test_number_package_plates_recombine_exactly_into_final_tif(tmp_path):
    """Running number on a design produces plates in package/ that recombine exactly
    into the composite TIFF, with exact dimensions and color count <= --colors."""
    src = tmp_path / 'diag_test.png'
    # Create clean 3-color synthetic design
    img = np.full((120, 120, 3), [240, 230, 210], dtype=np.uint8)
    cv2.circle(img, (60, 60), 30, [40, 90, 60], -1)
    cv2.fillPoly(img, [np.array([[10, 10], [50, 10], [10, 50]], np.int32)], [20, 20, 90])
    Image.fromarray(img).save(src)

    out_dir = tmp_path / 'out'
    res = cli.main(['number', str(src), '--out', str(out_dir), '--name', 'test_diag',
                    '--size', '300', '--colors', '4', '--dpi', '300'])
    assert res == 0

    # Verify report and dimensions
    report_file = out_dir / 'test_diag_number.json'
    assert report_file.exists()
    with open(report_file, encoding='utf-8') as f:
        rep = json.load(f)
    assert rep['size_px'] == [300, 300]
    assert len(rep['inks']) <= 4

    # Verify final TIFF in package
    pkg_dir = out_dir / 'package'
    final_tif_path = pkg_dir / 'test_diag_final_300px_300dpi.tif'
    assert final_tif_path.exists()
    final_tif = np.array(Image.open(final_tif_path))
    assert final_tif.shape == (300, 300, 3)

    # Verify each pixel is flat palette color
    unique_colors = np.unique(final_tif.reshape(-1, 3), axis=0)
    assert len(unique_colors) <= 4

    # Verify individual channels in zip recombine into the composite
    import glob
    import zipfile
    zips = glob.glob(str(pkg_dir / 'test_diag_colored_channels_*.zip'))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        ch_files = [n for n in zf.namelist() if n.endswith('.png')]
        assert len(ch_files) == len(unique_colors)
        # Recombined image starts empty with background
        recomb = np.zeros((300, 300, 3), dtype=np.uint8)
        for ch_name in sorted(ch_files):
            with zf.open(ch_name) as ch_f:
                ch_img = np.array(Image.open(ch_f).convert('RGBA'))
                alpha = ch_img[..., 3] > 0
                recomb[alpha] = ch_img[alpha, :3]
        assert np.array_equal(recomb, final_tif)
