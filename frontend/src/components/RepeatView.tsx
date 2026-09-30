import { useEffect, useState } from 'react';
import { imageUrl } from '../api';
import { REPEAT_TILE, repeatTiles, type RepeatMode } from '../lib/repeat';
import { useT } from '../lib/i18n';

/** The design 3 x 3 as it runs on the cloth, drawn in the browser from one
 *  small copy (the server shrinks it once and caches it). */
export function RepeatView({ path, mode }: { path: string; mode: Exclude<RepeatMode, 'off'> }) {
  const t = useT();
  const [url, setUrl] = useState<string>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let gone = false;
    let made: string | undefined;
    setFailed(false);
    const im = new Image();
    im.onload = () => {
      const w = im.naturalWidth, h = im.naturalHeight;
      const c = document.createElement('canvas');
      c.width = 3 * w; c.height = 3 * h;
      const g = c.getContext('2d');
      if (!g) { setFailed(true); return; }
      for (const [x, y] of repeatTiles(w, h, mode)) g.drawImage(im, x, y);     // 1:1, never scaled
      c.toBlob(b => {
        if (gone || !b) return;
        made = URL.createObjectURL(b);
        setUrl(made);
      });
    };
    im.onerror = () => { if (!gone) setFailed(true); };
    im.src = `${imageUrl(path)}?max_side=${REPEAT_TILE}`;
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [path, mode]);
  if (failed) return <div className="canvas empty">{t('The repeat could not be drawn here.')}</div>;
  return url ? <img src={url} alt={t(mode === 'half' ? 'half-drop repeat' : 'straight repeat')} />
    : <div className="canvas empty">{t('Laying out the repeat…')}</div>;
}
