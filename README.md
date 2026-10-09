# LoomLab Studio

LoomLab is a local-first textile design and prepress studio. It supports non-destructive image import, perceptual palette extraction and reduction, editable color mappings, printable spot-color separations, repeat previews, seam checks, exports, and portable `.textileproj` projects.

## Run locally

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

## Tests

```powershell
cd backend
pytest
```

RGB-to-CMYK previews are intentionally approximate. Production ICC transforms should be connected through the export engine before press output.
