import { Eye, EyeOff, Grid3x3, Download } from 'lucide-react';
import { downloadZip, imageUrl } from '../api';
import type { ImageInfo, Layer, Palette } from '../types';

export function LayerPanel({ layers, palette, img, onToggle, onOpacityChange, onHalftonePreview }: {
  layers: Layer[]; palette: Palette[]; img?: ImageInfo;
  onToggle: (index: number) => void; onOpacityChange: (index: number, value: number) => void;
  onHalftonePreview: (index: number) => void;
}) {
  if (!layers.length) return <p className="muted">Create separations from Color Separation.</p>;
  const totalCoverage = layers.reduce((sum, l) => sum + l.coverage, 0);
  const items = layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  return (
    <>
      <div className="summary">
        <div><small>COLORS</small><b>{palette.length || layers.length}</b></div>
        <div><small>SCREENS</small><b>{layers.length}</b></div>
        <div><small>DIMENSIONS</small><b>{img ? `${img.width}×${img.height}` : '—'}</b></div>
        <div><small>TOTAL INK</small><b>{totalCoverage.toFixed(1)}%</b></div>
      </div>
      <a className="export" href="" onClick={e => { e.preventDefault(); downloadZip({ layers: items, content: 'plate', format: 'png', dpi: 300 }, 'loomlab-plates.zip'); }}>Download colour plates (300 DPI) <Download size={16} /></a>
      <a className="export" href="" onClick={e => { e.preventDefault(); downloadZip({ layers: items, content: 'film', format: 'tiff', dpi: 300 }, 'loomlab-screens.zip'); }}>Download film screens (300 DPI) <Download size={16} /></a>
      {layers.map((l, i) => (
        <div className="layer" key={l.id}>
          <button onClick={() => onToggle(i)}>{l.visible ? <Eye size={16} /> : <EyeOff size={16} />}</button>
          {l.halftonePreviewUrl ? <img className="layer-thumb" src={imageUrl(l.halftonePreviewUrl)} /> : <i style={{ background: l.color }}></i>}
          <div>
            <b>{l.name}</b>
            <div className="coverage-bar"><span style={{ width: `${l.coverage}%` }} /></div>
            <small>{l.coverage}% coverage</small>
          </div>
          <button className="icon" title="Preview as a printable halftone dot pattern" onClick={() => onHalftonePreview(i)}><Grid3x3 size={14} /></button>
          <input type="range" min="0" max="100" value={l.opacity ?? 100} onChange={e => onOpacityChange(i, +e.target.value)} />
        </div>
      ))}
    </>
  );
}
