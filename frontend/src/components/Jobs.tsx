import { useEffect, useState } from 'react';
import { getJson, imageUrl, post } from '../api';
import { ago, counts, filterJobs, statTiles, STAGE_LABEL, WARN_LABEL, type JobFilter, type JobRow, type Stage, type Stats } from '../lib/jobs';
import { money } from '../lib/print';
import Library from './Library';
import { useT } from '../lib/i18n';

const FILTERS: [JobFilter, string][] = [['attention', 'Needs review'], ['open', 'Open'], ['done', 'Finished'], ['all', 'All']];

/** Every auto-mode job (Telegram bot, scripts): the operator opens this to
 *  see only the jobs that need a person, and to mark what was done. */
export default function Jobs({ onWaiting }: { onWaiting?: (n: number) => void }) {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const t = useT();
  const [filter, setFilter] = useState<JobFilter>('attention');
  const [tab, setTab] = useState<'jobs' | 'library'>('jobs');   // approved designs, kept for repeat orders
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const [total, setTotal] = useState(0);
  const [attention, setAttention] = useState(0);
  const [stats, setStats] = useState<Stats>();
  const load = () => getJson<{ jobs: JobRow[]; total: number; attention: number }>('/jobs?limit=1000')
    .then(r => {
      setJobs(r.jobs); setTotal(r.total); setAttention(r.attention); setError('');
      onWaiting?.(r.attention);     // counted by the engine over every job, as the header's count is
      getJson<Stats>('/stats?days=30').then(setStats).catch(() => { /* the numbers are extra */ });
    })
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

  const n = { ...counts(jobs), attention: Math.max(attention, counts(jobs).attention), all: Math.max(total, jobs.length) };
  const shown = filterJobs(jobs, filter);
  return (
    <section className="jobs">
      <div className="jobs-head">
        <h2>{t('Jobs')}</h2>
        <div className="jobs-tabs">
          {FILTERS.map(([f, label]) => (
            <button key={f} className={tab === 'jobs' && f === filter ? 'on' : ''} onClick={() => { setTab('jobs'); setFilter(f); }}>
              {t(label)} <b>{n[f]}</b>
            </button>
          ))}
          <button className={tab === 'library' ? 'on' : ''} onClick={() => setTab('library')}
            title={t('Approved designs, kept for good: films and repeat-order quotes')}>{t('📚 Library')}</button>
        </div>
        <button className="mini" onClick={load}>{t('↻ Refresh')}</button>
      </div>
      {tab === 'library' ? <Library /> : <>
      {stats && !!stats.designs && (
        <div className="stat-tiles">
          {statTiles(stats, money).map(([label, value, note]) => (
            <div key={label} className="stat-tile"><small>{t(label)}</small><b>{value}</b>{note && <span>{note}</span>}</div>
          ))}
        </div>
      )}
      {error && <p className="warn">{error}</p>}
      {total > jobs.length && <p className="muted">{t('Showing the newest {n} of {m} jobs.', { n: jobs.length, m: total })}</p>}
      {!shown.length && !error && (
        <p className="hint">{t(filter === 'attention' ? 'Nothing waiting: every held job has been dealt with.' : 'No jobs here yet.')}</p>
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
                  {t(j.status === 'needs_review' ? 'needs review' : 'auto OK')}</span>
                <span className="pill">{t(STAGE_LABEL[j.stage] ?? j.stage)}</span>
                <span>{t('{n} inks · {a}% match · {w} × {h} in', { n: j.inks, a: j.accuracy, w: j.print.width_in, h: j.print.height_in })}</span>
                {j.total != null && <span>· {t('{money} for {m} m', { money: money(j.total, j.currency ?? '₹'), m: j.meters ?? '' })}</span>}
              </div>
              {!!j.warnings.length && (
                <ul className="job-warn">{j.warnings.map(w => <li key={w.code} title={w.message}>⚠ {t(WARN_LABEL[w.code] ?? w.code)}: {w.message}</li>)}</ul>
              )}
              {j.last && <small className="job-last">{t(STAGE_LABEL[j.last.stage as Stage] ?? j.last.stage)}{j.last.by ? ` · ${j.last.by}` : ''} · {ago(j.last.at)}</small>}
            </div>
            <div className="job-actions">
              <a className="mini" href={imageUrl(j.package_url)} download>{t('⬇ Package')}</a>
              {j.stage === 'new' && <>
                <button className="mini go" disabled={busy === j.job_id} onClick={() => mark(j, 'reviewed')}>{t('✓ Checked')}</button>
                <button className="mini" disabled={busy === j.job_id} onClick={() => mark(j, 'rejected')}>{t('✕ Stop')}</button>
              </>}
              {(j.stage === 'reviewed' || j.stage === 'sent') &&
                <button className="mini go" disabled={busy === j.job_id} onClick={() => mark(j, 'approved')}>{t('Approved')}</button>}
            </div>
          </li>
        ))}
      </ul>
      </>}
    </section>
  );
}
