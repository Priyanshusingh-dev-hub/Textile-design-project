"""Shared: the old results. reference_code/method1_colorfill.py (the user's
tested script), unchanged, run once per test session on the samples."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'tests' / 'samples'
TAG = '3535px_300dpi'
RUNS = {  # how each sample was run with method1 (and what it gave)
    'floral': (['--line', 'floral_lineart.png', '--ref', 'floral_ref.png'], 9),
    'star': (['--line', 'star_lineart.png', '--ref', 'star_ref.png', '--max-colors', '6', '--line-color', '120F06'], 6),
}

@pytest.fixture(scope='session')
def reference(tmp_path_factory):
    """method1_colorfill.py, unchanged, on each sample: the old results."""
    out = {}
    for name, (args, _) in RUNS.items():
        d = tmp_path_factory.mktemp(f'ref_{name}')
        cmd = [sys.executable, '-W', 'ignore', str(ROOT / 'reference_code' / 'method1_colorfill.py'),
               *[str(SAMPLES / a) if a.endswith('.png') else a for a in args], '--out', str(d), '--name', name]
        subprocess.run(cmd, check=True, capture_output=True)
        out[name] = d
    return out


