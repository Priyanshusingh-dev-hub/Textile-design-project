"""Tests never touch the real working folder: without this every test run
left its auto-mode jobs in backend/data, and they showed up on the job
dashboard as real orders waiting for review."""
import os
import shutil
import tempfile

_DATA = tempfile.mkdtemp(prefix='loomlab-test-data-')
os.environ['DATA_DIR'] = _DATA   # read by app.core.store at import, so it is set before any test imports it
os.environ.setdefault('TEXTILE_LEARN_LOG', os.path.join(_DATA, 'number-log.jsonl'))   # textile number's own memory


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_DATA, ignore_errors=True)


class LocalEngine:
    """The bot's Engine (also used by the MCP server and the hot folder), its
    HTTP answered by the real API in-process: every request and error path
    but the socket itself."""

    def __new__(cls):
        import urllib.request
        from fastapi.testclient import TestClient
        from app.bot_orders import Engine, EngineError
        from app.main import app

        class _Local(Engine):
            def _open(self, req: urllib.request.Request):
                path = req.full_url[len(self.base):]
                r = self.client.request(req.get_method(), path, content=req.data,
                                        headers={k: v for k, v in req.header_items()})
                if r.status_code >= 400:
                    detail = r.json().get('detail') if 'json' in r.headers.get('content-type', '') else r.text
                    raise EngineError(str(detail))
                return r.content

        eng = _Local('http://engine')
        eng.client = TestClient(app)
        return eng
