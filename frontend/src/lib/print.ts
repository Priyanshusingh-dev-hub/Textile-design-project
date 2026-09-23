/** Pure prepress helpers, kept out of the component so they can be tested. */

export type Verdict = { tone: 'warn' | 'hint'; text: string };

/** Relative luminance (WCAG). Below 0.5 the cloth is "dark", which is what
 *  decides whether the inks need a white base under them. */
export function luminance(hex: string): number {
  const h = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export const isDarkCloth = (hex: string) => luminance(hex) < 0.5;

/**
 * Explain a weak match instead of showing a bare percentage.
 *
 * The ink-count sweep done at upload says whether MORE inks would help: if even
 * the top of that curve stays low the design is continuous-tone, and no ink
 * count will fix it — that is a different message from "you picked too few".
 */
export function matchVerdict(
  accuracy: number | undefined,
  curve: { colors: number; accuracy: number }[],
  suggested?: number,
  colorCount?: number,
): Verdict | null {
  if (accuracy === undefined) return null;
  if (accuracy >= 90) return null;                        // good enough — say nothing
  const ceiling = curve.length ? Math.max(...curve.map(c => c.accuracy)) : null;
  if (ceiling !== null && ceiling < 80) {
    return {
      tone: 'warn',
      text: `This design has smooth, photographic shading — flat spot colours can't reproduce it. `
        + `Even at 14 inks the match only reaches about ${Math.round(ceiling)}%. It will print as `
        + `visible bands of flat colour. Screen printing needs flat artwork, or halftones from a bureau.`,
    };
  }
  if (accuracy < 85) {
    const more = suggested && colorCount !== undefined && colorCount < suggested
      ? ` — try ${suggested} inks` : ' — more inks will tighten it';
    return { tone: 'hint', text: `${accuracy}% is a loose match${more}. Check the before/after above before you commit to screens.` };
  }
  return null;
}

/** An ink below this coverage costs a whole screen for almost nothing. */
export const TINY_COVERAGE = 0.5;
export const tinyInks = <T extends { coverage: number }>(inks: T[]) =>
  inks.filter(i => i.coverage < TINY_COVERAGE);

/** Ordinary anti-aliasing measures about 3px wide whatever the image size; a
 *  feathered or glowing edge starts around 12px. Six sits in the gap. */
export const SOFT_EDGE_PX = 6;

/** A flat ink cannot fade out, so a soft edge is printed as a hard one at the
 *  halfway point: the design comes out slightly smaller with a crisp rim. The
 *  accuracy score won't show it — it measures the pixels that do print — so
 *  the operator has to be told, or they find out at the press. */
export function softEdgeNote(softEdge: number | undefined): string | null {
  if (!softEdge || softEdge <= SOFT_EDGE_PX) return null;
  return `This design has soft, see-through edges (about ${Math.round(softEdge)}px of fade). `
    + `Flat inks can't fade, so those edges will print as a clean hard cut roughly halfway `
    + `through the fade — a glow or drop shadow will not survive. Flatten the design onto its `
    + `background first if you want to choose exactly where the edge lands.`;
}

/** Films are written at this resolution, so it also fixes how big the design
 *  prints: the artwork is never resampled, its pixels just land on the cloth
 *  at 300 to the inch. */
export const EXPORT_DPI = 300;

/** How large the design actually prints, which nothing else in the flow says.
 *  A mill needs this before burning screens — the artwork is not resampled, so
 *  a small file cannot be printed big without going soft. */
export function printSize(width?: number, height?: number, dpi = EXPORT_DPI) {
  if (!width || !height || dpi <= 0) return null;
  const inch = (px: number) => px / dpi;
  const round = (n: number) => Math.round(n * 10) / 10;
  return {
    inches: [round(inch(width)), round(inch(height))] as const,
    mm: [Math.round(inch(width) * 25.4), Math.round(inch(height) * 25.4)] as const,
    label: `${round(inch(width))} × ${round(inch(height))} in  ·  `
      + `${Math.round(inch(width) * 25.4)} × ${Math.round(inch(height) * 25.4)} mm`,
  };
}

/** The size is always shown, so this only has to catch the artwork that is
 *  genuinely unusable. A textile repeat is routinely printed at 4-6in, so
 *  warning there would be noise on ordinary work; under 3in even a repeat is
 *  a stretch and a placement print is out of the question. */
export const SMALL_PRINT_IN = 3;

export function printSizeNote(width?: number, height?: number, dpi = EXPORT_DPI): string | null {
  const size = printSize(width, height, dpi);
  if (!size) return null;
  const longest = Math.max(size.inches[0], size.inches[1]);
  if (longest >= SMALL_PRINT_IN) return null;
  return `At ${dpi} DPI this design prints ${size.label} — smaller than most textile work. `
    + `The artwork isn't resampled, so printing it bigger will soften every edge the `
    + `separation just kept crisp. Re-import it at a higher resolution if you need it larger.`;
}
