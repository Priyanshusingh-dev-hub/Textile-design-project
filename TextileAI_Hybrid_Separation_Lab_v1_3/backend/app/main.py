from __future__ import annotations
import json
import base64
import zipfile
import re
import os
import csv
from io import BytesIO, StringIO
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse, FileResponse
from PIL import Image, UnidentifiedImageError
from .models import AnalysisReport, SeparationSettings, PlanResponse
from .analysis import analyze_rgb
from .separation import (
    recommend_candidates, commit_plate_ids, generate_separation,
    render_plate_composite, recommend_mesh_count,
    calculate_theoretical_ink_estimate, DEPOSIT_RATES_G_PER_SQM,
    _png_bytes, _plate_contact_sheet, _plate_report_csv
)

app = FastAPI(title="TextileAI Hybrid Separation API", version="1.6.0")
FRONTEND_FILE = __import__("pathlib").Path(__file__).resolve().parents[2] / "frontend" / "index.html"

@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_FILE)
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

@app.get("/health")
def health():
    return {"status": "ok", "service": "textileai-separation", "version": "1.6.0"}

@app.post("/api/analysis/demo", response_model=AnalysisReport)
def demo_analysis():
    import numpy as np
    sample = np.zeros((64, 64, 3), dtype=np.uint8)
    sample[:, :, 0] = np.tile(np.arange(64, dtype=np.uint8) * 4, (64, 1))
    return analyze_rgb(sample)

@app.post("/api/analysis", response_model=AnalysisReport)
async def analyze_upload(file: UploadFile = File(...)):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image. Upload PNG, JPEG or WebP.")
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    import numpy as np
    # Convert over white for luminance analysis if alpha is present
    if ("A" in image.getbands()) or ("transparency" in image.info) or (image.mode in ("RGBA", "LA", "PA")):
        rgba = image.convert("RGBA")
        white_bg = Image.new("RGB", rgba.size, (255, 255, 255))
        white_bg.paste(rgba, mask=rgba.split()[3])
        rgb = white_bg
    else:
        rgb = image.convert("RGB")
    return analyze_rgb(np.asarray(rgb, dtype=np.uint8))

@app.post("/api/separation/candidates", response_model=PlanResponse)
def candidates(gradient_score: float = Query(0.0, ge=0, le=1), max_inks: int = Query(8, ge=1, le=32)):
    return recommend_candidates(gradient_score, max_inks)

@app.post("/api/separation/inspect")
async def separation_inspect(
    file: UploadFile = File(...),
    strategy: str = Query("hybrid", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    generate_underbase: bool = Query(False),
    underbase_choke_px: int = Query(1, ge=0, le=10),
    apply_trapping: bool = Query(False),
    trap_px: int = Query(1, ge=1, le=5),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    """Return lightweight plate thumbnails and metadata for the interactive browser inspector."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image. Upload PNG, JPEG or WebP.")
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    settings = SeparationSettings(
        strategy=strategy,
        max_inks=max_inks,
        lpi=lpi,
        dpi=dpi,
        merge_threshold=merge_threshold,
        generate_underbase=generate_underbase,
        underbase_choke_px=underbase_choke_px,
        apply_trapping=apply_trapping,
        trap_px=trap_px,
        min_feature_px=min_feature_px,
    )
    try:
        result = generate_separation(image, settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    plate_cards = []
    for entry in result["manifest"]["plates"]:
        mask = Image.open(BytesIO(result["files"][entry["filename"]])).convert("L")
        mask.thumbnail((720, 520), Image.Resampling.NEAREST)
        buffer = BytesIO()
        mask.save(buffer, format="PNG", optimize=True)
        plate_cards.append({**entry, "preview_data": base64.b64encode(buffer.getvalue()).decode("ascii")})
    preview = Image.open(BytesIO(result["files"]["preview/reconstructed_preview.png"])).convert("RGB")
    preview.thumbnail((1000, 700), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    preview.save(buffer, format="JPEG", quality=82, optimize=True)
    return {
        "strategy": strategy,
        "width": image.width,
        "height": image.height,
        "plates": plate_cards,
        "reconstructed_preview_data": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "metrics": result["manifest"]["reconstruction_metrics"],
        "quality_checks": result["manifest"]["quality_checks"],
    }


@app.post("/api/separation/composite")
async def separation_composite(
    file: UploadFile = File(...),
    strategy: str = Query("hybrid", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    fabric_color: str = Query("#FFFFFF"),
    generate_underbase: bool = Query(False),
    underbase_choke_px: int = Query(1, ge=0, le=10),
    apply_trapping: bool = Query(False),
    trap_px: int = Query(1, ge=1, le=5),
    min_feature_px: int = Query(0, ge=0, le=20),
    plate_settings: str = Form("{}"),
):
    """Render composite artwork preview reflecting per-plate visibility, opacity, and fabric color."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw))
        config = json.loads(plate_settings)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image.")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "plate_settings must be valid JSON.") from exc
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    settings = SeparationSettings(
        strategy=strategy,
        max_inks=max_inks,
        lpi=lpi,
        dpi=dpi,
        merge_threshold=merge_threshold,
        generate_underbase=generate_underbase,
        underbase_choke_px=underbase_choke_px,
        apply_trapping=apply_trapping,
        trap_px=trap_px,
        min_feature_px=min_feature_px,
    )
    result = generate_separation(image, settings)
    opacities = config.get("opacities", {})
    visibilities = config.get("visibilities", {})
    colors = config.get("colors", {})
    composite_im = render_plate_composite(
        result["manifest"]["plates"],
        result["files"],
        opacities=opacities,
        visibilities=visibilities,
        colors=colors,
        fabric_hex=fabric_color,
    )
    buf = BytesIO()
    composite_im.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")



@app.post("/api/separation/edit")
async def edit_separation(
    file: UploadFile = File(...),
    merge_groups: str = Form("[]"),
    strategy: str = Query("hybrid", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    """Merge explicitly selected spot plates by unioning masks and rebuilding export reports."""
    import numpy as np
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw)).convert("RGB")
        groups = json.loads(merge_groups)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image.")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "merge_groups must be valid JSON.") from exc
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    if not isinstance(groups, list) or any(not isinstance(g, list) or len(g) < 2 or any(not isinstance(n, str) for n in g) for g in groups):
        raise HTTPException(400, "Each merge group must be a list of at least two plate names.")
    settings = SeparationSettings(strategy=strategy, max_inks=max_inks, lpi=lpi, dpi=dpi, merge_threshold=merge_threshold, min_feature_px=min_feature_px)
    result = generate_separation(image, settings)
    files = dict(result["files"])
    manifest = dict(result["manifest"])
    plates = [dict(p) for p in manifest["plates"]]
    spot_names = {p["name"] for p in plates if p["type"] == "spot"}
    used = set()
    for group in groups:
        if len(set(group)) != len(group) or any(name not in spot_names for name in group):
            raise HTTPException(400, "Merge groups must contain distinct existing spot plate names only.")
        if used.intersection(group):
            raise HTTPException(400, "A plate cannot appear in multiple merge groups.")
        used.update(group)
    for group in groups:
        selected = [p for p in plates if p["name"] in group and p["type"] == "spot"]
        masks = [np.asarray(Image.open(BytesIO(files[p["filename"]])).convert("L"), dtype=np.uint8) for p in selected]
        union = np.maximum.reduce(masks)
        colors = [tuple(int(p["hex"][i:i+2], 16) for i in (1,3,5)) for p in selected]
        color = tuple(int(round(sum(c[i] for c in colors)/len(colors))) for i in range(3))
        first = selected[0]
        merged_name = "+".join(group)
        merged_file = f"plates/{merged_name.replace('+','_')}_merged.png"
        files[merged_file] = _png_bytes(Image.fromarray(union, mode="L"))
        original_first_file = first["filename"]
        cov_frac = float((union > 0).mean())
        ptype = first.get("type", "spot")
        grams_per_100 = calculate_theoretical_ink_estimate(
            image.width, image.height, dpi, cov_frac, ptype
        )
        first_update = {
            "name": merged_name,
            "hex": "#%02X%02X%02X" % color,
            "filename": merged_file,
            "coverage_percent": round(cov_frac * 100, 3),
            "mesh_recommendation": recommend_mesh_count(ptype, lpi),
            "merged_from": group,
            "type": ptype,
        }
        if grams_per_100 is not None:
            first_update["estimated_grams_per_100_prints"] = grams_per_100
        else:
            first_update["estimated_grams_per_100_prints"] = None
            first_update["estimated_grams_per_100_prints_status"] = "unavailable"
        first.update(first_update)
        files.pop(original_first_file, None)
        for p in selected[1:]:
            files.pop(p["filename"], None)
            plates.remove(p)
        for p in selected:
            if p is not first:
                files.pop(p["filename"], None)
    # Rebuild the diagnostic quantized preview using the merged representative ink colour.
    quantized = Image.open(BytesIO(files["preview/quantized_preview.png"])).convert("RGB")
    qarr = np.asarray(quantized).copy()
    for group in groups:
        selected_colors = [tuple(int(p["hex"][i:i+2],16) for i in (1,3,5))
                           for p in result["manifest"]["plates"] if p["name"] in group]
        target = tuple(int(round(sum(c[i] for c in selected_colors)/len(selected_colors))) for i in range(3))
        for c in selected_colors:
            qarr[np.all(qarr == c, axis=2)] = target
    files["preview/quantized_preview.png"] = _png_bytes(Image.fromarray(qarr, mode="RGB"))
    manifest["plates"] = plates
    manifest["plate_count"] = len(plates)
    manifest["manual_merge_groups"] = groups
    manifest["quality_checks"] = dict(manifest.get("quality_checks", {}))
    manifest["quality_checks"]["plate_count_within_requested_limit"] = len(plates) <= max_inks
    manifest["quality_checks"]["all_plates_nonempty"] = all(p["coverage_percent"] > 0 for p in plates)
    files["reports/plate_summary.csv"] = _plate_report_csv(plates)
    files["preview/plate_contact_sheet.png"] = _plate_contact_sheet(plates, files)
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, payload in files.items():
            zf.writestr(name, payload)
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="textileai-manual-merge.zip"'
    })

@app.post("/api/separation/preview")
async def separation_preview(
    file: UploadFile = File(...),
    strategy: str = Query("hybrid", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    generate_underbase: bool = Query(False),
    underbase_choke_px: int = Query(1, ge=0, le=10),
    apply_trapping: bool = Query(False),
    trap_px: int = Query(1, ge=1, le=5),
    include_registration_marks: bool = Query(False),
    film_margin_px: int = Query(40, ge=20, le=120),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image. Upload PNG, JPEG or WebP.")
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    settings = SeparationSettings(
        strategy=strategy,
        max_inks=max_inks,
        lpi=lpi,
        dpi=dpi,
        merge_threshold=merge_threshold,
        generate_underbase=generate_underbase,
        underbase_choke_px=underbase_choke_px,
        apply_trapping=apply_trapping,
        trap_px=trap_px,
        include_registration_marks=include_registration_marks,
        film_margin_px=film_margin_px,
        min_feature_px=min_feature_px,
    )
    try:
        result = generate_separation(image, settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(result["manifest"], indent=2))
        for name, payload in result["files"].items():
            zf.writestr(name, payload)
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="textileai-{strategy}-separation.zip"'
    })



@app.post("/api/separation/region-edit")
async def region_edit_separation(
    file: UploadFile = File(...),
    plate_name: str = Form(...),
    action: str = Form("erase"),
    polygon: str = Form(...),
    strategy: str = Query("spot", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    """Apply a polygon region edit to a single spot plate and export a revised ZIP.

    polygon is JSON: [[x,y], ...] in source-image pixel coordinates.
    action='erase' removes the polygon from the named plate; action='add' paints it
    onto that plate. The operation is deterministic and source image remains untouched.
    """
    import numpy as np
    from PIL import ImageDraw
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw)).convert("RGB")
        points = json.loads(polygon)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image.")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "polygon must be valid JSON.") from exc
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    if action not in ("erase", "add"):
        raise HTTPException(400, "action must be 'erase' or 'add'.")
    if not isinstance(points, list) or len(points) < 3:
        raise HTTPException(400, "polygon must contain at least three [x, y] points.")
    try:
        points = [(int(p[0]), int(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        raise HTTPException(400, "polygon points must be integer [x, y] pairs.")
    if any(x < 0 or y < 0 or x >= image.width or y >= image.height for x, y in points):
        raise HTTPException(400, "polygon points must lie within the source image.")
    settings = SeparationSettings(strategy=strategy, max_inks=max_inks, lpi=lpi, dpi=dpi, merge_threshold=merge_threshold, min_feature_px=min_feature_px)
    try:
        result = generate_separation(image, settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    files, manifest = dict(result["files"]), dict(result["manifest"])
    entry = next((p for p in manifest["plates"] if p["name"] == plate_name and p["type"] == "spot"), None)
    if entry is None:
        raise HTTPException(400, "plate_name must match an existing spot plate in this separation.")
    mask = Image.open(BytesIO(files[entry["filename"]])).convert("L")
    region = Image.new("L", image.size, 0)
    ImageDraw.Draw(region).polygon(points, fill=255)
    region_arr = np.asarray(region) > 0
    mask_arr = np.asarray(mask).copy()
    if action == "erase":
        mask_arr[region_arr] = 0
    else:
        mask_arr[region_arr] = 255
    mask = Image.fromarray(mask_arr.astype(np.uint8), mode="L")
    files[entry["filename"]] = _png_bytes(mask)
    cov_frac = float((mask_arr > 0).mean())
    entry["coverage_percent"] = round(cov_frac * 100, 3)
    ptype = entry.get("type", "spot")
    grams_per_100 = calculate_theoretical_ink_estimate(
        image.width, image.height, dpi, cov_frac, ptype
    )
    if grams_per_100 is not None:
        entry["estimated_grams_per_100_prints"] = grams_per_100
        entry.pop("estimated_grams_per_100_prints_status", None)
    else:
        entry["estimated_grams_per_100_prints"] = None
        entry["estimated_grams_per_100_prints_status"] = "unavailable"
    entry["region_edit"] = {"action": action, "polygon_points": points}
    manifest["plates"] = [dict(p) for p in manifest["plates"]]
    manifest["region_edits"] = manifest.get("region_edits", []) + [{
        "plate_name": plate_name, "action": action, "polygon": points
    }]
    manifest["quality_checks"] = dict(manifest.get("quality_checks", {}))
    manifest["quality_checks"]["all_plates_nonempty"] = all(p["coverage_percent"] > 0 for p in manifest["plates"])
    files["reports/plate_summary.csv"] = _plate_report_csv(manifest["plates"])
    files["preview/plate_contact_sheet.png"] = _plate_contact_sheet(manifest["plates"], files)
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, payload in files.items():
            zf.writestr(name, payload)
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="textileai-region-edited-separation.zip"'
    })




@app.post("/api/separation/edit-history")
async def edit_history_separation(
    file: UploadFile = File(...),
    operations: str = Form("[]"),
    strategy: str = Query("spot", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    """Replay an ordered region-edit history onto spot masks and export one final ZIP."""
    import numpy as np
    from PIL import ImageDraw
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 30 MB limit")
    try:
        image = Image.open(BytesIO(raw)).convert("RGB")
        ops = json.loads(operations)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Unsupported or corrupt image.")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "operations must be valid JSON.") from exc
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image exceeds the 25 megapixel MVP limit")
    if not isinstance(ops, list) or len(ops) > 200:
        raise HTTPException(400, "operations must be a list with at most 200 entries.")
    settings = SeparationSettings(strategy=strategy, max_inks=max_inks, lpi=lpi, dpi=dpi, merge_threshold=merge_threshold, min_feature_px=min_feature_px)
    try:
        result = generate_separation(image, settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    files, manifest = dict(result["files"]), dict(result["manifest"])
    entries = {p["name"]: p for p in manifest["plates"] if p["type"] == "spot"}
    history = []
    for index, op in enumerate(ops):
        if not isinstance(op, dict):
            raise HTTPException(400, f"Operation {index + 1} must be an object.")
        name, action, points = op.get("plate_name"), op.get("action"), op.get("polygon")
        if name not in entries:
            raise HTTPException(400, f"Operation {index + 1}: unknown spot plate.")
        if action not in ("erase", "add"):
            raise HTTPException(400, f"Operation {index + 1}: action must be 'erase' or 'add'.")
        if not isinstance(points, list) or len(points) < 3:
            raise HTTPException(400, f"Operation {index + 1}: polygon needs at least three points.")
        try:
            points = [(int(p[0]), int(p[1])) for p in points]
        except (TypeError, ValueError, IndexError):
            raise HTTPException(400, f"Operation {index + 1}: points must be integer [x, y] pairs.")
        if any(x < 0 or y < 0 or x >= image.width or y >= image.height for x, y in points):
            raise HTTPException(400, f"Operation {index + 1}: polygon points must be within image bounds.")
        entry = entries[name]
        mask = Image.open(BytesIO(files[entry["filename"]])).convert("L")
        region = Image.new("L", image.size, 0)
        ImageDraw.Draw(region).polygon(points, fill=255)
        region_arr = np.asarray(region) > 0
        mask_arr = np.asarray(mask).copy()
        if action == "erase":
            mask_arr[region_arr] = 0
        else:
            mask_arr[region_arr] = 255
        files[entry["filename"]] = _png_bytes(Image.fromarray(mask_arr.astype(np.uint8), mode="L"))
        cov_frac = float((mask_arr > 0).mean())
        entry["coverage_percent"] = round(cov_frac * 100, 3)
        ptype = entry.get("type", "spot")
        grams_per_100 = calculate_theoretical_ink_estimate(
            image.width, image.height, dpi, cov_frac, ptype
        )
        if grams_per_100 is not None:
            entry["estimated_grams_per_100_prints"] = grams_per_100
            entry.pop("estimated_grams_per_100_prints_status", None)
        else:
            entry["estimated_grams_per_100_prints"] = None
            entry["estimated_grams_per_100_prints_status"] = "unavailable"
        history.append({"plate_name": name, "action": action, "polygon": points})
    manifest["plates"] = [dict(p) for p in manifest["plates"]]
    manifest["region_edits"] = history
    manifest["edit_history_count"] = len(history)
    manifest["quality_checks"] = dict(manifest.get("quality_checks", {}))
    manifest["quality_checks"]["all_plates_nonempty"] = all(p["coverage_percent"] > 0 for p in manifest["plates"])
    files["reports/plate_summary.csv"] = _plate_report_csv(manifest["plates"])
    files["preview/plate_contact_sheet.png"] = _plate_contact_sheet(manifest["plates"], files)
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, payload in files.items():
            zf.writestr(name, payload)
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="textileai-edit-history.zip"'
    })


@app.post("/api/separation/commit")
def commit(settings: SeparationSettings, ink_ids: list[str]):
    if len(ink_ids) > settings.max_inks:
        raise HTTPException(400, "Ink count exceeds max_inks")
    if len(set(ink_ids)) != len(ink_ids):
        raise HTTPException(400, "Ink IDs must be unique")
    return {"plates": commit_plate_ids(settings, ink_ids), "committed": True}


@app.post("/api/separation/batch")
async def batch_separation(
    files: list[UploadFile] = File(...),
    strategy: str = Query("hybrid", pattern="^(spot|halftone|hybrid)$"),
    max_inks: int = Query(6, ge=1, le=16),
    lpi: int = Query(45, ge=10, le=100),
    dpi: int = Query(300, ge=72, le=2400),
    merge_threshold: float = Query(0.0, ge=0.0, le=30.0),
    generate_underbase: bool = Query(False),
    underbase_choke_px: int = Query(1, ge=0, le=10),
    apply_trapping: bool = Query(False),
    trap_px: int = Query(1, ge=1, le=5),
    include_registration_marks: bool = Query(False),
    film_margin_px: int = Query(40, ge=20, le=120),
    min_feature_px: int = Query(0, ge=0, le=20),
):
    """Process multiple designs in a single batch, outputting a consolidated ZIP with subdirectories and summary report."""
    if not files:
        raise HTTPException(400, "No files uploaded for batch separation.")
    if len(files) > 10:
        raise HTTPException(400, "Batch limit is 10 designs per request.")

    settings = SeparationSettings(
        strategy=strategy,
        max_inks=max_inks,
        lpi=lpi,
        dpi=dpi,
        merge_threshold=merge_threshold,
        generate_underbase=generate_underbase,
        underbase_choke_px=underbase_choke_px,
        apply_trapping=apply_trapping,
        trap_px=trap_px,
        include_registration_marks=include_registration_marks,
        film_margin_px=film_margin_px,
        min_feature_px=min_feature_px,
    )

    archive = BytesIO()
    batch_manifest = {
        "batch_size": len(files),
        "settings": settings.dict(),
        "designs": [],
    }
    csv_rows = []

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, upload in enumerate(files, start=1):
            raw = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(raw) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"File '{upload.filename}' exceeds 30 MB upload limit.")
            try:
                img = Image.open(BytesIO(raw))
            except (UnidentifiedImageError, OSError):
                raise HTTPException(400, f"File '{upload.filename}': Unsupported or corrupt image.")
            if img.width * img.height > 25_000_000:
                raise HTTPException(413, f"File '{upload.filename}' exceeds 25 megapixel limit.")

            try:
                res = generate_separation(img, settings)
            except ValueError as exc:
                raise HTTPException(400, f"File '{upload.filename}': {str(exc)}") from exc

            raw_filename = upload.filename or f"design_{idx}"
            safe_basename = os.path.basename(raw_filename)
            safe_name, _ = os.path.splitext(safe_basename)
            safe_slug = re.sub(r"[^\w\-]", "_", safe_name).strip("._") or f"design_{idx}"
            folder = f"design_{idx:02d}_{safe_slug}"

            zf.writestr(f"{folder}/manifest.json", json.dumps(res["manifest"], indent=2))
            for file_path, data in res["files"].items():
                zf.writestr(f"{folder}/{file_path}", data)

            total_grams = sum(
                p.get("estimated_grams_per_100_prints", 0)
                for p in res["manifest"]["plates"]
                if isinstance(p.get("estimated_grams_per_100_prints"), (int, float))
            )
            batch_manifest["designs"].append({
                "index": idx,
                "original_filename": upload.filename,
                "folder": folder,
                "plate_count": res["manifest"]["plate_count"],
                "total_estimated_grams_per_100": round(total_grams, 1),
            })
            csv_rows.append({
                "index": idx,
                "filename": upload.filename,
                "folder": folder,
                "width": img.width,
                "height": img.height,
                "plate_count": res["manifest"]["plate_count"],
                "total_estimated_grams_per_100": round(total_grams, 1),
            })

        summary_stream = StringIO(newline="")
        writer = csv.DictWriter(
            summary_stream,
            fieldnames=["index", "filename", "folder", "width", "height", "plate_count", "total_estimated_grams_per_100"],
        )
        writer.writeheader()
        writer.writerows(csv_rows)
        zf.writestr("batch_summary.csv", summary_stream.getvalue().encode("utf-8-sig"))
        zf.writestr("batch_manifest.json", json.dumps(batch_manifest, indent=2))

    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="textileai-batch-separation.zip"'},
    )
