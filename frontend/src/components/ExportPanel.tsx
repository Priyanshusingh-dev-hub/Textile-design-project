import { useState } from 'react';
import { Download } from 'lucide-react';
import { API, downloadZip, downloadSvg } from '../api';
import type { ImageInfo, Layer } from '../types';

function downloadBlob(blob: Blob, filename: string) {
  const u = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = u; a.download = filename; a.click(); URL.revokeObjectURL(u);
}

// smoothness 0-100 -> (blur radius, simplify epsilon): higher smoothness
// traces a softer curve and drops more redundant points, closer to a
// hand-simplified pen-tool path; lower stays closer to the raw pixel shape.
function smoothnessToParams(smoothness: number) {
  return { blur: 0.6 + (smoothness / 100) * 2.4, simplify: 0.3 + (smoothness / 100) * 1.7, corner_angle: 32 };
}

export function ExportPanel({ img, layers }: { img?: ImageInfo; layers: Layer[] }) {
  const [smoothness, setSmoothness] = useState(55);
  const items = layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  const exportOne = async (fmt: string) => {
    if (!img) return;
    const r = await fetch(API + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_id: img.image_id, format: fmt, dpi: 300 }) });
    downloadBlob(await r.blob(), `loomlab.${fmt}`);
  };
  const exportSvg = (perLayer: boolean) => {
    const { blur, simplify, corner_angle } = smoothnessToParams(smoothness);
    downloadSvg({ layers: items, blur, simplify, corner_angle, per_layer: perLayer },
      perLayer ? 'loomlab-vectors.zip' : 'loomlab-design.svg');
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

          <label>Vector curve smoothness <output>{smoothness}%</output></label>
          <input type="range" min={0} max={100} value={smoothness} onChange={e => setSmoothness(+e.target.value)} />
          <p className="muted">Traces each ink into real Bezier curves — pen-tool clean edges, not a pixel staircase. Higher smooths more; sharp corners are still detected and kept sharp.</p>
          <a className="export" href="" onClick={e => { e.preventDefault(); exportSvg(false); }} title="One vector SVG with every ink as its own smooth path">
            Export vector design (.svg) <Download size={16} />
          </a>
          <a className="export" href="" onClick={e => { e.preventDefault(); exportSvg(true); }} title="A separate vector SVG per ink colour, zipped">
            Export vector layers (.zip SVG) <Download size={16} />
          </a>
        </>
      )}
    </>
  );
}
