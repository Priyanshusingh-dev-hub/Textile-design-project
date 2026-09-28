import { imageUrl, screenUrl } from '../../api';
import { LivePreview } from '../LivePreview';
import { PlateColours } from '../PlateColours';
import { changedCount } from '../../lib/recolour';
import { Zoomable } from '../Zoomable';
import { separationNote } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';

/** Step 3: one plate per ink, the cloth colour, and plate colours. */
export function SeparateStep({ w }: { w: LoomLab }) {
  const {
    original,
    palette,
    accuracy,
    library,
    matches,
    layers,
    previewUrl,
    fabric,
    busy,
    go,
    toggleSkip,
    setInkColor,
    recolouring,
    snap,
    live,
    openRecolour,
    liveColour,
    resetColour,
    doneRecolour,
    cancelRecolour,
    printing,
    merge,
    isDarkCloth,
    pickFabric,
    tinyInks,
    ground,
    useGroundAsCloth,
  } = w;
  return (
    <section className="stage two with-strip">
      <div className="stage-main">
        <div className="preview-head">{recolouring
          ? <>Live preview — your {printing.length} screen{printing.length !== 1 ? 's' : ''} in the colours you are picking</>
          : <>Combined result — exactly what your {printing.length} screen{printing.length !== 1 ? 's' : ''} will print</>}</div>
        <Zoomable>
          {recolouring && live
            ? <LivePreview masks={live.masks.map(imageUrl)} colors={layers.map(l => (l.skip ? null : l.color))}
                fabric={fabric} width={live.width} height={live.height} exclusive={!original?.layers?.length} />
            : previewUrl ? <img src={screenUrl(previewUrl)} alt="combined print preview" />
            : <div className="canvas empty">Every ink hidden — nothing prints.</div>}
        </Zoomable>
        <div className="plate-strip">
          {layers.map((l, i) => (
            <figure className={'plate-chip' + (l.skip ? ' skipped' : '')} key={l.id}
              role="switch" aria-checked={!l.skip} tabIndex={0}
              aria-label={`Ink ${i + 1}${l.name && l.name !== `Ink ${i + 1}` ? ` (${l.name})` : ''}, ${l.coverage}% coverage — ${l.skip ? 'not printed (fabric)' : 'printing'}`}
              title={l.skip ? 'Hidden (fabric) — click to print' : 'Printing — click to mark as fabric'}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSkip(l.id); } }}
              onClick={() => toggleSkip(l.id)}>
              <div className="plate-chip-img"><img src={l.plate_url ? imageUrl(l.plate_url) : screenUrl(l.url)} alt={l.name} /></div>
              <figcaption>
                <span className="plate-line">
                  {/* the chip itself is a switch that takes Enter/Space, so the
                      picker must keep its own keys — otherwise opening it with
                      the keyboard also drops the ink from the print */}
                  <label className="plate-swatch editable" style={{ background: l.color }}
                    title={`Ink colour ${l.color} — click to change`}
                    onClick={e => e.stopPropagation()}
                    onKeyDown={e => e.stopPropagation()}>
                    <input type="color" value={l.color} disabled={busy}
                      aria-label={`Ink colour for ${l.name || `ink ${i + 1}`}`}
                      onClick={e => e.stopPropagation()}
                      onKeyDown={e => e.stopPropagation()}
                      onChange={e => (recolouring ? liveColour(l.id, e.target.value) : setInkColor(l.id, e.target.value))} />
                  </label>
                  {i + 1}<small>{l.coverage}%</small>
                </span>
                {l.name && l.name !== `Ink ${i + 1}` &&
                  <span className="plate-ink-name" title={l.name}>{l.name}</span>}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
      {recolouring ? (
      <aside className="panel">
        <PlateColours plates={layers} snapshot={snap} library={library} fabric={fabric}
          onColour={liveColour} onFabric={pickFabric} onReset={resetColour}
          onDone={doneRecolour} onCancel={cancelRecolour} changed={changedCount(layers, snap)} />
      </aside>
      ) : (
      <aside className="panel">
        <h3>Separation</h3>
        <p className="muted">{separationNote(!!original?.layers, original?.overlap)} Click a plate to hide your <b>fabric</b> colour (it won't be printed).</p>
        <div className="summary">
          <div><small>PRINTING</small><b>{printing.length}{printing.length !== layers.length ? ` / ${layers.length}` : ''}</b></div>
          <div><small>MATCH</small><b>{accuracy ? accuracy.accuracy + '%' : '—'}</b></div>
        </div>
        <label>Cloth colour</label>
        <div className="cloth-row">
          {['#FFFFFF', '#EDE3CC', '#1B2A1F', '#16202E', '#221A16'].map(hx => (
            <button key={hx} className={'cloth-swatch' + (fabric.toUpperCase() === hx ? ' on' : '')}
              style={{ background: hx }} title={hx} aria-label={`Cloth ${hx}`}
              onClick={() => pickFabric(hx)} />
          ))}
          <label className="cloth-swatch custom" style={{ background: fabric }} title="Pick any cloth colour">
            ✎<input type="color" value={fabric} onChange={e => pickFabric(e.target.value.toUpperCase())} />
          </label>
        </div>
        {isDarkCloth && <p className="muted">Dark cloth — a white under-base is included so the inks stay bright.</p>}
        {ground && (
          <div className="hint ground-hint">
            <span className="plate-swatch" style={{ background: ground.ink.color }} />
            <p>
              {ground.matches
                ? <>Ink <b>{layers.indexOf(ground.ink) + 1}</b> is the ground ({ground.ink.coverage}% of the design) and matches your cloth. Leave it unprinted — the cloth shows through — and save the biggest screen.</>
                : <>Ink <b>{layers.indexOf(ground.ink) + 1}</b> is the ground — {ground.ink.coverage}% of the design. Print on cloth already dyed this colour and that screen, the biggest, isn't needed.</>}
            </p>
            <button className="mini go" disabled={busy} onClick={useGroundAsCloth}>
              {ground.matches ? "Don't print it" : 'Use as cloth colour'}
            </button>
          </div>
        )}
        {!!tinyInks.length && (
          <p className="warn">
            {tinyInks.length === 1
              ? <>Ink <b>{layers.indexOf(tinyInks[0]) + 1}</b> covers only {tinyInks[0].coverage}% — a whole screen for almost nothing.</>
              : <><b>{tinyInks.length} inks</b> cover under 0.5% each — whole screens for almost nothing.</>}
            {' '}Hide {tinyInks.length === 1 ? 'it' : 'them'} here, or merge in the palette, to save a screen.
          </p>
        )}
        <button className="secondary wide recolour-open" disabled={busy || !layers.length} onClick={openRecolour}
          title="Change any plate's ink to any colour, with a live preview">🎨 Change plate colours</button>
        <button className="primary wide" disabled={busy || !printing.length} onClick={() => go('Export')}>Continue to Export →</button>
        {!original?.layers && <button className="secondary wide" disabled={busy} onClick={() => go('Reduce')}>← Back to palette</button>}
      </aside>
      )}
    </section>
  );
}
