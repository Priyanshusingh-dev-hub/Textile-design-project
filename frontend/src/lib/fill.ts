import type { FillInfo, FillTrial, FillTrials } from '../types';
import { english, type Tr } from './i18n';

/** The ways to make the flat design from a line art + reference pair. Auto
 *  tries them all, scores each against the reference and says why. */
export type FillMethod = 'auto' | '0' | '1' | '4' | '3' | '2';
export const FILL_METHODS: { value: FillMethod; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto (recommended)', hint: 'tries every way, scores each against the reference, picks the best' },
  { value: '0', label: 'Reference only', hint: 'ignores the line art: the reference is reduced like any design' },
  { value: '1', label: 'Method 1: aligned', hint: 'the reference is the same picture as the line art' },
  { value: '4', label: 'Method 4: gaps sealed', hint: 'like Method 1, but breaks in the line art no longer let colour leak' },
  { value: '3', label: 'Method 3: reference shifted', hint: 'the same drawing, but a little moved or stretched' },
  { value: '2', label: 'Method 2: different drawing', hint: 'two colours only: ground and motif, shapes from the line art' },
];

/** The way's name in the table, and the code `POST /api/fill` takes for it. */
export const TRIAL_LABEL: Record<FillTrial['name'], string> = {
  reduce: 'Reference only (Reduce)',
  method1: 'Method 1: aligned',
  method4: 'Method 4: gaps sealed',
  method3: 'Method 3: reference shifted',
  method2: 'Method 2: two colours',
};
export const TRIAL_CODE: Record<FillTrial['name'], FillMethod> = {
  reduce: '0', method1: '1', method4: '4', method3: '3', method2: '2',
};

export function alignmentVerdict(a: number): { text: string; good: boolean } {
  if (a >= 0.85) return { text: 'good', good: true };
  if (a >= 0.55) return { text: 'low: check the result closely', good: false };
  return { text: 'very low: the two images may not be the same design', good: false };
}

const row = (t: FillTrials, name: FillTrial['name']) => t.rows.find(r => r.name === name);
const bestFill = (t: FillTrials) =>
  t.rows.filter(r => r.name !== 'reduce' && r.status === 'ok').sort((a, b) => (b.match ?? 0) - (a.match ?? 0))[0];

/** Why this one: built from the numbers the judge measured, so the words
 *  can be translated and the numbers can be checked against the table. */
export function methodNote(f: FillInfo, tr: Tr = english): { text: string; warn: boolean } {
  const t = f.trials;
  if (!t) return { text: tr('You picked {name}.', { name: tr(TRIAL_LABEL[CODE_NAME[f.method]]) }), warn: false };
  if (t.reason === 'operator') {
    return { text: tr('You picked {name} instead of {auto}. Your choice stands, and is kept in the log.',
      { name: tr(TRIAL_LABEL[t.chosen]), auto: tr(TRIAL_LABEL[t.auto ?? 'reduce']) }), warn: false };
  }
  const red = row(t, 'reduce')?.match ?? 0;
  const best = bestFill(t);
  if (t.reason === 'no_fill' || !best) {
    return { text: tr('No fill could be made from this line art, so the reference alone was reduced.'), warn: true };
  }
  const name = tr(TRIAL_LABEL[best.name]);
  if (t.reason === 'fill_close') {
    return { text: tr('Chose {name}: it matches the reference {m}%, within {tol} points of the reference alone ({r}%), and the line art gives it cleaner edges.',
      { name, m: best.match ?? 0, tol: t.tolerance, r: red }), warn: false };
  }
  return { text: tr('Chose the reference alone: the best fill ({name}) matches only {m}%, {gap} points under it ({r}%), so this line art does not carry the design. If you want the line art’s shapes anyway, pick a fill below.',
    { name, m: best.match ?? 0, gap: Math.abs(t.margin ?? 0), r: red }), warn: true };
}
/** The one line shown while the table is closed: what was chosen, with its number. */
export function trialSummary(f: FillInfo, tr: Tr = english): { text: string; warn: boolean } {
  const t = f.trials;
  if (!t) return { text: tr('You picked {name}.', { name: tr(TRIAL_LABEL[CODE_NAME[f.method]]) }), warn: false };
  if (t.reason === 'operator') {
    return { text: tr('You picked {name} (the judge had chosen {auto})', { name: tr(TRIAL_LABEL[t.chosen]), auto: tr(TRIAL_LABEL[t.auto ?? 'reduce']) }), warn: false };
  }
  const red = row(t, 'reduce')?.match ?? 0;
  const best = bestFill(t);
  if (t.reason === 'no_fill' || !best) return { text: tr('Reference alone: no fill could be made.'), warn: true };
  if (t.reason === 'fill_close') {
    return { text: tr('Chose {name} ({m}%) over the reference alone ({r}%)', { name: tr(TRIAL_LABEL[best.name]), m: best.match ?? 0, r: red }), warn: false };
  }
  return { text: tr('Chose the reference alone ({r}%): the line art does not carry this design', { r: red }), warn: true };
}
const CODE_NAME: Record<number, FillTrial['name']> = { 0: 'reduce', 1: 'method1', 2: 'method2', 3: 'method3', 4: 'method4' };

/** The table kept after the operator takes another way: the same numbers, the
 *  tick on their choice, and what the judge had chosen remembered. */
export function pickedFrom(prev: FillTrials, method: number): FillTrials {
  const name = CODE_NAME[method];
  return { ...prev, rows: prev.rows.map(r => ({ ...r, chosen: r.name === name })), chosen: name,
    reason: 'operator', auto: prev.auto ?? prev.chosen };
}

/** The footer line after a fill. */
export function fillMessage(f: FillInfo, inks: number): string {
  if (f.method === 0) return `Made from the reference alone: ${inks} inks. Fine-tune the palette or continue.`;
  return f.alignment === null
    ? `Filled from the line art: ${inks} inks (Method ${f.method}). Check the result, then separate.`
    : `Filled from the line art: ${inks} inks, alignment ${f.alignment.toFixed(2)}. Check the result, then separate.`;
}

/** Method 2 gives two colours (ground + motif). When the reference has more,
 *  its own colours, reduced the usual way, keep them all: a line art drawn
 *  differently from the reference cannot carry them over (the elephant panel:
 *  Method 2 two colours, the reference reduced four, red and taupe included). */
export function offerReferenceColours(f: FillInfo): boolean {
  return f.method === 2;
}
