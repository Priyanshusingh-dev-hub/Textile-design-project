"""The working cache's cleanup (store.cleanup_expired): everything ages out
after CLEANUP_EXPIRY_HOURS, except an auto job still waiting on a decision
(sent to the client, or held by the bot for the mill), kept up to
PENDING_EXPIRY_HOURS counted from when it was sent / held, so a late Approve
still finds its films (R-0005 #3, R-0013 H2 / M3)."""
import json
import os
import time
from datetime import datetime

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


def _at(hours):
    """A naive local timestamp `hours` ago, as the engine writes them."""
    return datetime.fromtimestamp(time.time() - hours * 3600).isoformat(timespec="seconds")


def _job(root, hours, stage="sent", status="auto_ok", trial=False, held=False, waiting=None):
    """An auto job's report, zip, proof image (+ its screen copy) and one screen, all `hours` old;
    its stage (or the bot's hold) written `waiting` hours ago (default: `hours`)."""
    job, reduced, mask = next(IDS), next(IDS), next(IDS)
    files = [root / f"auto-{job}.json", root / f"auto-{job}.zip", root / f"{reduced}.png",
             root / f"{reduced}.s2400.png", root / f"{mask}.png"]
    when = _at(hours if waiting is None else waiting)
    report = {"job_id": job, "stage": stage, "status": status, "trial": trial, "reduced_id": reduced,
              "layers": [{"id": mask, "color": "#000000"}],
              "history": [] if stage == "new" else [{"stage": stage, "by": "bot", "note": "", "at": when}]}
    if held:
        report["held"] = {"why": "no_operator", "by": "bot", "at": when}
    files[0].write_text(json.dumps(report))
    for f in files[1:]:
        f.write_bytes(b"x")
    for f in files:
        _age(f, hours)
    return files


def test_the_default_cap_is_fourteen_days():
    assert store.PENDING_EXPIRY_HOURS == 336     # conftest does not set PENDING_EXPIRY_HOURS


def test_a_job_whose_proof_is_with_the_client_outlives_the_48h_cache(cache):
    sent = _job(cache, 72, stage="sent")
    stray = cache / f"{next(IDS)}.png"; stray.write_bytes(b"x"); _age(stray, 72)
    store.cleanup_expired()
    assert all(f.exists() for f in sent)
    assert not stray.exists()                    # everything else still ages out


@pytest.mark.parametrize("status", ["needs_review", "auto_ok"])
def test_a_job_the_bot_holds_is_kept_whatever_auto_mode_said(cache, status):
    """H2: OPERATOR= empty holds even an auto_ok job; the hold marker is what counts."""
    held = _job(cache, 72, stage="new", status=status, held=True)
    store.cleanup_expired()
    assert all(f.exists() for f in held)


@pytest.mark.parametrize("stage,status,trial,held", [
    ("new", "auto_ok", False, False), ("approved", "auto_ok", False, False), ("rejected", "auto_ok", False, False),
    ("changed", "auto_ok", False, False), ("expired", "auto_ok", False, False),
    ("new", "needs_review", False, False),        # M3: an app / hot-folder job nobody acted on is not held
    ("new", "needs_review", True, True)])         # a trial never is
def test_a_decided_unsent_or_unheld_job_still_ages_out_at_48h(cache, stage, status, trial, held):
    files = _job(cache, 49, stage=stage, status=status, trial=trial, held=held)
    store.cleanup_expired()
    assert not any(f.exists() for f in files)


def test_a_job_nobody_answers_goes_after_the_cap(cache):
    old = _job(cache, 24 * 15, stage="sent")
    young = _job(cache, 24 * 13, stage="sent")
    old_held = _job(cache, 24 * 15, stage="new", held=True)
    store.cleanup_expired()
    assert not any(f.exists() for f in old + old_held)
    assert all(f.exists() for f in young)


def test_the_cap_counts_from_when_it_was_sent_not_the_last_write(cache):
    """M3: a later write to the report (a colourway made from it) does not restart the clock."""
    touched = _job(cache, 24 * 15, stage="sent")
    _age(touched[0], 1)                            # report rewritten an hour ago; sent 15 days ago
    store.cleanup_expired()
    assert not any(f.exists() for f in touched[1:])


def test_a_report_without_a_readable_time_falls_back_to_its_mtime(cache):
    files = _job(cache, 72, stage="sent")
    r = json.loads(files[0].read_text()); r["history"] = [{"stage": "sent", "at": "yesterday-ish"}]
    files[0].write_text(json.dumps(r)); _age(files[0], 72)
    store.cleanup_expired()
    assert all(f.exists() for f in files)          # 72 h < 14 days by mtime


def test_the_cap_can_be_set_per_pc(cache, monkeypatch):
    monkeypatch.setattr(store, "PENDING_EXPIRY_HOURS", 24 * 3)
    files = _job(cache, 24 * 4, stage="sent")
    store.cleanup_expired()
    assert not any(f.exists() for f in files)


def test_a_fresh_job_is_never_touched_and_a_broken_report_keeps_nothing(cache):
    fresh = _job(cache, 1, stage="new")
    broken = _job(cache, 72, stage="sent")
    broken[0].write_text("{not json"); _age(broken[0], 72)
    store.cleanup_expired()
    assert all(f.exists() for f in fresh)
    assert not any(f.exists() for f in broken)
