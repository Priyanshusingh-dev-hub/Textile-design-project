import asyncio
from pathlib import Path
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from .core import store
from . import diagnostics, licence
from .color_engine import engine as colors  # noqa: F401  (tests patch main.colors)
from .routes import automation, export, images, licence_routes, palette, plates, settings
# names other code and the tests reach through app.main
from .routes.common import MAX_PRINT_PX, image_meta, image_response  # noqa: F401
from .routes.images import _INK_WORDS, _ink_from_name, _overlap  # noqa: F401
from .routes.export import _build_package  # noqa: F401

CLEANUP_INTERVAL_SECONDS = float(os.environ.get('CLEANUP_INTERVAL_SECONDS', 3600))


async def _cleanup_loop():
    while True:
        try:
            store.cleanup_expired()
        except Exception:
            pass
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    store.cleanup_expired()  # clear stale files once at boot
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title='LoomLab API', version='1.0.0', lifespan=lifespan)
_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=['*'], allow_headers=['*'])


# Calls that work without a licence: the engine answering at all, and
# activating it. Everything else waits for a licence once one is required.
_OPEN = ('/api/health', '/api/licence', '/api/diagnostics')   # help works while locked, too


@app.middleware('http')
async def _licence_gate(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/') and not path.startswith(_OPEN):
        st = licence.status()
        if st['required'] and not st['valid']:
            return JSONResponse(status_code=402, content={'detail': st['reason'], 'licence': st})
    return await call_next(request)


@app.exception_handler(FileNotFoundError)
def _missing_image(request: Request, exc: FileNotFoundError):
    """Generated images expire (see store.cleanup_expired), so an id from an
    old tab is an ordinary 'gone', not a server fault. Answer every endpoint
    with the same actionable message instead of a 500."""
    return JSONResponse(status_code=404, content={'detail': str(exc) or 'This image is no longer available. Please import it again.'})


@app.exception_handler(Exception)
def _engine_fault(request: Request, exc: Exception):
    """A real fault (a 500): kept for Settings -> Help and its log file, and
    answered in the words the app shows for it."""
    diagnostics.record(request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={'detail': 'The engine hit a problem with this design (error 500). '
                                                            'Try again; if it keeps happening, try fewer inks or a smaller file.'})


@app.get('/api/health')
def health():
    return {'ok': True}


@app.get('/api/diagnostics')
def diagnostics_report():
    """Versions, space, what the engine holds, settings and licence health,
    and the last errors: what someone helping the mill needs to see."""
    return diagnostics.report(APP_DIST)


@app.get('/api/diagnostics/report.txt', response_class=PlainTextResponse)
def diagnostics_text():
    return PlainTextResponse(diagnostics.as_text(diagnostics.report(APP_DIST)),
                             headers={'Content-Disposition': 'attachment; filename="loomlab-report.txt"'})


# The API, one module per step or area (app/routes/). Order does not matter
# among them; the built app is mounted after all of them (serve_app).
for _module in (licence_routes, images, palette, plates, export, automation, settings):
    app.include_router(_module.router)


# The app itself, built (`npm run build`), served by the engine: one server
# and one address for the mill (http://localhost:8003), no dev server and no
# Node at run time. Mounted last, so every /api route above wins. During
# development `npm run dev` still serves it with live reload.
APP_DIST = Path(os.environ.get('LOOMLAB_APP_DIR') or Path(__file__).resolve().parents[2] / 'frontend' / 'dist')


def serve_app(api, dist: Path) -> bool:
    if not (dist / 'index.html').is_file():
        return False
    api.mount('/', StaticFiles(directory=dist, html=True), name='app')
    return True


serve_app(app, APP_DIST)
