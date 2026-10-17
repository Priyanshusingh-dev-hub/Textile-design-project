import numpy as np
from .models import AnalysisReport

def analyze_rgb(image: np.ndarray) -> AnalysisReport:
    """Basic diagnostics for an HxWx3 uint8 RGB image; does not modify source."""
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("Expected HxWx3 uint8 RGB image")
    h, w, _ = image.shape
    rgb = image.astype(np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    dx = np.abs(np.diff(luminance, axis=1)) if w > 1 else np.zeros((h, 0))
    dy = np.abs(np.diff(luminance, axis=0)) if h > 1 else np.zeros((0, w))
    gradient_score = float(min(1.0, (float(dx.mean()) if dx.size else 0.0) +
                               (float(dy.mean()) if dy.size else 0.0)))
    edge_score = float(min(1.0, 2.0 * ((float(dx.mean()) if dx.size else 0.0) +
                                      (float(dy.mean()) if dy.size else 0.0))))
    unique = int(np.unique(image.reshape(-1, 3), axis=0).shape[0])
    warnings = []
    if min(w, h) < 256:
        warnings.append("Small source image: inspect at final physical print size.")
    if unique > 50000:
        warnings.append("High colour diversity: do not create one screen per RGB value.")
    return AnalysisReport(width=w, height=h, estimated_unique_rgb=unique,
        mean_luminance=float(luminance.mean()), luminance_stddev=float(luminance.std()),
        gradient_score=gradient_score, edge_score=edge_score, warnings=warnings)
