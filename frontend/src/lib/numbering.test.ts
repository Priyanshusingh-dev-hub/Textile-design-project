import { describe, expect, it } from 'vitest';
import { inkNames, millPixels, namesStale, numberMessage, parseInches, parseAreaNumbers, parseMinArea, areasMessage, rebuildMessage, zipHref, zipStale } from './numbering';
import { translate } from './i18n';
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

describe('palette edits after numbering', () => {
  const n = { built_from: 'a'.repeat(32) } as NumberInfo;
  it('the zip is stale once the design on screen is not the one it was made from', () => {
    expect(zipStale(n, 'a'.repeat(32))).toBe(false);
    expect(zipStale(n, 'b'.repeat(32))).toBe(true);
    expect(zipStale(n, undefined)).toBe(false);
    expect(zipStale({} as NumberInfo, 'b'.repeat(32))).toBe(false);      // a job saved before rebuilds: no claim
  });
  it('says what went into the zip, in Hinglish too', () => {
    const m = rebuildMessage(2, 5);
    expect(m).toBe('Your palette changes are in the zip now (colours changed: 2, inks: 5). Download it again.');
    expect(translate('hi', m)).toBe('Rang ke badlav ab zip me hain (badle rang: 2, inks: 5). Zip dobara download karo.');
    expect(translate('hi', rebuildMessage(0, 5, false, false))).toBe('Zip me pehle se yahi rang hain.');
    // every edit undone: the card is back on the first zip, which IS a different zip from the one held
    expect(rebuildMessage(0, 5)).toBe('Back to the first colours: the first zip is on the card again. Download it again.');
    expect(translate('hi', rebuildMessage(0, 5))).toBe('Pehle wale rang wapas: card par phir pehla zip hai. Dobara download karo.');
  });
});

describe('the mill’s ink names in the zip', () => {
  const palette = [{ hex: '#d96a8e' }, { hex: '#1F2A60' }, { hex: '#F0DEB4' }];
  const names = inkNames(palette, i => [' Rani Pink 12 ', undefined, ''][i]);
  it('are the names on screen, by upper-case #hex, blanks left out', () => {
    expect(names).toEqual({ '#D96A8E': 'Rani Pink 12' });
  });
  it('one name names its first ink only (as the engine does), so it never stays stale', () => {
    const twice = inkNames([{ hex: '#111111' }, { hex: '#222222' }], () => 'Ivory');
    expect(twice).toEqual({ '#111111': 'Ivory' });
    expect(inkNames([{ hex: '#111111' }, { hex: '#222222' }], i => ['Ivory', 'ivory '][i])).toEqual({ '#111111': 'Ivory' });
    expect(namesStale({ names: { '#111111': 'Ivory' } } as unknown as NumberInfo, twice)).toBe(false);
  });
  it('are stale when a name came or went, not when they agree', () => {
    expect(namesStale({} as NumberInfo, names)).toBe(true);
    expect(namesStale({ names: { '#D96A8E': 'Rani Pink 12' } } as unknown as NumberInfo, names)).toBe(false);
    expect(namesStale({ names: { '#D96A8E': 'Rani Pink 11' } } as unknown as NumberInfo, names)).toBe(true);
    expect(namesStale({ names: { '#D96A8E': 'Rani Pink 12', '#1F2A60': 'Navy' } } as unknown as NumberInfo, names)).toBe(true);
    expect(namesStale({} as NumberInfo, {})).toBe(false);
  });
  it('a rebuild that only named inks says so', () => {
    expect(rebuildMessage(0, 3, true)).toBe('Your ink names are in the zip now. Download it again.');
    expect(translate('hi', rebuildMessage(0, 3, true))).toBe('Aapke inks ke naam ab zip me hain. Dobara download karo.');
  });
});

describe('the operator’s smallest shape', () => {
  it('empty leaves it to Detail; a plain number is read, a comma too', () => {
    expect(parseMinArea('')).toBeNull();
    expect(parseMinArea('  ')).toBeNull();
    expect(parseMinArea('3')).toBe(3);
    expect(parseMinArea('2,5')).toBe(2.5);
    expect(parseMinArea(' 0.1 ')).toBe(0.1);
    expect(parseMinArea('50')).toBe(50);
  });
  it('anything else is caught before the run of a few minutes', () => {
    for (const bad of ['0', '0.05', '51', '-3', 'abc', '3mm', '1e2', '..5', '3.']) expect(parseMinArea(bad)).toBe('bad');
  });
});

describe('numbers typed to change by number', () => {
  it('reads single numbers, lists and ranges, once each, ascending', () => {
    expect(parseAreaNumbers('101', 873)).toEqual([101]);
    expect(parseAreaNumbers('104, 101 ,110-112; 101', 873)).toEqual([101, 104, 110, 111, 112]);
    expect(parseAreaNumbers('12 - 10', 873)).toEqual([10, 11, 12]);
    expect(parseAreaNumbers(' #7 #9 ', 873)).toEqual([7, 9]);
  });
  it('is empty for nothing and bad for anything off the sketch', () => {
    expect(parseAreaNumbers('  ', 873)).toBeNull();
    for (const bad of ['0', '874', 'x', '5-', '1-2-3', '-4', '3.5', '1-99999'])
      expect(parseAreaNumbers(bad, 873)).toBe('bad');
  });
  it('says what happened, in Hinglish too', () => {
    const m = areasMessage(3, '#1f2a60');
    expect(m).toBe('3 area(s) now #1F2A60: the colours list, plates, channels and design are in the new zip. Download it again.');
    expect(translate('hi', m)).toBe('3 hisse ab #1F2A60: colours list, plates, channels aur design naye zip me hain. Zip dobara download karo.');
  });
});
