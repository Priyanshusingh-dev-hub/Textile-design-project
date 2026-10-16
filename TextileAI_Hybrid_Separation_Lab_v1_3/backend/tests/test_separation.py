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
    perceptual_palette_map, _rgb_to_lab, render_plate_composite
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
    assert response.json()["version"] in ("1.3.0", "1.3.1")


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
    assert response.json()["version"] in ("1.3.0", "1.3.1")


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

