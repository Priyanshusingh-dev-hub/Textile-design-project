/** Screens laid over the cloth at their real coverage: the browser's copy of
 *  the backend proof (backend/app/separation_engine/ink_proof.py), so a live
 *  preview of a bureau's tinted screens shows the tints the films print.
 *
 *  A plain linear blend per screen, at coverage v = alpha / 255:
 *    proof = (1 - v) * below + v * ink
 *  rounded to the nearest 8-bit value after each screen, with the same integer
 *  rule PIL's composite uses on the backend, so the two give the same pixels.
 *  alpha 0 leaves the pixel alone and alpha 255 is the ink itself. */

const rgb = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));

/** One ink (0-255) at alpha `a` (0-255) over one colour channel `p` (0-255):
 *  round(((255 - a) * p + a * c) / 255), exactly as the backend does it. */
export function blend(p: number, c: number, a: number): number {
  const t = (255 - a) * p + a * c + 128;
  return ((t >> 8) + t) >> 8;
}

/** RGBA pixels (opaque) of `alphas` (one 0-255 coverage per pixel per screen,
 *  in stacking order) inked in `colors` (null = not printed) over `fabric`. */
export function inkProof(alphas: ArrayLike<number>[], colors: (string | null)[], fabric: string,
                         n: number, out = new Uint8ClampedArray(n * 4)): Uint8ClampedArray {
  const fab = rgb(fabric);
  for (let p = 0, q = 0; p < n; p++, q += 4) { out[q] = fab[0]; out[q + 1] = fab[1]; out[q + 2] = fab[2]; out[q + 3] = 255; }
  alphas.forEach((a, k) => {
    const col = colors[k];
    if (!col) return;
    const c = rgb(col);
    for (let p = 0, q = 0; p < n; p++, q += 4) {
      const av = a[p];
      if (!av) continue;
      if (av === 255) { out[q] = c[0]; out[q + 1] = c[1]; out[q + 2] = c[2]; continue; }
      out[q] = blend(out[q], c[0], av); out[q + 1] = blend(out[q + 1], c[1], av); out[q + 2] = blend(out[q + 2], c[2], av);
    }
  });
  return out;
}

/** The white of the under-base, as the backend proof draws it (UNDERBASE_WHITE). */
export const UNDERBASE_WHITE = '#FFFFFF';

/** The white under-base for a preview: on (255) wherever any printed screen
 *  has ink (alpha > 0), the rule of the backend's under-base film (before its
 *  1 px choke, which a preview-sized picture cannot show). */
export function underbaseAlpha(alphas: ArrayLike<number>[], colors: (string | null)[], n: number): Uint8Array {
  const ub = new Uint8Array(n);
  alphas.forEach((a, k) => {
    if (!colors[k]) return;
    for (let p = 0; p < n; p++) if (a[p]) ub[p] = 255;
  });
  return ub;
}

/** inkProof with a white under-base: where it is on, the inks sit on white,
 *  not on the cloth (R-0023), then the same blend. */
export function inkProofOnBase(alphas: ArrayLike<number>[], colors: (string | null)[], fabric: string,
                               n: number, underbase: boolean, out = new Uint8ClampedArray(n * 4)): Uint8ClampedArray {
  if (!underbase) return inkProof(alphas, colors, fabric, n, out);
  return inkProof([underbaseAlpha(alphas, colors, n), ...alphas], [UNDERBASE_WHITE, ...colors], fabric, n, out);
}
