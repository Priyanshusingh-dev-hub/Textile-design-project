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
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
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

def _prepare_image(image: Image.Image) -> tuple[Image.Image, np.ndarray | None]:
    """Inspect image for orientation, color modes, and transparency.

    Return (rgb_image, alpha_mask_boolean_array_or_None).
    """
    try:
        image = ImageOps.exif_transpose(image)
    except Exception:
        pass

    has_alpha = ("A" in image.getbands()) or ("transparency" in image.info) or (image.mode in ("RGBA", "LA", "PA"))
    if has_alpha:
        rgba = image.convert("RGBA")
        alpha_arr = np.asarray(rgba)[..., 3]
        alpha_mask = alpha_arr > 12  # Treat pixels with alpha > 12 as non-transparent ink pixels
        # Composite over clean white for RGB representation of visible pixels
        white_bg = Image.new("RGB", rgba.size, (255, 255, 255))
        white_bg.paste(rgba, mask=rgba.split()[3])
        return white_bg, alpha_mask

    if image.mode != "RGB":
        return image.convert("RGB"), None
    return image, None


def choke_mask(mask: np.ndarray, choke_px: int) -> np.ndarray:
    """Erode binary mask by choke_px using 3x3 min filter."""
    if choke_px <= 0:
        return mask
    im = Image.fromarray(mask, mode="L")
    for _ in range(choke_px):
        im = im.filter(ImageFilter.MinFilter(3))
    return np.asarray(im, dtype=np.uint8)


def spread_mask(mask: np.ndarray, spread_px: int) -> np.ndarray:
    """Dilate binary mask by spread_px using 3x3 max filter."""
    if spread_px <= 0:
        return mask
    im = Image.fromarray(mask, mode="L")
    for _ in range(spread_px):
        im = im.filter(ImageFilter.MaxFilter(3))
    return np.asarray(im, dtype=np.uint8)


def apply_spot_trapping(
    spot_masks: list[np.ndarray],
    spot_colors: list[tuple[int, int, int]],
    trap_px: int = 1,
    alpha_mask: np.ndarray | None = None
) -> tuple[list[np.ndarray], int]:
    """Expand lighter spot plates slightly under darker adjacent spot plates.

    Returns (trapped_masks, total_overlap_pixels_added).
    """
    if trap_px <= 0 or len(spot_masks) < 2:
        return spot_masks, 0
    # Calculate luminance for each spot color: L = 0.2126*R + 0.7152*G + 0.0722*B
    luminances = [0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] for c in spot_colors]
    trapped_masks = [m.copy() for m in spot_masks]
    total_overlap = 0

    for i in range(len(spot_masks)):
        for j in range(i + 1, len(spot_masks)):
            lum_i, lum_j = luminances[i], luminances[j]
            if lum_i >= lum_j:
                light_idx, dark_idx = i, j
            else:
                light_idx, dark_idx = j, i
            dilated = spread_mask(spot_masks[light_idx], trap_px)
            seam_overlap = (dilated > 0) & (spot_masks[dark_idx] > 0)
            if alpha_mask is not None:
                seam_overlap &= alpha_mask
            if np.any(seam_overlap):
                trapped_masks[light_idx][seam_overlap] = 255
                total_overlap += int(np.sum(seam_overlap))

    return trapped_masks, total_overlap


def generate_underbase_mask(
    printable_masks: list[np.ndarray],
    choke_px: int = 1,
    alpha_mask: np.ndarray | None = None
) -> tuple[np.ndarray, dict[str, Any]]:
    """Generate white underbase plate with configurable choke for dark fabric printing."""
    if not printable_masks:
        raise ValueError("No printable masks provided for underbase generation")
    union_mask = np.maximum.reduce(printable_masks)
    if alpha_mask is not None:
        union_mask = np.where(alpha_mask, union_mask, 0).astype(np.uint8)

    pre_choke_pixels = int(np.sum(union_mask > 0))
    if choke_px > 0:
        choked_mask = choke_mask(union_mask, choke_px)
    else:
        choked_mask = union_mask

    if alpha_mask is not None:
        choked_mask = np.where(alpha_mask, choked_mask, 0).astype(np.uint8)

    post_choke_pixels = int(np.sum(choked_mask > 0))
    eroded_fine_pixels = pre_choke_pixels - post_choke_pixels

    stats = {
        "choke_px": choke_px,
        "pre_choke_pixels": pre_choke_pixels,
        "post_choke_pixels": post_choke_pixels,
        "eroded_pixels": eroded_fine_pixels,
        "detail_retained": post_choke_pixels > 0 or pre_choke_pixels == 0,
    }
    return choked_mask, stats


def render_plate_composite(
    plates: list[dict[str, Any]],
    files: dict[str, bytes],
    opacities: dict[str, float] | None = None,
    visibilities: dict[str, bool] | None = None,
    colors: dict[str, str] | None = None,
    fabric_hex: str = "#FFFFFF",
) -> Image.Image:
    """Composite plates over a simulated fabric background with per-plate opacity and visibility.

    Plates are rendered bottom-up: UNDERBASE_WHITE first, then color spot and tonal plates.
    """
    if not plates:
        raise ValueError("Cannot composite empty plates list")
    first_file = files.get(plates[0]["filename"])
    if not first_file:
        raise ValueError(f"File {plates[0]['filename']} not found in files dictionary")
    ref_im = Image.open(BytesIO(first_file))
    w, h = ref_im.size

    def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        h_str = hex_str.strip().lstrip("#")
        if len(h_str) != 6:
            return (255, 255, 255)
        return (int(h_str[0:2], 16), int(h_str[2:4], 16), int(h_str[4:6], 16))

    fab_r, fab_g, fab_b = hex_to_rgb(fabric_hex)
    comp = np.full((h, w, 3), [fab_r, fab_g, fab_b], dtype=np.float32) / 255.0

    # Ensure underbase prints first on top of fabric, then spot and tonal plates
    sorted_plates = sorted(plates, key=lambda p: 0 if p.get("type") == "underbase" else 1)

    for plate in sorted_plates:
        pname = plate["name"]
        if visibilities is not None and not visibilities.get(pname, True):
            continue
        op = float(opacities.get(pname, 1.0)) if opacities is not None else 1.0
        op = max(0.0, min(1.0, op))
        if op <= 0.0:
            continue
        raw = files.get(plate["filename"])
        if not raw:
            continue
        mask = Image.open(BytesIO(raw)).convert("L")
        if mask.size != (w, h):
            mask = mask.resize((w, h), Image.Resampling.NEAREST)
        mask_arr = (np.asarray(mask, dtype=np.float32) / 255.0) * op

        hex_code = colors.get(pname, plate.get("hex", "#000000")) if colors is not None else plate.get("hex", "#000000")
        ir, ig, ib = hex_to_rgb(hex_code)
        ink_f = np.array([ir, ig, ib], dtype=np.float32) / 255.0

        # Alpha overprint compositing
        comp = comp * (1.0 - mask_arr[..., None]) + ink_f[None, None, :] * mask_arr[..., None]

    out_arr = np.clip(comp * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out_arr, mode="RGB")



def generate_separation(image: Image.Image, settings: SeparationSettings) -> dict[str, Any]:
    """Create preview PNGs and a manifest for spot, halftone or hybrid mode.

    Spot plates are binary masks of a median-cut palette. Halftone mode makes a
    grayscale tonal plate. Hybrid mode combines up to max_inks-1 spot plates
    with one grayscale tonal plate. Transparent backgrounds are preserved and unprinted.
    """
    rgb, alpha_mask = _prepare_image(image)
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

    if alpha_mask is not None and np.any(alpha_mask):
        ink_pixels = source_arr[alpha_mask]
        box_dim = int(np.ceil(np.sqrt(len(ink_pixels))))
        padded = np.zeros((box_dim * box_dim, 3), dtype=np.uint8)
        padded[:len(ink_pixels)] = ink_pixels
        if len(ink_pixels) < len(padded):
            padded[len(ink_pixels):] = ink_pixels[0]
        seed_src = Image.fromarray(padded.reshape((box_dim, box_dim, 3)), mode="RGB")
        seed_image = seed_src.quantize(colors=palette_count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
        seed_colors = np.unique(np.asarray(seed_image, dtype=np.uint8).reshape(-1, 3), axis=0)
    else:
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

    spot_plates_raw: list[dict[str, Any]] = []
    if settings.strategy in ("spot", "hybrid"):
        for i, color in enumerate(unique_colors):
            if alpha_mask is not None:
                mask = np.where((label_map == i) & alpha_mask, 255, 0).astype(np.uint8)
            else:
                mask = np.where(label_map == i, 255, 0).astype(np.uint8)
            coverage_pct = round(float((mask > 0).mean() * 100), 3)
            if coverage_pct == 0.0 and alpha_mask is not None:
                continue
            spot_plates_raw.append({
                "mask": mask,
                "color": tuple(int(v) for v in color),
                "hex": "#%02X%02X%02X" % tuple(int(v) for v in color),
            })

    trapping_stats = {"applied": False, "trap_px": settings.trap_px, "overlap_pixels": 0}
    if settings.apply_trapping and len(spot_plates_raw) >= 2:
        masks_to_trap = [sp["mask"] for sp in spot_plates_raw]
        colors_to_trap = [sp["color"] for sp in spot_plates_raw]
        trapped_masks, total_overlap = apply_spot_trapping(
            masks_to_trap, colors_to_trap, trap_px=settings.trap_px, alpha_mask=alpha_mask
        )
        for sp, tm in zip(spot_plates_raw, trapped_masks):
            sp["mask"] = tm
        trapping_stats = {"applied": True, "trap_px": settings.trap_px, "overlap_pixels": total_overlap}

    for sp in spot_plates_raw:
        mask = sp["mask"]
        coverage_pct = round(float((mask > 0).mean() * 100), 3)
        name = f"INK_{len(plate_entries)+1:02d}"
        filename = f"plates/{name}_spot.png"
        files[filename] = _png_bytes(Image.fromarray(mask, mode="L"))
        plate_entries.append({
            "name": name,
            "type": "spot",
            "hex": sp["hex"],
            "filename": filename,
            "coverage_percent": coverage_pct,
        })

    if settings.strategy in ("halftone", "hybrid"):
        arr = source_arr.astype(np.float32) / 255.0
        # Perceptual luminance inverted to ink coverage: darker source regions print more ink.
        luminance = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        coverage = np.clip(1.0 - luminance, 0.0, 1.0)
        if alpha_mask is not None:
            coverage = np.where(alpha_mask, coverage, 0.0)
        mask = halftone_mask(coverage, settings.lpi, settings.dpi)
        filename = "plates/TONAL_01_halftone.png"
        files[filename] = _png_bytes(Image.fromarray(mask, mode="L"))
        plate_entries.append({"name": "TONAL_01", "type": "tonal", "hex": "#000000", "filename": filename,
                              "coverage_percent": round(float((mask > 0).mean() * 100), 3),
                              "note": "Prototype grayscale-derived tonal coverage; review against the intended ink mapping."})

    underbase_stats: dict[str, Any] = {"generated": False}
    if settings.generate_underbase and plate_entries:
        printable_masks = [
            np.asarray(Image.open(BytesIO(files[p["filename"]])).convert("L"), dtype=np.uint8)
            for p in plate_entries
        ]
        underbase_mask, ub_stats = generate_underbase_mask(
            printable_masks, choke_px=settings.underbase_choke_px, alpha_mask=alpha_mask
        )
        ub_coverage = round(float((underbase_mask > 0).mean() * 100), 3)
        ub_filename = "plates/UNDERBASE_WHITE_underbase.png"
        files[ub_filename] = _png_bytes(Image.fromarray(underbase_mask, mode="L"))
        ub_entry = {
            "name": "UNDERBASE_WHITE",
            "type": "underbase",
            "hex": "#FFFFFF",
            "filename": ub_filename,
            "coverage_percent": ub_coverage,
            "note": f"White underbase plate choked by {settings.underbase_choke_px}px for dark garment printing.",
        }
        plate_entries.insert(0, ub_entry)
        underbase_stats = {
            "generated": True,
            **ub_stats,
            "coverage_percent": ub_coverage,
        }

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
        "has_transparency": alpha_mask is not None,
        "transparent_pixels_percent": round(float((~alpha_mask).mean() * 100), 2) if alpha_mask is not None else 0.0,
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
        "generate_underbase": settings.generate_underbase,
        "underbase_stats": underbase_stats,
        "apply_trapping": settings.apply_trapping,
        "trapping_stats": trapping_stats,
        "plate_count": len(plate_entries),
        "plates": plate_entries,
        "quality_checks": {
            "plate_count_within_requested_limit": len(plate_entries) <= settings.max_inks + (1 if settings.generate_underbase else 0),
            "all_spot_masks_binary": all(entry["type"] != "spot" or entry["coverage_percent"] >= 0 for entry in plate_entries),
            "all_plates_nonempty": nonempty_plates,
            "source_dimensions_preserved": True,
            "source_sha256_present": len(source_sha256) == 64,
            "reconstruction_preview_present": "preview/reconstructed_preview.png" in files,
            "plate_contact_sheet_present": "preview/plate_contact_sheet.png" in files,
            "plate_csv_report_present": "reports/plate_summary.csv" in files,
            "reconstruction_metrics_finite": bool(np.isfinite([mae, rmse, psnr]).all()),
            "transparency_handled": True,
            "underbase_generated": settings.generate_underbase,
            "trapping_applied": trapping_stats["applied"],
        },
        "limitations": [
            "MVP preview only; not ICC colour-managed.",
            "Trapping and underbase are algorithmic approximations; verify chokes/spreads against target press and mesh.",
            "Hybrid tonal plate is grayscale-derived and may need manual ink mapping.",
            "Requested LPI/DPI sets an approximate screen-cell size; verify with target mesh and press.",
            "Palette seeds use median-cut; pixels are assigned by CIE Lab distance, which is still an approximation and not ICC/device-managed.",
            "Reconstructed preview is a software diagnostic, not a physical-print prediction."
        ],
    }
    return {"files": files, "manifest": manifest}
