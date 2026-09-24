import { describe, it, expect } from 'vitest';
import { pushEntry, popEntry, HISTORY_LIMIT } from './history';

describe('palette undo history', () => {
  it('undoes the most recent edit first', () => {
    let h = pushEntry([], 'A', 'recolour ink 2');
    h = pushEntry(h, 'B', 'merge inks 1 and 3');
    const [last, rest] = popEntry(h)!;
    expect(last).toEqual({ state: 'B', label: 'merge inks 1 and 3' });
    expect(popEntry(rest)![0].state).toBe('A');
  });

  it('has nothing to undo when empty', () => {
    expect(popEntry([])).toBeNull();
  });

  it('keeps only the most recent steps', () => {
    let h: ReturnType<typeof pushEntry<number>> = [];
    for (let i = 0; i < HISTORY_LIMIT + 5; i++) h = pushEntry(h, i, `edit ${i}`);
    expect(h).toHaveLength(HISTORY_LIMIT);
    expect(h[0].state).toBe(5);
    expect(h[h.length - 1].state).toBe(HISTORY_LIMIT + 4);
  });

  it('never changes the history it was given', () => {
    const h = pushEntry([], 1, 'a');
    pushEntry(h, 2, 'b');
    popEntry(h);
    expect(h).toHaveLength(1);
  });
});
