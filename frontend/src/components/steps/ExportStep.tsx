import { imageUrl, screenUrl } from '../../api';
import { Zoomable } from '../Zoomable';
import { EXPORT_DPI, money, enlargeNote, printAt, TRAP_CHOICES, trapLabel, DOT_CHOICES, dotLabel } from '../../lib/print';
import type { LoomLab } from '../../hooks/useLoomLab';

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
  } = w;
  return (
    <section className="stage two">
      <div className="stage-main">
        <div className="preview-head">Final proof — {printing.length} ink{printing.length !== 1 ? 's' : ''}, print-ready{resizedWidth ? `, drawn at ${at?.inches.join(' × ')} in (zoom in to check edges)` : ''}</div>
        <Zoomable>
          {proofUrl ? <img src={screenUrl(proofUrl)} alt="proof" />
            : <div className="canvas empty">{resizedWidth ? `Drawing the screens at ${resizedWidth} in…` : 'Separate a design first.'}</div>}
        </Zoomable>
      </div>
      <aside className="panel">
        <h3>Export production package</h3>
        <div className="summary">
          <div><small>PLATES</small><b>{printing.length}</b></div>
          <div><small>DPI</small><b>{EXPORT_DPI}</b></div>
          {at && <div className="wide-cell"><small>PRINTS AT</small><b>{at.label}</b></div>}
        </div>
        <div className="panel-section">
          <h4>Print settings</h4>
          <label htmlFor="print-width">Print width</label>
          <div className="width-row">
            {/* never locked while busy: the proof redraws after a pause in typing,
                and locking the box then would trap "1" on the way to "12" */}
            <input id="print-width" className="width-input" type="number" min={0.5} max={200} step={0.1}
              inputMode="decimal"
              placeholder={at ? String(printAt(original?.width, original?.height)!.inches[0]) : ''}
              value={widthText} onChange={e => setWidthText(e.target.value)} />
            <span className="unit">in</span>
            {widthText && <button className="mini" disabled={busy} onClick={() => setWidthText('')}>own size</button>}
          </div>
          {widthNote && <p className={widthNote.tone}>{widthNote.text}</p>}
          {printing.length !== layers.length && <p className="muted">{layers.length - printing.length} ink marked as fabric won't be printed.</p>}
          <label className="check">
            <input type="checkbox" checked={underbase} disabled={busy} onChange={e => setUnderbase(e.target.checked)} />
            White under-base screen (for non-white cloth)
          </label>
          {canClean && (
            <>
              <label className="check trap-row" title="A screen's mesh can't hold very small dots: they print as nothing or clog and print as dirt. Cleaning gives each one to the ink around it (still one ink per pixel).">
                Clean tiny dots
                <select className="select mini-select" value={minDot} disabled={busy} onChange={e => setMinDot(Number(e.target.value))}>
                  {DOT_CHOICES.map(mm => <option key={mm} value={mm}>{dotLabel(mm)}</option>)}
                </select>
              </label>
              {dots && <p className={(dots.tone === 'hint' ? 'hint-note' : 'muted') + ' small-note'}>{dots.text}</p>}
            </>
          )}
          {canTrap && (
            <>
              <label className="check trap-row" title="Only if your prints show thin lines of cloth between colours: each lighter ink is spread under the darker inks it touches, on the films only. Printed light to dark, the print looks exactly like the proof.">
                Trap between colours
                <select className="select mini-select" value={trapPx} disabled={busy} onChange={e => setTrapPx(Number(e.target.value))}>
                  {TRAP_CHOICES.map(px => <option key={px} value={px}>{trapLabel(px, EXPORT_DPI)}</option>)}
                </select>
              </label>
              {!!trapPx && <p className="muted small-note">Lighter inks spread {trapLabel(trapPx, EXPORT_DPI)} under darker ones on the films — print in the job sheet's order.</p>}
            </>
          )}
        </div>
        <div className="panel-section">
          <h4>Download</h4>
          <label className="check">
            <input type="checkbox" checked={includeVector} disabled={busy} onChange={e => setIncludeVector(e.target.checked)} />
            Include scalable vector (SVG) outlines
          </label>
          <button className="primary wide" disabled={busy || !printing.length || !!at?.tooLarge} onClick={doExport}>{busy && busyLabel ? busyLabel : '⬇ Download .zip'}</button>
          <button className="secondary wide" disabled={busy || !printing.length} onClick={doExportSvg}>{busy && busyLabel === 'Tracing vectors…' ? busyLabel : '⬇ Vector SVG only'}</button>
          <p className="pack-line after">
            <b>screens/</b> B&amp;W TIFF films, {EXPORT_DPI} DPI, registration marks · <b>plates/</b> colour proof per ink
            · <b>proof.png</b> · <b>job-sheet.png</b> to pin up at the press
            {underbase && <> · <b>0-Underbase</b> printed first</>}
            {includeVector && <> · <b>vector/</b> SVG outlines</>}
          </p>
        </div>
        <div className="panel-section">
          <h4>Extras</h4>
          <details className="extra">
            <summary>₹ Quote a print run</summary>
            <div className="quote-box">
              <label htmlFor="quote-meters" className="sr-only">Meters to print</label>
              <div className="row">
                <input id="quote-meters" className="width-input" type="number" min={1} step={1} placeholder="meters"
                  value={quoteMeters} onChange={e => { setQuoteMeters(e.target.value); setQuote(undefined); }} />
                <input className="width-input" type="text" maxLength={60} placeholder="client (optional)"
                  value={quoteClient} onChange={e => { setQuoteClient(e.target.value); setQuote(undefined); }} />
                <button className="mini go" disabled={busy || !printing.length || !(Number(quoteMeters) > 0)} onClick={doQuote}>₹ Quote</button>
              </div>
              {quote && <p className="hint">{money(quote.total, quote.currency)} · {money(quote.per_meter, quote.currency)}/m ·{' '}
                <a href={quote.image_url} download={`quote-${quote.quote_no}.png`} target="_blank" rel="noreferrer">quote image ⬇</a></p>}
            </div>
          </details>
          <details className="extra">
            <summary>⤢ High-resolution design file</summary>
            <div className="quote-box">
              <label htmlFor="hi-width" className="sr-only">Width of the high-resolution file</label>
              <div className="row">
                <input id="hi-width" className="width-input" type="number" min={0.5} max={200} step={0.1}
                  placeholder={resizedWidth ? String(resizedWidth) : 'inches'} value={hiWidth}
                  onChange={e => { setHiWidth(e.target.value); setHiRes(undefined); }} />
                <span className="muted">in · {EXPORT_DPI} DPI</span>
                <button className="mini go" disabled={busy || !original || !(Number(hiWidth || resizedWidth) > 0)} onClick={doEnlarge}>⤢ Enlarge</button>
              </div>
              {hiRes && <>
                <p className={enlargeNote(hiRes).tone}>{enlargeNote(hiRes).text}</p>
                <p className="hint">{(['tif', 'jpg', 'png'] as const).map(f => (
                  <a key={f} href={imageUrl(`/api/image/${hiRes.image_id}/file?format=${f}&dpi=${EXPORT_DPI}&name=${encodeURIComponent((original?.file_name || 'design').replace(/\.[^.]+$/, ''))}`)}
                    download>⬇ {f.toUpperCase()}</a>)).reduce<React.ReactNode[]>((a, x) => a.length ? [...a, ' · ', x] : [x], [])}</p>
              </>}
            </div>
          </details>
        </div>
        <button className="secondary wide" disabled={busy} onClick={() => go('Separate')}>← Back to plates</button>
      </aside>
    </section>
  );
}
