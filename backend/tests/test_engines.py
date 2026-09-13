import numpy as np
import pytest
from PIL import Image
from app.color_engine.engine import analyze, reduce, rgb_lab
from app.repeat_engine.engine import seam_score, create
from app.separation_engine.engine import composite_masks
from app.project_engine import engine as projects

def fixture(): return Image.new('RGB',(20,20),'#D84876')
def test_color_analysis(): assert len(analyze(fixture(),2)) == 2
def test_reduction(): assert reduce(fixture(),2).size == (20,20)
def test_lab_is_perceptual_shape(): assert rgb_lab(np.array([255,0,0])).shape == (3,)
def test_repeat_dimensions(): assert create(fixture(),3,2,'grid').size == (60,40)
def test_seam_score(): assert seam_score(fixture())['score'] == 0

def _full_mask():
    return Image.new('RGBA',(10,10),(0,0,0,255))

def test_opacity_changes_composite_output():
    """Fix 1: opacity must actually change the composited pixel values."""
    full = composite_masks([(_full_mask(),'#FF0000',100)], (10,10))
    half = composite_masks([(_full_mask(),'#FF0000',50)], (10,10))
    full_alpha = np.asarray(full)[:,:,3]
    half_alpha = np.asarray(half)[:,:,3]
    assert full_alpha.mean() == 255
    assert half_alpha.mean() == pytest.approx(127.5, abs=1)
    assert not np.array_equal(full_alpha, half_alpha)

def test_opacity_zero_is_fully_transparent():
    invisible = composite_masks([(_full_mask(),'#00FF00',0)], (10,10))
    assert np.asarray(invisible)[:,:,3].max() == 0

def test_project_save_then_load_round_trip(tmp_path, monkeypatch):
    """Fix 2: load must actually retrieve what save wrote, not echo input."""
    monkeypatch.setattr(projects, 'DATA_DIR', tmp_path)
    data = {'version':1,'image_id':'abc123','palette':['#FF0000','#00FF00'],
            'mappings':[],'repeat':{'mode':'brick'},'canvas':{}}
    projects.save(data)
    loaded = projects.load('abc123')
    assert loaded == data

def test_project_load_missing_raises():
    with pytest.raises(FileNotFoundError):
        projects.load('does-not-exist-xyz')
