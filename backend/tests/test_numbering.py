"""The third way in: one coloured design through textile's `number` (and `final`
at the mill's size), as LoomLab's POST /api/number."""
import io
import zipfile

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

from app.main import app

client = TestClient(app)
BEIGE, RED, DARK_RED, BLACK = (240, 222, 180), (215, 23, 40), (180, 17, 31), (24, 26, 31)


def _petals_png():
    """A small AI-like design: red petals, each with a darker red shading patch, black stems, soft edges."""
    img = Image.new('RGB', (480, 320), BEIGE)
    d = ImageDraw.Draw(img)
    for cx, cy in ((110, 100), (300, 90), (200, 230), (400, 240)):
        d.line([(cx, cy + 40), (cx - 30, cy + 90)], fill=BLACK, width=7)
        d.ellipse([cx - 55, cy - 40, cx + 55, cy + 40], fill=RED)
        d.ellipse([cx - 40, cy - 5, cx + 5, cy + 30], fill=DARK_RED)
    buf = io.BytesIO()
    img.filter(ImageFilter.GaussianBlur(0.8)).save(buf, 'PNG')
    return buf.getvalue()


def _hexes(palette):
    return {p['hex'] for p in palette}


def _close(hexes, rgb, tol=12):
    return any(max(abs(int(h[i:i + 2], 16) - c) for i, c in zip((1, 3, 5), rgb)) <= tol for h in hexes)


def test_a_design_is_numbered_its_shading_joins_its_colour_and_everything_is_in_one_zip():
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '8', 'detail': 'normal', 'merge_shades': 'true', 'inches': '3x2', 'size': '900'})
    assert r.status_code == 200, r.text
    j = r.json()
    n = j['number']
    assert n['name'] == 'petals' and n['areas'] > 4 and n['verify']
    assert n['size_px'] == [900, 600]
    assert any(_close([m['from']], DARK_RED) and _close([m['into']], RED) for m in n['shades_merged'])
    red = j['reduced']
    assert (red['width'], red['height']) == (900, 600)
    hexes = _hexes(red['palette'])
    assert _close(hexes, RED) and _close(hexes, BLACK) and _close(hexes, BEIGE)
    assert not _close(hexes, DARK_RED, tol=8)                  # the shading is on the red screen
    assert red['accuracy'] > 80
    assert n['mill'] == {'inches': [3.0, 2.0], 'size_px': [900, 600], 'dpi': 300, 'inks': n['mill']['inks'],
                         'design_match': n['mill']['design_match'], 'passed': True, 'cropped': False,
                         'folder': 'petals_mill_3x2in'}
    for url in (n['sheet_url'], n['numbers_url'], j['original']['url'], red['url']):
        assert client.get(url).status_code == 200
    z = client.get(n['zip_url'], params={'name': n['zip_name']})
    assert z.status_code == 200 and 'petals_LoomLab_number.zip' in z.headers['content-disposition']
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    for want in ('petals_number/petals_sketch_bold_numbers.png', 'petals_number/petals_colors.csv',
                 'petals_number/package/petals_final_900x600px_300dpi.tif', 'petals_number/package/petals_layers_900px_300dpi.psd',
                 'petals_mill_3x2in/petals_final_900x600px_300dpi.tif', 'petals_mill_3x2in/petals_final.svg',
                 'petals_mill_3x2in/petals_layers_900x600px_300dpi.psd'):
        assert want in names, want


def test_without_merge_shades_the_shading_keeps_its_own_screen_and_no_mill_file_unless_asked():
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '8', 'merge_shades': 'false', 'size': '900'})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['number']['shades_merged'] == [] and j['number']['mill'] is None
    assert _close(_hexes(j['reduced']['palette']), DARK_RED, tol=8)


def test_bad_settings_are_a_4xx_and_a_gone_zip_is_a_404():
    png = _petals_png()
    for data, word in (({'inks': '1'}, 'Inks'), ({'detail': 'lots'}, 'Detail'), ({'inches': 'big'}, 'Mill size'),
                       ({'inches': '200x200'}, 'Mill size'), ({'inches': '100x100'}, 'too big'), ({'size': '10'}, 'Size')):
        r = client.post('/api/number', files={'design': ('p.png', png, 'image/png')}, data=data)
        assert r.status_code == 422 and word in r.json()['detail'], (data, r.text)
    r = client.post('/api/number', files={'design': ('p.png', b'not an image', 'image/png')})
    assert r.status_code == 422
    assert client.get('/api/number/' + '0' * 32 + '/zip').status_code == 404
    assert client.get('/api/number/..%2F..%2Fetc/zip').status_code == 404


# ---- palette edits into the zip (POST /api/number/{job}/rebuild) ----

import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402

from app.core import renumber, store  # noqa: E402

NAVY = '#1F2A60'


@pytest.fixture(scope='module')
def numbered():
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '8', 'merge_shades': 'true', 'inches': '3x2', 'size': '900'})
    assert r.status_code == 200, r.text
    return r.json()


def _zip_files(url):
    z = zipfile.ZipFile(io.BytesIO(client.get(url).content))
    return {n: z.read(n) for n in z.namelist()}


def _members(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n) for n in z.namelist()}


def _same_file(a, b, name):
    """Byte-same; an inner zip by its members (its timestamps change every run)."""
    return _members(a) == _members(b) if name.endswith('.zip') else a == b


def _rgb(url):
    return np.asarray(Image.open(io.BytesIO(client.get(url).content)).convert('RGB'))


def _edit(image_id, source, target):
    r = client.post('/api/colors/remap', json={'image_id': image_id, 'source': source, 'target': target})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_rebuild_is_the_tools_own_code_unchanged_colours_give_the_same_files(numbered, tmp_path):
    """The proof that the rebuild makes what `number` made: with every colour kept, each file under the run's
    folder (package, PSD, stacks, CSV, number.json, colour sheets) is byte-same as in the first zip."""
    n = numbered['number']
    first = _zip_files(n['zip_url'])
    zip_path = store.number_path(n['job'], 'zip')
    flat = renumber.first_final(zip_path, 'petals')
    mapping = renumber.colour_map(flat, flat)
    assert set(mapping) == {h[1:] for h in _hexes(numbered['reduced']['palette'])}
    assert all(k == v for k, v in mapping.items())
    picture = np.asarray(Image.open(io.BytesIO(_petals_png())).convert('RGB'))
    r = renumber.rebuild(zip_path, 'petals', n['mill'], mapping, picture, tmp_path)
    assert r['code'] == 0 and r['verify']
    made = {f"petals_number/{p.relative_to(tmp_path / 'number').as_posix()}": p.read_bytes()
            for p in (tmp_path / 'number').rglob('*') if p.is_file()}
    assert set(made) == {k for k in first if k.startswith('petals_number/')}
    for k, data in made.items():
        assert _same_file(first[k], data, k), k
    assert r['made']['design_match'] == n['design_match']


def test_a_recolour_goes_into_a_new_zip_and_the_first_one_stays(numbered):
    n, red = numbered['number'], numbered['reduced']
    red_hex = next(p['hex'] for p in red['palette'] if _close([p['hex']], RED))
    edited = _edit(red['image_id'], red_hex, NAVY)
    r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': edited['image_id']})
    assert r.status_code == 200, r.text
    m = r.json()['number']
    assert m['job'] != n['job'] and m['built_from'] == edited['image_id'] and m['verify']
    assert r.json()['changes'] == [{'from': red_hex, 'to': NAVY}] == m['changes']
    assert NAVY in {i['hex'] for i in m['inks']} and red_hex not in {i['hex'] for i in m['inks']}
    files = _zip_files(m['zip_url'])
    final = next(k for k in files if k.startswith('petals_number/package/petals_final_') and k.endswith('.png'))
    on_screen = _rgb(edited['url'])
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(files[final])).convert('RGB')), on_screen)
    csv_text = files['petals_number/petals_colors.csv'].decode()
    assert NAVY in csv_text and red_hex not in csv_text and ',navy,' in csv_text
    assert any(k.endswith(f'_navy_motif_{NAVY[1:]}.png') for k in files if '/channels/' in k)
    assert 'petals_number/package/petals_layers_900px_300dpi.psd' in files
    number_json = json.loads(files['petals_number/petals_number.json'])
    assert [h for h, _, _ in number_json['inks']] == [i['hex'][1:] for i in m['inks']]
    # the mill-size folder followed: its red screen is navy now
    mill_final = next(k for k in files if k.startswith('petals_mill_3x2in/petals_final_') and k.endswith('.png'))
    mill_hex = {'#%02X%02X%02X' % tuple(c) for c in np.unique(
        np.asarray(Image.open(io.BytesIO(files[mill_final])).convert('RGB')).reshape(-1, 3), axis=0)}
    assert NAVY in mill_hex and not _close(mill_hex, RED, tol=20)
    assert m['mill']['passed'] and m['mill']['left'] == [] and m['mill']['missing'] == []
    # the first zip still downloads as it was
    assert red_hex in _zip_files(n['zip_url'])['petals_number/petals_colors.csv'].decode()
    # asking again for the same design answers the same zip; undoing every edit answers the first run
    again = client.post(f"/api/number/{m['job']}/rebuild", json={'reduced_id': edited['image_id']}).json()['number']
    assert again['job'] == m['job']
    back = client.post(f"/api/number/{m['job']}/rebuild", json={'reduced_id': red['image_id']}).json()
    assert back['number']['job'] == n['job'] and back['changes'] == []


def test_a_merge_after_a_recolour_maps_from_the_first_run(numbered):
    n, red = numbered['number'], numbered['reduced']
    red_hex = next(p['hex'] for p in red['palette'] if _close([p['hex']], RED))
    black_hex = next(p['hex'] for p in red['palette'] if _close([p['hex']], BLACK))
    one = _edit(red['image_id'], red_hex, NAVY)
    m1 = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': one['image_id']}).json()['number']
    two = _edit(one['image_id'], black_hex, NAVY)                     # the stems join the navy screen
    r = client.post(f"/api/number/{m1['job']}/rebuild", json={'reduced_id': two['image_id']})
    assert r.status_code == 200, r.text
    m2 = r.json()['number']
    assert {c['from'] for c in m2['changes']} == {red_hex, black_hex} and {c['to'] for c in m2['changes']} == {NAVY}
    assert len(m2['inks']) == len(red['palette']) - 1 and m2['verify']
    files = _zip_files(m2['zip_url'])
    assert sum('/package/channels/' in k for k in files) == len(red['palette']) - 1


def test_an_edit_the_zip_cannot_follow_is_refused_and_gone_runs_are_404(numbered):
    n, red = numbered['number'], numbered['reduced']
    a = np.asarray(Image.open(io.BytesIO(client.get(red['url']).content)).convert('RGBA')).copy()
    ink = [int(red['palette'][1]['hex'][i:i + 2], 16) for i in (1, 3, 5)]
    a[0, 0, :3] = ink if tuple(a[0, 0, :3]) != tuple(ink) else [0, 0, 0]     # one pixel moved: its area is two colours
    r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': store.save(Image.fromarray(a))})
    assert r.status_code == 422 and 'one by one' in r.json()['detail']
    other = store.save(Image.new('RGB', (100, 100), (255, 0, 0)))
    r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': other})
    assert r.status_code == 422 and 'not the numbered design' in r.json()['detail']
    assert client.post('/api/number/' + 'a' * 32 + '/rebuild', json={'reduced_id': red['image_id']}).status_code == 404
    assert client.post('/api/number/x..y/rebuild', json={'reduced_id': red['image_id']}).status_code == 404
    assert client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': 'nope'}).status_code == 422
    assert client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': '0' * 32}).status_code == 404


def test_the_mill_says_what_it_could_not_follow(numbered, tmp_path):
    """A changed ink with no screen of its own at mill size, and a mill ink near no numbered ink: both reported,
    nothing changed behind the operator's back."""
    n = numbered['number']
    with zipfile.ZipFile(store.number_path(n['job'], 'zip')) as z:
        renumber._extract(z, n['mill']['folder'], tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    flat = renumber.first_final(store.number_path(n['job'], 'zip'), 'petals')
    mapping = {k: k for k in renumber.colour_map(flat, flat)}
    black = next(k for k in mapping if _close(['#' + k], BLACK))
    del mapping[black]                                   # the stems' ink is not a numbered ink here
    mapping['00FF00'] = '0000FF'                         # and this one changed but the mill has no such screen
    picture = np.asarray(Image.open(io.BytesIO(_petals_png())).convert('RGB'))
    out = renumber._mill(tmp_path, 'petals', n['mill'], mapping, picture)
    assert out['missing'] == ['00FF00'] and _close(['#' + h for h in out['left']], BLACK)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before   # no ink moved: the folder as it was


def test_the_run_record_ages_out_with_the_cache(numbered):
    path = store.number_path(numbered['number']['job'], 'json')
    assert json.loads(path.read_text(encoding='utf-8'))['root'] == numbered['number']['job']
    copy = path.with_name('number-' + 'e' * 32 + '.json')
    copy.write_text('{}', encoding='utf-8')
    old = time.time() - 49 * 3600
    os.utime(copy, (old, old))
    store.cleanup_expired()
    assert not copy.exists() and path.exists()


# ---- the mill's ink names in the zip ----

def test_shelf_names_go_into_the_files_safely_and_only_on_exact_inks(numbered):
    n, red = numbered['number'], numbered['reduced']
    pal = [p['hex'] for p in red['palette']]
    red_hex = next(h for h in pal if _close([h], RED))
    black_hex = next(h for h in pal if _close([h], BLACK))
    beige_hex = next(h for h in pal if _close([h], BEIGE))
    names = [{'hex': red_hex, 'name': 'Rani Pink #12'}, {'hex': black_hex, 'name': 'रानी काला'},
             {'hex': beige_hex, 'name': '=SUM(A1)'}, {'hex': '#123456', 'name': 'Not in the design'}]
    r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': red['image_id'], 'palette': names})
    assert r.status_code == 200, r.text
    m = r.json()['number']
    assert m['job'] != n['job'] and r.json()['changes'] == []                  # names only: still a new zip
    assert m['names'] == {red_hex: 'Rani Pink #12', black_hex: 'रानी काला', beige_hex: '=SUM(A1)'}
    files = _zip_files(m['zip_url'])
    channels = [k for k in files if k.startswith('petals_number/package/channels/')]
    assert any(k.endswith(f'_Rani-Pink-12_motif_{red_hex[1:]}.png') for k in channels)
    assert any(k.endswith(f'_SUM-A1_ground_{beige_hex[1:]}.png') for k in channels)
    assert any(k.endswith(f'_black_motif_{black_hex[1:]}.png') for k in channels)     # Devanagari: the colour word
    assert all(len(k.rsplit('/', 1)[1][:-4].split('_')) == 5 and '#' not in k.rsplit('/', 1)[1] for k in channels)
    raw = files['petals_number/petals_colors.csv']
    assert raw.startswith(b'\xef\xbb\xbf')                                     # a BOM: Excel shows the Hindi
    text = raw.decode('utf-8-sig')
    assert text.splitlines()[0] == 'Number,HEX,Colour,Share %,Group,Ink'
    assert 'Rani Pink #12' in text and 'रानी काला' in text and "'=SUM(A1)" in text and ',=SUM' not in text
    from psd_tools import PSDImage
    psd = PSDImage.open(io.BytesIO(files['petals_number/package/petals_layers_900px_300dpi.psd']))
    assert any(layer.name.endswith(f'Rani Pink 12 motif {red_hex[1:]}') for layer in psd)
    mill = [k for k in files if k.startswith('petals_mill_3x2in/') and k.endswith('_colored_channels_900x600px_300dpi.zip')]
    assert any('_Rani-Pink-12_' in member for member in _members(files[mill[0]]))   # the mill's red followed by name
    assert json.loads(files['petals_number/petals_number.json'])['ink_names'][red_hex[1:]] == 'Rani Pink #12'
    again = client.post(f"/api/number/{m['job']}/rebuild", json={'reduced_id': red['image_id'], 'palette': names})
    assert again.json()['number']['job'] == m['job']                           # the same names: the same zip
    plain = client.post(f"/api/number/{m['job']}/rebuild", json={'reduced_id': red['image_id']}).json()
    assert plain['number']['job'] == n['job']                                  # names dropped: the first zip again


def test_one_name_never_names_two_screens_and_bad_names_are_a_422(numbered):
    n, red = numbered['number'], numbered['reduced']
    pal = [p['hex'] for p in red['palette']]
    r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': red['image_id'],
                    'palette': [{'hex': pal[0], 'name': 'Ivory'}, {'hex': pal[1], 'name': 'ivory '}]})
    assert r.status_code == 200 and r.json()['number']['names'] == {pal[0]: 'Ivory'}
    for bad in ([{'hex': pal[0], 'name': 'x' * 61}], [{'hex': 'red', 'name': 'Red'}], [{'name': 'Red'}]):
        r = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': red['image_id'], 'palette': bad})
        assert r.status_code == 422, bad


# ---- 👍/👎 on a run, into the textile tool's memory ----

def _log_rows():
    from textile import learn
    with open(learn.log_path(), encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_a_word_on_a_run_lands_on_that_run_even_beside_one_of_the_same_name(numbered):
    first = numbered['number']
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '6', 'merge_shades': 'true', 'size': '700'})
    second = r.json()['number']
    assert second['name'] == first['name']
    runs = {x['run']: x for x in _log_rows() if x.get('event') == 'run' and x.get('run')}
    assert {first['job'], second['job']} <= set(runs)
    r = client.post(f"/api/number/{first['job']}/feedback", json={'verdict': 'good', 'note': ' clean lines '})
    assert r.status_code == 200 and r.json() == {'verdict': 'good', 'note': 'clean lines'}
    row = _log_rows()[-1]
    assert row['event'] == 'feedback' and row['run'] == first['job'] and row['run_time'] == runs[first['job']]['time']
    assert row['note'] == 'clean lines' and row['by'] == 'LoomLab'
    from textile import learn
    verdicts = learn._verdicts(_log_rows())
    assert learn._verdict_of(verdicts, runs[first['job']])[0] == 'good'
    assert learn._verdict_of(verdicts, runs[second['job']]) is None            # the other run of that name: no word


def test_a_word_on_a_rebuilt_zip_goes_to_its_first_run_with_the_edits(numbered):
    n, red = numbered['number'], numbered['reduced']
    red_hex = next(p['hex'] for p in red['palette'] if _close([p['hex']], RED))
    edited = _edit(red['image_id'], red_hex, '#2A6041')
    child = client.post(f"/api/number/{n['job']}/rebuild", json={'reduced_id': edited['image_id']}).json()['number']
    r = client.post(f"/api/number/{child['job']}/feedback", json={'verdict': 'bad'})
    assert r.status_code == 200
    row = _log_rows()[-1]
    assert row['run'] == n['job'] and row['verdict'] == 'bad' and row['changes'] == [{'from': red_hex, 'to': '#2A6041'}]


def test_bad_words_and_gone_runs_are_4xx(numbered):
    job = numbered['number']['job']
    assert client.post(f'/api/number/{job}/feedback', json={'verdict': 'meh'}).status_code == 422
    assert client.post(f'/api/number/{job}/feedback', json={'verdict': 'good', 'note': 'x' * 301}).status_code == 422
    assert client.post('/api/number/' + 'b' * 32 + '/feedback', json={'verdict': 'good'}).status_code == 404
    assert client.post('/api/number/nope/feedback', json={'verdict': 'good'}).status_code == 404


def test_the_mill_moves_only_what_the_operator_changed_and_never_joins_two_of_its_screens(tmp_path):
    """Untouched mill inks keep their own hex (not the 3535 sheet's, a dE or so away); of two mill screens near
    one changed ink only the nearer follows it, the other keeps its colour and is reported."""
    red_a, red_b, beige = (200, 20, 30), (184, 27, 40), (238, 220, 178)
    img = np.zeros((60, 60, 3), np.uint8)
    img[:] = beige
    img[5:25, 5:25] = red_a
    img[30:55, 30:55] = red_b
    Image.fromarray(img).save(tmp_path / 'm_final_60px_300dpi.png')
    (tmp_path / 'm_report.json').write_text('{}', encoding='utf-8')
    hx = lambda c: '%02X%02X%02X' % c
    key_red, key_beige = hx((198, 21, 32)), hx((240, 222, 180))
    out = renumber._mill(tmp_path, 'm', {'inches': [0.2, 0.2]}, {key_red: NAVY[1:], key_beige: key_beige}, img,
                         {NAVY[1:]: 'Deep Navy'})
    assert out['shared'] == [hx(red_b)] and out['left'] == [] and out['missing'] == []
    final = np.asarray(Image.open(next(tmp_path.glob('m_final_*.png'))).convert('RGB'))
    got = {'%02X%02X%02X' % tuple(c) for c in np.unique(final.reshape(-1, 3), axis=0)}
    assert got == {NAVY[1:], hx(red_b), hx(beige)}                  # beige untouched: its own hex, not the key's
    assert tuple(final[10, 10]) == tuple(int(NAVY[i:i + 2], 16) for i in (1, 3, 5))
    report = json.loads((tmp_path / 'm_report.json').read_text(encoding='utf-8'))
    assert report['colours'] == 3 and report['verify']['passed']
    assert {c['hex']: c.get('ink') for c in report['channels']}[NAVY[1:]] == 'Deep Navy'


def test_a_word_still_saves_after_a_crash_cut_a_hindi_note_in_half():
    from textile import learn
    with open(learn.log_path(), 'ab') as fh:
        fh.write('{"event": "feedback", "note": "रंग'.encode('utf-8')[:-1])      # torn inside a character
    assert all(isinstance(r, dict) for r in learn._read())


# ---- the operator's own smallest shape (sq mm) ----

def _grainy_petals_png():
    """Petals with scattered 2-3 px flecks of the dark red on the ground: parts of a few sq px each."""
    img = Image.open(io.BytesIO(_petals_png())).convert('RGB')
    d = ImageDraw.Draw(img)
    for x, y in ((20, 20), (60, 280), (150, 20), (260, 150), (330, 40), (440, 20), (20, 150), (230, 300), (380, 150), (300, 300)):
        d.ellipse([x, y, x + 3, y + 3], fill=DARK_RED)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


def test_a_bigger_smallest_shape_joins_tiny_parts_into_their_neighbour():
    def run(extra):
        r = client.post('/api/number', files={'design': ('flecks.png', _grainy_petals_png(), 'image/png')},
                        data={'inks': '8', 'merge_shades': 'false', 'detail': 'zyada', 'size': '900'} | extra)
        assert r.status_code == 200, r.text
        return r.json()['number']
    fine, coarse = run({}), run({'min_area_mm2': '20'})
    assert fine['min_area_mm2'] is None and coarse['min_area_mm2'] == 20.0
    assert coarse['areas'] < fine['areas']                                   # the flecks are no parts of their own
    assert coarse['verify'] and coarse['missed'] == 0


def test_the_smallest_shape_is_checked_before_the_run():
    png = _petals_png()
    for bad in ('-1', '51', 'nan', 'inf', 'abc'):
        r = client.post('/api/number', files={'design': ('p.png', png, 'image/png')}, data={'min_area_mm2': bad})
        assert r.status_code == 422, bad
    r = client.post('/api/number', files={'design': ('p.png', png, 'image/png')}, data={'min_area_mm2': '99'})
    assert r.status_code == 422 and 'Smallest shape' in r.json()['detail']


# ---- new numbering options and CLI args builder ----

from app.routes.numbering import build_number_args, filter_supported_args, get_supported_number_flags  # noqa: E402


def test_build_number_args_maps_options_to_cli_flags():
    # 1. Default args (all off except detail_rescue=True)
    args = build_number_args(src='src.png', out='out', name='test')
    assert args == [
        'number', 'src.png', '--out', 'out', '--name', 'test',
        '--colors', '8', '--detail', 'normal', '--size', '3535',
        '--merge-shades',
    ]

    # 2. Detail rescue turned off -> --no-detail-rescue
    args_no_rescue = build_number_args(src='src.png', out='out', name='test', detail_rescue=False)
    assert '--no-detail-rescue' in args_no_rescue

    # 3. Mode -> --mode
    for m in ('hybrid', 'gradients', 'spray'):
        args_mode = build_number_args(src='src.png', out='out', name='test', mode=m)
        idx = args_mode.index('--mode')
        assert args_mode[idx + 1] == m

    # 4. Underbase + choke -> --underbase --underbase-choke N
    args_ub = build_number_args(src='src.png', out='out', name='test', underbase=True, underbase_choke=2)
    assert '--underbase' in args_ub
    idx_ub = args_ub.index('--underbase-choke')
    assert args_ub[idx_ub + 1] == '2'

    # 5. Trap -> --trap N
    args_trap = build_number_args(src='src.png', out='out', name='test', trap=3)
    idx_tr = args_trap.index('--trap')
    assert args_trap[idx_tr + 1] == '3'

    # 6. Film -> --film
    args_film = build_number_args(src='src.png', out='out', name='test', film=True)
    assert '--film' in args_film

    # 7. Estimate -> --estimate
    args_est = build_number_args(src='src.png', out='out', name='test', estimate=True)
    assert '--estimate' in args_est

    # 8. Seam check -> --seam-check
    args_seam = build_number_args(src='src.png', out='out', name='test', seam_check=True)
    assert '--seam-check' in args_seam

    # 9. Halftone -> --halftone am --halftone-lpi N --halftone-angle N
    args_ht = build_number_args(
        src='src.png', out='out', name='test',
        halftone='am', halftone_lpi=55.0, halftone_angle=45.0
    )
    assert '--halftone' in args_ht and args_ht[args_ht.index('--halftone') + 1] == 'am'
    assert '--halftone-lpi' in args_ht and args_ht[args_ht.index('--halftone-lpi') + 1] == '55'
    assert '--halftone-angle' in args_ht and args_ht[args_ht.index('--halftone-angle') + 1] == '45'


def test_filter_supported_args_drops_unsupported_flags_safely():
    full_args = [
        'number', 'src.png', '--out', 'out', '--name', 'test',
        '--colors', '8', '--mode', 'hybrid', '--underbase',
        '--underbase-choke', '2', '--trap', '1', '--film',
    ]
    supported = {'--out', '--name', '--colors', '--underbase'}
    filtered, unsupported = filter_supported_args(full_args, supported)
    assert filtered == ['number', 'src.png', '--out', 'out', '--name', 'test', '--colors', '8', '--underbase']
    assert unsupported == ['--mode', '--underbase-choke', '--trap', '--film']


def test_number_design_validates_new_options_inputs():
    png = _petals_png()
    for bad_data, msg in (
        ({'mode': 'ultra'}, 'Mode'),
        ({'underbase_choke': '99'}, 'Underbase choke'),
        ({'underbase_choke': '-1'}, 'Underbase choke'),
        ({'trap': '99'}, 'Trapping'),
        ({'trap': '-1'}, 'Trapping'),
        ({'halftone': 'custom'}, 'Halftone'),
        ({'halftone_lpi': '999'}, 'Halftone LPI'),
        ({'halftone_angle': '500'}, 'Halftone angle'),
    ):
        r = client.post('/api/number', files={'design': ('p.png', png, 'image/png')}, data=bad_data)
        assert r.status_code == 422 and msg in r.json()['detail'], bad_data


def test_number_design_with_new_options_returns_metadata_and_downloads():
    r = client.post(
        '/api/number',
        files={'design': ('petals.png', _petals_png(), 'image/png')},
        data={
            'inks': '8', 'size': '900', 'mode': 'hybrid', 'detail_rescue': 'false',
            'underbase': 'true', 'underbase_choke': '2', 'trap': '1', 'film': 'true',
            'estimate': 'true', 'seam_check': 'true', 'halftone': 'am',
            'halftone_lpi': '55', 'halftone_angle': '45',
        }
    )
    assert r.status_code == 200, r.text
    j = r.json()
    n = j['number']
    opts = n['options']
    assert opts['mode'] == 'hybrid'
    assert opts['detail_rescue'] is False
    assert opts['underbase'] is True
    assert opts['underbase_choke'] == 2
    assert opts['trap'] == 1
    assert opts['film'] is True
    assert opts['estimate'] is True
    assert opts['seam_check'] is True
    assert opts['halftone'] == 'am'
    assert opts['halftone_lpi'] == 55.0
    assert opts['halftone_angle'] == 45.0
    assert isinstance(n['download_links'], list)
    assert len(n['download_links']) >= 3
    # Unsupported options was recorded safely
    assert isinstance(n['unsupported_options'], list)
