from typing import Literal
from pydantic import BaseModel, Field

Strategy = Literal["spot", "halftone", "hybrid"]

class AnalysisRequest(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    # Prototype receives an already decoded RGB array in engine tests.
    target_dpi: int = Field(default=300, ge=72, le=2400)
    max_inks: int = Field(default=8, ge=1, le=32)

class AnalysisReport(BaseModel):
    width: int
    height: int
    estimated_unique_rgb: int
    mean_luminance: float
    luminance_stddev: float
    gradient_score: float
    edge_score: float
    is_seamless_repeat: bool = False
    horizontal_seam_delta: float = 0.0
    vertical_seam_delta: float = 0.0
    horizontal_seam_p95: float = 0.0
    vertical_seam_p95: float = 0.0
    horizontal_seam_max: float = 0.0
    vertical_seam_max: float = 0.0
    warnings: list[str] = Field(default_factory=list)

class SeparationSettings(BaseModel):
    strategy: Strategy = "hybrid"
    max_inks: int = Field(default=8, ge=1, le=32)
    lpi: int = Field(default=45, ge=10, le=100)
    dpi: int = Field(default=300, ge=72, le=2400)
    preserve_tones: bool = True
    user_override: bool = False
    merge_threshold: float = Field(default=0.0, ge=0.0, le=30.0)
    generate_underbase: bool = False
    underbase_choke_px: int = Field(default=1, ge=0, le=10)
    apply_trapping: bool = False
    trap_px: int = Field(default=1, ge=1, le=5)
    include_registration_marks: bool = False
    film_margin_px: int = Field(default=40, ge=20, le=120)
    min_feature_px: int = Field(default=0, ge=0, le=20)

class Candidate(BaseModel):
    strategy: Strategy
    estimated_plates: int
    rationale: str
    caveats: list[str] = Field(default_factory=list)

class PlanResponse(BaseModel):
    recommendation: Strategy
    candidates: list[Candidate]
    needs_user_confirmation: bool = True

class PlateMetadata(BaseModel):
    plate_id: str
    ink_id: str
    strategy: Strategy
    channel_type: Literal["spot", "tonal", "underbase"]
    width: int
    height: int
    dpi: int
    lpi: int | None = None

