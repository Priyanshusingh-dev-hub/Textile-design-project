from io import BytesIO
from zipfile import ZipFile
import numpy as np
from PIL import Image
from app.color_engine.engine import analyze, reduce
from app.separation_engine.engine import create as separation_create, plate, to_print_ready
from app.core.archive import build_package
from app.core import regmarks


def _three_color():
    a = np.zeros((60, 60, 3), dtype=np.uint8)
    a[:, :20] = (216, 72, 118)   # pink
    a[:, 20:40] = (40, 64, 96)   # navy
    a[:, 40:] = (217, 164, 62)   # gold
    return Image.fromarray(a)


def test_full_pipeline_reduce_separate_package():
    img = _three_color()
    pal = [p.hex for p in analyze(img, 3)]
    flat = reduce(img, 3)
    layers = separation_create(flat, pal, cleanup=0)
    plates = [(f'Ink {i+1}', plate(m, hx)) for i, (hx, m, _, _) in enumerate(layers)]
    screens = [(f'Ink {i+1}', regmarks.add_registration_marks(to_print_ready(m), 300))
               for i, (_, m, _, _) in enumerate(layers)]
    data = build_package(plates, screens, dpi=300, composite=img.convert('RGB'), readme='hello')
    with ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        assert 'plates/Ink-1.png' in names
        assert 'plates/Ink-3.png' in names
        assert 'screens/Ink-1.tif' in names
        assert 'proof.png' in names
        assert 'README.txt' in names
        # screens are grayscale TIFFs at the requested DPI
        screen = Image.open(BytesIO(zf.read('screens/Ink-1.tif')))
        assert screen.mode == 'L'
        assert screen.info.get('dpi') == (300.0, 300.0)


def test_package_deduplicates_same_named_inks():
    m = Image.new('RGBA', (8, 8), (0, 0, 0, 255))
    plates = [('Red', plate(m, '#FF0000')), ('Red', plate(m, '#AA0000'))]
    screens = [('Red', to_print_ready(m)), ('Red', to_print_ready(m))]
    data = build_package(plates, screens, dpi=300)
    with ZipFile(BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert {'plates/Red.png', 'plates/Red-2.png',
                'screens/Red.tif', 'screens/Red-2.tif'} <= names


def test_reg_marks_enlarge_the_screen_with_a_white_margin():
    screen = to_print_ready(Image.new('RGBA', (100, 100), (0, 0, 0, 255)))
    marked = regmarks.add_registration_marks(screen, 300)
    assert marked.size[0] > 100 and marked.size[1] > 100
    # the added margin corners are white (255), not ink
    assert np.asarray(marked)[0, 0] == 255


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_export_package_with_vector_includes_svg_folder():
    c = _client()
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 5}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    body = {'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers],
            'dpi': 300, 'reg_marks': True, 'vector': True, 'composite_image_id': r['image_id']}
    resp = c.post('/api/export/package', json=body)
    assert resp.status_code == 200
    with ZipFile(BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert any(n.startswith('plates/') for n in names)
        assert any(n.startswith('screens/') for n in names)
        assert 'vector/design.svg' in names
        assert any(n.startswith('vector/') and n.endswith('.svg') and n != 'vector/design.svg' for n in names)
        assert b'<svg' in zf.read('vector/design.svg')


def test_export_package_without_vector_has_no_svg():
    c = _client()
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 4}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    body = {'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers]}
    with ZipFile(BytesIO(c.post('/api/export/package', json=body).content)) as zf:
        assert not any(n.startswith('vector/') for n in zf.namelist())


def test_standalone_svg_endpoint_returns_one_svg():
    c = _client()
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 5}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    resp = c.post('/api/export/svg', json={'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers]})
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('image/svg+xml')
    assert resp.content.startswith(b'<svg') and resp.content.count(b'<path') >= 1
