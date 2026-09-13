import type { Palette } from '../types';
import { PaletteView } from './shared';

export function ColorAnalysisPanel({ colorCount, setColorCount, onAnalyze, onReduce, palette }: {
  colorCount: number; setColorCount: (n: number) => void; onAnalyze: () => void; onReduce: () => void; palette: Palette[];
}) {
  return (
    <>
      <label>Production color count <output>{colorCount}</output></label>
      <input type="range" min="2" max="20" value={colorCount} onChange={e => setColorCount(+e.target.value)} />
      <div className="row"><button className="secondary" onClick={onAnalyze}>Analyze Colors</button><button className="primary" onClick={onReduce}>Reduce Colors</button></div>
      <PaletteView palette={palette} />
    </>
  );
}
