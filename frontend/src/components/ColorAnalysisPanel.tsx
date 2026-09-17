import { Download } from 'lucide-react';
import type { Palette } from '../types';
import { PaletteView } from './shared';

function downloadFile(blob: Blob, name: string) {
  const u = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u);
}

function downloadPaletteCard(palette: Palette[]) {
  const cols = Math.min(palette.length, 5), rows = Math.ceil(palette.length / cols);
  const sw = 150, sh = 180, pad = 16;
  const c = document.createElement('canvas'); c.width = cols * sw + pad * 2; c.height = rows * sh + pad * 2;
  const x = c.getContext('2d'); if (!x) return;
  x.fillStyle = '#ffffff'; x.fillRect(0, 0, c.width, c.height);
  palette.forEach((p, i) => {
    const cx = pad + (i % cols) * sw, cy = pad + Math.floor(i / cols) * sh;
    x.fillStyle = p.hex; x.fillRect(cx + 8, cy + 8, sw - 16, sw - 16);
    x.strokeStyle = '#00000022'; x.strokeRect(cx + 8, cy + 8, sw - 16, sw - 16);
    x.fillStyle = '#111111'; x.font = 'bold 15px monospace'; x.fillText(p.hex.toUpperCase(), cx + 8, cy + sw + 12);
    x.fillStyle = '#666666'; x.font = '12px monospace'; x.fillText(`${p.coverage}% · rgb(${p.rgb.join(',')})`, cx + 8, cy + sw + 32);
  });
  c.toBlob(b => { if (b) downloadFile(b, 'loomlab-palette.png'); });
}

function downloadHexList(palette: Palette[]) {
  const text = palette.map((p, i) => `${i + 1}. ${p.hex.toUpperCase()}  rgb(${p.rgb.join(', ')})  ${p.coverage}%`).join('\n');
  downloadFile(new Blob([text], { type: 'text/plain' }), 'loomlab-palette.txt');
}

export function ColorAnalysisPanel({ colorCount, setColorCount, onAnalyze, onReduce, palette, accuracy }: {
  colorCount: number; setColorCount: (n: number) => void; onAnalyze: () => void; onReduce: () => void; palette: Palette[];
  accuracy?: { accuracy: number; deltaE: number } | null;
}) {
  return (
    <>
      <label>Production color count <output>{colorCount}</output></label>
      <input type="range" min="2" max="20" value={colorCount} onChange={e => setColorCount(+e.target.value)} />
      <p className="muted">Up to 20 inks. Reduce keeps exactly this many: near-duplicate shades are merged and the least important colours (rare and similar to another) drop first, so heavily-used and visually distinct colours survive — even small ones like a lone accent flower.</p>
      <div className="row"><button className="secondary" onClick={onAnalyze}>Analyze Colors</button><button className="primary" onClick={onReduce}>Reduce Colors</button></div>
      {accuracy && (
        <div className="accuracy">
          <div className="accuracy-bar"><span style={{ width: `${accuracy.accuracy}%` }} /></div>
          <b>{accuracy.accuracy}% match</b> <small>mean ΔE2000 {accuracy.deltaE} · lower is closer</small>
        </div>
      )}
      <PaletteView palette={palette} />
      {!!palette.length && (
        <>
          <a className="export" href="" onClick={e => { e.preventDefault(); downloadPaletteCard(palette); }}>Download palette card (.png) <Download size={16} /></a>
          <a className="export" href="" onClick={e => { e.preventDefault(); downloadHexList(palette); }}>Download hex list (.txt) <Download size={16} /></a>
        </>
      )}
    </>
  );
}
