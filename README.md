# LoomLab Studio

LoomLab is a local-first textile design and prepress studio. It supports non-destructive image import, perceptual palette extraction and reduction, editable color mappings, printable spot-color separations, repeat previews, seam checks, exports, and portable `.textileproj` projects.

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite (normally `http://localhost:5173`).

## Architecture

- `backend/app/color_engine`: LAB-aware palette analysis, quantization, and mappings
- `backend/app/separation_engine`: individual printable masks and compositing
- `backend/app/repeat_engine`: repeat composition and edge-discontinuity scoring
- `backend/app/project_engine`: portable project serialization
- `frontend/src`: React workspace, tool panels, and canvas previews

The `ai/` service contract is deliberately independent of the UI and image engine, ready for a local or hosted generator adapter later.

## Tests

```powershell
cd backend
pytest
```

RGB-to-CMYK previews are intentionally approximate. Production ICC transforms should be connected through the export engine before press output.
