# Implementation Roadmap

## Phase 0 — Audit current repository
- Locate current colour merge/quantization function.
- Trace frontend settings -> API payload -> backend -> plate export.
- Capture current tests and baseline output before changing behaviour.
- Avoid replacing existing engine until regression baseline is recorded.

## Phase 1 — Source preservation and analysis
- Immutable source storage and metadata.
- Upload validation and image-size/decompression limits.
- Report colour statistics, tonal variation, edges, dimensions and print warnings.
- Unit tests with synthetic gradients and real reference fixtures.

## Phase 2 — Strategy candidates
- Generate spot, halftone and hybrid candidates.
- Compare estimated screens, reconstruction quality and caveats.
- Respect manual override; never silently merge colours.

## Phase 3 — Tonal maps and plates
- Separate ink identity from coverage.
- Implement calibrated screening and output polarity.
- Stable numbering after commit.
- Validate registration, overlaps, gaps and minimum printable features.

## Phase 4 — Colour management
- ICC proofing and measured ink/substrate profiles.
- Dot gain, trapping, underbase and overprint controls.

## Phase 5 — UI and production export
- Original/composite/individual plate views.
- Per-plate controls, manual merge/split and history.
- Lossless plate export, manifest and audit report.
- Physical print tests before production release.

## First milestone definition of done
- Source image remains immutable.
- Existing flat-colour workflow passes regression tests.
- Spot and halftone candidates can be compared.
- User override is respected.
- Stable plate IDs assigned on commit.
- Tests cover tonal coverage, mask polarity and output dimensions.
