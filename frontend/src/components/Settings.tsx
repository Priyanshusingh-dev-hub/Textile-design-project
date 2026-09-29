import { useEffect, useState } from 'react';
import { getJson, imageUrl, putJson, uploadFile } from '../api';
import { AUTO_FIELDS, fromForm, pricesFromRows, priceRows, RATE_FIELDS, toForm,
  type Field, type Form, type PriceRow, type Values } from '../lib/settings';

type Section = { values: Values; error: string | null };
type Loaded = { rate_card: Section; auto: Section & { codes: Record<string, string> } };
type Note = { tone: 'ok' | 'warn'; text: string } | undefined;

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Fields({ fields, form, errors, onChange }: {
  fields: Field[]; form: Form; errors: Record<string, string>; onChange: (key: string, v: string) => void;
}) {
  return (
    <div className="set-grid">
      {fields.map(f => (
        <label key={f.key} className={'set-field' + (errors[f.key] ? ' bad' : '')} title={f.hint}>
          <span>{f.label}{f.hint && <small>{f.hint}</small>}</span>
          <span className="set-input">
            <input type="text" inputMode="decimal" value={form[f.key] ?? ''} onChange={e => onChange(f.key, e.target.value)} />
            {f.unit && <em>{f.unit}</em>}
          </span>
          {errors[f.key] && <b className="set-err">{errors[f.key]}</b>}
        </label>
      ))}
    </div>
  );
}

/** Quote prices and auto mode's limits, edited here instead of in Notepad.
 *  The engine checks both again before it saves; the next quote/job uses them. */
export default function Settings() {
  const [loaded, setLoaded] = useState<Loaded>();
  const [loadError, setLoadError] = useState('');
  const [rate, setRate] = useState<Form>({});
  const [mill, setMill] = useState({ mill_name: '', currency: '' });
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [auto, setAuto] = useState<Form>({});
  const [blocking, setBlocking] = useState<string[]>([]);
  const [rateErr, setRateErr] = useState<Record<string, string>>({});
  const [autoErr, setAutoErr] = useState<Record<string, string>>({});
  const [rateNote, setRateNote] = useState<Note>();
  const [autoNote, setAutoNote] = useState<Note>();
  const [saving, setSaving] = useState('');
  const [backupNote, setBackupNote] = useState<Note>();

  const fill = (r: Loaded) => {
    setLoaded(r);
    const c = r.rate_card.values;
    setRate(toForm(c, RATE_FIELDS));
    setMill({ mill_name: String(c.mill_name ?? ''), currency: String(c.currency ?? '') });
    setPrices(priceRows(c.ink_prices));
    setAuto(toForm(r.auto.values, AUTO_FIELDS));
    setBlocking((r.auto.values.blocking as string[]) || []);
    setRateNote(r.rate_card.error ? { tone: 'warn', text: `The saved rate card has a problem: ${r.rate_card.error} Showing the defaults — check them and save.` } : undefined);
    setAutoNote(r.auto.error ? { tone: 'warn', text: `The saved auto settings have a problem: ${r.auto.error} Showing the defaults — check them and save.` } : undefined);
  };

  useEffect(() => {
    getJson<Loaded>('/settings').then(fill).catch(e => setLoadError(errText(e)));
  }, []);

  const saveRate = async () => {
    const { values, errors } = fromForm(rate, RATE_FIELDS);
    const p = pricesFromRows(prices);
    setRateErr(errors);
    if (Object.keys(errors).length || p.error) {
      setRateNote({ tone: 'warn', text: p.error || 'Fix the boxes marked in red.' });
      return;
    }
    setSaving('rate');
    try {
      const saved = await putJson<Values>('/settings/rate-card', { ...values, ...mill, ink_prices: p.prices });
      setRate(toForm(saved, RATE_FIELDS)); setPrices(priceRows(saved.ink_prices));
      setRateNote({ tone: 'ok', text: 'Saved — the next quote uses these prices.' });
    } catch (e) { setRateNote({ tone: 'warn', text: errText(e) }); } finally { setSaving(''); }
  };

  const saveAuto = async () => {
    const { values, errors } = fromForm(auto, AUTO_FIELDS);
    setAutoErr(errors);
    if (Object.keys(errors).length) { setAutoNote({ tone: 'warn', text: 'Fix the boxes marked in red.' }); return; }
    setSaving('auto');
    try {
      const saved = await putJson<Values>('/settings/auto', { ...values, blocking });
      setAuto(toForm(saved, AUTO_FIELDS));
      setAutoNote({ tone: 'ok', text: 'Saved — the next auto job (and the Telegram bot) uses these limits.' });
    } catch (e) { setAutoNote({ tone: 'warn', text: errText(e) }); } finally { setSaving(''); }
  };

  /** Put a backup back: every part is checked by the engine before anything is written. */
  const restore = async (file: File) => {
    if (!window.confirm(`Restore ${file.name}? The library, rate card, limits and inks on this PC are replaced by the backup's; the job log is added to.`)) return;
    setSaving('restore');
    try {
      const r = await uploadFile<{ library: number; job_log_rows_added: number; inks: number; made_at: string }>(
        file, '/backup/restore', 'This backup could not be restored.');
      setBackupNote({ tone: 'ok', text: `Restored the backup from ${r.made_at.slice(0, 10)}: ${r.library} library design${r.library !== 1 ? 's' : ''}, `
        + `${r.inks} shelf ink${r.inks !== 1 ? 's' : ''}, ${r.job_log_rows_added} job-log line${r.job_log_rows_added !== 1 ? 's' : ''} added, prices and limits.` });
      getJson<Loaded>('/settings').then(fill).catch(() => {});
    } catch (e) { setBackupNote({ tone: 'warn', text: errText(e) }); } finally { setSaving(''); }
  };

  if (loadError) return <section className="settings"><h2>Settings</h2><p className="warn">{loadError}</p></section>;
  if (!loaded) return <section className="settings"><h2>Settings</h2><p className="muted">Loading…</p></section>;

  const codes = loaded.auto.codes;
  return (
    <section className="settings">
      <h2>Settings</h2>
      <div className="set-cards">
        <div className="set-card">
          <h3>Quote prices <small>rate card</small></h3>
          <div className="set-grid">
            <label className="set-field"><span>Mill name<small>on the quote</small></span>
              <span className="set-input"><input type="text" maxLength={80} value={mill.mill_name}
                onChange={e => setMill(m => ({ ...m, mill_name: e.target.value }))} /></span></label>
            <label className="set-field"><span>Currency<small>₹ or Rs.</small></span>
              <span className="set-input"><input type="text" maxLength={6} value={mill.currency}
                onChange={e => setMill(m => ({ ...m, currency: e.target.value }))} /></span></label>
          </div>
          <Fields fields={RATE_FIELDS} form={rate} errors={rateErr} onChange={(k, v) => setRate(f => ({ ...f, [k]: v }))} />
          <h4>Ink prices by name <small>per kg — the name as on the plate, or its hex</small></h4>
          <div className="set-prices">
            {prices.map((r, i) => (
              <div className="set-price" key={i}>
                <input type="text" maxLength={60} placeholder="ink name, e.g. Rani Pink 12" value={r.name}
                  onChange={e => setPrices(ps => ps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input type="text" inputMode="decimal" placeholder="per kg" value={r.price}
                  onChange={e => setPrices(ps => ps.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))} />
                <button className="mini" title="Remove" onClick={() => setPrices(ps => ps.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
            <button className="mini" onClick={() => setPrices(ps => [...ps, { name: '', price: '' }])}>+ ink price</button>
          </div>
          {rateNote && <p className={rateNote.tone === 'ok' ? 'hint' : 'warn'}>{rateNote.text}</p>}
          <button className="primary wide" disabled={!!saving} onClick={saveRate}>{saving === 'rate' ? 'Saving…' : 'Save prices'}</button>
        </div>

        <div className="set-card">
          <h3>Auto mode <small>when a job waits for a person</small></h3>
          <Fields fields={AUTO_FIELDS} form={auto} errors={autoErr} onChange={(k, v) => setAuto(f => ({ ...f, [k]: v }))} />
          <h4>Stop the job for <small>ticked: it waits for review · unticked: only reported</small></h4>
          <div className="set-codes">
            {Object.entries(codes).map(([code, title]) => (
              <label key={code} className="check">
                <input type="checkbox" checked={blocking.includes(code)}
                  onChange={e => setBlocking(b => (e.target.checked ? [...b, code] : b.filter(c => c !== code)))} />
                {title}
              </label>
            ))}
          </div>
          {autoNote && <p className={autoNote.tone === 'ok' ? 'hint' : 'warn'}>{autoNote.text}</p>}
          <button className="primary wide" disabled={!!saving} onClick={saveAuto}>{saving === 'auto' ? 'Saving…' : 'Save limits'}</button>
        </div>
      </div>
      <div className="set-card set-backup">
        <h3>Backup <small>the design library with its films, the job log, your inks, prices and limits</small></h3>
        <p className="muted">Keep a copy somewhere else (a pen drive, Google Drive): a dead disk or a new PC then costs nothing.
          Restore puts it back on any LoomLab.</p>
        <div className="row">
          <a className="primary" href={imageUrl('/api/backup')} download>⬇ Download backup</a>
          <label className="secondary file-pick">
            {saving === 'restore' ? 'Restoring…' : '⤒ Restore a backup'}
            <input type="file" accept=".zip,application/zip" hidden disabled={!!saving}
              onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) restore(f); }} />
          </label>
        </div>
        {backupNote && <p className={backupNote.tone === 'ok' ? 'hint' : 'warn'}>{backupNote.text}</p>}
      </div>
    </section>
  );
}
