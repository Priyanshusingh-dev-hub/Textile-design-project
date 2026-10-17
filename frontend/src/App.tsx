import Jobs from './components/Jobs';
import Settings from './components/Settings';
import Activation from './components/Activation';
import { InkLibrary } from './components/InkLibrary';
import { AppHeader } from './components/AppHeader';
import { UploadStep } from './components/steps/UploadStep';
import { ReduceStep } from './components/steps/ReduceStep';
import { SeparateStep } from './components/steps/SeparateStep';
import { ExportStep } from './components/steps/ExportStep';
import { parseInkList } from './lib/inks';
import { useLoomLab } from './hooks/useLoomLab';
import { useContext, useState } from 'react';
import { LANG_KEY, LangContext, SetLangContext, savedLang, translate, useLang, type Lang } from './lib/i18n';

/** The shell: header, the step on screen (or the job dashboard), footer.
 *  The job and every action live in useLoomLab; each step is a view of it. */
export default function App() {
  // the language sits above the job, so the hook's notes are made in it too
  const [lang, setLangState] = useState<Lang>(savedLang);
  const setLang = (l: Lang) => { setLangState(l); try { localStorage.setItem(LANG_KEY, l); } catch { /* just not remembered */ } };
  return (
    <LangContext.Provider value={lang}>
      <SetLangContext.Provider value={setLang}>
        <Shell />
      </SetLangContext.Provider>
    </LangContext.Provider>
  );
}

function Shell() {
  const w = useLoomLab();
  const { view, step, licence, setLicence, setHeld, showLibrary, setShowLibrary, library, palette, inkName,
    busy, saveLibrary, status, message, original, input, onUpload } = w;
  const locked = licence?.required && !licence.valid;
  const lang = useLang();
  const setLang = useContext(SetLangContext);

  return (
    <div className="app">
      <AppHeader w={w} lang={lang} setLang={setLang} />

      <main>
        {locked && <Activation status={licence} onDone={setLicence} />}
        {!locked && <>
          {view === 'jobs' && <Jobs onWaiting={setHeld} />}
          {view === 'settings' && <Settings onRestored={w.reloadLibrary} />}
          {view === 'wizard' && step === 'Upload' && <UploadStep w={w} />}
          {view === 'wizard' && step === 'Reduce' && <ReduceStep w={w} />}
          {showLibrary && (
            <InkLibrary inks={library} palette={palette.map((p, i) => ({ hex: p.hex, name: inkName(i) }))}
              busy={busy} parse={parseInkList} onSave={saveLibrary} onClose={() => setShowLibrary(false)} />
          )}
          {view === 'wizard' && step === 'Separate' && <SeparateStep w={w} />}
          {view === 'wizard' && step === 'Export' && <ExportStep w={w} />}
        </>}
      </main>

      <footer>
        <span className={status.state === 'failed' ? 'err' : ''}>{translate(lang, status.state === 'failed' ? status.message ?? '' : message)}</span>
        <span>{original ? `${original.width}×${original.height}` : translate(lang, 'no design')}{palette.length ? ` · ${palette.length} inks` : ''}</span>
      </footer>

      <input ref={input} hidden type="file"
        accept="image/png,image/jpeg,image/webp,image/tiff,.psd,image/vnd.adobe.photoshop"
        onChange={e => e.target.files?.[0] && onUpload(e.target.files[0])} disabled={busy} />
    </div>
  );
}
