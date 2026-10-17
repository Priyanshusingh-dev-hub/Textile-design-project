"""Hot folder: drop a design in, get its screens out — nobody at the app.

    Hot-Folder/
      in/       put design files here (from email, WhatsApp Desktop, a pen drive)
      ready/    auto mode found nothing to worry about: films, proof, job sheet, price
      check/    auto mode held it: the same, plus why (report.txt) — a person looks
      failed/   LoomLab could not run it, with the reason

Settings can ride in the file name, the way a client writes them in a
caption: "rose 30in 500m 6inks.png" prints 30 inches wide, prices 500 m and
uses 6 inks; anything not written is chosen by the engine (and the defaults below).

When the engine is not running, files simply wait in in/ and go through once
it is back: a queue, not a lost order. A file still being copied is left
until its size stops changing. Every job is also on the app's Jobs dashboard.

    python -m app.hot_folder [FOLDER] [--width-in 30] [--meters 500] [--once]

Standard library only; talks to the running engine over HTTP like the bot.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'app'

from .bot_orders import Engine, EngineError, parse_request  # noqa: E402
from .mcp_server import DESIGN_TYPES, describe  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ('in', 'ready', 'check', 'failed', '.work')


def settings_from_name(name: str) -> dict:
    """'rose_30in_500m_6inks.png' -> {'width_in': 30, 'meters': 500, 'colors': 6}."""
    words = re.sub(r'[_\-]+', ' ', Path(name).stem)
    words = re.sub(r'(\d)(inch|in|m|mtr|inks?|colou?rs?)\b', r'\1 \2', words, flags=re.I)
    return parse_request(words)


def _unique(path: Path) -> Path:
    n, out = 2, path
    while out.exists():
        out = path.with_name(f'{path.stem}-{n}{path.suffix}')
        n += 1
    return out


class HotFolder:
    def __init__(self, engine: Engine, root: Path, defaults: dict | None = None, log=print):
        self.engine = engine
        self.root = root
        self.defaults = {k: v for k, v in (defaults or {}).items() if v is not None}
        self.log = log
        self.sizes: dict[Path, tuple] = {}     # last seen (size, mtime): a file must hold still once
        self.engine_down = False
        for f in FOLDERS:
            (root / f).mkdir(parents=True, exist_ok=True)

    def waiting(self) -> list[Path]:
        """Design files in in/ that have stopped growing, oldest first."""
        found, seen = [], {}
        for p in (self.root / 'in').iterdir():
            if p.name.startswith(('.', '~')) or p.suffix.lower() in ('.part', '.tmp', '.crdownload'):
                continue
            try:                                   # dragged out, or still locked by the copy: next time
                if not p.is_file():
                    continue
                st = p.stat()
            except OSError:
                continue
            seen[p] = (st.st_size, st.st_mtime_ns)
            if self.sizes.get(p) == seen[p] and st.st_size > 0:
                found.append((st.st_mtime_ns, p))
        self.sizes = seen
        return [p for _, p in sorted(found)]

    def poll(self) -> int:
        """One look at in/: every settled file is run. Returns how many went through."""
        done = 0
        for path in self.waiting():
            if path.suffix.lower() not in DESIGN_TYPES:
                self._fail(path, f'{path.name} is not a design file LoomLab reads '
                                 f'({", ".join(sorted(DESIGN_TYPES))}).')
                continue
            try:
                self.run(path)
                done += 1
            except EngineError as err:
                if err.down:                     # keep it queued; say so once
                    if not self.engine_down:
                        self.log(f'LoomLab engine band hai — {path.name} aur baaki files in/ me intezaar karengi.')
                    self.engine_down = True
                    return done
                self._fail(path, str(err))
            except OSError as err:               # locked by Windows / antivirus, or gone: try again next look
                self.sizes.pop(path, None)
                self.log(f'{path.name}: abhi padh nahi paaye ({err}); agli baar dobara.')
        if self.engine_down and done:
            self.log('Engine wapas aa gaya, queue chal rahi hai.')
        self.engine_down = self.engine_down and not done
        return done

    def run(self, path: Path) -> Path:
        params = {**self.defaults, **settings_from_name(path.name)}
        up = self.engine.upload(path.read_bytes(), path.name)
        if up.get('layers'):
            raise EngineError(f'{path.name} is a PSD already separated into screens; open it in the LoomLab app '
                              'and export it as it is.')
        report = self.engine.post('/api/auto', {'image_id': up['image_id'], 'name': path.name[:120], **params})
        # From here the job exists: a failure is reported with its id, never
        # left in in/ to run again (that would be a second job).
        try:
            files = {f'{path.stem}-screens.zip': self.engine.fetch(report['package_url']),
                     'proof.png': self.engine.fetch(f"/api/image/{report['reduced_id']}"),
                     'report.txt': (describe(report) + '\n').encode('utf-8')}
            if report.get('quote'):
                files['quote.png'] = self.engine.fetch(report['quote']['image_url'])
        except EngineError as err:
            raise EngineError(f"job {report['job_id']} was made (it is on the Jobs page), but its files could "
                              f"not be fetched: {err}") from None
        where = 'ready' if report['status'] == 'auto_ok' else 'check'
        # built in a work folder and moved in whole: ready/ never holds half a job
        work = self.root / '.work' / report['job_id']
        work.mkdir(parents=True, exist_ok=True)
        try:
            for name, data in files.items():
                (work / name).write_bytes(data)
            shutil.move(str(path), str(work / path.name))
            out = _unique(self.root / where / f"{datetime.now():%Y-%m-%d} {path.stem}")
            work.rename(out)
        except OSError as err:
            if (work / path.name).exists() and not path.exists():
                shutil.move(str(work / path.name), str(path))
            shutil.rmtree(work, ignore_errors=True)
            raise EngineError(f"job {report['job_id']} was made (it is on the Jobs page), but its folder could "
                              f"not be written: {err}") from None
        self.sizes.pop(path, None)
        self.log(f"{path.name}: {'taiyaar' if where == 'ready' else 'CHECK karo'} -> {out}")
        return out

    def _fail(self, path: Path, why: str) -> None:
        out = _unique(self.root / 'failed' / path.name)
        shutil.move(str(path), str(out))
        out.with_name(out.name + '.why.txt').write_text(why + '\n', encoding='utf-8')
        self.sizes.pop(path, None)
        self.log(f'{path.name}: nahi chala — {why}')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m app.hot_folder', description=__doc__.split('\n')[0])
    ap.add_argument('folder', nargs='?', default=os.environ.get('LOOMLAB_HOT_FOLDER') or str(ROOT / 'Hot-Folder'))
    ap.add_argument('--engine', default=os.environ.get('LOOMLAB_ENGINE') or 'http://localhost:8003')
    ap.add_argument('--width-in', type=float, help='print width when the file name gives none')
    ap.add_argument('--meters', type=float, help='meters to price when the file name gives none')
    ap.add_argument('--every', type=float, default=3.0, help='seconds between looks')
    ap.add_argument('--once', action='store_true', help='look twice (a file must hold still) and stop')
    a = ap.parse_args(argv)
    hot = HotFolder(Engine(a.engine, timeout=900), Path(a.folder),
                    {'width_in': a.width_in, 'meters': a.meters})
    print(f'Hot folder chal raha hai: {Path(a.folder).resolve()}')
    print(r'Design "in" folder me daalo; taiyaar jobs "ready" me, dekhne wali "check" me aayengi.')
    print('File ke naam me settings de sakte ho, jaise: rose 30in 500m 6inks.png')
    try:
        if a.once:
            hot.poll(); time.sleep(min(a.every, 1.0)); hot.poll()
            return 0
        while True:
            try:
                hot.poll()
            except Exception as err:   # one bad moment must not stop the folder for the day
                print(f'Hot folder: {err!r} — chalta rahega.')
            time.sleep(a.every)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
