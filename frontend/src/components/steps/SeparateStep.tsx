import { imageUrl, screenUrl } from '../../api';
import { LivePreview } from '../LivePreview';
import { PlateColours } from '../PlateColours';
import { changedCount } from '../../lib/recolour';
import { Zoomable } from '../Zoomable';
import { separationNote } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';

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
  const t = useT();
  return (
    <section className="stage two with-strip">
      <div className="stage-main">
        <div className="preview-head">{recolouring
          ? t('Live preview — your {n} screens in the colours you are picking', { n: printing.length })
          : t('Combined result — exactly what your {n} screens will print', { n: printing.length })}</div>
        <Zoomable repeatOf={recolouring ? undefined : previewUrl}>
          {recolouring && live
            ? <LivePreview masks={live.masks.map(imageUrl)} colors={layers.map(l => (l.skip ? null : l.color))}
                fabric={fabric} width={live.width} height={live.height} exclusive={!original?.layers?.length} />
            : previewUrl ? <img src={screenUrl(previewUrl)} alt="combined print preview" />
            : <div className="canvas empty">{t('Every ink hidden — nothing prints.')}</div>}
        </Zoomable>
        <div className="plate-strip">
          {layers.map((l, i) => (
            <figure className={'plate-chip' + (l.skip ? ' skipped' : '')} key={l.id}
              role="switch" aria-checked={!l.skip} tabIndex={0}
              aria-label={`Ink ${i + 1}${l.name && l.name !== `Ink ${i + 1}` ? ` (${l.name})` : ''}, ${l.coverage}% coverage — ${l.skip ? 'not printed (fabric)' : 'printing'}`}
              title={t(l.skip ? 'Hidden (fabric) — click to print' : 'Printing — click to mark as fabric')}
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
        <h3>{t('Separation')}</h3>
        <p className="muted">{separationNote(!!original?.layers, original?.overlap, t)} {t("Click a plate to hide your fabric colour (it won't be printed).")}</p>
        <div className="summary">
          <div><small>{t('PRINTING')}</small><b>{printing.length}{printing.length !== layers.length ? ` / ${layers.length}` : ''}</b></div>
          <div><small>{t('MATCH')}</small><b>{accuracy ? accuracy.accuracy + '%' : '—'}</b></div>
        </div>
        <label>{t('Cloth colour')}</label>
        <div className="cloth-row">
          {['#FFFFFF', '#EDE3CC', '#1B2A1F', '#16202E', '#221A16'].map(hx => (
            <button key={hx} className={'cloth-swatch' + (fabric.toUpperCase() === hx ? ' on' : '')}
              style={{ background: hx }} title={hx} aria-label={`Cloth ${hx}`}
              onClick={() => pickFabric(hx)} />
          ))}
          <label className="cloth-swatch custom" style={{ background: fabric }} title={t('Pick any cloth colour')}>
            ✎<input type="color" value={fabric} onChange={e => pickFabric(e.target.value.toUpperCase())} />
          </label>
        </div>
        {isDarkCloth && <p className="muted">{t('Dark cloth — a white under-base is included so the inks stay bright.')}</p>}
        {ground && (
          <div className="hint ground-hint">
            <span className="plate-swatch" style={{ background: ground.ink.color }} />
            <p>
              {ground.matches
                ? t('Ink {n} is the ground ({c}% of the design) and matches your cloth. Leave it unprinted — the cloth shows through — and save the biggest screen.', { n: layers.indexOf(ground.ink) + 1, c: ground.ink.coverage })
                : t("Ink {n} is the ground — {c}% of the design. Print on cloth already dyed this colour and that screen, the biggest, isn't needed.", { n: layers.indexOf(ground.ink) + 1, c: ground.ink.coverage })}
            </p>
            <button className="mini go" disabled={busy} onClick={useGroundAsCloth}>
              {t(ground.matches ? "Don't print it" : 'Use as cloth colour')}
            </button>
          </div>
        )}
        {!!tinyInks.length && (
          <p className="warn">
            {tinyInks.length === 1
              ? t('Ink {n} covers only {c}% — a whole screen for almost nothing. Hide it here, or merge in the palette, to save a screen.', { n: layers.indexOf(tinyInks[0]) + 1, c: tinyInks[0].coverage })
              : t('{n} inks cover under 0.5% each — whole screens for almost nothing. Hide them here, or merge in the palette, to save a screen.', { n: tinyInks.length })}
          </p>
        )}
        <button className="secondary wide recolour-open" disabled={busy || !layers.length} onClick={openRecolour}
          title={t("Change any plate's ink to any colour, with a live preview")}>{t('🎨 Change plate colours')}</button>
        <button className="primary wide" disabled={busy || !printing.length} onClick={() => go('Export')}>{t('Continue to Export →')}</button>
        {!original?.layers && <button className="secondary wide" disabled={busy} onClick={() => go('Reduce')}>{t('← Back to palette')}</button>}
      </aside>
      )}
    </section>
  );
}
