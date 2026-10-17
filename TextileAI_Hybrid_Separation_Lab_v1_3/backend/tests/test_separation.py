from io import BytesIO
import json
import zipfile
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.analysis import analyze_rgb
from app.separation import (
    halftone_mask, recommend_candidates, commit_plate_ids, generate_separation,
    perceptual_palette_map, _rgb_to_lab, render_plate_composite,
    choke_mask, spread_mask, generate_underbase_mask, apply_spot_trapping,
    create_film_positive, cleanup_isolated_noise,
    recommend_mesh_count, calculate_theoretical_ink_estimate, DEPOSIT_RATES_G_PER_SQM
)
from app.models import SeparationSettings
from app.main import app

client = TestClient(app)

def test_analysis_detects_image_dimensions_and_tones():
    img = np.zeros((32, 64, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(np.arange(64, dtype=np.uint8) * 4, (32, 1))
    report = analyze_rgb(img)
    assert report.width == 64
    assert report.height == 32
    assert report.estimated_unique_rgb > 1
    assert report.luminance_stddev > 0

def test_halftone_coverage_is_monotonic():
    low = np.full((64, 64), 0.2, dtype=np.float32)
    high = np.full((64, 64), 0.8, dtype=np.float32)
    low_mask = halftone_mask(low)
    high_mask = halftone_mask(high)
    assert set(np.unique(high_mask)).issubset({0, 255})
    assert (high_mask > 0).mean() > (low_mask > 0).mean()

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
    assert all(p["strategy"] == "hybrid" for p in plates)

def make_png():
    # Colour blocks plus a smooth gradient to exercise both spot and tonal paths.
    h, w = 48, 64
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :22] = [245, 120, 160]
    arr[:, 22:43] = [80, 130, 190]
    for x in range(43, w):
        arr[:, x] = [x * 4, x * 3, x * 2]
    buf = BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()

def test_generate_spot_separation_has_individual_binary_plates():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="spot", max_inks=4))
    plate_files = [v for k, v in result["files"].items() if k.startswith("plates/")]
    assert plate_files
    assert all(set(np.unique(np.asarray(Image.open(BytesIO(p))))) <= {0, 255} for p in plate_files)
    assert result["manifest"]["source_preserved"] is True

def test_hybrid_includes_tonal_plate_and_spot_plates():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="hybrid", max_inks=4))
    types = {p["type"] for p in result["manifest"]["plates"]}
    assert types == {"spot", "tonal"}
    assert "plates/TONAL_01_halftone.png" in result["files"]

def test_upload_analysis_endpoint_accepts_real_image():
    response = client.post("/api/analysis", files={"file": ("sample.png", make_png(), "image/png")})
    assert response.status_code == 200
    assert response.json()["width"] == 64
    assert response.json()["height"] == 48

def test_preview_endpoint_returns_zip_with_manifest():
    response = client.post("/api/separation/preview?strategy=hybrid&max_inks=4", files={"file": ("sample.png", make_png(), "image/png")})
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["strategy"] == "hybrid"
        assert any(name.endswith("halftone.png") for name in archive.namelist())

def test_upload_rejects_non_image():
    response = client.post("/api/analysis", files={"file": ("bad.txt", b"not an image", "text/plain")})
    assert response.status_code == 400


def test_frontend_route_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Hybrid Separation Lab" in response.text


def test_frontend_controls_integrity():
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    # Verify presence of essential UI control IDs and inputs
    required_ids = [
        "batchBtn",
        "batchFileInput",
        "minFeature",
        "underbaseCheck",
        "underbaseChoke",
        "trappingCheck",
        "trapWidth",
        "regMarksCheck",
        "saveProjectBtn",
        "loadProjectBtn",
        "repeat1Btn",
        "repeat2Btn",
        "repeat3Btn",
        "renderServerProofBtn",
        "fabricColorSelect",
    ]
    for cid in required_ids:
        assert f'id="{cid}"' in text, f"Missing control id: {cid}"


def test_lpi_changes_approximate_screen_pattern():
    coverage = np.tile(np.linspace(0.05, 0.95, 96, dtype=np.float32), (96, 1))
    fine = halftone_mask(coverage, lpi=60, dpi=300)
    coarse = halftone_mask(coverage, lpi=25, dpi=300)
    assert not np.array_equal(fine, coarse)


def test_manifest_contains_quality_checks_and_screen_metadata():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="hybrid", max_inks=4, lpi=50, dpi=300))
    manifest = result["manifest"]
    assert manifest["schema_version"] == "0.6"
    assert manifest["quality_checks"]["plate_count_within_requested_limit"] is True
    assert manifest["approx_screen_cell_px"] == 6


def test_manifest_has_stable_source_fingerprint_and_plate_counts():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="spot", max_inks=4))
    manifest = result["manifest"]
    assert len(manifest["source_sha256"]) == 64
    assert manifest["plate_count"] == len(manifest["plates"])
    assert manifest["quality_checks"]["all_plates_nonempty"] is True
    assert "preview/reconstructed_preview.png" in result["files"]
    assert "preview/source_preview.png" in result["files"]


def test_hybrid_never_exceeds_requested_ink_limit():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="hybrid", max_inks=3))
    manifest = result["manifest"]
    assert manifest["plate_count"] <= 3
    assert manifest["quality_checks"]["plate_count_within_requested_limit"] is True


def test_reconstruction_metrics_are_present_and_finite():
    image = Image.open(BytesIO(make_png()))
    for strategy in ("spot", "halftone", "hybrid"):
        result = generate_separation(image, SeparationSettings(strategy=strategy, max_inks=4))
        manifest = result["manifest"]
        metrics = manifest["reconstruction_metrics"]
        assert metrics["mae_rgb_0_255"] >= 0
        assert metrics["rmse_rgb_0_255"] >= 0
        assert metrics["psnr_db"] > 0
        assert len(metrics["per_channel_mae_rgb"]) == 3
        assert manifest["quality_checks"]["reconstruction_preview_present"] is True


def test_reconstruction_preview_exists_for_all_strategies():
    image = Image.open(BytesIO(make_png()))
    for strategy in ("spot", "halftone", "hybrid"):
        result = generate_separation(image, SeparationSettings(strategy=strategy, max_inks=4))
        assert "preview/reconstructed_preview.png" in result["files"]


def test_lab_conversion_orders_nearby_colours_sensibly():
    rgb = np.array([[[0, 0, 0], [255, 255, 255], [255, 0, 0]]], dtype=np.uint8)
    lab = _rgb_to_lab(rgb)
    assert lab.shape == (1, 3, 3)
    assert lab[0, 0, 0] < lab[0, 1, 0]
    assert np.isfinite(lab).all()


def test_perceptual_palette_map_preserves_palette_and_dimensions():
    source = np.array([[[250, 20, 30], [230, 25, 35], [10, 20, 240]]], dtype=np.uint8)
    seeds = np.array([[240, 20, 30], [0, 0, 255]], dtype=np.uint8)
    labels, palette = perceptual_palette_map(source, seeds, chunk_pixels=2)
    assert labels.shape == (1, 3)
    assert set(np.unique(labels)).issubset({0, 1})
    assert np.array_equal(palette, seeds)
    assert labels[0, 0] == labels[0, 1]
    assert labels[0, 2] == 1


def test_v06_manifest_declares_lab_assignment():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="spot", max_inks=4))
    manifest = result["manifest"]
    assert manifest["engine_version"] == "1.0.0"
    assert "CIE Lab" in manifest["palette_method"]
    assert manifest["quality_checks"]["plate_count_within_requested_limit"] is True


def test_v07_exports_plate_contact_sheet_and_csv_report():
    image = Image.open(BytesIO(make_png()))
    result = generate_separation(image, SeparationSettings(strategy="hybrid", max_inks=4))
    assert "preview/plate_contact_sheet.png" in result["files"]
    assert "reports/plate_summary.csv" in result["files"]
    contact = Image.open(BytesIO(result["files"]["preview/plate_contact_sheet.png"]))
    assert contact.width > 0 and contact.height > 0
    report = result["files"]["reports/plate_summary.csv"].decode("utf-8-sig")
    assert "name,type,hex,filename,coverage_percent,note" in report
    assert "TONAL_01" in report
    assert result["manifest"]["quality_checks"]["plate_contact_sheet_present"] is True
    assert result["manifest"]["quality_checks"]["plate_csv_report_present"] is True


def test_v08_interactive_inspector_endpoint_returns_plate_previews():
    response = client.post(
        "/api/separation/inspect?strategy=hybrid&max_inks=4&lpi=45&dpi=300",
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "hybrid"
    assert data["plates"]
    assert all(p["preview_data"] and p["name"] for p in data["plates"])
    assert data["reconstructed_preview_data"]
    assert "mae_rgb_0_255" in data["metrics"]


def test_v09_merge_threshold_is_recorded_and_applied():
    image = Image.open(BytesIO(make_png())).convert("RGB")
    settings = SeparationSettings(strategy="spot", max_inks=8, merge_threshold=12.0)
    result = generate_separation(image, settings)
    assert result["manifest"]["merge_threshold_lab_approx"] == 12.0
    assert "optional greedy Lab-threshold seed merge" in result["manifest"]["palette_method"]

def test_v09_inspect_endpoint_accepts_merge_threshold():
    response = client.post(
        "/api/separation/inspect?strategy=spot&max_inks=8&merge_threshold=12",
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["plates"]


def test_v10_manual_merge_endpoint_merges_selected_spot_masks():
    response = client.post(
        "/api/separation/edit?strategy=spot&max_inks=6",
        data={"merge_groups": '[["INK_01","INK_02"]]'},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    archive = zipfile.ZipFile(BytesIO(response.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["manual_merge_groups"] == [["INK_01", "INK_02"]]
    assert any(p["name"] == "INK_01+INK_02" for p in manifest["plates"])
    assert "reports/plate_summary.csv" in archive.namelist()
    assert "preview/plate_contact_sheet.png" in archive.namelist()

def test_v10_manual_merge_rejects_single_plate_group():
    response = client.post(
        "/api/separation/edit?strategy=spot&max_inks=6",
        data={"merge_groups": '[["INK_01"]]'},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 400


def test_v11_region_edit_erases_polygon_and_exports_updated_reports():
    response = client.post(
        "/api/separation/region-edit?strategy=spot&max_inks=6",
        data={
            "plate_name": "INK_01",
            "action": "erase",
            "polygon": "[[0,0],[20,0],[20,20],[0,20]]",
        },
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["region_edits"][0]["action"] == "erase"
        assert manifest["region_edits"][0]["plate_name"] == "INK_01"
        assert "reports/plate_summary.csv" in archive.namelist()
        assert "preview/plate_contact_sheet.png" in archive.namelist()

def test_v11_region_edit_rejects_unknown_plate_and_invalid_polygon():
    unknown = client.post(
        "/api/separation/region-edit?strategy=spot&max_inks=6",
        data={"plate_name": "NO_SUCH_PLATE", "action": "erase", "polygon": "[[0,0],[5,0],[5,5]]"},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert unknown.status_code == 400
    invalid = client.post(
        "/api/separation/region-edit?strategy=spot&max_inks=6",
        data={"plate_name": "INK_01", "action": "erase", "polygon": "[[0,0],[1000,0],[2,2]]"},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert invalid.status_code == 400

def test_v11_health_reports_version():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] in ("1.3.0", "1.3.1", "1.4.0", "1.5.0", "1.6.0")


def test_v12_edit_history_replays_multiple_operations_in_order():
    response = client.post(
        "/api/separation/edit-history?strategy=spot&max_inks=6",
        data={"operations": json.dumps([
            {"plate_name": "INK_01", "action": "erase", "polygon": [[0,0],[10,0],[10,10],[0,10]]},
            {"plate_name": "INK_01", "action": "add", "polygon": [[1,1],[5,1],[5,5],[1,5]]},
        ])},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["edit_history_count"] == 2
        assert [op["action"] for op in manifest["region_edits"]] == ["erase", "add"]
        assert "preview/plate_contact_sheet.png" in archive.namelist()

def test_v12_edit_history_rejects_out_of_bounds_operation():
    response = client.post(
        "/api/separation/edit-history?strategy=spot&max_inks=6",
        data={"operations": json.dumps([
            {"plate_name": "INK_01", "action": "erase", "polygon": [[0,0],[1000,0],[5,5]]}
        ])},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 400

def test_v12_health_reports_version():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] in ("1.3.0", "1.3.1", "1.4.0", "1.5.0", "1.6.0")


def make_transparent_png():
    h, w = 40, 40
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    # Paint a solid red square in the center
    arr[10:30, 10:25] = [210, 40, 40, 255]
    # Paint a solid blue square next to it
    arr[10:30, 25:35] = [40, 60, 210, 255]
    # The borders [0:10, :] and [30:40, :] have alpha=0 (fully transparent)
    buf = BytesIO()
    Image.fromarray(arr, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def test_v13_alpha_transparency_preserves_unprinted_background():
    img = Image.open(BytesIO(make_transparent_png()))
    settings = SeparationSettings(strategy="hybrid", max_inks=4)
    result = generate_separation(img, settings)
    manifest = result["manifest"]
    assert manifest["has_transparency"] is True
    assert manifest["transparent_pixels_percent"] > 0
    assert manifest["quality_checks"]["transparency_handled"] is True

    # Verify that in transparent border areas (e.g. y=2, x=2), no ink mask prints
    for plate in manifest["plates"]:
        mask = np.asarray(Image.open(BytesIO(result["files"][plate["filename"]])).convert("L"))
        # Border must have zero ink coverage
        assert mask[0:8, :].max() == 0
        assert mask[32:40, :].max() == 0


def test_v13_render_plate_composite_opacity_changes_pixels():
    img = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(strategy="spot", max_inks=4)
    result = generate_separation(img, settings)
    plates = result["manifest"]["plates"]
    files = result["files"]

    # Render with 100% opacity
    comp_100 = np.asarray(render_plate_composite(plates, files, opacities={"INK_01": 1.0}))
    # Render with 40% opacity
    comp_40 = np.asarray(render_plate_composite(plates, files, opacities={"INK_01": 0.4}))
    # Render with 0% opacity
    comp_0 = np.asarray(render_plate_composite(plates, files, opacities={"INK_01": 0.0}))

    # Verify that changing opacity directly alters pixel values
    assert not np.array_equal(comp_100, comp_40)
    assert not np.array_equal(comp_40, comp_0)
    assert not np.array_equal(comp_100, comp_0)


def test_v13_render_plate_composite_visibility_and_fabric_color():
    img = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(strategy="spot", max_inks=4)
    result = generate_separation(img, settings)
    plates = result["manifest"]["plates"]
    files = result["files"]

    # Test toggling plate visibility
    comp_visible = np.asarray(render_plate_composite(plates, files, visibilities={"INK_01": True}))
    comp_hidden = np.asarray(render_plate_composite(plates, files, visibilities={"INK_01": False}))
    assert not np.array_equal(comp_visible, comp_hidden)

    # When a plate is hidden or artwork has unprinted areas, fabric shows through
    comp_white_hidden = np.asarray(render_plate_composite(plates, files, visibilities={"INK_01": False}, fabric_hex="#FFFFFF"))
    comp_dark_hidden = np.asarray(render_plate_composite(plates, files, visibilities={"INK_01": False}, fabric_hex="#112233"))
    assert not np.array_equal(comp_white_hidden, comp_dark_hidden)

    # Test fabric color on artwork with transparent unprinted regions
    t_result = generate_separation(Image.open(BytesIO(make_transparent_png())), settings)
    t_white = np.asarray(render_plate_composite(t_result["manifest"]["plates"], t_result["files"], fabric_hex="#FFFFFF"))
    t_dark = np.asarray(render_plate_composite(t_result["manifest"]["plates"], t_result["files"], fabric_hex="#112233"))
    assert not np.array_equal(t_white, t_dark)


def test_v13_api_separation_composite_endpoint():
    response = client.post(
        "/api/separation/composite?strategy=hybrid&max_inks=4&fabric_color=%23112233",
        data={"plate_settings": json.dumps({"opacities": {"INK_01": 0.5}})},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    im = Image.open(BytesIO(response.content))
    assert im.size == (64, 48)


def test_v13_api_analysis_and_inspect_transparent_image():
    # Analysis must handle transparent images without error
    resp_analysis = client.post(
        "/api/analysis",
        files={"file": ("transparent.png", make_transparent_png(), "image/png")}
    )
    assert resp_analysis.status_code == 200
    assert resp_analysis.json()["width"] == 40
    assert resp_analysis.json()["height"] == 40

    # Inspection must return valid plates
    resp_inspect = client.post(
        "/api/separation/inspect?strategy=spot&max_inks=4",
        files={"file": ("transparent.png", make_transparent_png(), "image/png")}
    )
    assert resp_inspect.status_code == 200
    data = resp_inspect.json()
    assert len(data["plates"]) >= 1
    assert data["quality_checks"]["transparency_handled"] is True


def test_morphological_choke_and_spread():
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[10:20, 10:20] = 255  # 10x10 square = 100 pixels

    choked = choke_mask(mask, 1)
    # After 1px choke, each side erodes by 1 pixel -> 8x8 square = 64 pixels
    assert np.sum(choked > 0) == 64
    assert np.all(choked[11:19, 11:19] == 255)
    assert np.all(choked[10, :] == 0) and np.all(choked[:, 10] == 0)

    spread = spread_mask(mask, 1)
    # After 1px spread, each side expands by 1 pixel -> 12x12 square = 144 pixels
    assert np.sum(spread > 0) == 144
    assert np.all(spread[9:21, 9:21] == 255)


def test_underbase_generation_with_choke():
    image = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(strategy="spot", max_inks=4, generate_underbase=True, underbase_choke_px=1)
    result = generate_separation(image, settings)
    manifest = result["manifest"]
    plates = manifest["plates"]

    # First plate should be UNDERBASE_WHITE
    assert plates[0]["name"] == "UNDERBASE_WHITE"
    assert plates[0]["type"] == "underbase"
    assert plates[0]["hex"] == "#FFFFFF"
    assert "plates/UNDERBASE_WHITE_underbase.png" in result["files"]

    ub_mask = np.asarray(Image.open(BytesIO(result["files"]["plates/UNDERBASE_WHITE_underbase.png"])).convert("L"))
    assert set(np.unique(ub_mask)) <= {0, 255}
    assert plates[0]["coverage_percent"] > 0

    # Underbase stats in manifest
    assert manifest["generate_underbase"] is True
    assert manifest["underbase_stats"]["generated"] is True
    assert manifest["underbase_stats"]["choke_px"] == 1
    assert manifest["quality_checks"]["underbase_generated"] is True


def test_spot_trapping_creates_inter_plate_overlap():
    # Create two adjacent color blocks (Light yellow next to Dark navy)
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:, :20] = [255, 255, 0]   # Light yellow
    arr[:, 20:] = [10, 20, 50]    # Dark navy
    im = Image.fromarray(arr, mode="RGB")

    # Without trapping: no overlap between spot plates
    no_trap = generate_separation(im, SeparationSettings(strategy="spot", max_inks=2, apply_trapping=False))
    m1 = np.asarray(Image.open(BytesIO(no_trap["files"][no_trap["manifest"]["plates"][0]["filename"]])).convert("L"))
    m2 = np.asarray(Image.open(BytesIO(no_trap["files"][no_trap["manifest"]["plates"][1]["filename"]])).convert("L"))
    assert np.sum((m1 > 0) & (m2 > 0)) == 0

    # With trapping (1px): lighter plate expands into darker plate along seam
    trapped = generate_separation(im, SeparationSettings(strategy="spot", max_inks=2, apply_trapping=True, trap_px=1))
    tm1 = np.asarray(Image.open(BytesIO(trapped["files"][trapped["manifest"]["plates"][0]["filename"]])).convert("L"))
    tm2 = np.asarray(Image.open(BytesIO(trapped["files"][trapped["manifest"]["plates"][1]["filename"]])).convert("L"))
    overlap = np.sum((tm1 > 0) & (tm2 > 0))
    assert overlap == 40  # 40px seam height * 1px trap
    assert trapped["manifest"]["trapping_stats"]["applied"] is True
    assert trapped["manifest"]["trapping_stats"]["overlap_pixels"] == 40
    assert trapped["manifest"]["quality_checks"]["trapping_applied"] is True


def test_underbase_excludes_transparent_pixels():
    image = Image.open(BytesIO(make_transparent_png()))
    settings = SeparationSettings(strategy="spot", max_inks=4, generate_underbase=True, underbase_choke_px=1)
    result = generate_separation(image, settings)
    ub_mask = np.asarray(Image.open(BytesIO(result["files"]["plates/UNDERBASE_WHITE_underbase.png"])).convert("L"))

    # Transparent margin in make_transparent_png: corners and outer border have alpha=0
    raw_rgba = np.asarray(image)
    alpha = raw_rgba[..., 3]
    transparent_coords = (alpha == 0)
    assert np.all(ub_mask[transparent_coords] == 0)


def test_non_rgb_image_modes_ingestion():
    # Grayscale image (L)
    im_l = Image.new("L", (32, 24), 180)
    res_l = generate_separation(im_l, SeparationSettings(strategy="spot", max_inks=2))
    assert res_l["manifest"]["width"] == 32
    assert res_l["manifest"]["height"] == 24
    assert res_l["manifest"]["source_preserved"] is True

    # Palette image (P)
    im_p = Image.new("P", (32, 24))
    res_p = generate_separation(im_p, SeparationSettings(strategy="spot", max_inks=2))
    assert res_p["manifest"]["width"] == 32
    assert res_p["manifest"]["height"] == 24
    assert res_p["manifest"]["source_preserved"] is True


def test_composite_with_recoloring_and_underbase():
    image = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(strategy="spot", max_inks=4, generate_underbase=True, underbase_choke_px=1)
    result = generate_separation(image, settings)
    plates = result["manifest"]["plates"]
    files = result["files"]

    # Render composite with custom recoloring
    comp_normal = render_plate_composite(plates, files, fabric_hex="#000000")
    comp_recolored = render_plate_composite(
        plates, files,
        colors={"UNDERBASE_WHITE": "#D0D0D0", "INK_01": "#FF00FF"},
        fabric_hex="#000000"
    )
    assert comp_normal.size == (64, 48)
    assert comp_recolored.size == (64, 48)
    assert not np.array_equal(np.asarray(comp_normal), np.asarray(comp_recolored))


def test_v14_api_endpoints_underbase_and_trapping():
    # Inspect endpoint with underbase & trapping
    resp_inspect = client.post(
        "/api/separation/inspect?strategy=spot&max_inks=4&generate_underbase=true&underbase_choke_px=1&apply_trapping=true&trap_px=1",
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_inspect.status_code == 200
    data = resp_inspect.json()
    assert data["quality_checks"]["underbase_generated"] is True
    assert data["quality_checks"]["trapping_applied"] is True
    assert any(p["type"] == "underbase" for p in data["plates"])

    # Composite endpoint with underbase & trapping & custom colors
    resp_composite = client.post(
        "/api/separation/composite?strategy=spot&max_inks=4&generate_underbase=true&apply_trapping=true&fabric_color=%23112233",
        data={"plate_settings": json.dumps({"colors": {"UNDERBASE_WHITE": "#F0F0F0"}})},
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_composite.status_code == 200
    assert resp_composite.headers["content-type"] == "image/png"

    # Preview endpoint ZIP with underbase plate
    resp_preview = client.post(
        "/api/separation/preview?strategy=spot&max_inks=4&generate_underbase=true&apply_trapping=true",
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_preview.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_preview.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["generate_underbase"] is True
        assert manifest["apply_trapping"] is True
        assert "plates/UNDERBASE_WHITE_underbase.png" in archive.namelist()


def test_create_film_positive_structure_and_dimensions():
    # 64 wide x 48 high test mask
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[10:38, 10:54] = 255
    margin = 40
    header = 32

    film = create_film_positive(mask, "INK_01", "spot", "#FF0000", dpi=300, lpi=45, margin_px=margin)
    expected_w = 64 + 2 * margin
    expected_h = 48 + 2 * margin + header
    assert film.size == (expected_w, expected_h)
    assert film.mode == "L"

    film_arr = np.asarray(film)
    # The mask content should be centered in the canvas
    artwork_region = film_arr[margin + header : margin + header + 48, margin : margin + 64]
    assert np.array_equal(artwork_region, mask)

    # Margin perimeter should contain registration target pixels (value 255)
    margin_top = film_arr[:margin + header, :]
    assert np.any(margin_top == 255)
    margin_bot = film_arr[margin + header + 48:, :]
    assert np.any(margin_bot == 255)


def test_generate_separation_with_film_positives():
    image = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(
        strategy="spot",
        max_inks=4,
        include_registration_marks=True,
        film_margin_px=40
    )
    result = generate_separation(image, settings)
    manifest = result["manifest"]
    files = result["files"]

    assert manifest["include_registration_marks"] is True
    assert len(manifest["film_positives"]) == len(manifest["plates"])
    assert manifest["quality_checks"]["registration_marks_present"] is True

    # Check film files exist in files dictionary
    for entry in manifest["film_positives"]:
        assert entry["filename"] in files
        film_im = Image.open(BytesIO(files[entry["filename"]]))
        assert film_im.width == 64 + 2 * 40
        assert film_im.height == 48 + 2 * 40 + 32


def test_preview_endpoint_with_film_positives():
    resp = client.post(
        "/api/separation/preview?strategy=spot&max_inks=4&include_registration_marks=true&film_margin_px=40",
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(BytesIO(resp.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["include_registration_marks"] is True
        film_files = [f for f in archive.namelist() if f.startswith("films/")]
        assert len(film_files) == len(manifest["plates"])


def test_cleanup_isolated_noise_removes_pinholes():
    # 20x20 mask with a 6x6 solid block and isolated 1-pixel and 2-pixel islands
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[2:8, 2:8] = 255  # 36 pixels (solid feature)
    mask[12, 12] = 255     # 1-pixel island
    mask[15, 15:17] = 255  # 2-pixel island

    # With min_feature_px=0, mask should be completely untouched
    untouched, cleaned_count = cleanup_isolated_noise(mask, min_feature_px=0)
    assert np.array_equal(untouched, mask)
    assert cleaned_count == 0

    # With min_feature_px=2, 1-pixel and 2-pixel islands should be removed, solid block preserved
    cleaned, cleaned_count = cleanup_isolated_noise(mask, min_feature_px=2)
    assert cleaned[12, 12] == 0
    assert np.all(cleaned[15, 15:17] == 0)
    assert np.all(cleaned[2:8, 2:8] == 255)
    assert (cleaned > 0).sum() == 36
    assert cleaned_count == 3


def test_pattern_repeat_analysis_metrics():
    # Perfectly repeating pattern: horizontal and vertical borders match exactly
    seamless = np.zeros((32, 32, 3), dtype=np.uint8)
    for y in range(32):
        for x in range(32):
            seamless[y, x] = [
                int(128 + 127 * np.sin(x * 2 * np.pi / 31)),
                int(128 + 127 * np.cos(y * 2 * np.pi / 31)),
                100,
            ]
    rep = analyze_rgb(seamless)
    assert rep.is_seamless_repeat is True
    assert rep.horizontal_seam_delta < 0.01
    assert rep.vertical_seam_delta < 0.01
    assert rep.horizontal_seam_p95 < 0.01
    assert rep.vertical_seam_p95 < 0.01
    assert rep.horizontal_seam_max < 0.01
    assert rep.vertical_seam_max < 0.01
    assert any("edge continuity diagnostic" in w for w in rep.warnings)

    # Deliberate localized edge defect on single pixel:
    # Mean delta remains low (< 0.035), but localized max delta spikes (> 0.15).
    # Verifies we do NOT classify as seamless based on average edge colour alone.
    defect_img = np.copy(seamless)
    defect_img[10, 0] = [255, 0, 0]
    defect_img[10, -1] = [0, 255, 0]
    rep_defect = analyze_rgb(defect_img)
    assert rep_defect.is_seamless_repeat is False
    assert rep_defect.horizontal_seam_max > 0.15
    assert any("Repeat seam discontinuity detected" in w for w in rep_defect.warnings)
    assert any("p95" in w for w in rep_defect.warnings)

    # Non-seamless image: top row is black, bottom row is white
    non_seamless = np.zeros((32, 32, 3), dtype=np.uint8)
    non_seamless[:16, :] = [0, 0, 0]
    non_seamless[16:, :] = [255, 255, 255]
    rep_non = analyze_rgb(non_seamless)
    assert rep_non.is_seamless_repeat is False
    assert rep_non.vertical_seam_delta > 0.5
    assert any("Repeat seam discontinuity detected" in w for w in rep_non.warnings)


def test_repeat_analysis_p95_warning_consistency_regression():
    # 100x100 pattern where top/bottom borders match identically,
    # and 93 border pixels match identically, while 7 border pixels have a moderate delta of ~0.12.
    # Max delta = 0.12 (<= 0.15) -> does not trigger old max condition.
    # Mean delta = (7 * 0.12) / 100 = 0.0084 (<= 0.08 and <= 0.035) -> does not trigger old mean condition.
    # p95 delta = 0.12 (> 0.08) -> fails seamless classification, must trigger warning!
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [100, 100, 100]
    # Place 7 differing pixels strictly in middle rows (rows 40..46) along the right border
    # Delta: |153 - 100| / (255 * sqrt(3)) = 53 / 441.6729 = 0.1200
    for y in range(40, 47):
        img[y, -1] = [153, 100, 100]

    rep = analyze_rgb(img)
    assert rep.is_seamless_repeat is False
    assert rep.horizontal_seam_max <= 0.15
    assert rep.horizontal_seam_delta <= 0.08
    assert rep.horizontal_seam_p95 > 0.08
    # The warning MUST be emitted now, even though old max (>0.15) and mean (>0.08) conditions are not met
    assert any("Repeat seam discontinuity detected" in w for w in rep.warnings)
    assert any("p95" in w for w in rep.warnings)


def test_generate_separation_with_speckle_cleanup():
    # Generate image with noise dots
    img_arr = np.zeros((48, 64, 3), dtype=np.uint8)
    img_arr[:, :30] = [200, 50, 50]
    img_arr[:, 30:] = [50, 50, 200]
    # Add isolated pixel noise
    img_arr[5, 50] = [200, 50, 50]
    img = Image.fromarray(img_arr)

    settings = SeparationSettings(strategy="spot", max_inks=3, min_feature_px=2)
    result = generate_separation(image=img, settings=settings)
    manifest = result["manifest"]
    assert manifest["min_feature_px"] == 2
    assert manifest["speckle_cleanup_applied"] is True
    assert manifest["quality_checks"]["speckle_cleanup_applied"] is True


def test_api_endpoints_speckle_cleanup_and_repeat():
    # 1. /api/analysis includes repeat metrics
    resp_analysis = client.post("/api/analysis", files={"file": ("sample.png", make_png(), "image/png")})
    assert resp_analysis.status_code == 200
    data_a = resp_analysis.json()
    assert "is_seamless_repeat" in data_a
    assert "horizontal_seam_delta" in data_a
    assert "vertical_seam_delta" in data_a

    # 2. /api/separation/inspect with min_feature_px
    resp_inspect = client.post(
        "/api/separation/inspect?strategy=spot&max_inks=4&min_feature_px=2",
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_inspect.status_code == 200
    data_i = resp_inspect.json()
    assert data_i["quality_checks"]["speckle_cleanup_applied"] is True

    # 3. /api/separation/composite with min_feature_px
    resp_composite = client.post(
        "/api/separation/composite?strategy=spot&max_inks=4&min_feature_px=2&fabric_color=%23FFFFFF",
        data={"plate_settings": "{}"},
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_composite.status_code == 200
    assert resp_composite.headers["content-type"] == "image/png"

    # 4. /api/separation/preview with min_feature_px
    resp_preview = client.post(
        "/api/separation/preview?strategy=spot&max_inks=4&min_feature_px=2",
        files={"file": ("sample.png", make_png(), "image/png")}
    )
    assert resp_preview.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_preview.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["min_feature_px"] == 2
        assert manifest["speckle_cleanup_applied"] is True


def test_mesh_recommendation_and_ink_consumption_calculation():
    image = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(strategy="hybrid", max_inks=4, generate_underbase=True)
    result = generate_separation(image, settings)
    manifest = result["manifest"]
    plates = manifest["plates"]

    # Verify each plate has prepress recommendations
    for p in plates:
        assert "mesh_recommendation" in p
        assert "mesh" in p["mesh_recommendation"]
        assert "estimated_grams_per_100_prints" in p
        assert p["estimated_grams_per_100_prints"] >= 0

    # Specific type checks
    ub = next(p for p in plates if p["type"] == "underbase")
    assert "110-156 mesh" in ub["mesh_recommendation"]

    tonal = next(p for p in plates if p["type"] == "tonal")
    assert "halftone screen" in tonal["mesh_recommendation"]

    spot = next(p for p in plates if p["type"] == "spot")
    assert "156-230 mesh" in spot["mesh_recommendation"]

    # CSV report should have columns
    csv_bytes = result["files"]["reports/plate_summary.csv"]
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "mesh_recommendation" in csv_text
    assert "estimated_grams_per_100_prints" in csv_text


def test_cleanup_preserves_fine_diagonal_strokes():
    # 20x20 mask with a 4-pixel continuous diagonal stroke and isolated 1-pixel noise
    mask = np.zeros((20, 20), dtype=np.uint8)
    for i in range(4):
        mask[2 + i, 2 + i] = 255  # 4 pixels in diagonal continuity
    mask[15, 15] = 255  # 1-pixel isolated noise

    cleaned, count = cleanup_isolated_noise(mask, min_feature_px=2)
    # The 1-pixel noise must be cleared
    assert cleaned[15, 15] == 0
    # The 4-pixel diagonal stroke MUST be preserved thanks to 8-connectivity!
    for i in range(4):
        assert cleaned[2 + i, 2 + i] == 255
    assert (cleaned > 0).sum() == 4
    assert count == 1


def test_repeat_analysis_detects_localized_edge_defects():
    # 64x64 image that matches along 95% of the border, but has a localized defect
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:, :] = [100, 150, 200]
    # Localized defect: top edge at x in 10..13 has bright red mismatch (defect width 4px)
    arr[0, 10:14] = [255, 0, 0]

    rep = analyze_rgb(arr)
    # Mean delta might be small because 4/64 is only ~6% of edge
    assert rep.vertical_seam_delta < 0.10
    # But max delta exposes the defect
    assert rep.vertical_seam_max > 0.40
    # It must NOT be falsely classified as seamless
    assert rep.is_seamless_repeat is False


def test_min_feature_px_persisted_across_edit_endpoints():
    # 1. /api/separation/edit accepts min_feature_px
    resp_edit = client.post(
        "/api/separation/edit?strategy=spot&max_inks=6&min_feature_px=2",
        data={"merge_groups": json.dumps([["INK_01", "INK_02"]])},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert resp_edit.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_edit.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["min_feature_px"] == 2
        assert manifest["speckle_cleanup_applied"] is True

    # 2. /api/separation/region-edit accepts min_feature_px
    resp_reg = client.post(
        "/api/separation/region-edit?strategy=spot&max_inks=6&min_feature_px=2",
        data={"plate_name": "INK_01", "action": "erase", "polygon": json.dumps([[0, 0], [10, 0], [10, 10], [0, 10]])},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert resp_reg.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_reg.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["min_feature_px"] == 2
        assert manifest["speckle_cleanup_applied"] is True

    # 3. /api/separation/edit-history accepts min_feature_px
    resp_hist = client.post(
        "/api/separation/edit-history?strategy=spot&max_inks=6&min_feature_px=2",
        data={"operations": json.dumps([{"plate_name": "INK_01", "action": "erase", "polygon": [[0, 0], [5, 0], [5, 5], [0, 5]]}])},
        files={"file": ("sample.png", make_png(), "image/png")},
    )
    assert resp_hist.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_hist.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["min_feature_px"] == 2
        assert manifest["speckle_cleanup_applied"] is True


def test_batch_separation_endpoint():
    png1 = make_png()
    png2 = make_png()
    files = [
        ("files", ("colorway_a.png", png1, "image/png")),
        ("files", ("colorway_b.png", png2, "image/png")),
    ]
    resp = client.post(
        "/api/separation/batch?strategy=spot&max_inks=4&min_feature_px=1",
        files=files,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(resp.content)) as archive:
        names = archive.namelist()
        assert "batch_summary.csv" in names
        assert "batch_manifest.json" in names
        assert any(n.startswith("design_01_colorway_a/") for n in names)
        assert any(n.startswith("design_02_colorway_b/") for n in names)
        b_manifest = json.loads(archive.read("batch_manifest.json"))
        assert b_manifest["batch_size"] == 2
        assert len(b_manifest["designs"]) == 2


def test_theoretical_ink_estimate_numerical_assertion():
    # 600x400 px at 300 DPI
    # width_m = (600 / 300) * 0.0254 = 0.0508 m
    # height_m = (400 / 300) * 0.0254 = 0.033866667 m
    # total_sqm = 0.001720427 m^2
    # Area per 100 prints = 0.1720427 m^2

    # 1. Underbase: 50.0 g/m², 100% coverage
    ub_est = calculate_theoretical_ink_estimate(600, 400, 300, 1.0, "underbase")
    # 0.1720427 * 1.0 * 50.0 = 8.6021 -> 8.6 g
    assert ub_est == 8.6

    # 2. Spot: 30.0 g/m², 50% coverage
    spot_est = calculate_theoretical_ink_estimate(600, 400, 300, 0.5, "spot")
    # 0.1720427 * 0.5 * 30.0 = 2.5806 -> 2.6 g
    assert spot_est == 2.6

    # 3. Tonal: 18.0 g/m², 25% coverage
    tonal_est = calculate_theoretical_ink_estimate(600, 400, 300, 0.25, "tonal")
    # 0.1720427 * 0.25 * 18.0 = 0.77419 -> 0.8 g
    assert tonal_est == 0.8

    # 4. Unknown plate type or None: returns None
    assert calculate_theoretical_ink_estimate(600, 400, 300, 0.5, "specialty_puff") is None
    assert calculate_theoretical_ink_estimate(600, 400, 300, 0.5, None) is None


def test_generate_separation_plate_type_ink_estimation_consistency():
    img = Image.open(BytesIO(make_png()))
    settings = SeparationSettings(
        strategy="hybrid",
        max_inks=4,
        dpi=300,
        lpi=45,
        generate_underbase=True
    )
    result = generate_separation(img, settings)
    manifest = result["manifest"]
    plates = manifest["plates"]

    # Verify presence of all three plate types: underbase, spot, tonal
    types = [p["type"] for p in plates]
    assert "underbase" in types
    assert "spot" in types
    assert "tonal" in types

    for p in plates:
        cov_frac = p["coverage_percent"] / 100.0
        expected_g = calculate_theoretical_ink_estimate(img.width, img.height, settings.dpi, cov_frac, p["type"])
        assert p["estimated_grams_per_100_prints"] == expected_g
        assert p["mesh_recommendation"] == recommend_mesh_count(p["type"], settings.lpi)


def test_batch_separation_error_handling_and_path_sanitization():
    # 1. Corrupt image file returns 400
    files_corrupt = [
        ("files", ("bad.png", b"not-a-valid-image-bytes", "image/png"))
    ]
    resp_corrupt = client.post("/api/separation/batch", files=files_corrupt)
    assert resp_corrupt.status_code == 400
    assert "Unsupported or corrupt image" in resp_corrupt.json()["detail"]

    # 2. Path traversal filename is safely sanitized
    png_data = make_png()
    files_traversal = [
        ("files", ("../../evil_design.png", png_data, "image/png"))
    ]
    resp_trav = client.post("/api/separation/batch?strategy=spot&max_inks=3", files=files_traversal)
    assert resp_trav.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_trav.content)) as archive:
        names = archive.namelist()
        # Verify no directory traversal tokens exist in ZIP
        assert not any(".." in n for n in names)
        assert any(n.startswith("design_01_evil_design/") for n in names)


def test_region_edit_plate_type_ink_estimates_underbase_spot_tonal():
    png_data = make_png()

    # 1. Underbase plate region-edit (underbase rate = 50.0 g/m²)
    resp_ub = client.post(
        "/api/separation/region-edit?strategy=hybrid&max_inks=4&dpi=300&generate_underbase=true",
        data={
            "plate_name": "UNDERBASE_WHITE",
            "action": "erase",
            "polygon": json.dumps([[0, 0], [20, 0], [20, 20], [0, 20]]),
        },
        files={"file": ("sample.png", png_data, "image/png")},
    )
    assert resp_ub.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_ub.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        ub_plate = next(p for p in manifest["plates"] if p["name"] == "UNDERBASE_WHITE")
        assert ub_plate["type"] == "underbase"
        cov_frac = ub_plate["coverage_percent"] / 100.0
        expected_g = calculate_theoretical_ink_estimate(64, 48, 300, cov_frac, "underbase")
        assert ub_plate["estimated_grams_per_100_prints"] == expected_g
        assert ub_plate["mesh_recommendation"] == "110-156 mesh (opaque underbase deposit)"
        # Check CSV output consistency
        csv_text = archive.read("reports/plate_summary.csv").decode("utf-8-sig")
        assert "UNDERBASE_WHITE" in csv_text
        assert str(expected_g) in csv_text

    # 2. Spot plate region-edit (spot rate = 30.0 g/m²)
    resp_spot = client.post(
        "/api/separation/region-edit?strategy=spot&max_inks=4&dpi=300",
        data={
            "plate_name": "INK_01",
            "action": "erase",
            "polygon": json.dumps([[0, 0], [15, 0], [15, 15], [0, 15]]),
        },
        files={"file": ("sample.png", png_data, "image/png")},
    )
    assert resp_spot.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_spot.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        spot_plate = next(p for p in manifest["plates"] if p["name"] == "INK_01")
        assert spot_plate["type"] == "spot"
        cov_frac = spot_plate["coverage_percent"] / 100.0
        expected_g = calculate_theoretical_ink_estimate(64, 48, 300, cov_frac, "spot")
        assert spot_plate["estimated_grams_per_100_prints"] == expected_g
        csv_text = archive.read("reports/plate_summary.csv").decode("utf-8-sig")
        assert str(expected_g) in csv_text

    # 3. Tonal plate region-edit (tonal rate = 18.0 g/m²)
    resp_tonal = client.post(
        "/api/separation/region-edit?strategy=hybrid&max_inks=4&dpi=300",
        data={
            "plate_name": "TONAL_01",
            "action": "erase",
            "polygon": json.dumps([[0, 0], [10, 0], [10, 10], [0, 10]]),
        },
        files={"file": ("sample.png", png_data, "image/png")},
    )
    assert resp_tonal.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_tonal.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        tonal_plate = next(p for p in manifest["plates"] if p["name"] == "TONAL_01")
        assert tonal_plate["type"] == "tonal"
        cov_frac = tonal_plate["coverage_percent"] / 100.0
        expected_g = calculate_theoretical_ink_estimate(64, 48, 300, cov_frac, "tonal")
        assert tonal_plate["estimated_grams_per_100_prints"] == expected_g
        assert tonal_plate["mesh_recommendation"] == "200-230 mesh (halftone screen)"
        csv_text = archive.read("reports/plate_summary.csv").decode("utf-8-sig")
        assert str(expected_g) in csv_text


def test_plate_ink_estimate_unknown_type_handling():
    # If a plate has an unknown or missing type, estimate is unavailable rather than silently applying spot rate
    assert calculate_theoretical_ink_estimate(600, 400, 300, 0.5, "custom_metallic") is None
    assert calculate_theoretical_ink_estimate(600, 400, 300, 0.5, None) is None

    plate_entries = [
        {"name": "METALLIC_01", "type": "custom_metallic", "hex": "#D4AF37", "filename": "plates/METALLIC_01.png", "coverage_percent": 25.0},
        {"name": "NO_TYPE_01", "type": None, "hex": "#000000", "filename": "plates/NO_TYPE_01.png", "coverage_percent": 10.0},
    ]
    for p in plate_entries:
        ptype = p.get("type")
        grams = calculate_theoretical_ink_estimate(600, 400, 300, p["coverage_percent"] / 100.0, ptype)
        if grams is not None:
            p["estimated_grams_per_100_prints"] = grams
        else:
            p["estimated_grams_per_100_prints"] = None
            p["estimated_grams_per_100_prints_status"] = "unavailable"

    assert plate_entries[0]["estimated_grams_per_100_prints"] is None
    assert plate_entries[0]["estimated_grams_per_100_prints_status"] == "unavailable"
    assert plate_entries[1]["estimated_grams_per_100_prints"] is None
    assert plate_entries[1]["estimated_grams_per_100_prints_status"] == "unavailable"

    # Verify CSV output marks it as unavailable
    from app.separation import _plate_report_csv
    csv_bytes = _plate_report_csv(plate_entries)
    csv_str = csv_bytes.decode("utf-8-sig")
    assert "METALLIC_01,custom_metallic,#D4AF37" in csv_str
    assert "unavailable" in csv_str


def test_batch_separation_edge_cases_and_limits():
    # 1. More than 10 files returns 400
    png_data = make_png()
    files_11 = [("files", (f"design_{i}.png", png_data, "image/png")) for i in range(11)]
    resp_11 = client.post("/api/separation/batch", files=files_11)
    assert resp_11.status_code == 400
    assert "Batch limit is 10 designs" in resp_11.json()["detail"]

    # 2. Valid batch creates proper structure, plate PNGs, and manifests
    files_2 = [
        ("files", ("floral_motif.png", png_data, "image/png")),
        ("files", ("geometric_repeat.png", png_data, "image/png")),
    ]
    resp_valid = client.post(
        "/api/separation/batch?strategy=spot&max_inks=3&dpi=300",
        files=files_2,
    )
    assert resp_valid.status_code == 200
    with zipfile.ZipFile(BytesIO(resp_valid.content)) as archive:
        names = archive.namelist()
        # Per design folders exist
        assert any(n.startswith("design_01_floral_motif/") for n in names)
        assert any(n.startswith("design_02_geometric_repeat/") for n in names)
        # Manifests and plate files exist
        assert "design_01_floral_motif/manifest.json" in names
        assert "design_01_floral_motif/reports/plate_summary.csv" in names
        assert any(n.startswith("design_01_floral_motif/plates/") and n.endswith(".png") for n in names)
        # Summary CSV exists and contains headers and both designs
        summary_csv = archive.read("batch_summary.csv").decode("utf-8-sig")
        assert "floral_motif.png" in summary_csv
        assert "geometric_repeat.png" in summary_csv
        assert "design_01_floral_motif" in summary_csv







