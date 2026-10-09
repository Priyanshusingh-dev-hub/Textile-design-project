from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import main
from app.core import store

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    return TestClient(main.app)

def _png(image):
    b = BytesIO(); image.save(b, format='PNG'); return b.getvalue()

def _upload(client, image, name='design.png', content_type='image/png'):
    r = client.post('/api/image/upload', files={'file': (name, _png(image) if isinstance(image, Image.Image) else image, content_type)})
    assert r.status_code == 200, r.text
    return r.json()

def _two_inks():
    a = np.zeros((20, 20, 3), dtype=np.uint8); a[:, :10] = (216, 72, 118); a[:, 10:] = (40, 64, 96)
    return Image.fromarray(a)

def test_missing_image_is_a_clear_404_not_a_500(client):
    r = client.post('/api/colors/analyze', json={'image_id': '0' * 32, 'colors': 4})
    assert r.status_code == 404
    assert 'no longer available' in r.json()['detail']

def test_image_ids_cannot_escape_the_data_directory(client):
    r = client.post('/api/colors/analyze', json={'image_id': '../../app/main', 'colors': 4})
    assert r.status_code == 404

def test_stored_image_is_served_with_long_lived_cache(client):
    meta = _upload(client, _two_inks())
    r = client.get(meta['url'])
    assert r.status_code == 200 and r.headers['content-type'] == 'image/png'
    assert 'immutable' in r.headers['cache-control']

def test_upload_accepts_images_with_a_generic_content_type(client):
    meta = _upload(client, _two_inks(), name='scan.png', content_type='application/octet-stream')
    assert (meta['width'], meta['height']) == (20, 20)

def test_upload_rejects_non_images(client):
    r = client.post('/api/image/upload', files={'file': ('notes.txt', b'hello', 'text/plain')})
    assert r.status_code == 415

def test_upload_applies_exif_orientation(client):
    img = Image.new('RGB', (40, 20), 'red')
    exif = Image.Exif(); exif[0x0112] = 6   # "rotate 90 CW to display"
    b = BytesIO(); img.save(b, format='JPEG', exif=exif.tobytes())
    meta = _upload(client, b.getvalue(), name='phone.jpg', content_type='image/jpeg')
    assert (meta['width'], meta['height']) == (20, 40)

def test_upload_scales_16_bit_greyscale_instead_of_clipping_to_white(client):
    a = np.full((10, 10), 32768, dtype=np.uint16)   # mid-grey in 16-bit
    b = BytesIO(); Image.fromarray(a).save(b, format='TIFF')
    meta = _upload(client, b.getvalue(), name='scan.tif', content_type='image/tiff')
    value = np.asarray(store.load(meta['image_id']))[0, 0, 0]
    assert 120 <= value <= 135

def test_invalid_palette_colour_is_rejected_cleanly(client):
    meta = _upload(client, _two_inks())
    r = client.post('/api/separation/create', json={'image_id': meta['image_id'], 'palette': ['red']})
    assert r.status_code == 422
    r = client.post('/api/separation/create', json={'image_id': meta['image_id'], 'palette': []})
    assert r.status_code == 422

def test_map_reports_how_many_pixels_changed(client):
    meta = _upload(client, _two_inks())
    hit = client.post('/api/colors/map', json={'image_id': meta['image_id'], 'mappings': [{'source': '#D84876', 'target': '#00FF00'}]}).json()
    assert hit['changed_percent'] == 50.0
    miss = client.post('/api/colors/map', json={'image_id': meta['image_id'], 'mappings': [{'source': '#FFFF00', 'target': '#00FF00'}]}).json()
    assert miss['changed_pixels'] == 0

def test_jpg_export_flattens_transparency_onto_white(client):
    a = np.zeros((10, 10, 4), dtype=np.uint8)   # fully transparent
    meta = _upload(client, Image.fromarray(a))
    r = client.post('/api/export', json={'image_id': meta['image_id'], 'format': 'jpg'})
    assert r.status_code == 200
    assert np.asarray(Image.open(BytesIO(r.content)).convert('RGB')).min() >= 250

def test_project_export_then_import_restores_the_workspace(client):
    original = _upload(client, _two_inks())
    palette = client.post('/api/colors/analyze', json={'image_id': original['image_id'], 'colors': 2}).json()['palette']
    layers = client.post('/api/separation/create', json={'image_id': original['image_id'], 'palette': [p['hex'] for p in palette]}).json()['layers']
    body = {'name': 'Spring / Summer 26', 'original_id': original['image_id'], 'image_id': original['image_id'], 'palette': palette,
            'layers': [{**l, 'visible': i == 0, 'opacity': 60} for i, l in enumerate(layers)], 'settings': {'repeatMode': 'half-drop'}}
    r = client.post('/api/project/export', json=body)
    assert r.status_code == 200
    assert 'Spring-Summer-26.textileproj' in r.headers['content-disposition']
    assert 'project.json' in ZipFile(BytesIO(r.content)).namelist()

    store.cleanup_expired(expiry_hours=-1)   # the working images are gone...
    restored = client.post('/api/project/import', files={'file': ('p.textileproj', r.content, 'application/zip')})
    assert restored.status_code == 200, restored.text
    p = restored.json()                       # ...but the project still opens
    assert p['name'] == 'Spring / Summer 26' and p['settings'] == {'repeatMode': 'half-drop'}
    assert [c['hex'] for c in p['palette']] == [c['hex'] for c in palette]
    assert [l['color'] for l in p['layers']] == [l['color'] for l in layers]
    assert [l['visible'] for l in p['layers']] == [True, False] and p['layers'][0]['opacity'] == 60
    for url in [p['image']['url'], p['original']['url']] + [l[k] for l in p['layers'] for k in ('url', 'mask_url', 'plate_url')]:
        assert client.get(url).status_code == 200

def test_project_import_rejects_other_files(client):
    r = client.post('/api/project/import', files={'file': ('x.textileproj', b'garbage', 'application/octet-stream')})
    assert r.status_code == 422

def _separate(client):
    a = np.zeros((30, 30, 3), dtype=np.uint8); a[:, :15] = (30, 58, 138); a[:, 15:] = (242, 208, 75)
    meta = _upload(client, Image.fromarray(a))
    layers = client.post('/api/separation/create', json={'image_id': meta['image_id'], 'palette': ['#1E3A8A', '#F2D04B'], 'cleanup': 0}).json()['layers']
    return [{'id': l['id'], 'name': n, 'color': l['color']} for l, n in zip(layers, ['1 NAVY 120', '2 YELLOW 90'])]

def test_multichannel_psd_export_reimports_as_the_same_named_screens(client):
    inks = _separate(client)
    r = client.post('/api/export/psd-multichannel', json={'layers': inks, 'dpi': 300})
    assert r.status_code == 200 and r.content[:4] == b'8BPS'
    back = _upload(client, r.content, name='loomlab-separation.psd', content_type='application/octet-stream')
    assert [l['name'] for l in back['layers']] == ['1 NAVY 120', '2 YELLOW 90']
    assert [l['coverage'] for l in back['layers']] == [50.0, 50.0]

def test_trapped_screen_export_spreads_the_lighter_ink(client):
    inks = _separate(client)
    def yellow_ink_pixels(trap):
        r = client.post('/api/export/zip', json={'layers': inks, 'content': 'film', 'format': 'png', 'trap': trap})
        zf = ZipFile(BytesIO(r.content))
        film = np.asarray(Image.open(BytesIO(zf.read('2-YELLOW-90.png'))).convert('L'))
        return int((film < 128).sum())
    assert yellow_ink_pixels(0) == 15 * 30
    assert yellow_ink_pixels(2) == 17 * 30

def test_trap_width_is_validated(client):
    inks = _separate(client)
    r = client.post('/api/export/psd-multichannel', json={'layers': inks, 'trap': 50})
    assert r.status_code == 422

def test_trapped_svg_paints_lighter_inks_first(client):
    inks = _separate(client)                     # navy listed first, yellow second
    svg = client.post('/api/export/svg', json={'layers': inks, 'trap': 2, 'min_area': 0}).text
    assert svg.index('fill="#F2D04B"') < svg.index('fill="#1E3A8A"')

def test_trap_preview_marks_exactly_the_spread(client):
    inks = _separate(client)                     # navy | yellow, 15 columns each, 30 rows
    r = client.post('/api/separation/trap-preview', json={'layers': inks, 'trap': 2})
    assert r.status_code == 200, r.text
    p = r.json()
    navy, yellow = p['layers']
    assert navy['spread_percent'] == 0                       # the darkest ink never spreads
    assert yellow['spread_percent'] == round(2 * 30 / 900 * 100, 2)
    spread = np.asarray(store.load(yellow['spread_url'].rsplit('/', 1)[1]))[:, :, 3] > 0
    assert spread[:, 13:15].all() and spread.sum() == 2 * 30  # only the 2 columns it grew into
    film = np.asarray(store.load(yellow['film_url'].rsplit('/', 1)[1]).convert('L'))
    assert (film < 128).sum() == 17 * 30                      # the film is the trapped one
    assert p['overlap_percent'] == yellow['spread_percent']
    composite = np.asarray(store.load(p['composite_url'].rsplit('/', 1)[1]))
    assert tuple(composite[0, 14, :3]) == (30, 58, 138)       # navy prints on top of the spread

def test_spread_highlight_switches_colour_for_magenta_inks():
    assert main._spread_colour('#1E3A8A') == main._SPREAD_MAGENTA
    assert main._spread_colour('#F010C0') == main._SPREAD_CYAN
