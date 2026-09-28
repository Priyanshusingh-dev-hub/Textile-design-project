import { STEPS } from '../types';
import type { LoomLab } from '../hooks/useLoomLab';

/** The brand, the four steps (each unlocked as it is reached), Jobs and the status badge. */
export function AppHeader({ w }: { w: LoomLab }) {
  const {
    step,
    setStep,
    reached,
    view,
    setView,
    held,
    status,
    busy,
  } = w;
  return (
    <header>
      <div className="brand"><span className="loom">L</span><div>LoomLab<small>COLOR SEPARATION</small></div></div>
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s} className={s === step && view === 'wizard' ? 'on' : i <= reached ? 'done' : ''}>
            <button disabled={i > reached || busy} onClick={() => { setView('wizard'); setStep(s); }}><b>{i + 1}</b><span>{s}</span></button>
          </li>
        ))}
      </ol>
      <button className={'jobs-link' + (view === 'jobs' ? ' on' : '')} onClick={() => setView(v => v === 'jobs' ? 'wizard' : 'jobs')}
        title="Jobs from auto mode and the Telegram bot">Jobs{held > 0 && <b>{held}</b>}</button>
      <div className={'badge s-' + status.state}>{status.state === 'processing' ? 'WORKING' : status.state === 'failed' ? 'ERROR' : status.state === 'done' ? 'DONE' : 'READY'}</div>
    </header>
  );
}
