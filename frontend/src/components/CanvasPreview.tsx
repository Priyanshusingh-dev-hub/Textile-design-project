import { useRef, useState } from 'react';
import { Palette as PaletteIcon, Upload, ZoomIn, ZoomOut, Maximize } from 'lucide-react';
import { imageUrl } from '../api';
import type { ImageInfo, View } from '../types';

const clamp = (z: number) => Math.min(8, Math.max(1, z));

export function CanvasPreview({ img, original, view, onImportClick }: {
  img?: ImageInfo; original?: ImageInfo; view: View; onImportClick: () => void;
}) {
  const [split, setSplit] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const comparing = !!(original && img && original.image_id !== img.image_id);

  const setZoomKeep = (z: number) => { const nz = clamp(z); setZoom(nz); if (nz === 1) setPan({ x: 0, y: 0 }); };
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };
  const onWheel = (e: React.WheelEvent) => { if (comparing) return; e.preventDefault(); setZoomKeep(zoom * (e.deltaY < 0 ? 1.15 : 0.87)); };
  const onDown = (e: React.PointerEvent) => { if (zoom <= 1) return; drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; (e.target as HTMLElement).setPointerCapture(e.pointerId); };
  const onMove = (e: React.PointerEvent) => { if (!drag.current) return; setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); };
  const onUp = () => { drag.current = null; };

  return (
    <main>
      <div className="canvasbar">
        <b>{view}</b>
        <div>
          <button className="tool" onClick={() => setZoomKeep(zoom - 0.25)} disabled={!img || comparing} title="Zoom out"><ZoomOut size={15} /></button>
          <button className="tool" onClick={reset} disabled={!img} title="Fit to screen">{Math.round(zoom * 100)}%</button>
          <button className="tool" onClick={() => setZoomKeep(zoom + 0.25)} disabled={!img || comparing} title="Zoom in"><ZoomIn size={15} /></button>
          <button className="tool" onClick={reset} disabled={!img} title="Reset view"><Maximize size={15} /></button>
        </div>
      </div>
      <div className={'canvas ' + (!img ? 'empty' : '')} onWheel={onWheel}>
        {img ? (
          comparing ? (
            <div className="compare" style={{ aspectRatio: `${img.width} / ${img.height}`, height: '100%' }}>
              <img src={imageUrl(img.url)} className="compare-after" />
              <div className="compare-before" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
                <img src={imageUrl(original!.url)} />
              </div>
              <div className="compare-divider" style={{ left: `${split}%` }} />
              <input type="range" className="compare-slider" min={0} max={100} value={split} onChange={e => setSplit(+e.target.value)} title="Drag to compare original vs. processed" />
              <div className="compare-label compare-label-left">ORIGINAL</div>
              <div className="compare-label compare-label-right">PROCESSED</div>
              <div className="canvas-tag">{img.width} × {img.height}px</div>
            </div>
          ) : (
            <>
              <img
                src={imageUrl(img.url)}
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, cursor: zoom > 1 ? (drag.current ? 'grabbing' : 'grab') : 'default', transition: drag.current ? 'none' : 'transform .08s' }}
                onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
                draggable={false}
              />
              <div className="canvas-tag">{img.width} × {img.height}px · {Math.round(zoom * 100)}%</div>
            </>
          )
        ) : (
          <div><PaletteIcon size={50} /><h2>Your textile canvas is ready</h2><p>Import a fabric artwork to begin a non-destructive production workflow.</p><button className="primary" onClick={onImportClick}><Upload /> Import Design</button></div>
        )}
      </div>
    </main>
  );
}
