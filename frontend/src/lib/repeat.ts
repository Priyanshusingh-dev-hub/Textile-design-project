/** Seeing a design as it runs on the cloth: 3 x 3 copies, laid straight or
 *  half-drop (every other column dropped by half a design), so a seam or an
 *  awkward rhythm shows before a screen is burnt. Only a view: the films are
 *  the design once. */
export type RepeatMode = 'off' | 'straight' | 'half';

export const NEXT_REPEAT: Record<RepeatMode, RepeatMode> = { off: 'straight', straight: 'half', half: 'off' };

export const REPEAT_LABEL: Record<RepeatMode, string> = {
  off: '⊞ See the repeat',
  straight: '⊞ Straight repeat',
  half: '⊞ Half-drop repeat',
};

/** Each copy's side in the view: the 3 x 3 stays within a screen image
 *  (SCREEN_SIDE), and copies are placed pixel for pixel — a scaled copy's edge
 *  would blend with nothing and draw a seam the print does not have. */
export const REPEAT_TILE = 800;

/** Where each copy of a w x h design goes in a 3w x 3h view. A dropped
 *  column starts half a design above the top, so it has four copies and the
 *  canvas clips the ends. */
export function repeatTiles(w: number, h: number, mode: Exclude<RepeatMode, 'off'>): [number, number][] {
  const out: [number, number][] = [];
  const drop = Math.round(h / 2);
  for (let c = 0; c < 3; c++) {
    const dropped = mode === 'half' && c === 1;
    for (let r = dropped ? -1 : 0; r < 3; r++) out.push([c * w, r * h + (dropped ? drop : 0)]);
  }
  return out;
}
