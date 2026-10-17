import { describe, expect, it } from 'vitest';
import type { FillInfo, FillTrial, FillTrials } from '../types';
import { alignmentVerdict, fillMessage, methodNote, offerReferenceColours, pickedFrom, TRIAL_CODE, TRIAL_LABEL, trialSummary } from './fill';
import { HI, translate } from './i18n';

const ok = (name: FillTrial['name'], match: number, inks = 6, edge = 12): FillTrial =>
  ({ name, status: 'ok', match, inks, edge_share: edge, seconds: 1 });
const trials = (rows: FillTrial[], chosen: FillTrial['name'], reason: FillTrials['reason'], margin: number | null): FillTrials =>
  ({ rows: rows.map(r => ({ ...r, chosen: r.name === chosen })), chosen, reason, margin, tolerance: 15, inks: 6, trial_px: 1200, seconds: 25 });
const base: FillInfo = { method: 4, trials: null, alignment: 0.96, regions: 10, doubtful: 0, debug_url: null,
  line_color: '#000000', stray_merged: [], size_px: [3535, 3535] };

describe('what the judge says', () => {
  it('a fill that is close enough wins, and the words carry the numbers', () => {
    const t = trials([ok('reduce', 86.2), ok('method1', 69), ok('method4', 74.1)], 'method4', 'fill_close', -12.1);
    const n = methodNote({ ...base, trials: t });
    expect(n.warn).toBe(false);
    expect(n.text).toContain('Method 4: gaps sealed');
    expect(n.text).toContain('74.1%');
    expect(n.text).toContain('86.2%');
    expect(n.text).toContain('within 15 points');
  });
  it('the reference alone wins when every fill trails by more, and says so as a warning', () => {
    const t = trials([ok('reduce', 83.3), ok('method1', 35.5), ok('method4', 44.8)], 'reduce', 'fill_far', -38.5);
    const n = methodNote({ ...base, method: 0, alignment: null, trials: t });
    expect(n.warn).toBe(true);
    expect(n.text).toContain('44.8%');
    expect(n.text).toContain('38.5 points');
    expect(n.text).toContain('Method 4: gaps sealed');      // the best fill, named
  });
  it('no fill at all, and a method picked by hand', () => {
    const t = trials([ok('reduce', 80), { name: 'method1', status: 'failed', seconds: 1 }], 'reduce', 'no_fill', null);
    expect(methodNote({ ...base, method: 0, trials: t }).text).toContain('No fill could be made');
    expect(methodNote({ ...base, method: 3 }).text).toBe('You picked Method 3: reference shifted.');
  });
  it('one line while the table is closed, with the number that decided', () => {
    const close = trials([ok('reduce', 86.2), ok('method4', 74.1)], 'method4', 'fill_close', -12.1);
    expect(trialSummary({ ...base, trials: close }).text).toBe('Chose Method 4: gaps sealed (74.1%) over the reference alone (86.2%)');
    const far = trials([ok('reduce', 83.3), ok('method4', 44.8)], 'reduce', 'fill_far', -38.5);
    const s = trialSummary({ ...base, method: 0, trials: far });
    expect(s.warn).toBe(true);
    expect(s.text).toContain('83.3%');
    expect(trialSummary({ ...base, method: 0, trials: far }, (t, v) => translate('hi', t, v)).text).toContain('Sirf reference');
  });
  it('taking another way keeps the table, moves the tick and remembers what the judge chose', () => {
    const far = trials([ok('reduce', 83.3), ok('method4', 44.8)], 'reduce', 'fill_far', -38.5);
    const mine = pickedFrom(far, 4);
    expect(mine.chosen).toBe('method4');
    expect(mine.auto).toBe('reduce');
    expect(mine.rows.filter(r => r.chosen).map(r => r.name)).toEqual(['method4']);
    expect(mine.rows.find(r => r.name === 'reduce')?.match).toBe(83.3);       // the numbers stay
    const again = pickedFrom(mine, 0);                                           // and back again
    expect(again.auto).toBe('reduce');                                           // the judge's choice is not overwritten
    const info = { ...base, trials: mine };
    expect(methodNote(info).text).toContain('instead of Reference only (Reduce)');
    expect(trialSummary(info).text).toContain('the judge had chosen');
    expect(methodNote(info, (t, v) => translate('hi', t, v)).text).not.toContain('You picked');
  });
  it('every way has a label and a code the engine takes', () => {
    for (const k of Object.keys(TRIAL_LABEL) as FillTrial['name'][]) expect(TRIAL_CODE[k]).toMatch(/^[0-4]$/);
    expect(TRIAL_CODE.reduce).toBe('0');
  });
  it('has its Hinglish for every sentence', () => {
    const tr = (t: string, v?: Record<string, string | number>) => translate('hi', t, v);
    const t = trials([ok('reduce', 83.3), ok('method4', 44.8)], 'reduce', 'fill_far', -38.5);
    const hi = methodNote({ ...base, method: 0, trials: t }, tr).text;
    expect(hi).toContain('44.8');
    expect(hi).not.toContain('Chose the reference');
    const close = methodNote({ ...base, trials: trials([ok('reduce', 86), ok('method4', 74)], 'method4', 'fill_close', -12) }, tr).text;
    expect(close).not.toContain('Chose ');
    expect(Object.keys(HI)).toContain('You picked {name}.');
  });
});

describe('the rest of the fill notes', () => {
  it('rates the alignment', () => {
    expect(alignmentVerdict(0.9).good).toBe(true);
    expect(alignmentVerdict(0.6).text).toMatch(/^low/);
    expect(alignmentVerdict(0.3).text).toMatch(/^very low/);
  });
  it('words the footer for each outcome', () => {
    expect(fillMessage(base, 9)).toBe('Filled from the line art: 9 inks, alignment 0.96. Check the result, then separate.');
    expect(fillMessage({ ...base, alignment: null, method: 2 }, 2)).toContain('2 inks (Method 2)');
    expect(fillMessage({ ...base, alignment: null, method: 0 }, 6)).toContain('reference alone: 6 inks');
    expect(translate('hi', fillMessage({ ...base, alignment: null, method: 0 }, 6))).not.toContain('Made from');
  });
  it('the two-colour way out is offered after Method 2 only', () => {
    expect(offerReferenceColours({ ...base, method: 2, alignment: null })).toBe(true);
    expect(offerReferenceColours(base)).toBe(false);
    expect(offerReferenceColours({ ...base, method: 0, alignment: null })).toBe(false);
  });
});
