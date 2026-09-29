/** The job dashboard's pure logic: which jobs need a person, and how to say
 *  where each one stands. Kept out of the component so it is testable. */

export type JobWarning = { code: string; message: string };
export type JobRow = {
  job_id: string; name: string; client: string; created_at: string;
  status: 'auto_ok' | 'needs_review'; stage: Stage; accuracy: number; inks: number;
  print: { width_in: number; height_in: number }; reduced_id: string; package_url: string;
  warnings: JobWarning[]; notes: string[]; total: number | null; meters: number | null; currency: string | null;
  last: { stage: string; by: string; note: string; at: string } | null;
};
export type Stage = 'new' | 'reviewed' | 'sent' | 'approved' | 'rejected' | 'changed';
export type JobFilter = 'attention' | 'open' | 'done' | 'all';

export const STAGE_LABEL: Record<Stage, string> = {
  new: 'New', reviewed: 'Checked', sent: 'With client', approved: 'Approved', rejected: 'Stopped', changed: 'Changed',
};

export const WARN_LABEL: Record<string, string> = {
  photographic: 'photo-like shading', low_match: 'low match', soft_edges: 'soft edges', tiny_dots: 'tiny dots',
  similar_inks: 'near-duplicate inks', many_inks: 'many screens', low_resolution: 'file too small for the size',
  grainy_source: 'grainy file', seamless_repeat: 'seamless repeat', small_inks: 'inks under 2%',
};

/** A job waits for a person when auto mode held it and nobody has acted yet. */
export const needsAttention = (j: JobRow) => j.status === 'needs_review' && j.stage === 'new';
const finished = (j: JobRow) => j.stage === 'approved' || j.stage === 'rejected';

export function filterJobs(jobs: JobRow[], f: JobFilter): JobRow[] {
  if (f === 'attention') return jobs.filter(needsAttention);
  if (f === 'open') return jobs.filter(j => !finished(j));
  if (f === 'done') return jobs.filter(finished);
  return jobs;
}

export function counts(jobs: JobRow[]): Record<JobFilter, number> {
  return { attention: filterJobs(jobs, 'attention').length, open: filterJobs(jobs, 'open').length,
    done: filterJobs(jobs, 'done').length, all: jobs.length };
}

/** "just now", "5 min ago", "3 h ago", "2 days ago". */
export function ago(iso: string, now = Date.now()): string {
  const t = new Date(iso).getTime();
  if (!iso || Number.isNaN(t)) return '';
  const s = Math.max(0, (now - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return `${d} day${d > 1 ? 's' : ''} ago`;
}
