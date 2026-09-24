import { describe, it, expect } from 'vitest';
import { inkOwner, LIBRARY_CLOSE, matchLabel, parseInkList, planSwap, swapPalette } from './inks';

describe('parseInkList', () => {
  it('reads the ways a mill writes its inks down', () => {
    const { inks, errors } = parseInkList(
      'Rani Pink 12, #D96A8E\nNavy 3 #1e2a4a\n#E8C317 Haldi\n\nKora (cream)\t#EFE3C8\n');
    expect(errors).toEqual([]);
    expect(inks).toEqual([
      { name: 'Rani Pink 12', hex: '#D96A8E' }, { name: 'Navy 3', hex: '#1E2A4A' },
      { name: 'Haldi', hex: '#E8C317' }, { name: 'Kora (cream)', hex: '#EFE3C8' }]);
  });

  it('reports lines it cannot read instead of guessing', () => {
    const { inks, errors } = parseInkList('Maroon\n#123456\nGold, #C8A13A');
    expect(inks).toEqual([{ name: 'Gold', hex: '#C8A13A' }]);
    expect(errors).toEqual(['Maroon', '#123456']);
  });
});

describe('matchLabel', () => {
  it('is honest about how close the shelf ink is', () => {
    expect(matchLabel({ name: 'Haldi', hex: '#E8C317', delta_e: 0.4 })!.tone).toBe('same');
    expect(matchLabel({ name: 'Haldi', hex: '#E8C317', delta_e: 3.2 })!.text).toBe('≈ Haldi · ΔE 3.2');
    const far = matchLabel({ name: 'Haldi', hex: '#E8C317', delta_e: 14 })!;
    expect(far.tone).toBe('far');
    expect(far.text).toMatch(/mix a new ink/);
    expect(matchLabel(null)).toBeNull();
  });
});

describe('planSwap', () => {
  const palette = [{ hex: '#DA6B8C' }, { hex: '#202C4C', locked: true }, { hex: '#FFFFFF' }];
  const matches = [{ name: 'Rani Pink 12', hex: '#D96A8E', delta_e: 1.1 },
                   { name: 'Navy 3', hex: '#1E2A4A', delta_e: 1.0 },
                   { name: 'Kora', hex: '#EFE3C8', delta_e: LIBRARY_CLOSE + 4 }];
  it('swaps only close, unlocked inks', () => {
    const { targets, count } = planSwap(palette, matches);
    expect(count).toBe(1);
    expect(targets.map(t => t?.name ?? null)).toEqual(['Rani Pink 12', null, null]);
  });
});

describe('planSwap, one shelf ink per colour', () => {
  const near = { name: 'Near', hex: '#515442', delta_e: 1.2 };
  it('gives a shelf ink to the closest colour only', () => {
    const pal = [{ hex: '#525543' }, { hex: '#60614C' }];
    const { targets, count } = planSwap(pal, [near, { ...near, delta_e: 4.2 }]);
    expect(count).toBe(1);
    expect(targets.map(t => t?.name ?? null)).toEqual(['Near', null]);
  });
  it('skips a colour that already is the shelf ink, or whose ink another colour prints', () => {
    const pal = [{ hex: '#515442' }, { hex: '#60614C' }];
    expect(planSwap(pal, [{ ...near, delta_e: 0 }, { ...near, delta_e: 4 }]).count).toBe(0);
  });
});

describe('swapPalette', () => {
  const pal: { hex: string; coverage: number; pixels: number; name?: string }[] = [{ hex: '#C0392B', coverage: 30, pixels: 300 }, { hex: '#1A1A1A', coverage: 50, pixels: 500 },
               { hex: '#BB3A2E', coverage: 20, pixels: 200 }];
  it('names swapped inks after the shelf ink', () => {
    const out = swapPalette(pal, [{ name: 'Lal', hex: '#c1392c', delta_e: 1 }, null, null]);
    expect(out[0]).toMatchObject({ hex: '#C1392C', name: 'Lal', coverage: 30 });
    expect(out[1].name).toBeUndefined();
  });

  it('folds inks that land on the same shelf ink into one', () => {
    const lal = { name: 'Lal', hex: '#C1392C', delta_e: 1 };
    const out = swapPalette(pal, [lal, null, lal]);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ hex: '#C1392C', name: 'Lal', coverage: 50, pixels: 500 });
  });
});

describe('inkOwner', () => {
  it('finds another palette entry printing the colour', () => {
    const pal = [{ hex: '#AA0000' }, { hex: '#00aa00' }];
    expect(inkOwner(pal, '#00AA00', 0)).toBe(1);
    expect(inkOwner(pal, '#00AA00', 1)).toBe(-1);
  });
});
