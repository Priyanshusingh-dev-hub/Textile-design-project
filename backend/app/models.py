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
    colors: int = Field(6, ge=1, le=20)   # a one-colour design is one screen
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
    # bleeds into a different-but-similar ink the operator wants kept apart —
    # reduce keeps inks as close as dE 3, so anything wider could take a
    # neighbour with it.
    threshold: float = Field(1, ge=0.5, le=100)

class ImageIdRequest(BaseModel):
    image_id: ImageId

class ImagesExistRequest(BaseModel):
    # a saved job's images: the upload, the reduced design, undo steps, masks
    ids: list[ImageId] = Field(max_length=300)

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

class LiveMasksRequest(BaseModel):
    """Small copies of the screens, for recolouring live in the browser."""
    ids: list[ImageId] = Field(min_length=1, max_length=MAX_INKS)
    max_side: int = Field(1600, ge=256, le=2400)


class PreviewRequest(BaseModel):
    """The enabled ink screens, back to front. Composited over `fabric` to show
    exactly what will print."""
    layers: list[PreviewLayer] = Field(min_length=1, max_length=MAX_INKS)
    fabric: HexColor = '#FFFFFF'
    # set for a display thumbnail (e.g. a plate chip after its ink is recoloured):
    # rendered small instead of at full print resolution
    thumb: bool = False
    # How wide the design should print, in inches. Unset = its own size (the
    # file's pixels at `dpi`, output exactly as separated). Set wider and the
    # screens are redrawn at that size with smooth edges, still one ink per
    # pixel. Height follows the design's proportions.
    width_in: float | None = Field(None, gt=0, le=200)
    dpi: int = Field(300, ge=72, le=1200)
    # dots smaller than this (mm across, at the print size) are given to the
    # ink around them; 0 = off, the screens exactly as separated
    min_dot_mm: float = Field(0, ge=0, le=1)
    # For the screen: the proof no bigger than this on its longer side. A
    # 30-inch design is 61 MP, which a browser shows as an empty box. The
    # package always draws its own full-size proof.
    max_side: int | None = Field(None, ge=256, le=20000)


class SpeckRequest(PreviewRequest):
    """How many dots on each screen are too small for the mesh to hold."""
    min_dot_mm: float = Field(0.2, gt=0, le=1)

class PackageRequest(BaseModel):
    """One production package: a colour PNG plate and a print-ready TIFF
    screen (300 DPI, with registration marks) for every ink, plus a colour
    proof — all in a single zip a mill can hand to the press."""
    layers: list[PackageLayer] = Field(min_length=1, max_length=MAX_INKS)
    dpi: int = Field(300, ge=72, le=1200)
    reg_marks: bool = True
    # How wide the design should print, in inches. Unset = its own size (the
    # file's pixels at `dpi`, output exactly as separated). Set wider and the
    # screens are redrawn at that size with smooth edges, still one ink per
    # pixel. Height follows the design's proportions.
    width_in: float | None = Field(None, gt=0, le=200)
    composite_image_id: ImageId | None = None
    vector: bool = False   # also include scalable SVG outlines in the package
    # Trap, in film pixels: each ink spread this far under the darker inks it
    # touches, so a slipping screen leaves no line of bare cloth. 0 = off (the
    # films are exactly the separation, one ink per pixel).
    trap_px: int = Field(0, ge=0, le=3)
    # Tiny dots: islands smaller than this many mm across (at the print size)
    # go to the ink around them — a screen can't hold them. 0 = off.
    min_dot_mm: float = Field(0, ge=0, le=1)
    fabric: HexColor = '#FFFFFF'   # the cloth being printed on
    # On non-white cloth an ink goes muddy without a white base under it, so
    # optionally emit that extra screen (printed first, choked to sit under the
    # colours). The colour plates remain mutually exclusive regardless.
    underbase: bool = False
    underbase_choke: int = Field(1, ge=0, le=4)

class SvgExportRequest(BaseModel):
    layers: list[PackageLayer] = Field(min_length=1, max_length=MAX_INKS)
    simplify: float = Field(1.0, ge=0, le=8)
    smooth: int = Field(0, ge=0, le=4)
    min_area: float = Field(6.0, ge=0, le=5000)   # = the package default, so both SVGs match
    width_in: float | None = Field(None, gt=0, le=200)   # print width: sets the SVG's physical size
    dpi: int = Field(300, ge=72, le=1200)


class SmallInksRequest(BaseModel):
    """Which inks cover under `below`% of the reduced design, and what
    dropping them would cost."""
    image_id: ImageId           # the reduced design
    source_id: ImageId          # the original it was reduced from
    palette: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)
    below: float = Field(2.0, gt=0, le=10)
    locked: list[HexColor] = Field(default_factory=list, max_length=MAX_INKS)


class DropInksRequest(BaseModel):
    """Remove inks from the reduced design: each of their pixels goes to the
    remaining ink closest to its original colour."""
    image_id: ImageId
    source_id: ImageId
    palette: list[HexColor] = Field(min_length=2, max_length=MAX_INKS)
    drop: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)


class LibraryInk(BaseModel):
    """One ink the mill has mixed and on the shelf."""
    name: str = Field(min_length=1, max_length=60)
    hex: HexColor


class InkLibraryRequest(BaseModel):
    inks: list[LibraryInk] = Field(default_factory=list, max_length=500)


class InkMatchRequest(BaseModel):
    palette: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)


class RepaintRequest(BaseModel):
    """Recolour every ink of a reduced design at once: palette[i] -> targets[i]."""
    image_id: ImageId
    palette: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)
    targets: list[HexColor] = Field(min_length=1, max_length=MAX_INKS)
