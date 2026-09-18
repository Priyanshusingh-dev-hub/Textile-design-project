import { useState } from 'react';
import { Download, Spline } from 'lucide-react';
import { imageUrl, downloadZip, downloadSvg } from '../api';
import type { Layer } from '../types';

type PlateView = 'color' | 'film';

export function PlatesGallery({ layers }: { layers: Layer[] }) {
  const [mode, setMode] = useState<PlateView>('color');
  const items = () => layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  const download = () => {
    if (mode === 'film') downloadZip({ layers: items(), content: 'film', format: 'tiff', dpi: 300, reg_marks: true }, 'loomlab-screens.zip');
    else downloadZip({ layers: items(), content: 'plate', format: 'png', dpi: 300 }, 'loomlab-plates.zip');
  };
  const downloadVector = () => downloadSvg({ layers: items(), blur: 1.7, simplify: 1.0, corner_angle: 32, min_area: 20 }, 'loomlab-design.svg');
  return (
    <main>
      <div className="canvasbar">
        <b>Color-Separated Plates</b>
        <div className="plate-toggle">
          <button className={mode === 'color' ? 'tool active' : 'tool'} onClick={() => setMode('color')}>Color plates</button>
          <button className={mode === 'film' ? 'tool active' : 'tool'} onClick={() => setMode('film')}>Film / screens</button>
          {!!layers.length && <button className="tool" onClick={download} title="Download every plate as a 300 DPI file"><Download size={14} /> Download 300 DPI</button>}
          {!!layers.length && <button className="tool" onClick={downloadVector} title="Download as a real vector SVG (smooth Bezier curves, pen-tool clean)"><Spline size={14} /> Download vector (.svg)</button>}
        </div>
      </div>
      {layers.length ? (
        <div className="plates">
          {layers.map((l, i) => {
            const src = mode === 'film' ? l.mask_url : (l.plate_url || l.url);
            return (
              <figure className="plate-card" key={l.id}>
                <div className="plate-img"><img src={imageUrl(src || '')} alt={l.name} /></div>
                <figcaption>
                  <span className="plate-swatch" style={{ background: l.color }} />
                  <span className="plate-name">Plate {i + 1} — {l.name}</span>
                  <span className="plate-cov">{l.coverage}% ink</span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      ) : (
        <div className="canvas empty"><div><h2>No plates yet</h2><p>Create separations first (Color Separation tab), then come back here to review each color plate.</p></div></div>
      )}
    </main>
  );
}
