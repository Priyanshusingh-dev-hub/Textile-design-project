import numpy as np
from .models import Candidate, PlanResponse, SeparationSettings

def recommend_candidates(gradient_score: float, max_inks: int) -> PlanResponse:
    """Transparent heuristic placeholder; replace with calibrated candidate scoring."""
    if gradient_score >= 0.08:
        recommendation = "hybrid" if max_inks >= 4 else "halftone"
    else:
        recommendation = "spot"
    candidates = [
        Candidate(strategy="spot", estimated_plates=max_inks,
                  rationale="Clean solid regions; gradients require extra inks or another mode."),
        Candidate(strategy="halftone", estimated_plates=max_inks,
                  rationale="Encodes continuous tone as screened coverage.",
                  caveats=["Validate LPI, dot geometry and minimum dot on target mesh."]),
        Candidate(strategy="hybrid", estimated_plates=max_inks,
                  rationale="Combines spot plates with selected tonal halftones.",
                  caveats=["Production version needs explicit region/ink mapping."]),
    ]
    return PlanResponse(recommendation=recommendation, candidates=candidates)

def halftone_mask(coverage: np.ndarray, lpi: int = 45, dpi: int = 300) -> np.ndarray:
    """Simple ordered-screen prototype for tests, not production-calibrated."""
    if coverage.ndim != 2:
        raise ValueError("Expected a 2D coverage map")
    if not (10 <= lpi <= 100 and dpi >= 72):
        raise ValueError("Unsupported prototype LPI/DPI")
    if np.any(coverage < 0) or np.any(coverage > 1):
        raise ValueError("Coverage values must be within [0, 1]")
    h, w = coverage.shape
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                      [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)
    threshold = (bayer + 0.5) / 16.0
    tiled = np.tile(threshold, (int(np.ceil(h / 4)), int(np.ceil(w / 4))))[:h, :w]
    return np.where(coverage >= tiled, 255, 0).astype(np.uint8)

def commit_plate_ids(settings: SeparationSettings, ink_ids: list[str]) -> list[dict]:
    """Assign stable IDs only after the user confirms a plan."""
    return [{
        "plate_id": f"PLATE_{index:03d}", "ink_id": ink_id,
        "strategy": settings.strategy,
        "channel_type": "tonal" if settings.strategy in ("halftone", "hybrid") else "spot",
        "dpi": settings.dpi,
        "lpi": settings.lpi if settings.strategy in ("halftone", "hybrid") else None,
    } for index, ink_id in enumerate(ink_ids, start=1)]
