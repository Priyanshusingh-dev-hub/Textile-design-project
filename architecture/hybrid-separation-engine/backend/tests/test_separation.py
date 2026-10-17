import numpy as np
import pytest
from app.analysis import analyze_rgb
from app.separation import halftone_mask, recommend_candidates, commit_plate_ids
from app.models import SeparationSettings

def test_analysis_detects_dimensions_and_tones():
    img = np.zeros((32, 64, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(np.arange(64, dtype=np.uint8) * 4, (32, 1))
    report = analyze_rgb(img)
    assert (report.width, report.height) == (64, 32)
    assert report.estimated_unique_rgb > 1
    assert report.luminance_stddev > 0

def test_halftone_coverage_is_monotonic():
    low = np.full((64, 64), 0.2, dtype=np.float32)
    high = np.full((64, 64), 0.8, dtype=np.float32)
    assert (halftone_mask(high) > 0).mean() > (halftone_mask(low) > 0).mean()

def test_invalid_coverage_rejected():
    with pytest.raises(ValueError):
        halftone_mask(np.array([[1.2]], dtype=np.float32))

def test_planner_recommends_tonal_mode_for_gradient():
    plan = recommend_candidates(0.2, 8)
    assert plan.recommendation in ("halftone", "hybrid")
    assert {c.strategy for c in plan.candidates} == {"spot", "halftone", "hybrid"}

def test_plate_ids_assigned_on_commit():
    settings = SeparationSettings(strategy="hybrid", max_inks=4)
    plates = commit_plate_ids(settings, ["pink", "navy"])
    assert [p["plate_id"] for p in plates] == ["PLATE_001", "PLATE_002"]
