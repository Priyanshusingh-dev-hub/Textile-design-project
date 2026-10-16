from fastapi import FastAPI, HTTPException
import numpy as np
from .models import AnalysisReport, SeparationSettings
from .analysis import analyze_rgb
from .separation import recommend_candidates, commit_plate_ids

app = FastAPI(title="TextileAI Hybrid Separation API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "service": "textileai-separation"}

@app.post("/api/analysis/demo", response_model=AnalysisReport)
def demo_analysis():
    sample = np.zeros((64, 64, 3), dtype=np.uint8)
    sample[:, :, 0] = np.tile(np.arange(64, dtype=np.uint8) * 4, (64, 1))
    return analyze_rgb(sample)

@app.post("/api/separation/candidates")
def candidates(gradient_score: float = 0.0, max_inks: int = 8):
    if not 0 <= gradient_score <= 1:
        raise HTTPException(400, "gradient_score must be between 0 and 1")
    if not 1 <= max_inks <= 32:
        raise HTTPException(400, "max_inks must be between 1 and 32")
    return recommend_candidates(gradient_score, max_inks)

@app.post("/api/separation/commit")
def commit(settings: SeparationSettings, ink_ids: list[str]):
    if len(ink_ids) > settings.max_inks:
        raise HTTPException(400, "Ink count exceeds max_inks")
    if len(set(ink_ids)) != len(ink_ids):
        raise HTTPException(400, "Ink IDs must be unique")
    return {"plates": commit_plate_ids(settings, ink_ids), "committed": True}
