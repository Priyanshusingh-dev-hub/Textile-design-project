from typing import Annotated, Literal
from pydantic import AfterValidator, BaseModel, Field

# '#RRGGBB' (leading '#' optional on input, always present after validation)
# -- checked here so a malformed colour is a clear 422 instead of a crash deep
# inside an engine, and so nothing unescaped ever reaches an SVG attribute.
Hex = Annotated[str, Field(pattern=r'^#?[0-9A-Fa-f]{6}$'), AfterValidator(lambda v: '#' + v.lstrip('#'))]
Palette = Annotated[list[Hex], Field(min_length=1, max_length=32)]

class Color(BaseModel):
    hex: Hex
    rgb: list[int]
    pixels: int = 0
    coverage: float = 0

class AnalyzeRequest(BaseModel): image_id: str; colors: int = Field(6, ge=2, le=20)
class ReduceRequest(AnalyzeRequest):
    region: bool = False
    edge_strength: float = Field(12, ge=2, le=60)
    min_region: int = Field(40, ge=0, le=5000)
class MapItem(BaseModel): source: Hex; target: Hex; enabled: bool = True
class MapRequest(BaseModel): image_id: str; mappings: list[MapItem]; threshold: float = Field(10, ge=1, le=100)
class MergeRequest(BaseModel): image_id: str; sources: list[Hex]; target: Hex; threshold: float = Field(20, ge=1, le=100)
class SeparationRequest(BaseModel):
    image_id: str; palette: Palette; mode: Literal['flat','gradient','region'] = 'flat'; cleanup: int = Field(2, ge=0, le=5)
    edge_strength: float = Field(12, ge=2, le=60); min_region: int = Field(40, ge=0, le=5000)
class RepeatRequest(BaseModel):
    image_id: str; columns: int = Field(4, ge=1, le=12); rows: int = Field(3, ge=1, le=12)
    mode: Literal['grid','half-drop','brick','mirror'] = 'grid'; offset_x: int = 0; offset_y: int = 0
class ExportRequest(BaseModel): image_id: str; format: Literal['png','jpg','webp','psd'] = 'png'; dpi: int = Field(300, ge=72, le=1200)
class CompositeRequest(BaseModel): image_id: str; palette: Palette
class LayerCompositeItem(BaseModel): id: str; color: Hex; opacity: float = Field(100, ge=0, le=100)
class LayerCompositeRequest(BaseModel): layers: list[LayerCompositeItem]
class ZipLayerItem(BaseModel): id: str; name: str; color: Hex | None = None
class ZipExportRequest(BaseModel): layers: list[ZipLayerItem]; composite_image_id: str | None = None; content: Literal['mask','film','plate'] = 'mask'; format: Literal['png','tiff'] = 'png'; dpi: int = Field(300, ge=72, le=1200); reg_marks: bool = False
class HalftoneRequest(BaseModel): image_id: str; cell_size: int = Field(8, ge=2, le=64); angle: float = Field(45, ge=0, le=180)
class SvgExportRequest(BaseModel):
    layers: list[ZipLayerItem]
    blur: float = Field(1.5, ge=0, le=6)
    simplify: float = Field(0.8, ge=0, le=5)
    corner_angle: float = Field(32, ge=5, le=90)
    min_area: float = Field(20, ge=0, le=2000)
    per_layer: bool = False
class DnaRequest(BaseModel): image_id: str; description: str = ''
class InstructionRequest(BaseModel):
    image_id: str
    intent: Literal['exact_recreation','premium_improvement','color_change','new_variation','same_style_new','print_optimization'] = 'premium_improvement'
    fidelity: int = Field(85, ge=0, le=100)
    user_request: str = ''
    description: str = ''
    target_colors: int | None = Field(None, ge=1, le=32)
class ProjectLayer(BaseModel):
    id: str; name: str = Field('Ink', max_length=200); color: Hex; coverage: float = 0
    visible: bool = True; opacity: float = Field(100, ge=0, le=100)
class ProjectExportRequest(BaseModel):
    name: str = Field('loomlab-project', max_length=200)
    original_id: str | None = None
    image_id: str | None = None
    palette: list[Color] = Field([], max_length=32)
    layers: list[ProjectLayer] = Field([], max_length=64)
    settings: dict = {}
