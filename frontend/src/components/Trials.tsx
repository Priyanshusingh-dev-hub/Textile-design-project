import type { LoomLab } from '../hooks/useLoomLab';
import { TRIAL_CODE, TRIAL_LABEL, methodNote, trialSummary } from '../lib/fill';
import { useT } from '../lib/i18n';

/** What the engine tried to make this design, each scored against the
 *  reference, and why it chose what it chose — like a training run's table.
 *  Any way that ran can be taken instead with one click (the engine logs it). */
export function Trials({ w }: { w: LoomLab }) {
  const { fillInfo, refill, canRefill, busy } = w;
  const t = useT();
  const tr = fillInfo?.trials;
  if (!fillInfo || !tr) return null;
  const how = methodNote(fillInfo, t);
  const line = trialSummary(fillInfo, t);
  return (
    <details className={'trials' + (line.warn ? ' warn' : '')}>
      <summary>{line.text} <span className="dim">· {t('what was tried')}</span></summary>
      <p className={how.warn ? 'warn' : 'hint'}>{how.text}</p>
      <table className="trials-table">
        <thead>
          <tr><th>{t('Tried')}</th><th>{t('Match')}</th><th>{t('Inks')}</th><th>{t('Edges')}</th><th /></tr>
        </thead>
        <tbody>
          {tr.rows.map(r => (
            <tr key={r.name} className={r.chosen ? 'chosen' : ''}>
              <td>{t(TRIAL_LABEL[r.name])}</td>
              {r.status === 'ok'
                ? <><td>{r.match}%</td><td>{r.inks}</td><td>{r.edge_share}%</td></>
                : <td colSpan={3} className="dim">{t('could not run')}</td>}
              <td>
                {r.chosen ? <b title={t('chosen')}>✔</b>
                  : r.status === 'ok' && canRefill
                    ? <button className="mini" disabled={busy} onClick={() => refill(TRIAL_CODE[r.name])}>{t('Use this')}</button>
                    : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <small className="dim">
        {t('Match: how closely the result reproduces the reference, pixel by pixel. Edges: share of pixels with another ink beside them (lower is cleaner). Tried at {px} px in {s} s.',
          { px: tr.trial_px, s: tr.seconds })}
      </small>
    </details>
  );
}
