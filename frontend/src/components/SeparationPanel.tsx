import type { Palette } from '../types';
import { PaletteView } from './shared';

export function SeparationPanel({ palette, onSeparate }: { palette: Palette[]; onSeparate: () => void }) {
  return (
    <>
      <p className="muted">Generate transparent, exportable ink masks from your active palette.</p>
      <PaletteView palette={palette} />
      <button className="primary wide" onClick={onSeparate}>Create separations</button>
    </>
  );
}
