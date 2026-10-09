# LoomLab Studio

LoomLab is a local-first textile design and prepress studio. It supports non-destructive image import, perceptual palette extraction and reduction, editable color mappings, printable spot-color separations, repeat previews, seam checks, exports, and portable `.textileproj` projects.

## Windows app (no Python or Node needed)

`LoomLab-Studio.exe` is a single file that contains everything. Double-click it: a small window shows the address and the browser opens on LoomLab. Close that window to quit. Working files are kept in `%LOCALAPPDATA%\LoomLab\data`.

Where to get it:

- **Releases** — every version tag (`git tag v1.0.0 && git push origin v1.0.0`) publishes the `.exe` on the repository's Releases page.
- **Latest build** — every push builds it: open the *Windows app* run under the repository's **Actions** tab and download `LoomLab-Studio-windows` (requires being signed in to GitHub).

The `.exe` is not code-signed, so the first time Windows SmartScreen may say "Windows protected your PC": click **More info → Run anyway**. The first start takes a few seconds while it unpacks.

To build it yourself on Windows:

```powershell
cd frontend; npm ci; npm run build; cd ..
pip install -r backend/requirements.txt -r packaging/requirements-build.txt
pyinstaller packaging/loomlab.spec          # -> dist\LoomLab-Studio.exe
```

## Run from source

On Windows, double-click `run-windows.bat` — it sets up both servers on first run and opens the browser.

Or start them by hand:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite (normally `http://localhost:5173`). The Vite dev server forwards `/api` to the backend on port **8003**, so the backend must run on that port.

You can import by clicking **Import Design** or by dropping a file anywhere on the window. Supported: PNG, JPG, WEBP, TIFF (including 16-bit greyscale scans) and PSD (layered, or Multichannel with one pre-separated screen per channel).

## Production output

- **Ink names** — click an ink's name in the Layers panel to rename it (e.g. `1 RED 120`). Names are used for every exported file and PSD channel.
- **Trapping** — the *Trapping (spread)* slider in Export grows each lighter ink under the darker inks it touches (typically 1–3 px at 300 DPI), so a slightly mis-registered screen never shows a gap of bare fabric. It applies to every ink export: screens, plates, layer PNGs, vectors and the PSD. The Plates view previews it live: each plate shows the trapped version with the added spread highlighted, an *Overlap map* shows where inks overlap, and clicking a plate opens it at up to 8× to check the spread pixel by pixel.
- **Multichannel PSD** — one Photoshop file with a named spot channel per ink (black = ink), with the ink colour, 300 DPI and optional registration marks. It is the format mills exchange separations in, and LoomLab imports it back as the same named screens.

## Projects

**Save Project** downloads a self-contained `.textileproj` file (a zip holding the original and current images, every separated layer, the palette and the panel settings). **Open Project** — or dropping the file onto the window — restores the whole workspace, on any machine and at any time.

Working images on the server are temporary: they are removed after 48 hours without use (`CLEANUP_EXPIRY_HOURS`). Save a project to keep your work.

## Architecture

- `backend/app/color_engine`: LAB / CIEDE2000 palette analysis, importance-ranked reduction, colour mapping
- `backend/app/separation_engine`: per-ink masks (flat, tonal), colour plates, print-ready screens, compositing
- `backend/app/region_engine`: region flattening — one flat colour per outlined shape
- `backend/app/vector_engine`: Bezier tracing of separations to SVG
- `backend/app/halftone_engine`: halftone dot previews
- `backend/app/repeat_engine`: straight / brick / half-drop / mirror repeats and seam scoring
- `backend/app/design_ai`: Design DNA analysis and prompt instructions for an external AI image generator (no model runs here)
- `backend/app/project_engine`: portable `.textileproj` packing and unpacking
- `backend/app/core`: temporary image store, PSD import, registration marks, zip export
- `frontend/src`: React workspace, tool panels, and canvas previews

## Tests and CI

```powershell
cd backend
pytest
```

GitHub Actions runs on every push and pull request: *Tests* runs the backend suite on Linux (Python 3.11 and 3.13) and Windows and builds the UI; *Windows app* builds `LoomLab-Studio.exe`, starts it and runs `packaging/smoke_test.py` against it (the UI is served and a sample goes through analysis, separation, PSD and SVG export) before uploading it.

A built UI can also be served by the backend itself — `npm run build`, then `python backend/launcher.py` runs everything on one port, the same way the `.exe` does.

RGB-to-CMYK previews are intentionally approximate. Production ICC transforms should be connected through the export engine before press output.
