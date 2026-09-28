"""Settings the owner changes in the app instead of Notepad: the rate card
(quote prices) and auto mode's limits. Both are checked before they are
saved, and the files are read on every quote/job, so a change needs no restart."""
from fastapi import APIRouter, Body, HTTPException
from .. import auto as auto_mode
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
