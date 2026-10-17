"""The libraries every upload passes through must stay at or above the
releases that fixed their known advisories (pip-audit, Oct 2026): an old
virtualenv on a mill PC, or a pin moved back, fails here instead of quietly
running a vulnerable version."""
from importlib.metadata import version
from pathlib import Path

import pytest

FLOORS = {                     # package: first release with every known fix
    'pillow': (12, 3, 0),      # PSD out-of-bounds write, decompression bombs (PYSEC-2026-2249 ...)
    'python-multipart': (0, 0, 31),   # multipart parsing DoS (PYSEC-2026-3038/3039/3040 ...)
    'starlette': (1, 3, 1),    # FileResponse Range DoS, Host validation (PYSEC-2026-161/248/249 ...)
}


def _tuple(v: str) -> tuple:
    return tuple(int(p) for p in v.split('.')[:3] if p.isdigit())


@pytest.mark.parametrize('package, floor', FLOORS.items())
def test_installed_version_has_the_security_fixes(package, floor):
    assert _tuple(version(package)) >= floor, f'{package} {version(package)} is older than {floor}'


@pytest.mark.parametrize('package, floor', FLOORS.items())
def test_requirements_pin_has_the_security_fixes(package, floor):
    pins = {}
    for line in (Path(__file__).resolve().parents[1] / 'requirements.txt').read_text().splitlines():
        line = line.split('#')[0].strip()
        if '==' in line:
            name, _, v = line.partition('==')
            pins[name.split('[')[0].strip().lower()] = v.strip()
    assert package in pins, f'{package} is not pinned in backend/requirements.txt'
    assert _tuple(pins[package]) >= floor
