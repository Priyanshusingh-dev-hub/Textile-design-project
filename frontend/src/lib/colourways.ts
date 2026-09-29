// Colourways: the same screens printed in other inks. A mill sells one design
// in several colour sets and burns its screens once; each colourway is only a
// colour (and name) for every screen, plus the cloth.

export type ColourwayInk = { color: string; name: string };
export type Colourway = { name: string; fabric: string; inks: Record<string, ColourwayInk> };
type Plate = { id: string; color: string; name: string; skip?: boolean };

const LETTERS = 'ABCDEFGH';
export const MAX_COLOURWAYS = 8;

/** The next free name: A, B, C… */
export function nextName(ways: Colourway[]): string {
  const taken = new Set(ways.map(w => w.name.trim().toUpperCase()));
  return [...LETTERS].find(l => !taken.has(l)) ?? `${ways.length + 1}`;
}

/** The plates' colours as they are now, every plate (a hidden one may be shown again later). */
export function snapshot(name: string, plates: Plate[], fabric: string): Colourway {
  return { name: name.trim(), fabric: fabric.toUpperCase(),
    inks: Object.fromEntries(plates.map(p => [p.id, { color: p.color.toUpperCase(), name: p.name }])) };
}

/** Why a colourway can't be saved under `name`, or '' if it can. */
export function nameProblem(name: string, ways: Colourway[]): string {
  const n = name.trim();
  if (!n) return 'Give the colourway a name.';
  if (n.length > 40) return 'Keep the name under 40 letters.';
  const safe = (s: string) => s.replace(/[^\p{L}\p{N} _-]/gu, '-').trim().toLowerCase();
  if (ways.some(w => safe(w.name) === safe(n))) return `There is already a colourway called ${n}.`;
  if (ways.length >= MAX_COLOURWAYS) return `Up to ${MAX_COLOURWAYS} colourways.`;
  return '';
}

/** The package request's colourways, for the screens that print. */
export function toRequest(ways: Colourway[], printing: Plate[]) {
  return ways.map(w => ({
    name: w.name, fabric: w.fabric,
    inks: printing.map(p => {
      const ink = w.inks[p.id] ?? { color: p.color, name: p.name };
      return { id: p.id, color: ink.color, name: ink.name };
    }),
  }));
}

/** Plates wearing a colourway's inks (to look at it, or print it as the main set). */
export function apply(w: Colourway, plates: Plate[]) {
  return plates.map(p => (w.inks[p.id] ? { ...p, color: w.inks[p.id].color, name: w.inks[p.id].name || p.name } : p));
}
