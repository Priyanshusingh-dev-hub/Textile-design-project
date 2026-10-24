import type { ImageInfo, Palette } from '../types';
import type { ActionStatus } from '../hooks/useAsyncStatus';

export function Footer({ status, message, img, palette }: {
  status: ActionStatus; message: string; img?: ImageInfo; palette: Palette[];
}) {
  const text = status.state === 'failed' ? (status.message || 'Processing failed.') : (status.state === 'processing' ? 'Processing image…' : message);
  return (
    <footer>
      <span className={status.state === 'processing' ? 'busy' : status.state === 'failed' ? 'busy failed' : ''}>{text}</span>
      <span>{img ? `${img.width} × ${img.height}px` : 'No image'} · {palette.length || '—'} colors · 100%</span>
    </footer>
  );
}
