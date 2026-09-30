import { useRef, useState, useCallback, WheelEvent, PointerEvent } from 'react';
import { RepeatView } from './RepeatView';
import { NEXT_REPEAT, REPEAT_LABEL, type RepeatMode } from '../lib/repeat';
import { useT } from '../lib/i18n';

/** A pan/zoom viewport for inspecting prepress detail: scroll to zoom toward the
 * cursor, drag to pan, double-click to reset. Keeps a mill operator able to
 * check edge cleanliness and fine motifs without leaving the app. With
 * `repeatOf` (a stored image), a button also lays the design out 3 x 3 as it
 * runs on the cloth. */
export function Zoomable({ children, repeatOf }: { children: React.ReactNode; repeatOf?: string }) {
  const tr = useT();
  const [t, setT] = useState({ s: 1, x: 0, y: 0 });
  const [repeat, setRepeat] = useState<RepeatMode>('off');
  const mode = repeatOf ? repeat : 'off';
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
        {mode === 'off' ? children : <RepeatView path={repeatOf!} mode={mode} />}
      </div>
      {repeatOf && <button className={'zoom-repeat' + (mode !== 'off' ? ' on' : '')}
        title={tr('See the design as it runs on the cloth: straight, then half-drop (every other column dropped by half). Only a view — the films are the design once.')}
        onPointerDown={e => e.stopPropagation()} onDoubleClick={e => e.stopPropagation()}
        onClick={e => { e.stopPropagation(); setRepeat(NEXT_REPEAT[mode]); reset(); }}>{tr(REPEAT_LABEL[mode])}</button>}
      {t.s > 1 && <button className="zoom-reset" onClick={e => { e.stopPropagation(); reset(); }}>{t.s.toFixed(1)}× · reset</button>}
    </div>
  );
}
