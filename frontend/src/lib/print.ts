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

/** The largest print the engine renders (it answers 422 above this; keep in
 *  step with MAX_PRINT_PX in backend/app/main.py). */
export const MAX_PRINT_PX = 70_000_000;

/** A design this small at its own size is below most textile work — the note
 *  points at the print-width box instead of staying silent. */
export const SMALL_PRINT_IN = 3;

/** The print a chosen width gives, in the design's proportions. `widthIn`
 *  unset (or its own width) means the design's own size, output untouched. */
export function printAt(width?: number, height?: number, widthIn?: number, dpi = EXPORT_DPI) {
  if (!width || !height || dpi <= 0) return null;
  const px = widthIn && widthIn > 0 ? Math.max(1, Math.round(widthIn * dpi)) : width;
  const pxH = Math.max(1, Math.round(height * px / width));
  const inch = (n: number) => Math.round(n / dpi * 100) / 100;
  const mm = (n: number) => Math.round(n / dpi * 25.4);
  const scale = px / width;
  return {
    px: [px, pxH] as const,
    inches: [inch(px), inch(pxH)] as const,
    scale,
    resized: px !== width || pxH !== height,
    tooLarge: px * pxH > MAX_PRINT_PX,
    /** the widest this design can print before the engine refuses */
    maxIn: Math.floor(Math.sqrt(MAX_PRINT_PX * width / height) / dpi * 10) / 10,
    /** real pixels of the file behind each printed inch */
    sourcePpi: Math.round(width / (px / dpi)),
    label: `${inch(px)} × ${inch(pxH)} in  ·  ${mm(px)} × ${mm(pxH)} mm`,
  };
}

/** What changing the print width does — said plainly, including what it
 *  cannot do. Enlarging redraws edges smoothly; it cannot invent detail. */
export function printWidthNote(width?: number, height?: number, widthIn?: number, dpi = EXPORT_DPI):
  { tone: 'hint' | 'warn'; text: string } | null {
  const at = printAt(width, height, widthIn, dpi);
  if (!at) return null;
  if (at.tooLarge) {
    return { tone: 'warn', text: `That is too large to render here — this design can go up to ${at.maxIn} in wide. `
      + 'For anything bigger, use the vector SVG, which scales to any size.' };
  }
  if (!at.resized) {
    if (Math.max(...at.inches) >= SMALL_PRINT_IN) return null;
    return { tone: 'warn', text: `At its own size this design prints only ${at.label}. Set a larger print width `
      + 'above: the screens are redrawn at that size with smooth edges.' };
  }
  if (at.scale > 1) {
    const coarse = at.sourcePpi < 75
      ? ` That is only ${at.sourcePpi} pixels of the file per inch, so fine texture will look coarse up close.` : '';
    return { tone: coarse ? 'warn' : 'hint', text: `Enlarged ${at.scale.toFixed(1)}×: every screen is redrawn at this `
      + 'size with smooth edges, still one ink per pixel. Detail finer than the file itself — fine texture, '
      + `tiny dots — can't be added, so it stays as it is in the file.${coarse}` };
  }
  return { tone: 'hint', text: `Reduced to ${Math.round(at.scale * 100)}%: lines thinner than `
    + `${Math.max(1, Math.round(1 / at.scale))} px in the file may break up at this size.` };
}

/** What the Separate panel may truthfully say about how the screens relate.
 *  A reduced design is split one ink per pixel by construction. A
 *  pre-separated PSD is the bureau's own work, left as it came — and bureaus
 *  often overlap screens on purpose (trapping, so no gap shows if a screen
 *  shifts), in which case "one ink per pixel" would be false. */
export function separationNote(fromPsd: boolean, overlap?: number): string {
  if (!fromPsd) {
    return 'Every pixel prints on exactly one plate — no overlap, no gaps. The preview above '
      + 'is these screens stacked back together, so it is your final print.';
  }
  const kept = 'These screens come from your PSD exactly as it was separated — LoomLab has not changed them.';
  if (!overlap) return `${kept} No two screens print on the same spot.`;
  return `${kept} ${overlap < 0.1 ? 'Under 0.1' : overlap.toFixed(1)}% of the design is printed by more than `
    + 'one screen (trapping or overprint), kept as in your file. Where screens overlap, the preview '
    + 'shows the later one on top.';
}

/** CIE76 colour difference between two #RRGGBB colours, in LAB. Coarse next
 *  to CIEDE2000, but ample for "is this ink the cloth's colour?". */
export function colourDistance(a: string, b: string): number {
  const lab = (hex: string) => {
    const lin = [1, 3, 5].map(i => {
      const c = parseInt(hex.replace('#', '').padEnd(7, '0').slice(i - 1, i + 1), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    const xyz = [
      (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047,
      (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]),
      (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883,
    ].map(t => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116));
    return [116 * xyz[1] - 16, 500 * (xyz[0] - xyz[1]), 200 * (xyz[1] - xyz[2])];
  };
  const [p, q] = [lab(a), lab(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}

/** The ground: the ink the motifs sit on. It owns most of the design's outer
 *  edge (a motif on a transparent ground owns none) and a real share of it. */
export const GROUND_EDGE = 40;
export const GROUND_COVERAGE = 20;
/** Below this CIE76 distance an ink reads as the cloth's own colour. */
export const SAME_AS_CLOTH = 6;

/** Whether to suggest leaving the ground unprinted. A mill usually prints on
 *  cloth already dyed the ground colour and skips that screen — the largest
 *  one, and the most ink. `matches` = the cloth chosen already is that colour,
 *  so the ink only needs hiding. Null once it is hidden, or with no ground. */
export function groundSuggestion<T extends { color: string; coverage: number; edge?: number; skip?: boolean }>(
  layers: T[], fabric: string): { ink: T; matches: boolean } | null {
  const ground = layers
    .filter(l => (l.edge ?? 0) >= GROUND_EDGE && l.coverage >= GROUND_COVERAGE)
    .sort((a, b) => (b.edge ?? 0) - (a.edge ?? 0))[0];
  if (!ground || ground.skip) return null;
  return { ink: ground, matches: colourDistance(ground.color, fabric) < SAME_AS_CLOTH };
}

/** A pair of inks the engine found nearly identical (CIEDE2000), with the
 *  measured match if `drop` were merged into `keep`. Indices are palette order. */
export type SimilarPair = { keep: number; drop: number; delta_e: number; accuracy: number };

/** The merge worth offering: the closest pair the operator hasn't locked.
 *  A locked ink is one they chose on purpose, so it is never merged away. */
export function mergeSuggestion(pairs: SimilarPair[] | undefined, palette: { locked?: boolean }[]):
  SimilarPair | null {
  return (pairs ?? []).find(p => palette[p.keep] && palette[p.drop]
    && !palette[p.keep].locked && !palette[p.drop].locked) ?? null;
}

/** A seamless repeat is processed wrapped round (so its edges stay seamless
 *  when the tile is printed edge to edge). Say so, so the operator knows the
 *  seams were looked after — and which way the design repeats. */
export function repeatNote(repeat?: { x: boolean; y: boolean }): string | null {
  if (!repeat || (!repeat.x && !repeat.y)) return null;
  const way = repeat.x && repeat.y ? 'both ways' : repeat.x ? 'left to right' : 'top to bottom';
  return `Seamless repeat (${way}): the edges were processed as they meet when the tile repeats, `
    + 'so the reduced design stays seamless — no line at the join.';
}
