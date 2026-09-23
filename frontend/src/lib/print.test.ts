import { describe, it, expect } from 'vitest';
import { luminance, isDarkCloth, matchVerdict, tinyInks, softEdgeNote, printSize, printSizeNote } from './print';

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

describe('softEdgeNote', () => {
  it('stays quiet for ordinary anti-aliasing', () => {
    // measured across 64px icons, 600px discs and dense linework: all ~3-3.6px
    for (const w of [0, 2.98, 3.48, 3.63, 6]) expect(softEdgeNote(w)).toBeNull();
  });

  it('stays quiet when the design is fully opaque', () => {
    expect(softEdgeNote(0)).toBeNull();
    expect(softEdgeNote(undefined)).toBeNull();
  });

  it('warns on a feathered edge and says what will happen', () => {
    const note = softEdgeNote(47.17);
    expect(note).toContain('47px');
    expect(note).toMatch(/hard cut/);
  });

  it('warns from just past the threshold', () => {
    expect(softEdgeNote(12.32)).not.toBeNull();
  });
});

describe('printSize', () => {
  it('converts pixels to the size the design actually prints', () => {
    const s = printSize(1254, 1254, 300)!;
    expect(s.inches).toEqual([4.2, 4.2]);
    expect(s.mm).toEqual([106, 106]);
    expect(s.label).toContain('4.2 × 4.2 in');
  });

  it('handles a non-square design', () => {
    expect(printSize(3600, 1800, 300)!.inches).toEqual([12, 6]);
  });

  it('returns nothing without dimensions', () => {
    expect(printSize(undefined, 100)).toBeNull();
    expect(printSize(100, 0)).toBeNull();
    expect(printSize(100, 100, 0)).toBeNull();
  });
});

describe('printSizeNote', () => {
  it('warns when the design is genuinely too small to use', () => {
    const note = printSizeNote(720, 720, 300)!;          // 2.4 in
    expect(note).toContain('2.4 × 2.4 in');
    expect(note).toMatch(/soften/);
  });

  it('stays quiet at sizes a mill actually prints', () => {
    expect(printSizeNote(3600, 3000, 300)).toBeNull();   // 12 x 10 in placement print
    expect(printSizeNote(1254, 1254, 300)).toBeNull();   // 4.2 in — an ordinary repeat
    expect(printSizeNote(900, 900, 300)).toBeNull();     // 3 in, exactly the threshold
  });
});
