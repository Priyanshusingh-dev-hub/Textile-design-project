from PIL import Image
from app import main as api


def test_empty_layer_composite_preserves_source_dimensions(monkeypatch):
    source = Image.new("RGBA", (37, 23), (255, 0, 0, 255))
    saved = {}

    def save(image):
        saved["image"] = image
        return "composite-id"

    monkeypatch.setattr(api.store, "load", lambda image_id: source)
    monkeypatch.setattr(api.store, "save", save)

    result = api.composite_layers(api.LayerCompositeRequest(layers=[], image_id="source-id"))

    assert result["width"] == 37
    assert result["height"] == 23
    assert saved["image"].size == (37, 23)
    assert saved["image"].getchannel("A").getbbox() is None
