import numpy as np
from app.vector_engine import engine as V


def _area(poly):
    a = np.array(poly, float)
    return 0.5 * abs(np.dot(a[:, 0], np.roll(a[:, 1], -1)) - np.dot(a[:, 1], np.roll(a[:, 0], -1)))


def test_solid_square_traces_one_loop_with_right_area():
    m = np.zeros((30, 30), bool); m[5:15, 5:15] = True
    loops = V.mask_to_loops(m, simplify=0.8, smooth=0, min_area=2)
    assert len(loops) == 1
    assert abs(_area(loops[0]) - 100) < 6


def test_shape_with_hole_traces_two_loops():
    m = np.zeros((40, 40), bool); m[5:35, 5:35] = True; m[15:25, 15:25] = False
    loops = V.mask_to_loops(m, 0.8, 0, 2)
    areas = sorted(_area(l) for l in loops)
    assert len(loops) == 2
    assert abs(areas[0] - 100) < 10 and abs(areas[1] - 900) < 20


def test_two_disjoint_shapes_trace_two_loops():
    m = np.zeros((40, 40), bool); m[5:12, 5:12] = True; m[25:35, 25:35] = True
    assert len(V.mask_to_loops(m, 0.8, 0, 2)) == 2


def test_tiny_specks_are_dropped_by_min_area():
    m = np.zeros((20, 20), bool); m[10, 10] = True  # single pixel
    assert V.mask_to_loops(m, 0.5, 0, min_area=6.0) == []


def test_empty_mask_yields_no_loops_and_empty_path_svg():
    m = np.zeros((10, 10), bool)
    assert V.mask_to_loops(m) == []
    svg = V.layer_svg(m, '#FF0000', (10, 10))
    assert '<path' not in svg and svg.startswith('<svg')


def test_build_svg_has_one_path_per_nonempty_layer_with_even_odd_fill():
    a = np.zeros((20, 20), bool); a[2:8, 2:8] = True
    b = np.zeros((20, 20), bool); b[12:18, 12:18] = True
    svg = V.build_svg([('#E63946', a), ('#457B9D', b)], (20, 20))
    assert svg.count('<path') == 2
    assert 'fill="#E63946"' in svg and 'fill="#457B9D"' in svg
    assert 'fill-rule="evenodd"' in svg
    assert 'viewBox="0 0 20 20"' in svg


def test_layer_svg_smoothing_rounds_but_stays_near_shape():
    m = np.zeros((40, 40), bool); m[8:32, 8:32] = True
    rough = V.mask_to_loops(m, 0.5, 0, 2)[0]
    smooth = V.mask_to_loops(m, 0.5, 2, 2)[0]
    # smoothing adds points (rounded corners) but keeps roughly the same area
    assert len(smooth) > len(rough)
    assert abs(_area(smooth) - _area(rough)) / _area(rough) < 0.2   # within 20%
