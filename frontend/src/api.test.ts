import { describe, it, expect } from 'vitest';
import { errorText } from './api';

describe('API error messages', () => {
  it('passes our own plain-string detail straight through', () => {
    expect(errorText('This image is no longer available. Please import it again.', 'x'))
      .toMatch(/no longer available/);
  });

  it('renders a FastAPI validation array instead of [object Object]', () => {
    const detail = [{ loc: ['body', 'palette', 0], msg: 'String should match pattern', type: 'string_pattern_mismatch' }];
    const out = errorText(detail, 'fallback');
    expect(out).toBe('String should match pattern (palette.0)');
    expect(out).not.toMatch(/object Object/);
  });

  it('drops the noisy "body" prefix from the field path', () => {
    expect(errorText([{ loc: ['body', 'colors'], msg: 'Input should be <= 20' }], 'x'))
      .toBe('Input should be <= 20 (colors)');
  });

  it('still reads well when there is no field path', () => {
    expect(errorText([{ msg: 'Something went wrong' }], 'x')).toBe('Something went wrong');
  });

  it('falls back when the body is empty, null or an unexpected shape', () => {
    expect(errorText(undefined, 'Export failed.')).toBe('Export failed.');
    expect(errorText(null, 'Export failed.')).toBe('Export failed.');
    expect(errorText('', 'Export failed.')).toBe('Export failed.');
    expect(errorText([], 'Export failed.')).toBe('Export failed.');
    expect(errorText({ unexpected: true }, 'Export failed.')).toBe('Export failed.');
  });
});
