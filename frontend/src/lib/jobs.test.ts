import { describe, expect, it } from 'vitest';
import { ago, counts, filterJobs, needsAttention, type JobRow } from './jobs';

const job = (over: Partial<JobRow>): JobRow => ({
  job_id: 'x', name: 'd.png', client: '', created_at: '2026-09-27T10:00:00', status: 'auto_ok', stage: 'new',
  accuracy: 90, inks: 4, print: { width_in: 30, height_in: 22 }, reduced_id: 'r', package_url: '/p',
  warnings: [], notes: [], total: null, meters: null, currency: null, last: null, ...over });

describe('job dashboard', () => {
  const jobs = [job({ job_id: 'a', status: 'needs_review' }), job({ job_id: 'b', status: 'needs_review', stage: 'rejected' }),
    job({ job_id: 'c', stage: 'sent' }), job({ job_id: 'd', stage: 'approved' })];
  it('asks for a person only on held jobs nobody has touched', () => {
    expect(jobs.filter(needsAttention).map(j => j.job_id)).toEqual(['a']);
  });
  it('filters open and finished jobs', () => {
    expect(filterJobs(jobs, 'open').map(j => j.job_id)).toEqual(['a', 'c']);
    expect(filterJobs(jobs, 'done').map(j => j.job_id)).toEqual(['b', 'd']);
    expect(counts(jobs)).toEqual({ attention: 1, open: 2, done: 2, all: 4 });
  });
  it('says how long ago', () => {
    const t = new Date('2026-09-27T10:00:00').getTime();
    expect(ago('2026-09-27T10:00:00', t + 20_000)).toBe('just now');
    expect(ago('2026-09-27T10:00:00', t + 5 * 60_000)).toBe('5 min ago');
    expect(ago('2026-09-27T10:00:00', t + 3 * 3600_000)).toBe('3 h ago');
    expect(ago('2026-09-27T10:00:00', t + 2 * 86400_000)).toBe('2 days ago');
    expect(ago('', t)).toBe('');                 // no time known: say nothing
    expect(ago('not a date', t)).toBe('');
  });
});
