import { describe, expect, it } from 'vitest';
import { areaAt, areaList, idsFromRgba, paintPicked, toggleArea } from './areas';

describe('areas picture', () => {
  it('reads area numbers from red x 256 + green', () => {
    const data = [0, 5, 0, 255, 1, 2, 0, 255, 0, 0, 0, 255];
    expect([...idsFromRgba(data, 3)]).toEqual([5, 258, 0]);
  });
  it('finds the area under a click, 0 on a line or off the picture', () => {
    const ids = new Uint16Array([1, 2, 3, 4]);              // 2 x 2
    expect(areaAt(ids, 2, 2, 0.1, 0.1)).toBe(1);
    expect(areaAt(ids, 2, 2, 0.9, 0.1)).toBe(2);
    expect(areaAt(ids, 2, 2, 0.1, 0.9)).toBe(3);
    expect(areaAt(ids, 2, 2, 0.99, 0.99)).toBe(4);
    for (const [x, y] of [[-0.1, 0.5], [1, 0.5], [0.5, 1], [NaN, 0.2]]) expect(areaAt(ids, 2, 2, x, y)).toBe(0);
  });
  it('toggles a pick in and out, ascending', () => {
    expect(toggleArea([], 5)).toEqual([5]);
    expect(toggleArea([5, 9], 7)).toEqual([5, 7, 9]);
    expect(toggleArea([5, 7, 9], 7)).toEqual([5, 9]);
  });
  it('writes the list the way the field is typed', () => {
    expect(areaList([101, 104, 110, 111, 112, 113])).toBe('101, 104, 110-113');
    expect(areaList([1, 2])).toBe('1, 2');
    expect(areaList([])).toBe('');
  });
  it('paints only the picked areas', () => {
    const out = new Uint8ClampedArray(12);
    paintPicked(new Uint16Array([1, 2, 0]), new Set([2]), out, [255, 0, 170, 120]);
    expect([...out]).toEqual([0, 0, 0, 0, 255, 0, 170, 120, 0, 0, 0, 0]);
  });
});
