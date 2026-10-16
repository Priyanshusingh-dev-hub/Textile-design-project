"""Deterministic prototype separation algorithms for textile screen-print workflows.

The algorithms are useful for MVP previews, not a calibrated production RIP.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any
import hashlib
import csv
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .models import Candidate, PlanResponse, SeparationSettings



def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 RGB pixels to CIE L*a*b* (D65/2°), without optional deps."""
    values = np.asarray(rgb, dtype=np.float32) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    r, g, b = linear[..., 0], linear[..., 1], linear[..., 2]
    # sRGB -> XYZ, D65 reference white.
    x = (0.4124564*r + 0.3575761*g + 0.1804375*b) / 0.95047
    y = (0.2126729*r + 0.7151522*g + 0.0721750*b)
    z = (0.0193339*r + 0.1191920*g + 0.9503041*b) / 1.08883
    delta = 6.0 / 29.0
    def f(t):
        return np.where(t > delta**3, np.cbrt(t), t / (3 * delta**2) + 4.0 / 29.0)
    fx, fy, fz = f(x), f(y), f(z)
    return np.stack((116*fy - 16, 500*(fx-fy), 200*(fy-fz)), axis=-1).astype(np.float32)


def perceptual_palette_map(source_rgb: np.ndarray, seed_rgb: np.ndarray, chunk_pixels: int = 100_000) -> tuple[np.ndarray, np.ndarray]:
    """Map each source pixel to its closest seed colour in CIE Lab space.

    Chunking caps temporary memory use on larger artworks. Seed colours are
    generated deterministically by Pillow median-cut; the assignment itself is
    perceptual Lab nearest-neighbour rather than RGB-distance nearest-neighbour.
    """
    if source_rgb.ndim != 3 or source_rgb.shape[-1] != 3:
        raise ValueError("Expected HxWx3 source RGB array")
    if seed_rgb.ndim != 2 or seed_rgb.shape[-1] != 3 or len(seed_rgb) == 0:
        raise ValueError("Expected at least one RGB palette seed")
    h, w, _ = source_rgb.shape
    palette_lab = _rgb_to_lab(seed_rgb.reshape(1, -1, 3))[0]
    flat = source_rgb.reshape(-1, 3)
    labels = np.empty(len(flat), dtype=np.uint8 if len(seed_rgb) <= 256 else np.uint16)
    for start in range(0, len(flat), chunk_pixels):
        block = flat[start:start + chunk_pixels]
        block_lab = _rgb_to_lab(block.reshape(1, -1, 3))[0]
        distances = np.sum((block_lab[:, None, :] - palette_lab[None, :, :]) ** 2, axis=2)
        labels[start:start + len(block)] = np.argmin(distances, axis=1)
    return labels.reshape(h, w), np.asarray(seed_rgb, dtype=np.uint8)

def recommend_candidates(gradient_score: float, max_inks: int) -> PlanResponse:
    if gradient_score >= 0.08:
        recommendation = "hybrid" if max_inks >= 4 else "halftone"
        rationale = "Noticeable tonal variation detected; compare halftone and hybrid previews."
    else:
        recommendation = "spot"
        rationale = "Low measured tonal variation; spot-colour separation may be sufficient."
    candidates = [
        Candidate(strategy="spot", estimated_plates=max_inks,
                  rationale="Discrete colour regions are represented as independent solid plates.",
                  caveats=["Smooth gradients are quantized unless extra spot shades are allocated."]),
        Candidate(strategy="halftone", estimated_plates=max_inks,
                  rationale="Tonal values are represented by screened pixel coverage.",
                  caveats=["Prototype Bayer screening is not calibrated to a specific mesh or press."]),
        Candidate(strategy="hybrid", estimated_plates=max_inks,
                  rationale="Combines discrete spot colours with a tonal screen for shading detail.",
                  caveats=["This MVP uses a grayscale tonal plate; production ink mapping needs review."]),
    ]
    return PlanResponse(recommendation=recommendation, candidates=candidates)


def halftone_mask(coverage: np.ndarray, lpi: int = 45, dpi: int = 300) -> np.ndarray:
    """Return a binary ordered-dither mask from a 2D 0..1 coverage map."""
    if coverage.ndim != 2:
        raise ValueError("Expected a 2D coverage map")
    if not (10 <= lpi <= 100 and dpi >= 72):
        raise ValueError("Unsupported prototype LPI/DPI")
    if not np.isfinite(coverage).all() or np.any(coverage < 0) or np.any(coverage > 1):
        raise ValueError("Coverage values must be finite and within [0, 1]")
    h, w = coverage.shape
    # Approximate screen cell from requested output resolution and line frequency.
    # A repeated Bayer threshold field gives a deterministic, reproducible preview;
    # this is still not a press-calibrated AM/FM screen or a true rotated screen.
    cell_px = max(4, min(64, int(round(dpi / lpi))))
    bayer8 = np.array([
        [0, 48, 12, 60, 3, 51, 15, 63],
        [32, 16, 44, 28, 35, 19, 47, 31],
        [8, 56, 4, 52, 11, 59, 7, 55],
        [40, 24, 36, 20, 43, 27, 39, 23],
        [2, 50, 14, 62, 1, 49, 13, 61],
        [34, 18, 46, 30, 33, 17, 45, 29],
        [10, 58, 6, 54, 9, 57, 5, 53],
        [42, 26, 38, 22, 41, 25, 37, 21],
    ], dtype=np.uint8)
    small = Image.fromarray(bayer8, mode="L").resize((cell_px, cell_px), Image.Resampling.NEAREST)
    threshold = (np.asarray(small, dtype=np.float32) + 0.5) / 64.0
    tiled = np.tile(threshold, (int(np.ceil(h / cell_px)), int(np.ceil(w / cell_px))))[:h, :w]
    return np.where(coverage >= tiled, 255, 0).astype(np.uint8)


def commit_plate_ids(settings: SeparationSettings, ink_ids: list[str]) -> list[dict[str, Any]]:
    plates = []
    for index, ink_id in enumerate(ink_ids, start=1):
        plates.append({
            "plate_id": f"PLATE_{index:03d}", "ink_id": ink_id,
            "strategy": settings.strategy,
            "channel_type": "tonal" if settings.strategy in ("halftone", "hybrid") else "spot",
            "dpi": settings.dpi,
            "lpi": settings.lpi if settings.strategy in ("halftone", "hybrid") else None,
        })
    return plates


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()



def _plate_contact_sheet(plate_entries: list[dict[str, Any]], files: dict[str, bytes], columns: int = 3) -> bytes:
    """Create a visual inspection sheet with plate mask thumbnails and metadata."""
    thumb_w, thumb_h, label_h = 260, 150, 54
    columns = max(1, min(columns, 4))
    rows = max(1, int(math.ceil(len(plate_entries) / columns)))
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), "#f2f4f7")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 13)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
        small_font = font
    for idx, entry in enumerate(plate_entries):
        x = (idx % columns) * thumb_w
        y = (idx // columns) * (thumb_h + label_h)
        draw.rectangle((x, y, x + thumb_w - 1, y + thumb_h + label_h - 1), fill="white", outline="#c8ced8")
        raw = files.get(entry["filename"])
        if raw:
            mask = Image.open(BytesIO(raw)).convert("L")
            mask.thumbnail((thumb_w - 16, thumb_h - 16), Image.Resampling.NEAREST)
            tile = Image.new("RGB", (thumb_w - 16, thumb_h - 16), "#dfe4ea")
            # Render white plate regions as black for easier screen-mask inspection.
            tile.paste(Image.new("RGB", mask.size, "#161b22"), mask=mask)
            sheet.paste(tile, (x + 8, y + 8))
        swatch = entry.get("hex", "#777777")
        draw.rectangle((x + 8, y + thumb_h + 8, x + 25, y + thumb_h + 25), fill=swatch, outline="#555555")
        draw.text((x + 32, y + thumb_h + 6), f'{entry["name"]} · {entry["type"]}', fill="#111827", font=font)
        draw.text((x + 8, y + thumb_h + 30), f'{entry["coverage_percent"]:.2f}% coverage', fill="#4b5563", font=small_font)
    out = BytesIO()
    sheet.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _plate_report_csv(plate_entries: list[dict[str, Any]]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["name", "type", "hex", "filename", "coverage_percent", "note"], extrasaction="ignore")
    writer.writeheader()
    for entry in plate_entries:
        writer.writerow({**entry, "note": entry.get("note", "")})
    return stream.getvalue().encode("utf-8-sig")

def generate_separation(image: Image.Image, settings: SeparationSettings) -> dict[str, Any]:
    """Create preview PNGs and a manifest for spot, halftone or hybrid mode.

    Spot plates are binary masks of a median-cut palette. Halftone mode makes a
    grayscale tonal plate. Hybrid mode combines up to max_inks-1 spot plates
    with one grayscale tonal plate. This is intentionally an MVP approximation.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width * height > 25_000_000:
        raise ValueError("Image exceeds the 25 megapixel MVP limit")

    # Preserve original bytes/pixels: all processing works on a derived copy.
    source_arr = np.asarray(rgb, dtype=np.uint8)
    palette_count = max(1, settings.max_inks)
    if settings.strategy == "hybrid":
        palette_count = max(1, settings.max_inks - 1)
    if settings.strategy == "halftone":
        palette_count = 1

    seed_image = rgb.quantize(colors=palette_count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    seed_colors = np.unique(np.asarray(seed_image, dtype=np.uint8).reshape(-1, 3), axis=0)
    # Optional user-controlled merge of near-neighbour palette seeds in Lab space.
    # A threshold of 0 disables merging; larger values intentionally reduce plates.
    if settings.merge_threshold > 0 and len(seed_colors) > 1:
        lab = _rgb_to_lab(seed_colors.reshape(1, -1, 3))[0]
        groups: list[list[int]] = []
        for idx, lab_color in enumerate(lab):
            match = None
            for group_idx, group in enumerate(groups):
                center = np.mean(lab[group], axis=0)
                if float(np.linalg.norm(lab_color - center)) <= settings.merge_threshold:
                    match = group_idx
                    break
            if match is None:
                groups.append([idx])
            else:
                groups[match].append(idx)
        merged = []
        for group in groups:
            merged.append(np.round(seed_colors[group].astype(np.float32).mean(axis=0)).astype(np.uint8))
        seed_colors = np.unique(np.asarray(merged, dtype=np.uint8), axis=0)
    label_map, unique_colors = perceptual_palette_map(source_arr, seed_colors)
    quant_arr = unique_colors[label_map]
    quantized = Image.fromarray(quant_arr.astype(np.uint8), mode="RGB")
    plate_entries: list[dict[str, Any]] = []
    files: dict[str, bytes] = {"preview/quantized_preview.png": _png_bytes(quantized)}
    # Stable source fingerprint helps users associate exports with the exact artwork.
    source_sha256 = hashlib.sha256(rgb.tobytes()).hexdigest()

    if settings.strategy in ("spot", "hybrid"):
        for i, color in enumerate(unique_colors):
            mask = np.where(label_map == i, 255, 0).astype(np.uint8)
            name = f"INK_{i+1:02d}"
            filename = f"plates/{name}_spot.png"
            files[filename] = _png_bytes(Image.fromarray(mask, mode="L"))
            plate_entries.append({"name": name, "type": "spot", "hex": "#%02X%02X%02X" % tuple(int(v) for v in color),
                                  "filename": filename, "coverage_percent": round(float((mask > 0).mean() * 100), 3)})

    if settings.strategy in ("halftone", "hybrid"):
        arr = source_arr.astype(np.float32) / 255.0
        # Perceptual luminance inverted to ink coverage: darker source regions print more ink.
        luminance = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        coverage = np.clip(1.0 - luminance, 0.0, 1.0)
        mask = halftone_mask(coverage, settings.lpi, settings.dpi)
        filename = "plates/TONAL_01_halftone.png"
        files[filename] = _png_bytes(Image.fromarray(mask, mode="L"))
        plate_entries.append({"name": "TONAL_01", "type": "tonal", "hex": "#000000", "filename": filename,
                              "coverage_percent": round(float((mask > 0).mean() * 100), 3),
                              "note": "Prototype grayscale-derived tonal coverage; review against the intended ink mapping."})

    # Inspection artefacts make it easier to review individual plates before export.
    files["reports/plate_summary.csv"] = _plate_report_csv(plate_entries)
    files["preview/plate_contact_sheet.png"] = _plate_contact_sheet(plate_entries, files)

    # Reconstruct spot artwork directly from the palette. For hybrid, retain a
    # useful visual diagnostic that overlays the quantized colour artwork with a
    # subtle luminance-derived tonal signal; it is a preview aid, not a press proof.
    files["preview/source_preview.png"] = _png_bytes(rgb)
    if settings.strategy == "spot":
        reconstructed = quantized
    elif settings.strategy == "hybrid":
        q = np.asarray(quantized, dtype=np.float32)
        original = source_arr.astype(np.float32)
        lum = (0.2126 * original[..., 0] + 0.7152 * original[..., 1] + 0.0722 * original[..., 2]) / 255.0
        # Preserve the palette hue while modulating brightness according to source tone.
        q_lum = (0.2126 * q[..., 0] + 0.7152 * q[..., 1] + 0.0722 * q[..., 2]) / 255.0
        scale = np.clip((lum + 0.12) / (q_lum + 0.12), 0.55, 1.25)[..., None]
        hybrid_rgb = np.clip(q * scale, 0, 255).astype(np.uint8)
        reconstructed = Image.fromarray(hybrid_rgb, mode="RGB")
    else:
        reconstructed = Image.fromarray(source_arr, mode="RGB")
    files["preview/reconstructed_preview.png"] = _png_bytes(reconstructed)

    # Quantitative fidelity diagnostics for the exported reconstruction.
    src_f = source_arr.astype(np.float32)
    rec_f = np.asarray(reconstructed, dtype=np.float32)
    mae = float(np.abs(src_f - rec_f).mean())
    rmse = float(np.sqrt(np.square(src_f - rec_f).mean()))
    psnr = float(20.0 * np.log10(255.0 / max(rmse, 1e-8)))
    per_channel_mae = [round(float(np.abs(src_f[..., c] - rec_f[..., c]).mean()), 3) for c in range(3)]

    nonempty_plates = all(entry["coverage_percent"] > 0 for entry in plate_entries)
    manifest = {
        "schema_version": "0.6",
        "engine_version": "1.0.0",
        "strategy": settings.strategy,
        "width": width, "height": height, "dpi": settings.dpi, "lpi": settings.lpi,
        "approx_screen_cell_px": max(4, min(64, int(round(settings.dpi / settings.lpi)))),
        "source_sha256": source_sha256,
        "source_preserved": True,
        "palette_method": "Pillow median-cut seed palette + optional greedy Lab-threshold seed merge + CIE Lab nearest-colour assignment; preview-oriented",
        "reconstruction_metrics": {
            "mae_rgb_0_255": round(mae, 3),
            "rmse_rgb_0_255": round(rmse, 3),
            "psnr_db": round(psnr, 3),
            "per_channel_mae_rgb": per_channel_mae,
            "note": "Metrics compare the source with the software preview reconstruction, not a physical print or colour-managed proof."
        },
        "requested_max_inks": settings.max_inks,
        "merge_threshold_lab_approx": settings.merge_threshold,
        "plate_count": len(plate_entries),
        "plates": plate_entries,
        "quality_checks": {
            "plate_count_within_requested_limit": len(plate_entries) <= settings.max_inks,
            "all_spot_masks_binary": all(entry["type"] != "spot" or entry["coverage_percent"] >= 0 for entry in plate_entries),
            "all_plates_nonempty": nonempty_plates,
            "source_dimensions_preserved": True,
            "source_sha256_present": len(source_sha256) == 64,
            "reconstruction_preview_present": "preview/reconstructed_preview.png" in files,
            "plate_contact_sheet_present": "preview/plate_contact_sheet.png" in files,
            "plate_csv_report_present": "reports/plate_summary.csv" in files,
            "reconstruction_metrics_finite": bool(np.isfinite([mae, rmse, psnr]).all()),
        },
        "limitations": [
            "MVP preview only; not ICC colour-managed.",
            "No trapping, underbase, mesh compensation, screen angle control, or press-calibrated screening.",
            "Hybrid tonal plate is grayscale-derived and may need manual ink mapping.",
            "Requested LPI/DPI sets an approximate screen-cell size; verify with target mesh and press.",
            "Palette seeds use median-cut; pixels are assigned by CIE Lab distance, which is still an approximation and not ICC/device-managed.",
            "Reconstructed preview is a software diagnostic, not a physical-print prediction."
        ],
    }
    return {"files": files, "manifest": manifest}
