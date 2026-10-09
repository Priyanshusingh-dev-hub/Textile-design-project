import { useEffect, useRef, useState } from 'react';
import { Palette as PaletteIcon, Upload, ZoomIn, ZoomOut, Maximize, Columns2 } from 'lucide-react';
import { imageUrl } from '../api';
import type { ImageInfo, View } from '../types';

const clamp = (z: number) => Math.min(8, Math.max(1, z));

export function CanvasPreview({ img, original, view, onImportClick }: {
  img?: ImageInfo; original?: ImageInfo; view: View; onImportClick: () => void;
}) {
  const [split, setSplit] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [compare, setCompare] = useState(true);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const canCompare = !!(original && img && original.image_id !== img.image_id);
  // Before/after is the default once the design has been processed, but it
  // can be switched off to zoom into the processed result on its own.
  const comparing = canCompare && compare;

  useEffect(() => { if (zoom === 1) setPan({ x: 0, y: 0 }); }, [zoom]);

  // React registers wheel listeners as passive, so preventDefault() there is
  // ignored; attach a native non-passive one instead.
  useEffect(() => {
    const el = canvas.current;
    if (!el || !img || comparing) return;
    const onWheel = (e: WheelEvent) => { e.preventDefault(); setZoom(z => clamp(z * (e.deltaY < 0 ? 1.15 : 0.87))); };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [img, comparing]);

  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };
  const onDown = (e: React.PointerEvent) => { if (zoom <= 1) return; drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; setDragging(true); (e.target as HTMLElement).setPointerCapture(e.pointerId); };
  const onMove = (e: React.PointerEvent) => { if (!drag.current) return; setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); };
  const onUp = () => { drag.current = null; setDragging(false); };

  return (
    <main>
      <div className="canvasbar">
        <b>{view}</b>
        <div>
          <button className={comparing ? 'tool active' : 'tool'} onClick={() => setCompare(c => !c)} disabled={!canCompare} title="Compare original vs. processed (turn off to zoom)"><Columns2 size={15} /> Compare</button>
          <button className="tool" onClick={() => setZoom(z => clamp(z - 0.25))} disabled={!img || comparing} title="Zoom out"><ZoomOut size={15} /></button>
          <button className="tool" onClick={reset} disabled={!img} title="Fit to screen">{Math.round(zoom * 100)}%</button>
          <button className="tool" onClick={() => setZoom(z => clamp(z + 0.25))} disabled={!img || comparing} title="Zoom in"><ZoomIn size={15} /></button>
          <button className="tool" onClick={reset} disabled={!img} title="Reset view"><Maximize size={15} /></button>
        </div>
      </div>
      <div ref={canvas} className={'canvas ' + (!img ? 'empty' : '')}>
        {img ? (
          comparing ? (
            // fit inside the canvas on both axes: a fixed height:100% made any
            // image wider than the canvas overflow and get clipped
            <div className="compare" style={{ aspectRatio: `${img.width} / ${img.height}`, width: `min(100cqw, ${img.width / img.height} * 100cqh)` }}>
              <img src={imageUrl(img.url)} className="compare-after" alt="Processed design" />
              <div className="compare-before" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
                <img src={imageUrl(original!.url)} alt="Original design" />
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
                alt="Design"
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, cursor: zoom > 1 ? (dragging ? 'grabbing' : 'grab') : 'default', transition: dragging ? 'none' : 'transform .08s' }}
                onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
                draggable={false}
              />
              <div className="canvas-tag">{img.width} × {img.height}px · {Math.round(zoom * 100)}%</div>
            </>
          )
        ) : (
          <div><PaletteIcon size={50} /><h2>Your textile canvas is ready</h2><p>Import a fabric artwork — or drop an image, PSD or .textileproj anywhere — to begin a non-destructive production workflow.</p><button className="primary" onClick={onImportClick}><Upload /> Import Design</button></div>
        )}
      </div>
    </main>
  );
}
