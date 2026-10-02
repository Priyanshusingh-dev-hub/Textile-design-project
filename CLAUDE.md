# LoomLab — developer notes (for Claude / contributors)

Textile **color-separation** tool for screen-printing mills. Non-technical
operators upload a design, reduce it to a printable number of inks, separate it
into one screen per ink, and export a production package. **It does not generate
artwork** — it only processes an uploaded image. Keep it that way.

## textile_project/ (the `textile` tool, being built)
The user's design pipeline (colour fill, repeat, tile, original designs) as
one command, built phase by phase from `textile_project/ROADMAP.md`. Its own
`textile_project/CLAUDE.md` wins inside that folder (Hinglish, mill rules:
3535 px @ 300 DPI, flat colours, no smoothing, no '#' in names). The tested
logic is `reference_code/` (prototypes): move it into `textile/` modules
WITHOUT changing it, and ask the user before changing any logic. Proof of
"unchanged": `tests/test_phase1.py` runs reference_code on the samples and
the new modules must write byte-identical files. Phase 1 (done): `io_utils`,
`palette` (+ `merge_stray`, < 0.05% -> nearest big colour by RGB), `export`,
`verify` (reads the written files back), `cli` (`python -m textile export |
verify | palette`). Phase 2 (done but for one item): `fill --method 1` (byte-identical
to reference_code method1), `2` (pixel-identical to the method2 prototype on the
tree), `3` (new: the reference registered onto the line art tile by tile, then
Method 1's vote; for a drifted reference, any number of colours) and `auto`
(Method 1, judged by alignment and colour shares vs the reference; then 3; then
2). Not done: 3+ colours when the reference is a *different drawing*; the depth
+ local-colour idea was tried on the tree and lost to Method 2 (~70% agreement). Phase 3 (done): `repeat` (repeat_analyze.py as a module, JSON;
a vertical-only repeat = panel print) and `tile` (deshear -> crop search ->
seam-cut, the prototypes' code; with their fixed settings the same tile pixel
for pixel; then wrap-padded Lanczos upscale, optional flat colours/clean ground). Phase 4 (done): `make` (a JSON config -> an original repeat or
panel, hard-edged PIL shapes on a palette-index canvas drawn 9x round the
wrap; motifs phool/buti/patti/sprig/dots/haathi, layouts grid/half-drop/
scatter/panel bands; examples/ has three, the tests check flat + seamless). Phase 5 (done): `batch` (every pair in a folder, auto method,
one bad pair never stops the rest; `run-textile-windows.bat`), `vector`
(OpenCV contours + approxPolyDP, redrawn LINE_8, + SVG; potrace is not offline)
and `--dpi 600` (same inches, double pixels, warned at start and end). Then `edges` (the user asked for it:
each ink's outline smoothed ALONG itself, corners found by two straight arms and held, thin lines/dots held,
redrawn hard-edged on the `--size` grid; no new colour; speck removal off by default because it cost 2.5 match
points on real small motifs; at its own size there is no gain, the finer grid is the point; matches LoomLab's
print-width redraw within +-0.5 match and ~8% fewer wrong px on a drawn-at-4x truth, so it stayed a CLI tool, not
an app step). `colorfill/` below is method1 alone, kept until
`textile fill` (Phase 2) replaces it.

## colorfill/ (on trial, beside LoomLab)
A second, separate tool: **line art + a coloured reference of the same design
-> flat channels** (each closed area of the line art takes the reference's
majority colour). Its own rules are in `colorfill/CLAUDE.md` and win inside
that folder: use `colorfill.py` as it is (the user's approved method), no
smoothing, 3535 px @ 300 DPI by default, no `#` in file names. Windows:
`run-colorfill-windows.bat` runs every `NAME_lineart` + `NAME_colored` pair in
`colorfill/input/`. CI runs the sample pair on Ubuntu and Windows against the
checklist in its CLAUDE.md. Known on the sample: 3 doubtful regions, two of
them a real leak (a line-art gap at the swirl-leaf tips lets the rust stripe
fill the outline band); `--line-threshold` 170/190 does not close it. It is
on trial: the user decides later what of LoomLab stays. LoomLab's rules below
do not apply to colorfill/, and colorfill's do not apply to LoomLab.

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
   flat spot colours. Say so (see `matchVerdict` in `lib/print.ts`, driven by the
   `suggest_colors` curve) rather than showing a bare low percentage.

## Layout
- `backend/` FastAPI + numpy/PIL. `app/main.py` assembles the app (licence
  gate, error handler, health, serving the built frontend); the endpoints live
  in `app/routes/`, one module per step or area: `images` (upload, enlarge,
  files), `palette` (Reduce), `plates` (Separate), `export`, `automation`
  (auto mode, jobs, quote), `licence_routes`, with shared helpers in `common`.
  Names the tests use (`MAX_PRINT_PX`, `_build_package`, `colors`...) are
  re-exported from `app.main`.
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
- `frontend/` React + Vite (TypeScript). `src/hooks/useLoomLab.ts` holds the
  job, its settings and every action; `src/App.tsx` is only the shell (header,
  the step on screen, footer) and each step is a view of the hook in
  `src/components/steps/` (Upload/Reduce/Separate/ExportStep, passed `w`).
  Other components in `src/components/`; pure helpers in `src/lib/` (put logic
  there, not in a view, so it is testable); tests alongside as `*.test.ts`.
  **Hinglish** (`lib/i18n.ts`, header button EN/हिं, remembered in
  localStorage): English is the key; `const t = useT()` and `t('Label')`,
  `t('{n} inks', { n })`. Add the Hinglish (Roman script, like the bot) to
  `HI` for every new visible string; a missing one shows in English — and
  fails `i18n-coverage.test.ts`, which scans the source for t()/tr()
  literals (joined `'a' + 'b'`, either side of `?:`) and the label lists
  (Settings fields, stages, warnings, periods). A key
  with {values} is also a template, so a message built elsewhere with its
  numbers in ("Reduced to 7 inks — 88% match…") is translated by `t(text)`
  too; both sides must carry the same {values} (tested). The language lives
  above `useLoomLab` (App → Shell), so the hook's notes are built in it: a
  note made of pieces (small inks, dots, enlarge, repeat...) takes a `Tr`
  (`t`, or `english` by default) instead of being matched as one string.
  The engine's error answers are HI keys like any label (the footer and
  error lines go through `t`); auto mode's warnings carry their own
  Hinglish (`hi`, written next to the English in `auto.review`, numbers
  identical, tested) for the Jobs page and the bot — reports from before
  fall back to the English.

- **Line art + reference** (Upload's second tab, `routes/linefill.py`,
  `POST /api/fill`, `core/filltrial.py`, `components/Trials.tsx`, `lib/fill.ts`):
  the second way to a flat design, beside Reduce. The textile tool's fills
  (imported from `../textile_project`, not copied; the backend needs opencv +
  scikit-learn) are only worth using when the line art carries the design, so
  `method=auto` does not trust them, it TRIES them: Reduce of the reference
  alone (`0`) and each fill (Method 1; **4** = Method 1 with the line art's
  gaps sealed, `fill_method4`; 3 = reference registered onto the line art; 2 =
  two colours) are each drawn at the reference's own size (<= 1200 px, one
  pixel grid for all), take their colours from Reduce's few inks (not k-means'
  shading), and are scored against the reference with `pixel_match` (the
  Reduce step's own match). Rule (`filltrial.decide`): the best fill wins when
  it trails plain Reduce by <= TOLERANCE (13) match points (the line art's
  clean edges are worth that much: edge share ~8 vs ~18% on the AI pairs),
  else Reduce wins and the line art is set aside. Only the winner is made at
  full size. Calibrated on ten pairs (fill minus Reduce): the user's approved
  floral -7 and star -12.2, an AI floral -12.1 (all fill); a teal ikat -14.2
  (its fill lost most cream diamonds: the reason 15 became 13), a cream
  paisley -22, an AI star -23, a blue stripe -30, a mustard floral -35, an
  elephant -39 (Reduce). Tried and not used as a second test: alignment
  (ikat 0.90, good pairs 0.97, but the approved star was 0.58) and "a fill
  loses an ink's area" (the approved floral/star also differ 52-67% per ink
  from Reduce, the ikat 71%). The tree panel (line art a different drawing ON
  PURPOSE, Method 2 approved) cannot be picked by any match, so the answer is
  not final: the card shows every trial (one line closed, a table open) and
  "Use this" re-makes it another way from the same two files (the table is
  kept, the tick moves). Every auto run is a line in `data/fill-trials.jsonl`
  (never aged out: time, design hash, all trials with their numbers, the
  choice and why), an operator pick another ("overrides" = what auto chose),
  `GET /api/fill/log`: the data to tune the rule on, and the start of the
  feedback set. A bad crop (shapes differ) is a 422 before any trial: never
  hidden behind the fallback. When Reduce wins the answer is the Reduce
  step's own (`reduce_route`), with its usual controls. The result is the
  reduced design, so the palette tools, Separate and Export take it from
  here; its match is `pixel_match` against the reference (`filled` on
  `/colors/accuracy`). The fill's Hinglish errors become English keys
  (`MISFIT`). Seen on the user's pairs: an elephant panel and a star mandala
  (line art and colour drawn separately, the stripes/saddle do not agree):
  Reduce of the reference kept every colour (83-84%) and the fills lost the
  design (35-61%). A region-colouring experiment (Method 2's shapes, colours
  voted from the registered reference) lost on the elephant: line-art gaps
  leak and the registration pulls the reference onto Method 2's wrong
  ground/motif guesses.

- **One command for any picture** (`app/photo_batch.py`, `run-photo-windows.bat`,
  `python -m app.photo_batch <folder>`): the whole route in one place so a new
  picture needs no hand-work and no per-image tuning. By NAME: `X_lineart` +
  `X_ref`/`_colored`/`_reference` is a pair (the fill judge above); every other
  picture is Reduce alone. Then, for all: textile's `edges` (clean edges) on the
  `--size` grid (3535 px @ 300 DPI), textile's export package (final TIF for the
  mill, final PNG = every ink stacked, channels, B/W, report), `X_compare.png`,
  and `summary.csv/json` (route, why, match, inks, verify). It drives the real
  API in-process (TestClient, like the benchmark); a bad picture is an `error`
  row. Learnings it encodes (do not re-litigate per picture): AI line art and
  AI colour image drawn separately rarely agree, so the fill is tried, not
  trusted (judge, tolerance 13); the reference through Reduce is the fallback
  and often the winner; edge cleaning helps only on a finer grid than the
  source (1254 -> 3535 px), not at the source's own size; speck removal off
  (it deletes real small motifs); the mottled bits inside a Reduce are Reduce's
  own noise, not edge noise. A Reduce of a photo-like design (the app's own
  rule: the suggest curve's best match under auto's `photographic_ceiling`,
  80) also gets `X/dots/` (the app's index separation, redrawn at print size
  by `resize_masks(dots=True)`, dot size in mm + the app's 0.12/0.45 mm
  limits); flat stays the main file (the mesh is the mill's call). Tried
  first and dropped: "make dots when they LOOK closer" — on the AI pictures
  (ceilings 86-89) dots scored 2-3 seen-match points higher only by
  sprinkling the picture's noise over flat grounds as stray dots.

## Measuring colour separation (truth benchmark; learnings, do not redo)
The Reduce match is taken against the NOISY input, so it under-reports: flat
designs from `textile make` (known truth) degraded like an AI image (blur 0.8,
low-frequency shading and tint, mottling, grain, JPEG q70) are recovered at
96-98% (truth match) while the app shows 84-90%. Anything on a real AI picture
that scores 95%+ against its own pixels is therefore not reachable and not the
goal: judge changes against a TRUTH (or an operator's separation:
`NAME.operator.png` in the benchmark), with agreement (% pixels whose ink is the
truth's), truth-match (`pixel_match` vs truth) and extra edge share. Baseline
(quantize_full, k = true inks): truth match 82.1, agreement 84.5% over 3 simple
+ 3 detailed designs (the reduced AI pictures as stand-ins), mild + heavy.
Tried, in this order (all before clustering, labels from the filtered image):
bilateral x3 (agreement 97.8 on the simple 3 but ink colours -2), mean-shift,
edge-preserving (cv2), TV denoise (skimage), rolling guidance, SLIC superpixels,
own edge-aware Potts MRF on the labels, vtracer on the noisy image: none beat
the baseline cleanly. Best: OpenCV contrib `ximgproc.l0Smooth` (lambda 0.01-0.03,
kappa 2; kappa 1.5 is unstable) for the labels with ink colours taken back from
the ORIGINAL (filtered colours cost 4 points): truth match +1.1, agreement
+3.8 on all six at lambda 0.01, edge share down. BUT on the real AI star
(fine stripes) it lost 9 match points when colours came from interior medians
(L0 widens thin stripes), and taking the palette from the unfiltered
image with L0 only for assignment was worse on the benchmark (-0.8) and better
on the real star (+2.6): the two measures disagree, so L0 is NOT in the app. Needs
opencv-contrib (replaces opencv-python-headless, Apache) if it ever goes in.
The benchmark is `python -m app.truth_bench` (`app/truth_bench.py`, METHODS to
compare another; tests in `tests/test_truth_bench.py`). Generic tools lose to
the app's Reduce on it: Pillow median-cut -8, Pillow octree -12, plain Lab
k-means -2 truth-match, and their edge share is +7..+14 above the truth's
(ours -0.2). Reveal (github.com/electrosaur-labs/reveal, Apache-2.0, Node) run through its own
CLI (`--methods reveal`, REVEAL_CLI): auto 65.1 truth / 63% agreement / +9.6 edge,
its adaptive archetypes 60-65 / 65-68%, vs ours 70.6 / 75%: not adopted. Its
LPI-aware Bayer dots (ordered dither per macro-cell, re-done in numpy) on the AI
pictures at 8 inks: seen match 0.7-1.6 below our Floyd-Steinberg dots but fewer
1-2 px islands (10.4 -> 6.9% on the floral); a mesh question for the mill, not
in the app; colorsep / InkSplit
take a palette you give them (InkSplit is a GIMP plug-in), so nothing to adopt.
Inspired by Reveal's PaletteDistiller (over-quantize, then keep the most
DISTINCT colours rather than the most covered), phase 2 of `_merge_to` was tried
with cost = share^a x dE instead of count x dE (+ a 0.2% ghost floor): on the
truth set +3.7 truth match / +2.7 agreement (a=0.2; pure distance a=0 +4.2/+4.9),
and at the same ink count the six real designs were level (81.73 -> 81.88 match,
edges a little cleaner) — BUT pink-paisley lost its small orange dots (they went
red) for a pale pink, i.e. a visible accent colour, so it is NOT in the engine.
Adding "a colour lying between two others is a blend, drop it first" did not
save the orange: the orange lies between the red and the ochre. Same lesson as
the rejected blend snapping: colour geometry alone cannot tell a blend from a
real in-between ink. (The suggested ink count also moved with it: pink-floral
8 -> 6, teal 9 -> 7; suggest's curve is calibrated on the current cost.)
A real case FOR distinctness since (stock design 2218, AI-flattened): its
thin cream lattice (1.4% of pixels, dE2000 8.8 from the beige ground) got no
ink until 10 inks, while three dark browns/maroons (dE 5.9-17 apart) all
kept theirs; the fix by hand was the operator's own palette (9 inks with the
cream, `quantize_full(palette_hex=)`): 86.6 pixel / 92.7 seen. So the
trade-off is real on both sides (paisley orange vs 2218 lattice); a rule
that protects thin LINE-shaped colours specifically is the open idea.
Colours must never come from a filtered image; ink count 4 -> 20 adds only
4-5 match points on the AI pictures (noise, not ink count, is the ceiling).

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
  grainy sources. Chosen per design (`auto_smoothing`, returned by suggest;
  a reduce request without `smoothing` uses it) from `grain`: the median
  colour change a 3x3 median makes, on five full-resolution tiles. All six
  real designs (painterly included) measure 0.6–1.2 and get Off — on every
  one, Light erased petal outlines, lace dots and veins and muddied the brown
  zigzag, while the mottling merge already keeps grounds solid. That is why
  the old app default of Light was dropped. Grain >= 4 → Light (a noisy scan
  measures ~7 and speckles without it), >= 9 → Medium. The app shows why and
  warns on an override either way (`cleanupNote`). A median
  erases 1px lines, so `_keep_hairlines` restores pixels shaped like a line
  (across: both neighbours differ and match each other; along: it continues,
  allowing a slanted step; and it touches other line pixels). Hard 1px lines
  kept 2% -> 96%; floral match/speckle unchanged; pure noise < 2% restored.
- **Suggested ink count** (`suggest_colors`): the reduce's own clusters
  (`_clusters`, shared with `_quantize`) on a 250k px proxy, merged to every
  count 1–14 by `_merge_to`, so each point is the palette reduce would reach.
  The first stop is judged on solid areas + thin lines (anti-alias rims never
  print as their own ink): flat art at FLAT_DONE (97), painterly art at the
  knee (two more inks add < KNEE_GAIN 1.5). Then inks are added while the
  all-pixel match (what Reduce shows) is under GOOD_MATCH (88) and still
  climbing, so the next screen never calls the suggestion loose. Real designs:
  pink 8, red 5, brown 5, lace 6, teal 9; flat 2/3/5-colour art exactly 2/3/5.
  The old median-cut sweep said 10 for nearly everything. `curve` is the
  all-pixel match, which drives the continuous-tone verdict.
- **Mottling is one colour** (`_adjacency`, `_shade_pair`, phase 1b of
  `_merge_to`): two clusters under ΔE 6 whose shared boundary is >= 10% of
  the smaller one's pixels are woven through each other — a painterly
  ground's mottling or scan grain — and merge before phase 2 drops anything.
  Kept apart they printed as blotches (teal's navy ground, brown's ground,
  red's cream star) and cost a screen a real colour then lost. Separate
  motifs in close colours meet along ~1% of their area and stay apart
  (`test_two_close_colours_in_separate_shapes_stay_two_inks`). Tried first
  and rejected: judging "shading vs edge" by how much the blurred image
  changes across the boundary — for colours ΔE 1-3 apart texture noise
  alone reads as an edge (every pair scored 5-15% shading), and discounting
  the area-weighted phase-2 cost never outweighed a big ground's area.
- **Print as dots** (index separation; Reduce's checkbox, `dots` on reduce,
  accuracy, preview and package): for photo-like shading, which flat inks
  print as bands. The reduce's own palette, placed by Floyd–Steinberg error
  diffusion (`colors.dither`: PIL's C quantizer, its 256 slots filled with the
  inks repeated so nothing lands on filler black) — still exactly one ink per
  pixel. Judged as seen (`seen_match`: both blurred SEEN_BLUR px first); pixel
  by pixel dots always "miss". On a photo-like test 64% flat -> 80% dots.
  At a print width the dots are redrawn on a grid of `dot_pixels` (the scale,
  rounded): the dotted design in its inks is averaged onto the grid and
  dithered again there (`_dots_at`) — scaling the dots by a non-whole factor
  made them 2 and 3 px by turns, a beat that shows as bands; smoothing would
  run them together. Export states the dot size (`dotSizeNote`, the same
  rounding: under 0.12 mm most mesh loses it, over 0.45 mm the pattern
  shows). Transparent pixels wear an ink's own colour before dithering, so
  no hidden colour pushes its error into the edge. No trap, vectors,
  tiny-dot cleaning, small-ink removal or merge hints (priced on the flat
  scale) with dots. Switching dots on/off after a reduce is
  `/api/colors/dots` with the palette AS EDITED (flat again via
  `quantize_full(palette_hex=)`, reduce's own last step on given inks), one
  undo step; the setting follows only a redraw that worked, and a new upload
  starts flat. Never automatic: auto mode's photographic warning only
  points to it. Asked for (`AutoRequest.dots`; "dots"/"index" in a bot
  caption or hot-folder name via `parse_request`; MCP `dots`, which
  `rerun_job` keeps, and its instructions send a photographic job there),
  auto mode makes a dotted job: no trap, vectors, dot cleaning or tiny-dot
  check, no small-ink or photographic warnings (the flat-ink ceiling no
  longer applies), `tiny_dots` None; its colourway jobs (API and MCP
  `save_package` colourways) stay dotted. The report's settings keep the
  trap/vector ASKED for (the package just leaves them out), so a re-run
  without dots gets them back. Words read both ways (`_dots_wanted`): "no
  dots", "dots hatao/mat/off", "bina dots", "flat" = False; "0.2 mm dots",
  "tiny dots" are specks, not a print mode. Boundary share can't tell dots from fine flat
  art (brown mandala 0.38 flat vs rose 0.29 dotted), so the flag is explicit.
- **Large images** (>2.5 MP): palette from a downscaled proxy, full-res assigned
  block-wise (bounded memory/time).
- **Nearest ink is solved per colour, not per pixel** (`nearest_centre`): the
  answer depends only on a pixel's colour, so reduce and separate map each
  distinct colour once. Separation runs on the reduced design (a handful of
  colours), so never go back to a per-pixel LAB distance tensor there — at a
  12-inch design it was ~3 GB and 29s. Reduce's recolour/merge (`merge`,
  `/colors/remap`) works the same way: byte-identical, 16s -> 0.9s at 6 MP.
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
- **Plates belong to one reduced design** (`layersFor` in `useLoomLab`): any
  palette edit after Separate (re-reduce, merge, recolour, undo, small inks)
  makes a new reduced image, so the plates are dropped and Separate locked —
  the header used to reopen Separate/Export with the old plates.
- **One busy state for everything** (`hooks/useAsyncStatus.ts`, `Work`): user
  actions and the previews the page redraws itself share it, and it stays busy
  until the LAST one ends — a quick preview finishing first used to unlock
  Download mid-build.
- **Colourways** (`PackageRequest.colourways`, `_colourways` in
  routes/export.py, `lib/colourways.ts`, MCP `preview_colourway` /
  `save_package(colourways=)`): the same screens in other inks. Films are made
  once (byte-identical to the job's own); each colourway adds
  `colourways/<name>/proof.png` + `job-sheet.png`, rows ordered lightest
  first by ITS inks and naming the screen by the number on the film. Refused
  with a trap (made for one ink order); names must stay distinct after the
  folder-safe rewrite. Plates re-cut from a new design drop the colourways.
  Auto reports keep `settings` so a package can be made again the same.
- **Resume** (`src/lib/job.ts`): the job's ids and settings are saved in
  localStorage as they change; the Upload step offers to continue it. On
  continue, `POST /api/image/exists` says which images the 48 h cache has
  cleared, and the job resumes only as far as its images reach.
- **Auto mode** (`/api/auto`, `/api/auto/upload`, `app/auto.py`,
  `backend/auto-config.json`): suggest → reduce → separate → package by
  calling the app's own handlers (`reduce`, `separate`, `_build_package`,
  split out of `export_package`) — no second copy of any step. `_build_package`
  also reports dots under `tiny_dot_mm` on the screens it draws at print size
  (+3s on a 30-inch job, instead of redrawing them). `review()` turns the
  measured facts into warnings and `auto_ok | needs_review`; which codes block
  is config. The photographic ceiling (80) mirrors `matchVerdict`'s in
  print.ts: keep them equal. Job files are `auto-{id}.zip/.json` in the cache
  folder and age out with it (the glob never touches inks.json there). The
  user's real 1448 px designs all come out needs_review, honestly: at their
  own size (4.8 in) they are 1-6% sub-0.2 mm dots, at 30 in only 48 px/inch.
- **Job dashboard** (`/api/jobs`, `/api/jobs/{id}/stage`, `components/Jobs.tsx`,
  `lib/jobs.ts`): reads the auto-*.json reports in the cache (the jobs age
  out with it), stage new → reviewed/sent → approved/rejected/changed with a
  history; the bot writes its stages best-effort (`Engine.stage`). "Needs
  review" = held and still `new`; the header's count uses the same rule, from
  the server, and the dashboard updates it after every change. Reports from
  before the dashboard have no stage/time: `new` and the file's mtime.
- **Job log + stats** (`core/joblog.py`, `/api/stats`, Jobs page tiles,
  MCP `job_stats`): `data/job-log.csv`, one row per job made and per stage
  change, never aged out (cleanup only globs *.png and auto-*). Written best
  effort (a full disk never fails a job). Time saved = jobs x manual minutes
  - held x review minutes - engine time, at the rate card's
  `manual_minutes_per_design` / `review_minutes_per_design` /
  `staff_cost_per_hour` (not used by quotes) — always shown as an estimate.
  Designs are counted once by `design` (a hash of the source pixels in the
  report), by their latest run: a re-run or a client's change is not another
  design saved. `trial` jobs (the benchmark) stay off the log and dashboard.
  Text cells starting like a formula get a leading ' (Excel injection).
  An older log's header is rewritten once to today's columns.
- **Client ledger** (`joblog.clients`, `/api/clients`, Jobs → 👥 Clients,
  MCP `client_summary`): per client (names match ignoring case/spaces; the
  latest spelling shown; no-client jobs left out) their designs — each once,
  by its latest run, per client — approved/stopped/waiting, approved meters,
  repeat orders, and `business` = approved quotes + repeat quotes. A
  colourway job has its design's hash, so it replaces the run it came from.
  The bot's "mere order" / `/orders` lists a client's OWN orders from
  `orders.json` by Telegram id (never by name: a name could be anyone's).
- **Design library** (`core/library.py`, `/api/library`, Jobs → 📚 Library,
  MCP `find_design` / `repeat_quote`): marking a job `approved` (dashboard or
  bot) copies its report, a <=1200 px proof and its zip to
  `data/library/<job id>/` (built in `.part`, renamed whole; not touched by
  the 48 h cleanup, whose globs are not recursive). `POST /api/quote
  {library_id}` prices a repeat order from the stored coverage with
  `screens_ready` (no screen cost; printing still per screen) and says so on
  the quote image. A confirmed repeat is `POST /api/library/{id}/repeat`
  (once per `token`: a retried press is the same order), kept on the entry
  (`repeat_orders`, survives a re-approval) and logged as a `repeat` event
  for stats. An entry that fails `library.valid` is left out of the list and
  a 404 to quote, never a 500. A failed copy on approval (disk, a zip open
  on Windows) keeps the approval and answers `library: False` with why; the
  old entry is swapped out only once the new one is built. The proof is the
  cached screen copy when there is one, transparency on white.
- **Backup** (`core/backup.py`, `/api/backup`, `/api/backup/restore`,
  Settings -> Backup): one zip of library (films stored, not re-deflated), job
  log, inks, rate card, auto limits + `manifest.json` (`loomlab_backup: 1`).
  Built in a temp file (not memory, ZIP64) and deleted after sending or on
  failure; a file over the restore cap (4 GB) is left out and named in the
  manifest (`skipped_too_big`), so every backup made restores; the entry's
  report then says `has_package`/`has_proof` false. Files restore reads whole
  (JSON, the CSV log) have their own small caps (16 MB / 512 MB). The app
  reloads the shelf inks after a restore. Restore reads
  only known names (`library/<32 hex>/(report.json|proof.png|package.zip)`;
  anything else, `..` included, is ignored), caps sizes, validates every part
  with the app's own checks BEFORE writing any; the job log is merged by
  (time, event, job, stage), the rest replaced.
- **Benchmark** (`app/benchmark.py`, `run-benchmark-windows.bat`): auto mode
  in-process (TestClient, the real API) over a folder; report.html/csv/json.
  `NAME.operator.ext` pairs with NAME: `image_match` = mean CIEDE2000 pixel
  by pixel against the original, the Reduce step's 0-100 scale, for both.
  Warning titles come from `auto.TITLES`. The user's 7 real designs at 12 in:
  4/7 auto OK, ~20 s each.
- **Enlarge** (`core/enlarge.py`, `/api/image/enlarge`, `/api/image/{id}/file`,
  Export's "High-resolution design file"): Lanczos x2 then to size +
  UnsharpMask(2.5, 60, 2), or a local realesrgan-ncnn-vulkan (tools/realesrgan/
  or REALESRGAN; x4 then resized; any failure falls back with a note). Match
  = `pixel_match` of the result BOX-shrunk to the original (Lanczos ~98%);
  under MIN_MATCH 95 it is flagged. The same `pixel_match` scores operator
  files in the benchmark. Alpha is enlarged separately. Tests use a stand-in
  upscaler script (POSIX only) for the run / redraw-caught / crash paths.
- **Cost/quote** (`core/quote.py`, `backend/rate-card.json`, `/api/quote`,
  Export's "₹ Quote", auto's `meters`): ink kg = coverage x meters x cloth
  width x g/m2 x wastage, per screen (+ a white under-base covering all inks
  together); screens, cloth, printing (meters x screens), setup; margin is
  spread over the lines the client sees, GST on top. The card is validated
  (negative, unknown or non-numeric settings are an error, not a silent
  default). The image is 1080 px wide for phones; ₹ needs a font with the
  glyph (DejaVu, Arial on Windows), set `currency` to "Rs." otherwise.
  **Client rates** (`clients` in the card, Settings → Client rates):
  a regular client's own margin/screen/printing/setup/ink/cloth, by name
  (case and spaces ignored), only the settings named; every quote goes
  through `_quote`, which applies `for_client` and answers `client_rate`
  (the app, MCP and bot say so). GST, wastage and the ink model are not
  per client: they are facts, not prices.
- **Settings** (`routes/settings.py`, `components/Settings.tsx`,
  `lib/settings.ts`): the rate card and auto limits edited in the app. Numbers
  must be finite (JSON also carries NaN/Infinity: NaN passed every `<` check).
  `check_card` / `check_config` are the one validation for the file and the
  screen; a save writes atomically and keeps the file's `_comment`. A broken
  file is shown with the defaults and its error, so the screen can repair it.
  Tests run on a temporary DATA_DIR (`tests/conftest.py`): they used to leave
  auto jobs in backend/data, where the dashboard showed them as orders.
- **Licence** (`app/licence.py`, `components/Activation.tsx`): Ed25519 in
  plain Python (RFC 8032 section 6; both RFC vectors are tests; verify ~7 ms,
  status cached per file change). Key = `LL1.<b64 json {mill, machine,
  issued, expires}>.<b64 sig>`; machine code = sha256 of MachineGuid /
  machine-id. Enforced only when `backend/licence-public.key` (or
  LOOMLAB_PUBLIC_KEY) exists — never commit one unless the seller means to
  lock the build; `backend/licence.key` and `*private*.key` are gitignored. The
  middleware answers every /api call but health/licence with 402 while locked.
  It asks `status()` on every request, so that is two stat calls when nothing
  changed (the machine code is read once per process).
- **Telegram inbox** (`app/inbox_bot.py`, `run-bot-windows.bat`,
  `telegram-bot.txt` gitignored): a bot that only saves received designs to
  `Designs-Inbox/<date>/` + `inbox-log.csv`; no colour work (rule 4 is about
  colour processing — the bot is the one part that talks to the internet).
  Standard library only (long polling, no public URL). The offset advances
  only after a message is saved or answered; network/disk errors, 429 and 5xx
  leave it, so a dropped download is retried, not lost.
  **Order desk** (`app/bot_orders.py`: `Engine`, `Jobs`, `parse_request`,
  `summary`): with ENGINE set, a saved design goes to `/api/auto/upload`
  (the bot's own multipart; `test_the_bots_upload_is_accepted_by_the_real_engine`
  posts it to the real API), proof + quote + Approve/Change go back; held jobs
  go to OPERATOR first (send/rej buttons, only operators may press them;
  ok/chg only the client or an operator). Stages: review → sent → approved |
  rejected | changed, in `orders.json`. Once the design is saved a Telegram or
  engine failure is reported, never retried (a retry would save it twice and
  run a second job). The one exception is the engine being CLOSED (`down`):
  the design joins `orders.json`'s `queue` and `retry_queue` (from the poll
  loop, every QUEUE_RETRY_SECONDS) runs it once the engine answers, oldest
  first; each item leaves the queue before it runs, so a lost proof after
  that is reported, not re-run. Repeat orders (`handle_repeat`, text matching
  `_REPEAT` with meters): the client's own jobs in `orders.json` (however
  they were approved) intersected with `/api/library`; several -> a proof
  per design with an `rpq:<token>` button; the quote gets `rpk:<token>` to
  confirm (client or an operator, once): recorded in the engine first, then
  operators and client told, `done` last — so a dropped send is finished by
  the next press, and nothing lives only in the chat. Tokens live in `orders.json` `repeats` (10 hex, well under
  Telegram's 64-byte callback limit). **Colourways on Telegram**
  (`🎨 cw:<job>` under the proof, `app/colour_words.py`, stdlib): the bot
  lists the inks by number and nearest colour name; the client writes
  "pink ko neela", "1 navy", "kapda kala" (Hinglish/English names, light/
  halka, dark/gehra, #hex) — or types them after ✏️ Change — and gets
  `/api/separation/preview` of the same screens back (`recoloured`, shared
  with MCP), each message building on the last (`awaiting_colours`). The
  words only read what the client asked; nothing picks colours for them.
  `cwk:<token>` makes them a job: `POST /api/auto/{id}/colourway` (with the
  token, so a retried press gets the same job back), the original goes
  `changed` with a note, and the new job is delivered like any (`_deliver`:
  to the client, or the operators first if held); a proof lost on the way
  is re-sent by the next press (`_send_job`).
- **Colourway jobs** (`/api/auto/{id}/colourway`, MCP `make_colourway_job`):
  the job's screens (same layer ids, same pixels) in other inks, a job of
  its own with package, proof (`print_preview` of the masks), quote and
  `colourway_of`. A colour within ΔE 5 of a shelf ink becomes that ink
  (`shelf_inks`) — each shelf ink for one screen only, the closest (the
  `planSwap` rule) — else it is named by `colour_words.name_of`; dark cloth
  (the app's isDarkCloth rule) adds the white under-base. The screens'
  warnings stand; `similar_inks` is asked again of the new inks
  (`auto.similar_warning`, inks counted from 1). A lock per token makes one
  job per token even for two presses at once, and the original's report is
  re-read under its own lock (the one `job_stage` takes) before
  `colourway_jobs` is written, so a stage set meanwhile is kept. Only `engine.auto` failing as closed queues:
  a failure after the job exists (the proof fetch) is reported, and a read
  timeout is NOT `down` (the engine is running; the job may exist). Callback data is `action:job_id` (35 bytes; Telegram
  allows 64).
- **MCP server** (`app/mcp_server.py`, `setup-claude-windows.bat`): the plan's
  "AI decides, engine does the pixels". Stdio JSON-RPC in the standard library
  (checked against the official `mcp` client), talking to the running engine
  through the bot's `Engine` (so the dashboard sees every job; `mark_job`
  writes `by: AI operator`). Tools return the proof as an image (<= 1200 px)
  so the model can look before it marks a job; tool failures are `isError`
  results, never protocol errors; the engine being closed is said plainly.
  `--install-desktop` merges into Claude Desktop's config, keeping a `.bak`,
  and refuses a config it cannot parse. Nothing but protocol goes to stdout.
- **Hot folder** (`app/hot_folder.py`, `run-hotfolder-windows.bat`):
  `in/` -> `ready/` (auto_ok) | `check/` (held) | `failed/` (+ `.why.txt`).
  Settings from the file name via `parse_request` ("rose 30in 500m 6inks").
  A file is run only after its size/mtime held still for one poll; the
  engine being down leaves files queued in `in/` (said once). Output folders
  and names never overwrite. A job's folder is built in `.work/<job id>` and
  renamed in whole, so ready/ never holds half a job; once the job exists any
  failure sends the file to failed/ naming the job (never a second run). A
  locked or vanished file is skipped until the next look, and the loop
  survives any one error. `tests/conftest.py`'s `LocalEngine` answers the
  bot's `Engine` with the real API in-process (MCP and hot-folder tests).
- **Seamless repeats** (`seamless_axes`, per axis): a repeat tile is wrapped
  round (`_wrap_pad`, 32 px) before reduce's neighbourhood filters and cropped
  after; `resize_masks` detects a repeat from the masks and resamples with
  PIL's `box` over wrapped fields. Without it a seamless tile came out with its
  seam as the single worst line in the image. Plain-ground edges also count as
  seamless (wrapping them changes nothing — tested identical); only edges that
  carry design are *reported* to the operator (`repeat_to_report`).

- **Repeat view** (`lib/repeat.ts`, `components/RepeatView.tsx`, the ⊞
  button on Separate's and Export's proof via `Zoomable repeatOf`): the proof
  3 x 3, straight then half-drop, so a seam or a broken half-drop shows
  before a screen is burnt. Drawn in the browser from one `?max_side=800`
  copy placed 1:1 (a scaled copy's edge blends with nothing and draws a seam
  the print doesn't have). Only a view: the films are the design once.
- **Help / diagnostics** (`app/diagnostics.py`, `/api/diagnostics`,
  `/api/diagnostics/report.txt`, Settings → Help, MCP `engine_report`): an
  `Exception` handler records every 500 (last 50 in memory, a running
  `errors_total`, full traceback in `data/loomlab-errors.log`, rotated at
  1 MB to `.1`) and answers with the app's own "engine hit a problem" words;
  an `HTTPException` of 5xx is recorded too, then answered as usual. The
  report: commit (read from .git without git), versions, cache and disk,
  library/log/inks counts (counted, not parsed, each in `_count` so a
  damaged file reads "unreadable: ..." instead of failing the report that
  is meant to diagnose it), settings and licence health, the last errors —
  no designs, prices or clients. The JSON carries `text` (what Copy copies).
  Open while locked (it helps fix a licence).

## Big designs on screen
A 30-inch design at 300 DPI is 9000x6750 = 61 MP. Sent as-is the browser got
a 70 MB PNG after ~50s and showed an empty box (Reduce's "after", Separate's
proof, Export's proof). So everything the screen shows goes through
`screenUrl` (`GET /api/image/{id}?max_side=2400`: shrunk, PNG level 1, cached
next to the image as `{id}.s2400.png`, 3.6s first time, 0.03s after), and the
two proof requests pass `max_side`. Anything that prints stays full size: the
package always draws proof.png from its own screens at print size
(`composite_image_id` is accepted and ignored — an older preview once made a
proof that disagreed with the films).

## Performance (a 12-inch design = 3600x3600, 10 inks)
Upload 2s, reduce 17s, separate 10s, package 11s (26s with vectors). Keep it
that way:
- chip thumbnails are rendered small (`preview_thumb`), never full-res;
- a package renders/encodes inks on a thread pool (film text is drawn under a
  lock — FreeType isn't thread-safe) and writes the zip in order;
- films are LZW TIFF, PNG/TIFF entries are stored (not re-deflated), the
  working cache writes PNG level 1;
- vectors trace each mask once (`path_data`) and walk integer edge arrays;
- `rgb_lab` of 8-bit pixels looks the sRGB curve up (`_LINEAR_8BIT`; per
  distinct colour was tried: on AVX-512 numpy's cube root differs in the last
  bit between array lengths, so it was not identical in CI); `_assign` and `_cluster`
  go one centre at a time in reused buffers (no pixels x centres tensor),
  summing in the old order so labels and ties are unchanged. Suggest +
  reduce on the six real designs: 50 s -> 40 s, outputs byte-identical.
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
  (Vite proxies `/api` to 8003). Windows: double-click `run-windows.bat`: it
  builds the app and the engine serves `frontend/dist` itself (`serve_app`,
  mounted last so /api wins) — one server on 8003, no dev server, Node only
  for the build. In a .bat, run npm as `call ...npm.cmd`: without `call` a
  .cmd never returns (the old launcher stopped after a first `npm install`).
- When changing the reduce/separation math, verify on a **real painterly image**
  (not just synthetic): reduce, separate, and check plates aren't speckled and
  the stacked plates still equal the reduced image.
