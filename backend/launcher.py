"""LoomLab Studio desktop launcher -- the entry point of the packaged app
(LoomLab-Studio.exe), also runnable from source with `python launcher.py`.

It runs the API and the built UI as one local server, opens the browser on
it, and keeps running until its window is closed. Working images live in
the user's own app-data folder, because a packaged app's install folder may
be read-only and a one-file build unpacks into a temporary folder that is
deleted on exit.
"""
import argparse
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = 'LoomLab Studio'
PREFERRED_PORT = 8003


def data_dir() -> Path:
    if os.environ.get('DATA_DIR'):
        return Path(os.environ['DATA_DIR'])
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return base / 'LoomLab' / 'data'


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def pick_port(preferred: int = PREFERRED_PORT) -> int:
    """The usual port when it is free (e.g. the dev backend isn't running),
    otherwise any free one -- so a second copy never fails to start."""
    if port_is_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def open_when_ready(url: str, timeout: float = 90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + 'api/health', timeout=2) as r:
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(0.4)


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'Run {APP_NAME} locally.')
    parser.add_argument('--port', type=int, help=f'port to serve on (default {PREFERRED_PORT}, or any free port)')
    parser.add_argument('--no-browser', action='store_true', help="don't open the browser")
    args = parser.parse_args(argv)

    # must be set before the app is imported: the image store reads DATA_DIR at import
    os.environ.setdefault('DATA_DIR', str(data_dir()))
    port = args.port or pick_port()
    url = f'http://127.0.0.1:{port}/'

    import uvicorn
    from app.main import app, ui_dir

    print(f'\n  {APP_NAME} is running at {url}')
    print(f'  Working files: {os.environ["DATA_DIR"]}')
    if ui_dir() is None:
        print('  (No built UI found -- run "npm run build" in frontend/, or use the Vite dev server.)')
    print('  Close this window to quit.\n', flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
