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

/** The numbering card's checks failed: the plates did not stack back, or the mill-size check failed.
 *  Never send these files. */
export const numberFailed = (n: NumberInfo) => !n.verify || n.mill?.passed === false;
/** Any warning line on the numbering card (NumberCard): a failed check, a repeat cut to shape,
 *  numbers with no room. The mascot never cheers beside one; keep this in step with the card. */
export const numberCautions = (n: NumberInfo) => numberFailed(n) || !!n.mill?.cropped || n.missed > 0
  || !!n.mill?.left?.length || !!n.mill?.shared?.length || !!n.mill?.missing?.length;

/** The palette was edited after this zip was made (recolour, merge, my inks, undo): the zip still has
 *  the colours it was made with. A job saved before zips could be rebuilt has no `built_from`: never stale. */
export const zipStale = (n: NumberInfo, reducedId: string | undefined) =>
  !!reducedId && !!n.built_from && n.built_from !== reducedId;

/** The mill's names for the inks on screen ("Use my inks", a shelf ink picked, or one already within
 *  ΔE 1 of a shelf ink: `inkName`), by upper-case '#RRGGBB': what the films are called in Separate/Export. */
export function inkNames(palette: { hex: string }[], name: (i: number) => string | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  const used = new Set<string>();
  palette.forEach((p, i) => {          // the engine's rule: a name goes to its first ink only, never to two screens
    const n = name(i)?.trim(), hex = p.hex.toUpperCase();
    if (n && !(hex in out) && !used.has(n.toLowerCase())) { out[hex] = n; used.add(n.toLowerCase()); }
  });
  return out;
}

/** The zip's colours are right but its ink names are not the ones on screen (a shelf name came or went). */
export function namesStale(n: NumberInfo, names: Record<string, string>): boolean {
  const had = n.names ?? {};
  const keys = new Set([...Object.keys(had), ...Object.keys(names)]);
  return [...keys].some(k => had[k] !== names[k]);
}

/** The footer line after ↻: `changes` against the first run, `switched` = the zip on the card is another one. */
export function rebuildMessage(changes: number, inks: number, renamed = false, switched = true): string {
  if (!switched) return 'The zip already has these colours.';
  return changes
    ? `Your palette changes are in the zip now (colours changed: ${changes}, inks: ${inks}). Download it again.`
    : renamed ? 'Your ink names are in the zip now. Download it again.'
    : 'Back to the first colours: the first zip is on the card again. Download it again.';
}

/** The footer line after a numbering run. */
export function numberMessage(n: NumberInfo, inks: number): string {
  return `Numbered: ${n.areas} areas, ${inks} inks, ${n.design_match}% like your picture. Download everything, or carry on to Separate.`;
}
