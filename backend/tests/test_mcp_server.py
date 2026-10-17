"""The MCP server: an AI operator driving the real engine through its tools."""
import base64
import io
import json

import pytest
from PIL import Image, ImageDraw

from app import mcp_server as M
from app.bot_orders import Engine
from conftest import LocalEngine


def design(path, size=(600, 400)):
    im = Image.new('RGB', size, '#F4ECD8')
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 300, 300], fill='#8A1C1C')
    d.rectangle([340, 80, 540, 320], fill='#1F4E9C')
    im.save(path)
    return path


@pytest.fixture
def server(tmp_path):
    inbox = tmp_path / 'Designs-Inbox'
    (inbox / '2026-09-29').mkdir(parents=True)
    return M.Server(M.LoomLabTools(LocalEngine(), inbox)), inbox


def rpc(server, method, params=None, mid=1):
    return server.handle({'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': params or {}})


def call(server, name, **args):
    r = rpc(server, 'tools/call', {'name': name, 'arguments': args})['result']
    return r, '\n'.join(c['text'] for c in r['content'] if c['type'] == 'text')


def job_id_of(text):
    return text.split()[1]


def test_the_handshake_and_the_tool_list(server):
    s, _ = server
    init = rpc(s, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                 'clientInfo': {'name': 't', 'version': '1'}})['result']
    assert init['protocolVersion'] == '2025-06-18' and init['capabilities'] == {'tools': {}}
    assert 'operator' in init['instructions']
    assert rpc(s, 'initialize', {'protocolVersion': '1999-01-01'})['result']['protocolVersion'] == M.PROTOCOLS[0]
    assert s.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) is None
    assert rpc(s, 'ping')['result'] == {}
    tools = rpc(s, 'tools/list')['result']['tools']
    assert {t['name'] for t in tools} == {'separate_design', 'rerun_job', 'get_job', 'list_jobs', 'mark_job',
                                          'quote_job', 'save_package', 'list_inbox', 'preview_colourway', 'job_stats',
                                          'find_design', 'repeat_quote', 'make_colourway_job', 'client_summary', 'engine_report'}
    for t in tools:
        assert t['description'] and t['inputSchema']['type'] == 'object'
    assert rpc(s, 'nope')['error']['code'] == -32601
    assert rpc(s, 'tools/call', {'name': 'rm_rf'})['error']['code'] == -32602


def test_a_design_goes_through_and_the_operator_sees_the_proof(server, tmp_path):
    s, inbox = server
    f = design(inbox / '2026-09-29' / '101500_Ravi_rose.png')
    r, text = call(s, 'separate_design', file=str(f), meters=500, client='Ravi')
    assert not r['isError'], text
    assert 'Status: ' in text and 'Inks (3' in text and 'Quote' in text
    img = [c for c in r['content'] if c['type'] == 'image']
    assert len(img) == 1 and img[0]['mimeType'] == 'image/png'
    proof = Image.open(io.BytesIO(base64.b64decode(img[0]['data'])))
    assert max(proof.size) <= M.PROOF_SIDE
    job = job_id_of(text)

    # the inbox now shows the job made from the file
    _, listing = call(s, 'list_inbox')
    assert f'-> job {job}' in listing

    # compare with the original, then re-run with fewer inks
    r, text = call(s, 'get_job', job_id=job, with_original=True)
    assert sum(c['type'] == 'image' for c in r['content']) == 2 and 'Original design' in text
    r, text = call(s, 'rerun_job', job_id=job, colors=2)
    assert not r['isError'] and 'Inks (2' in text and job_id_of(text) != job
    assert 'Ravi' in json.dumps(LocalEngine().get(f'/api/auto/{job_id_of(text)}')['client'])

    # mark it, price it, save the zip (twice: the first is never overwritten)
    _, text = call(s, 'mark_job', job_id=job, stage='reviewed', note='proof checked')
    assert "'reviewed'" in text
    rep = LocalEngine().get(f'/api/auto/{job}')
    assert rep['stage'] == 'reviewed' and rep['history'][-1]['by'] == 'AI operator'
    r, text = call(s, 'quote_job', job_id=job, meters=1200)
    assert not r['isError'] and '1200 m' in text and 'GST' in text and 'own rates' not in text
    from app.core import quote as costing
    card = tmp_path / 'rate-card.json'
    card.write_text(json.dumps({'clients': {'Ravi': {'margin_percent': 2}}}), encoding='utf-8')
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(costing, 'CARD_PATH', card)
        _, text = call(s, 'quote_job', job_id=job, meters=1200, client='ravi')
    assert "Ravi's own rates" in text
    out = tmp_path / 'out'; out.mkdir()
    _, a = call(s, 'save_package', job_id=job, folder=str(out))
    _, b = call(s, 'save_package', job_id=job, folder=str(out))
    zips = sorted(p.name for p in out.iterdir())
    assert len(zips) == 2 and all(z.endswith('.zip') for z in zips) and a != b


def test_waiting_jobs_are_listed_for_the_operator(server, monkeypatch, tmp_path):
    from app import auto as auto_mode
    from app.core import store
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'cache')
    (tmp_path / 'cache').mkdir()
    cfg = tmp_path / 'auto.json'
    cfg.write_text(json.dumps({'max_inks': 1}), encoding='utf-8')      # every job is held
    monkeypatch.setattr(auto_mode, 'CONFIG_PATH', cfg)
    s, inbox = server
    _, text = call(s, 'list_jobs')
    assert 'No jobs waiting' in text
    _, made = call(s, 'separate_design', file=str(design(inbox / 'a.png')))
    assert 'needs_review' in made and 'STOPS THE JOB [many_inks]' in made
    _, text = call(s, 'list_jobs')
    assert job_id_of(made) in text and '1 waiting for a person' in text and 'many_inks' in text
    call(s, 'mark_job', job_id=job_id_of(made), stage='rejected', note='too many screens')
    _, text = call(s, 'list_jobs')
    assert 'No jobs waiting' in text
    _, text = call(s, 'list_jobs', show='all')
    assert job_id_of(made) in text
    _, text = call(s, 'job_stats', days=7)
    assert 'Last 7 days: 1 designs (1 runs), 0 needed nobody' in text and 'rejected 1' in text


def test_mistakes_come_back_as_tool_errors_not_crashes(server, tmp_path):
    s, inbox = server
    for args in ({'file': str(tmp_path / 'nothing.png')}, {'file': str(tmp_path)}):
        r, text = call(s, 'separate_design', **args)
        assert r['isError'] and 'No file' in text
    (tmp_path / 'notes.txt').write_text('hi')
    r, text = call(s, 'separate_design', file=str(tmp_path / 'notes.txt'))
    assert r['isError'] and 'not a design file' in text
    r, text = call(s, 'get_job', job_id='0' * 12)
    assert r['isError'] and 'no longer available' in text
    r, text = call(s, 'save_package', job_id='0' * 12, folder=str(tmp_path / 'missing'))
    assert r['isError'] and 'No folder' in text
    r, text = call(s, 'list_inbox', folder=str(tmp_path / 'missing'))
    assert r['isError']


def test_an_engine_that_is_not_running_is_said_plainly(tmp_path):
    s = M.Server(M.LoomLabTools(Engine('http://127.0.0.1:9', timeout=2), tmp_path))
    r, text = call(s, 'list_jobs')
    assert r['isError'] and 'not running' in text


def test_the_stdio_loop_answers_one_line_per_request():
    class Tools:
        pass
    s = M.Server(Tools())
    lines = [json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode() + b'\n', b'\n', b'{broken\n',
             json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}).encode() + b'\n',
             json.dumps({'jsonrpc': '2.0', 'id': 'x', 'method': 'tools/list'}).encode() + b'\n']
    out = io.BytesIO()
    M.serve(s, stdin=iter(lines), stdout=out)
    answers = [json.loads(l) for l in out.getvalue().splitlines()]
    assert [a.get('id') for a in answers] == [1, None, 'x']
    assert answers[1]['error']['code'] == -32700 and 'tools' in answers[2]['result']


def test_setup_names_this_pcs_python_and_the_server():
    text = M.setup_text()
    assert 'mcpServers' in text and 'claude mcp add loomlab' in text and 'mcp_server.py' in text


def test_install_keeps_the_rest_of_claude_desktops_settings(tmp_path):
    cfg = tmp_path / 'Claude' / 'claude_desktop_config.json'
    assert M.install_desktop(cfg) == str(cfg)                       # no file yet: made
    assert json.loads(cfg.read_text())['mcpServers']['loomlab']['args'][0].endswith('mcp_server.py')
    cfg.write_text(json.dumps({'mcpServers': {'files': {'command': 'x'}}, 'theme': 'dark'}), encoding='utf-8')
    M.install_desktop(cfg)
    got = json.loads(cfg.read_text())
    assert got['theme'] == 'dark' and set(got['mcpServers']) == {'files', 'loomlab'}
    assert json.loads((tmp_path / 'Claude' / 'claude_desktop_config.json.bak').read_text())['theme'] == 'dark'
    cfg.write_text('{broken', encoding='utf-8')
    with pytest.raises(SystemExit):
        M.install_desktop(cfg)
    assert cfg.read_text() == '{broken'                               # left alone


def test_colourways_are_previewed_and_packed_on_the_same_screens(server, tmp_path):
    import zipfile
    s, inbox = server
    _, made = call(s, 'separate_design', file=str(design(inbox / 'rose.png')))
    job = job_id_of(made)
    inks = LocalEngine().get(f'/api/auto/{job}')['inks']
    navy = ['#1F2A44', '#C9A227', '#DDEEFF'][:len(inks)]
    r, text = call(s, 'preview_colourway', job_id=job, inks=navy)
    assert not r['isError'] and sum(c['type'] == 'image' for c in r['content']) == 1
    r, text = call(s, 'preview_colourway', job_id=job, inks=navy[:1])
    assert r['isError'] and f'give exactly {len(inks)} colours' in text
    out = tmp_path / 'pkg'; out.mkdir()
    r, text = call(s, 'save_package', job_id=job, folder=str(out),
                   colourways=[{'name': 'Navy', 'inks': navy}, {'name': 'Rust', 'inks': ['#8B3A1A', '#F2E3C6', '#3B3B3B'][:len(inks)]}])
    assert not r['isError'], text
    (zp,) = out.iterdir()
    z = zipfile.ZipFile(zp)
    names = z.namelist()
    assert {'colourways/Navy/proof.png', 'colourways/Rust/job-sheet.png'} <= set(names)
    assert 'screen 1 = #1F2A44' in z.read('README.txt').decode() or '= #1F2A44' in z.read('README.txt').decode()
    # the films are the job's own films, byte for byte
    orig = zipfile.ZipFile(io.BytesIO(LocalEngine().fetch(f'/api/auto/{job}/package')))
    films = [n for n in orig.namelist() if n.startswith('screens/')]
    assert films and all(z.read(n) == orig.read(n) for n in films)
    # made a job of its own: marked like any job
    r, text = call(s, 'make_colourway_job', job_id=job, inks=navy, meters=300)
    assert not r['isError'] and f'a colourway of job {job}' in text and sum(c['type'] == 'image' for c in r['content']) == 1
    cw = LocalEngine().get(f'/api/auto/{job_id_of(text)}')
    assert cw['colourway_of'] == job and cw['quote']['meters'] == 300


def test_a_rerun_keeps_what_the_job_was_made_with(server):
    s, inbox = server
    _, made = call(s, 'separate_design', file=str(design(inbox / 'rose.png')), fabric='#1f2a44',
                   underbase=True, width_in=3, meters=250, client='Ravi')
    r, text = call(s, 'rerun_job', job_id=job_id_of(made), colors=2)
    assert not r['isError'], text
    new = LocalEngine().get(f'/api/auto/{job_id_of(text)}')
    assert new['settings']['fabric'] == '#1F2A44' and new['underbase'] and new['settings']['width_in'] == 3
    assert new['quote']['meters'] == 250 and new['client'] == 'Ravi' and len(new['inks']) == 2


def test_wrong_arguments_are_tool_errors_and_the_server_lives_on(server):
    s, _ = server
    for name, args in (('separate_design', {'file': None}), ('save_package', {'job_id': 'x', 'folder': '.',
                                                                             'colourways': ['A']})):
        r = rpc(s, 'tools/call', {'name': name, 'arguments': args})
        assert r['result']['isError']
    assert rpc(s, 'ping')['result'] == {}


def test_a_repeat_order_is_found_in_the_library_and_priced(server, tmp_path, monkeypatch):
    from app.core import store
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'cache'); (tmp_path / 'cache').mkdir()
    s, inbox = server
    _, text = call(s, 'find_design', query='rose')
    assert 'library is empty' in text or 'No approved design' in text
    _, made = call(s, 'separate_design', file=str(design(inbox / 'rose.png')), client='Ravi', meters=300)
    call(s, 'mark_job', job_id=job_id_of(made), stage='approved')
    r, text = call(s, 'find_design', query='ravi', with_proofs=True)
    assert job_id_of(made) in text and sum(c['type'] == 'image' for c in r['content']) == 1
    r, text = call(s, 'repeat_quote', library_id=job_id_of(made), meters=1000)
    assert not r['isError'] and 'no new screens' in text and '1000 m' in text


def test_the_operator_asks_how_a_client_is_doing(server):
    s, inbox = server
    _, made = call(s, 'separate_design', file=str(design(inbox / 'zeta.png')), client='Zeta Prints', meters=150)
    call(s, 'mark_job', job_id=job_id_of(made), stage='approved')
    r, text = call(s, 'client_summary', client='zeta')
    assert not r['isError'] and 'Zeta Prints: 1 designs, 1 approved (150 m)' in text and 'business' in text
    _, text = call(s, 'client_summary', client='nobody-like-this')
    assert "No client orders in the last 90 days matching 'nobody-like-this'" in text


def test_a_photo_like_job_can_be_run_again_as_dots(server, tmp_path):
    import numpy as np
    from PIL import ImageFilter
    s, inbox = server
    yy, xx = np.mgrid[0:240, 0:320]
    img = Image.fromarray(np.stack([80 + 150 * xx / 320, 60 + 160 * yy / 240, 200 - 120 * xx / 320], -1)
                          .clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))
    path = inbox / 'photo.png'; img.save(path)
    _, made = call(s, 'separate_design', file=str(path), colors=5)
    assert 'photographic' in made
    r, text = call(s, 'rerun_job', job_id=job_id_of(made), dots=True)
    assert not r['isError'] and 'printed as dots (index separation)' in text and 'photographic' not in text


def test_the_engines_health_is_one_tool_away(server):
    s, _ = server
    r, text = call(s, 'engine_report')
    assert not r['isError'] and text.startswith('LoomLab report') and '[system]' in text and '[errors since start' in text


def test_a_dotted_jobs_colourways_are_packed_as_dots(server, tmp_path):
    import zipfile
    s, inbox = server
    _, made = call(s, 'separate_design', file=str(design(inbox / 'rose.png')), dots=True)
    job = job_id_of(made)
    rep = LocalEngine().get(f'/api/auto/{job}')
    assert rep['dots']
    out = tmp_path / 'pkg'; out.mkdir()
    r, text = call(s, 'save_package', job_id=job, folder=str(out),
                   colourways=[{'name': 'Navy', 'inks': ['#1F2A44'] * len(rep['inks'])}])
    assert not r['isError'], text
    (zp,) = out.iterdir()
    z = zipfile.ZipFile(zp)
    assert 'Index separation' in z.read('README.txt').decode() and 'colourways/Navy/proof.png' in z.namelist()
