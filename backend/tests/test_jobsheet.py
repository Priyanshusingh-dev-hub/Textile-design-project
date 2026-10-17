"""The job sheet: one printable page pinned up at the press."""
import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.jobsheet import PAGE, MARGIN, build_job_sheet
from app.main import app


def _pic(hx='#C0392B'):
    return Image.new('RGB', (80, 80), hx)


@pytest.mark.parametrize('n', [1, 6, 7, 12, 20, 40, 64])
def test_sheet_fits_any_number_of_screens_on_one_page(n):
    rows = [(i + 1, f'Ink {i + 1} with a longish name', '#%02X4040' % (i * 3 % 256), 1.5, _pic()) for i in range(n)]
    sheet = build_job_sheet(rows, _pic('#EFE3C8'), title='t', print_size='12 x 12 in',
                            cloth='#FFFFFF', underbase=False, dpi=300)
    assert sheet.size == PAGE
    a = np.asarray(sheet.convert('L'))
    # nothing drawn into the side margins: text never runs off the page
    assert (a[:, :MARGIN - 20] > 250).all() and (a[:, -(MARGIN - 20):] > 250).all()


def test_every_package_carries_a_job_sheet():
    c = TestClient(app)
    im = Image.new('RGB', (120, 120), '#EFE3C8'); ImageDraw.Draw(im).ellipse((20, 20, 100, 100), fill='#C0392B')
    b = io.BytesIO(); im.save(b, 'PNG')
    info = c.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': info['image_id'], 'colors': 2, 'smoothing': 0}).json()
    lay = c.post('/api/separation/create', json={'image_id': red['image_id'],
                 'palette': [p['hex'] for p in red['palette']]}).json()['layers']
    z = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={
        'layers': [{'id': l['id'], 'name': f'Ink {i + 1}', 'color': l['color']} for i, l in enumerate(lay)],
        'fabric': '#1B2A1F', 'underbase': True}).content))
    sheet = Image.open(io.BytesIO(z.read('job-sheet.png')))
    assert sheet.size == PAGE
    assert 'job-sheet.png' in z.read('README.txt').decode()
