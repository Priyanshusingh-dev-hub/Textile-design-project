import { useState } from 'react';
import { API, getJson, imageUrl, request } from '../api';
import { useT } from '../lib/i18n';

type Report = {
  loomlab: { commit: string; up_for_minutes: number; app_built: string };
  // a count the engine could not make is said as text
  data: { disk_free_gb: number | null; cache_mb: number; library_designs: number | string; job_log_lines: number | string };
  settings: Record<string, string>;
  licence: { required: boolean; valid: boolean; reason?: string };
  errors_total: number;
  text: string;
  errors: { at: string; method: string; path: string; error: string; where: string }[];
};

/** Settings -> Help: the engine's report, to copy or download and send to
 *  whoever helps the mill — versions, space, settings, the last errors. */
export default function Help() {
  const t = useT();
  const [r, setR] = useState<Report>();
  const [note, setNote] = useState('');
  const load = () => getJson<Report>('/diagnostics').then(x => { setR(x); setNote(''); })
    .catch(e => setNote(e instanceof Error ? e.message : String(e)));
  const copy = async () => {
    try {
      // the report as shown; a fresh one only if none was loaded
      const text = r?.text ?? await (await request(API + '/diagnostics/report.txt')).text();
      await navigator.clipboard.writeText(text);
      setNote('Copied — paste it into WhatsApp or an email.');
    } catch { setNote('Could not copy here: use Download instead.'); }
  };
  const low = r?.data.disk_free_gb != null && r.data.disk_free_gb < 2;
  const bad = r ? Object.entries(r.settings).filter(([, v]) => v !== 'ok') : [];
  const SETTING: Record<string, string> = { rate_card: 'Rate card', auto_limits: 'Auto limits' };
  return (
    <div className="set-card set-backup">
      <h3>{t('Help')} <small>{t('a report for whoever helps you: versions, space, settings and the last errors — no designs, prices or clients')}</small></h3>
      {!r && <button className="secondary" onClick={load}>{t('Check the engine')}</button>}
      {r && <>
        <p className="muted">
          {t('LoomLab {c} · running {m} min · {g} GB free · cache {mb} MB · {d} library designs', {
            c: r.loomlab.commit, m: r.loomlab.up_for_minutes, g: r.data.disk_free_gb ?? '?', mb: r.data.cache_mb,
            d: r.data.library_designs })}
        </p>
        {low && <p className="warn">{t('Under 2 GB free on this disk: big designs and packages may fail. Free some space.')}</p>}
        {bad.map(([k, v]) => <p key={k} className="warn">
          {t(SETTING[k] ?? k)}: {t(v.replace(/^problem: /, ''))}</p>)}
        {r.licence.required && !r.licence.valid && <p className="warn">{t(r.licence.reason ?? 'Not activated')}</p>}
        <p className={r.errors_total ? 'warn' : 'hint'}>
          {r.errors_total ? t('{n} errors since the engine started (newest first):', { n: r.errors_total })
            : t('No errors since the engine started.')}
        </p>
        {!!r.errors.length && <ul className="help-errors">
          {r.errors.slice(0, 5).map((e, i) => <li key={i}><code>{e.at.slice(11, 16)}</code> {e.path} — {e.error}</li>)}
        </ul>}
        <div className="row">
          <button className="secondary" onClick={copy}>{t('📋 Copy report')}</button>
          <a className="secondary file-pick" href={imageUrl('/api/diagnostics/report.txt')} download>{t('⬇ Download report')}</a>
          <button className="mini" onClick={load}>{t('↻ Refresh')}</button>
        </div>
      </>}
      {note && <p className="hint">{t(note)}</p>}
    </div>
  );
}
