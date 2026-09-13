from pydantic import BaseModel, Field
from typing import Literal

class Color(BaseModel):
    hex: str
    rgb: list[int]
    pixels: int = 0
    coverage: float = 0

class AnalyzeRequest(BaseModel): image_id: str; colors: int = Field(6, ge=2, le=32)
class ReduceRequest(AnalyzeRequest): pass
class MapItem(BaseModel): source: str; target: str; enabled: bool = True
class MapRequest(BaseModel): image_id: str; mappings: list[MapItem]
class MergeRequest(BaseModel): image_id: str; sources: list[str]; target: str; threshold: float = Field(20, ge=1, le=100)
class SeparationRequest(BaseModel): image_id: str; palette: list[str]; mode: Literal['flat','gradient'] = 'flat'
class RepeatRequest(BaseModel):
    image_id: str; columns: int = Field(4, ge=1, le=12); rows: int = Field(3, ge=1, le=12)
    mode: Literal['grid','half-drop','brick','mirror'] = 'grid'; offset_x: int = 0; offset_y: int = 0
class ExportRequest(BaseModel): image_id: str; format: Literal['png','jpg','webp','psd'] = 'png'; dpi: int = Field(300, ge=72, le=1200)
class CompositeRequest(BaseModel): image_id: str; palette: list[str]
class LayerCompositeItem(BaseModel): id: str; color: str; opacity: float = Field(100, ge=0, le=100)
class LayerCompositeRequest(BaseModel): layers: list[LayerCompositeItem]
class ProjectData(BaseModel): version: int = 1; image_id: str | None = None; palette: list[str] = []; mappings: list[MapItem] = []; repeat: dict = {}; canvas: dict = {}
class ProjectLoadRequest(BaseModel): image_id: str
class ZipLayerItem(BaseModel): id: str; name: str
class ZipExportRequest(BaseModel): layers: list[ZipLayerItem]; composite_image_id: str | None = None
class HalftoneRequest(BaseModel): image_id: str; cell_size: int = Field(8, ge=2, le=64); angle: float = Field(45, ge=0, le=180)
