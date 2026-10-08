import type { NumberDetail, NumberInfo } from '../types';

/** The third way in: one coloured design numbered by the textile tool. Its
 *  settings, in the tool's own words underneath (kam / normal / zyada = parts
 *  under 3 / 0.4 / 0.1 sq mm join a neighbour). */
export const NUMBER_DETAILS: { value: NumberDetail; label: string; hint: string }[] = [
  { value: 'kam', label: 'Less detail', hint: 'fewer, bigger areas: tiny bits join their neighbour' },
  { value: 'normal', label: 'Normal', hint: 'parts under 0.4 sq mm join their neighbour' },
  { value: 'zyada', label: 'More detail', hint: 'small dots and thin bits keep their own number' },
];

/** The mill's repeat size as typed ("23.5x20.7", "23.5 × 20.7"): [width, height]
 *  in inches, null when left empty, 'bad' when it cannot be read — checked here
 *  so a typo is caught before a run of a few minutes, and again by the engine. */
export function parseInches(text: string): [number, number] | null | 'bad' {
  const s = text.trim();
  if (!s) return null;
  const m = /^(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)$/.exec(s);
  if (!m) return 'bad';
  const w = Number(m[1]), h = Number(m[2]);
  return w >= 1 && w <= 120 && h >= 1 && h <= 120 ? [w, h] : 'bad';
}

/** Pixels at 300 DPI for a size in inches, as the engine makes it (inch x DPI). */
export const millPixels = (inches: number[], dpi = 300) => inches.map(v => Math.round(v * dpi));

/** The zip's download link, with the file name the engine gives it. */
export const zipHref = (n: NumberInfo) => `${n.zip_url}?name=${encodeURIComponent(n.zip_name)}`;

/** The footer line after a numbering run. */
export function numberMessage(n: NumberInfo, inks: number): string {
  return `Numbered: ${n.areas} areas, ${inks} inks, ${n.design_match}% like your picture. Download everything, or carry on to Separate.`;
}
