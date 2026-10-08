import { describe, expect, it } from 'vitest';
import { millPixels, numberMessage, parseInches, zipHref } from './numbering';
import type { NumberInfo } from '../types';

describe('the mill size as typed', () => {
  it('reads width x height in inches, however the x is written', () => {
    expect(parseInches('23.5x20.7')).toEqual([23.5, 20.7]);
    expect(parseInches(' 23.5 × 20.7 ')).toEqual([23.5, 20.7]);
    expect(parseInches('12X12')).toEqual([12, 12]);
  });
  it('empty is no mill file, anything else unreadable or out of range is caught before the run', () => {
    expect(parseInches('')).toBeNull();
    expect(parseInches('23.5')).toBe('bad');
    expect(parseInches('23.5x')).toBe('bad');
    expect(parseInches('200x10')).toBe('bad');
    expect(parseInches('0.5x10')).toBe('bad');
  });
  it('pixels are inch x DPI, as the engine makes them', () => {
    expect(millPixels([23.5, 20.7])).toEqual([7050, 6210]);
  });
});

describe('after a numbering run', () => {
  const n = { areas: 673, design_match: 88.4, zip_url: '/api/number/abc/zip', zip_name: 'rose & co_LoomLab_number.zip' } as NumberInfo;
  it('says what was made, with its numbers', () => {
    expect(numberMessage(n, 5)).toBe('Numbered: 673 areas, 5 inks, 88.4% like your picture. Download everything, or carry on to Separate.');
  });
  it('downloads under the name the engine gave, safely in the link', () => {
    expect(zipHref(n)).toBe('/api/number/abc/zip?name=rose%20%26%20co_LoomLab_number.zip');
  });
});
