import { Eye, EyeOff, Grid3x3, Download } from 'lucide-react';
import { imageUrl } from '../api';
import type { DownloadFn, ImageInfo, Layer, Palette } from '../types';

export function LayerPanel({ layers, palette, img, onToggle, onOpacityChange, onHalftonePreview, onRename, trap, onDownload }: {
  layers: Layer[]; palette: Palette[]; img?: ImageInfo;
  onToggle: (index: number) => void; onOpacityChange: (index: number, value: number) => void;
  onHalftonePreview: (index: number) => void; onRename: (index: number, name: string) => void;
  trap: number; onDownload: DownloadFn;
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
      <button className="export" onClick={() => onDownload('/export/zip', { layers: items, content: 'plate', format: 'png', dpi: 300, trap }, 'loomlab-plates.zip')}>Download colour plates (300 DPI) <Download size={16} /></button>
      <button className="export" onClick={() => onDownload('/export/zip', { layers: items, content: 'film', format: 'tiff', dpi: 300, reg_marks: true, trap }, 'loomlab-screens.zip')} title="Print-ready screens with registration marks">Download film screens (300 DPI) <Download size={16} /></button>
      <button className="export" onClick={() => onDownload('/export/psd-multichannel', { layers: items, dpi: 300, reg_marks: true, trap }, 'loomlab-separation.psd')} title="One PSD with a named spot channel per ink">Download multichannel PSD <Download size={16} /></button>
      <p className="muted">Click an ink's name to rename it — names go into every export (e.g. "1 RED 120"). Trapping: {trap ? `${trap} px` : 'off'} (set in Export).</p>
      {layers.map((l, i) => (
        <div className="layer" key={l.id}>
          <button onClick={() => onToggle(i)} title={l.visible ? 'Hide this ink' : 'Show this ink'}>{l.visible ? <Eye size={16} /> : <EyeOff size={16} />}</button>
          {l.halftonePreviewUrl ? <img className="layer-thumb" src={imageUrl(l.halftonePreviewUrl)} alt={`${l.name} halftone`} /> : <i style={{ background: l.color }}></i>}
          <div>
            <input className="layer-name" value={l.name} maxLength={60} aria-label={`Name of ink ${i + 1}`} title="Rename this ink"
              onChange={e => onRename(i, e.target.value)} onBlur={e => { if (!e.target.value.trim()) onRename(i, `Ink ${i + 1}`); }} />
            <div className="coverage-bar"><span style={{ width: `${l.coverage}%` }} /></div>
            <small>{l.coverage}% coverage</small>
          </div>
          <button className="icon" title="Preview as a printable halftone dot pattern" onClick={() => onHalftonePreview(i)}><Grid3x3 size={14} /></button>
          <input type="range" min="0" max="100" value={l.opacity ?? 100} onChange={e => onOpacityChange(i, +e.target.value)} title={`Opacity ${l.opacity ?? 100}%`} />
        </div>
      ))}
    </>
  );
}
