"""Licence status and activation (the gate itself is middleware in main.py)."""
from fastapi import APIRouter, HTTPException
from ..models import *
from .. import licence

router = APIRouter()


@router.get('/api/licence')
def licence_status():
    """Whether this PC needs a licence, and whether it has a valid one."""
    return licence.status()


@router.post('/api/licence')
def licence_activate(req: LicenceRequest):
    """Activate this PC with a licence key issued for its machine code."""
    result = licence.activate(req.key)
    if not result['valid']:
        raise HTTPException(422, result['reason'])
    return result
