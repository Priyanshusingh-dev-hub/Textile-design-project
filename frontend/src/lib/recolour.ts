/** Recolouring plates after separation. The screens are geometry; an ink's
 *  colour is only a label on one, so changing it never touches a film — it
 *  changes the plates, the proof, the job sheet and the ink's name. Pure, so
 *  it is tested. */

/** "#d96a8e", "D96A8E", "#d6e" -> "#D96A8E"; anything else -> null. */
export function parseHex(text: string): string | null {
  const t = text.trim().replace(/^#/, '');
  if (/^[0-9a-fA-F]{6}$/.test(t)) return '#' + t.toUpperCase();
  if (/^[0-9a-fA-F]{3}$/.test(t)) return '#' + t.split('').map(c => c + c).join('').toUpperCase();
  return null;
}

type Ink = { id: string; color: string; name: string };
export type ColourSnapshot = Record<string, { color: string; name: string }>;

/** The colours and names as they were when recolouring began. */
export function snapshotColours(layers: Ink[]): ColourSnapshot {
  return Object.fromEntries(layers.map(l => [l.id, { color: l.color.toUpperCase(), name: l.name }]));
}

/** How many plates now differ from the snapshot. */
export function changedCount(layers: Ink[], snap: ColourSnapshot): number {
  return layers.filter(l => snap[l.id] && snap[l.id].color !== l.color.toUpperCase()).length;
}

/** One click colours for plate `id`: the other plates' inks and the mill's
 *  shelf inks, each once, never the colour it already has. */
export function quickPicks(layers: Ink[], id: string, library: { name: string; hex: string }[] = []):
  { hex: string; name?: string; from: 'plate' | 'shelf' }[] {
  const own = layers.find(l => l.id === id)?.color.toUpperCase();
  const seen = new Set<string>(own ? [own] : []);
  const out: { hex: string; name?: string; from: 'plate' | 'shelf' }[] = [];
  for (const l of layers) {
    const hex = l.color.toUpperCase();
    if (!seen.has(hex)) { seen.add(hex); out.push({ hex, from: 'plate' }); }
  }
  for (const ink of library) {
    const hex = ink.hex.toUpperCase();
    if (!seen.has(hex)) { seen.add(hex); out.push({ hex, name: ink.name, from: 'shelf' }); }
  }
  return out;
}

/** The plate's name after a colour change: a shelf ink's name when one was
 *  picked; otherwise a name that belonged to the OLD colour (a shelf ink it no
 *  longer is) falls back to the plate's number, and any other name is kept. */
export function renamed(current: string, index: number, pickedName: string | undefined,
  library: { name: string }[] = []): string {
  if (pickedName) return pickedName;
  return library.some(i => i.name === current) ? `Ink ${index + 1}` : current;
}
