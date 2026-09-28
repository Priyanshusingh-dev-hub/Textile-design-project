"""Tests never touch the real working folder: without this every test run
left its auto-mode jobs in backend/data, and they showed up on the job
dashboard as real orders waiting for review."""
import os
import shutil
import tempfile

_DATA = tempfile.mkdtemp(prefix='loomlab-test-data-')
os.environ['DATA_DIR'] = _DATA   # read by app.core.store at import, so it is set before any test imports it


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_DATA, ignore_errors=True)
