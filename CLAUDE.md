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
   plates reconstructs the reduced image byte-for-byte. The one exception is
   the operator's optional **trap** at export (`trap_px`, default 0): the
   *films* then overlap by design, lighter under darker, and stacking them in
   press order (light → dark) still rebuilds the design exactly.
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
- **True CIELAB** (`rgb_lab`, tested against reference values). It once applied
  the sRGB->XYZ matrix untransposed (white L*107 a*-91, blue's a* sign flipped),
  so every "perceptual" distance bent with hue; the Euclidean thresholds below
  were recalibrated to the true space on the floral (edge 8->6.2, feature
  11->8.5, hairline 20->16). dE2000 thresholds (jnd 3, SIMILAR_DE, library 5)
  needed no change — they now mean what they say.
- **Thin-feature detector**: a real line is far from the local blur AND
  connected (`_dense`) AND far *relative to local contrast* (`_FEATURE_RATIO`
  0.3 of `_local_range`): a line sits ~0.45 of the contrast from its blur, an
  anti-aliased step-edge rim only ~0.2. Without the ratio, rims of long edges
  counted as features and became a muddy ink; isolated specks are noise and
  get flattened.
- **Direct assignment**: after the over-segmented clusters are merged to k,
  every pixel goes to its nearest *final* ink (as `_quantize_large` does), not
  to the ink its cluster was merged into — that put a tan vein between cream
  and dark leaf on ochre when cream was nearer.
- **Tried and rejected: snapping a "blend" ink's thin bands** (a sage that is
  also the mix of cream and dark green shows as sage bits on cream/dark rims).
  Two versions on a real design (green lace): "solid cream and dark nearby"
  and "cream on one side, dark straight across" both also erased a genuine
  sage vein drawn inside a cream paisley (dark dashes sit right beside it),
  while the visible rim bits barely changed (the original has grey shading
  there too). Pixel data can't tell that rim from a real thin line reliably;
  `test_a_thin_line_of_the_middle_ink_inside_one_ink_is_kept` guards the vein.
- **Texture cleanup** (`smoothing` 0–3): edge-preserving median pre-smooth for
  painterly/scanned sources. Engine default 0 (keep everything); the app request
  defaults to 1 (Light), since real textile uploads are painterly. A median
  erases 1px lines, so `_keep_hairlines` restores pixels shaped like a line
  (across: both neighbours differ and match each other; along: it continues,
  allowing a slanted step; and it touches other line pixels). Hard 1px lines
  kept 2% -> 96%; floral match/speckle unchanged; pure noise < 2% restored.
- **Suggested ink count** (`suggest_colors`): the reduce's own clusters
  (`_clusters`, shared with `_quantize`) on a 250k px proxy, merged to every
  count 1–14 by `_merge_to`, so each point is the palette reduce would reach.
  The choice is judged on solid areas + thin lines (anti-alias rims never
  print as their own ink): flat art stops at FLAT_DONE (97), painterly art at
  the knee (two more inks add < KNEE_GAIN 1.5). The old median-cut sweep said
  10 for nearly everything and 4 for a 2-colour design. `curve` stays the
  all-pixel match, which drives the continuous-tone verdict.
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
- **Tiny dots** (`separation.speck_report` / `clean_specks`, scipy labels,
  8-connected): islands at or under `dot_area(min_dot_mm, dpi)` px, measured
  on the masks *at print size*; cleaning gives each to the ink most of its
  border touches (or bare cloth), repeating until none are left (3x max).
  Applied before trap, in the package and the Export proof. Islands touching
  the edge of a repeat tile are never dots. Off by default.
- **Trap** (`separation.trap`, 1–3 px, films only): each ink spread under the
  darker inks it touches — never onto cloth — ordered by `press_lightness`,
  the same key the package sorts the press by (keep them one function, or a
  spread could end up on top). Wraps round a seamless repeat. Refused (422)
  for non-exclusive bureau masks. ~2.7s at 12 inches, only when switched on.
- **Small inks** (`small_inks` / `drop_inks`, `/api/colors/small|drop`): inks
  under `below`% (default 2). Removing one sends each of its pixels to the
  remaining ink closest to its ORIGINAL colour (not the whole ink into one
  neighbour: worse on every measure), then only the 1-2 px strays among the
  moved pixels go to their neighbours (`_islands_1_2`, neighbour counts, no
  full labelling; a full majority filter blunted edges). `distinct` = its
  pixels would end up > DISTINCT_DE (5) further off than now: kept. The
  source's own colours are used (texture cleanup made no difference, cost
  4.6s). 12-inch: report 1.4s, removal 2.1s. Transparent neighbours never
  vote, so a moved pixel stays inked.
- **Plate colours** (Separate → 🎨, `components/PlateColours.tsx`,
  `components/LivePreview.tsx`, `lib/recolour.ts`, `/api/separation/live-masks`):
  a plate's colour is only a label on its mask, so recolouring is live in the
  browser. The engine sends each screen shrunk to <= 1600 px (box-filtered
  alpha); the browser reads once, per pixel, its main ink and the ink it
  shares an anti-aliased edge with, and each change is one pass over the pixels
  (17 ms at 1254 px/10 plates without a GPU; the tint-and-stack canvas route
  was 97 ms). Overlapping bureau screens use the canvas route. The server
  preview is suspended while recolouring and runs once on Done.
- **My inks** (`core/inks.py`, `backend/data/inks.json`, `INK_LIBRARY` env to
  move it): the mill's shelf inks. Reduce shows each palette colour's nearest
  shelf ink (`nearest_library_inks`, CIEDE2000); within ΔE 5 it is one click to
  use it (`repaint`, one pass, one undo step), and plates/films take its name.
  One shelf ink goes to one palette colour (`planSwap`) — never merge two plates
  behind the operator's back.
- **Resume** (`src/lib/job.ts`): the job's ids and settings are saved in
  localStorage as they change; the Upload step offers to continue it. On
  continue, `POST /api/image/exists` says which images the 48 h cache has
  cleared, and the job resumes only as far as its images reach.
- **Telegram inbox** (`app/inbox_bot.py`, `run-bot-windows.bat`,
  `telegram-bot.txt` gitignored): a bot that only saves received designs to
  `Designs-Inbox/<date>/` + `inbox-log.csv`; no colour work (rule 4 is about
  colour processing — the bot is the one part that talks to the internet).
  Standard library only (long polling, no public URL). The offset advances
  only after a message is saved or answered; network/disk errors, 429 and 5xx
  leave it, so a dropped download is retried, not lost.
- **Seamless repeats** (`seamless_axes`, per axis): a repeat tile is wrapped
  round (`_wrap_pad`, 32 px) before reduce's neighbourhood filters and cropped
  after; `resize_masks` detects a repeat from the masks and resamples with
  PIL's `box` over wrapped fields. Without it a seamless tile came out with its
  seam as the single worst line in the image. Plain-ground edges also count as
  seamless (wrapping them changes nothing — tested identical); only edges that
  carry design are *reported* to the operator (`repeat_to_report`).

## Big designs on screen
A 30-inch design at 300 DPI is 9000x6750 = 61 MP. Sent as-is the browser got
a 70 MB PNG after ~50s and showed an empty box (Reduce's "after", Separate's
proof, Export's proof). So everything the screen shows goes through
`screenUrl` (`GET /api/image/{id}?max_side=2400`: shrunk, PNG level 1, cached
next to the image as `{id}.s2400.png`, 3.6s first time, 0.03s after), and the
two proof requests pass `max_side`. Anything that prints stays full size: the
package draws its own proof at print size whenever the screen's is smaller.

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
  CI (`.github/workflows/ci.yml`) runs them on Ubuntu **and Windows** — mills run
  LoomLab on Windows — plus the frontend build/tests and a no-`http(s)://`-in-`src/` check.
  Frontend deps are pinned to the lockfile's versions; never go back to `"latest"`.
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
