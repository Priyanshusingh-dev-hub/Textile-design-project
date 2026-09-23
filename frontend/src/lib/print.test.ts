import { describe, it, expect } from 'vitest';
import { luminance, isDarkCloth, matchVerdict, tinyInks } from './print';

describe('cloth colour', () => {
  it('reads white as light and black as dark', () => {
    expect(isDarkCloth('#FFFFFF')).toBe(false);
    expect(isDarkCloth('#000000')).toBe(true);
  });

  it('treats the real mill cloths correctly', () => {
    expect(isDarkCloth('#EDE3CC')).toBe(false);   // natural/ecru
    expect(isDarkCloth('#1B2A1F')).toBe(true);    // bottle green
    expect(isDarkCloth('#16202E')).toBe(true);    // navy
  });

  it('accepts a hex with or without the hash', () => {
    expect(luminance('#FFFFFF')).toBeCloseTo(1, 5);
    expect(luminance('FFFFFF')).toBeCloseTo(1, 5);
  });

  it('weights green most, as human vision does', () => {
    expect(luminance('#00FF00')).toBeGreaterThan(luminance('#FF0000'));
    expect(luminance('#FF0000')).toBeGreaterThan(luminance('#0000FF'));
  });
});

describe('match verdict', () => {
  const goodCurve = [{ colors: 4, accuracy: 88 }, { colors: 14, accuracy: 97 }];
  const toneCurve = [{ colors: 4, accuracy: 60 }, { colors: 14, accuracy: 66 }];

  it('stays quiet when the match is good', () => {
    expect(matchVerdict(96, goodCurve)).toBeNull();
    expect(matchVerdict(90, goodCurve)).toBeNull();     // boundary
  });

  it('says nothing when there is no measurement yet', () => {
    expect(matchVerdict(undefined, goodCurve)).toBeNull();
  });

  it('warns that a continuous-tone design cannot be reproduced flat', () => {
    const v = matchVerdict(63, toneCurve);
    expect(v?.tone).toBe('warn');
    expect(v?.text).toMatch(/photographic shading/);
    expect(v?.text).toMatch(/66%/);                      // quotes the real ceiling
  });

  it('does NOT blame the design when more inks would in fact help', () => {
    const v = matchVerdict(80, goodCurve, 14, 4);
    expect(v?.tone).toBe('hint');
    expect(v?.text).toMatch(/try 14 inks/);
    expect(v?.text).not.toMatch(/photographic/);
  });

  it('suggests more inks generically when already at the suggestion', () => {
    expect(matchVerdict(80, goodCurve, 6, 6)?.text).toMatch(/more inks will tighten it/);
  });

  it('falls back to a hint when no curve was measured', () => {
    expect(matchVerdict(70, [])?.tone).toBe('hint');
  });

  it('leaves the awkward 85-90 band unremarked', () => {
    expect(matchVerdict(87, goodCurve)).toBeNull();
  });
});

describe('negligible inks', () => {
  it('flags only inks that waste a whole screen', () => {
    const inks = [{ coverage: 50 }, { coverage: 0.04 }, { coverage: 0.5 }, { coverage: 0.2 }];
    expect(tinyInks(inks)).toEqual([{ coverage: 0.04 }, { coverage: 0.2 }]);
  });

  it('is empty when every ink earns its screen', () => {
    expect(tinyInks([{ coverage: 12 }, { coverage: 3 }])).toEqual([]);
  });
});
