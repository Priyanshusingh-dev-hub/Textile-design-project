import { Eye, EyeOff } from 'lucide-react';
import type { ImageInfo, Layer, Palette } from '../types';

export function LayerPanel({ layers, palette, img, onToggle, onOpacityChange }: {
  layers: Layer[]; palette: Palette[]; img?: ImageInfo; onToggle: (index: number) => void; onOpacityChange: (index: number, value: number) => void;
}) {
  if (!layers.length) return <p className="muted">Create separations from Color Separation.</p>;
  const totalCoverage = layers.reduce((sum, l) => sum + l.coverage, 0);
  return (
    <>
      <div className="summary">
        <div><small>COLORS</small><b>{palette.length || layers.length}</b></div>
        <div><small>SCREENS</small><b>{layers.length}</b></div>
        <div><small>DIMENSIONS</small><b>{img ? `${img.width}×${img.height}` : '—'}</b></div>
        <div><small>TOTAL INK</small><b>{totalCoverage.toFixed(1)}%</b></div>
      </div>
      {layers.map((l, i) => (
        <div className="layer" key={l.id}>
          <button onClick={() => onToggle(i)}>{l.visible ? <Eye size={16} /> : <EyeOff size={16} />}</button>
          <i style={{ background: l.color }}></i>
          <div>
            <b>{l.name}</b>
            <div className="coverage-bar"><span style={{ width: `${l.coverage}%` }} /></div>
            <small>{l.coverage}% coverage</small>
          </div>
          <input type="range" min="0" max="100" value={l.opacity ?? 100} onChange={e => onOpacityChange(i, +e.target.value)} />
        </div>
      ))}
    </>
  );
}
