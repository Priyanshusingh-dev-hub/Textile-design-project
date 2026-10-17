"""Unit tests for textile.region_classify module."""

import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from PIL import Image

from textile.region_classify import classify_regions, main, save_debug_overlay


def test_1_solid_black_is_100_percent_flat():
    """1. A solid black image gives 100% FLAT and has_shading False."""
    img = np.zeros((120, 120, 3), dtype=np.uint8)
    res = classify_regions(img)

    assert res["fractions"]["flat"] == 1.0
    assert res["fractions"]["line"] == 0.0
    assert res["fractions"]["shaded"] == 0.0
    assert res["has_shading"] is False
    assert res["recommended_mode"] == "flat"
    assert np.all(res["labels"] == 0)


def test_2_hard_edge_gives_zero_shaded_beyond_2px():
    """2. Two flat colours split by a hard edge give 0 SHADED pixels beyond 2 px from the edge."""
    H, W = 120, 120
    edge_col = 60
    img = np.zeros((H, W, 3), dtype=np.uint8)
    # Left: Red flat patch, Right: Blue flat patch
    img[:, :edge_col] = [220, 30, 40]
    img[:, edge_col:] = [30, 100, 220]

    res = classify_regions(img)
    labels = res["labels"]

    # Check beyond 2 px from the edge: [0, edge_col - 2) and [edge_col + 2, W)
    beyond_mask = np.ones((H, W), dtype=bool)
    beyond_mask[:, edge_col - 2 : edge_col + 2] = False

    shaded_beyond_2px = int(np.sum(labels[beyond_mask] == 2))
    assert shaded_beyond_2px == 0
    assert res["has_shading"] is False
    assert res["fractions"]["shaded"] == 0.0


def test_3_radial_gradient_disc_is_mostly_shaded_and_ground_flat():
    """3. A smooth radial gradient disc on a flat ground gives the disc mostly SHADED (>80%) and the ground FLAT."""
    H, W = 160, 160
    center_y, center_x = 80, 80
    radius = 50

    img = np.zeros((H, W, 3), dtype=np.uint8)
    # Flat grey background
    img[:, :] = [40, 40, 40]

    y, x = np.ogrid[:H, :W]
    dist = np.sqrt((y - center_y) ** 2 + (x - center_x) ** 2)
    disc_mask = dist <= radius

    # Smooth cosine / quadratic radial falloff inside disc
    falloff = np.clip(1.0 - (dist[disc_mask] / radius) ** 2, 0.0, 1.0)
    img[disc_mask, 0] = np.clip(40 + falloff * 200, 0, 255).astype(np.uint8)
    img[disc_mask, 1] = np.clip(40 + falloff * 140, 0, 255).astype(np.uint8)
    img[disc_mask, 2] = np.clip(40 + falloff * 70, 0, 255).astype(np.uint8)

    res = classify_regions(img)
    labels = res["labels"]

    # Inside the disc: mostly SHADED (>80%)
    disc_inner = dist <= (radius - 4)  # exclude margin transition
    disc_shaded_acc = float(np.mean(labels[disc_inner] == 2))
    assert disc_shaded_acc > 0.80, f"Expected >80% shaded in disc, got {disc_shaded_acc * 100:.1f}%"

    # Outside the disc: ground is FLAT (>95%)
    ground_mask = dist >= (radius + 4)
    ground_flat_acc = float(np.mean(labels[ground_mask] == 0))
    assert ground_flat_acc > 0.95, f"Expected >95% flat in ground, got {ground_flat_acc * 100:.1f}%"

    assert res["has_shading"] is True


def test_4_blotchy_gradient_is_mostly_shaded():
    """4. An irregular blotchy gradient (gaussian-blurred noise) gives mostly SHADED."""
    H, W = 150, 150
    rng = np.random.default_rng(12345)
    noise = rng.uniform(0, 255, (H, W)).astype(np.float32)
    blotchy = cv2.GaussianBlur(noise, (25, 25), 8.0)
    blotchy = ((blotchy - blotchy.min()) / (blotchy.max() - blotchy.min()) * 255.0).astype(np.uint8)
    img = cv2.cvtColor(blotchy, cv2.COLOR_GRAY2RGB)

    res = classify_regions(img)
    assert res["fractions"]["shaded"] > 0.80, f"Expected >80% shaded, got {res['fractions']['shaded'] * 100:.1f}%"
    assert res["has_shading"] is True


def test_5_thin_stripes_and_dots_are_line_with_dots_kept():
    """5. Thin 2 px stripes and 5 px dots on a flat ground give them LINE, with the dots kept."""
    H, W = 140, 140
    # Flat light ground
    img = np.full((H, W, 3), 245, dtype=np.uint8)

    # Thin 2 px black stripes
    img[:, 25:27] = [10, 10, 10]
    img[:, 75:77] = [10, 10, 10]

    # 5 px diameter circular black dots (radius 2-3)
    dot1_center = (45, 50)
    dot2_center = (110, 90)
    cv2.circle(img, dot1_center, 2, (10, 10, 10), -1)
    cv2.circle(img, dot2_center, 3, (10, 10, 10), -1)

    res = classify_regions(img)
    labels = res["labels"]

    # 1. Stripes must be classified as LINE
    stripe1_acc = np.mean(labels[:, 25:27] == 1)
    stripe2_acc = np.mean(labels[:, 75:77] == 1)
    assert stripe1_acc > 0.90, f"Stripe 1 line accuracy: {stripe1_acc * 100:.1f}%"
    assert stripe2_acc > 0.90, f"Stripe 2 line accuracy: {stripe2_acc * 100:.1f}%"

    # 2. Both dots must be kept and classified as LINE
    assert labels[dot1_center[1], dot1_center[0]] == 1, "Dot 1 center was not labeled LINE"
    assert labels[dot2_center[1], dot2_center[0]] == 1, "Dot 2 center was not labeled LINE"

    # 3. Ground remains FLAT
    ground_mask = np.ones((H, W), dtype=bool)
    ground_mask[:, 22:30] = False
    ground_mask[:, 72:80] = False
    cv2.circle(ground_mask, dot1_center, 8, False, -1)
    cv2.circle(ground_mask, dot2_center, 8, False, -1)
    ground_flat_acc = np.mean(labels[ground_mask] == 0)
    assert ground_flat_acc > 0.98, f"Ground flat accuracy: {ground_flat_acc * 100:.1f}%"

    assert res["has_lines"] is True


def test_6_all_three_classes_present_with_high_accuracy():
    """6. An image with all three gives each label in the right area (>75% accuracy per area)."""
    H, W = 120, 300
    img = np.zeros((H, W, 3), dtype=np.uint8)

    # Area 1: Left (cols 0..100) -> FLAT patch with two flat colors
    img[:, :100] = [230, 220, 210]
    img[60:, :100] = [40, 70, 120]

    # Area 2: Middle (cols 100..200) -> LINE patch (stripes & dots on flat ground)
    img[:, 100:200] = [255, 255, 255]
    img[:, 125:128] = [15, 15, 15]
    img[:, 155:157] = [15, 15, 15]
    img[:, 180:182] = [15, 15, 15]
    cv2.circle(img, (140, 40), 3, (15, 15, 15), -1)
    cv2.circle(img, (170, 80), 3, (15, 15, 15), -1)

    # Area 3: Right (cols 200..300) -> SHADED patch (radial gradient)
    img[:, 200:300] = [30, 30, 30]
    y, x = np.ogrid[-60:60, -50:50]
    r = np.sqrt(x**2 + y**2)
    disc_mask = r <= 45
    falloff = np.clip(1.0 - (r[disc_mask] / 45.0) ** 2, 0.0, 1.0)
    img_right = img[:, 200:300]
    img_right[disc_mask, 0] = np.clip(30 + falloff * 220, 0, 255).astype(np.uint8)
    img_right[disc_mask, 1] = np.clip(30 + falloff * 150, 0, 255).astype(np.uint8)
    img_right[disc_mask, 2] = np.clip(30 + falloff * 70, 0, 255).astype(np.uint8)

    res = classify_regions(img)
    labels = res["labels"]

    # Verify Area 1 (FLAT): >75% accuracy
    flat_acc = float(np.mean(labels[:, :100] == 0))
    assert flat_acc > 0.75, f"Flat area accuracy: {flat_acc * 100:.1f}% (expected >75%)"

    # Verify Area 2 foreground lines: >75% accuracy
    line_mask = np.zeros((H, W), dtype=bool)
    line_mask[:, 125:128] = True
    line_mask[:, 155:157] = True
    line_mask[:, 180:182] = True
    cv2.circle(line_mask, (140, 40), 3, True, -1)
    cv2.circle(line_mask, (170, 80), 3, True, -1)
    line_acc = float(np.mean(labels[line_mask] == 1))
    assert line_acc > 0.75, f"Line pixels accuracy: {line_acc * 100:.1f}% (expected >75%)"

    # Verify Area 3 disc (SHADED): >75% accuracy
    shaded_mask = np.zeros((H, W), dtype=bool)
    shaded_mask[:, 200:300] = r <= 40
    shaded_acc = float(np.mean(labels[shaded_mask] == 2))
    assert shaded_acc > 0.75, f"Shaded pixels accuracy: {shaded_acc * 100:.1f}% (expected >75%)"

    assert res["has_shading"] is True
    assert res["has_lines"] is True


def test_save_debug_overlay_with_custom_alpha(tmp_path):
    """Verify save_debug_overlay creates a blended image with custom alpha."""
    rgb = np.full((50, 50, 3), 200, dtype=np.uint8)
    labels = np.zeros((50, 50), dtype=np.uint8)
    labels[10:20, :] = 1  # LINE
    labels[30:40, :] = 2  # SHADED

    out_file = tmp_path / "overlay_alpha.png"
    save_debug_overlay(rgb, labels, out_file, alpha=0.3)

    assert out_file.is_file()
    saved = np.array(Image.open(out_file))
    assert saved.shape == (50, 50, 3)
    # Check 30% blend: 200 * 0.7 + 128 * 0.3 = 140 + 38.4 = 178
    assert np.allclose(saved[0, 0], [178, 178, 178], atol=2)


def test_cli_execution_with_alpha_generates_all_outputs(tmp_path):
    """Verify CLI produces labels.png, overlay.png, and report.json with alpha."""
    img_path = tmp_path / "test_input.png"
    img = np.full((60, 60, 3), 120, dtype=np.uint8)
    img[:, 28:32] = [20, 20, 20]  # stripe
    Image.fromarray(img).save(img_path)

    out_dir = tmp_path / "cli_out"
    main([str(img_path), "--out", str(out_dir), "--alpha", "0.4"])

    assert (out_dir / "labels.png").is_file()
    assert (out_dir / "overlay.png").is_file()
    assert (out_dir / "report.json").is_file()

    with open(out_dir / "report.json", encoding="utf-8") as f:
        rep = json.load(f)
    assert "fractions" in rep
    assert "has_shading" in rep
    assert "has_lines" in rep
    assert "recommended_mode" in rep
    assert abs(sum(rep["fractions"].values()) - 1.0) < 1e-4


def test_input_normalization_handles_rgba_and_grayscale():
    """Verify classifier accepts RGBA and Grayscale inputs without error."""
    # RGBA input
    rgba = np.zeros((60, 60, 4), dtype=np.uint8)
    rgba[:, :, :3] = 128
    rgba[:, :, 3] = 255
    res_rgba = classify_regions(rgba)
    assert res_rgba["labels"].shape == (60, 60)
    assert res_rgba["has_shading"] is False

    # Grayscale 2D input
    gray = np.full((60, 60), 128, dtype=np.uint8)
    res_gray = classify_regions(gray)
    assert res_gray["labels"].shape == (60, 60)
    assert res_gray["has_shading"] is False


def test_real_repo_sample_floral_ref_is_flat():
    """Verify that a real flat screenprint sample (floral_ref.png) has zero shading."""
    sample_path = Path("tests/samples/floral_ref.png")
    if sample_path.is_file():
        img = np.array(Image.open(sample_path).convert("RGB"))
        res = classify_regions(img)
        assert res["has_shading"] is False
        assert res["fractions"]["shaded"] < 0.005
        assert res["recommended_mode"] == "flat"
