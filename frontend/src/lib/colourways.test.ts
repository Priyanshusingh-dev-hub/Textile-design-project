import { describe, expect, it } from 'vitest';
import { apply, nameProblem, nextName, snapshot, toRequest } from './colourways';

const plates = [{ id: 'a', color: '#c0392b', name: 'Red' }, { id: 'b', color: '#f4e8cc', name: 'Cream', skip: true }];

describe('colourways', () => {
  it('names them A, B, C… skipping taken ones', () => {
    expect(nextName([])).toBe('A');
    expect(nextName([snapshot('A', plates, '#fff'), snapshot('c', plates, '#fff')])).toBe('B');
  });

  it('keeps every plate, hidden ones too, and upper-cases colours', () => {
    const w = snapshot(' Navy ', plates, '#ffffff');
    expect(w).toEqual({ name: 'Navy', fabric: '#FFFFFF',
      inks: { a: { color: '#C0392B', name: 'Red' }, b: { color: '#F4E8CC', name: 'Cream' } } });
  });

  it('refuses names the package could not tell apart', () => {
    const ways = [snapshot('Olive/Gold', plates, '#fff')];
    expect(nameProblem('olive-gold', ways)).toMatch(/already/);
    expect(nameProblem('  ', ways)).toMatch(/name/);
    expect(nameProblem('Navy', ways)).toBe('');
  });

  it('sends one ink per printing screen, the current colour for a screen it never saw', () => {
    const w = snapshot('B', [plates[0]], '#FFFFFF');
    w.inks.a = { color: '#1F2A44', name: 'Navy' };
    expect(toRequest([w], plates)).toEqual([{ name: 'B', fabric: '#FFFFFF',
      inks: [{ id: 'a', color: '#1F2A44', name: 'Navy' }, { id: 'b', color: '#f4e8cc', name: 'Cream' }] }]);
  });

  it('puts a colourway back on the plates, keeping which are hidden', () => {
    const w = snapshot('B', plates, '#FFFFFF');
    w.inks.a = { color: '#1F2A44', name: '' };
    const got = apply(w, plates);
    expect(got[0]).toEqual({ id: 'a', color: '#1F2A44', name: 'Red' });
    expect(got[1].skip).toBe(true);
  });
});
