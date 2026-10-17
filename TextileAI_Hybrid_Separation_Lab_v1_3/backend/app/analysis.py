import numpy as np
from .models import AnalysisReport

def analyze_rgb(image: np.ndarray) -> AnalysisReport:
    """Basic deterministic analysis for an HxWx3 uint8 RGB array.

    This is a starter diagnostic, not a complete gradient segmentation algorithm.
    Keep the original image separately; never use this report to overwrite pixels.
    """
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("Expected HxWx3 uint8 RGB image")
    h, w, _ = image.shape
    rgb = image.astype(np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    dx = np.abs(np.diff(luminance, axis=1)) if w > 1 else np.zeros((h, 0))
    dy = np.abs(np.diff(luminance, axis=0)) if h > 1 else np.zeros((0, w))
    mean_step = (float(dx.mean()) if dx.size else 0.0) + (float(dy.mean()) if dy.size else 0.0)
    # Combine adjacent-pixel changes with overall tonal spread. This is a useful
    # routing heuristic, not a semantic gradient/region segmentation score.
    tonal_spread = float(luminance.std())
    gradient_score = float(np.clip(0.65 * min(1.0, mean_step * 8.0) + 0.35 * tonal_spread, 0.0, 1.0))
    edge_score = float(np.clip(mean_step * 2.0, 0.0, 1.0))
    unique = int(np.unique(image.reshape(-1, 3), axis=0).shape[0])
    # Seam continuity check for textile repeat patterns (left vs right, top vs bottom)
    h_delta = float(np.mean(np.abs(rgb[:, 0] - rgb[:, -1]))) if w > 1 else 0.0
    v_delta = float(np.mean(np.abs(rgb[0, :] - rgb[-1, :]))) if h > 1 else 0.0
    is_seamless = bool(h_delta < 0.04 and v_delta < 0.04)

    warnings = []
    if is_seamless:
        warnings.append("Pattern repeat: edges align seamlessly for continuous fabric tiling.")
    elif h_delta > 0.15 or v_delta > 0.15:
        warnings.append(f"Repeat seam discontinuity detected (horizontal delta {h_delta:.2f}, vertical delta {v_delta:.2f}). Check pattern tile alignment.")
    if min(w, h) < 256:
        warnings.append("Small source image: inspect output at final physical print size.")
    if unique > 50000:
        warnings.append("High colour diversity: avoid one-screen-per-RGB-value separation.")
    if tonal_spread > 0.22:
        warnings.append("Broad tonal range detected: compare halftone and hybrid outputs before committing plates.")
    if w * h > 12_000_000:
        warnings.append("Large artwork: preview generation may take time and use substantial memory.")
    return AnalysisReport(
        width=w,
        height=h,
        estimated_unique_rgb=unique,
        mean_luminance=float(luminance.mean()),
        luminance_stddev=float(luminance.std()),
        gradient_score=gradient_score,
        edge_score=edge_score,
        is_seamless_repeat=is_seamless,
        horizontal_seam_delta=round(h_delta, 4),
        vertical_seam_delta=round(v_delta, 4),
        warnings=warnings,
    )
