import type { FillInfo } from '../types';
import { english, type Tr } from './i18n';

/** The four ways to fill line art from a reference (the textile tool's). */
export type FillMethod = 'auto' | '1' | '3' | '2';
export const FILL_METHODS: { value: FillMethod; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto (recommended)', hint: 'tries Method 1, checks it, then 3 or 2' },
  { value: '1', label: 'Method 1: aligned', hint: 'the reference is the same picture as the line art' },
  { value: '3', label: 'Method 3: reference shifted', hint: 'the same drawing, but a little moved or stretched' },
  { value: '2', label: 'Method 2: different drawing', hint: 'two colours only: ground and motif, shapes from the line art' },
];

export function alignmentVerdict(a: number): { text: string; good: boolean } {
  if (a >= 0.85) return { text: 'good', good: true };
  if (a >= 0.55) return { text: 'low: check the result closely', good: false };
  return { text: 'very low: the two images may not be the same design', good: false };
}

/** Which method filled the design, and, for auto, why: built from the
 *  numbers the engine measured (its own reasons are in Hinglish only). */
export function methodNote(f: FillInfo, tr: Tr = english): { text: string; warn: boolean } {
  const a = f.auto;
  if (!a) return { text: tr('Filled with Method {n}.', { n: f.method }), warn: false };
  const m1 = a.method1;
  if (a.chosen === 1) {
    return { text: tr('Auto chose Method 1: the two images line up (colour shares {d} points off the reference).',
      { d: m1.coverage_diff }), warn: false };
  }
  const off = tr('Method 1 was off: alignment {a}, colour shares {d} points off the reference (more than {l} fails).',
    { a: m1.alignment_score.toFixed(2), d: m1.coverage_diff, l: a.limit });
  if (a.chosen === 3) {
    return { text: off + ' ' + tr('Auto chose Method 3: the reference was moved onto the line art.'), warn: false };
  }
  return {
    text: off + ' ' + tr(a.only_two
      ? 'Method 3 found nothing to shift to either, so the reference looks like a different drawing. Auto chose Method 2: two colours (ground and motif), shapes from the line art. If the design needs more colours, make the line art and the reference from the same picture.'
      : 'Auto chose Method 2: two colours (ground and motif), shapes from the line art.'),
    warn: !!a.only_two,
  };
}

/** The footer line after a fill. */
export function fillMessage(f: FillInfo, inks: number): string {
  return f.alignment === null
    ? `Filled from the line art: ${inks} inks (Method ${f.method}). Check the result, then separate.`
    : `Filled from the line art: ${inks} inks, alignment ${f.alignment.toFixed(2)}. Check the result, then separate.`;
}
