import { useCallback, useRef, useState } from 'react';

export type AsyncState = 'idle' | 'processing' | 'done' | 'failed';
export type ActionStatus = { state: AsyncState; message?: string; label?: string };

const DONE_LINGER_MS = 1800;

export function useAsyncStatus() {
  const [status, setStatus] = useState<ActionStatus>({ state: 'idle' });
  const revertTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  /** `label` names the work in progress (e.g. "Reducing…"), so a button can say
   * what it is doing. Reducing or exporting a mill-sized design takes seconds;
   * without that, an operator thinks it hung and clicks again. */
  const run = useCallback(async (fn: () => Promise<void>, label?: string) => {
    clearTimeout(revertTimer.current);
    setStatus({ state: 'processing', label });
    try {
      await fn();
      setStatus({ state: 'done' });
      revertTimer.current = setTimeout(() => setStatus({ state: 'idle' }), DONE_LINGER_MS);
    } catch (e: any) {
      setStatus({ state: 'failed', message: e.message || 'Processing failed.' });
    }
  }, []);

  return { status, run, busy: status.state === 'processing', busyLabel: status.label };
}
