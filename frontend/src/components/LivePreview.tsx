import { useEffect, useRef, useState } from 'react';

type Props = {
  /** small copies of each screen (alpha = where it prints), in stacking order */
  masks: string[];
  /** each screen's ink; null = not printed (the cloth shows) */
  colors: (string | null)[];
  fabric: string;
  width: number;
  height: number;
  /** LoomLab's own separations never overlap: at most two inks meet at any
   *  pixel's edge, so the preview is one pass over the pixels. A bureau's
   *  overlapping screens are stacked with the canvas instead. */
  exclusive: boolean;
};

/** Per pixel: its main ink and the one it shares an anti-aliased edge with,
 *  and how much of each (0-255). Read once from the masks; after that a colour
 *  change is one pass over the pixels (the canvas route took ~100 ms a frame
 *  at 10 plates without a GPU). */
type Coverage = { a: Uint8Array; ia: Uint8Array; b: Uint8Array; ib: Uint8Array };

const rgb = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));

function readCoverage(images: HTMLImageElement[], w: number, h: number): Coverage {
  const n = w * h;
  const cov = { a: new Uint8Array(n), ia: new Uint8Array(n), b: new Uint8Array(n), ib: new Uint8Array(n) };
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true })!;
  images.forEach((im, k) => {
    ctx.clearRect(0, 0, w, h); ctx.drawImage(im, 0, 0, w, h);
    const d = ctx.getImageData(0, 0, w, h).data;
    for (let p = 0, q = 3; p < n; p++, q += 4) {
      const v = d[q];
      if (!v) continue;
      if (v > cov.a[p]) { cov.b[p] = cov.a[p]; cov.ib[p] = cov.ia[p]; cov.a[p] = v; cov.ia[p] = k; }
      else if (v > cov.b[p]) { cov.b[p] = v; cov.ib[p] = k; }
    }
  });
  return cov;
}

/** The print, recoloured in the browser the moment a colour changes. */
export function LivePreview({ masks, colors, fabric, width, height, exclusive }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const tint = useRef<HTMLCanvasElement>(document.createElement('canvas'));
  const [images, setImages] = useState<HTMLImageElement[]>();
  const cov = useRef<Coverage | undefined>(undefined);
  const frame = useRef<ImageData | undefined>(undefined);

  useEffect(() => {
    let live = true;
    setImages(undefined); cov.current = undefined; frame.current = undefined;
    Promise.all(masks.map(src => new Promise<HTMLImageElement>((ok, fail) => {
      const im = new Image(); im.onload = () => ok(im); im.onerror = fail; im.src = src;
    }))).then(ims => {
      if (!live) return;
      if (exclusive) cov.current = readCoverage(ims, width, height);
      setImages(ims);
    }).catch(() => {});
    return () => { live = false; };
  }, [masks.join('|'), exclusive, width, height]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!images || !canvas.current) return;
    const raf = requestAnimationFrame(() => {
      const c = canvas.current!, ctx = c.getContext('2d')!;
      const t0 = performance.now();
      if (exclusive && cov.current) {
        const { a, ia, b, ib } = cov.current;
        const fab = rgb(fabric);
        // an ink that isn't printed shows the cloth
        const lut = colors.map(col => (col ? rgb(col) : fab));
        const R = Uint8Array.from(lut, x => x[0]), G = Uint8Array.from(lut, x => x[1]), B = Uint8Array.from(lut, x => x[2]);
        if (!frame.current) frame.current = ctx.createImageData(width, height);
        const out = frame.current.data;
        for (let p = 0, q = 0, n = a.length; p < n; p++, q += 4) {
          const wa = a[p], wb = b[p];
          if (wa === 255) {
            const k = ia[p]; out[q] = R[k]; out[q + 1] = G[k]; out[q + 2] = B[k];
          } else {
            const wf = Math.max(0, 255 - wa - wb), ka = ia[p], kb = ib[p];
            out[q] = (wa * R[ka] + wb * R[kb] + wf * fab[0]) / 255;
            out[q + 1] = (wa * G[ka] + wb * G[kb] + wf * fab[1]) / 255;
            out[q + 2] = (wa * B[ka] + wb * B[kb] + wf * fab[2]) / 255;
          }
          out[q + 3] = 255;
        }
        ctx.putImageData(frame.current, 0, 0);
      } else {
        // overlapping screens: tint each and stack it, in order, over the cloth
        const t = tint.current;
        if (t.width !== width || t.height !== height) { t.width = width; t.height = height; }
        const tctx = t.getContext('2d')!;
        ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = fabric; ctx.fillRect(0, 0, width, height);
        images.forEach((im, i) => {
          const color = colors[i];
          if (!color) return;
          tctx.globalCompositeOperation = 'source-over';
          tctx.clearRect(0, 0, width, height);
          tctx.drawImage(im, 0, 0, width, height);
          tctx.globalCompositeOperation = 'source-in';
          tctx.fillStyle = color; tctx.fillRect(0, 0, width, height);
          ctx.drawImage(t, 0, 0);
        });
      }
      c.dataset.drawMs = (performance.now() - t0).toFixed(1);     // for tests and the curious
    });
    return () => cancelAnimationFrame(raf);
  }, [images, colors.join(','), fabric, width, height, exclusive]);   // eslint-disable-line react-hooks/exhaustive-deps

  return images
    ? <canvas ref={canvas} width={width} height={height} className="live-canvas" aria-label="Live colour preview" />
    : <div className="canvas empty">Loading the live preview…</div>;
}
