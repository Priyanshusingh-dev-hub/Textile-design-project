# TextileAI Hybrid Separation Engine — Architecture Pack

Reference scaffold for textile screen-printing workflows supporting spot-ink channels, tonal coverage maps, halftone plates, hybrid strategies, analysis-first planning, user overrides, and stable plate numbering after commit.

## Quick start
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

## Core principles
1. Never overwrite source pixels.
2. Colour similarity analysis is separate from destructive colour merging.
3. Evaluate candidates before final plate IDs are assigned.
4. Keep ink identity separate from tonal coverage and plate raster.
5. User-selected settings override recommendations.
6. AI may recommend; deterministic code owns masks, pixels and validation.

This is a starter scaffold, not a production-certified RIP. Calibrated ink mixing, ICC proofing, trapping, underbase generation and press-specific screening still require implementation and print-shop validation.
