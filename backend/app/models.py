from pydantic import BaseModel, Field

class Color(BaseModel):
    hex: str
    rgb: list[int]
    pixels: int = 0
    coverage: float = 0

class ReduceRequest(BaseModel):
    image_id: str
    colors: int = Field(6, ge=2, le=20)

class RemapRequest(BaseModel):
    """Recolour or merge a palette colour: every pixel within `threshold`
    of `source` (in perceptual LAB) is repainted `target`. Recolour uses a
    new hex as target; merge uses another existing swatch as target."""
    image_id: str
    source: str
    target: str
    # The reduced image is already flat, so a source ink's pixels sit exactly
    # on its colour. A tight threshold repaints only that one ink and never
    # bleeds into a different-but-similar ink the operator wants kept apart.
    threshold: float = Field(6, ge=1, le=100)

class AccuracyRequest(BaseModel):
    image_id: str
    palette: list[str]

class SeparationRequest(BaseModel):
    image_id: str
    palette: list[str]
    cleanup: int = Field(0, ge=0, le=5)

class PackageLayer(BaseModel):
    id: str
    name: str
    color: str = '#000000'

class PackageRequest(BaseModel):
    """One production package: a colour PNG plate and a print-ready TIFF
    screen (300 DPI, with registration marks) for every ink, plus a colour
    proof — all in a single zip a mill can hand to the press."""
    layers: list[PackageLayer]
    dpi: int = Field(300, ge=72, le=1200)
    reg_marks: bool = True
    composite_image_id: str | None = None
