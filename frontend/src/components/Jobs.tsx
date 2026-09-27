import { useEffect, useState } from 'react';
import { getJson, imageUrl, post } from '../api';
import { ago, counts, filterJobs, STAGE_LABEL, WARN_LABEL, type JobFilter, type JobRow, type Stage } from '../lib/jobs';
import { money } from '../lib/print';

const FILTERS: [JobFilter, string][] = [['attention', 'Needs review'], ['open', 'Open'], ['done', 'Finished'], ['all', 'All']];

/** Every auto-mode job (Telegram bot, scripts): the operator opens this to
 *  see only the jobs that need a person, and to mark what was done. */
export default function Jobs({ onWaiting }: { onWaiting?: (n: number) => void }) {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [filter, setFilter] = useState<JobFilter>('attention');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = () => getJson<{ jobs: JobRow[] }>('/jobs')
    .then(r => { setJobs(r.jobs); setError(''); onWaiting?.(counts(r.jobs).attention); })
    .catch(e => setError(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);     // the bot adds jobs while this is open
    return () => clearInterval(t);
  }, []);

  const mark = async (j: JobRow, stage: Stage) => {
    setBusy(j.job_id);
    try {
      await post(`/jobs/${j.job_id}/stage`, { stage, by: 'Operator' });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(''); }
  };

  const n = counts(jobs);
  const shown = filterJobs(jobs, filter);
  return (
    <section className="jobs">
      <div className="jobs-head">
        <h2>Jobs</h2>
        <div className="jobs-tabs">
          {FILTERS.map(([f, label]) => (
            <button key={f} className={f === filter ? 'on' : ''} onClick={() => setFilter(f)}>
              {label} <b>{n[f]}</b>
            </button>
          ))}
        </div>
        <button className="mini" onClick={load}>↻ Refresh</button>
      </div>
      {error && <p className="warn">{error}</p>}
      {!shown.length && !error && (
        <p className="hint">{filter === 'attention' ? 'Nothing waiting: every held job has been dealt with.' : 'No jobs here yet.'}</p>
      )}
      <ul className="job-list">
        {shown.map(j => (
          <li key={j.job_id} className={'job ' + (j.status === 'needs_review' ? 'held' : 'ok')}>
            <img src={imageUrl(`/api/image/${j.reduced_id}`) + '?max_side=240'} alt=""
              onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }} />
            <div className="job-main">
              <div className="job-title">
                <b>{j.name || j.job_id.slice(0, 8)}</b>
                {j.client && <span> · {j.client}</span>}
                <small> · {ago(j.created_at)}</small>
              </div>
              <div className="job-facts">
                <span className={'pill ' + (j.status === 'needs_review' ? 'warn-pill' : 'ok-pill')}>
                  {j.status === 'needs_review' ? 'needs review' : 'auto OK'}</span>
                <span className="pill">{STAGE_LABEL[j.stage] ?? j.stage}</span>
                <span>{j.inks} inks · {j.accuracy}% match · {j.print.width_in} × {j.print.height_in} in</span>
                {j.total != null && <span>· {money(j.total, j.currency ?? '₹')} for {j.meters} m</span>}
              </div>
              {!!j.warnings.length && (
                <ul className="job-warn">{j.warnings.map(w => <li key={w.code} title={w.message}>⚠ {WARN_LABEL[w.code] ?? w.code}: {w.message}</li>)}</ul>
              )}
              {j.last && <small className="job-last">{STAGE_LABEL[j.last.stage as Stage] ?? j.last.stage}{j.last.by ? ` by ${j.last.by}` : ''} · {ago(j.last.at)}</small>}
            </div>
            <div className="job-actions">
              <a className="mini" href={imageUrl(j.package_url)} download>⬇ Package</a>
              {j.stage === 'new' && <>
                <button className="mini go" disabled={busy === j.job_id} onClick={() => mark(j, 'reviewed')}>✓ Checked</button>
                <button className="mini" disabled={busy === j.job_id} onClick={() => mark(j, 'rejected')}>✕ Stop</button>
              </>}
              {(j.stage === 'reviewed' || j.stage === 'sent') &&
                <button className="mini go" disabled={busy === j.job_id} onClick={() => mark(j, 'approved')}>Approved</button>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
