import { describe, expect, it } from 'vitest';
import { AUTO_FIELDS, fromForm, pricesFromRows, priceRows, RATE_FIELDS, toForm } from './settings';

describe('settings form', () => {
  it('round-trips the numbers', () => {
    const values = Object.fromEntries(RATE_FIELDS.map((f, i) => [f.key, i + 1]));
    expect(fromForm(toForm(values, RATE_FIELDS), RATE_FIELDS)).toEqual({ values, errors: {} });
  });

  it('reads Indian-style thousands', () => {
    const form = toForm({}, [RATE_FIELDS[0]]);
    form.screen_cost = '1,500';
    expect(fromForm(form, [RATE_FIELDS[0]]).values.screen_cost).toBe(1500);
  });

  it('says what is wrong with each box', () => {
    const form = Object.fromEntries(AUTO_FIELDS.map(f => [f.key, '1']));
    form.min_accuracy = '120'; form.max_inks = '7.5'; form.tiny_dot_mm = '-1'; form.min_source_ppi = 'abc';
    const { errors } = fromForm(form, AUTO_FIELDS);
    expect(errors).toEqual({ min_accuracy: '100 at most', max_inks: 'a whole number', tiny_dot_mm: '0 or more',
      min_source_ppi: 'a number' });
  });

  it('turns ink price rows back into a map, and refuses unnamed or repeated inks', () => {
    expect(priceRows({ 'Rani Pink 12': 620 })).toEqual([{ name: 'Rani Pink 12', price: '620' }]);
    expect(pricesFromRows([{ name: ' Rani Pink 12 ', price: '620' }, { name: '', price: '' }]))
      .toEqual({ prices: { 'Rani Pink 12': 620 } });
    expect(pricesFromRows([{ name: '', price: '5' }]).error).toMatch(/name/);
    expect(pricesFromRows([{ name: 'A', price: '1' }, { name: 'a', price: '2' }]).error).toMatch(/twice/);
    expect(pricesFromRows([{ name: 'A', price: '-1' }]).error).toMatch(/number/);
  });
});
