import { useState } from 'react';
import { imageUrl } from '../api';
import type { Layer } from '../types';

type PlateView = 'color' | 'film';

export function PlatesGallery({ layers }: { layers: Layer[] }) {
  const [mode, setMode] = useState<PlateView>('color');
  return (
    <main>
      <div className="canvasbar">
        <b>Color-Separated Plates</b>
        <div className="plate-toggle">
          <button className={mode === 'color' ? 'tool active' : 'tool'} onClick={() => setMode('color')}>Color plates</button>
          <button className={mode === 'film' ? 'tool active' : 'tool'} onClick={() => setMode('film')}>Film / screens</button>
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
