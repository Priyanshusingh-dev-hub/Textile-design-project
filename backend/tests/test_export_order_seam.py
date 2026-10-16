"""R-0010 gaps 2 and 3: films named in print order, and a repeat's films
still meet themselves edge to edge after trap and tiny-dot cleaning."""
import io
import re
import zipfile

import numpy as np
import pytest
from PIL import Image

from app.color_engine import engine as E
from app.core import store
from app.core.archive import screen_stem
from app.core.jobsheet import build_job_sheet
from app.models import PackageLayer, PackageRequest
from app.routes.export import _build_package
from app.separation_engine import engine as S
from test_repeat import _tile


# ---- gap 2: names -----------------------------------------------------------
@pytest.mark.parametrize('order, name, colour, want', [
    (1, 'Lemon', '#FFE14D', '01_Lemon_FFE14D'),
    (0, 'Underbase', '#FFFFFF', '00_Underbase_FFFFFF'),
    (12, 'Navy 3 / dark', '#1e2a4a', '12_Navy-3-dark_1E2A4A'),
    (3, 'नीला', '#2A5DA8', '03_Ink_2A5DA8'),                       # nothing safe left: 'Ink'
    (4, '..\\CON:<>|?*"', '#000000', '04_CON_000000'),             # no path or Windows-reserved characters
    (5, 'x' * 80, '#C0392B', '05_' + 'x' * 24 + '_C0392B'),              # the name part is capped at 24
    (6, 'Royal Blue / No:1 *?"<>| \\ x', '#1E2A4A', '06_Royal-Blue-No-1-x_1E2A4A'),
    (7, 'Abcdefghijklmnopqrstuvw-yz', '#ABCDEF', '07_Abcdefghijklmnopqrstuvw_ABCDEF'),   # cut at 24, no trailing '-'
])
def test_screen_stem_is_print_order_name_and_hex_and_filesystem_safe(order, name, colour, want):
    stem = screen_stem(order, name, colour)
    assert stem == want
    assert re.fullmatch(r'\d\d_[A-Za-z0-9.-]{1,24}_[0-9A-F]{6}', stem) and stem.isascii()
    assert not set(stem) & set(' /\\:*?"<>|')


def _named_package(names_colours, **kw):
    """Hard-edged vertical bands, one per (name, ink), as a package request."""
    w = 30 * len(names_colours)
    layers = []
    for i, (name, hx) in enumerate(names_colours):
        a = np.zeros((40, w, 4), np.uint8); a[:, 30 * i:30 * (i + 1), 3] = 255
        layers.append(PackageLayer(id=store.save(Image.fromarray(a)), name=name, color=hx))
    return PackageRequest(layers=layers, dpi=300, reg_marks=False, **kw)


def test_two_inks_of_one_name_stay_apart_by_order_and_hex():
    data, _ = _build_package(_named_package([('Red', '#C0392B'), ('Red', '#E63946')]))
    films = sorted(n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.startswith('screens/'))
    assert films == ['screens/01_Red_E63946.tif', 'screens/02_Red_C0392B.tif']   # lighter red prints first


def test_readme_and_job_sheet_name_the_screens_exactly_as_the_zip_does(monkeypatch):
    from app.routes import export as export_routes
    sheets = []
    real = export_routes.build_job_sheet
    monkeypatch.setattr(export_routes, 'build_job_sheet',
                        lambda rows, *a, **k: sheets.append([r[1] for r in rows]) or real(rows, *a, **k))
    req = _named_package([('Lemon', '#FFE14D'), ('Royal Blue / No:1', '#1E2A4A'), ('Red', '#C0392B'),
                          ('Red', '#E63946'), ('x' * 30, '#6B4530')],
                         fabric='#101010', underbase=True, vector=True)
    data, _ = _build_package(req)
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    stems = [n[len('screens/'):-len('.tif')] for n in names if n.startswith('screens/')]
    assert stems[0] == '00_Underbase_FFFFFF' and stems == sorted(stems) and len(stems) == 6
    assert [n[len('plates/'):-len('.png')] for n in names if n.startswith('plates/')] == stems
    assert [n[len('vector/'):-len('.svg')] for n in names
            if n.startswith('vector/') and n != 'vector/design.svg'] == stems[1:]       # no SVG for the under-base
    readme = z.read('README.txt').decode().splitlines()
    at = next(i for i, line in enumerate(readme) if line.startswith('Screens in print order'))
    assert [line.strip() for line in readme[at + 1:at + 1 + len(stems)]] == stems
    assert sheets == [stems]                                                     # the one job sheet, same names


# ---- gap 3: the seam ----------------------------------------------------------
def _repeat_with_specks():
    """The repeat tile of test_repeat.py, reduced to 5 inks, with 2x2 dots of
    one ink inside another (some next to the seam): too small for a 0.3 mm
    mesh at 300 DPI (dot area 9 px), so cleaning has work to do."""
    red, pal = E.quantize_full(_tile(), 5, 1)
    a = np.asarray(red.convert('RGB')).copy()
    cols = [np.array(E.hex_rgb(p.hex), np.uint8) for p in pal]
    for k, (y, x) in enumerate([(30, 30), (100, 60), (180, 200), (60, 2), (2, 120), (200, 236)]):
        a[y:y + 2, x:x + 2] = cols[k % len(cols)] if not (a[y, x] == cols[k % len(cols)]).all() else cols[(k + 1) % len(cols)]
    return Image.fromarray(a), [p.hex for p in pal]


def _package(design, pal, **kw):
    layers = S.create(design, pal, 0)
    req = PackageRequest(layers=[PackageLayer(id=store.save(m), name=f'Ink {i + 1}', color=hx)
                                 for i, (hx, m, _) in enumerate(layers)],
                         dpi=300, reg_marks=False, trap_px=2, min_dot_mm=0.3, **kw)
    return layers, req


def _films(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: np.asarray(Image.open(io.BytesIO(z.read(n)))) < 128
            for n in sorted(z.namelist()) if n.startswith('screens/')}


def test_a_repeat_stays_seamless_through_trap_and_tiny_dot_cleaning(monkeypatch):
    """One regression test for R-0010 row 5: repeat + trap 2 px + tiny-dot clean-up.

    (a) At the design's own size the films of the tile, and of the same tile
        started elsewhere (rolled), are the same films rolled: no step treats
        the tile's edge as a wall. Exact, pixel for pixel.
    (b) Enlarged to print width too, the job sheet / README seam check says OK.
    Both are shown to fail when the steps stop wrapping."""
    design, pal = _repeat_with_specks()
    assert E.repeat_to_report(design) == (True, True)
    layers, req = _package(design, pal)
    assert sum(d for d, _ in S.speck_report([m for _, m, _ in layers], S.dot_area(0.3, 300))) >= 4
    data, made = _build_package(req)
    films = _films(data)
    assert (sum(f.astype(int) for f in films.values()) > 1).any()          # the trap really spread a film
    from scipy import ndimage
    for f in films.values():                                                # and the tiny dots really went
        lab, _ = ndimage.label(f, structure=np.ones((3, 3)))
        assert (np.bincount(lab.ravel())[1:] > 9).all()

    def rolled_films(shift):
        moved = Image.fromarray(np.roll(np.asarray(design), shift, (0, 1)))
        out = _films(_build_package(_package(moved, pal)[1])[0])
        assert out.keys() == films.keys()
        return {n: np.roll(f, (-shift[0], -shift[1]), (0, 1)) for n, f in out.items()}

    shifts = [(40, 0), (17, 83)]
    for shift in shifts:
        back = rolled_films(shift)
        assert all(np.array_equal(films[n], back[n]) for n in films), shift
    assert made['seams'] == {'L-R': True, 'T-B': True}

    big, made_big = _build_package(_package(design, pal, width_in=2.0)[1])     # 600 px, enlarged 2.5x
    assert made_big['seams'] == {'L-R': True, 'T-B': True}
    assert 'Repeat seam check on the films (after resize, trap and dot cleaning): L-R OK · T-B OK' \
        in zipfile.ZipFile(io.BytesIO(big)).read('README.txt').decode()

    # the test bites: every step treating the edge as a wall
    monkeypatch.setattr(S, '_repeat_axes', lambda label: (False, False))
    films = _films(_build_package(_package(design, pal)[1])[0])
    assert any(not all(np.array_equal(films[n], f) for n, f in rolled_films(s).items()) for s in shifts)
    walled, made_walled = _build_package(_package(design, pal, width_in=2.0)[1])
    assert not all(made_walled['seams'].values())
    readme = zipfile.ZipFile(io.BytesIO(walled)).read('README.txt').decode()
    assert 'FAIL' in readme and 'check that edge before engraving' in readme


def test_a_design_that_is_not_a_repeat_gets_no_seam_line():
    im = Image.new('RGB', (120, 90), '#F4E8CC')
    im.paste('#C0392B', (20, 20, 70, 60))
    red, pal = E.quantize_full(im, 2, 0)
    _, req = _package(red, [p.hex for p in pal])
    data, made = _build_package(req)
    assert made['seams'] == {}
    assert 'Repeat seam' not in zipfile.ZipFile(io.BytesIO(data)).read('README.txt').decode()


def test_job_sheet_carries_the_seam_line_red_when_it_fails():
    rows = [(1, 'Ink 1', '#C0392B', 50.0, Image.new('RGB', (40, 40), '#C0392B'))]
    kw = dict(title='t', print_size='1 x 1 in', cloth='#FFFFFF', underbase=False, dpi=300)
    plain = np.asarray(build_job_sheet(rows, None, **kw))
    ok = np.asarray(build_job_sheet(rows, None, seam='L-R OK · T-B OK', **kw))
    bad = np.asarray(build_job_sheet(rows, None, seam='L-R OK · T-B FAIL', **kw))
    assert not np.array_equal(plain, ok)
    red = lambda a: ((a[:, :, 0] > 150) & (a[:, :, 1] < 90) & (a[:, :, 2] < 70)).sum()
    assert red(bad) > red(ok)


def test_job_sheet_prints_a_capped_file_name_whole_not_cut():
    from PIL import ImageDraw
    from app.core import jobsheet
    d = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    stem = screen_stem(20, 'x' * 80, '#C0392B')                 # the longest a stem gets: 34 characters
    assert len(stem) == 34
    f = jobsheet._shrink_to_fit(d, stem, 26, 300)              # 300 px: the room in a 2-column sheet
    assert d.textlength(stem, font=f) <= 300
