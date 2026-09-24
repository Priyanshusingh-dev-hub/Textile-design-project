import { describe, it, expect } from 'vitest';
import { luminance, isDarkCloth, matchVerdict, tinyInks, softEdgeNote, printSize, separationNote, printAt, printWidthNote, colourDistance, groundSuggestion, SAME_AS_CLOTH, mergeSuggestion } from './print';

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

describe('printAt', () => {
  it("is the design's own size when no width is chosen", () => {
    const at = printAt(1254, 1254)!;
    expect(at.resized).toBe(false);
    expect(at.px).toEqual([1254, 1254]);
    expect(at.inches).toEqual([4.18, 4.18]);
  });

  it("follows a chosen width in the design's proportions", () => {
    const at = printAt(1254, 836, 12)!;
    expect(at.px).toEqual([3600, 2400]);
    expect(at.inches).toEqual([12, 8]);
    expect(at.scale).toBeCloseTo(2.87, 2);
    expect(at.sourcePpi).toBe(105);
    expect(at.label).toContain('305 × 203 mm');
  });

  it("treats the design's own width as untouched", () => {
    expect(printAt(1254, 1254, 1254 / 300)!.resized).toBe(false);
  });

  it('knows the largest width the engine will render', () => {
    const at = printAt(1000, 1000, 40)!;           // 12000 x 12000 px = 144 MP
    expect(at.tooLarge).toBe(true);
    expect(at.maxIn).toBe(27.8);
    expect(printAt(1000, 1000, 27.8)!.tooLarge).toBe(false);
  });
});

describe('printWidthNote', () => {
  it('points a tiny design at the print-width box', () => {
    const n = printWidthNote(720, 720)!;
    expect(n.tone).toBe('warn');
    expect(n.text).toMatch(/Set a larger print width/);
  });

  it('stays quiet at an ordinary own size', () => {
    expect(printWidthNote(3600, 3000)).toBeNull();
    expect(printWidthNote(900, 900)).toBeNull();   // 3 in, exactly the threshold
  });

  it('says what enlarging does, and what it cannot', () => {
    const n = printWidthNote(1254, 1254, 12)!;
    expect(n.tone).toBe('hint');
    expect(n.text).toMatch(/2\.9×/);
    expect(n.text).toMatch(/smooth edges/);
    expect(n.text).toMatch(/can't be added/);
  });

  it('warns when the file is stretched very thin', () => {
    const n = printWidthNote(500, 500, 12)!;           // 42 px per inch
    expect(n.tone).toBe('warn');
    expect(n.text).toMatch(/42 pixels of the file per inch/);
  });

  it('warns before the engine would refuse', () => {
    expect(printWidthNote(1000, 1000, 40)!.text).toMatch(/up to 27.8 in/);
  });

  it('warns that shrinking can break thin lines', () => {
    expect(printWidthNote(3000, 3000, 5)!.text).toMatch(/Reduced to 50%/);
  });
});

describe('separationNote', () => {
  it('promises one ink per pixel only for a design LoomLab separated', () => {
    expect(separationNote(false)).toMatch(/exactly one plate/);
    expect(separationNote(true, 0)).not.toMatch(/exactly one plate/);
  });

  it('says a PSD was left as the bureau separated it', () => {
    expect(separationNote(true, 0)).toMatch(/exactly as it was separated/);
    expect(separationNote(true, 0)).toMatch(/No two screens/);
  });

  it('reports deliberate overlap instead of hiding it', () => {
    const t = separationNote(true, 3.25);
    expect(t).toContain('3.3%');
    expect(t).toMatch(/trapping/);
    expect(separationNote(true, 0.04)).toContain('Under 0.1%');
  });
});

describe('colourDistance', () => {
  it('is zero for the same colour and large for opposites', () => {
    expect(colourDistance('#D4C1A7', '#d4c1a7')).toBeCloseTo(0, 5);
    expect(colourDistance('#000000', '#FFFFFF')).toBeCloseTo(100, 0);
  });
  it('sees a near-miss cloth as the same colour', () => {
    expect(colourDistance('#D4C1A7', '#D6C3A9')).toBeLessThan(SAME_AS_CLOTH);
    expect(colourDistance('#D4C1A7', '#FFFFFF')).toBeGreaterThan(SAME_AS_CLOTH);
  });
});

describe('groundSuggestion', () => {
  const floral = [
    { color: '#D4C1A7', coverage: 46, edge: 58.2 },     // cream ground
    { color: '#525542', coverage: 10.5, edge: 12.3 },
    { color: '#CFB594', coverage: 9.1, edge: 4.8 },
  ];

  it('offers to print on cloth of the ground colour', () => {
    const g = groundSuggestion(floral, '#FFFFFF')!;
    expect(g.ink.color).toBe('#D4C1A7');
    expect(g.matches).toBe(false);
  });

  it('only asks to hide it when the cloth is already that colour', () => {
    expect(groundSuggestion(floral, '#D4C1A7')!.matches).toBe(true);
  });

  it('goes quiet once the ground is hidden', () => {
    expect(groundSuggestion([{ ...floral[0], skip: true }, ...floral.slice(1)], '#D4C1A7')).toBeNull();
  });

  it('never calls a big motif on a transparent ground a ground', () => {
    expect(groundSuggestion([{ color: '#C0392B', coverage: 53.7, edge: 0 }], '#FFFFFF')).toBeNull();
  });

  it('ignores a sliver that happens to run along the edge', () => {
    expect(groundSuggestion([{ color: '#C0392B', coverage: 4, edge: 90 }], '#FFFFFF')).toBeNull();
  });
});

describe('mergeSuggestion', () => {
  const pairs = [{ keep: 0, drop: 2, delta_e: 3.9, accuracy: 90.9 }, { keep: 6, drop: 8, delta_e: 4.0, accuracy: 91.2 }];
  const palette = Array.from({ length: 10 }, () => ({ locked: false }));

  it('offers the closest pair', () => {
    expect(mergeSuggestion(pairs, palette)).toEqual(pairs[0]);
  });

  it('never merges away an ink the operator locked', () => {
    const locked = palette.map((p, i) => ({ locked: i === 2 }));
    expect(mergeSuggestion(pairs, locked)).toEqual(pairs[1]);
  });

  it('offers nothing when there is nothing close', () => {
    expect(mergeSuggestion([], palette)).toBeNull();
    expect(mergeSuggestion(undefined, palette)).toBeNull();
  });

  it('ignores a pair that no longer fits the palette', () => {
    expect(mergeSuggestion([{ keep: 0, drop: 12, delta_e: 2, accuracy: 90 }], palette)).toBeNull();
  });
});
