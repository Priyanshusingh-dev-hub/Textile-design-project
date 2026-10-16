from typing import Literal
from pydantic import BaseModel, Field

Strategy = Literal["spot", "halftone", "hybrid"]

class AnalysisReport(BaseModel):
    width: int
    height: int
    estimated_unique_rgb: int
    mean_luminance: float
    luminance_stddev: float
    gradient_score: float
    edge_score: float
    warnings: list[str] = []

class SeparationSettings(BaseModel):
    strategy: Strategy = "hybrid"
    max_inks: int = Field(default=8, ge=1, le=32)
    lpi: int = Field(default=45, ge=10, le=100)
    dpi: int = Field(default=300, ge=72, le=2400)
    preserve_tones: bool = True
    user_override: bool = False
