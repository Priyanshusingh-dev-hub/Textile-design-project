/** A short undo history for palette edits (recolour, merge).
 *
 *  Every edit produces a new reduced image on the engine, and the engine keeps
 *  the old ones for 48 hours, so undoing is just pointing back at the previous
 *  image and palette — nothing is recomputed. */
export type Entry<S> = { state: S; label: string };

/** Enough to walk back a whole palette session; older steps drop off. */
export const HISTORY_LIMIT = 25;

export function pushEntry<S>(history: Entry<S>[], state: S, label: string, limit = HISTORY_LIMIT): Entry<S>[] {
  const next = [...history, { state, label }];
  return next.length > limit ? next.slice(next.length - limit) : next;
}

/** [the state to restore, the history without it] — or null when empty. */
export function popEntry<S>(history: Entry<S>[]): [Entry<S>, Entry<S>[]] | null {
  if (!history.length) return null;
  return [history[history.length - 1], history.slice(0, -1)];
}
