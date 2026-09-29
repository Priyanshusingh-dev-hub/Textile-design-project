import { STEPS } from '../types';
import type { LoomLab } from '../hooks/useLoomLab';
import { useT, type Lang } from '../lib/i18n';

/** The brand, the four steps (each unlocked as it is reached), Jobs and the status badge. */
export function AppHeader({ w, lang, setLang }: { w: LoomLab; lang: Lang; setLang: (l: Lang) => void }) {
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
  const t = useT();
  return (
    <header>
      <div className="brand"><span className="loom">L</span><div>LoomLab<small>{t('COLOR SEPARATION')}</small></div></div>
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s} className={s === step && view === 'wizard' ? 'on' : i <= reached ? 'done' : ''}>
            <button disabled={i > reached || busy} onClick={() => { setView('wizard'); setStep(s); }}><b>{i + 1}</b><span>{t(s)}</span></button>
          </li>
        ))}
      </ol>
      <div className="header-links">
        <button className={'jobs-link' + (view === 'jobs' ? ' on' : '')} onClick={() => setView(v => v === 'jobs' ? 'wizard' : 'jobs')}
          title={t('Jobs from auto mode and the Telegram bot')}>{t('Jobs')}{held > 0 && <b>{held}</b>}</button>
        <button className={'jobs-link' + (view === 'settings' ? ' on' : '')} onClick={() => setView(v => v === 'settings' ? 'wizard' : 'settings')}
          title={t("Quote prices and auto mode's limits")}>{t('⚙ Settings')}</button>
        <button className="jobs-link lang" onClick={() => setLang(lang === 'hi' ? 'en' : 'hi')}
          title={lang === 'hi' ? 'Switch to English' : 'Hinglish me dekho'}>{lang === 'hi' ? 'EN' : 'हिं'}</button>
      </div>
      <div className={'badge s-' + status.state}>{t(status.state === 'processing' ? 'WORKING' : status.state === 'failed' ? 'ERROR' : status.state === 'done' ? 'DONE' : 'READY')}</div>
    </header>
  );
}
