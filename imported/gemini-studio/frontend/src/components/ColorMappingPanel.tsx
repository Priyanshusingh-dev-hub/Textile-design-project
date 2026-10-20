import { RotateCcw } from 'lucide-react';

export type Mapping = { source: string; target: string };

export function ColorMappingPanel({ mapping, setMapping, onApply, onReset }: {
  mapping: Mapping; setMapping: (m: Mapping) => void; onApply: () => void; onReset: () => void;
}) {
  return (
    <>
      <p className="muted">Map a source ink to a target ink. Changes preserve the original import and can be undone.</p>
      <label>Source color</label>
      <input type="color" value={mapping.source} onChange={e => setMapping({ ...mapping, source: e.target.value })} />
      <label>Target color</label>
      <input type="color" value={mapping.target} onChange={e => setMapping({ ...mapping, target: e.target.value })} />
      <button className="primary wide" onClick={onApply}>Apply mapping</button>
      <button className="secondary wide" onClick={onReset}><RotateCcw size={15} /> Reset mapping</button>
    </>
  );
}
