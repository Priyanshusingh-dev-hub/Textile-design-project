import { Repeat2 } from 'lucide-react';
import type { Seam } from '../types';

export function RepeatPanel({ repeatMode, setRepeatMode, onMakeRepeat, onCheckSeam, seam }: {
  repeatMode: string; setRepeatMode: (m: string) => void; onMakeRepeat: () => void; onCheckSeam: () => void; seam?: Seam;
}) {
  return (
    <>
      <label>Repeat construction</label>
      <select value={repeatMode} onChange={e => setRepeatMode(e.target.value)}>
        <option value="grid">Straight repeat</option>
        <option value="half-drop">Half-drop</option>
        <option value="brick">Brick repeat</option>
        <option value="mirror">Mirror repeat</option>
      </select>
      <div className="repeat-grid"><span>4 columns</span><span>3 rows</span></div>
      <button className="primary wide" onClick={onMakeRepeat}><Repeat2 size={16} /> Create repeat preview</button>
      <button className="secondary wide" onClick={onCheckSeam}>Check Seam</button>
      {seam && <div className={'seam ' + seam.rating.replace(' ', '-')}><b>{seam.rating}</b><small>Left ↔ Right {seam.left_right} · Top ↔ Bottom {seam.top_bottom}</small></div>}
    </>
  );
}
