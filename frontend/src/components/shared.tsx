import type { Palette, ImageInfo, Seam } from '../types';
import type { ActionStatus } from '../hooks/useAsyncStatus';

export function PaletteView({ palette }: { palette: Palette[] }) {
  return <div className="palette">{palette.map((p, i) => <div className="swatch" key={p.hex + i}><i style={{ background: p.hex }}></i><div><b>{p.hex}</b><small>{p.coverage}% · {p.pixels.toLocaleString()} px</small></div></div>)}</div>;
}

export function Meta({ img }: { img: ImageInfo }) {
  return <div className="meta"><div><small>DIMENSIONS</small><b>{img.width} × {img.height} px</b></div><div><small>ASPECT</small><b>{(img.width / img.height).toFixed(2)}:1</b></div></div>;
}

const LABELS: Record<ActionStatus['state'], string> = { idle: 'LIVE', processing: 'PROCESSING', done: 'DONE', failed: 'FAILED' };

export function StatusBadge({ status }: { status: ActionStatus }) {
  return <span className={'status-badge status-' + status.state}>{LABELS[status.state]}</span>;
}

export function SeamResult({ seam }: { seam?: Seam }) {
  if (!seam) return null;
  return <div className={'seam ' + seam.rating.replace(' ', '-')}><b>{seam.rating}</b><small>Left ↔ Right {seam.left_right} · Top ↔ Bottom {seam.top_bottom}</small></div>;
}
