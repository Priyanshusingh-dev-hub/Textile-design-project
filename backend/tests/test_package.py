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
    plates = [(f'Ink {i+1}', plate(m, hx)) for i, (hx, m, _) in enumerate(layers)]
    screens = [(f'Ink {i+1}', regmarks.add_registration_marks(to_print_ready(m), 300))
               for i, (_, m, _) in enumerate(layers)]
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


def test_print_preview_reconstructs_the_reduced_design_exactly():
    c = _client()
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 6, 'smoothing': 1}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    pv = c.post('/api/separation/preview', json={'layers': [{'id': l['id'], 'color': l['color']} for l in layers]}).json()
    preview = np.asarray(Image.open(BytesIO(c.get(pv['url']).content)).convert('RGB'))
    reduced = np.asarray(Image.open(BytesIO(c.get(r['url']).content)).convert('RGB'))
    assert preview.shape == reduced.shape
    assert np.array_equal(preview, reduced)          # stacked plates == the design, exactly


def test_print_preview_hiding_a_plate_shows_fabric():
    c = _client()
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 4, 'smoothing': 0}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    pv = c.post('/api/separation/preview', json={'layers': [{'id': l['id'], 'color': l['color']} for l in layers[:-1]], 'fabric': '#FFFFFF'}).json()
    preview = np.asarray(Image.open(BytesIO(c.get(pv['url']).content)).convert('RGB'))
    assert (preview == 255).all(axis=2).any()        # the hidden ink's area is now blank fabric (white)


def test_screen_label_enlarges_and_stays_black_and_white():
    screen = to_print_ready(Image.new('RGBA', (80, 80), (0, 0, 0, 255)))
    marked = regmarks.add_registration_marks(screen, 300, label='3  Ink-3  #A15745  6.0%')
    assert marked.mode == 'L' and marked.size[0] > 80
    # the label sits in the bottom margin as black text on white
    assert np.asarray(marked)[0, 0] == 255


def test_caption_plate_adds_a_bar_below_without_touching_the_art():
    p = Image.new('RGB', (60, 60), (200, 80, 80))
    out = regmarks.caption_plate(p, 'Ink 1  #C85050', '#C85050', 300)
    assert out.size[0] == 60 and out.size[1] > 60     # taller: caption bar added below
    assert np.asarray(out)[30, 30].tolist() == [200, 80, 80]   # original art unchanged


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


def test_package_prints_light_inks_before_dark_ones():
    """The usual order on a textile press: a dark ink put down first is picked
    up by the screens after it and dirties the lighter colours."""
    import io, zipfile
    from fastapi.testclient import TestClient
    from PIL import ImageDraw
    from app.main import app
    c = TestClient(app)
    im = Image.new('RGB', (120, 60), '#1E2A4A')                         # navy covers the most
    d = ImageDraw.Draw(im)
    d.rectangle((40, 0, 79, 59), fill='#F2C94C'); d.rectangle((80, 0, 119, 20), fill='#C0392B')
    b = io.BytesIO(); im.save(b, 'PNG')
    info = c.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': info['image_id'], 'colors': 3, 'smoothing': 0}).json()
    lay = c.post('/api/separation/create', json={'image_id': red['image_id'],
                 'palette': [p['hex'] for p in red['palette']]}).json()['layers']
    assert lay[0]['color'] == '#1E2A4A'                                 # separation ranks by coverage
    z = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={
        'layers': [{'id': l['id'], 'name': l['color'][1:], 'color': l['color']} for l in lay]}).content))
    films = [n.split('/')[1].split('.')[0] for n in z.namelist() if n.startswith('screens/')]
    assert films == ['F2C94C', 'C0392B', '1E2A4A']                      # yellow, red, navy
