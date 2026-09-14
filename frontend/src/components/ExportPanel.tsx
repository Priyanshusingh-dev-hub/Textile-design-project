import { Download } from 'lucide-react';
import { API } from '../api';
import type { ImageInfo, Layer } from '../types';

function downloadBlob(blob: Blob, filename: string) {
  const u = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = u; a.download = filename; a.click(); URL.revokeObjectURL(u);
}

export function ExportPanel({ img, layers }: { img?: ImageInfo; layers: Layer[] }) {
  const exportOne = async (fmt: string) => {
    if (!img) return;
    const r = await fetch(API + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_id: img.image_id, format: fmt, dpi: 300 }) });
    downloadBlob(await r.blob(), `loomlab.${fmt}`);
  };
  const exportZip = async () => {
    const r = await fetch(API + '/export/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layers: layers.map(l => ({ id: l.id, name: l.name })), composite_image_id: img?.image_id }) });
    if (!r.ok) return;
    downloadBlob(await r.blob(), 'loomlab-layers.zip');
  };
  const exportScreens = async () => {
    const r = await fetch(API + '/export/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layers: layers.map(l => ({ id: l.id, name: l.name })), format: 'tiff', dpi: 300 }) });
    if (!r.ok) return;
    downloadBlob(await r.blob(), 'loomlab-screens.zip');
  };
  return (
    <>
      <p className="muted">Export the active composite; PSD is a Photoshop-compatible flattened file.</p>
      {['png', 'jpg', 'webp', 'psd'].map(fmt => (
        <a key={fmt} className="export" href={img ? `${API}/export` : ''} onClick={e => { e.preventDefault(); exportOne(fmt); }}>
          Export {fmt.toUpperCase()} <Download size={16} />
        </a>
      ))}
      {!!layers.length && (
        <>
          <a className="export" href="" onClick={e => { e.preventDefault(); exportZip(); }}>
            Export all layers (.zip) <Download size={16} />
          </a>
          <a className="export" href="" onClick={e => { e.preventDefault(); exportScreens(); }} title="Print-ready B&amp;W screens (300 DPI TIFF), one file per ink">
            Export production screens (.zip TIFF) <Download size={16} />
          </a>
        </>
      )}
    </>
  );
}
