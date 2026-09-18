import { useState } from 'react';

/** A draggable before/after comparison. `before` shows on the left of the
 * divider, `after` on the right — so a mill operator can confirm the reduced
 * design still matches the original at every point of the slider. Both images
 * are stacked at full size; the "before" layer is clipped to the divider so
 * the two always stay in perfect registration. */
export function BeforeAfter({ before, after, beforeLabel = 'Original', afterLabel = 'Reduced' }:
  { before: string; after: string; beforeLabel?: string; afterLabel?: string }) {
  const [pos, setPos] = useState(50);
  return (
    <div className="compare">
      <img src={after} alt={afterLabel} draggable={false} />
      <img src={before} alt={beforeLabel} draggable={false}
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
      <div className="compare-divider" style={{ left: pos + '%' }} />
      <span className="compare-label compare-label-left">{beforeLabel}</span>
      <span className="compare-label compare-label-right">{afterLabel}</span>
      <input className="compare-slider" type="range" min={0} max={100} value={pos}
        onChange={e => setPos(Number(e.target.value))} aria-label="Compare original and reduced" />
    </div>
  );
}
