import { useState } from 'react';
import { Palette as PaletteIcon, Upload } from 'lucide-react';
import type { ImageInfo, View } from '../types';

export function CanvasPreview({ img, original, view, onImportClick }: {
  img?: ImageInfo; original?: ImageInfo; view: View; onImportClick: () => void;
}) {
  const [split, setSplit] = useState(50);
  const comparing = !!(original && img && original.image_id !== img.image_id);
  return (
    <main>
      <div className="canvasbar"><b>{view}</b><div><button className="tool">Grid</button><button className="tool">Fit</button><button className="tool">100%</button></div></div>
      <div className={'canvas ' + (!img ? 'empty' : '')}>
        {img ? (
          comparing ? (
            <div className="compare" style={{ aspectRatio: `${img.width} / ${img.height}`, height: '100%' }}>
              <img src={img.url} className="compare-after" />
              <div className="compare-before" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
                <img src={original!.url} />
              </div>
              <div className="compare-divider" style={{ left: `${split}%` }} />
              <input type="range" className="compare-slider" min={0} max={100} value={split} onChange={e => setSplit(+e.target.value)} title="Drag to compare original vs. processed" />
              <div className="compare-label compare-label-left">ORIGINAL</div>
              <div className="compare-label compare-label-right">PROCESSED</div>
              <div className="canvas-tag">{img.width} × {img.height}px</div>
            </div>
          ) : (
            <><img src={img.url} /><div className="canvas-tag">{img.width} × {img.height}px</div></>
          )
        ) : (
          <div><PaletteIcon size={50} /><h2>Your textile canvas is ready</h2><p>Import a fabric artwork to begin a non-destructive production workflow.</p><button className="primary" onClick={onImportClick}><Upload /> Import Design</button></div>
        )}
      </div>
    </main>
  );
}
