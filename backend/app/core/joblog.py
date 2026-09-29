"""Every auto job, kept for good: the working cache clears jobs after 48 h,
but a mill (and a pilot) needs the month — how many designs came, how many
went through with nobody, what was quoted, and roughly how much time that saved.

One CSV line per event (`made` when auto mode finishes a job, `stage` when
someone moves it on the dashboard or the bot does), in the data folder next
to the cache. Plain CSV so it also opens in Excel.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import store

FIELDS = ['time', 'event', 'job_id', 'name', 'client', 'status', 'stage', 'inks', 'accuracy', 'seconds',
          'width_in', 'meters', 'quote_total', 'currency', 'by', 'note']
_LOCK = threading.Lock()


def log_path() -> Path:
    return store.ROOT / 'job-log.csv'


def record(**event) -> None:
    """Append one event. Best effort by design: a full disk must never fail the job itself."""
    row = {k: event.get(k, '') for k in FIELDS}
    row['time'] = row['time'] or datetime.now().isoformat(timespec='seconds')
    path = log_path()
    try:
        with _LOCK:
            new = not path.exists()
            # utf-8-sig on a new file so Excel on Windows shows Hindi names properly
            with path.open('a', newline='', encoding='utf-8-sig' if new else 'utf-8') as f:
                w = csv.DictWriter(f, FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: ('' if v is None else v) for k, v in row.items()})
    except OSError as e:
        print(f'job log not written: {e}')


def made(report: dict) -> None:
    q = report.get('quote') or {}
    record(event='made', job_id=report['job_id'], name=report.get('name', ''), client=report.get('client', ''),
           status=report['status'], stage='new', inks=len(report['inks']), accuracy=report['accuracy'],
           seconds=round(sum((report.get('seconds') or {}).values()), 1),
           width_in=report['print']['width_in'], meters=q.get('meters', ''), quote_total=q.get('total', ''),
           currency=q.get('currency', ''))


def read(since: datetime | None = None) -> list[dict]:
    path = log_path()
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if since is not None:
        rows = [r for r in rows if (r.get('time') or '') >= since.isoformat(timespec='seconds')]
    return rows


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stats(days: int, card: dict, now: datetime | None = None) -> dict:
    """The last `days` days: jobs made, how many needed nobody, where they
    ended, what was quoted, and the time saved at the mill's own estimates
    (rate card: minutes a design takes by hand, minutes a held one takes to
    check, staff cost per hour). Estimates, and labelled so."""
    now = now or datetime.now()
    end = now.isoformat(timespec='seconds')
    rows = [r for r in read(now - timedelta(days=days)) if (r.get('time') or '') <= end]
    jobs = {}
    for r in rows:
        if r['event'] == 'made':
            jobs[r['job_id']] = dict(r)
        elif r['event'] == 'stage' and r['job_id'] in jobs:
            jobs[r['job_id']]['stage'] = r['stage']
    made_rows = list(jobs.values())
    n = len(made_rows)
    auto_ok = sum(1 for j in made_rows if j['status'] == 'auto_ok')
    held = n - auto_ok
    stages = {}
    for j in made_rows:
        stages[j['stage'] or 'new'] = stages.get(j['stage'] or 'new', 0) + 1
    per_day = {}
    for j in made_rows:
        d = (j['time'] or '')[:10]
        per_day[d] = per_day.get(d, 0) + 1
    manual, review = card.get('manual_minutes_per_design', 0), card.get('review_minutes_per_design', 0)
    saved_min = max(0.0, n * manual - held * review - sum(_num(j['seconds']) for j in made_rows) / 60)
    return {
        'days': days, 'jobs': n, 'auto_ok': auto_ok, 'needs_review': held,
        'auto_ok_percent': round(auto_ok / n * 100) if n else 0,
        'stages': stages,
        'avg_seconds': round(sum(_num(j['seconds']) for j in made_rows) / n, 1) if n else 0,
        'quoted': round(sum(_num(j['quote_total']) for j in made_rows)),
        'meters': round(sum(_num(j['meters']) for j in made_rows)),
        'currency': card.get('currency', ''),
        'per_day': dict(sorted(per_day.items())),
        'hours_saved': round(saved_min / 60, 1),
        'money_saved': round(saved_min / 60 * card.get('staff_cost_per_hour', 0)),
        'estimate': {'manual_minutes_per_design': manual, 'review_minutes_per_design': review,
                     'staff_cost_per_hour': card.get('staff_cost_per_hour', 0)},
    }
