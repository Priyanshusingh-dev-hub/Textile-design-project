import { RotateCcw } from 'lucide-react';
import type { Mapping, Palette } from '../types';

export function ColorMappingPanel({ mapping, setMapping, palette, tolerance, setTolerance, onApply, onReset }: {
  mapping: Mapping; setMapping: (m: Mapping) => void; palette: Palette[];
  tolerance: number; setTolerance: (n: number) => void; onApply: () => void; onReset: () => void;
}) {
  const pick = (hex: string) => setMapping({ ...mapping, source: hex.toLowerCase() });
  return (
    <>
      <p className="muted">Map a source ink to a target ink. Changes preserve the original import and can be undone.</p>
      {!!palette.length && (
        <>
          <label>Pick the source from the palette</label>
          <div className="chips">
            {palette.map((p, i) => (
              <button key={p.hex + i} className={p.hex.toLowerCase() === mapping.source.toLowerCase() ? 'chip active' : 'chip'} style={{ background: p.hex }} title={`${p.hex} · ${p.coverage}%`} onClick={() => pick(p.hex)} />
            ))}
          </div>
        </>
      )}
      <label>Source color <output>{mapping.source.toUpperCase()}</output></label>
      <input type="color" value={mapping.source} onChange={e => setMapping({ ...mapping, source: e.target.value })} />
      <label>Target color <output>{mapping.target.toUpperCase()}</output></label>
      <input type="color" value={mapping.target} onChange={e => setMapping({ ...mapping, target: e.target.value })} />
      <label>Match tolerance <output>{tolerance}</output></label>
      <input type="range" min={1} max={60} value={tolerance} onChange={e => setTolerance(+e.target.value)} />
      <p className="muted">How close (LAB distance) a pixel must be to the source to be repainted. Keep it low on a reduced design; raise it to catch shading variations of the source.</p>
      <button className="primary wide" onClick={onApply}>Apply mapping</button>
      <button className="secondary wide" onClick={onReset}><RotateCcw size={15} /> Reset mapping</button>
    </>
  );
}
