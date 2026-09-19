# LoomLab — Textile Color-Separation Tool

A simple, offline tool for screen-printing mills: take a design, reduce it to a
printable number of inks, and generate clean, print-ready color-separated
plates — **without hurting the design's quality**.

LoomLab does **not** generate artwork. It processes a design you already have
(from a client, or one you made elsewhere) through four steps:

1. **Upload** — PNG, JPG, WEBP, TIFF, or PSD (up to 80 MB). Before/after preview.
2. **Reduce** — bring the colors down to a printable count (2–20 inks), with a
   measured accuracy score. Fine-tune the palette: recolor, merge, or lock inks.
3. **Separate** — one flat screen per ink. Every pixel prints on exactly one
   plate — no overlap, no muddy fringe.
4. **Export** — a single `.zip` with color PNG plates, print-ready B&W TIFF
   screens (300 DPI) with registration marks, a full-color proof, and
   (optional) scalable **SVG** vector outlines.

Transparent PNGs are handled correctly: a transparent background carries no
ink — it never becomes a plate or wastes an ink slot.

## Quality bar

The reduced design looks like the original — only with fewer colors: smooth
edges, no lost detail, no torn shapes. Reduction removes colors, not quality.
This is achieved with:

- an **edge-aware LAB k-means**: anti-aliased transition bands are excluded so
  no ink is wasted on a blend colour — the cause of muddy halos;
- a **thin-feature detector** so genuine fine linework (stems, outlines, veins)
  is kept even though it reads as "edge" — a smooth transition equals the local
  blur, a thin line is a spike far from it;
- **CIEDE2000** perceptual merging of near-duplicate colours; and
- a majority-filter edge cleanup that protects those thin features.

A measured reconstruction accuracy (mean ΔE2000, over printed pixels only)
scores every palette so tuning is objective, not guesswork.

## Run on Windows

Double-click **`run-windows.bat`**. It sets up the backend and frontend the
first time, then opens the app in your browser.

## Run manually

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

Frontend (in another terminal):

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`).

## Architecture

- `backend/app/color_engine` — LAB palette analysis, reduction, CIEDE2000
  merging, measured reconstruction accuracy.
- `backend/app/separation_engine` — mutually-exclusive flat spot-color screens
  and per-plate proofs.
- `backend/app/vector_engine` — pixel-boundary contour tracing to clean,
  hole-aware (even-odd) SVG outlines.
- `backend/app/core` — image store, PSD import (including pre-separated
  multichannel PSDs), registration marks, zip packaging.
- `frontend/src` — the four-step React workspace.

Everything runs locally; no external AI or API is used for color processing.

## Tests

```bash
cd backend
pytest
```
