import type { Palette, SeparationMode } from '../types';
import { PaletteView } from './shared';

export function SeparationPanel({ palette, mode, setMode, onSeparate }: {
  palette: Palette[]; mode: SeparationMode; setMode: (m: SeparationMode) => void; onSeparate: () => void;
}) {
  return (
    <>
      <p className="muted">Generate transparent, exportable ink masks from your active palette.</p>
      <label>Separation style</label>
      <select value={mode} onChange={e => setMode(e.target.value as SeparationMode)}>
        <option value="flat">Flat colors (exclusive spot color)</option>
        <option value="gradient">Gradient / tonal (soft blended ink)</option>
      </select>
      <PaletteView palette={palette} />
      <button className="primary wide" onClick={onSeparate}>Create separations</button>
    </>
  );
}
