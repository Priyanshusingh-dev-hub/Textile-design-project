import { imageUrl, screenUrl } from '../../api';
import { Zoomable } from '../Zoomable';
import { EXPORT_DPI, money, enlargeNote, printAt, TRAP_CHOICES, trapLabel, DOT_CHOICES, dotLabel } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';
import { useT } from '../../lib/i18n';

/** Step 4: print width, films package, quote and a high-resolution file. */
export function ExportStep({ w }: { w: LoomLab }) {
  const {
    original,
    small,
    layers,
    includeVector,
    setIncludeVector,
    fabric,
    underbase,
    setUnderbase,
    trapPx,
    setTrapPx,
    minDot,
    setMinDot,
    widthText,
    setWidthText,
    quoteMeters,
    setQuoteMeters,
    quoteClient,
    setQuoteClient,
    hiWidth,
    setHiWidth,
    hiRes,
    setHiRes,
    quote,
    setQuote,
    input,
    run,
    busy,
    busyLabel,
    go,
    printing,
    canTrap,
    canClean,
    at,
    widthNote,
    resizedWidth,
    doExport,
    doQuote,
    doEnlarge,
    doExportSvg,
    dots,
    proofUrl,
    colourways,
    cwName,
    setCwName,
    saveColourway,
    removeColourway,
    showColourway,
  } = w;
  const t = useT();
  return (
    <section className="stage two">
      <div className="stage-main">
        <div className="preview-head">{t('Final proof — {n} inks, print-ready', { n: printing.length })}{resizedWidth ? t(', drawn at {size} in (zoom in to check edges)', { size: at?.inches.join(' × ') ?? '' }) : ''}</div>
        <Zoomable>
          {proofUrl ? <img src={screenUrl(proofUrl)} alt="proof" />
            : <div className="canvas empty">{resizedWidth ? t('Drawing the screens at {w} in…', { w: resizedWidth }) : t('Separate a design first.')}</div>}
        </Zoomable>
      </div>
      <aside className="panel">
        <h3>{t('Export production package')}</h3>
        <div className="summary">
          <div><small>{t('PLATES')}</small><b>{printing.length}</b></div>
          <div><small>DPI</small><b>{EXPORT_DPI}</b></div>
          {at && <div className="wide-cell"><small>{t('PRINTS AT')}</small><b>{at.label}</b></div>}
        </div>
        <div className="panel-section">
          <h4>{t('Print settings')}</h4>
          <label htmlFor="print-width">{t('Print width')}</label>
          <div className="width-row">
            {/* never locked while busy: the proof redraws after a pause in typing,
                and locking the box then would trap "1" on the way to "12" */}
            <input id="print-width" className="width-input" type="number" min={0.5} max={200} step={0.1}
              inputMode="decimal"
              placeholder={at ? String(printAt(original?.width, original?.height)!.inches[0]) : ''}
              value={widthText} onChange={e => setWidthText(e.target.value)} />
            <span className="unit">in</span>
            {widthText && <button className="mini" disabled={busy} onClick={() => setWidthText('')}>{t('own size')}</button>}
          </div>
          {widthNote && <p className={widthNote.tone}>{t(widthNote.text)}</p>}
          {printing.length !== layers.length && <p className="muted">{t("{n} ink marked as fabric won't be printed.", { n: layers.length - printing.length })}</p>}
          <label className="check">
            <input type="checkbox" checked={underbase} disabled={busy} onChange={e => setUnderbase(e.target.checked)} />
            {t('White under-base screen (for non-white cloth)')}
          </label>
          {canClean && (
            <>
              <label className="check trap-row" title={t("A screen's mesh can't hold very small dots: they print as nothing or clog and print as dirt. Cleaning gives each one to the ink around it (still one ink per pixel).")}>
                {t('Clean tiny dots')}
                <select className="select mini-select" value={minDot} disabled={busy} onChange={e => setMinDot(Number(e.target.value))}>
                  {DOT_CHOICES.map(mm => <option key={mm} value={mm}>{dotLabel(mm, t)}</option>)}
                </select>
              </label>
              {dots && <p className={(dots.tone === 'hint' ? 'hint-note' : 'muted') + ' small-note'}>{t(dots.text)}</p>}
            </>
          )}
          {canTrap && (
            <>
              <label className="check trap-row" title={t('Only if your prints show thin lines of cloth between colours: each lighter ink is spread under the darker inks it touches, on the films only. Printed light to dark, the print looks exactly like the proof.')}>
                {t('Trap between colours')}
                <select className="select mini-select" value={trapPx} disabled={busy} onChange={e => setTrapPx(Number(e.target.value))}>
                  {TRAP_CHOICES.map(px => <option key={px} value={px}>{trapLabel(px, EXPORT_DPI, t)}</option>)}
                </select>
              </label>
              {!!trapPx && <p className="muted small-note">{t("Lighter inks spread {w} under darker ones on the films — print in the job sheet's order.", { w: trapLabel(trapPx, EXPORT_DPI) })}</p>}
            </>
          )}
        </div>
        <div className="panel-section">
          <h4>{t('Download')}</h4>
          <label className="check">
            <input type="checkbox" checked={includeVector} disabled={busy} onChange={e => setIncludeVector(e.target.checked)} />
            {t('Include scalable vector (SVG) outlines')}
          </label>
          <button className="primary wide" disabled={busy || !printing.length || !!at?.tooLarge} onClick={doExport}>{t(busy && busyLabel ? busyLabel : '⬇ Download .zip')}</button>
          <button className="secondary wide" disabled={busy || !printing.length} onClick={doExportSvg}>{t(busy && busyLabel === 'Tracing vectors…' ? busyLabel : '⬇ Vector SVG only')}</button>
          <p className="pack-line after">
            <b>screens/</b> B&amp;W TIFF films, {EXPORT_DPI} DPI, registration marks · <b>plates/</b> colour proof per ink
            · <b>proof.png</b> · <b>job-sheet.png</b> to pin up at the press
            {underbase && <> · <b>0-Underbase</b> printed first</>}
            {includeVector && <> · <b>vector/</b> SVG outlines</>}
          </p>
        </div>
        <div className="panel-section">
          <h4>{t('Extras')}</h4>
          <details className="extra" open={colourways.length > 0 || undefined}>
            <summary>{t('🎨 Colourways')}{colourways.length ? ` (${colourways.length})` : ''}</summary>
            <div className="quote-box">
              <p className="muted small-note">{t('The same screens printed in other inks — no new screens. Save these colours, change the plate colours (Separate → 🎨) and save again: the zip gets a proof and a job sheet for every colourway.')}</p>
              {colourways.map((cw, i) => (
                <div className="cw-row" key={cw.name}>
                  <b>{cw.name}</b>
                  <span className="cw-swatches">
                    {layers.filter(l => !l.skip).map(l => (
                      <span key={l.id} className="plate-swatch" title={cw.inks[l.id]?.name || cw.inks[l.id]?.color}
                        style={{ background: cw.inks[l.id]?.color ?? l.color }} />
                    ))}
                    <span className="cw-cloth" title={`cloth ${cw.fabric}`} style={{ background: cw.fabric }} />
                  </span>
                  <button className="mini" disabled={busy} onClick={() => showColourway(i)} title={t('Put these inks on the plates')}>{t('show')}</button>
                  <button className="mini" disabled={busy} onClick={() => removeColourway(i)} title="Remove">✕</button>
                </div>
              ))}
              <div className="row">
                <input className="width-input" type="text" maxLength={40} aria-label={t('Colourway name')}
                  value={cwName} onChange={e => setCwName(e.target.value)} />
                <button className="mini go" disabled={busy || !layers.length} onClick={saveColourway}>{t('+ Save current colours')}</button>
              </div>
              {!!colourways.length && <p className="muted small-note">{t('Trap is off while there are colourways (it is made for one set of inks).')}</p>}
            </div>
          </details>
          <details className="extra">
            <summary>{t('₹ Quote a print run')}</summary>
            <div className="quote-box">
              <label htmlFor="quote-meters" className="sr-only">Meters to print</label>
              <div className="row">
                <input id="quote-meters" className="width-input" type="number" min={1} step={1} placeholder={t('meters')}
                  value={quoteMeters} onChange={e => { setQuoteMeters(e.target.value); setQuote(undefined); }} />
                <input className="width-input" type="text" maxLength={60} placeholder={t('client (optional)')}
                  value={quoteClient} onChange={e => { setQuoteClient(e.target.value); setQuote(undefined); }} />
                <button className="mini go" disabled={busy || !printing.length || !(Number(quoteMeters) > 0)} onClick={doQuote}>₹ Quote</button>
              </div>
              {quote && <p className="hint">{money(quote.total, quote.currency)} · {money(quote.per_meter, quote.currency)}/m ·{' '}
                <a href={imageUrl(quote.image_url)} download={`quote-${quote.quote_no}.png`} target="_blank" rel="noreferrer">{t('quote image ⬇')}</a></p>}
            </div>
          </details>
          <details className="extra">
            <summary>{t('⤢ High-resolution design file')}</summary>
            <div className="quote-box">
              <label htmlFor="hi-width" className="sr-only">Width of the high-resolution file</label>
              <div className="row">
                <input id="hi-width" className="width-input" type="number" min={0.5} max={200} step={0.1}
                  placeholder={resizedWidth ? String(resizedWidth) : t('inches')} value={hiWidth}
                  onChange={e => { setHiWidth(e.target.value); setHiRes(undefined); }} />
                <span className="muted">in · {EXPORT_DPI} DPI</span>
                <button className="mini go" disabled={busy || !original || !(Number(hiWidth || resizedWidth) > 0)} onClick={doEnlarge}>{t('⤢ Enlarge')}</button>
              </div>
              {hiRes && <>
                <p className={enlargeNote(hiRes, t).tone}>{enlargeNote(hiRes, t).text}</p>
                <p className="hint">{(['tif', 'jpg', 'png'] as const).map(f => (
                  <a key={f} href={imageUrl(`/api/image/${hiRes.image_id}/file?format=${f}&dpi=${EXPORT_DPI}&name=${encodeURIComponent((original?.file_name || 'design').replace(/\.[^.]+$/, ''))}`)}
                    download>⬇ {f.toUpperCase()}</a>)).reduce<React.ReactNode[]>((a, x) => a.length ? [...a, ' · ', x] : [x], [])}</p>
              </>}
            </div>
          </details>
        </div>
        <button className="secondary wide" disabled={busy} onClick={() => go('Separate')}>{t('← Back to plates')}</button>
      </aside>
    </section>
  );
}
