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

## v1.3.0 — Visual editor and project files
- Added a mouse/touch canvas polygon editor that converts screen coordinates to source-image pixel coordinates.
- Added self-contained `.textileai.json` project save/load, including embedded source artwork, settings, and queued undo/redo history.
- Kept existing separation, inspection, manual merge, region edit, and ZIP export APIs unchanged.
- Project save/load is browser-local file export/import; there is no server-side project database.
