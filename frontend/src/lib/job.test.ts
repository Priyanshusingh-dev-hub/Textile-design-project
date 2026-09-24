import { describe, expect, it } from 'vitest';
import { ago, JOB_MAX_AGE_MS, jobSummary, packJob, unpackJob } from './job';

const state = { original: { image_id: 'a'.repeat(32), file_name: 'floral.png' }, palette: [1, 2, 3], layers: [] };

describe('saved job', () => {
  it('round-trips', () => {
    const job = unpackJob<typeof state>(packJob('Reduce', state, 1000), 2000);
    expect(job?.step).toBe('Reduce');
    expect(job?.state.palette).toHaveLength(3);
  });
  it('is dropped when too old for the engine to still have its images', () => {
    expect(unpackJob(packJob('Reduce', state, 0), JOB_MAX_AGE_MS + 1)).toBeNull();
  });
  it('is dropped when unreadable, another version, or without a design', () => {
    expect(unpackJob(null, 0)).toBeNull();
    expect(unpackJob('{not json', 0)).toBeNull();
    expect(unpackJob(JSON.stringify({ v: 2, savedAt: 0, step: 'Reduce', state }), 0)).toBeNull();
    expect(unpackJob(packJob('Upload', { original: {} }, 0), 0)).toBeNull();
  });
});

describe('jobSummary', () => {
  it('says where the job was left', () => {
    const now = 10 * 60_000;
    expect(jobSummary({ step: 'Reduce', savedAt: 0, state }, now)).toBe('floral.png · 3 inks · at Reduce · 10 min ago');
    expect(jobSummary({ step: 'Export', savedAt: now, state: { ...state, layers: [{}, { skip: true }, {}] } }, now))
      .toBe('floral.png · 2 plates · at Export · just now');
  });
  it('reads time in words', () => {
    expect(ago(3 * 3600_000)).toBe('3 h ago');
    expect(ago(30 * 3600_000)).toBe('yesterday');
  });
});
