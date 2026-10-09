import { useState } from 'react';
import { Download } from 'lucide-react';
import type { DownloadFn, ImageInfo, Layer } from '../types';

// smoothness 0-100 -> (blur radius, simplify epsilon): higher smoothness
// traces a softer curve and drops more redundant points, closer to a
// hand-simplified pen-tool path; lower stays closer to the raw pixel shape.
function smoothnessToParams(smoothness: number) {
  return { blur: 0.6 + (smoothness / 100) * 2.4, simplify: 0.3 + (smoothness / 100) * 1.7, corner_angle: 32 };
}

export function ExportPanel({ img, layers, onDownload }: { img?: ImageInfo; layers: Layer[]; onDownload: DownloadFn }) {
  const [smoothness, setSmoothness] = useState(55);
  const [minArea, setMinArea] = useState(20);
  const [regMarks, setRegMarks] = useState(true);
  const items = layers.map(l => ({ id: l.id, name: l.name, color: l.color }));
  const exportSvg = (perLayer: boolean) => {
    const { blur, simplify, corner_angle } = smoothnessToParams(smoothness);
    onDownload('/export/svg', { layers: items, blur, simplify, corner_angle, min_area: minArea, per_layer: perLayer },
      perLayer ? 'loomlab-vectors.zip' : 'loomlab-design.svg');
  };
  return (
    <>
      <p className="muted">Export the active composite; PSD is a Photoshop-compatible flattened file. JPG and PSD place transparent areas on white.</p>
      {!img && <p className="muted">Import a design to enable exports.</p>}
      {['png', 'jpg', 'webp', 'psd'].map(fmt => (
        <button key={fmt} className="export" disabled={!img} onClick={() => img && onDownload('/export', { image_id: img.image_id, format: fmt, dpi: 300 }, `loomlab.${fmt}`)}>
          Export {fmt.toUpperCase()} <Download size={16} />
        </button>
      ))}
      {!!layers.length && (
        <>
          <button className="export" onClick={() => onDownload('/export/zip', { layers: items, composite_image_id: img?.image_id, content: 'mask', format: 'png', dpi: 300 }, 'loomlab-layers.zip')}>
            Export all layers (.zip) <Download size={16} />
          </button>
          <button className="export" onClick={() => onDownload('/export/zip', { layers: items, content: 'plate', format: 'png', dpi: 300 }, 'loomlab-plates.zip')} title="Colour plates (ink on white) at 300 DPI, one file per ink">
            Export colour plates (.zip PNG, 300 DPI) <Download size={16} />
          </button>
          <label className="checkline"><input type="checkbox" checked={regMarks} onChange={e => setRegMarks(e.target.checked)} /> Add registration marks to screens</label>
          <p className="muted">Prints an identical crosshair target in each corner of every screen so the press operator can align all the inks. Marks sit in an added white margin, never over the artwork.</p>
          <button className="export" onClick={() => onDownload('/export/zip', { layers: items, content: 'film', format: 'tiff', dpi: 300, reg_marks: regMarks }, 'loomlab-screens.zip')} title="Print-ready B&amp;W screens at 300 DPI TIFF, one file per ink">
            Export production screens (.zip TIFF, 300 DPI) <Download size={16} />
          </button>

          <label>Vector curve smoothness <output>{smoothness}%</output></label>
          <input type="range" min={0} max={100} value={smoothness} onChange={e => setSmoothness(+e.target.value)} />
          <p className="muted">Traces each ink into real Bezier curves — pen-tool clean edges, not a pixel staircase. Higher smooths more; sharp corners are still detected and kept sharp.</p>

          <label>Remove scan-noise specks <output>{minArea}px²</output></label>
          <input type="range" min={0} max={80} value={minArea} onChange={e => setMinArea(+e.target.value)} />
          <p className="muted">Drops stray dots and JPEG-edge noise below this size so the export has one clean path per real motif instead of hundreds of fragments. Lower it if your design has genuinely tiny details.</p>
          <button className="export" onClick={() => exportSvg(false)} title="One vector SVG with every ink as its own smooth path">
            Export vector design (.svg) <Download size={16} />
          </button>
          <button className="export" onClick={() => exportSvg(true)} title="A separate vector SVG per ink colour, zipped">
            Export vector layers (.zip SVG) <Download size={16} />
          </button>
        </>
      )}
    </>
  );
}
