"""Settings the owner changes in the app instead of Notepad: the rate card
(quote prices) and auto mode's limits. Both are checked before they are
saved, and the files are read on every quote/job, so a change needs no restart."""
from datetime import datetime
from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from .. import auto as auto_mode
from ..core import backup as backups
from ..core import quote as costing

router = APIRouter()


def _read(load, defaults):
    try:
        return {'values': load(), 'error': None}
    except ValueError as e:   # shown on the screen, with the defaults to start from
        return {'values': dict(defaults), 'error': str(e)}


@router.get('/api/settings')
def settings():
    """The rate card and auto mode's limits, with the warning codes a job can raise."""
    return {'rate_card': _read(costing.load_card, costing.DEFAULTS),
            'auto': _read(auto_mode.load_config, auto_mode.DEFAULTS) | {'codes': auto_mode.TITLES}}


@router.put('/api/settings/rate-card')
def save_rate_card(values: dict = Body(...)):
    try:
        return costing.save_card(values)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put('/api/settings/auto')
def save_auto(values: dict = Body(...)):
    try:
        return auto_mode.save_config(values)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get('/api/backup')
def backup():
    """Everything the mill has built up (library with films, job log, shelf
    inks, rate card, auto limits) as one zip, to keep somewhere safe."""
    path = backups.temp_path()
    try:
        backups.make(path)
    except BaseException:
        path.unlink(missing_ok=True)       # never leave a half-written multi-GB zip in %TEMP%
        raise
    name =f'loomlab-backup-{datetime.now():%Y-%m-%d}.zip'
    return FileResponse(path, media_type='application/zip', filename=name,
                        background=BackgroundTask(path.unlink, missing_ok=True))


@router.post('/api/backup/restore')
def restore(file: UploadFile = File(...)):
    """Put a backup back (e.g. on a new PC). Every part is checked before
    anything is written; what is there already is replaced or, for the job
    log, added to."""
    try:
        return backups.restore(file.file)
    except ValueError as e:
        raise HTTPException(422, str(e))
