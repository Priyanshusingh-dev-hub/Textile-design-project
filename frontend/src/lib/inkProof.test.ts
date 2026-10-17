import { describe, expect, it } from 'vitest';
import { blend, inkProof, inkProofOnBase, underbaseAlpha } from './inkProof';

describe('inkProof (screens at real coverage, linear blend)', () => {
  it('a hard screen is the ink itself and no ink is the cloth', () => {
    const px = inkProof([[255, 0]], ['#C0392B'], '#16202E', 2);
    expect(Array.from(px)).toEqual([0xC0, 0x39, 0x2B, 255, 0x16, 0x20, 0x2E, 255]);
  });

  it('a 50% tint is halfway between cloth and ink (R-0009 test 2, within 2)', () => {
    const [r, g, b] = inkProof([[128]], ['#C0392B'], '#FFFFFF', 1);
    const half = [(255 + 0xC0) / 2, (255 + 0x39) / 2, (255 + 0x2B) / 2];
    [r, g, b].forEach((v, j) => expect(Math.abs(v - half[j])).toBeLessThanOrEqual(2));
    expect(Array.from(inkProof([[128]], ['#000000'], '#FFFFFF', 1)).slice(0, 3)).toEqual([127, 127, 127]);
  });

  it('blend is exactly round(((255 - a) * p + a * c) / 255) for every input', () => {
    for (let a = 0; a < 256; a += 3) for (let p = 0; p < 256; p += 5) for (let c = 0; c < 256; c += 7)
      expect(blend(p, c, a)).toBe(Math.round(((255 - a) * p + a * c) / 255));
  });

  it('gives the backend proof pixel for pixel (two screens, tints both ways, coloured cloth)', () => {
    // ink_proof.proof([(a, #FFD400), (reversed a, #1E2A4A)], cloth #C0392B), printed by the backend
    const a = [0, 1, 2, 60, 64, 127, 128, 200, 254, 255];
    const px = inkProof([a, [...a].reverse()], ['#FFD400', '#1E2A4A'], '#C0392B', a.length);
    const want = [30, 42, 74, 31, 42, 74, 65, 45, 67, 118, 67, 54, 119, 69, 53, 175, 111, 35, 178, 113, 33,
                  239, 178, 10, 254, 210, 0, 255, 212, 0];
    expect(Array.from(px).filter((_, i) => i % 4 !== 3)).toEqual(want);
  });

  it('a hidden screen (null colour) is not printed', () => {
    const px = inkProof([[200]], [null], '#FFFFFF', 1);
    expect(Array.from(px)).toEqual([255, 255, 255, 255]);
  });

  it('two overlapping screens composite in order with no jump at alpha 1', () => {
    const a = [0, 1, 2, 64, 128];
    const one = inkProof([a, a], ['#FFFF00', '#0000FF'], '#FFFFFF', a.length);
    // red falls smoothly from the cloth's 255: never straight to the ink at alpha 1
    expect(one[4]).toBeGreaterThan(250);
    for (let i = 1; i < a.length; i++) expect(one[i * 4]).toBeLessThanOrEqual(one[(i - 1) * 4]);
  });
});

describe('inkProofOnBase (white under-base on dark cloth, R-0023)', () => {
  it('a tint sits on white where the base is on; bare cloth stays the cloth', () => {
    const a = [0, 128, 64, 255];
    const px = inkProofOnBase([a], ['#C0392B'], '#1E2A4A', a.length, true);
    expect(Array.from(px.slice(0, 3))).toEqual([0x1E, 0x2A, 0x4A]);
    const half = [(255 + 0xC0) / 2, (255 + 0x39) / 2, (255 + 0x2B) / 2];
    [0, 1, 2].forEach(j => expect(Math.abs(px[4 + j] - half[j])).toBeLessThanOrEqual(2));
    const quarter = [0.75 * 255 + 0.25 * 0xC0, 0.75 * 255 + 0.25 * 0x39, 0.75 * 255 + 0.25 * 0x2B];
    [0, 1, 2].forEach(j => expect(Math.abs(px[8 + j] - quarter[j])).toBeLessThanOrEqual(2));
    expect(Array.from(px.slice(12, 15))).toEqual([0xC0, 0x39, 0x2B]);
  });

  it('without a base it is inkProof, and a hard screen is the same either way', () => {
    const a = [0, 255, 255, 0];
    expect(Array.from(inkProofOnBase([a], ['#C0392B'], '#1E2A4A', 4, false)))
      .toEqual(Array.from(inkProof([a], ['#C0392B'], '#1E2A4A', 4)));
    expect(Array.from(inkProofOnBase([a], ['#C0392B'], '#1E2A4A', 4, true)))
      .toEqual(Array.from(inkProof([a], ['#C0392B'], '#1E2A4A', 4)));
  });

  it('the base is the union of the printed screens only', () => {
    expect(Array.from(underbaseAlpha([[0, 9, 0], [0, 0, 200]], ['#000000', null], 3))).toEqual([0, 255, 0]);
  });
});
