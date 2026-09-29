import { useCallback, useRef, useState } from 'react';

export type AsyncState = 'idle' | 'processing' | 'done' | 'failed';
export type ActionStatus = { state: AsyncState; message?: string; label?: string };

const DONE_LINGER_MS = 1800;

/** Every piece of work in flight — an operator's click and the previews the
 *  page redraws on its own share one status. It stays "processing" until the
 *  LAST one ends: a quick preview finishing first must not unlock the
 *  Download button while a package is still being built. An error during
 *  that time is what is shown when everything has ended. */
export class Work {
  private running = new Map<number, string | undefined>();
  private seq = 0;
  private error?: string;

  start(label?: string): [number, ActionStatus] {
    const id = ++this.seq;
    if (!this.running.size) this.error = undefined;
    this.running.set(id, label);
    return [id, this.status()];
  }

  end(id: number, error?: string): ActionStatus {
    this.running.delete(id);
    if (error) this.error = error;
    return this.status();
  }

  status(): ActionStatus {
    if (this.running.size) {
      const labels = [...this.running.values()].filter(Boolean);
      return { state: 'processing', label: labels[labels.length - 1] };   // the newest named action
    }
    return this.error ? { state: 'failed', message: this.error } : { state: 'done' };
  }
}

export function useAsyncStatus() {
  const [status, setStatus] = useState<ActionStatus>({ state: 'idle' });
  const work = useRef(new Work());
  const revertTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  /** `label` names the work in progress (e.g. "Reducing…"), so a button can say
   * what it is doing. Reducing or exporting a mill-sized design takes seconds;
   * without that, an operator thinks it hung and clicks again. */
  const run = useCallback(async (fn: () => Promise<void>, label?: string) => {
    clearTimeout(revertTimer.current);
    const [id, started] = work.current.start(label);
    setStatus(started);
    let error: string | undefined;
    try {
      await fn();
    } catch (e: any) {
      error = e?.message || 'Processing failed.';
    }
    const next = work.current.end(id, error);
    setStatus(next);
    if (next.state === 'done') revertTimer.current = setTimeout(() => setStatus({ state: 'idle' }), DONE_LINGER_MS);
  }, []);

  return { status, run, busy: status.state === 'processing', busyLabel: status.label };
}
