# LoomLab — Textile Color-Separation Tool

A simple, offline tool for screen-printing mills: take a design, reduce it to a
printable number of inks, and generate clean, print-ready color-separated
plates — **without hurting the design's quality**.

LoomLab does **not** generate artwork. It processes a design you already have
(from a client, or one you made elsewhere) through four steps:

1. **Upload** — PNG, JPG, WEBP, TIFF, or PSD (up to 80 MB). Before/after preview.
2. **Reduce** — bring the colors down to a printable count (2–20 inks). LoomLab
   suggests a sensible count, shows a measured accuracy score, and cleans up
   brush/scan texture. Fine-tune the palette: recolor, merge, or lock inks.
3. **Separate** — one flat screen per ink. Every pixel prints on exactly one
   plate — no overlap, no muddy fringe. The combined preview is those screens
   stacked back together, so **it is exactly what will print**. Pick your cloth
   colour and hide any ink that is the fabric itself.
4. **Export** — a single `.zip` with color PNG plates, print-ready B&W TIFF
   screens (300 DPI) with registration marks and a label on every film, a
   full-color proof, and (optional) scalable **SVG** vector outlines. The
   panel shows the size the design actually prints at, in inches and mm,
   since the artwork is never resampled.

### Printing on coloured or dark cloth

Set the cloth colour and the preview shows the design on that fabric. On dark
cloth LoomLab also emits a **white under-base** screen (`0-Underbase`, printed
first, choked 1px so the white never peeks past the colour above it) — without
it, inks laid straight onto dark fabric go muddy. The colour plates stay
mutually exclusive; the under-base is an additional screen.

Transparent PNGs are handled correctly: a transparent background carries no
ink — it never becomes a plate or wastes an ink slot.

### Honest about fit

Screen printing needs flat artwork. If a design has smooth, photographic
shading, LoomLab says so plainly — rather than showing a low percentage and
leaving you to guess — and distinguishes that from simply needing more inks.

It also warns when a design has **soft, see-through edges** — a glow, a drop
shadow, a feathered rim. A flat ink cannot fade, so those edges print as a
hard cut, and the accuracy score won't reveal it because it measures the
pixels that do print. Ordinary anti-aliasing is not flagged: the two are told
apart by how *wide* the fade is (anti-aliasing measures about 3px whatever the
image size, a feather starts around 12px), not by how many pixels it covers.

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
scores every palette so tuning is objective, not guesswork. Verified against
five design archetypes (geometric, line art, continuous-tone, scanned-with-
grain, logo): every pixel lands on exactly one plate, and stacking the plates
reproduces the reduced design byte-for-byte.

Mill-sized files stay usable: above ~2.5 MP the palette is computed from a
downscaled proxy and the full-resolution image is assigned block-wise, so
memory and time stay bounded.

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
- `frontend/src` — the four-step React workspace (pure prepress helpers in
  `src/lib/print.ts`).

Everything runs locally; no external AI or API is used for color processing.

## Tests

```bash
cd backend && pytest          # engine, API and export
cd frontend && npm test       # prepress helpers and error formatting
```
