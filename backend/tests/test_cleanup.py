"""The working cache's cleanup (store.cleanup_expired): everything ages out
after CLEANUP_EXPIRY_HOURS, except an auto job still waiting on a decision
(sent to the client, or held for the operator), kept up to PENDING_EXPIRY_HOURS
so a late Approve still finds its films (R-0005 #3)."""
import json
import os
import time

import pytest

from app.core import store

IDS = iter(f"{n:032x}" for n in range(1, 10_000))


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    return tmp_path


def _age(path, hours):
    then = time.time() - hours * 3600
    os.utime(path, (then, then))


def _job(root, hours, stage="sent", status="auto_ok", trial=False):
    """An auto job's report, zip, proof image (+ its screen copy) and one screen, all `hours` old."""
    job, reduced, mask = next(IDS), next(IDS), next(IDS)
    files = [root / f"auto-{job}.json", root / f"auto-{job}.zip", root / f"{reduced}.png",
             root / f"{reduced}.s2400.png", root / f"{mask}.png"]
    files[0].write_text(json.dumps({"job_id": job, "stage": stage, "status": status, "trial": trial,
                                    "reduced_id": reduced, "layers": [{"id": mask, "color": "#000000"}]}))
    for f in files[1:]:
        f.write_bytes(b"x")
    for f in files:
        _age(f, hours)
    return files


def test_a_job_whose_proof_is_with_the_client_outlives_the_48h_cache(cache):
    sent = _job(cache, 72, stage="sent")
    stray = cache / f"{next(IDS)}.png"; stray.write_bytes(b"x"); _age(stray, 72)
    store.cleanup_expired()
    assert all(f.exists() for f in sent)
    assert not stray.exists()                    # everything else still ages out


def test_a_job_held_for_the_operator_is_kept_too(cache):
    held = _job(cache, 72, stage="new", status="needs_review")
    store.cleanup_expired()
    assert all(f.exists() for f in held)


@pytest.mark.parametrize("stage,status,trial", [("new", "auto_ok", False), ("approved", "auto_ok", False),
                                                ("rejected", "auto_ok", False), ("changed", "auto_ok", False),
                                                ("new", "needs_review", True)])
def test_a_decided_or_unsent_job_still_ages_out_at_48h(cache, stage, status, trial):
    files = _job(cache, 49, stage=stage, status=status, trial=trial)
    store.cleanup_expired()
    assert not any(f.exists() for f in files)


def test_a_job_nobody_answers_goes_after_the_longer_cap(cache, monkeypatch):
    monkeypatch.setattr(store, "PENDING_EXPIRY_HOURS", 24 * 30)
    old = _job(cache, 24 * 31, stage="sent")
    young = _job(cache, 24 * 29, stage="sent")
    store.cleanup_expired()
    assert not any(f.exists() for f in old)
    assert all(f.exists() for f in young)


def test_a_fresh_job_is_never_touched_and_a_broken_report_keeps_nothing(cache):
    fresh = _job(cache, 1, stage="new")
    broken = _job(cache, 72, stage="sent")
    broken[0].write_text("{not json"); _age(broken[0], 72)
    store.cleanup_expired()
    assert all(f.exists() for f in fresh)
    assert not any(f.exists() for f in broken)
