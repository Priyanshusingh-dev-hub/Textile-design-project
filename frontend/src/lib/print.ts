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
