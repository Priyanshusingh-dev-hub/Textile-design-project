// The Settings screen's form logic: the rate card and auto mode's limits as
// text boxes, and back to the numbers the engine checks again before saving.

export type Field = { key: string; label: string; unit?: string; hint?: string; whole?: boolean; max?: number };

export const RATE_FIELDS: Field[] = [
  { key: 'screen_cost', label: 'One screen', unit: 'per screen', hint: 'making one screen for a design' },
  { key: 'ink_per_kg', label: 'Ink', unit: 'per kg', hint: 'any ink not priced by name below' },
  { key: 'underbase_ink_per_kg', label: 'White under-base ink', unit: 'per kg' },
  { key: 'ink_g_per_sqm', label: 'Ink laid down', unit: 'g per m²', hint: 'at full cover' },
  { key: 'fabric_width_in', label: 'Cloth width', unit: 'inch' },
  { key: 'fabric_per_meter', label: 'Cloth', unit: 'per meter', hint: "0 = the client's own cloth" },
  { key: 'labour_per_meter_per_screen', label: 'Printing', unit: 'per meter per screen' },
  { key: 'setup_per_job', label: 'Setup', unit: 'per job', hint: 'table setup, washing, a sample' },
  { key: 'wastage_percent', label: 'Wastage', unit: '%', max: 100 },
  { key: 'margin_percent', label: 'Your margin', unit: '%', max: 1000 },
  { key: 'gst_percent', label: 'GST', unit: '%', max: 100 },
  { key: 'quote_valid_days', label: 'Quote valid for', unit: 'days', whole: true, max: 3650 },
  { key: 'manual_minutes_per_design', label: 'A design by hand', unit: 'minutes', hint: 'for the time-saved estimate on Jobs' },
  { key: 'review_minutes_per_design', label: 'Checking a held design', unit: 'minutes', hint: 'for the time-saved estimate' },
  { key: 'staff_cost_per_hour', label: 'Operator cost', unit: 'per hour', hint: 'for the money-saved estimate' },
];

export const AUTO_FIELDS: Field[] = [
  { key: 'min_accuracy', label: 'Lowest match', unit: '%', max: 100, hint: 'below it a job waits for a person' },
  { key: 'photographic_ceiling', label: 'Photo-like below', unit: '%', max: 100, hint: 'best match any ink count reaches' },
  { key: 'max_inks', label: 'Most screens', unit: 'screens', whole: true, max: 20 },
  { key: 'tiny_dot_mm', label: 'Tiny dot', unit: 'mm', hint: 'smaller than this will not hold on the mesh' },
  { key: 'max_tiny_dot_share', label: 'Tiny dots allowed', unit: '% of the print', max: 100 },
  { key: 'clean_dots_mm', label: 'Clean dots under', unit: 'mm', hint: '0 = leave them' },
  { key: 'min_source_ppi', label: 'Lowest file resolution', unit: 'pixels per inch' },
];

export type Values = Record<string, unknown>;
export type Form = Record<string, string>;

export const toForm = (values: Values, fields: Field[]): Form =>
  Object.fromEntries(fields.map(f => [f.key, values[f.key] === undefined ? '' : String(values[f.key])]));

/** The typed form as numbers, or what is wrong with each box. */
export function fromForm(form: Form, fields: Field[]): { values: Values; errors: Record<string, string> } {
  const values: Values = {}, errors: Record<string, string> = {};
  for (const f of fields) {
    const text = (form[f.key] ?? '').trim().replace(/,/g, '');
    const n = Number(text);
    if (!text || !Number.isFinite(n)) errors[f.key] = 'a number';
    else if (n < 0) errors[f.key] = '0 or more';
    else if (f.whole && !Number.isInteger(n)) errors[f.key] = 'a whole number';
    else if (f.max !== undefined && n > f.max) errors[f.key] = `${f.max} at most`;
    else values[f.key] = n;
  }
  return { values, errors };
}

export type PriceRow = { name: string; price: string };

export const priceRows = (prices: unknown): PriceRow[] =>
  Object.entries((prices as Record<string, number>) || {}).map(([name, p]) => ({ name, price: String(p) }));

/** Named ink prices back to {name: price}; rows with no name and no price are dropped. */
export function pricesFromRows(rows: PriceRow[]): { prices: Record<string, number>; error?: string } {
  const prices: Record<string, number> = {};
  for (const r of rows) {
    const name = r.name.trim(), text = r.price.trim().replace(/,/g, '');
    if (!name && !text) continue;
    if (!name) return { prices, error: 'Every ink price needs the ink name.' };
    const n = Number(text);
    if (!text || !Number.isFinite(n) || n < 0) return { prices, error: `${name}: the price must be a number, 0 or more.` };
    if (Object.keys(prices).some(k => k.toUpperCase() === name.toUpperCase())) return { prices, error: `${name} is listed twice.` };
    prices[name] = n;
  }
  return { prices };
}
