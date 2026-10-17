# Architecture & Engineering Plan

## Pipeline
1. **Ingest**: preserve original bytes, dimensions, alpha and embedded profile metadata.
2. **Analyze**: collect colour statistics, gradient/edge indicators, dimensions and source diagnostics.
3. **Plan**: evaluate spot, halftone and hybrid candidates under screen-count and print constraints.
4. **Review**: show candidate previews and estimated trade-offs; allow manual mapping and strategy override.
5. **Commit**: freeze settings and only then allocate stable `PLATE_001...` IDs.
6. **Generate**: create independent coverage masks, apply selected screening method, keep source immutable.
7. **Validate**: check dimensions, plate count, blank plates, tonal monotonicity, minimum feature/dot constraints and registration metadata.
8. **Export**: plate images, composite preview, ink manifest and reproducibility settings.

## Core domain concepts
- `SourceImage`: immutable source reference and metadata.
- `AnalysisReport`: colour statistics, gradient score, edge/detail indicators, print warnings.
- `InkDefinition`: ink ID, nominal colour/specification, optional measured profile.
- `TonalChannel`: continuous coverage map (0..1) for an ink.
- `Plate`: final monochrome raster / screen image and metadata.
- `SeparationPlan`: candidate strategy, ink budget, screening settings and user overrides.
- `CommittedSeparation`: frozen plan and stable plate IDs.

## Strategy semantics
- `spot`: one solid coverage mask per ink; tonal gradation requires separate inks or a different mode.
- `halftone`: tonal coverage for an ink is screened into dots.
- `hybrid`: selected regions/inks use spot plates while other tonal channels are halftoned.

## Recommendation logic
The planner should treat production constraints as hard constraints first:
- maximum screens,
- allowed ink list,
- target physical size and DPI,
- validated LPI/dot geometry for selected mesh/process,
- allowed transparency/underbase policy.

Then rank feasible candidates using:
- reconstruction error in a perceptual space,
- number of screens,
- detail retention,
- expected registration sensitivity,
- expected ink/fabric interactions if calibrated data exists.

Do not claim accurate print simulation without measured ink/substrate profiles. If calibration data is absent, label the preview as an estimate.

## Colour matching policy
- Preserve source pixels.
- Use perceptual distance only to propose merges or palette candidates.
- Never silently merge colours.
- User-approved merges must be reversible and tracked in the project history.
- Keep `ink identity`, `tonal coverage`, and `plate raster` as separate objects.

## Numbering
Temporary candidate IDs are used during planning. Assign stable plate IDs only after commit. When palette/strategy changes, regenerate affected plates and update the committed manifest deterministically.

## Suggested later modules
- ICC profile-aware source conversion and proofing.
- Ink/substrate calibration model and measured colour library.
- Dot gain compensation, trapping/choke/spread, underbase and overprint controls.
- Seamless repeat edge consistency checks for textile patterns.
- Async job queue, cancellation, progress reporting, caching and audit trail.


## MVP 0.3 notes
The ordered-dither preview now derives an approximate screen-cell size from DPI/LPI and writes this value plus basic output quality checks into the manifest. This is a reproducible preview approximation only: it is not a calibrated screen angle, mesh compensation, ICC proof, or production RIP. Analysis uses both local luminance differences and global tonal spread for strategy routing; it must not be treated as semantic gradient segmentation.


## v0.4 export traceability
Every separation ZIP now includes the SHA-256 fingerprint of the decoded RGB source pixels, engine version, requested ink limit, actual plate count, palette method, non-empty plate checks, and source dimensions. The source preview is bundled for direct comparison; spot mode also includes a quantized reconstruction preview. The fingerprint identifies decoded pixels, not the original file bytes or its metadata.


## v0.5 reconstruction diagnostics
The export now contains a reconstructed preview for each strategy and RGB MAE/RMSE/PSNR metrics comparing that preview with the decoded source pixels. These values quantify only the software preview's pixel error; they are not colour-difference measurements (such as Delta E), ICC proofing, or predictions of physical ink on fabric. The hybrid reconstruction is a visual heuristic and must not be used as a press proof.


## v1.1 region-edit API
`POST /api/separation/region-edit` accepts `plate_name`, `action` (`add` or `erase`), and a JSON polygon of source-pixel coordinates. It modifies a single spot plate mask and refreshes manifest coverage metadata, CSV report, and contact sheet. This is mask editing; it does not alter source pixels or provide chained transactional history.


## v1.2 edit history
`POST /api/separation/edit-history` accepts an ordered `operations` JSON list. Each operation has `plate_name`, `action` (`add`/`erase`) and `polygon` points in source pixels. The browser stores a temporary undo/redo queue; the API replays the surviving queue on freshly generated masks and exports updated reports. History is not persisted server-side.
