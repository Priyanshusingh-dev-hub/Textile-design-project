import { useRef, useState } from 'react';
import { post, uploadFile, downloadPackage, downloadSvg, imageUrl } from './api';
import type { ImageInfo, Palette, Layer, ReduceResult, Step } from './types';
import { STEPS } from './types';
import { useAsyncStatus } from './hooks/useAsyncStatus';
import { BeforeAfter } from './components/BeforeAfter';
import { Zoomable } from './components/Zoomable';

export default function App() {
  const [step, setStep] = useState<Step>('Upload');
  const [reached, setReached] = useState(0);              // furthest unlocked step index
  const [original, setOriginal] = useState<ImageInfo>();
  const [reducedId, setReducedId] = useState<string>();   // current flat image id
  const [reducedUrl, setReducedUrl] = useState<string>();
  const [palette, setPalette] = useState<Palette[]>([]);
  const [accuracy, setAccuracy] = useState<{ accuracy: number; deltaE: number }>();
  const [colorCount, setColorCount] = useState(6);
  const [smoothing, setSmoothing] = useState(1);
  const [suggested, setSuggested] = useState<number>();
  const [layers, setLayers] = useState<Layer[]>([]);
  const [mergeFrom, setMergeFrom] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [includeVector, setIncludeVector] = useState(false);
  const [message, setMessage] = useState('Upload a design to begin.');
  const input = useRef<HTMLInputElement>(null);
  const { status, run, busy } = useAsyncStatus();

  const go = (s: Step) => { const i = STEPS.indexOf(s); setReached(r => Math.max(r, i)); setStep(s); };

  function loadImported(x: ImageInfo) {
    setOriginal(x); setReducedId(undefined); setReducedUrl(undefined);
    setPalette([]); setAccuracy(undefined);
    if (x.layers && x.layers.length) {
      // A multichannel PSD arrives already separated — skip reduce.
      setLayers(x.layers); setReached(STEPS.indexOf('Export')); setStep('Export');
      setMessage(`Imported ${x.layers.length} ready-made screens from this PSD — go straight to export.`);
    } else {
      setLayers([]); go('Reduce');
      setMessage(`Imported ${x.file_name || 'design'} (${x.width}×${x.height}). Choose an ink count and reduce.`);
    }
  }

  const autoSuggest = async (x: ImageInfo) => {
    if (x.layers) return;
    try {
      const sug = await post<{ suggested: number }>('/colors/suggest', { image_id: x.image_id });
      setSuggested(sug.suggested); setColorCount(sug.suggested);
    } catch { /* suggestion is best-effort */ }
  };
  const onUpload = (f: File) => run(async () => { const x = await uploadFile<ImageInfo>(f); loadImported(x); await autoSuggest(x); });
  const loadSample = () => run(async () => { const x = await post<ImageInfo>('/image/sample', {}); loadImported(x); await autoSuggest(x); });

  const suggestCount = () => run(async () => {
    if (!original) return;
    const sug = await post<{ suggested: number; curve: { colors: number; accuracy: number }[] }>('/colors/suggest', { image_id: original.image_id });
    setSuggested(sug.suggested); setColorCount(sug.suggested);
    setMessage(`Suggested ${sug.suggested} inks — best balance of match vs number of screens.`);
  });

  const doReduce = () => run(async () => {
    if (!original) return;
    const x = await post<ReduceResult>('/colors/reduce', { image_id: original.image_id, colors: colorCount, smoothing });
    setReducedId(x.image_id); setReducedUrl(x.url);
    setPalette(x.palette.map(p => ({ ...p, locked: false })));
    setAccuracy({ accuracy: x.accuracy, deltaE: x.delta_e }); setMergeFrom(null);
    setMessage(`Reduced to ${x.palette.length} inks — ${x.accuracy}% match (ΔE2000 ${x.delta_e}). Fine-tune the palette or continue.`);
  });

  const refreshAccuracy = async (pal: Palette[]) => {
    if (!original) return;
    const a = await post<{ accuracy: number; delta_e: number }>('/colors/accuracy',
      { image_id: original.image_id, palette: pal.map(p => p.hex) });
    setAccuracy({ accuracy: a.accuracy, deltaE: a.delta_e });
  };

  const recolor = (i: number, hex: string) => run(async () => {
    if (!reducedId || palette[i].locked || hex.toUpperCase() === palette[i].hex.toUpperCase()) return;
    const x = await post<ImageInfo>('/colors/remap', { image_id: reducedId, source: palette[i].hex, target: hex });
    setReducedId(x.image_id); setReducedUrl(x.url);
    const next = palette.map((p, idx) => idx === i ? { ...p, hex: hex.toUpperCase() } : p);
    setPalette(next); await refreshAccuracy(next);
    setMessage(`Ink ${i + 1} recoloured to ${hex.toUpperCase()}.`);
  });

  const mergeInto = (target: number) => run(async () => {
    if (mergeFrom === null || !reducedId) return;
    const from = mergeFrom;
    if (from === target || palette[target].locked || palette[from].locked) { setMergeFrom(null); return; }
    const x = await post<ImageInfo>('/colors/remap',
      { image_id: reducedId, source: palette[from].hex, target: palette[target].hex });
    setReducedId(x.image_id); setReducedUrl(x.url);
    const next = palette
      .map((p, idx) => idx === target
        ? { ...p, coverage: Math.round((p.coverage + palette[from].coverage) * 100) / 100, pixels: p.pixels + palette[from].pixels }
        : p)
      .filter((_, idx) => idx !== from);
    setPalette(next); setMergeFrom(null); await refreshAccuracy(next);
    setMessage(`Merged into one ink — ${next.length} inks now.`);
  });

  const toggleLock = (i: number) =>
    setPalette(p => p.map((s, idx) => idx === i ? { ...s, locked: !s.locked } : s));

  const refreshPreview = async (ls: Layer[]) => {
    const on = ls.filter(l => !l.skip);
    if (!on.length) { setPreviewUrl(undefined); return; }
    const pv = await post<ImageInfo>('/separation/preview', { layers: on.map(l => ({ id: l.id, color: l.color })) });
    setPreviewUrl(pv.url);
  };

  const doSeparate = () => run(async () => {
    if (!reducedId) return;
    const x = await post<{ layers: Layer[] }>('/separation/create',
      { image_id: reducedId, palette: palette.map(p => p.hex), cleanup: 0 });
    setLayers(x.layers); await refreshPreview(x.layers); go('Separate');
    setMessage(`${x.layers.length} clean plates ready — one ink per screen, no overlap. This preview is exactly what they print.`);
  });

  const toggleSkip = (id: string) => {
    const next = layers.map(l => l.id === id ? { ...l, skip: !l.skip } : l);
    setLayers(next); run(() => refreshPreview(next));
  };

  const printing = layers.filter(l => !l.skip);

  const exportLayers = () => printing.map(l => ({ id: l.id, name: l.name, color: l.color }));

  const doExport = () => run(async () => {
    if (!printing.length) return;
    await downloadPackage(
      { layers: exportLayers(), dpi: 300, reg_marks: true, vector: includeVector, composite_image_id: reducedId },
      'loomlab-production.zip');
    setMessage(`Production package downloaded — ${printing.length} plate${printing.length > 1 ? 's' : ''}, 300 DPI TIFF screens${includeVector ? ', vector SVG' : ''} and a colour proof.`);
  });

  const doExportSvg = () => run(async () => {
    if (!printing.length) return;
    await downloadSvg({ layers: exportLayers() }, 'loomlab-design.svg');
    setMessage('Vector SVG downloaded — scalable outlines of every ink.');
  });

  const proofUrl = previewUrl || (original?.layers ? original.url : reducedUrl);

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="loom">L</span><div>LoomLab<small>COLOR SEPARATION</small></div></div>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s} className={s === step ? 'on' : i <= reached ? 'done' : ''}>
              <button disabled={i > reached || busy} onClick={() => setStep(s)}><b>{i + 1}</b><span>{s}</span></button>
            </li>
          ))}
        </ol>
        <div className={'badge s-' + status.state}>{status.state === 'processing' ? 'WORKING' : status.state === 'failed' ? 'ERROR' : status.state === 'done' ? 'DONE' : 'READY'}</div>
      </header>

      <main>
        {step === 'Upload' && (
          <section className="stage">
            {original && !original.layers
              ? <div className="canvas"><img src={imageUrl(original.url)} alt="design" /></div>
              : <div className="drop" onClick={() => input.current?.click()}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) onUpload(f); }}>
                  <h2>Drop a design here</h2>
                  <p>PNG · JPG · WEBP · TIFF · PSD — up to 80 MB</p>
                  <div className="row">
                    <button className="primary" disabled={busy} onClick={e => { e.stopPropagation(); input.current?.click(); }}>Choose file</button>
                    <button className="secondary" disabled={busy} onClick={e => { e.stopPropagation(); loadSample(); }}>Try a sample</button>
                  </div>
                </div>}
            {original && !original.layers && <div className="row center"><button className="primary" onClick={() => go('Reduce')}>Continue to Reduce →</button><button className="secondary" onClick={() => input.current?.click()}>Replace</button></div>}
          </section>
        )}

        {step === 'Reduce' && (
          <section className="stage two">
            <div className="stage-main">
              {reducedUrl && original
                ? <BeforeAfter before={imageUrl(original.url)} after={imageUrl(reducedUrl)} />
                : original ? <div className="canvas"><img src={imageUrl(original.url)} alt="design" /></div>
                : <div className="canvas empty">Upload a design first.</div>}
            </div>
            <aside className="panel">
              <h3>Reduce colors</h3>
              <label>Print inks<output>{colorCount}</output></label>
              <input type="range" min={2} max={20} value={colorCount} disabled={busy}
                onChange={e => setColorCount(Number(e.target.value))} />
              <div className="suggest-row">
                {suggested ? <span className="suggest-chip" title="Recommended balance of match vs number of screens">✨ suggested: {suggested}</span> : <span />}
                <button className="mini" disabled={busy || !original} onClick={suggestCount}>{suggested ? 're-suggest' : '✨ suggest count'}</button>
              </div>
              <label>Texture cleanup</label>
              <select className="select" value={smoothing} disabled={busy}
                onChange={e => setSmoothing(Number(e.target.value))}>
                <option value={0}>Off — clean / vector art</option>
                <option value={1}>Light — painterly / AI (default)</option>
                <option value={2}>Medium — scans, fabric weave</option>
                <option value={3}>Strong — very noisy</option>
              </select>
              <button className="primary wide" disabled={busy || !original} onClick={doReduce}>
                {reducedUrl ? 'Re-reduce' : 'Reduce design'}
              </button>
              {accuracy && (
                <div className="accuracy">
                  <div className="accuracy-bar"><span style={{ width: accuracy.accuracy + '%' }} /></div>
                  <b>{accuracy.accuracy}% match</b>
                  <small>mean ΔE2000 {accuracy.deltaE} vs original</small>
                </div>
              )}
              {!!palette.length && (
                <>
                  <div className="palette-head">
                    <span>Palette · {palette.length} inks</span>
                    {mergeFrom !== null && <em>pick an ink to merge into…</em>}
                  </div>
                  <div className="palette">
                    {palette.map((p, i) => (
                      <div className={'swatch' + (mergeFrom === i ? ' picking' : '')} key={p.hex + i}>
                        <label className="swatch-color" style={{ background: p.hex }} title={p.locked ? 'Locked' : 'Click to recolor this ink'}>
                          {!p.locked && <span className="swatch-edit">✎</span>}
                          <input type="color" value="#000000" disabled={busy || p.locked}
                            onChange={e => recolor(i, e.target.value)} />
                        </label>
                        <div className="swatch-info">
                          <b>{p.hex}</b>
                          <small>{p.coverage}% · Ink {i + 1}</small>
                          <div className="coverage-bar"><span style={{ width: Math.min(100, p.coverage) + '%' }} /></div>
                        </div>
                        <div className="swatch-tools">
                          <button className="mini" title={p.locked ? 'Unlock' : 'Lock'} onClick={() => toggleLock(i)}>{p.locked ? '🔒' : '🔓'}</button>
                          {palette.length > 2 && !p.locked && (
                            mergeFrom === null
                              ? <button className="mini" title="Merge this ink into another" disabled={busy} onClick={() => setMergeFrom(i)}>merge</button>
                              : mergeFrom === i
                                ? <button className="mini" onClick={() => setMergeFrom(null)}>cancel</button>
                                : <button className="mini go" disabled={busy} onClick={() => mergeInto(i)}>→ here</button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="hint">Click a swatch to recolor · <b>merge</b> combines two inks · <b>🔓</b> locks an ink. Re-reduce to start the palette over.</p>
                  <button className="primary wide" disabled={busy} onClick={doSeparate}>Separate into plates →</button>
                </>
              )}
            </aside>
          </section>
        )}

        {step === 'Separate' && (
          <section className="stage two">
            <div className="stage-main">
              <div className="preview-head">Combined result — exactly what your {printing.length} screen{printing.length !== 1 ? 's' : ''} will print</div>
              <Zoomable>
                {previewUrl ? <img src={imageUrl(previewUrl)} alt="combined print preview" />
                  : <div className="canvas empty">Every ink hidden — nothing prints.</div>}
              </Zoomable>
              <div className="plate-strip">
                {layers.map((l, i) => (
                  <figure className={'plate-chip' + (l.skip ? ' skipped' : '')} key={l.id}
                    title={l.skip ? 'Hidden (fabric) — click to print' : 'Printing — click to mark as fabric'}
                    onClick={() => !busy && toggleSkip(l.id)}>
                    <div className="plate-chip-img"><img src={imageUrl(l.plate_url || l.url)} alt={l.name} /></div>
                    <figcaption><span className="plate-swatch" style={{ background: l.color }} />{i + 1}<small>{l.coverage}%</small></figcaption>
                  </figure>
                ))}
              </div>
            </div>
            <aside className="panel">
              <h3>Separation</h3>
              <p className="muted">Every pixel prints on exactly one plate — no overlap, no gaps. The preview above is these screens stacked back together, so it <b>is</b> your final print. Click a plate to hide your <b>fabric</b> colour (it won't be printed).</p>
              <div className="summary">
                <div><small>PRINTING</small><b>{printing.length}{printing.length !== layers.length ? ` / ${layers.length}` : ''}</b></div>
                <div><small>MATCH</small><b>{accuracy ? accuracy.accuracy + '%' : '—'}</b></div>
              </div>
              <button className="primary wide" disabled={busy || !printing.length} onClick={() => go('Export')}>Continue to Export →</button>
              {!original?.layers && <button className="secondary wide" disabled={busy} onClick={() => go('Reduce')}>← Back to palette</button>}
            </aside>
          </section>
        )}

        {step === 'Export' && (
          <section className="stage two">
            <div className="stage-main">
              <div className="preview-head">Final proof — {printing.length} ink{printing.length !== 1 ? 's' : ''}, print-ready</div>
              <Zoomable>
                {proofUrl ? <img src={imageUrl(proofUrl)} alt="proof" /> : <div className="canvas empty">Separate a design first.</div>}
              </Zoomable>
            </div>
            <aside className="panel">
              <h3>Export production package</h3>
              <ul className="pack-list">
                <li><b>plates/</b> — colour PNG proof per ink</li>
                <li><b>screens/</b> — B&amp;W TIFF, 300 DPI</li>
                <li>registration marks on every screen</li>
                <li><b>proof.png</b> — full-colour composite</li>
                {includeVector && <li><b>vector/</b> — scalable SVG outlines</li>}
              </ul>
              <div className="summary">
                <div><small>PLATES</small><b>{printing.length}</b></div>
                <div><small>DPI</small><b>300</b></div>
              </div>
              {printing.length !== layers.length && <p className="muted">{layers.length - printing.length} ink marked as fabric won't be printed.</p>}
              <label className="check">
                <input type="checkbox" checked={includeVector} disabled={busy} onChange={e => setIncludeVector(e.target.checked)} />
                Include scalable vector (SVG) outlines
              </label>
              <button className="primary wide" disabled={busy || !printing.length} onClick={doExport}>⬇ Download .zip</button>
              <button className="secondary wide" disabled={busy || !printing.length} onClick={doExportSvg}>⬇ Vector SVG only</button>
              <button className="secondary wide" disabled={busy} onClick={() => go('Separate')}>← Back to plates</button>
            </aside>
          </section>
        )}
      </main>

      <footer>
        <span className={status.state === 'failed' ? 'err' : ''}>{status.state === 'failed' ? status.message : message}</span>
        <span>{original ? `${original.width}×${original.height}` : 'no design'}{palette.length ? ` · ${palette.length} inks` : ''}</span>
      </footer>

      <input ref={input} hidden type="file"
        accept="image/png,image/jpeg,image/webp,image/tiff,.psd,image/vnd.adobe.photoshop"
        onChange={e => e.target.files?.[0] && onUpload(e.target.files[0])} disabled={busy} />
    </div>
  );
}
