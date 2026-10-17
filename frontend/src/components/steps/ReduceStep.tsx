import { useEffect, useState } from 'react';
import { screenUrl } from '../../api';
import { inkOwner, matchLabel } from '../../lib/inks';
import { BeforeAfter } from '../BeforeAfter';
import { repeatNote, SMALL_CHOICES } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';
import { alignmentVerdict, methodNote, offerReferenceColours } from '../../lib/fill';
import { Trials } from '../Trials';
import { inkNames, namesStale, zipHref, zipStale } from '../../lib/numbering';

/** Step 2: bring the design down to a printable number of inks. */
export function ReduceStep({ w }: { w: LoomLab }) {
  const {
    original,
    reducedUrl,
    palette,
    accuracy,
    repeat,
    history,
    library,
    matches,
    setShowLibrary,
    small,
    smallBelow,
    setSmallBelow,
    colorCount,
    setColorCount,
    smoothing,
    setSmoothing,
    suggested,
    mergeFrom,
    setMergeFrom,
    fabric,
    busy,
    busyLabel,
    go,
    suggestCount,
    doReduce,
    printDots,
    toggleDots,
    recolor,
    mergeInto,
    mergePair,
    removeSmall,
    smallNote,
    inkName,
    swap,
    useMyInks,
    undo,
    toggleLock,
    doSeparate,
    cleanup,
    matchVerdictNote,
    softEdgeWarning,
    merge,
    at,
    fillInfo,
    numberInfo,
    reducedId,
    rebuildNumber,
  } = w;
  const t = useT();
  return (
    <section className="stage two">
      <div className="stage-main">
        {reducedUrl && original
          ? <BeforeAfter before={screenUrl(original.url)} after={screenUrl(reducedUrl)} />
          : original ? <div className="canvas"><img src={screenUrl(original.url)} alt="design" /></div>
          : <div className="canvas empty">{t('Upload a design first.')}</div>}
      </div>
      <aside className="panel">
        <h3>{t(numberInfo ? 'Numbered design' : fillInfo && fillInfo.method !== 0 ? 'Filled from line art' : 'Reduce colors')}</h3>
        {fillInfo && fillInfo.method === 0 && <Trials w={w} />}
        {numberInfo ? <NumberCard w={w} /> : fillInfo && fillInfo.method !== 0 ? <FillCard w={w} /> : <>
        <label>{t('Print inks')}<output>{colorCount}</output></label>
        <input type="range" min={1} max={20} value={colorCount} disabled={busy}
          onChange={e => setColorCount(Number(e.target.value))} />
        <div className="suggest-row">
          {suggested ? <span className="suggest-chip" title={t('Recommended balance of match vs number of screens')}>✨ {t('suggested: {n}', { n: suggested })}</span> : <span />}
          <button className="mini" disabled={busy || !original} onClick={suggestCount}>{t(suggested ? 're-suggest' : '✨ suggest count')}</button>
        </div>
        <label>{t('Texture cleanup')}</label>
        <select className="select" value={smoothing} disabled={busy}
          onChange={e => setSmoothing(Number(e.target.value))}>
          <option value={0}>{t('Off — keeps every outline and dot')}</option>
          <option value={1}>{t('Light — grainy scans')}</option>
          <option value={2}>{t('Medium — heavy grain, fabric weave')}</option>
          <option value={3}>{t('Strong — very noisy')}</option>
        </select>
        {cleanup && <p className={cleanup.tone + ' cleanup-note'}>{t(cleanup.text)}</p>}
        <label className="check dots-row" title={t('For photo-like shading: the inks are placed as fine dots that mix into the shading seen from a step away. Still one ink per pixel; needs a fine mesh.')}>
          <input type="checkbox" checked={printDots} disabled={busy || !original || !!original.layers?.length}
            onChange={e => toggleDots(e.target.checked)} />
          {t('Print as dots (index separation)')}
        </label>
        <button className={(reducedUrl ? 'secondary' : 'primary') + ' wide'} disabled={busy || !original} onClick={() => doReduce()}>
          {t(busy && busyLabel === 'Reducing…' ? busyLabel : reducedUrl ? 'Re-reduce' : 'Reduce design')}
        </button>
        </>}
        {accuracy && (
          <div className="accuracy">
            <div className="accuracy-bar"><span style={{ width: accuracy.accuracy + '%' }} /></div>
            <b>{t('{n}% match', { n: accuracy.accuracy })}</b>
            <small>{t('mean ΔE2000 {d} vs original', { d: accuracy.deltaE })}{printDots ? ' · ' + t('seen from a step away (dots)') : ''}</small>
          </div>
        )}
        {matchVerdictNote && <p className={matchVerdictNote.tone === 'warn' ? 'warn' : 'hint'}>{t(matchVerdictNote.text)}</p>}
        {softEdgeWarning && <p className="warn">{softEdgeWarning}</p>}
        {repeatNote(repeat, t) && <p className="hint">{repeatNote(repeat, t)}</p>}
        {merge && (
          <div className="hint merge-hint">
            <span className="pair">
              <span className="plate-swatch" style={{ background: palette[merge.keep].hex }} />
              <span className="plate-swatch" style={{ background: palette[merge.drop].hex }} />
            </span>
            <p>{t('Inks {a} and {b} look almost the same (ΔE {d}). Merging them saves a screen; the match goes from {x}% to {y}%.',
              { a: merge.keep + 1, b: merge.drop + 1, d: merge.delta_e, x: accuracy?.accuracy ?? '', y: merge.accuracy })}</p>
            <button className="mini go" disabled={busy} onClick={() => mergePair(merge.drop, merge.keep)}>{t('Merge them')}</button>
          </div>
        )}
        {/* the way forward sits under the score, not below every palette
            row — at 10 inks on a laptop screen it was off the bottom */}
        {!!palette.length && (
          <button className="primary wide" disabled={busy} onClick={doSeparate}>
            {t(busy && busyLabel === 'Separating…' ? busyLabel : 'Separate into plates →')}
          </button>
        )}
        {smallNote && (
          <div className="hint small-hint">
            <p>{smallNote.text}</p>
            <div className="small-row">
              {smallNote.action && <button className="mini go" disabled={busy} onClick={removeSmall}>{smallNote.action}</button>}
              <label>{t('small = under')}
                <select className="select mini-select" value={smallBelow} disabled={busy}
                  onChange={e => setSmallBelow(Number(e.target.value))}>
                  {SMALL_CHOICES.map(v => <option key={v} value={v}>{v}%</option>)}
                </select>
              </label>
            </div>
          </div>
        )}
        {!!palette.length && (
          <>
            <div className="palette-head">
              <span>{t('Palette · {n} inks', { n: palette.length })}</span>
              {mergeFrom !== null && <em>{t('pick an ink to merge into…')}</em>}
              {mergeFrom === null && !!history.length && (
                <button className="mini" disabled={busy} onClick={undo}
                  title={`Undo the ${history[history.length - 1].label} (Ctrl+Z)`}>{t('↶ Undo')}</button>
              )}
              <button className="mini" onClick={() => setShowLibrary(true)}
                title={t('The inks your mill already has — match the palette to them')}>{t('My inks ({n})', { n: library.length })}</button>
            </div>
            {numberInfo && (zipStale(numberInfo, reducedId) || namesStale(numberInfo, inkNames(palette, inkName))) && (   /* where the edits are made: the card's line is above the fold */
              <button className="secondary wide lib-all" disabled={busy} onClick={rebuildNumber}>{t('↻ Put my palette changes in the zip')}</button>
            )}
            {swap.count > 0 && (
              <button className="secondary wide lib-all" disabled={busy} onClick={useMyInks}>
                {t('Use my inks for {n} of {m}', { n: swap.count, m: palette.length })}
              </button>
            )}
            <div className="palette">
              {palette.map((p, i) => (
                <div className={'swatch' + (mergeFrom === i ? ' picking' : '')} key={p.hex + i}>
                  <label className="swatch-color" style={{ background: p.hex }} title={t(p.locked ? 'Locked' : 'Click to recolor this ink')}>
                    {!p.locked && <span className="swatch-edit">✎</span>}
                    <input type="color" value="#000000" disabled={busy || p.locked}
                      onChange={e => recolor(i, e.target.value)} />
                  </label>
                  <div className="swatch-info">
                    <b>{p.hex}</b>
                    <small>{p.coverage}% · {inkName(i) ?? `Ink ${i + 1}`}</small>
                    {(() => {
                      const m = matches[i], label = matchLabel(m);
                      if (!m || !label || label.tone === 'same' || p.name) return null;
                      const owner = inkOwner(palette, m.hex, i);
                      if (label.tone === 'close' && owner >= 0)
                        return <span className="lib-match far" title={t('Using it here would print both as one ink')}>
                          <span className="dot" style={{ background: m.hex }} />≈ {m.name} · already ink {owner + 1}</span>;
                      return label.tone === 'close' && !p.locked
                        ? <button className="lib-match close" disabled={busy} title={`Use ${m.name} (${m.hex})`}
                            onClick={() => recolor(i, m.hex, m.name)}>
                            <span className="dot" style={{ background: m.hex }} />{label.text}</button>
                        : <span className={'lib-match ' + label.tone}>
                            <span className="dot" style={{ background: m.hex }} />{label.text}</span>;
                    })()}
                    <div className="coverage-bar"><span style={{ width: Math.min(100, p.coverage) + '%' }} /></div>
                  </div>
                  <div className="swatch-tools">
                    <button className="mini" title={t(p.locked ? 'Unlock' : 'Lock')} onClick={() => toggleLock(i)}>{p.locked ? '🔒' : '🔓'}</button>
                    {palette.length > 2 && !p.locked && (
                      mergeFrom === null
                        ? <button className="mini" title={t('Merge this ink into another')} disabled={busy} onClick={() => setMergeFrom(i)}>{t('merge')}</button>
                        : mergeFrom === i
                          ? <button className="mini" onClick={() => setMergeFrom(null)}>{t('cancel')}</button>
                          : <button className="mini go" disabled={busy} onClick={() => mergeInto(i)}>{t('→ here')}</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <p className="hint">{t('Click a swatch to recolor · merge combines two inks · 🔓 locks an ink. Re-reduce to start the palette over.')}</p>
          </>
        )}
      </aside>
    </section>
  );
}


/** What the numbering run made, in place of the reduce controls: the
 *  numbered sketch, the inks (and any shading put on its colour's screen), the
 *  mill-size file, and the zip of every file. */
function NumberCard({ w }: { w: LoomLab }) {
  const { numberInfo: n, go, busy, reducedId, rebuildNumber, palette, inkName } = w;
  const t = useT();
  const [inspect, setInspect] = useState<{ title: string; url: string; isFilm?: boolean } | null>(null);
  const [inverted, setInverted] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [copiedEstimate, setCopiedEstimate] = useState(false);

  useEffect(() => {
    if (!inspect) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setInspect(null);
        setInverted(false);
        setZoomLevel(1);
      } else if (e.key === 'i' || e.key === 'I') {
        if (inspect.isFilm) setInverted(v => !v);
      } else if (e.key === '+' || e.key === '=') {
        setZoomLevel(z => Math.min(5, Number((z + 0.25).toFixed(2))));
      } else if (e.key === '-' || e.key === '_') {
        setZoomLevel(z => Math.max(0.5, Number((z - 0.25).toFixed(2))));
      } else if (e.key === '0') {
        setZoomLevel(1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [inspect]);

  const closeInspect = () => {
    setInspect(null);
    setInverted(false);
    setZoomLevel(1);
  };

  const handleCopyEstimate = () => {
    if (!n || !Array.isArray(n.estimate)) return;
    const header = ['Screen', 'Mesh', 'Ink (g)', 'Area (m²)'].join('\t');
    const rows = n.estimate.map((row, idx) => [
      row.screen ?? row.name ?? `Ink ${idx + 1}`,
      row.mesh ?? '-',
      row.ink_g != null ? `${row.ink_g} g` : row.ink_kg != null ? `${row.ink_kg} kg` : '-',
      row.area_m2 != null ? `${row.area_m2} m²` : '-'
    ].join('\t'));
    const tsv = [header, ...rows].join('\n');
    navigator.clipboard.writeText(tsv).then(() => {
      setCopiedEstimate(true);
      setTimeout(() => setCopiedEstimate(false), 2000);
    }).catch(() => {});
  };

  if (!n) return null;
  const stale = zipStale(n, reducedId);
  const renamed = !stale && namesStale(n, inkNames(palette, inkName));
  const swatches = (pairs: { from: string; to: string }[]) => pairs.map(m => (
    <span className="pair" key={m.from}>
      <span className="plate-swatch" style={{ background: m.from }} title={m.from} />→
      <span className="plate-swatch" style={{ background: m.to }} title={m.to} />
    </span>
  ));
  return (
    <div className="fill-card number-card">
      <p className="hint">{t('{a} areas numbered · {m}% like your picture · {w} × {h} px at 300 DPI',
        { a: n.areas, m: n.design_match, w: n.size_px[0], h: n.size_px[1] })}</p>

      {/* Active options badges */}
      {(() => {
        const o = n.options;
        if (!o) return null;
        const chips: string[] = [];
        if (o.mode && o.mode !== 'flat') chips.push(`Mode: ${o.mode}`);
        if (o.detail_rescue === false) chips.push(t('No detail rescue'));
        if (o.underbase) chips.push(t('White underbase (choke {n}px)', { n: o.underbase_choke ?? 1 }));
        if (o.trap) chips.push(t('Trap {n}px', { n: o.trap }));
        if (o.film) chips.push(t('Film positives'));
        if (o.estimate) chips.push(t('Estimate'));
        if (o.seam_check) chips.push(t('Repeat seam check'));
        if (o.halftone && o.halftone !== 'none') chips.push(t('Halftone: {h} {lpi} LPI', { h: o.halftone.toUpperCase(), lpi: o.halftone_lpi ?? 45 }));
        if (!chips.length) return null;
        return (
          <div className="number-options-chips">
            <span className="dim">{t('Active options:')}</span>
            {chips.map(c => <span key={c} className="opt-chip">{c}</span>)}
          </div>
        );
      })()}

      {/* the zip first: at 1366 x 768 everything below the sheet is under the fold */}
      <a className={'primary wide button-link' + (busy ? ' disabled' : '')} href={zipHref(n)} download={n.zip_name}>{t('⬇ Download everything (.zip)')}</a>
      <small className="dim">{t(n.mill
        ? 'Sketch, numbers, colours list, plates, the mill’s TIF and a Photoshop file, and the mill-size files (TIF, plates, Photoshop file) in their own folder.'
        : 'Sketch, numbers, colours list, plates, the mill’s TIF and a Photoshop file.')}</small>
      {stale ? <>
        <p className="warn">{t('The palette was changed after this zip was made: the zip still has the earlier colours.')}</p>
        <button className="secondary wide" disabled={busy} onClick={rebuildNumber}>{t('↻ Put my palette changes in the zip')}</button>
      </> : renamed ? <>
        <p className="hint">{t('Your mill’s ink names are not in this zip yet.')}</p>
        <button className="secondary wide" disabled={busy} onClick={rebuildNumber}>{t('↻ Put my palette changes in the zip')}</button>
      </> : !!n.changes?.length && <div className="hint">{t('Your palette changes in this zip:')} {swatches(n.changes)}</div>}
      {!!n.names && Object.keys(n.names).length > 0 && (
        <small className="dim">{t('Named from your shelf: {names}', { names: Object.values(n.names).join(', ') })}</small>
      )}
      {!n.verify && <p className="warn">{t('The plates did not stack back to the design exactly: do not send these files to the mill.')}</p>}
      {n.mill && <>
        <p className={n.mill.passed ? 'hint' : 'warn'}>
          {t('Mill size: {wi} × {hi} in = {w} × {h} px at 300 DPI, {k} inks, {m}% like your picture.',
            { wi: n.mill.inches[0], hi: n.mill.inches[1], w: n.mill.size_px[0], h: n.mill.size_px[1], k: n.mill.inks, m: n.mill.design_match })}
          {' '}{t(n.mill.passed ? 'Checked: ready for the mill.' : 'Check failed: do not send it to the mill.')}
        </p>
        {n.mill.cropped && <p className="warn">{t('The design was cut to the repeat’s shape (never stretched). If it was a seamless repeat, its join no longer meets.')}</p>}
        {!!n.mill.missing?.length && <p className="warn">{t('Mill size: {inks} has no screen of its own there, so that change is not in the mill files.', { inks: n.mill.missing.join(', ') })}</p>}
        {!!n.mill.shared?.length && <p className="warn">{t('Mill size: {inks} is a second screen beside the one that took your change there, so it kept its colour.', { inks: n.mill.shared.join(', ') })}</p>}
        {!!n.mill.left?.length && <p className="warn">{t('Mill size: {inks} is near none of the numbered inks, so it kept its colour.', { inks: n.mill.left.join(', ') })}</p>}
      </>}
      {n.shades_merged.length > 0 && (
        <div className="hint">
          {t('Shading put on its colour’s screen:')}
          {swatches(n.shades_merged.map(m => ({ from: m.from, to: m.into })))}
        </div>
      )}
      {n.missed > 0 && <p className="warn">{t('{n} areas had no room for their number (a blue dot marks them).', { n: n.missed })}</p>}
      <a className="number-sheet" href={n.sheet_url} target="_blank" rel="noreferrer" title={t('Open full size')}>
        <img src={screenUrl(n.sheet_url)} alt={t('Numbered sketch')} />
      </a>
      <p className="hint">
        <a href={n.sheet_url} target="_blank" rel="noreferrer">{t('Numbered sketch')}</a>{' · '}
        <a href={n.numbers_url} target="_blank" rel="noreferrer">{t('Numbers on the colour design')}</a>
      </p>

      {/* Seam 2x2 repeat preview */}
      {n.seam_2x2_url && (
        <div className="number-section-box">
          <div className="section-head-row">
            <b>{t('Repeat Seam 2×2 Preview')}</b>
            <button type="button" className="mini inspect-btn" onClick={() => setInspect({ title: t('Repeat seam check 2×2'), url: n.seam_2x2_url! })}>
              🔍 {t('Inspect')}
            </button>
          </div>
          <a className="number-sheet seam-sheet" href={n.seam_2x2_url} onClick={e => { e.preventDefault(); setInspect({ title: t('Repeat seam check 2×2'), url: n.seam_2x2_url! }); }} title={t('Open full size 2×2 repeat')}>
            <img src={screenUrl(n.seam_2x2_url)} alt={t('Repeat seam check 2×2')} />
          </a>
          {n.seam_info && (
            <small className="dim">
              {typeof n.seam_info === 'string' ? n.seam_info : JSON.stringify(n.seam_info)}
            </small>
          )}
        </div>
      )}

      {/* Film positives gallery */}
      {!!n.films?.length && (
        <div className="number-section-box">
          <div className="section-head-row">
            <b>{t('Film positives ({n})', { n: n.films.length })}</b>
          </div>
          <div className="film-thumbs-grid">
            {n.films.map(f => (
              <button key={f.name} type="button" className="film-thumb-link" onClick={() => setInspect({ title: f.name, url: f.url, isFilm: true })} title={t('Inspect film {name}', { name: f.name })}>
                <img src={screenUrl(f.url)} alt={f.name} />
                <span>{f.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Mesh & ink estimate table */}
      {n.estimate && (
        <div className="number-section-box">
          <div className="section-head-row">
            <b>{t('Mesh & ink estimate')}</b>
            {Array.isArray(n.estimate) && (
              <button
                type="button"
                className={'mini copy-btn' + (copiedEstimate ? ' go' : '')}
                onClick={handleCopyEstimate}
                title={t('Copy table to clipboard for Excel or Sheets')}
              >
                {copiedEstimate ? t('✓ Copied!') : t('📋 Copy estimate')}
              </button>
            )}
          </div>
          {Array.isArray(n.estimate) ? (
            <div className="estimate-table-wrap">
              <table className="estimate-table">
                <thead>
                  <tr>
                    <th>{t('Screen')}</th>
                    <th>{t('Mesh')}</th>
                    <th>{t('Ink')}</th>
                    <th>{t('Area')}</th>
                  </tr>
                </thead>
                <tbody>
                  {n.estimate.map((row, idx) => (
                    <tr key={idx}>
                      <td>{row.screen ?? row.name ?? `Ink ${idx + 1}`}</td>
                      <td>{row.mesh ?? '-'}</td>
                      <td>{row.ink_g != null ? `${row.ink_g} g` : row.ink_kg != null ? `${row.ink_kg} kg` : '-'}</td>
                      <td>{row.area_m2 != null ? `${row.area_m2} m²` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : typeof n.estimate === 'object' ? (
            <div className="estimate-summary">
              {Object.entries(n.estimate).map(([k, v]) => (
                <div className="est-row" key={k}>
                  <span className="dim">{k.replace(/_/g, ' ')}:</span>{' '}
                  <b>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</b>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {/* Tone channels list */}
      {!!n.tone_channels?.length && (
        <div className="number-section-box">
          <b>{t('Tone channels ({n})', { n: n.tone_channels.length })}</b>
          <div className="film-thumbs-grid">
            {n.tone_channels.map((tc, idx) => {
              const name = typeof tc === 'string' ? tc : tc.name || `Tone ${idx + 1}`;
              const url = typeof tc === 'object' && tc.url ? tc.url : undefined;
              return url ? (
                <a key={name} href={url} target="_blank" rel="noreferrer" className="film-thumb-link">
                  <img src={screenUrl(url)} alt={name} />
                  <span>{name}</span>
                </a>
              ) : (
                <div key={name} className="tone-chip">
                  <span>{name}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Direct download links */}
      {!!n.download_links?.length && (
        <div className="number-section-box">
          <b>{t('Direct downloads')}</b>
          <div className="downloads-pills">
            {n.download_links.map(dl => (
              <a key={dl.name + dl.url} href={dl.url} download={dl.name} className="mini download-pill">
                ⬇ {dl.label}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Info on unsupported flags if any */}
      {!!n.unsupported_options?.length && (
        <p className="dim hint-unsupported">
          {t('Options {opts} will take effect once the extended backend module is active.', {
            opts: n.unsupported_options.join(', ')
          })}
        </p>
      )}

      <NumberRating key={n.job} w={w} />
      <p className="hint">{t('Or carry on here: Separate and Export work on this design too. After a palette change, ↻ puts it in the zip as well.')}</p>
      <button className="secondary wide" onClick={() => go('Upload')}>{t('← Change the design or settings')}</button>

      {/* Lightbox / Modal for inspecting films or seam preview */}
      {inspect && (
        <div className="lib-backdrop" onClick={closeInspect}>
          <div className="lib-dialog inspect-dialog" onClick={e => e.stopPropagation()}>
            <div className="inspect-header">
              <b>{inspect.title}</b>
              <div className="inspect-actions">
                <div className="inspect-zoom-controls">
                  <button type="button" className="mini" onClick={() => setZoomLevel(z => Math.max(0.5, Number((z - 0.25).toFixed(2))))} title={t('Zoom out')}>−</button>
                  <button type="button" className="mini" onClick={() => setZoomLevel(1)} title={t('Reset zoom')}>{Math.round(zoomLevel * 100)}%</button>
                  <button type="button" className="mini" onClick={() => setZoomLevel(z => Math.min(5, Number((z + 0.25).toFixed(2))))} title={t('Zoom in')}>+</button>
                </div>
                {inspect.isFilm && (
                  <button type="button" className={'mini' + (inverted ? ' go' : '')} onClick={() => setInverted(v => !v)}>
                    {t('Invert film')}
                  </button>
                )}
                <a className="mini button-link" href={inspect.url} download={inspect.title + '.png'}>
                  {t('Download image')}
                </a>
                <button type="button" className="mini" onClick={closeInspect}>✕</button>
              </div>
            </div>
            <div
              className={'inspect-body' + (inverted ? ' inverted' : '')}
              onWheel={e => {
                e.preventDefault();
                if (e.deltaY < 0) {
                  setZoomLevel(z => Math.min(5, Number((z + 0.25).toFixed(2))));
                } else {
                  setZoomLevel(z => Math.max(0.5, Number((z - 0.25).toFixed(2))));
                }
              }}
              style={{ overflow: zoomLevel > 1 ? 'auto' : 'hidden' }}
            >
              <img
                src={screenUrl(inspect.url)}
                alt={inspect.title}
                style={{
                  transform: `scale(${zoomLevel})`,
                  transformOrigin: 'center center',
                  transition: 'transform 0.12s ease-out',
                }}
              />
            </div>
            <div className="inspect-footer">
              <small className="dim">
                {t('Esc to close · "i" to invert · Scroll or +/- to zoom')}
              </small>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 👍/👎 and a note on the numbering run: the textile tool keeps it and shows it beside lookalike designs. */
function NumberRating({ w }: { w: LoomLab }) {
  const { numberInfo: n, busy, rateNumber } = w;
  const t = useT();
  const [note, setNote] = useState(n?.feedback?.note ?? '');
  if (!n) return null;
  const said = n.feedback?.verdict;
  return (
    <div className="number-rate">
      <span>{t('Was this numbering right? Your word helps the tool with designs like it.')}</span>
      <input type="text" maxLength={300} value={note} disabled={busy} onChange={e => setNote(e.target.value)}
        placeholder={t('A note (optional): what was right or wrong')} />
      <button className={'mini' + (said === 'good' ? ' go' : '')} aria-pressed={said === 'good'} disabled={busy}
        onClick={() => rateNumber('good', note.trim())}>{t('👍 Right')}</button>
      <button className={'mini' + (said === 'bad' ? ' go' : '')} aria-pressed={said === 'bad'} disabled={busy}
        onClick={() => rateNumber('bad', note.trim())}>{t('👎 Not right')}</button>
      {said && <small className="dim">{t('Noted: the tool will remember this run.')}</small>}
    </div>
  );
}

/** What the line art + reference fill measured, in place of the reduce controls. */
function FillCard({ w }: { w: LoomLab }) {
  const { fillInfo, go, accuracy, takeReferenceColours, busy } = w;
  const t = useT();
  if (!fillInfo) return null;
  const a = fillInfo.alignment;
  const verdict = a === null ? null : alignmentVerdict(a);
  const how = methodNote(fillInfo, t);
  return (
    <div className="fill-card">
      {fillInfo.trials ? <Trials w={w} /> : <p className={how.warn ? 'warn' : 'hint'}>{how.text}</p>}
      {verdict && <p className={verdict.good ? 'hint' : 'warn'}>{t('Alignment {a} ({v})', { a: a!.toFixed(2), v: t(verdict.text) })}</p>}
      {fillInfo.doubtful > 0 && (
        <p className="warn">
          {t('{n} areas where the reference has several colours (often a gap in a line, so a colour leaks).', { n: fillInfo.doubtful })}
          {fillInfo.debug_url && <> <a href={fillInfo.debug_url} target="_blank" rel="noreferrer">{t('See them in red')}</a></>}
        </p>
      )}
      {accuracy && accuracy.accuracy < 85 && (
        <p className="warn">{t('The shapes come from the line art, so where the two drawings differ the colours differ too. Compare the before/after closely.')}</p>
      )}
      {fillInfo.stray_merged.length > 0 && (
        <p className="hint">{t('{n} tiny colours (a few hundred pixels) joined the nearest ink.', { n: fillInfo.stray_merged.length })}</p>
      )}
      <p className="hint">{fillInfo.line_color
        ? t('Outline colour {c} · {w} × {h} px at 300 DPI', { c: fillInfo.line_color, w: fillInfo.size_px[0], h: fillInfo.size_px[1] })
        : t('{w} × {h} px at 300 DPI', { w: fillInfo.size_px[0], h: fillInfo.size_px[1] })}</p>
      {offerReferenceColours(fillInfo) && <>
        <p className="warn">{t('Two colours only. If the reference has more (red, grey…), use its own colours: the reference is reduced like any design and keeps them all.')}</p>
        <button className="primary wide" disabled={busy} onClick={takeReferenceColours}>{t('Use the reference’s own colours →')}</button>
      </>}
      <button className="secondary wide" onClick={() => go('Upload')}>{t('← Change the files or settings')}</button>
    </div>
  );
}
