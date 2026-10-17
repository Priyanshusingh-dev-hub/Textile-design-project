# TextileAI Hybrid Separation Engine — Hybrid Separation Lab — v1.6

A reference implementation scaffold for a textile screen-printing workflow that supports:
- independent spot-ink channels,
- tonal coverage maps and halftone plates,
- hybrid spot + halftone strategies,
- analysis-first planning and user-controlled overrides,
- stable plate numbering only after strategy commit.

This is an **architecture starter**, not a production-certified RIP or colour-management system. Validate all output with the target fabric, ink, mesh, emulsion, and press setup.

## Design principles
1. Never overwrite the source image.
2. Colour similarity analysis is not the same as destructive colour merging.
3. Candidate strategies are evaluated before final plate IDs are assigned.
4. Every plate stores ink identity separately from tonal coverage.
5. UI-selected settings override recommendations.
6. AI may explain/recommend; deterministic code owns pixels, masks, and validation.

## v0.8 upgrades
- Added an interactive browser plate inspector with per-plate visibility toggles, opacity controls and show/hide-all actions.\n- Added `/api/separation/inspect` to return downscaled plate mask previews, reconstruction preview and quality metrics.\n- The Generate plates action opens the inspector and still downloads the full export ZIP.\n- Exports include a plate contact-sheet preview and a CSV plate coverage report.\n- Manifest quality checks confirm both inspection artefacts are included.\n- Pixel-to-palette assignment uses CIE Lab distance after deterministic median-cut seed generation.\n- Lab conversion is implemented with NumPy only and uses chunked assignment to cap temporary memory.\n- Export manifest identifies the mapping method and engine version 0.6.0.\n- Added regression tests for Lab conversion, assignment consistency and manifest metadata.\n\nPrevious v0.5 upgrades: every strategy exports a reconstructed preview image.
- Hybrid preview approximates tonal shading while preserving the quantized palette hue.
- Export manifest reports RGB MAE, RMSE, PSNR and per-channel MAE for preview reconstruction.
- Added 17 passing tests across upload, separation, screening and preview metrics.

## v0.4 upgrades\n- Source artwork fingerprint (`source_sha256`) in the export manifest.\n- Plate count, non-empty plate and dimension checks in the manifest.\n- Source preview and spot-mode reconstructed preview included in exports.\n- Stable engine version metadata for export traceability.\n\n## Quick start
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

## Workflow
`source image -> analysis -> candidate strategies -> user selection/override -> commit -> plate IDs -> export`

## Important limitation
The starter includes basic measurable analysis and a synthetic halftone implementation for testing. It does not yet implement calibrated ink mixing, ICC-managed proofing, trapping, underbase generation, or production RIP screening. Do not use it as final production output without print-shop validation.

## Browser MVP
After starting the API, open **http://127.0.0.1:8000/**. The included responsive browser interface lets you upload a design, analyze it, choose/override the recommended strategy, and download a ZIP of prototype plates. The API also serves interactive docs at `/docs`.

### API endpoints added in MVP 0.2
- `POST /api/analysis` — multipart image upload and tonal/colour metrics.
- `POST /api/separation/candidates?gradient_score=0.12&max_inks=6` — compare the three strategies.
- `POST /api/separation/preview?strategy=hybrid&max_inks=6&lpi=45&dpi=300` — multipart upload, returns a ZIP containing preview PNGs, plate masks and `manifest.json`.

### Current implementation scope
- Spot mode: median-cut palette, with one binary mask per quantized colour.
- Halftone mode: a grayscale-derived tonal mask using a simple ordered-dither screen.
- Hybrid mode: quantized spot masks plus one grayscale-derived tonal mask.
- Upload validation: supported raster image decoding, 30 MB upload cap and 25 megapixel image cap.

These are useful development previews, not press-ready separations. Production use still needs region-aware ink mapping, perceptual colour handling, calibrated screening, ICC proofing, trapping/underbase, and validation on the target mesh/fabric/ink system.


## v0.9 upgrades
- Added a user-controlled near-colour palette seed merge threshold (approximate CIE Lab distance, 0–30).
- Exposed merge threshold through both inspection and ZIP export endpoints.
- Added UI control to merge similar palette seeds; increasing maximum inks allows finer palette detail.
- Added regression tests for merge-threshold metadata and API support.

The merge control is heuristic: it groups palette seeds using a greedy Lab-distance threshold. It is not a region-aware editor and does not guarantee a perceptually optimal merge.


## v1.0.0 — manual spot-plate merging
- Added `/api/separation/edit`, which accepts explicit merge groups and unions the selected binary spot masks into one plate.
- Added “Merge selected spots” to the browser inspector. Select two or more spot plates and download a revised ZIP.
- Rebuilds manifest plate metadata, CSV coverage report and contact sheet after merging.
- Records the requested merge groups in `manifest.json`.
- Added API regression tests for successful merges and invalid one-plate groups.

Manual merging changes exported masks and reports. The diagnostic quantized preview is approximate and is not a calibrated composite proof. Tonal plates cannot be manually merged through this endpoint.


## v1.1.0 — polygon region editing
- Added `POST /api/separation/region-edit` for deterministic polygon edits on a named spot plate.
- Supports `erase` (remove a polygon from a plate) and `add` (paint a polygon onto a plate mask), with coordinates in original-image pixels.
- Added a browser form for choosing a spot plate, operation, and polygon JSON; the edited ZIP includes updated mask, manifest, CSV report, and plate contact sheet.
- Added validation for malformed polygons, out-of-bounds coordinates, unknown plates, unsupported actions, and oversized uploads.
- Updated API/health version to 1.1.0.

Example multipart fields for `/api/separation/region-edit`:
- `plate_name=INK_01`
- `action=erase` or `action=add`
- `polygon=[[0,0],[100,0],[100,100],[0,100]]`

**Editing caveat:** polygon coordinates are source-image pixels. This is a mask-level region editor, not a brush-based canvas or undo/redo history system. The current edit endpoint starts from a fresh separation of the uploaded source for each request, so chain multiple edits by preserving/replaying the operation list in your own workflow. Reconstruction previews are diagnostic and not colour-calibrated.


## v1.2.0 — queued edit history with undo/redo
- Added `POST /api/separation/edit-history`, which validates and replays an ordered list of polygon operations on spot plates.
- Browser region editor now queues operations, supports undo/redo before export, and applies the remaining queue in sequence.
- Export manifest records `region_edits` and `edit_history_count`; reports and contact sheets are refreshed.
- Changing the source artwork clears the queued history to prevent accidental cross-image edits.
- API/health version updated to 1.2.0.

History is a browser-side operation queue, not persistent server-side project storage. Undo/redo changes the queued list; the exported masks are generated when the user clicks Apply history. The browser currently uses typed source-pixel polygon coordinates, not freehand canvas painting.


## v1.3 visual editor and project workflow
- Use the Visual Region Editor in the plate inspector: click/tap the artwork to add polygon points, then choose Finish polygon. The generated coordinates are source-image pixels and can still be edited as JSON.
- Use **Save project file** to export a self-contained `.textileai.json` file containing the source image, separation settings, and queued region-edit history. Use **Load project file** to restore it later.
- Project files are stored wherever you download them; the application does not yet maintain cloud or server-side project storage. Canvas overlay is a region-selection guide, not a calibrated print preview.

## v1.3.1 — Alpha transparency & dynamic composite preview
- Transparent PNG preservation: transparent areas produce 0% ink coverage without unwanted black inversion.
- Full-resolution composite renderer (`POST /api/separation/composite`) with layer visibility, per-plate opacity, and fabric ground color simulation (White, Navy, Black, Heather Grey, Linen).
- Client-side HTML5 Canvas preview for real-time adjustments without roundtrip latency.

## v1.4.0 — White Underbase, Spot Trapping, Film Positives & Interactive Recoloring
- **White Underbase (`UNDERBASE_WHITE`)**: Configurable 0-10px choke via mathematical morphological erosion (`ImageFilter.MinFilter(3)`), perfectly masking dark garment prints without white peeking along color edges.
- **Auto-Trapping (Choke/Spread)**: Automatic 1-5px trapping based on color luminance, slightly dilating lighter spot plates under darker adjacent plates along color boundaries to prevent white gaps from mechanical press registration shifts.
- **Press-Ready Film Positives**: Full film positive generation with 8-point perimeter registration crosshair targets and plate job metadata slugs burned into the margins for direct screen burning on exposure units.
- **Interactive Plate Recoloring**: Live `<input type="color">` swatch controls directly on each plate inspector card; immediately updates both client-side canvas composite and server-side composite proof.
- **Format & Orientation Resilience**: Integrated `ImageOps.exif_transpose` and seamless ingestion for Grayscale (`L`), Palette (`P`), CMYK, and RGBA images.
- **Automated Verification**: Comprehensive regression test coverage across all features (47 passing tests).

## v1.5.0 — Speckle Mesh Cleanup, Seamless Repeat Continuity & Pattern Tiling
- **Mesh Speckle Cleanup (`min_feature_px`)**: Connected-component island filtering using `scipy.ndimage.label` (with morphological `MedianFilter` fallback) to eliminate isolated 1-6px orphan speckles smaller than screen mesh apertures, preventing pinhole washouts and mesh clogging.
- **Continuous Repeat Seam Diagnostics**: Edge boundary color continuity analysis (`is_seamless_repeat`, `horizontal_seam_delta`, `vertical_seam_delta`) in `/api/analysis` to identify seamless fabric tiles.
- **Multi-Up Pattern Tiling Preview**: Instant client-side and server-side $1\times 1$, $2\times 2$, and $3\times 3$ pattern repeat preview tiling on the inspector canvas.
- **Workflow & Proofing Integration**: Seamless project persistence (`.textileai.json`) of speckle cleanup settings and tiled composite proofing.
- **Screen Mesh & Ink Estimation**: Prepress recommendations for recommended polyester screen mesh count (110–156 for underbase, 156–230 for spot, 200–355 for tonal screens) and ink consumption estimates in grams per 100 prints integrated into reports, manifest, and plate cards.
- **Automated Verification**: 52 passing automated regression tests.
 
## v1.6.0 — Production Prepress Enhancements, 8-Connectivity Noise Filtering, Seam Defect Analysis & Batch Collection Processing
- **8-Connectivity Stroke Protection**: Noise cleanup algorithm (`cleanup_isolated_noise`) uses full 8-connectivity `np.ones((3, 3), dtype=bool)` structuring element in `scipy.ndimage.label`. Fine diagonal stippling and 1-pixel diagonal strokes are recognized as connected textile motifs and preserved, preventing accidental erasure of valid design features.
- **Euclidean Repeat Seam Defect Detection & Consistent Diagnostics**: Per-pixel Euclidean color distance along tile seams calculates mean, 95th percentile, and maximum seam deltas (`horizontal_seam_max`, `vertical_seam_max`, `horizontal_seam_p95`, `vertical_seam_p95`). Diagnostic repeat warnings are fully consistent with classification thresholds, explicitly reporting mean, p95, and max metrics for both axes.
- **Shared Prepress Ink Consumption Estimation**: Centralized theoretical ink consumption into `calculate_theoretical_ink_estimate()` across `/preview`, `/edit`, `/region-edit`, `/edit-history`, and `/batch` endpoints. Implements documented deposit rates for each plate type (underbase: 50 g/m², spot: 30 g/m², tonal/halftone: 18 g/m²) and marks unknown plate types as `unavailable` rather than silently defaulting.
- **Multi-Design Batch Collection Processing**: `POST /api/separation/batch` endpoint processes entire colorway collections or motif sets in a single call. Exports a consolidated ZIP with sanitized per-design directories, individual plate sets and film positives, `batch_manifest.json`, and an overall `batch_summary.csv`.
- **Frontend Batch Workflow**: Integrated batch collection file selector and trigger button (`batchBtn`) in `index.html` with mobile/Android multi-file selection support.
- **Endpoint Parameter Persistence**: Verified consistent propagation of `min_feature_px` across `/inspect`, `/preview`, `/composite`, `/edit`, `/region-edit`, `/edit-history`, and `/batch` endpoints.
- **Automated Verification**: 74 passing automated regression tests with 100% pass rate. Comprehensive test suites validate real-world textile cases (smooth gradients, similar adjacent colors, fine floral outlines with trapping, diagonal stippling and 1-px strokes, transparent PNGs, and hybrid flat/continuous tonal separation), end-to-end export integrity, prepress choke/registration targets, and project save/load persistence.


