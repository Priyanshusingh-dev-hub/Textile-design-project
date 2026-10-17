# Implementation Roadmap

## Phase 0 — Audit current repository
- Find the existing colour merge/quantization function.
- Trace frontend settings -> API payload -> backend processing -> plate export.
- Record current tests and outputs before changing behaviour.
- Do not replace existing engine until regression baseline is captured.

## Phase 1 — Source preservation and analysis
- Immutable source storage and image metadata.
- Upload validation, decompression limits and file type checks.
- Analysis report for colours, tonal variation, edges, dimensions and print warnings.
- Add unit tests with synthetic gradients and real reference fixtures.

## Phase 2 — Strategy candidates
- Generate spot, halftone and hybrid candidates.
- Show estimated screen count, reconstruction quality and caveats.
- User can choose/override; no silent merge.

## Phase 3 — Tonal maps and plates
- Separate ink identity from coverage.
- Implement calibrated screening, dot geometry and output polarity.
- Stable numbering only after plan commit.
- Validate registration, overlaps, gaps and minimum printable features.

## Phase 4 — Colour management
- ICC-aware conversion and proofing.
- Measured ink/substrate profiles.
- Dot gain compensation, trapping, underbase and print-order controls.

## Phase 5 — UI and production export
- Original / composite / individual plate views.
- Per-plate controls, manual merge/split and history.
- Export lossless plate files, manifest, preview and audit report.
- Test on the actual production process before release.

## Definition of done for first usable milestone
- Source image never mutated.
- Existing flat-colour workflow passes regression tests.
- User can compare at least spot and halftone candidates.
- User override is respected.
- Plate IDs stable after commit.
- Tests cover tonal preservation, mask polarity and export dimensions.


## Completed in v0.4
- Added a source-pixel SHA-256 fingerprint to export manifests.
- Added engine/version traceability, actual plate counts and non-empty plate checks.
- Bundled source preview and a spot-mode reconstructed preview in the ZIP.
- Added regression tests for fingerprint presence and ink-count limits.
- Verification: `pytest -q` → 15 passed.

## Next production-oriented milestone
Implement perceptual colour-space palette selection and per-region gradient maps; then add a proper reconstructed composite for hybrid output. Keep calibrated CMYK/ICC proofing, trapping and press-specific screening as separately validated features.


## Completed in v0.5
- Reconstructed preview is bundled for spot, halftone and hybrid strategies.
- Export includes RGB MAE, RMSE, PSNR and per-channel MAE diagnostics.
- Preview endpoint enforces the 25-megapixel limit consistently.
- Verification: `pytest -q -p no:cacheprovider` → 17 passed.

## Next
Replace RGB median-cut palette approximation with a perceptual colour-space palette workflow, expose per-plate preview toggles in the UI, and add region-aware tonal maps. Physical print proofing still requires ICC/device calibration and press validation.


## Completed in v0.6
- Added NumPy-only sRGB-to-CIE-Lab conversion and chunked nearest-seed palette assignment.
- Plate masks and quantized previews now share the same perceptual label map.
- Manifest schema 0.5 and engine version 0.6.0 identify the new mapping method.
- Added tests for conversion, label assignment and manifest metadata.

## Next
Add region-aware gradient mapping and UI plate visibility toggles. Lab distance is not a substitute for ICC profiles, measured ink/substrate behaviour or physical print calibration.


## Completed in v0.7
- Added `preview/plate_contact_sheet.png` to inspect each plate mask, plate type, swatch and coverage.
- Added `reports/plate_summary.csv` with per-plate colour/type/file/coverage metadata.
- Export manifest verifies the contact sheet and CSV report are present.
- Verification target: automated tests cover artefact generation and manifest traceability.

## Next
Add interactive per-plate toggles and region-aware tonal mapping in the browser. These inspection artefacts do not replace calibrated ICC proofing or press testing.


## Completed in v0.8
- Added a lightweight JSON inspection endpoint with downscaled PNG masks and a reconstruction preview.
- Added browser controls to show/hide each plate and adjust thumbnail opacity.
- Added show-all/hide-all actions and reconstruction metric display.
- Added an endpoint regression test for response structure.

## Next
Implement real plate recomposition (currently controls affect visual inspection only), manual palette merge/split, and region-aware gradient preservation. Inspection opacity does not change exported plate data.


## Completed in v0.9
- User-adjustable approximate Lab-distance merge threshold, exposed in the UI and both inspect/export APIs.
- Metadata records the chosen merge threshold and palette method.
- Regression tests cover threshold use and endpoint response.

## Next
True region-aware split/merge editing, regenerated plate composites, and plate-level colour remapping.


## Completed in v1.0
- Manual multi-plate spot-mask union through the API.
- Browser plate selection and merge-export action.
- Updated plate CSV and contact sheet after a merge.
- Regression coverage for the manual-merge endpoint.

## Next
Manual region-based split/paint, plate colour reassignment with true composite recomposition, undo/redo, and export validation for production workflows.
