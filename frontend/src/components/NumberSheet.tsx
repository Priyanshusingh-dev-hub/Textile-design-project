import { useEffect, useMemo, useRef, useState } from 'react';
import { getJson, imageUrl, screenUrl } from '../api';
import type { LoomLab } from '../hooks/useLoomLab';
import { useT } from '../lib/i18n';
import { areaAt, areaList, idsFromRgba, paintPicked, toggleArea } from '../lib/areas';
import { parseAreaNumbers } from '../lib/numbering';

type AreasMap = { url: string; width: number; height: number; areas: number; colours: Record<string, string> };

/** The numbered sheet of a numbering run, and the easiest way to change colours on it: click an area to pick
 *  it (again to drop it), or type numbers; pick a colour (or take one from another area, or from an ink the
 *  design has) and press the button: the zip, plates, channels and design follow. */
export function NumberSheet({ w }: { w: LoomLab }) {
  const { numberInfo: n, busy, recolourAreas, palette } = w;
  const t = useT();
  const [view, setView] = useState<'colours' | 'sketch'>('colours');
  const [text, setText] = useState('');
  const [hex, setHex] = useState('#1F2A60');
  const [taking, setTaking] = useState(false);
  const [big, setBig] = useState(false);              // the sheet full screen, the controls beside it
  const [map, setMap] = useState<AreasMap | null>(null);
  const [hover, setHover] = useState(0);
  const ids = useRef<Uint16Array | null>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const job = n?.job, areas = n?.areas ?? 0;
  const picked = parseAreaNumbers(text, areas);
  const list = useMemo(() => (Array.isArray(picked) ? picked : []), [picked && Array.isArray(picked) ? picked.join(',') : picked]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                  // what each area prints in comes with this zip: ask again per zip
    if (!job) return;
    let live = true;
    (async () => {
      try {
        const m = await getJson<AreasMap>(`/number/${job}/areas-map`);
        const image = new Image();
        image.onload = () => {
          if (!live) return;
          const c = document.createElement('canvas');
          c.width = m.width; c.height = m.height;
          const g = c.getContext('2d', { willReadFrequently: true });
          if (!g) return;
          g.drawImage(image, 0, 0);
          ids.current = idsFromRgba(g.getImageData(0, 0, m.width, m.height).data, m.width * m.height);
          setMap(m);
        };
        image.src = imageUrl(m.url);
      } catch { if (live) { setMap(null); ids.current = null; } }   // no map (a gone run): the typed numbers still work
    })();
    return () => { live = false; };
  }, [job]);

  useEffect(() => { setText(''); setTaking(false); }, [job]);   // a new zip: the edit is done

  useEffect(() => {                                  // the highlight on the picture
    const c = overlay.current;
    if (!c || !map || !ids.current) return;
    c.width = map.width; c.height = map.height;
    const g = c.getContext('2d');
    if (!g) return;
    const data = g.createImageData(map.width, map.height);
    paintPicked(ids.current, new Set(list), data.data, [255, 0, 170, 130]);
    g.putImageData(data, 0, 0);
  }, [map, list]);

  if (!n) return null;
  const shown = view === 'colours' && n.flat_numbers_url ? n.flat_numbers_url : n.sheet_url;

  const at = (e: React.MouseEvent): number => {
    const el = img.current;
    if (!el || !map || !ids.current) return 0;
    const r = el.getBoundingClientRect();
    return areaAt(ids.current, map.width, map.height, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
  };
  const click = (e: React.MouseEvent) => {
    const a = at(e);
    if (!a || busy) return;
    if (taking) {
      const c = map?.colours[String(a)];
      if (c) setHex(c.toUpperCase());
      setTaking(false);
    } else setText(areaList(toggleArea(list, a)));
  };
  const inks = palette.slice(0, 12);

  return (
    <div className={'number-pick' + (big ? ' big' : '')}>
      <div className="ns-sheet">
      <div className="number-views">
        {n.flat_numbers_url && (
          <button className={'mini' + (view === 'colours' ? ' go' : '')} onClick={() => setView('colours')}>{t('Colours + numbers')}</button>
        )}
        <button className={'mini' + (view === 'sketch' || !n.flat_numbers_url ? ' go' : '')} onClick={() => setView('sketch')}>{t('Sketch + numbers')}</button>
        <button className="mini" onClick={() => setBig(v => !v)}>{t(big ? '✕ Close' : '⤢ Bigger')}</button>
      </div>
      <div className={'number-sheet picker' + (map ? ' live' : '') + (taking ? ' taking' : '')}
        onClick={click} onMouseMove={e => map && setHover(at(e))} onMouseLeave={() => setHover(0)}>
        <img ref={img} src={screenUrl(shown)} alt={t('Numbered sketch')} draggable={false} />
        <canvas ref={overlay} className="area-overlay" />
      </div>
      <p className="hint">
        {hover > 0 && map
          ? t('Area {n} · {hex}', { n: hover, hex: map.colours[String(hover)] ?? '' })
          : map ? t('Click an area to pick it (click again to drop it), or type numbers below.') : ''}
        {' '}
        {n.flat_numbers_url && <><a href={n.flat_numbers_url} target="_blank" rel="noreferrer">{t('Colours + numbers')}</a>{' · '}</>}
        <a href={n.sheet_url} target="_blank" rel="noreferrer">{t('Numbered sketch')}</a>{' · '}
        <a href={n.numbers_url} target="_blank" rel="noreferrer">{t('Numbers on the colour design')}</a>
      </p>
      </div>
      <div className="area-colours ns-side">
        <b>{t('Change colours by number')}</b>
        <input type="text" placeholder="101, 104, 110-115" value={text} disabled={busy} maxLength={400}
          onChange={e => setText(e.target.value)} />
        {picked === 'bad' && <small className="warn">{t('Numbers are not right: use 1 to {max}, like 101, 104, 110-115.', { max: n.areas })}</small>}
        <div className="area-colour">
          <label>{t('New colour')}
            <input type="color" value={hex} disabled={busy} onChange={e => setHex(e.target.value.toUpperCase())} />
          </label>
          <b>{hex}</b>
          {map && <button className={'mini' + (taking ? ' go' : '')} disabled={busy} onClick={() => setTaking(v => !v)}>
            {t(taking ? 'Click the area whose colour you want…' : 'Take the colour of an area')}</button>}
        </div>
        <div className="area-inks">
          {inks.map(p => (
            <button key={p.hex} className="plate-swatch" style={{ background: p.hex }} title={p.hex} disabled={busy}
              onClick={() => setHex(p.hex.toUpperCase())} />
          ))}
        </div>
        <button className="secondary wide" disabled={busy || !list.length} onClick={() => recolourAreas(list, hex)}>
          {t('Change {n} area(s) →', { n: list.length })}
        </button>
      </div>
    </div>
  );
}
