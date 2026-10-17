# Changelog

## v1.2.0
- Added ordered edit-history replay endpoint.
- Added queued region operations with browser-side undo/redo controls.
- Added history metadata to exports and reset history when source image changes.
- Updated API version to 1.2.0.

## v1.1.0
- Added polygon-based spot plate region editing (`add` and `erase`) through `/api/separation/region-edit`.
- Added browser controls for plate selection, operation and source-pixel polygon coordinates.
- Added updated region-edit exports, validation and regression tests.
- Updated API version to 1.1.0.

## v1.0.0
- Added manual merge of selected spot plates via `/api/separation/edit`.
- Added inspector selection checkboxes and a “Merge selected spots” export action.
- Rebuilt CSV report and contact sheet after a merge.
- Added regression tests for valid and invalid merge groups.

## v0.9.0
- Added approximate Lab-threshold merging for similar palette seeds, disabled by default.
- Exposed merge threshold in browser controls and inspection/export API.

## Limitations
Manual spot merging unions binary masks and updates reports. It does not provide region painting, pixel-level split, or production-calibrated colour proofing. Tonal plates are excluded from manual merge. The composite preview remains diagnostic only. Validate output with the target fabric, ink, mesh, emulsion and press.

## v1.3.1 — Alpha transparency & dynamic composite preview
- Added alpha-channel and transparency preservation across spot, halftone, and hybrid modes; unprinted transparent backgrounds no longer cause spurious black plates or inverted coverage.
- Added `/api/separation/composite` endpoint for high-resolution composite rendering with per-plate opacity, visibility, and fabric color simulation.
- Added live client-side HTML5 Canvas composite preview in the browser inspector with real-time opacity sliders and fabric ground selection (White, Navy, Black, Heather Grey, Natural Linen).
- Fixed Show all / Hide all checkbox selector collision that previously toggled merge checkboxes.
- Added comprehensive regression tests verifying opacity pixel effects, transparency preservation, and composite API endpoints (37 total passing tests).

## v1.4.0 — White Underbase, Spot Trapping, Film Positives & Interactive Recoloring
- Added white underbase mask generation (`UNDERBASE_WHITE`) with configurable choke (0-10px) using mathematical morphological erosion (`ImageFilter.MinFilter(3)`) to eliminate white fringing on dark fabric printing.
- Added automatic spot plate trapping (1-5px choke/spread) using luminance-based morphological dilation (`ImageFilter.MaxFilter(3)`), expanding lighter inks slightly under darker adjacent inks along seams to eliminate registration gaps on press.
- Added press-ready film positive generation with industry-standard 8-point perimeter registration crosshair targets and plate job metadata slugs burned into the margin for direct screen exposure.
- Added native image ingestion support for EXIF orientation transposition and diverse image modes (Grayscale `L`, Palette `P`, CMYK, and RGBA).
- Added interactive plate recoloring swatches (`<input type="color">`) in the browser inspector for real-time client-side canvas recoloring and server-side composite proof generation.
- Exposed `generate_underbase`, `underbase_choke_px`, `apply_trapping`, `trap_px`, `include_registration_marks`, and `film_margin_px` parameters across `/api/separation/inspect`, `/api/separation/preview`, and `/api/separation/composite`.
- Added automated regression tests verifying morphological choking/spreading, underbase generation, seam overlap calculations, film positive geometry, transparent pixel masking, non-RGB ingestion, and API integration (47 total passing tests).

## v1.5.0 — Speckle Mesh Cleanup, Seamless Repeat Continuity & Pattern Tiling
- Added connected-component speckle noise cleanup (`cleanup_isolated_noise`) via `scipy.ndimage.label` with `ImageFilter.MedianFilter(3)` fallback, removing isolated pinhole islands smaller than or equal to `min_feature_px` (0-6px in UI, 0-20px in API) to prevent mesh aperture clogging and washout failure.
- Manifest tracks `min_feature_px`, `speckles_cleaned` total count, and `speckle_cleanup_applied` quality check.
- Added textile pattern repeat seam continuity diagnostics in `analyze_rgb`: evaluates boundary RGB color transitions to determine `is_seamless_repeat`, `horizontal_seam_delta`, and `vertical_seam_delta`.
- Added interactive client-side and server-side pattern repeat tiling preview (`1×1`, `2×2`, `3×3`) in the plate inspector canvas for instant repeat flow and seam verification.
- Added UI repeat seam badges and hints in analysis dashboard.
- Integrated `min_feature_px` into `.textileai.json` project save/load workflows and composite endpoints.
- Added screen-print prepress recommendations: per-plate recommended polyester mesh count (110-156 for underbase, 156-230 for spot, 200-355 for halftones based on LPI rule-of-thumb) and estimated ink volume consumption in grams per 100 garment prints based on physical area and coverage.
- Exposed prepress recommendations across `manifest.json`, `reports/plate_summary.csv`, and inspector plate cards.
## v1.6.0 — Production Prepress Enhancements, 8-Connectivity Noise Filtering, Seam Defect Analysis & Batch Collection Processing
- Upgraded `cleanup_isolated_noise` using 8-connectivity `np.ones((3, 3), dtype=bool)` structuring element in `scipy.ndimage.label` to preserve delicate diagonal strokes, stippling, and fine textile motifs while eliminating true orphan noise dots.
- Upgraded repeat continuity checking with Euclidean color distance, 95th percentile delta, and localized max delta (`horizontal_seam_max`, `vertical_seam_max`) to reliably detect localized edge defects that would pass under an average-only check.
- Added `/api/separation/batch` endpoint supporting multi-design uploads yielding structured ZIPs with per-design folders, individual manifests/plates/film positives, `batch_manifest.json`, and `batch_summary.csv`.
- Added Batch Collection file picker and trigger button in `index.html` with mobile/Android multi-file selection support.
- Added explicit prepress ink estimation assumptions (underbase ~50g/m², spot ~30g/m², tonal ~18g/m²; setup reservoir minimums) and mesh recommendations disclaimer to `manifest.json`.
- Ensured `min_feature_px` is persisted and consistently applied across all endpoints (`/inspect`, `/preview`, `/composite`, `/edit`, `/region-edit`, `/edit-history`, `/batch`).
- Added comprehensive regression tests verifying 8-connectivity stroke protection, localized repeat seam defect rejection, endpoint min_feature_px persistence, batch collection processing, and frontend controls integrity (57 total passing tests).


