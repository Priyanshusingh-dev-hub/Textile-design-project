/** The mill's ink library, on the frontend side: parsing a pasted list,
 *  deciding which palette colours to swap for shelf inks, and folding inks
 *  that land on the same shelf ink into one. Pure, so it is tested. */

export type LibraryInk = { name: string; hex: string };
export type InkMatch = { name: string; hex: string; delta_e: number } | null;

/** A shelf ink this close (CIEDE2000) can stand in for a palette colour on
 *  cloth; further than this and the design would visibly change, so the
 *  operator is told to mix a new ink instead of being swapped silently. */
export const LIBRARY_CLOSE = 5;

/** How a match reads next to a palette colour. */
export function matchLabel(m: InkMatch): { tone: 'same' | 'close' | 'far'; text: string } | null {
  if (!m) return null;
  if (m.delta_e <= 1) return { tone: 'same', text: `${m.name}` };
  if (m.delta_e <= LIBRARY_CLOSE) return { tone: 'close', text: `≈ ${m.name} · ΔE ${m.delta_e}` };
  return { tone: 'far', text: `nearest ${m.name} · ΔE ${m.delta_e} — mix a new ink` };
}

/** Lines like "Rani Pink 12, #D96A8E", "Rani Pink 12 #d96a8e" or
 *  "#D96A8E Rani Pink 12" (a paste from a spreadsheet or a phone note).
 *  Returns the inks read and the lines that couldn't be. */
export function parseInkList(text: string): { inks: LibraryInk[]; errors: string[] } {
  const inks: LibraryInk[] = []; const errors: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/#?([0-9a-fA-F]{6})\b/);
    const name = m ? line.replace(m[0], '').replace(/[,;:\t|]+/g, ' ').replace(/\s+/g, ' ').trim() : '';
    if (!m || !name || name.length > 60) { errors.push(line); continue; }
    inks.push({ name, hex: '#' + m[1].toUpperCase() });
  }
  return { inks, errors };
}

/** The palette entry other than `i` that already prints `hex`, or -1. */
export function inkOwner(palette: { hex: string }[], hex: string, i: number): number {
  return palette.findIndex((p, k) => k !== i && p.hex.toUpperCase() === hex.toUpperCase());
}

/** Which palette colours "use my inks" would swap, and to what: only the
 *  unlocked ones with a close enough shelf ink they aren't already. One shelf
 *  ink goes to one palette colour (the closest): two separate inks are never
 *  merged behind the operator's back, nor is one already in the palette. */
export function planSwap(palette: { hex: string; locked?: boolean }[], matches: InkMatch[]) {
  const targets: InkMatch[] = palette.map((p, i) => {
    const m = matches[i];
    if (p.locked || !m || m.delta_e > LIBRARY_CLOSE) return null;
    if (m.hex.toUpperCase() === p.hex.toUpperCase() || inkOwner(palette, m.hex, i) >= 0) return null;
    return m;
  });
  targets.forEach((t, i) => {
    if (t && targets.some((o, k) => k !== i && o && o.hex.toUpperCase() === t.hex.toUpperCase()
        && (o.delta_e < t.delta_e || (o.delta_e === t.delta_e && k < i)))) targets[i] = null;
  });
  return { targets, count: targets.filter(Boolean).length };
}

/** The palette after swapping: each swapped ink takes the shelf ink's colour
 *  and name; inks that land on the same colour become one ink (coverage and
 *  pixels added), kept at the position of the first. */
export function swapPalette<P extends { hex: string; coverage: number; pixels: number; name?: string }>(
  palette: P[], targets: InkMatch[]): P[] {
  const out: P[] = [];
  palette.forEach((p, i) => {
    const t = targets[i];
    const next = t ? { ...p, hex: t.hex.toUpperCase(), name: t.name } : p;
    const same = out.find(o => o.hex.toUpperCase() === next.hex.toUpperCase());
    if (same) {
      same.coverage = Math.round((same.coverage + next.coverage) * 100) / 100;
      same.pixels += next.pixels;
      if (!same.name && next.name) same.name = next.name;
    } else out.push({ ...next });
  });
  return out;
}
