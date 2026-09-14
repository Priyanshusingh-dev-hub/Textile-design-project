import { Download } from 'lucide-react';
import { API, downloadZip } from '../api';
import type { ImageInfo, Layer } from '../types';

function downloadBlob(blob: Blob, filename: string) {
  const u = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = u; a.download = filename; a.click(); URL.revokeObjectURL(u);
}

export function ExportPanel({ img, layers }: { img?: ImageInfo; layers: Layer[] }) {
  const items = layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  const exportOne = async (fmt: string) => {
    if (!img) return;
    const r = await fetch(API + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_id: img.image_id, format: fmt, dpi: 300 }) });
    downloadBlob(await r.blob(), `loomlab.${fmt}`);
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
          <a className="export" href="" onClick={e => { e.preventDefault(); downloadZip({ layers: items, composite_image_id: img?.image_id, content: 'mask', format: 'png', dpi: 300 }, 'loomlab-layers.zip'); }}>
            Export all layers (.zip) <Download size={16} />
          </a>
          <a className="export" href="" onClick={e => { e.preventDefault(); downloadZip({ layers: items, content: 'plate', format: 'png', dpi: 300 }, 'loomlab-plates.zip'); }} title="Colour plates (ink on white) at 300 DPI, one file per ink">
            Export colour plates (.zip PNG, 300 DPI) <Download size={16} />
          </a>
          <a className="export" href="" onClick={e => { e.preventDefault(); downloadZip({ layers: items, content: 'film', format: 'tiff', dpi: 300 }, 'loomlab-screens.zip'); }} title="Print-ready B&amp;W screens at 300 DPI TIFF, one file per ink">
            Export production screens (.zip TIFF, 300 DPI) <Download size={16} />
          </a>
        </>
      )}
    </>
  );
}
