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

