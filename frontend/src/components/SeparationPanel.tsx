import type { Palette, SeparationMode } from '../types';
import { PaletteView } from './shared';

export function SeparationPanel({ palette, mode, setMode, cleanup, setCleanup, onSeparate }: {
  palette: Palette[]; mode: SeparationMode; setMode: (m: SeparationMode) => void;
  cleanup: number; setCleanup: (n: number) => void; onSeparate: () => void;
}) {
  return (
    <>
      <p className="muted">Generate transparent, exportable ink masks from your active palette.</p>
      <label>Separation style</label>
      <select value={mode} onChange={e => setMode(e.target.value as SeparationMode)}>
        <option value="flat">Flat colors (exclusive spot color)</option>
        <option value="gradient">Gradient / tonal (soft blended ink)</option>
      </select>
      {mode === 'flat' && (
        <>
          <label>Edge cleanup <output>{['Off', 'Light', 'Normal', 'Strong', 'Heavy', 'Max'][cleanup]}</output></label>
          <input type="range" min="0" max="5" value={cleanup} onChange={e => setCleanup(+e.target.value)} />
          <p className="muted">Higher removes scan speckle and sharpens screen boundaries; too high can soften fine detail.</p>
        </>
      )}
      <PaletteView palette={palette} />
      <button className="primary wide" onClick={onSeparate}>Create separations</button>
    </>
  );
}
