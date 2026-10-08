import { useEffect, useState } from 'react';
import { screenUrl } from '../../api';
import { jobSummary } from '../../lib/job';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';
import { FILL_METHODS, type FillMethod } from '../../lib/fill';
import { NUMBER_DETAILS, parseInches, millPixels } from '../../lib/numbering';
import type { NumberDetail } from '../../types';

const HOW = [
  ['Upload', 'Your design file — PNG, JPG, TIFF or a layered PSD.'],
  ['Reduce', 'Down to the inks you will print. LoomLab suggests how many.'],
  ['Separate', 'One screen per ink. Pick the cloth colour, change any ink.'],
  ['Export', 'Films at print size, proof, job sheet — and a quote.'],
];

type Way = 'design' | 'lineart' | 'number';

/** Step 1: drop a design, or continue the last job — or the second way in:
 *  line art + a coloured reference of the same design — or the third: one
 *  coloured design numbered by the textile tool (sketch, plates, mill file). */
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
    numberInfo,
  } = w;
  const t = useT();
  const [way, setWay] = useState<Way>(fillInfo ? 'lineart' : numberInfo ? 'number' : 'design');
  const showDesign = original && !original.layers;
  return (
    <section className="stage">
      <div className="way-tabs" role="tablist">
        <button role="tab" aria-selected={way === 'design'} className={way === 'design' ? 'on' : ''}
          onClick={() => setWay('design')}>{t('One design')}<small>{t('LoomLab picks the inks')}</small></button>
        <button role="tab" aria-selected={way === 'lineart'} className={way === 'lineart' ? 'on' : ''}
          onClick={() => setWay('lineart')}>{t('Line art + reference')}<small>{t('your outlines, the reference’s colours')}</small></button>
        <button role="tab" aria-selected={way === 'number'} className={way === 'number' ? 'on' : ''}
          onClick={() => setWay('number')}>{t('Numbered sketch + mill file')}<small>{t('one design: sketch, plates, PSD, mill size')}</small></button>
      </div>
      {way === 'lineart' ? <LineArtForm w={w} /> : way === 'number' ? <NumberForm w={w} /> : showDesign
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
  const [method, setMethod] = useState<FillMethod>('auto');
  const lineUrl = useObjectUrl(line);
  const refUrl = useObjectUrl(ref);
  return (
    <div className="lineart">
      <div className="lineart-pair">
        <FilePick label={t('Line art')} hint={t('black outlines on white')} url={lineUrl} file={line} onPick={setLine} busy={busy} />
        <FilePick label={t('Coloured reference')} hint={t('the same design, same crop, in colour')} url={refUrl} file={ref} onPick={setRef} busy={busy} />
      </div>
      <div className="lineart-opts">
        <label>{t('Method')}
          <select value={method} disabled={busy} onChange={e => setMethod(e.target.value as FillMethod)}>
            {FILL_METHODS.map(m => <option key={m.value} value={m.value}>{t(m.label)}</option>)}
          </select>
          <small>{t(FILL_METHODS.find(m => m.value === method)!.hint)}</small>
        </label>
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
        {(method === '1' || method === '4') && <label className="check">
          <input type="checkbox" checked={force} disabled={busy} onChange={e => setForce(e.target.checked)} />
          {t('Fill even if the two images do not line up well')}
        </label>}
      </div>
      <p className="hint">{t('Made at 3535 × 3535 px, 300 DPI (11.78 in), with no smoothing: every corner and dot stays as drawn.')}</p>
      <div className="row center">
        <button className="primary" disabled={busy || !line || !ref}
          onClick={() => line && ref && onLineFill(line, ref, maxColors, lineColor || 'auto', force, method)}>
          {t(busy && busyLabel === 'Making the design…' ? busyLabel : 'Fill colours →')}
        </button>
        {fillInfo && <button className="secondary" disabled={busy} onClick={() => go('Reduce')}>{t('Continue to Reduce →')}</button>}
      </div>
    </div>
  );
}

/** One coloured design and a few settings; the textile tool numbers it and
 *  makes every file, the Reduce step shows the result with the zip. */
function NumberForm({ w }: { w: LoomLab }) {
  const { busy, busyLabel, onNumber, numberInfo, go } = w;
  const t = useT();
  const [file, setFile] = useState<File>();
  const [inks, setInks] = useState(8);
  const [detail, setDetail] = useState<NumberDetail>('normal');
  const [mergeShades, setMergeShades] = useState(true);
  const [inches, setInches] = useState('');
  const url = useObjectUrl(file);
  const size = parseInches(inches);
  return (
    <div className="lineart">
      <div className="lineart-pair">
        <FilePick label={t('Coloured design')} hint={t('an AI picture or any flat-colour design')} url={url} file={file} onPick={setFile} busy={busy} />
      </div>
      <div className="lineart-opts">
        <label>{t('Max inks')}
          <input type="number" min={2} max={20} value={inks} disabled={busy}
            onChange={e => setInks(Math.max(2, Math.min(20, Number(e.target.value) || 8)))} />
          <small>{t('fewer when the design has fewer colours')}</small>
        </label>
        <label>{t('Detail')}
          <select value={detail} disabled={busy} onChange={e => setDetail(e.target.value as NumberDetail)}>
            {NUMBER_DETAILS.map(d => <option key={d.value} value={d.value}>{t(d.label)}</option>)}
          </select>
          <small>{t(NUMBER_DETAILS.find(d => d.value === detail)!.hint)}</small>
        </label>
        <label>{t('Mill repeat size (inches)')}
          <input type="text" placeholder="23.5x20.7" value={inches} disabled={busy} maxLength={20}
            onChange={e => setInches(e.target.value)} />
          <small className={size === 'bad' ? 'warn' : undefined}>{size === 'bad'
            ? t('Write width x height in inches, like 23.5x20.7 (1 to 120).')
            : size ? t('Also made at exactly {w} × {h} px, 300 DPI: cut to that shape, never stretched.', { w: millPixels(size)[0], h: millPixels(size)[1] })
            : t('optional: empty = only the 11.78 in working file')}</small>
        </label>
        <label className="check">
          <input type="checkbox" checked={mergeShades} disabled={busy} onChange={e => setMergeShades(e.target.checked)} />
          {t('Shades of one colour on one screen')}
        </label>
      </div>
      <p className="hint">{t('Makes the numbered sketch, the colours list, one plate per ink, the mill’s TIF and a Photoshop file, all in one zip. Takes 1 to 3 minutes.')}</p>
      <div className="row center">
        <button className="primary" disabled={busy || !file || size === 'bad'}
          onClick={() => file && onNumber(file, inks, detail, mergeShades, inches)}>
          {t(busy && busyLabel === 'Numbering the design…' ? busyLabel : 'Number the design →')}
        </button>
        {numberInfo && <button className="secondary" disabled={busy} onClick={() => go('Reduce')}>{t('See the result →')}</button>}
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
