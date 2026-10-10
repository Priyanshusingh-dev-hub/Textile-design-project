import { describe, expect, it } from 'vitest';
import { HI } from './i18n';
import { AUTO_FIELDS, CLIENT_FIELDS, RATE_FIELDS } from './settings';
import { STAGE_LABEL, WARN_LABEL } from './jobs';
import { PERIODS } from './clients';
import { MASCOT_LINES } from './mascot';

/** Every English string the app passes to t() as written in the source. */
function literalKeys(): Map<string, string> {
  // the app's own source, as text (Vite reads it; no Node APIs needed)
  const sources = import.meta.glob(['/src/**/*.{ts,tsx}', '!/src/**/*.test.ts'],
    { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  const lit = String.raw`'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"`;
  const chain = new RegExp(String.raw`\b(?:t|tr)\(\s*((?:(?:${lit})\s*\+\s*)*(?:${lit}))\s*[,)]`, 'g');
  const ternary = new RegExp(String.raw`\b(?:t|tr)\(\s*[\w.?!\s=<>&|()[\]'"-]*?\?\s*(${lit})\s*:\s*(${lit})\s*[,)]`, 'g');
  const unquote = (s: string) => s.slice(1, -1).replace(/\\(['"\\])/g, '$1');
  const keys = new Map<string, string>();
  for (const [f, src] of Object.entries(sources)) {
    for (const m of src.matchAll(chain)) {
      keys.set([...m[1].matchAll(new RegExp(lit, 'g'))].map(x => unquote(x[0])).join(''), f);
    }
    for (const m of src.matchAll(ternary)) { keys.set(unquote(m[1]), f); keys.set(unquote(m[2]), f); }
  }
  return keys;
}

describe('every visible string has its Hinglish', () => {
  it('in the source: t("…") and tr("…"), joined and either side of a ?:', () => {
    const keys = literalKeys();
    expect(keys.size).toBeGreaterThan(200);                    // the scan really found the app's strings
    const missing = [...keys].filter(([k]) => !(k in HI)).map(([k, f]) => `${f}: ${k}`);
    expect(missing).toEqual([]);
  });

  it('in the label lists the views translate', () => {
    const labels = [
      ...[...RATE_FIELDS, ...AUTO_FIELDS, ...CLIENT_FIELDS].flatMap(f => [f.label, f.unit, f.hint]),
      ...Object.values(STAGE_LABEL), ...Object.values(WARN_LABEL), ...PERIODS.map(([, l]) => l), ...MASCOT_LINES,
    ].filter((s): s is string => !!s);
    expect(labels.filter(l => !(l in HI))).toEqual([]);
  });
});
