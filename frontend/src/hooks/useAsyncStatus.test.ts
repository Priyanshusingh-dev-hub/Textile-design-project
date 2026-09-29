import { describe, expect, it } from 'vitest';
import { Work } from './useAsyncStatus';

describe('shared work status', () => {
  it('stays busy until the last piece of work ends', () => {
    const w = new Work();
    const [zip] = w.start('Building zip…');
    const [proof, s] = w.start();                  // a preview the page redraws on its own
    expect(s).toEqual({ state: 'processing', label: 'Building zip…' });
    expect(w.end(proof)).toEqual({ state: 'processing', label: 'Building zip…' });
    expect(w.end(zip)).toEqual({ state: 'done' });
  });

  it('reports an error once everything has ended, and forgets it on the next start', () => {
    const w = new Work();
    const [a] = w.start('Reducing…');
    const [b] = w.start();
    expect(w.end(b, 'engine closed').state).toBe('processing');
    expect(w.end(a)).toEqual({ state: 'failed', message: 'engine closed' });
    const [c] = w.start('Reducing…');
    expect(w.end(c)).toEqual({ state: 'done' });
  });

  it('shows the newest named action', () => {
    const w = new Work();
    w.start('Reducing…');
    const [, s] = w.start('Separating…');
    expect(s.label).toBe('Separating…');
  });
});
