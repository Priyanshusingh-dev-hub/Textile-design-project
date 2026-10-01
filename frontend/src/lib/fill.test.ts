import { describe, expect, it } from 'vitest';
import type { FillInfo } from '../types';
import { alignmentVerdict, fillMessage, methodNote, offerReferenceColours } from './fill';
import { HI, translate } from './i18n';

const base: FillInfo = { method: 1, auto: null, alignment: 0.96, regions: 10, doubtful: 0, debug_url: null,
  line_color: '#000000', stray_merged: [], size_px: [3535, 3535] };
const m1 = { alignment_score: 0.53, coverage_diff: 6.9 };

describe('fill notes', () => {
  it('says which method ran, and for auto why', () => {
    expect(methodNote(base).text).toBe('Filled with Method 1.');
    const ok = methodNote({ ...base, auto: { chosen: 1, method1: { alignment_score: 0.96, coverage_diff: 1.7 }, limit: 6, coverage_diff: 1.7 } });
    expect(ok.text).toContain('Method 1');
    expect(ok.warn).toBe(false);
    const three = methodNote({ ...base, method: 3, auto: { chosen: 3, method1: m1, limit: 6, coverage_diff: 2.3 } });
    expect(three.text).toContain('alignment 0.53, colour shares 6.9 points');
    expect(three.text).toContain('Auto chose Method 3');
    const two = methodNote({ ...base, method: 2, alignment: null, auto: { chosen: 2, method1: m1, limit: 6, coverage_diff: 7.6, only_two: true } });
    expect(two.warn).toBe(true);
    expect(two.text).toContain('different drawing');
  });
  it('has its Hinglish for every piece', () => {
    const tr = (t: string, v?: Record<string, string | number>) => translate('hi', t, v);
    const two = methodNote({ ...base, method: 2, alignment: null, auto: { chosen: 2, method1: m1, limit: 6, coverage_diff: 7.6, only_two: true } }, tr);
    expect(two.text).toContain('0.53');
    expect(two.text).not.toContain('Auto chose');
    // the footer is built with its numbers in and matched to its template
    expect(translate('hi', fillMessage({ ...base, alignment: null, method: 2 }, 2))).toContain('Method 2');
    expect(translate('hi', fillMessage({ ...base, alignment: null, method: 2 }, 2))).not.toContain('Filled from');
    expect(Object.keys(HI)).toContain('Filled with Method {n}.');
  });
  it('rates the alignment', () => {
    expect(alignmentVerdict(0.9).good).toBe(true);
    expect(alignmentVerdict(0.6).text).toMatch(/^low/);
    expect(alignmentVerdict(0.3).text).toMatch(/^very low/);
  });
  it('words the footer with and without an alignment', () => {
    expect(fillMessage(base, 9)).toBe('Filled from the line art: 9 inks, alignment 0.96. Check the result, then separate.');
    expect(fillMessage({ ...base, alignment: null, method: 2 }, 2)).toContain('2 inks (Method 2)');
  });
});

describe('the way out of a two-colour fill', () => {
  it('is offered after Method 2 only', () => {
    expect(offerReferenceColours({ ...base, method: 2, alignment: null })).toBe(true);
    expect(offerReferenceColours(base)).toBe(false);
    expect(offerReferenceColours({ ...base, method: 3 })).toBe(false);
  });
});
