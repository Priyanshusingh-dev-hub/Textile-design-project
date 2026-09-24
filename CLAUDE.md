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
- Pre-separated (multichannel) PSDs skip Reduce/Separate and are kept exactly
  as the bureau made them — including deliberate overlaps (trapping). The
  upload reports `overlap`; never claim one ink per pixel for those.
- `frontend/` React + Vite (TypeScript). `src/App.tsx` is the 4-step wizard;
  small components in `src/components/` (BeforeAfter, Zoomable); pure helpers
  in `src/lib/print.ts`; tests alongside as `*.test.ts`.

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
- **Nearest ink is solved per colour, not per pixel** (`nearest_centre`): the
  answer depends only on a pixel's colour, so reduce and separate map each
  distinct colour once. Separation runs on the reduced design (a handful of
  colours), so never go back to a per-pixel LAB distance tensor there — at a
  12-inch design it was ~3 GB and 29s.
- **Soft edges**: `soft_edge_width` measures how *wide* the part-transparent
  rim is (area / edge length). Counting part-transparent pixels does not work
  — dense anti-aliased linework is ~99% partial, more than a real feather.
- **16-bit sources** are brought to 8 bits once, at upload (`to_8bit`); PIL
  clips `I;16` to white otherwise.
- **Print width** (`resize_masks`): at its own size a design is output
  untouched. At a chosen width the masks are redrawn: ink fields blurred
  1.2 px + Lanczos, argmax per pixel (one ink per pixel by construction), then
  each ink's <3px parts painted back where its *unblurred* field >= 0.45.
  Don't switch smoothing off near thin features for every ink — on painterly
  art that left 66% of boundaries unsmoothed. Overlapping/soft (bureau)
  masks are resized one by one. Cap: `MAX_PRINT_PX` (70 MP), a 422 above.
- **Seamless repeats** (`seamless_axes`, per axis): a repeat tile is wrapped
  round (`_wrap_pad`, 32 px) before reduce's neighbourhood filters and cropped
  after; `resize_masks` detects a repeat from the masks and resamples with
  PIL's `box` over wrapped fields. Without it a seamless tile came out with its
  seam as the single worst line in the image. Plain-ground edges also count as
  seamless (wrapping them changes nothing — tested identical); only edges that
  carry design are *reported* to the operator (`repeat_to_report`).

## Performance (a 12-inch design = 3600x3600, 10 inks)
Upload 2s, reduce 17s, separate 10s, package 11s (26s with vectors). Keep it
that way:
- chip thumbnails are rendered small (`preview_thumb`), never full-res;
- a package renders/encodes inks on a thread pool (film text is drawn under a
  lock — FreeType isn't thread-safe) and writes the zip in order;
- films are LZW TIFF, PNG/TIFF entries are stored (not re-deflated), the
  working cache writes PNG level 1;
- vectors trace each mask once (`path_data`) and walk integer edge arrays.
Any speed change must be byte-identical (or pixel-identical for TIFF, whose
alignment padding byte libtiff leaves uninitialised): snapshot before, compare
after.

## Working here
- Backend tests: `cd backend && .venv/bin/python -m pytest -q` (keep them green).
- Frontend: `cd frontend && npm run build` must type-check clean, and
  `npm test` (vitest) must pass. Pure prepress logic lives in `src/lib/print.ts`
  (cloth luminance, the match verdict, negligible-ink threshold) and the error
  formatting in `src/api.ts` — put logic there, not in the component, so it is
  testable. Operators reach the engine through the Vite proxy, so a closed
  engine is a 502, not a failed fetch (`statusText`).
- Test at 1366x768 too: the next-step button and the plate strip must be on
  screen without scrolling.
- Run locally: backend `uvicorn app.main:app --port 8003`, frontend `npm run dev`
  (Vite proxies `/api` to 8003). Windows: double-click `run-windows.bat`.
- When changing the reduce/separation math, verify on a **real painterly image**
  (not just synthetic): reduce, separate, and check plates aren't speckled and
  the stacked plates still equal the reduced image.
