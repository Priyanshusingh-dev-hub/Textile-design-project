/** The job in progress, kept in this browser so a reload or a closed tab
 *  doesn't lose the operator's palette work. Only ids and settings are kept —
 *  the images themselves stay in the engine's working cache, which clears
 *  them after 48 hours, so an older job isn't offered. Pure, so it is tested. */

export const JOB_KEY = 'loomlab.job.v1';
/** A little under the engine's 48-hour cache, so the images are still there. */
export const JOB_MAX_AGE_MS = 47 * 3600 * 1000;

export type SavedJob<S> = { v: 1; savedAt: number; step: string; state: S };

export function packJob<S>(step: string, state: S, now: number): string {
  return JSON.stringify({ v: 1, savedAt: now, step, state } satisfies SavedJob<S>);
}

/** The saved job, or null when there is none, it is unreadable, from another
 *  version, too old for its images to still exist, or has no design. */
export function unpackJob<S extends { original?: { image_id?: string } }>(text: string | null, now: number): SavedJob<S> | null {
  if (!text) return null;
  try {
    const job = JSON.parse(text) as SavedJob<S>;
    if (!job || job.v !== 1 || typeof job.savedAt !== 'number' || typeof job.step !== 'string') return null;
    if (now - job.savedAt > JOB_MAX_AGE_MS || now < job.savedAt - 60_000) return null;
    if (!job.state?.original?.image_id) return null;
    return job;
  } catch { return null; }
}

/** "3 min ago", "2 h ago", "yesterday" — how long since the job was left. */
export function ago(ms: number): string {
  const min = Math.max(0, Math.round(ms / 60_000));
  if (min < 1) return 'just now';
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 24 ? `${h} h ago` : 'yesterday';
}

/** One line for the "continue your last job" card. */
export function jobSummary(job: { step: string; savedAt: number;
  state: { original?: { file_name?: string }; palette?: unknown[]; layers?: { skip?: boolean }[] } }, now: number): string {
  const name = job.state.original?.file_name || 'design';
  const plates = job.state.layers?.filter(l => !l.skip).length ?? 0;
  const inks = job.state.palette?.length ?? 0;
  const where = plates ? `${plates} plates` : inks ? `${inks} inks` : 'not reduced yet';
  return `${name} · ${where} · at ${job.step} · ${ago(now - job.savedAt)}`;
}
