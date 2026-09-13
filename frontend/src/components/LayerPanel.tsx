import { Eye, EyeOff } from 'lucide-react';
import type { Layer } from '../types';

export function LayerPanel({ layers, onToggle, onOpacityChange }: {
  layers: Layer[]; onToggle: (index: number) => void; onOpacityChange: (index: number, value: number) => void;
}) {
  if (!layers.length) return <p className="muted">Create separations from Color Separation.</p>;
  return (
    <>
      {layers.map((l, i) => (
        <div className="layer" key={l.id}>
          <button onClick={() => onToggle(i)}>{l.visible ? <Eye size={16} /> : <EyeOff size={16} />}</button>
          <i style={{ background: l.color }}></i>
          <div><b>{l.name}</b><small>{l.coverage}% coverage</small></div>
          <input type="range" min="0" max="100" value={l.opacity ?? 100} onChange={e => onOpacityChange(i, +e.target.value)} />
        </div>
      ))}
    </>
  );
}
