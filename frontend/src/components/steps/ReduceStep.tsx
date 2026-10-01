import { screenUrl } from '../../api';
import { inkOwner, matchLabel } from '../../lib/inks';
import { BeforeAfter } from '../BeforeAfter';
import { repeatNote, SMALL_CHOICES } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';
import { alignmentVerdict, methodNote, offerReferenceColours } from '../../lib/fill';

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
        <h3>{t(fillInfo ? 'Filled from line art' : 'Reduce colors')}</h3>
        {fillInfo ? <FillCard w={w} /> : <>
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
      <p className={how.warn ? 'warn' : 'hint'}>{how.text}</p>
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
