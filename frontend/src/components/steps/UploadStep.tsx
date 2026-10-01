import { useEffect, useState } from 'react';
import { screenUrl } from '../../api';
import { jobSummary } from '../../lib/job';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';

const HOW = [
  ['Upload', 'Your design file — PNG, JPG, TIFF or a layered PSD.'],
  ['Reduce', 'Down to the inks you will print. LoomLab suggests how many.'],
  ['Separate', 'One screen per ink. Pick the cloth colour, change any ink.'],
  ['Export', 'Films at print size, proof, job sheet — and a quote.'],
];

type Way = 'design' | 'lineart';

/** Step 1: drop a design, or continue the last job — or the second way in:
 *  line art + a coloured reference of the same design. */
export function UploadStep({ w }: { w: LoomLab }) {
  const {
    original,
    input,
    busy,
    go,
    resumable,
    forgetJob,
    resumeJob,
    onUpload,
    loadSample,
    fillInfo,
  } = w;
  const t = useT();
  const [way, setWay] = useState<Way>(fillInfo ? 'lineart' : 'design');
  const showDesign = original && !original.layers && !(way === 'lineart' && !fillInfo);
  return (
    <section className="stage">
      <div className="way-tabs" role="tablist">
        <button role="tab" aria-selected={way === 'design'} className={way === 'design' ? 'on' : ''}
          onClick={() => setWay('design')}>{t('One design')}<small>{t('LoomLab picks the inks')}</small></button>
        <button role="tab" aria-selected={way === 'lineart'} className={way === 'lineart' ? 'on' : ''}
          onClick={() => setWay('lineart')}>{t('Line art + reference')}<small>{t('your outlines, the reference’s colours')}</small></button>
      </div>
      {way === 'lineart' ? <LineArtForm w={w} /> : showDesign
        ? <div className="canvas"><img src={screenUrl(original!.url)} alt="design" /></div>
        : <div className="drop" onClick={() => input.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) onUpload(f); }}>
            <h2>{t('Drop a design here')}</h2>
            <p>{t('PNG · JPG · WEBP · TIFF · PSD — up to 80 MB')}</p>
            {resumable && !original && (
              <div className="resume" onClick={e => e.stopPropagation()}>
                <span>{t('Continue your last job')}<small>{jobSummary(resumable, Date.now())}</small></span>
                <button className="primary" disabled={busy} onClick={resumeJob}>{t('Continue')}</button>
                <button className="mini" disabled={busy} onClick={forgetJob} title={t('Forget it and start a new design')}>✕</button>
              </div>
            )}
            <div className="row">
              <button className="primary" disabled={busy} onClick={e => { e.stopPropagation(); input.current?.click(); }}>{t('Choose file')}</button>
              <button className="secondary" disabled={busy} onClick={e => { e.stopPropagation(); loadSample(); }}>{t('Try a sample')}</button>
            </div>
          </div>}
      {way === 'design' && !original && (
        <ol className="how">
          {HOW.map(([name, text], i) => <li key={name}><b><span>{i + 1}</span>{t(name)}</b><p>{t(text)}</p></li>)}
        </ol>
      )}
      {way === 'design' && showDesign && <div className="row center"><button className="primary" onClick={() => go('Reduce')}>{t('Continue to Reduce →')}</button><button className="secondary" onClick={() => input.current?.click()}>{t('Replace')}</button></div>}
    </section>
  );
}

/** Two files and a few settings; the engine fills, the Reduce step shows it. */
function LineArtForm({ w }: { w: LoomLab }) {
  const { busy, busyLabel, onLineFill, fillInfo, go } = w;
  const t = useT();
  const [line, setLine] = useState<File>();
  const [ref, setRef] = useState<File>();
  const [maxColors, setMaxColors] = useState(16);
  const [lineColor, setLineColor] = useState('');
  const [force, setForce] = useState(false);
  const lineUrl = useObjectUrl(line);
  const refUrl = useObjectUrl(ref);
  return (
    <div className="lineart">
      <div className="lineart-pair">
        <FilePick label={t('Line art')} hint={t('black outlines on white')} url={lineUrl} file={line} onPick={setLine} busy={busy} />
        <FilePick label={t('Coloured reference')} hint={t('the same design, same crop, in colour')} url={refUrl} file={ref} onPick={setRef} busy={busy} />
      </div>
      <div className="lineart-opts">
        <label>{t('Max colours')}
          <input type="number" min={2} max={20} value={maxColors} disabled={busy}
            onChange={e => setMaxColors(Math.max(2, Math.min(20, Number(e.target.value) || 16)))} />
          <small>{t('used only when the reference has shading')}</small>
        </label>
        <label>{t('Outline colour')}
          <input type="text" placeholder="auto" value={lineColor} disabled={busy} maxLength={7}
            onChange={e => setLineColor(e.target.value.trim())} />
          <small>{t('auto = the colour under the lines in the reference, or a code like #120F06')}</small>
        </label>
        <label className="check">
          <input type="checkbox" checked={force} disabled={busy} onChange={e => setForce(e.target.checked)} />
          {t('Fill even if the two images do not line up well')}
        </label>
      </div>
      <p className="hint">{t('Made at 3535 × 3535 px, 300 DPI (11.78 in), with no smoothing: every corner and dot stays as drawn.')}</p>
      <div className="row center">
        <button className="primary" disabled={busy || !line || !ref}
          onClick={() => line && ref && onLineFill(line, ref, maxColors, lineColor || 'auto', force)}>
          {t(busy && busyLabel === 'Filling colours…' ? busyLabel : 'Fill colours →')}
        </button>
        {fillInfo && <button className="secondary" disabled={busy} onClick={() => go('Reduce')}>{t('Continue to Reduce →')}</button>}
      </div>
    </div>
  );
}

function FilePick({ label, hint, url, file, onPick, busy }:
  { label: string; hint: string; url?: string; file?: File; onPick: (f: File) => void; busy: boolean }) {
  return (
    <label className={'file-box' + (file ? ' has' : '')}
      onDragOver={e => e.preventDefault()}
      onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) onPick(f); }}>
      <input type="file" accept="image/*" hidden disabled={busy}
        onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); }} />
      {url ? <img src={url} alt={label} /> : <span className="file-plus">+</span>}
      <b>{label}</b>
      <small>{file ? file.name : hint}</small>
    </label>
  );
}

/** A preview URL for a picked file, released when it changes. */
function useObjectUrl(file?: File) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!file) { setUrl(undefined); return; }
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return url;
}
