# Architecture & Engineering Plan

## Pipeline
1. Ingest source immutably; preserve dimensions, alpha and profile metadata.
2. Analyze colour statistics, tonal variation, edges and print constraints.
3. Generate spot, halftone and hybrid candidates.
4. Show trade-offs and allow manual override.
5. Commit the selected strategy; only then assign stable PLATE_001... IDs.
6. Generate coverage masks and screened plates.
7. Validate dimensions, blank plates, tonal monotonicity, minimum features and registration metadata.
8. Export plates, composite preview, ink manifest and reproducibility settings.

## Domain concepts
- SourceImage: immutable source reference and metadata.
- AnalysisReport: colour statistics, gradient score, edge/detail indicators and warnings.
- InkDefinition: ink ID, nominal colour and optional measured profile.
- TonalChannel: continuous coverage map (0..1) for an ink.
- Plate: final monochrome raster and metadata.
- SeparationPlan: strategy, ink budget, screening settings and user overrides.
- CommittedSeparation: frozen plan and stable plate IDs.

## Strategy semantics
- spot: solid coverage mask per ink; tonal gradation needs extra inks or another mode.
- halftone: screen tonal coverage into dots.
- hybrid: combine solid spot plates and selected tonal halftones.

## Planner
Apply hard constraints first: max screens, allowed inks, target dimensions/DPI, validated LPI/dot geometry and underbase policy. Then rank feasible candidates by perceptual reconstruction error, screen count, detail retention and registration sensitivity. Without measured ink/substrate data, label preview as an estimate.

## Colour matching policy
Preserve source pixels. Use perceptual distance only to propose merges/palette candidates. Never silently merge. User-approved merges must be reversible and recorded. Keep ink identity, tonal coverage and plate raster as separate objects.

## Numbering
Use temporary candidate IDs while planning. Assign stable plate IDs only after commit. Regenerate affected plates if palette or strategy changes.

## Later modules
ICC proofing, measured ink/substrate profiles, dot-gain compensation, trapping, underbase, overprint controls, seamless-repeat checks, async jobs, cancellation, progress, caching and audit history.
