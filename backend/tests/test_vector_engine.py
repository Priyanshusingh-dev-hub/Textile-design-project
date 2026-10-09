import re
import numpy as np
import pytest
from app.vector_engine import engine as vec

def _circle_mask(size=80, cx=40, cy=40, r=30):
    yy, xx = np.mgrid[0:size, 0:size]
    return ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r).astype(np.uint8) * 255

def _square_mask(size=60, x0=15, y0=15, side=30):
    m = np.zeros((size, size), dtype=np.uint8)
    m[y0:y0 + side, x0:x0 + side] = 255
    return m

def _shoelace_area(points):
    x, y = points[:, 0], points[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

def test_marching_squares_finds_one_closed_contour_for_a_circle():
    mask = _circle_mask()
    field = vec.blur_mask(mask, 1.5)
    contours = vec.marching_squares(field, 127.5)
    assert len(contours) == 1
    assert len(contours[0]) >= 20

def test_marching_squares_area_matches_circle_area():
    mask = _circle_mask(r=30)
    field = vec.blur_mask(mask, 1.5)
    contours = vec.marching_squares(field, 127.5)
    area = _shoelace_area(contours[0])
    expected = 3.14159265 * 30 * 30
    assert area == pytest.approx(expected, rel=0.03)

def test_marching_squares_two_shapes_give_two_contours():
    mask = np.zeros((100, 60), dtype=np.uint8)
    mask |= _circle_mask(100, 15, 15, 10)[:, :60] if False else 0
    # build two disjoint circles directly
    yy, xx = np.mgrid[0:100, 0:60]
    a = (xx - 15) ** 2 + (yy - 15) ** 2 <= 10 * 10
    b = (xx - 45) ** 2 + (yy - 80) ** 2 <= 10 * 10
    mask = ((a | b).astype(np.uint8)) * 255
    field = vec.blur_mask(mask, 1.2)
    contours = vec.marching_squares(field, 127.5)
    assert len(contours) == 2

def test_douglas_peucker_reduces_point_count_on_a_straight_ish_line():
    pts = np.array([[float(i), 0.0 if i % 5 else 0.01] for i in range(50)])
    simplified = vec.douglas_peucker(pts, epsilon=0.5)
    assert len(simplified) < len(pts)

def test_simplify_closed_keeps_a_closed_shape_reasonable():
    mask = _circle_mask(r=25)
    field = vec.blur_mask(mask, 1.5)
    contours = vec.marching_squares(field, 127.5)
    simplified = vec.simplify_closed(contours[0], epsilon=0.8)
    assert 8 <= len(simplified) < len(contours[0])

def test_bezier_path_is_well_formed_svg_path_data():
    mask = _circle_mask(r=20)
    field = vec.blur_mask(mask, 1.5)
    contours = vec.marching_squares(field, 127.5)
    simplified = vec.simplify_closed(contours[0], 0.8)
    d = vec.path_to_bezier_d(simplified, corner_angle_deg=32)
    assert d.startswith('M ')
    assert d.endswith('Z')
    assert 'C ' in d

def test_square_mask_produces_sharp_corners_as_line_commands():
    mask = _square_mask()
    field = vec.blur_mask(mask, 0.8)
    contours = vec.marching_squares(field, 127.5)
    simplified = vec.simplify_closed(contours[0], 0.6)
    d = vec.path_to_bezier_d(simplified, corner_angle_deg=32)
    # a square's 4 corners are sharp turns -> should produce straight (L) segments
    assert 'L ' in d

def test_mask_to_path_d_nonempty_for_solid_shape():
    d = vec.mask_to_path_d(_circle_mask())
    assert d.startswith('M ')

def test_mask_to_path_d_empty_for_blank_mask():
    blank = np.zeros((40, 40), dtype=np.uint8)
    d = vec.mask_to_path_d(blank)
    assert d == ''

def test_build_svg_contains_viewbox_and_path_per_layer():
    svg = vec.build_svg([('#FF0000', _circle_mask()), ('#00FF00', _square_mask(size=80))], (80, 80))
    assert '<svg' in svg and 'viewBox="0 0 80 80"' in svg
    assert svg.count('<path') == 2
    assert '#FF0000' in svg and '#00FF00' in svg

def test_build_svg_skips_empty_layers():
    blank = np.zeros((40, 40), dtype=np.uint8)
    svg = vec.build_svg([('#FF0000', blank)], (40, 40))
    assert svg.count('<path') == 0

def test_min_area_drops_noise_specks_but_keeps_real_motifs():
    # one real 30px-radius flower plus a scatter of 1-2px scan-noise dots
    mask = _circle_mask(size=200, cx=100, cy=100, r=30)
    rng = np.random.RandomState(0)
    for _ in range(40):
        x, y = rng.randint(10, 185), rng.randint(10, 185)
        mask[y:y + 3, x:x + 3] = 255  # a few pixels wide, like real scan noise
    field = vec.blur_mask(mask, 1.2)
    contours = vec.marching_squares(field, 127.5)
    big = [c for c in contours if vec._polygon_area(c) >= 12.0]
    small = [c for c in contours if vec._polygon_area(c) < 12.0]
    assert len(big) == 1  # the real flower survives
    assert len(small) >= 1  # at least some noise specks were actually present to filter
    d = vec.mask_to_path_d(mask, blur_radius=1.2, min_area=12.0)
    assert d.count('M ') == 1  # noise specks excluded from the traced path

def test_min_area_zero_keeps_everything():
    mask = _circle_mask(size=200, cx=100, cy=100, r=30)
    mask[5:6, 5:6] = 255  # a single-pixel speck
    d_filtered = vec.mask_to_path_d(mask, blur_radius=1.0, min_area=12.0)
    d_unfiltered = vec.mask_to_path_d(mask, blur_radius=1.0, min_area=0.0)
    assert d_unfiltered.count('M ') >= d_filtered.count('M ')

def test_marching_squares_scales_to_a_large_image_quickly():
    """Regression guard: an earlier implementation looped over every pixel
    of the image in pure Python, which was unusable on real mill-sized
    files. The vectorised classification pass + boundary-only Python loop
    must stay proportional to contour length, not image area."""
    import time
    mask = _circle_mask(size=1600, cx=800, cy=800, r=500)
    field = vec.blur_mask(mask, 1.5)
    start = time.time()
    contours = vec.marching_squares(field, 127.5)
    elapsed = time.time() - start
    assert len(contours) == 1
    assert elapsed < 5.0

def test_shapes_touching_the_image_edge_are_kept():
    """The ground colour and motifs cut by a repeat edge touch the border;
    they used to trace as open contours and vanish from the SVG."""
    half = np.zeros((30, 30), np.uint8); half[:, :15] = 255
    assert vec.mask_to_path_d(half, min_area=0)
    assert vec.mask_to_path_d(np.full((30, 30), 255, np.uint8), min_area=0)

def test_edge_outline_lies_exactly_on_the_tile_border():
    full = np.full((30, 40), 255, np.uint8)
    nums = [float(v) for v in re.findall(r'-?\d+\.\d+', vec.mask_to_path_d(full, min_area=0))]
    xs, ys = nums[0::2], nums[1::2]
    assert min(xs) == 0 and max(xs) == 40 and min(ys) == 0 and max(ys) == 30

def test_paths_register_with_the_pixel_grid():
    sq = np.zeros((30, 30), np.uint8); sq[5:15, 5:15] = 255     # covers 5..15 in SVG units
    nums = [float(v) for v in re.findall(r'-?\d+\.\d+', vec.mask_to_path_d(sq, blur_radius=0.6, min_area=0))]
    xs = nums[0::2]
    assert abs((min(xs) + max(xs)) / 2 - 10) < 0.2

def test_round_shapes_trace_as_curves_not_polygons():
    for r in (25, 60):
        d = vec.mask_to_path_d(_circle_mask(size=200, cx=100, cy=100, r=r), 1.9, 1.2, 45, 0)
        assert d.count('C ') > 0 and d.count('L ') == 0, (r, d)
    small = vec.mask_to_path_d(_circle_mask(size=200, cx=100, cy=100, r=12), 1.9, 1.2, 45, 0)
    assert small.count('C ') > small.count('L ')     # a tiny dot is mostly curve too

def test_closed_path_has_no_zero_length_closing_segment():
    d = vec.mask_to_path_d(_circle_mask(size=120, cx=60, cy=60, r=40), min_area=0)
    # endpoint of M and of every L/C command, in order: no segment may start
    # where it ends (the old duplicated start point drew a loop there)
    ends = [re.findall(r'-?\d+\.\d+,-?\d+\.\d+', cmd)[-1] for cmd in re.findall(r'[MLC][^MLCZ]*', d)]
    assert all(a != b for a, b in zip(ends, ends[1:]))
