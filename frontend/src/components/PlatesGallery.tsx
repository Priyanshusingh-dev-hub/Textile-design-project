import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Download, FileStack, Spline, X } from 'lucide-react';
import { imageUrl, post } from '../api';
import type { DownloadFn, Layer } from '../types';

type PlateView = 'color' | 'film';
type TrapLayer = { id: string; plate_url: string; film_url: string; spread_url: string; spread_percent: number };
type TrapPreview = { trap: number; layers: TrapLayer[]; composite_url: string; overlap_url: string; overlap_percent: number };
type Inspected = { title: string; src: string; overlay?: string };
type Zoom = 'fit' | 1 | 2 | 4 | 8;

const ZOOMS: Zoom[] = ['fit', 1, 2, 4, 8];

export function PlatesGallery({ layers, trap, onDownload, busy }: { layers: Layer[]; trap: number; onDownload: DownloadFn; busy: boolean }) {
  const [mode, setMode] = useState<PlateView>('color');
  const [preview, setPreview] = useState<TrapPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [highlight, setHighlight] = useState(true);
  const [inspected, setInspected] = useState<Inspected | null>(null);
  const seq = useRef(0);
  const items = () => layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  const download = () => {
    if (mode === 'film') onDownload('/export/zip', { layers: items(), content: 'film', format: 'tiff', dpi: 300, reg_marks: true, trap }, 'loomlab-screens.zip');
    else onDownload('/export/zip', { layers: items(), content: 'plate', format: 'png', dpi: 300, trap }, 'loomlab-plates.zip');
  };
  const downloadVector = () => onDownload('/export/svg', { layers: items(), blur: 1.7, simplify: 1.0, corner_angle: 45, min_area: 20, trap }, 'loomlab-design.svg');
  const downloadPsd = () => onDownload('/export/psd-multichannel', { layers: items(), dpi: 300, reg_marks: true, trap }, 'loomlab-separation.psd');

  // Rebuild the trapped previews whenever the trap width or the inks change.
  // Debounced so dragging the slider doesn't fire a request per step, and
  // only the newest response is shown.
  const inkKey = layers.map(l => l.id + l.color).join('|');
  useEffect(() => {
    const mine = ++seq.current;
    if (!trap || !layers.length) { setPreview(null); setLoading(false); setError(''); return; }
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const p = await post<TrapPreview>('/separation/trap-preview', { layers: items(), trap });
        if (mine === seq.current) { setPreview(p); setError(''); }
      } catch (e) {
        if (mine === seq.current) setError(e instanceof Error ? e.message : 'Could not build the trap preview.');
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [inkKey, trap]);

  const trapped = trap > 0 && preview ? new Map(preview.layers.map(t => [t.id, t])) : null;
  const plateSrc = (l: Layer, t?: TrapLayer) => mode === 'film' ? (t?.film_url ?? l.mask_url ?? '') : (t?.plate_url ?? l.plate_url ?? l.url);

  return (
    <main className="plates-main">
      <div className="canvasbar">
        <b>Color-Separated Plates</b>
        <div className="plate-toggle">
          <button className={mode === 'color' ? 'tool active' : 'tool'} onClick={() => setMode('color')}>Color plates</button>
          <button className={mode === 'film' ? 'tool active' : 'tool'} onClick={() => setMode('film')}>Film / screens</button>
          {!!layers.length && <button className="tool" onClick={download} disabled={busy} title="Download every plate as a 300 DPI file"><Download size={14} /> Download 300 DPI</button>}
          {!!layers.length && <button className="tool" onClick={downloadPsd} disabled={busy} title="One Photoshop file with a named spot channel per ink"><FileStack size={14} /> Multichannel PSD</button>}
          {!!layers.length && <button className="tool" onClick={downloadVector} disabled={busy} title="Download as a real vector SVG (smooth Bezier curves, pen-tool clean)"><Spline size={14} /> Download vector (.svg)</button>}
        </div>
      </div>
      {!!layers.length && (
        <div className="trapbar">
          {trap ? (
            <>
              <span><b>Trapping {trap} px</b> ≈ {(trap * 25.4 / 300).toFixed(2)} mm at 300 DPI — plates show exactly what will be exported.</span>
              <label className="checkline"><input type="checkbox" checked={highlight} onChange={e => setHighlight(e.target.checked)} /> Highlight spread</label>
              {loading ? <span className="trap-status">Updating…</span> : error ? <span className="trap-status failed">{error}</span> : null}
            </>
          ) : (
            <span>Trapping is <b>off</b> — set a spread in the Export panel on the right to preview it here.</span>
          )}
          <span className="muted">Click a plate to inspect it up close.</span>
        </div>
      )}
      {layers.length ? (
        <div className="plates">
          {trapped && preview && (
            <figure className="plate-card trap-map">
              <button className="plate-img" onClick={() => setInspected({ title: `Overlap map — trap ${preview.trap} px`, src: preview.composite_url, overlay: preview.overlap_url })} title="Inspect">
                <img src={imageUrl(preview.composite_url)} alt="Design as printed with trapping" />
                <img className="plate-overlay" src={imageUrl(preview.overlap_url)} alt="" />
              </button>
              <figcaption>
                <span className="plate-swatch trap-swatch" />
                <span className="plate-name" title="Every pixel where two or more inks overlap after trapping">Overlap map</span>
                <span className="plate-cov">{preview.overlap_percent}% overlap</span>
              </figcaption>
            </figure>
          )}
          {layers.map((l, i) => {
            const t = trapped?.get(l.id);
            const src = plateSrc(l, t);
            const title = `Plate ${i + 1} — ${l.name}`;
            return (
              <figure className="plate-card" key={l.id}>
                <button className="plate-img" onClick={() => setInspected({ title, src, overlay: t && highlight ? t.spread_url : undefined })} title="Inspect">
                  <img src={imageUrl(src)} alt={l.name} />
                  {t && highlight && <img className="plate-overlay" src={imageUrl(t.spread_url)} alt="" />}
                </button>
                <figcaption>
                  <span className="plate-swatch" style={{ background: l.color }} />
                  <span className="plate-name">{title}</span>
                  <span className="plate-cov">{l.coverage}% ink{t ? ` · +${t.spread_percent}% trap` : ''}</span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      ) : (
        <div className="canvas empty"><div><h2>No plates yet</h2><p>Create separations first (Color Separation tab), then come back here to review each color plate.</p></div></div>
      )}
      {inspected && <Inspector item={inspected} onClose={() => setInspected(null)} />}
    </main>
  );
}

// Full-size look at one plate. Fit shows the whole plate; 1x-8x show real
// pixels (no smoothing) so a 2-3 px spread is plainly visible.
function Inspector({ item, onClose }: { item: Inspected; onClose: () => void }) {
  const [zoom, setZoom] = useState<Zoom>('fit');
  const [natural, setNatural] = useState({ w: 0, h: 0 });
  const [box, setBox] = useState({ w: 0, h: 0 });
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  useLayoutEffect(() => {
    const el = scroller.current; if (!el) return;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure); ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scale = zoom === 'fit'
    ? (natural.w && box.w ? Math.min((box.w - 32) / natural.w, (box.h - 32) / natural.h) : 0)
    : zoom;
  const size = natural.w ? { width: Math.round(natural.w * scale), height: Math.round(natural.h * scale) } : undefined;

  return (
    <div className="inspect" role="dialog" aria-modal="true" aria-label={item.title}>
      <div className="canvasbar">
        <b>{item.title}</b>
        <div className="plate-toggle">
          {ZOOMS.map(z => <button key={z} className={zoom === z ? 'tool active' : 'tool'} onClick={() => setZoom(z)}>{z === 'fit' ? 'Fit' : `${z}×`}</button>)}
          <button className="tool" onClick={onClose} title="Close (Esc)"><X size={14} /></button>
        </div>
      </div>
      <div ref={scroller} className="inspect-scroll">
        <div className={'inspect-stack' + (scale > 1 ? ' pixelated' : '')} style={size}>
          <img src={imageUrl(item.src)} alt={item.title} onLoad={e => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
          {item.overlay && <img src={imageUrl(item.overlay)} alt="" />}
        </div>
      </div>
    </div>
  );
}
