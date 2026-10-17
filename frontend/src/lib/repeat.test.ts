import { describe, expect, it } from 'vitest';
import { NEXT_REPEAT, repeatTiles } from './repeat';

describe('repeat view', () => {
  it('lays a straight repeat as a 3 x 3 grid', () => {
    const t = repeatTiles(100, 60, 'straight');
    expect(t).toHaveLength(9);
    expect(t).toContainEqual([0, 0]);
    expect(t).toContainEqual([200, 120]);
  });

  it('drops the middle column by half a design and fills its ends', () => {
    const t = repeatTiles(100, 60, 'half');
    const mid = t.filter(([x]) => x === 100).map(([, y]) => y);
    expect(mid).toEqual([-30, 30, 90, 150]);          // covers 0..180 with no gap
    expect(t.filter(([x]) => x === 0).map(([, y]) => y)).toEqual([0, 60, 120]);
  });

  it('cycles off -> straight -> half-drop -> off', () => {
    expect(NEXT_REPEAT.off).toBe('straight');
    expect(NEXT_REPEAT.straight).toBe('half');
    expect(NEXT_REPEAT.half).toBe('off');
  });
});
