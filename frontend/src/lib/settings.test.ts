import { describe, expect, it } from 'vitest';
import { AUTO_FIELDS, clientRows, clientsFromRows, fromForm, pricesFromRows, priceRows, RATE_FIELDS, toForm } from './settings';
import { translate } from './i18n';

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

describe("a regular client's own rates", () => {
  it('round-trips, a blank box meaning the rate card', () => {
    const rows = clientRows({ 'Ravi Textiles': { margin_percent: 10, screen_cost: 1200 } });
    expect(rows).toEqual([{ name: 'Ravi Textiles', rates: { margin_percent: '10', screen_cost: '1200' } }]);
    rows.push({ name: '', rates: { setup_per_job: '  ' } });                 // an untouched new row
    expect(clientsFromRows(rows)).toEqual({ clients: { 'Ravi Textiles': { margin_percent: 10, screen_cost: 1200 } } });
  });

  it('says what is wrong, in either language', () => {
    expect(clientsFromRows([{ name: '', rates: { margin_percent: '5' } }]).error).toMatch(/client name/);
    expect(clientsFromRows([{ name: 'Ravi', rates: {} }]).error).toMatch(/at least one/);
    expect(clientsFromRows([{ name: 'Ravi', rates: { margin_percent: '5' } }, { name: 'ravi', rates: { margin_percent: '6' } }]).error)
      .toMatch(/twice/);
    expect(clientsFromRows([{ name: 'Ravi', rates: { margin_percent: '5000' } }]).error).toBe('Ravi: Your margin must be 1000 at most.');
    const hi = (t: string, v?: Record<string, string | number>) => translate('hi', t, v);
    expect(clientsFromRows([{ name: 'Ravi', rates: { screen_cost: 'lots' } }], hi).error).toBe('Ravi: Ek screen — number chahiye.');
  });
});
