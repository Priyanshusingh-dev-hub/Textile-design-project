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
