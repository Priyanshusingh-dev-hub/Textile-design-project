import { describe, expect, it } from 'vitest';
import { HI, translate } from './i18n';

describe('the app in Hinglish', () => {
  it('translates, and falls back to English for anything not in the list', () => {
    expect(translate('hi', 'Choose file')).toBe('File chuno');
    expect(translate('en', 'Choose file')).toBe('Choose file');
    expect(translate('hi', 'A label nobody translated')).toBe('A label nobody translated');
  });

  it('puts the values in, in either language', () => {
    expect(translate('hi', '{n}% match', { n: 88 })).toBe('88% milaan');
    expect(translate('en', 'My inks ({n})', { n: 3 })).toBe('My inks (3)');
  });

  it('keeps every {value} of the English in the Hinglish', () => {
    const marks = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(',');
    for (const [en, hi] of Object.entries(HI)) expect([en, marks(hi)]).toEqual([en, marks(en)]);
  });
});

describe('messages with their numbers already in', () => {
  it('are found by their template and keep the numbers', () => {
    expect(translate('hi', 'Reduced to 7 inks — 88% match (ΔE2000 2.99). Fine-tune the palette or continue.'))
      .toBe('7 inks me ho gaya — 88% milaan (ΔE2000 2.99). Rang theek karo ya aage badho.');
    expect(translate('hi', '7,186 dots under 0.2 mm on 7 screens: too small for the mesh to hold, they print as nothing or as dirt. Clean them here.'))
      .toMatch(/^7 screens par 0.2 mm se chhoti 7,186 bindiyan/);
    expect(translate('hi', 'Imported rose (1).png (1448×1086). Choose an ink count and reduce.'))
      .toBe('Design aa gaya: rose (1).png (1448×1086). Kitni inks chahiye chuno aur rang kam karo.');
  });

  it('an optional tail may be empty', () => {
    const base = "Enlarged 2.5×: every screen is redrawn at this size with smooth edges, still one ink per pixel. Detail finer than the file itself — fine texture, tiny dots — can't be added, so it stays as it is in the file.";
    expect(translate('hi', base)).toMatch(/^2.5× bada kiya/);
  });

  it('leaves English alone, and unknown messages as they are', () => {
    const msg = 'Reduced to 7 inks — 88% match (ΔE2000 2.99). Fine-tune the palette or continue.';
    expect(translate('en', msg)).toBe(msg);
    expect(translate('hi', 'Something new happened.')).toBe('Something new happened.');
  });
});
