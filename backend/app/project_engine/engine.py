import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / 'data'

def _path_for(image_id):
    return DATA_DIR / f'project-{image_id or "empty"}.textileproj'

def save(data):
    path=_path_for(data.get("image_id"))
    path.write_text(json.dumps(data,indent=2)); return path

def load(image_id):
    """Read a previously saved .textileproj file back from disk."""
    path=_path_for(image_id)
    if not path.exists():
        raise FileNotFoundError(f'No saved project found for image_id={image_id!r}.')
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f'Saved project file is corrupted: {e}')
