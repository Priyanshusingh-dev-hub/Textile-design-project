import { useCallback, useRef, useState } from 'react';

export type AsyncState = 'idle' | 'processing' | 'done' | 'failed';
export type ActionStatus = { state: AsyncState; message?: string };

const DONE_LINGER_MS = 1800;

export function useAsyncStatus() {
  const [status, setStatus] = useState<ActionStatus>({ state: 'idle' });
  const revertTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const run = useCallback(async (fn: () => Promise<void>) => {
    clearTimeout(revertTimer.current);
    setStatus({ state: 'processing' });
    try {
      await fn();
      setStatus({ state: 'done' });
      revertTimer.current = setTimeout(() => setStatus({ state: 'idle' }), DONE_LINGER_MS);
    } catch (e: any) {
      setStatus({ state: 'failed', message: e.message || 'Processing failed.' });
    }
  }, []);

  return { status, run, busy: status.state === 'processing' };
}
