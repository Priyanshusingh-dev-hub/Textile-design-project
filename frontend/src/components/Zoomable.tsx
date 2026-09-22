import { useRef, useState, useCallback, WheelEvent, PointerEvent } from 'react';

/** A pan/zoom viewport for inspecting prepress detail: scroll to zoom toward the
 * cursor, drag to pan, double-click to reset. Keeps a mill operator able to
 * check edge cleanliness and fine motifs without leaving the app. */
export function Zoomable({ children }: { children: React.ReactNode }) {
  const [t, setT] = useState({ s: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const r = box.current!.getBoundingClientRect();
    const cx = e.clientX - r.left - r.width / 2;
    const cy = e.clientY - r.top - r.height / 2;
    setT(p => {
      const s = Math.min(12, Math.max(1, p.s * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      if (s === 1) return { s: 1, x: 0, y: 0 };
      const k = s / p.s;
      return { s, x: cx - (cx - p.x) * k, y: cy - (cy - p.y) * k };
    });
  }, []);

  const onDown = (e: PointerEvent) => {
    if (t.s === 1) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, ox: t.x, oy: t.y };
  };
  const onMove = (e: PointerEvent) => {
    if (!drag.current) return;
    setT(p => ({ ...p, x: drag.current!.ox + (e.clientX - drag.current!.x), y: drag.current!.oy + (e.clientY - drag.current!.y) }));
  };
  const onUp = () => { drag.current = null; };
  const reset = () => setT({ s: 1, x: 0, y: 0 });

  return (
    <div ref={box} className="zoom" onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove}
      onPointerUp={onUp} onPointerLeave={onUp} onDoubleClick={reset}
      style={{ cursor: t.s > 1 ? (drag.current ? 'grabbing' : 'grab') : 'zoom-in' }}>
      <div className="zoom-inner" style={{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.s})` }}>
        {children}
      </div>
      {t.s > 1 && <button className="zoom-reset" onClick={e => { e.stopPropagation(); reset(); }}>{t.s.toFixed(1)}× · reset</button>}
    </div>
  );
}
