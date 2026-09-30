/** Pure prepress helpers, kept out of the component so they can be tested. */
import { english, type Tr } from './i18n';

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
  const most = curve.length ? Math.max(...curve.map(c => c.colors)) : 14;
  if (ceiling !== null && ceiling < 80) {
    return {
      tone: 'warn',
      text: `This design has smooth, photographic shading — flat spot colours can't reproduce it. `
        + `Even at ${most} inks the match only reaches about ${Math.round(ceiling)}%. It will print as `
        + `visible bands of flat colour. Tick Print as dots above, or get halftones from a bureau.`,
    };
  }
  if (accuracy < 85) {
    // at or past the suggestion, and the most inks tried barely do better
    // (under a point per extra screen): "more inks will tighten it" would
    // send the operator after screens that don't help
    const extra = colorCount !== undefined ? Math.max(0, most - colorCount) : 0;
    if (ceiling !== null && ceiling - accuracy < Math.max(4, extra) && !(suggested && colorCount !== undefined && colorCount < suggested)) {
      return { tone: 'hint', text: `${accuracy}% is about as close as flat inks get for this design — even ${most} inks `
        + `reach only ${Math.round(ceiling)}%. Its fine shading prints as flat areas; check the before/after above.` };
    }
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
export function softEdgeNote(softEdge: number | undefined, tr: Tr = english): string | null {
  if (!softEdge || softEdge <= SOFT_EDGE_PX) return null;
  return tr("This design has soft, see-through edges (about {n}px of fade). Flat inks can't fade, so those "
    + 'edges will print as a clean hard cut roughly halfway through the fade — a glow or drop shadow will not '
    + 'survive. Flatten the design onto its background first if you want to choose exactly where the edge lands.',
  { n: Math.round(softEdge) });
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
export function printWidthNote(width?: number, height?: number, widthIn?: number, dpi = EXPORT_DPI, tr: Tr = english):
  { tone: 'hint' | 'warn'; text: string } | null {
  const at = printAt(width, height, widthIn, dpi);
  if (!at) return null;
  if (at.tooLarge) {
    return { tone: 'warn', text: tr('That is too large to render here — this design can go up to {n} in wide. '
      + 'For anything bigger, use the vector SVG, which scales to any size.', { n: at.maxIn }) };
  }
  if (!at.resized) {
    if (Math.max(...at.inches) >= SMALL_PRINT_IN) return null;
    return { tone: 'warn', text: tr('At its own size this design prints only {size}. Set a larger print width '
      + 'above: the screens are redrawn at that size with smooth edges.', { size: at.label }) };
  }
  if (at.scale > 1) {
    const coarse = at.sourcePpi < 75
      ? ' ' + tr('That is only {n} pixels of the file per inch, so fine texture will look coarse up close.', { n: at.sourcePpi }) : '';
    return { tone: coarse ? 'warn' : 'hint', text: tr('Enlarged {x}×: every screen is redrawn at this '
      + 'size with smooth edges, still one ink per pixel. Detail finer than the file itself — fine texture, '
      + "tiny dots — can't be added, so it stays as it is in the file.{more}", { x: at.scale.toFixed(1), more: coarse }) };
  }
  return { tone: 'hint', text: tr('Reduced to {p}%: lines thinner than {n} px in the file may break up at this size.',
    { p: Math.round(at.scale * 100), n: Math.max(1, Math.round(1 / at.scale)) }) };
}

/** What the Separate panel may truthfully say about how the screens relate.
 *  A reduced design is split one ink per pixel by construction. A
 *  pre-separated PSD is the bureau's own work, left as it came — and bureaus
 *  often overlap screens on purpose (trapping, so no gap shows if a screen
 *  shifts), in which case "one ink per pixel" would be false. */
export function separationNote(fromPsd: boolean, overlap?: number, tr: Tr = english): string {
  if (!fromPsd) {
    return tr('Every pixel prints on exactly one plate — no overlap, no gaps. The preview above '
      + 'is these screens stacked back together, so it is your final print.');
  }
  const kept = tr('These screens come from your PSD exactly as it was separated — LoomLab has not changed them.');
  if (!overlap) return `${kept} ${tr('No two screens print on the same spot.')}`;
  return `${kept} ${tr('{p}% of the design is printed by more than one screen (trapping or overprint), kept as in '
    + 'your file. Where screens overlap, the preview shows the later one on top.',
  { p: overlap < 0.1 ? tr('Under 0.1') : overlap.toFixed(1) })}`;
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
export function repeatNote(repeat?: { x: boolean; y: boolean }, tr: Tr = english): string | null {
  if (!repeat || (!repeat.x && !repeat.y)) return null;
  const way = tr(repeat.x && repeat.y ? 'both ways' : repeat.x ? 'left to right' : 'top to bottom');
  return tr('Seamless repeat ({way}): the edges were processed as they meet when the tile repeats, '
    + 'so the reduced design stays seamless — no line at the join.', { way });
}

/** Trap widths offered at export, in film pixels. 0 = off: the films are the
 *  separation itself, one ink per pixel. */
export const TRAP_CHOICES = [0, 1, 2, 3] as const;

/** "2 px · 0.17 mm": how wide a trap is on the film at `dpi`. */
export function trapLabel(px: number, dpi: number, tr: Tr = english): string {
  if (!px) return tr('Off');
  return `${px} px · ${(px / dpi * 25.4).toFixed(2)} mm`;
}

/** Tiny-dot cleaning at export, in mm across at the print size. 0 = off. */
export const DOT_CHOICES = [0, 0.15, 0.2, 0.3] as const;
/** The size a report is made at while cleaning is off, to show what's there. */
export const DOT_REPORT_MM = 0.2;

export function dotLabel(mm: number, tr: Tr = english): string {
  return mm ? tr('under {mm} mm', { mm }) : tr('Off');
}

export type SpeckReport = { min_dot_mm: number; inks: { id: string; dots: number }[] };

/** What the operator is told about dots a screen can't hold. */
export function dotNote(report: SpeckReport | undefined, cleaning: boolean, tr: Tr = english):
  { tone: 'muted' | 'hint'; text: string } | null {
  if (!report) return null;
  const withDots = report.inks.filter(i => i.dots > 0);
  const total = withDots.reduce((s, i) => s + i.dots, 0);
  if (!total) return null;
  const vars = { n: total.toLocaleString('en-IN'), mm: report.min_dot_mm, s: withDots.length };
  // one key per wording, so each reads right in either language
  const what = total === 1 ? '1 dot under {mm} mm on 1 screen' : withDots.length === 1
    ? '{n} dots under {mm} mm on 1 screen' : '{n} dots under {mm} mm on {s} screens';
  return cleaning
    ? { tone: 'muted', text: tr(total === 1 ? `${what} goes to the ink around it — the proof shows the result.`
      : `${what} go to the ink around them — the proof shows the result.`, vars) }
    : { tone: 'hint', text: tr(total === 1 ? `${what}: too small for the mesh to hold, it prints as nothing or as dirt. Clean it here.`
      : `${what}: too small for the mesh to hold, they print as nothing or as dirt. Clean them here.`, vars) };
}

/** Coverage (%) under which an ink counts as "small" — each still costs a screen. */
export const SMALL_CHOICES = [1, 2, 3] as const;
export type SmallInk = { index: number; hex: string; coverage: number; shift: number; distinct: boolean };
export type SmallInkReport = { inks: SmallInk[]; drop: number[]; accuracy: number | null; below: number };

/** What the Reduce step says about small inks, and the button's label. */
export function smallInkNote(r: SmallInkReport | undefined, accuracy: number | undefined, inks: number, tr: Tr = english):
  { text: string; action: string | null } | null {
  if (!r || !r.inks.length) return null;
  const kept = r.inks.filter(i => i.distinct);
  const list = kept.map(i => tr('ink {n} ({c}%)', { n: i.index + 1, c: i.coverage })).join(', ');
  const keptText = !kept.length ? '' : tr(kept.length > 1
    ? 'Kept: {list} — unlike any other ink, they would visibly change.'
    : 'Kept: {list} — unlike any other ink, it would visibly change.', { list });
  const n = r.drop.length;
  if (!n) return { text: keptText, action: null };
  const score = accuracy !== undefined && r.accuracy !== null ? ' ' + tr('(match {a}% → {b}%)', { a: accuracy, b: r.accuracy }) : '';
  const vars = { n, b: r.below, k: inks - n, score };
  return {
    text: tr(n > 1
      ? '{n} inks cover under {b}% each. Removing them leaves {k} inks{score}: each pixel moves to the closest remaining ink.'
      : '1 ink covers under {b}%. Removing it leaves {k} inks{score}: each pixel moves to the closest remaining ink.', vars)
      + (keptText ? ' ' + keptText : ''),
    action: tr(n > 1 ? 'Remove {n} small inks' : 'Remove 1 small ink', { n }),
  };
}

/** Why texture cleanup is set as it is. The engine picks the level from the
 *  source's grain; an override either way has a cost worth saying. */
export function cleanupNote(auto: number | undefined, current: number, grain?: number): { tone: 'hint' | 'warn'; text: string } | null {
  if (auto === undefined) return null;
  if (current === auto) {
    return auto === 0
      ? { tone: 'hint', text: 'Chosen for this design: off. It has no grain, so every outline, dot and vein is kept.' }
      : { tone: 'hint', text: `Chosen for this design: the source is grainy${grain !== undefined ? ` (${grain})` : ''}, and cleanup keeps the plates from speckling.` };
  }
  return current > auto
    ? { tone: 'warn', text: 'More cleanup than this design needs: it erases thin outlines, dots and veins.' }
    : { tone: 'warn', text: 'This source is grainy: with less cleanup the plates will speckle.' };
}

/** Money the way the quote image writes it: Indian grouping, 1,23,456. */
export function money(value: number, currency = '₹'): string {
  const n = Math.round(value);
  return (n < 0 ? '-' : '') + currency + Math.abs(n).toLocaleString('en-IN');
}

export type Enlarged = { image_id: string; width: number; height: number; match: number; ok: boolean;
  min_match: number; method: string; note: string; source_ppi: number; width_in: number; height_in: number };

/** What an enlargement came out as, and whether to trust it. */
export function enlargeNote(e: Enlarged, tr: Tr = english): { tone: 'hint' | 'warn'; text: string } {
  const vars = { size: `${e.width} × ${e.height} px (${e.width_in} × ${e.height_in} in)`,
    how: e.method === 'realesrgan' ? 'Real-ESRGAN' : 'Lanczos', m: e.match, p: e.source_ppi };
  const note = e.note ? ' ' + tr(e.note) : '';
  if (!e.ok) {
    return { tone: 'warn', text: tr('{size} by {how}, but only a {m}% match with the original: the '
      + 'enlargement changed the design. Check it closely, or use Lanczos.', vars) + note };
  }
  return { tone: 'hint', text: tr(e.source_ppi < 100
    ? "{size} by {how} · {m}% match with the original · from only {p} px per inch: edges are smooth, but fine detail can't be added."
    : '{size} by {how} · {m}% match with the original.', vars) + note };
}

/** Dots (index separation) a mesh holds and an eye mixes: finer than this is
 *  lost on most textile mesh, coarser than that shows as a dot pattern. */
export const DOT_FINE_MM = 0.12;
export const DOT_COARSE_MM = 0.45;

/** How big each dot of an index separation prints, and whether that works:
 *  each pixel of the design becomes one square dot at the print size. */
export function dotSizeNote(width?: number, height?: number, widthIn?: number, dpi = EXPORT_DPI, tr: Tr = english):
  { tone: 'hint' | 'warn'; text: string; mm: number } | null {
  const at = printAt(width, height, widthIn, dpi);
  if (!at) return null;
  // each design pixel prints as a square of a whole number of film pixels (engine: dot_pixels)
  const mm = Math.round(Math.max(1, Math.round(at.scale)) / dpi * 25.4 * 100) / 100;
  if (mm < DOT_FINE_MM) {
    return { tone: 'warn', mm, text: tr('Printed as dots, each {mm} mm: finer than most textile mesh holds. Print it wider, or use a very fine mesh.', { mm }) };
  }
  if (mm > DOT_COARSE_MM) {
    return { tone: 'warn', mm, text: tr('Printed as dots, each {mm} mm: the dot pattern will show. A larger file (Extras → High-resolution design file) gives finer dots.', { mm }) };
  }
  return { tone: 'hint', mm, text: tr('Printed as dots, each {mm} mm square: they mix into the shading seen from a step away. Use a fine mesh; no trap or tiny-dot cleaning (the dots are the design).', { mm }) };
}
