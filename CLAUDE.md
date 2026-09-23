# LoomLab — developer notes (for Claude / contributors)

Textile **color-separation** tool for screen-printing mills. Non-technical
operators upload a design, reduce it to a printable number of inks, separate it
into one screen per ink, and export a production package. **It does not generate
artwork** — it only processes an uploaded image. Keep it that way.

## Golden rules (do not break)
1. **Reduce keeps quality** — the reduced design must look like the original:
   smooth edges, no lost detail, no torn shapes. Fewer colors, not less quality.
2. **Exactly one ink per pixel** — separation is mutually exclusive (every pixel
   on exactly one plate). No overlap, no gaps. This is verifiable: stacking the
   plates reconstructs the reduced image byte-for-byte.
3. **No muddy fringe/halo** — anti-aliased edges must not create a blend ink.
4. **Offline** — no external AI/API for color processing (pure numpy/PIL) and
   no CDN assets in the frontend: fonts are system stacks, so a mill with bad
   internet still gets a correct first paint. Keep `src/` free of `http(s)://`.
5. **Bad input is a 4xx, never a 500** — ids and colours are validated in
   `models.py` (`ImageId`, `HexColor`), and an expired image id is answered by
   the `FileNotFoundError` handler in `main.py` with 'import it again'.
6. **Stay simple** — the flow is Upload → Reduce → Separate → Export. Don't add
   modes/features that don't serve those four steps.
7. **Be honest about fit** — a continuous-tone design cannot be reproduced by
   flat spot colours. Say so (see `matchVerdict` in `App.tsx`, driven by the
   `suggest_colors` curve) rather than showing a bare low percentage.

## Layout
- `backend/` FastAPI + numpy/PIL. `app/main.py` is the whole API surface.
  - `color_engine/engine.py` — the heart. LAB conversion, CIEDE2000, edge-aware
    k-means (`_quantize`), thin-feature preservation, texture cleanup
    (`_presmooth`), large-image proxy path (`_quantize_large`), `quantize_full`
    (one pass → reduced image + palette), `reconstruction_accuracy`,
    `suggest_colors`.
  - `separation_engine/engine.py` — `create` (mutually-exclusive masks),
    `plate` (colour proof over the cloth colour), `to_print_ready` (B&W screen),
    `print_preview` (stack enabled plates = the final print), `underbase`
    (choked union of every ink — the white screen laid down first on non-white
    cloth; an ADDITIONAL screen, the colour plates stay mutually exclusive),
    `composite_masks`.
  - `vector_engine/engine.py` — pixel-boundary contour trace → SVG (even-odd holes).
  - `core/` — `store` (image cache), `psd_import` (incl. multichannel PSD),
    `regmarks` (registration marks + film/plate labels), `archive` (zip package).
- `frontend/` React + Vite (TypeScript). `src/App.tsx` is the 4-step wizard;
  small components in `src/components/` (BeforeAfter, Zoomable).

## Key engine ideas
- **Edge-aware clustering**: cluster on solid interior + connected thin features
  only; anti-alias transition bands are excluded so no muddy ink forms.
- **Thin-feature detector**: a real line is far from the local blur AND
  connected (`_dense`); isolated high-detail specks are noise and get flattened.
- **Texture cleanup** (`smoothing` 0–3): edge-preserving median pre-smooth for
  painterly/scanned sources. Engine default 0 (keep everything); the app request
  defaults to 1 (Light), since real textile uploads are painterly.
- **Large images** (>2.5 MP): palette from a downscaled proxy, full-res assigned
  block-wise (bounded memory/time).

## Working here
- Backend tests: `cd backend && .venv/bin/python -m pytest -q` (keep them green).
- Frontend: `cd frontend && npm run build` must type-check clean.
- Run locally: backend `uvicorn app.main:app --port 8003`, frontend `npm run dev`
  (Vite proxies `/api` to 8003). Windows: double-click `run-windows.bat`.
- When changing the reduce/separation math, verify on a **real painterly image**
  (not just synthetic): reduce, separate, and check plates aren't speckled and
  the stacked plates still equal the reduced image.
