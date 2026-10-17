"""Region classifier for LoomLab "auto mode".

Labels every pixel in a textile design image as one of:
- 0 = FLAT: solid single-colour patch (plain ground, flat petal, flat motif).
- 1 = LINE: fine lines, stripes, veins, outlines, small dots (roughly 1-12 px wide).
- 2 = SHADED: real spray/airbrush tone, irregular continuous gradients.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Union

import cv2
import numpy as np
from PIL import Image


def classify_regions(rgb: np.ndarray, *, min_region_px: int = 64) -> Dict[str, Any]:
    """Classify every pixel in rgb as FLAT (0), LINE (1), or SHADED (2).

    Parameters
    ----------
    rgb : np.ndarray
        HxWx3 uint8 image array.
    min_region_px : int, optional
        Minimum pixel area for contiguous shaded or flat regions (default: 64).
        Small islands below this area are merged into surrounding regions.
        LINE features (including small dots and fine veins) are preserved.

    Returns
    -------
    dict
        {
            "labels": HxW uint8 array (0 FLAT, 1 LINE, 2 SHADED),
            "fractions": {"flat": f, "line": f, "shaded": f},  # sum to 1.0
            "has_shading": bool,  # True only if shaded fraction > 0.5%
            "has_lines": bool,    # True only if line fraction > 0.5%
        }
    """
    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be a 3D numpy array of shape (H, W, 3)")

    H, W = rgb.shape[:2]
    total_px = H * W
    if total_px == 0:
        return {
            "labels": np.zeros((H, W), dtype=np.uint8),
            "fractions": {"flat": 1.0, "line": 0.0, "shaded": 0.0},
            "has_shading": False,
            "has_lines": False,
        }

    # Work in Lab colour space (scaled to standard Delta E units)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[:, :, 0] * (100.0 / 255.0)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0

    # 1. Continuous variation & gradient magnitude in Lab space
    grad_sq = np.zeros((H, W), dtype=np.float32)
    var_tot = np.zeros((H, W), dtype=np.float32)
    for ch in [L, a, b]:
        gx = cv2.Sobel(ch, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(ch, cv2.CV_32F, 0, 1, ksize=3)
        grad_sq += gx**2 + gy**2

        m = cv2.boxFilter(ch, cv2.CV_32F, (7, 7))
        m2 = cv2.boxFilter(ch**2, cv2.CV_32F, (7, 7))
        var_tot += np.maximum(0.0, m2 - m**2)

    mag = np.sqrt(grad_sq)
    std_local = np.sqrt(var_tot)

    # Shaded variation: sustained non-zero gradient AND local standard deviation
    # In Lab, typical JPEG compression noise has std < 2.0, mag < 1.0
    var_mask = ((mag > 1.2) & (std_local > 2.2)).astype(np.uint8)

    # Morphological opening (radius 2 ellipse, 5x5) to eliminate hard step-edges
    # and thin line boundaries (which are only 1-2 px wide)
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    shaded_cand = cv2.morphologyEx(var_mask, cv2.MORPH_OPEN, k_open)

    # Filter out small shaded islands below min_region_px
    if min_region_px > 1 and np.any(shaded_cand):
        num_s, labels_s, stats_s, _ = cv2.connectedComponentsWithStats(shaded_cand)
        areas_s = stats_s[:, cv2.CC_STAT_AREA]
        small_s_ids = np.where((areas_s < min_region_px) & (np.arange(len(areas_s)) > 0))[0]
        if len(small_s_ids) > 0:
            shaded_cand[np.isin(labels_s, small_s_ids)] = 0

    # 2. Line & thin structure detection via Top-Hat / Black-Hat (1-12 px wide)
    k_line = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    th_sq = np.zeros((H, W), dtype=np.float32)
    for ch in [L, a, b]:
        wth = cv2.morphologyEx(ch, cv2.MORPH_TOPHAT, k_line)
        bth = cv2.morphologyEx(ch, cv2.MORPH_BLACKHAT, k_line)
        th_sq += np.maximum(wth, bth)**2
    th = np.sqrt(th_sq)

    # Line mask:
    # - Outside shaded areas: any thin structure with contrast >= 15.0 Delta E
    # - Inside shaded areas: sharp lines/veins with high contrast >= 50.0 and steep edge
    line_mask = ((shaded_cand == 0) & (th >= 15.0)) | ((shaded_cand == 1) & (th >= 50.0) & (mag >= 30.0))

    # 3. Form initial labels: 0 FLAT, 1 LINE, 2 SHADED
    labels = np.zeros((H, W), dtype=np.uint8)
    labels[shaded_cand == 1] = 2
    labels[line_mask] = 1

    # 4. Fill small flat holes enclosed inside shaded regions
    if min_region_px > 1 and np.any(labels == 2):
        inv_shaded = ((labels != 2) & (labels != 1)).astype(np.uint8)
        num_inv, labels_inv, stats_inv, _ = cv2.connectedComponentsWithStats(inv_shaded)
        areas_inv = stats_inv[:, cv2.CC_STAT_AREA]
        # Any flat component enclosed inside shading with area < min_region_px becomes shaded
        small_inv_ids = np.where((areas_inv < min_region_px) & (np.arange(len(areas_inv)) > 0))[0]
        if len(small_inv_ids) > 0:
            labels[np.isin(labels_inv, small_inv_ids)] = 2

    # 5. Compute class fractions
    n_flat = int(np.sum(labels == 0))
    n_line = int(np.sum(labels == 1))
    n_shaded = int(np.sum(labels == 2))

    f_flat = float(n_flat / total_px)
    f_line = float(n_line / total_px)
    f_shaded = float(n_shaded / total_px)

    return {
        "labels": labels,
        "fractions": {
            "flat": f_flat,
            "line": f_line,
            "shaded": f_shaded,
        },
        "has_shading": bool(f_shaded > 0.005),
        "has_lines": bool(f_line > 0.005),
    }


def save_debug_overlay(rgb: np.ndarray, labels: np.ndarray, path: Union[str, Path]) -> None:
    """Save an inspection overlay: FLAT grey, LINE red, SHADED blue, 50% over source.

    Parameters
    ----------
    rgb : np.ndarray
        HxWx3 uint8 source image.
    labels : np.ndarray
        HxW uint8 labels array (0 FLAT, 1 LINE, 2 SHADED).
    path : str or Path
        Target file path (e.g. overlay.png).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 0 = FLAT grey [128, 128, 128]
    # 1 = LINE red   [255, 0, 0]
    # 2 = SHADED blue [0, 0, 255]
    color_map = np.array([
        [128, 128, 128],
        [255, 0, 0],
        [0, 0, 255],
    ], dtype=np.uint8)

    # Map labels to RGB overlay colors
    overlay_rgb = color_map[np.clip(labels, 0, 2)]

    # Blend 50% source, 50% label color
    blended = (rgb.astype(np.float32) * 0.5 + overlay_rgb.astype(np.float32) * 0.5).clip(0, 255).astype(np.uint8)

    Image.fromarray(blended).save(path)


def main(args=None) -> None:
    """CLI entry point for region classification."""
    parser = argparse.ArgumentParser(description="Region classifier for LoomLab auto mode")
    parser.add_argument("img", type=str, help="Path to input image")
    parser.add_argument("--out", type=str, required=True, help="Directory to save output files")
    parser.add_argument("--min-region-px", type=int, default=64, help="Minimum region size in pixels (default: 64)")
    parsed = parser.parse_args(args)

    img_path = Path(parsed.img)
    if not img_path.is_file():
        raise FileNotFoundError(f"Input image not found: {img_path}")

    out_dir = Path(parsed.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rgb = np.array(Image.open(img_path).convert("RGB"))
    res = classify_regions(rgb, min_region_px=parsed.min_region_px)

    # 1. labels.png
    Image.fromarray(res["labels"]).save(out_dir / "labels.png")

    # 2. overlay.png
    save_debug_overlay(rgb, res["labels"], out_dir / "overlay.png")

    # 3. report.json
    report = {
        "fractions": res["fractions"],
        "has_shading": res["has_shading"],
        "has_lines": res["has_lines"],
    }
    with open(out_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Classification completed for {img_path.name}:")
    print(f"  flat:    {res['fractions']['flat'] * 100:.2f}%")
    print(f"  line:    {res['fractions']['line'] * 100:.2f}%")
    print(f"  shaded:  {res['fractions']['shaded'] * 100:.2f}%")
    print(f"  has_shading: {res['has_shading']}")
    print(f"  has_lines:   {res['has_lines']}")
    print(f"Outputs written to: {out_dir}")


if __name__ == "__main__":
    main()
