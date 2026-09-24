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


def test_zip_design_svg_matches_the_standalone_svg_export():
    """The same design exported via the zip or via 'Vector SVG only' must give
    the same vector. They used to drop different specks (min_area 6 vs 8), and
    the zip traced every ink twice to build it."""
    import io, zipfile
    from fastapi.testclient import TestClient
    from PIL import Image, ImageDraw
    from app.main import app
    c = TestClient(app)
    im = Image.new('RGB', (160, 120), '#EFE3C8')
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 90, 100), fill='#C0392B'); d.rectangle((100, 30, 150, 90), fill='#2A5DA8')
    for x in range(10, 150, 13):                          # specks either side of the area cut
        d.rectangle((x, 108, x + (x % 4), 108 + (x % 3)), fill='#1A1A1A')
    b = io.BytesIO(); im.save(b, 'PNG')
    info = c.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': info['image_id'], 'colors': 4, 'smoothing': 0}).json()
    lay = c.post('/api/separation/create', json={'image_id': red['image_id'],
                 'palette': [p['hex'] for p in red['palette']]}).json()['layers']
    payload = [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in lay]
    zf = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={'layers': payload, 'vector': True}).content))
    assert zf.read('vector/design.svg') == c.post('/api/export/svg', json={'layers': payload}).content
