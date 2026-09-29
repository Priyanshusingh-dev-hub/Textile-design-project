import { describe, expect, it } from 'vitest';
import { ago, counts, filterJobs, needsAttention, statTiles, type JobRow, type Stats } from './jobs';
import { money } from './print';
import { translate } from './i18n';

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


describe('the month at a glance', () => {
  const s: Stats = { days: 30, designs: 40, jobs: 46, auto_ok: 26, needs_review: 14, auto_ok_percent: 65,
    stages: { approved: 20, rejected: 2, new: 18 }, avg_seconds: 21, quoted: 325000, meters: 12000, currency: '₹',
    hours_saved: 35.3, money_saved: 7060,
    estimate: { manual_minutes_per_design: 60, review_minutes_per_design: 10, staff_cost_per_hour: 200 } };

  it('says how much went through with nobody, and what it saved', () => {
    const t = statTiles(s, money);
    expect(t.map(x => x[0])).toEqual(['Designs', 'Needed nobody', 'Approved', 'Quoted', 'Time saved']);
    expect(t[0][2]).toBe('last 30 days · 46 runs');
    expect(t[1][1]).toBe('65%');
    expect(t[3][1]).toBe('₹3,25,000');
    expect(t[4][2]).toMatch(/estimate: 60 min by hand/);
  });

  it('counts repeat orders, and speaks Hinglish when asked', () => {
    const r = statTiles({ ...s, repeat_orders: 3, repeat_meters: 2400, repeat_quoted: 180000 }, money,
      (text, vars) => translate('hi', text, vars));
    expect(r.map(x => x[0])).toEqual(['Designs', 'Needed nobody', 'Approved', 'Quoted', 'Repeat orders', 'Time saved']);
    expect(r[4]).toEqual(['Repeat orders', '3', '2,400 m · ₹1,80,000 · nayi screen nahi']);
    expect(r[0][2]).toBe('pichhle 30 din · 46 baar chala');
    expect(r[5][2]).toMatch(/^≈ ₹7,060 · andaaza: haath se 60 min/);
  });

  it('shows nothing before the first job', () => {
    expect(statTiles({ ...s, designs: 0, jobs: 0 }, money)).toEqual([]);
  });
});
