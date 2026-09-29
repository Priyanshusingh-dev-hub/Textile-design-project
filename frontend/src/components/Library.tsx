import { useEffect, useState } from 'react';
import { getJson, imageUrl, post } from '../api';
import { money } from '../lib/print';

type Entry = {
  id: string; name: string; client: string; kept_at: string; inks: { name: string; hex: string; coverage: number }[];
  print: { width_in: number; height_in: number }; underbase: boolean; fabric: string; last_meters: number | null;
  has_proof: boolean; has_package: boolean;
};
type Quote = { total: number; per_meter: number; currency: string; image_url: string; quote_no: string };

/** Approved designs, kept for good: find one, burn a screen again from its
 *  films, or price a repeat order — the screens already exist, so none are charged. */
export default function Library() {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Entry[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [meters, setMeters] = useState<Record<string, string>>({});
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [busy, setBusy] = useState('');

  useEffect(() => {
    const t = setTimeout(() => {
      getJson<{ designs: Entry[]; total: number }>(`/library?q=${encodeURIComponent(q)}`)
        .then(r => { setItems(r.designs); setTotal(r.total); setError(''); })
        .catch(e => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const repeatQuote = async (e: Entry) => {
    const m = Number(meters[e.id]);
    if (!(m > 0)) return;
    setBusy(e.id);
    try {
      const r = await post<Quote>('/quote', { library_id: e.id, meters: m });
      setQuotes(qs => ({ ...qs, [e.id]: r }));
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(''); }
  };

  return (
    <div className="library">
      <div className="library-head">
        <input className="lib-search" type="search" placeholder="Find a design or client…" value={q}
          onChange={e => setQ(e.target.value)} aria-label="Search the library" />
        <span className="muted">{total} approved design{total !== 1 ? 's' : ''}, kept for repeat orders</span>
      </div>
      {error && <p className="warn">{error}</p>}
      {!items.length && !error && (
        <p className="hint">{q ? 'Nothing matches.' : 'Designs land here when a job is marked Approved (on this page or by the client on Telegram).'}</p>
      )}
      <ul className="job-list">
        {items.map(e => (
          <li key={e.id} className="job ok">
            {e.has_proof ? <img src={imageUrl(`/api/library/${e.id}/proof`)} alt="" /> : <div className="lib-noproof" />}
            <div className="job-main">
              <div className="job-title"><b>{e.name || e.id.slice(0, 8)}</b>
                <small> · {e.client || 'no client'} · approved {e.kept_at.slice(0, 10)}</small></div>
              <div className="job-facts">
                <span className="lib-inks">{e.inks.map(i => <span key={i.hex + i.name} className="plate-swatch" title={`${i.name} ${i.coverage}%`} style={{ background: i.hex }} />)}</span>
                {e.inks.length} screens · {e.print.width_in} × {e.print.height_in} in{e.underbase ? ' · white under-base' : ''}
                {e.last_meters ? ` · last run ${e.last_meters} m` : ''}
              </div>
              <div className="row lib-repeat">
                <input className="width-input" type="number" min={1} placeholder="meters" value={meters[e.id] ?? ''}
                  onChange={ev => { setMeters(m => ({ ...m, [e.id]: ev.target.value })); setQuotes(qs => { const n = { ...qs }; delete n[e.id]; return n; }); }} />
                <button className="mini go" disabled={busy === e.id || !(Number(meters[e.id]) > 0)} onClick={() => repeatQuote(e)}>
                  ₹ Repeat quote</button>
                {quotes[e.id] && <span className="hint-inline">{money(quotes[e.id].total, quotes[e.id].currency)} · {money(quotes[e.id].per_meter, quotes[e.id].currency)}/m, no new screens ·{' '}
                  <a href={imageUrl(quotes[e.id].image_url)} download={`quote-${quotes[e.id].quote_no}.png`} target="_blank" rel="noreferrer">quote image ⬇</a></span>}
              </div>
            </div>
            <div className="job-actions">
              {e.has_package && <a className="mini" href={imageUrl(`/api/library/${e.id}/package`)} download>⬇ Films</a>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
