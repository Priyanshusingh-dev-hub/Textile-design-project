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
          'width_in', 'meters', 'quote_total', 'currency', 'by', 'note', 'design']


def _cell(v):
    """A value safe to open in Excel: text starting like a formula (a name a
    Telegram client typed, say "=HYPERLINK(...)") is kept as text."""
    if v is None:
        return ''
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v
    return v
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
            _upgrade(path)
            new = not path.exists()
            # utf-8-sig on a new file so Excel on Windows shows Hindi names properly
            with path.open('a', newline='', encoding='utf-8-sig' if new else 'utf-8') as f:
                w = csv.DictWriter(f, FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: _cell(v) for k, v in row.items()})
    except OSError as e:
        print(f'job log not written: {e}')


def _upgrade(path: Path) -> None:
    """A log written by an older LoomLab has fewer columns: rewrite it with
    today's header once, so new columns line up."""
    if not path.exists():
        return
    with path.open(newline='', encoding='utf-8-sig') as f:
        head = next(csv.reader(f), [])
    if head == FIELDS:
        return
    rows = read()
    tmp = path.with_name(path.name + '.part')
    with tmp.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows({k: r.get(k) or '' for k in FIELDS} for r in rows)
    tmp.replace(path)


def made(report: dict) -> None:
    q = report.get('quote') or {}
    record(event='made', job_id=report['job_id'], name=report.get('name', ''), client=report.get('client', ''),
           status=report['status'], stage='new', inks=len(report['inks']), accuracy=report['accuracy'],
           seconds=round(sum((report.get('seconds') or {}).values()), 1),
           width_in=report['print']['width_in'], meters=q.get('meters', ''), quote_total=q.get('total', ''),
           currency=q.get('currency', ''), design=report.get('design', ''))


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
    repeats = [r for r in rows if r['event'] == 'repeat']
    for r in rows:
        if r['event'] == 'made':
            jobs[r['job_id']] = dict(r)
        elif r['event'] == 'stage' and r['job_id'] in jobs:
            jobs[r['job_id']]['stage'] = r['stage']
    runs = list(jobs.values())
    # a design run again (another ink count, a client's change, the AI trying
    # a width) is still one design: count each by its latest run
    latest = {}
    for j in runs:
        latest[j.get('design') or j['job_id']] = j
    designs = list(latest.values())
    n = len(designs)
    auto_ok = sum(1 for j in designs if j['status'] == 'auto_ok')
    held = n - auto_ok
    stages = {}
    for j in designs:
        stages[j['stage'] or 'new'] = stages.get(j['stage'] or 'new', 0) + 1
    per_day = {}
    for j in designs:
        d = (j['time'] or '')[:10]
        per_day[d] = per_day.get(d, 0) + 1
    manual, review = card.get('manual_minutes_per_design', 0), card.get('review_minutes_per_design', 0)
    engine_min = sum(_num(j['seconds']) for j in runs) / 60
    saved_min = max(0.0, n * manual - held * review - engine_min)
    return {
        'days': days, 'designs': n, 'jobs': len(runs), 'auto_ok': auto_ok, 'needs_review': held,
        'auto_ok_percent': round(auto_ok / n * 100) if n else 0,
        'stages': stages,
        'avg_seconds': round(engine_min * 60 / len(runs), 1) if runs else 0,
        'quoted': round(sum(_num(j['quote_total']) for j in designs)),
        'meters': round(sum(_num(j['meters']) for j in designs)),
        'currency': card.get('currency', ''),
        'per_day': dict(sorted(per_day.items())),
        'hours_saved': round(saved_min / 60, 1),
        'money_saved': round(saved_min / 60 * card.get('staff_cost_per_hour', 0)),
        'estimate': {'manual_minutes_per_design': manual, 'review_minutes_per_design': review,
                     'staff_cost_per_hour': card.get('staff_cost_per_hour', 0)},
        # repeat orders on screens already made (no new design, no new screens)
        'repeat_orders': len(repeats), 'repeat_meters': round(sum(_num(r['meters']) for r in repeats)),
        'repeat_quoted': round(sum(_num(r['quote_total']) for r in repeats)),
    }


def _client_key(name: str) -> str:
    return ' '.join((name or '').split()).casefold()


def clients(days: int, card: dict, now: datetime | None = None, client: str = '') -> list[dict]:
    """Each client's business over the last `days` days, from the log: their
    designs (each counted once, by its latest run, as in `stats`), where those
    ended, the meters and money quoted — all and approved — and their repeat
    orders. Names match ignoring case and spaces; the latest spelling is shown.
    Jobs with no client are left out. `client` narrows it to one."""
    now = now or datetime.now()
    end = now.isoformat(timespec='seconds')
    rows = [r for r in read(now - timedelta(days=days)) if (r.get('time') or '') <= end]
    jobs = {}
    for r in rows:
        if r['event'] == 'made':
            jobs[r['job_id']] = dict(r)
        elif r['event'] == 'stage' and r['job_id'] in jobs:
            jobs[r['job_id']]['stage'] = r['stage']
            jobs[r['job_id']]['last'] = r['time']
    latest = {}
    for j in jobs.values():
        latest[(_client_key(j['client']), j.get('design') or j['job_id'])] = j
    rated = {_client_key(k) for k in (card.get('clients') or {})}
    out = {}

    def entry(name, time):
        key = _client_key(name)
        e = out.setdefault(key, {'client': name.strip(), 'designs': 0, 'approved': 0, 'rejected': 0, 'waiting': 0,
                                 'meters': 0.0, 'quoted': 0.0, 'approved_meters': 0.0, 'approved_quoted': 0.0,
                                 'repeat_orders': 0, 'repeat_meters': 0.0, 'repeat_quoted': 0.0,
                                 'last': '', 'own_rates': key in rated})
        if (time or '') >= e['last']:
            e['last'], e['client'] = time or '', name.strip()
        return e

    for (key, _), j in latest.items():
        if not key:
            continue
        e = entry(j['client'], j.get('last') or j['time'])
        e['designs'] += 1
        stage = j.get('stage') or 'new'
        if stage == 'approved':
            e['approved'] += 1
            e['approved_meters'] += _num(j['meters'])
            e['approved_quoted'] += _num(j['quote_total'])
        elif stage == 'rejected':
            e['rejected'] += 1
        elif stage != 'changed':
            e['waiting'] += 1
        e['meters'] += _num(j['meters'])
        e['quoted'] += _num(j['quote_total'])
    for r in rows:
        if r['event'] == 'repeat' and _client_key(r['client']):
            e = entry(r['client'], r['time'])
            e['repeat_orders'] += 1
            e['repeat_meters'] += _num(r['meters'])
            e['repeat_quoted'] += _num(r['quote_total'])
    result = []
    for e in out.values():
        for k in ('meters', 'quoted', 'approved_meters', 'approved_quoted', 'repeat_meters', 'repeat_quoted'):
            e[k] = round(e[k])
        # what the client has brought in: approved runs and repeat orders
        e['business'] = e['approved_quoted'] + e['repeat_quoted']
        result.append(e)
    if client:
        result = [e for e in result if _client_key(client) in _client_key(e['client'])]
    result.sort(key=lambda e: (e['business'], e['last']), reverse=True)
    return result
