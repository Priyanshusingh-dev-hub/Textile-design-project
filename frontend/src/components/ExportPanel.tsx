import { Download } from 'lucide-react';
import { API } from '../api';
import type { ImageInfo } from '../types';

export function ExportPanel({ img }: { img?: ImageInfo }) {
  const exportOne = async (fmt: string) => {
    if (!img) return;
    const r = await fetch(API + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_id: img.image_id, format: fmt, dpi: 300 }) });
    const b = await r.blob(); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `loomlab.${fmt}`; a.click(); URL.revokeObjectURL(u);
  };
  return (
    <>
      <p className="muted">Export the active composite; PSD is a Photoshop-compatible flattened file.</p>
      {['png', 'jpg', 'webp', 'psd'].map(fmt => (
        <a key={fmt} className="export" href={img ? `${API}/export` : ''} onClick={e => { e.preventDefault(); exportOne(fmt); }}>
          Export {fmt.toUpperCase()} <Download size={16} />
        </a>
      ))}
    </>
  );
}
