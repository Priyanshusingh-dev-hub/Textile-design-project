import type { Palette, SeparationMode } from '../types';
import { PaletteView } from './shared';

export function SeparationPanel({ palette, mode, setMode, cleanup, setCleanup, edgeStrength, setEdgeStrength, minRegion, setMinRegion, onSeparate }: {
  palette: Palette[]; mode: SeparationMode; setMode: (m: SeparationMode) => void;
  cleanup: number; setCleanup: (n: number) => void;
  edgeStrength: number; setEdgeStrength: (n: number) => void;
  minRegion: number; setMinRegion: (n: number) => void;
  onSeparate: () => void;
}) {
  return (
    <>
      <p className="muted">Generate transparent, exportable ink masks from your active palette.</p>
      <label>Separation style</label>
      <select value={mode} onChange={e => setMode(e.target.value as SeparationMode)}>
        <option value="flat">Flat colors (exclusive spot color)</option>
        <option value="region">Region flatten (one flat color per shape — pen-tool clean)</option>
        <option value="gradient">Gradient / tonal (soft blended ink)</option>
      </select>
      {mode === 'flat' && (
        <>
          <label>Edge cleanup <output>{['Off', 'Light', 'Normal', 'Strong', 'Heavy', 'Max'][cleanup]}</output></label>
          <input type="range" min="0" max="5" value={cleanup} onChange={e => setCleanup(+e.target.value)} />
          <p className="muted">Higher removes scan speckle and sharpens screen boundaries; too high can soften fine detail.</p>
        </>
      )}
      {mode === 'region' && (
        <>
          <p className="muted">Detects each outlined shape and fills it with a single flat colour — a shaded petal becomes one clean ink instead of a highlight/shadow split. Best for block-print / outlined artwork.</p>
          <label>Outline sensitivity <output>{edgeStrength}</output></label>
          <input type="range" min="4" max="40" value={edgeStrength} onChange={e => setEdgeStrength(+e.target.value)} />
          <p className="muted">Lower catches finer outlines (more, smaller regions); higher keeps only strong outlines (fewer, larger shapes). If colours bleed across an outline, lower this.</p>
          <label>Remove tiny regions <output>{minRegion}px²</output></label>
          <input type="range" min="0" max="400" value={minRegion} onChange={e => setMinRegion(+e.target.value)} />
          <p className="muted">Absorbs speck-sized regions into their surroundings so each real shape stays one clean fill.</p>
        </>
      )}
      <PaletteView palette={palette} />
      <button className="primary wide" onClick={onSeparate}>Create separations</button>
    </>
  );
}
