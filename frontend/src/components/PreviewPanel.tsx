import type { Seam } from '../types';
import { SeamResult } from './shared';

export function PreviewPanel({ onCheckSeam, seam }: { onCheckSeam: () => void; seam?: Seam }) {
  return (
    <>
      <p className="muted">Use the center canvas to inspect your repeat. The image is a preview; export keeps native resolution.</p>
      <button className="secondary wide" onClick={onCheckSeam}>Check Seam</button>
      <SeamResult seam={seam} />
    </>
  );
}
