"""Only LoomLab's own page may change things in the engine.

The engine listens on this PC only (127.0.0.1:8003), but any web page the
operator opens in the same browser can still *send* it a request: a hidden
form posting a fake backup to /api/backup/restore would replace the rate card,
the auto limits, the ink shelf and the library. CORS does not stop that (it
only stops the page from *reading* the answer), so every request that changes
something (POST, PUT, PATCH, DELETE) is checked here first:

- a browser always says which page sent it (`Origin`, or at least `Referer`);
  it must be LoomLab itself (http://localhost:8003, the dev server on :5173, or
  an origin added in ALLOWED_ORIGINS), else the answer is 403;
- a request with neither header is not from a web page (the Telegram bot, the
  MCP server, the hot folder, a script), so it goes through, unless the browser
  marks it cross-site (`Sec-Fetch-Site`).

Reading (GET) is left alone: the app's own <img> and download links carry no
Origin, and a foreign page cannot read the answer anyway. The Host check
(TrustedHostMiddleware in main.py, LOOMLAB_ALLOWED_HOSTS) stops a page from
reaching the engine under its own domain name (DNS rebinding).
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# LoomLab's own page: served by the engine (run-windows.bat) or by `npm run dev`
DEFAULT_ORIGINS = ('http://localhost:8003', 'http://127.0.0.1:8003',
                   'http://localhost:5173', 'http://127.0.0.1:5173')
DEFAULT_HOSTS = ('localhost', '127.0.0.1')

REFUSED = ('LoomLab refused this request: it came from another web page ({origin}), not from LoomLab itself. '
           'Open LoomLab at http://localhost:8003 and try again.')


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(',') if v.strip()]


def allowed_hosts() -> list[str]:
    """Host names the engine answers to (LOOMLAB_ALLOWED_HOSTS, comma-separated)."""
    return _split(os.environ.get('LOOMLAB_ALLOWED_HOSTS', '')) or list(DEFAULT_HOSTS)


def allowed_origins() -> set[str]:
    """LoomLab's own origins plus any in ALLOWED_ORIGINS (the CORS list)."""
    extra = _split(os.environ.get('ALLOWED_ORIGINS', ''))
    return {o.rstrip('/').lower() for o in (*DEFAULT_ORIGINS, *extra)}


def _origin_of(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return f'{parts.scheme}://{parts.netloc}'.lower()


class OriginGuard:
    """ASGI middleware: refuse state-changing requests sent by another site."""

    def __init__(self, app, origins: set[str] | None = None, hosts: list[str] | None = None):
        self.app = app
        self.origins = origins if origins is not None else allowed_origins()
        self.hosts = {h.lower() for h in (hosts if hosts is not None else allowed_hosts())}

    def _same_origin(self, origin: str, scope) -> bool:
        """The page the engine itself served, on whatever port it was started
        (uvicorn --port 8010): the Origin equals this request's own address,
        and that address is one of the trusted host names."""
        headers = dict(scope.get('headers') or [])
        host = headers.get(b'host', b'').decode('latin-1').lower()
        if not host or host.split(':')[0] not in self.hosts:
            return False
        return origin == f"{scope.get('scheme', 'http')}://{host}"

    def verdict(self, scope) -> str | None:
        """None when the request may go on, else the origin it came from."""
        if scope.get('method', 'GET').upper() not in UNSAFE_METHODS:
            return None
        headers = dict(scope.get('headers') or [])
        origin = headers.get(b'origin', b'').decode('latin-1').strip().lower()
        referer = headers.get(b'referer', b'').decode('latin-1').strip()
        site = headers.get(b'sec-fetch-site', b'').decode('latin-1').strip().lower()
        if origin:
            if origin == 'null':                      # a sandboxed frame or a local file
                return 'null'
            origin = origin.rstrip('/')
            return None if origin in self.origins or self._same_origin(origin, scope) else origin
        if referer:
            ref = _origin_of(referer)
            if ref and (ref in self.origins or self._same_origin(ref, scope)):
                return None
            return ref or 'unknown page'
        if site in ('cross-site', 'same-site'):
            return site
        return None                                   # not a browser: bot, MCP, hot folder, script

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            bad = self.verdict(scope)
            if bad is not None:
                body = json.dumps({'detail': REFUSED.format(origin=bad)}).encode()
                await send({'type': 'http.response.start', 'status': 403,
                            'headers': [(b'content-type', b'application/json'),
                                        (b'content-length', str(len(body)).encode())]})
                await send({'type': 'http.response.body', 'body': body})
                return
        await self.app(scope, receive, send)
