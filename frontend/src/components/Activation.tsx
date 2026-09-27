import { useState } from 'react';
import { post } from '../api';

export type LicenceStatus = { required: boolean; valid: boolean; machine: string; mill: string | null;
  expires: string | null; reason: string };

/** Shown instead of the app when this PC needs a licence: its machine code
 *  to send to the seller, and a box for the key they send back. */
export default function Activation({ status, onDone }: { status: LicenceStatus; onDone: (s: LicenceStatus) => void }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const activate = async () => {
    setBusy(true); setError('');
    try {
      onDone(await post<LicenceStatus>('/licence', { key: key.trim() }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  const copy = () => {
    navigator.clipboard?.writeText(status.machine).then(() => setCopied(true)).catch(() => { /* select it by hand */ });
  };

  return (
    <section className="activation">
      <h2>Activate LoomLab on this PC</h2>
      <p>{status.reason && !status.reason.startsWith('LoomLab is not activated') ? status.reason
        : 'Send this machine code to your LoomLab supplier. They send back a licence key for this PC.'}</p>
      <div className="machine">
        <code>{status.machine}</code>
        <button className="mini" onClick={copy}>{copied ? '✓ Copied' : 'Copy'}</button>
      </div>
      <label htmlFor="licence-key">Licence key</label>
      <textarea id="licence-key" rows={4} value={key} placeholder="LL1.…" spellCheck={false}
        onChange={e => { setKey(e.target.value); setError(''); }} />
      {error && <p className="warn">{error}</p>}
      <button className="primary" disabled={busy || key.trim().length < 10} onClick={activate}>
        {busy ? 'Checking…' : 'Activate'}</button>
    </section>
  );
}
