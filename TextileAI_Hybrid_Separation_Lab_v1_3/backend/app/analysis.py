import numpy as np
from .models import AnalysisReport

def analyze_rgb(image: np.ndarray) -> AnalysisReport:
    """Basic deterministic analysis for an HxWx3 uint8 RGB array.

    This is a starter diagnostic, not a complete gradient segmentation algorithm.
    Keep the original image separately; never use this report to overwrite pixels.
    The repeat continuity metric is an edge boundary diagnostic evaluating seam deltas;
    do not label a tile production-seamless based solely on this heuristic, as it does
    not guarantee visual repeat quality across internal motif structures.
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
    # Per-pixel Euclidean color distance along borders for textile repeat verification
    if w > 1:
        h_diffs = np.linalg.norm(rgb[:, 0, :] - rgb[:, -1, :], axis=-1) / np.sqrt(3.0)
        h_mean_delta = float(np.mean(h_diffs))
        h_max_delta = float(np.max(h_diffs))
        h_p95_delta = float(np.percentile(h_diffs, 95))
    else:
        h_mean_delta, h_max_delta, h_p95_delta = 0.0, 0.0, 0.0

    if h > 1:
        v_diffs = np.linalg.norm(rgb[0, :, :] - rgb[-1, :, :], axis=-1) / np.sqrt(3.0)
        v_mean_delta = float(np.mean(v_diffs))
        v_max_delta = float(np.max(v_diffs))
        v_p95_delta = float(np.percentile(v_diffs, 95))
    else:
        v_mean_delta, v_max_delta, v_p95_delta = 0.0, 0.0, 0.0

    # A pattern is genuinely seamless only when the mean color delta is low AND
    # there are no localized seam mismatch spikes (95th percentile and max thresholds).
    is_seamless = bool(
        h_mean_delta < 0.035 and v_mean_delta < 0.035 and
        h_p95_delta < 0.08 and v_p95_delta < 0.08 and
        h_max_delta < 0.15 and v_max_delta < 0.15
    )

    warnings = []
    if is_seamless:
        warnings.append(
            "Pattern repeat: edge borders align within repeat tolerance "
            "(edge continuity diagnostic, not proof of visual repeat quality)."
        )
    else:
        warnings.append(
            f"Repeat seam discontinuity detected (H: mean {h_mean_delta:.2f}, p95 {h_p95_delta:.2f}, max {h_max_delta:.2f}; "
            f"V: mean {v_mean_delta:.2f}, p95 {v_p95_delta:.2f}, max {v_max_delta:.2f}). Edge motifs do not align across boundary."
        )
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
        horizontal_seam_delta=round(h_mean_delta, 4),
        vertical_seam_delta=round(v_mean_delta, 4),
        horizontal_seam_p95=round(h_p95_delta, 4),
        vertical_seam_p95=round(v_p95_delta, 4),
        horizontal_seam_max=round(h_max_delta, 4),
        vertical_seam_max=round(v_max_delta, 4),
        warnings=warnings,
    )
