import { describe, expect, it } from 'vitest';
import { changedCount, parseHex, quickPicks, renamed, snapshotColours } from './recolour';

const layers = [{ id: 'a', color: '#8F1528', name: 'Ink 1' }, { id: 'b', color: '#F2E9E2', name: 'Ink 2' }];

describe('parseHex', () => {
  it('reads what an operator types', () => {
    expect(parseHex('#d96a8e')).toBe('#D96A8E');
    expect(parseHex(' D96A8E ')).toBe('#D96A8E');
    expect(parseHex('#d6e')).toBe('#DD66EE');
    expect(parseHex('red')).toBeNull();
    expect(parseHex('#12345')).toBeNull();
  });
});

describe('snapshot', () => {
  it('counts the plates whose colour changed', () => {
    const snap = snapshotColours(layers);
    expect(changedCount(layers, snap)).toBe(0);
    expect(changedCount([{ ...layers[0], color: '#1E2A4A' }, layers[1]], snap)).toBe(1);
    expect(changedCount([{ ...layers[0], color: '#8f1528' }, layers[1]], snap)).toBe(0);
  });
});

describe('quickPicks', () => {
  it('offers the other plates and the shelf, once each, never the current colour', () => {
    const picks = quickPicks(layers, 'a', [{ name: 'Rani Pink', hex: '#d96a8e' }, { name: 'Cream 2', hex: '#F2E9E2' }]);
    expect(picks).toEqual([{ hex: '#F2E9E2', from: 'plate' }, { hex: '#D96A8E', name: 'Rani Pink', from: 'shelf' }]);
  });
});

describe('renamed', () => {
  const lib = [{ name: 'Rani Pink' }];
  it('takes a shelf ink name, drops a stale one, keeps a custom one', () => {
    expect(renamed('Ink 1', 0, 'Rani Pink', lib)).toBe('Rani Pink');
    expect(renamed('Rani Pink', 0, undefined, lib)).toBe('Ink 1');
    expect(renamed('Border Red', 0, undefined, lib)).toBe('Border Red');
  });
});
