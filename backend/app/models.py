from typing import Annotated
from pydantic import BaseModel, Field

# Colours arrive from the client as hex. Validating the shape here turns a
# typo into a clean 422 instead of a 500 deep inside the colour maths.
HexColor = Annotated[str, Field(pattern=r'^#?[0-9a-fA-F]{6}$')]
# An id we minted (uuid4 hex); anything else can never name a stored image.
ImageId = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
MAX_INKS = 64          # the UI tops out at 20; this is a sane hard ceiling

class Color(BaseModel):
    hex: str
    rgb: list[int]
    pixels: int = 0
    coverage: float = 0

class ReduceRequest(BaseModel):
    image_id: ImageId
    colors: int = Field(6, ge=2, le=20)
    # 0 = keep every detail (clean vector art); 1 = light (default, flattens
    # brush/scan/fabric texture, keeps 2px+ lines); 2-3 = stronger for noisy scans.
    smoothing: int = Field(1, ge=0, le=3)

class RemapRequest(BaseModel):
    """Recolour or merge a palette colour: every pixel within `threshold`
    of `source` (in perceptual LAB) is repainted `target`. Recolour uses a
    new hex as target; merge uses another existing swatch as target."""
    image_id: ImageId
    source: HexColor
    target: HexColor
    # The reduced image is already flat, so a source ink's pixels sit exactly
    # on its colour. A tight threshold repaints only that one ink and never
    # bleeds into a different-but-similar ink the operator wants kept apart.
    threshold: float = Field(6, ge=1, le=100)

class ImageIdRequest(BaseModel):
    image_id: ImageId

class AccuracyRequest(BaseModel):
    image_id: ImageId
    palette: list[HexColor] = Field(min_length=0, max_length=MAX_INKS)

class SeparationRequest(BaseModel):
    image_id: ImageId
    palette: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)
    cleanup: int = Field(0, ge=0, le=5)

class PackageLayer(BaseModel):
    id: ImageId
    name: str = Field('Ink', max_length=120)
    color: HexColor = '#000000'

class PreviewLayer(BaseModel):
    id: ImageId
    color: HexColor = '#000000'

class PreviewRequest(BaseModel):
    """The enabled ink screens, back to front. Composited over `fabric` to show
    exactly what will print."""
    layers: list[PreviewLayer] = Field(min_length=1, max_length=MAX_INKS)
    fabric: HexColor = '#FFFFFF'

class PackageRequest(BaseModel):
    """One production package: a colour PNG plate and a print-ready TIFF
    screen (300 DPI, with registration marks) for every ink, plus a colour
    proof — all in a single zip a mill can hand to the press."""
    layers: list[PackageLayer] = Field(min_length=1, max_length=MAX_INKS)
    dpi: int = Field(300, ge=72, le=1200)
    reg_marks: bool = True
    composite_image_id: ImageId | None = None
    vector: bool = False   # also include scalable SVG outlines in the package

class SvgExportRequest(BaseModel):
    layers: list[PackageLayer] = Field(min_length=1, max_length=MAX_INKS)
    simplify: float = Field(1.0, ge=0, le=8)
    smooth: int = Field(0, ge=0, le=4)
    min_area: float = Field(8, ge=0, le=5000)
