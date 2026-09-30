import { useEffect, useState } from 'react';
import { getJson } from '../api';
import { ago } from '../lib/jobs';
import { type ClientRow, PERIODS } from '../lib/clients';
import { money } from '../lib/print';
import { useT } from '../lib/i18n';

/** Each client's business from the job log (kept for good): what they sent,
 *  what was approved, what it brought in, repeat orders — the biggest first. */
export default function Clients() {
  const t = useT();
  const [days, setDays] = useState(90);
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<ClientRow[]>([]);
  const [currency, setCurrency] = useState('₹');
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      getJson<{ clients: ClientRow[]; currency: string }>(`/clients?days=${days}&client=${encodeURIComponent(q.trim())}`)
        .then(r => { setRows(r.clients); setCurrency(r.currency || '₹'); setError(''); })
        .catch(e => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(timer);
  }, [days, q]);

  return (
    <div className="clients">
      <div className="library-head">
        <input className="lib-search" type="search" placeholder={t('Find a client…')} value={q}
          onChange={e => setQ(e.target.value)} aria-label={t('Find a client…')} />
        <div className="jobs-tabs">
          {PERIODS.map(([d, label]) => (
            <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>{t(label)}</button>
          ))}
        </div>
      </div>
      {error && <p className="warn">{t(error)}</p>}
      {!rows.length && !error && <p className="hint">{t('No client orders in this period yet. Jobs with a client name (the Telegram bot fills it in) show here.')}</p>}
      {!!rows.length && (
        <div className="client-table-wrap">
          <table className="client-table">
            <thead>
              <tr>
                <th>{t('Client')}</th><th>{t('Designs')}</th><th>{t('Approved')}</th><th>{t('Waiting')}</th>
                <th>{t('Approved meters')}</th><th>{t('Repeat orders')}</th><th>{t('Business')}</th><th>{t('Last')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.client}>
                  <td><b>{c.client}</b>{c.own_rates && <small className="pill" title={t('Has its own rates (Settings)')}>{t('own rates')}</small>}</td>
                  <td>{c.designs}</td>
                  <td>{c.approved}{c.rejected ? <small className="muted"> · {t('{n} stopped', { n: c.rejected })}</small> : null}</td>
                  <td>{c.waiting || '—'}</td>
                  <td>{c.approved_meters ? `${c.approved_meters.toLocaleString('en-IN')} m` : '—'}</td>
                  <td>{c.repeat_orders ? `${c.repeat_orders} · ${c.repeat_meters.toLocaleString('en-IN')} m` : '—'}</td>
                  <td><b>{money(c.business, currency)}</b>
                    {c.quoted > c.approved_quoted && <small className="muted" title={t('Quoted but not approved yet')}> · {t('{m} quoted', { m: money(c.quoted - c.approved_quoted, currency) })}</small>}</td>
                  <td>{ago(c.last, Date.now(), t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small-note">{t('Business = approved runs + repeat orders, as quoted. Each design counts once, by its latest run.')}</p>
    </div>
  );
}
