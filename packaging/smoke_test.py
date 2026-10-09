"""Smoke test for a running LoomLab server (the packaged app or a dev run):
the UI is served, and one trip through the real pipeline works -- which,
for a frozen build, proves numpy, scipy, Pillow and psd-tools all made it
into the bundle.

    python packaging/smoke_test.py http://127.0.0.1:8123/
"""
import json
import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8003/').rstrip('/')


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.headers.get('content-type', ''), r.read()


def wait_until_up(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if call('/api/health')[0] == 200:
                return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f'server at {BASE} did not come up within {timeout}s')


def main():
    wait_until_up()
    status, ctype, body = call('/')
    assert status == 200 and 'text/html' in ctype and b'LoomLab' in body, 'UI is not being served'
    sample = json.loads(call('/api/image/sample', {})[2])
    palette = json.loads(call('/api/colors/analyze', {'image_id': sample['image_id'], 'colors': 6})[2])['palette']
    assert len(palette) == 4, palette                                    # numpy
    inks = [p['hex'] for p in palette]
    layers = json.loads(call('/api/separation/create', {'image_id': sample['image_id'], 'palette': inks, 'mode': 'region'})[2])['layers']
    assert len(layers) == 4                                              # scipy.ndimage
    items = [{'id': l['id'], 'name': f'{i + 1} INK', 'color': l['color']} for i, l in enumerate(layers)]
    status, ctype, psd = call('/api/export/psd-multichannel', {'layers': items, 'trap': 2})
    assert status == 200 and psd[:4] == b'8BPS'                          # psd-tools (+ its RLE codec)
    svg = call('/api/export/svg', {'layers': items})[2]
    assert svg.count(b'<path') == 4                                      # vector tracing
    print(f'smoke test ok: UI served, {len(palette)} inks, {len(layers)} layers, PSD {len(psd)} bytes, SVG {len(svg)} bytes')


if __name__ == '__main__':
    main()
