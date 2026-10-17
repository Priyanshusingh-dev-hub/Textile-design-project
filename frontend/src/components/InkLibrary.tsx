import { useEffect, useState } from 'react';
import type { LibraryInk } from '../lib/inks';

type Props = {
  inks: LibraryInk[];
  /** the current design's inks, to seed the library from */
  palette: { hex: string; name?: string }[];
  busy: boolean;
  parse: (text: string) => { inks: LibraryInk[]; errors: string[] };
  onSave: (inks: LibraryInk[]) => void;
  onClose: () => void;
};

/** "My inks": the inks the mill has mixed and on the shelf. Every change is
 *  saved straight away by the engine, so the list is there next time, on any
 *  browser on this PC. */
export function InkLibrary({ inks, palette, busy, parse, onSave, onClose }: Props) {
  const [name, setName] = useState('');
  const [hex, setHex] = useState('#C0392B');
  const [paste, setPaste] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  /** Add inks; one already on the list by the same name gets the new colour. */
  const addAll = (more: LibraryInk[]) => {
    const next = [...inks];
    for (const ink of more) {
      const at = next.findIndex(i => i.name.toLowerCase() === ink.name.toLowerCase());
      if (at >= 0) next[at] = ink; else next.push(ink);
    }
    onSave(next);
  };
  const addOne = () => {
    if (!name.trim()) return;
    addAll([{ name: name.trim(), hex: hex.toUpperCase() }]); setName('');
  };
  const addPasted = () => {
    const { inks: read, errors } = parse(paste);
    if (read.length) addAll(read);
    setNote(errors.length
      ? `Added ${read.length}. Couldn't read ${errors.length} line${errors.length > 1 ? 's' : ''} (each needs a name and a colour like #D96A8E): ${errors.slice(0, 3).join(' · ')}`
      : `Added ${read.length} ink${read.length !== 1 ? 's' : ''}.`);
    if (!errors.length) setPaste('');
  };
  const fromDesign = palette.filter(p => !inks.some(i => i.hex.toUpperCase() === p.hex.toUpperCase()));

  return (
    <div className="lib-backdrop" onClick={onClose}>
      <div className="lib-dialog" role="dialog" aria-modal="true" aria-labelledby="lib-title" onClick={e => e.stopPropagation()}>
        <div className="lib-head">
          <h3 id="lib-title">My inks <small>{inks.length} on the shelf</small></h3>
          <button className="mini" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="muted">The inks your mill already has. The palette shows the nearest one for each
          colour, and one click swaps to it — so you print with inks you have, and the films carry their names.</p>

        <div className="lib-list">
          {!inks.length && <p className="muted">No inks yet — add them below, or paste your list.</p>}
          {inks.map((ink, i) => (
            <div className="lib-row" key={ink.name + i}>
              <label className="lib-swatch" style={{ background: ink.hex }} title="Change colour">
                <input type="color" value={ink.hex.toLowerCase()} disabled={busy}
                  onChange={e => onSave(inks.map((x, k) => k === i ? { ...x, hex: e.target.value.toUpperCase() } : x))} />
              </label>
              <input className="lib-name" defaultValue={ink.name} maxLength={60} disabled={busy} aria-label="Ink name"
                onBlur={e => { const v = e.target.value.trim(); if (v && v !== ink.name) onSave(inks.map((x, k) => k === i ? { ...x, name: v } : x)); }} />
              <code>{ink.hex}</code>
              <button className="mini" disabled={busy} aria-label={`Remove ${ink.name}`}
                onClick={() => onSave(inks.filter((_, k) => k !== i))}>✕</button>
            </div>
          ))}
        </div>

        <div className="lib-add">
          <label className="lib-swatch" style={{ background: hex }} title="Pick the ink's colour">
            <input type="color" value={hex.toLowerCase()} onChange={e => setHex(e.target.value.toUpperCase())} />
          </label>
          <input className="lib-name" placeholder="Ink name, e.g. Rani Pink 12" value={name} maxLength={60}
            onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') addOne(); }} />
          <button className="mini go" disabled={busy || !name.trim()} onClick={addOne}>Add</button>
        </div>

        <details className="lib-paste">
          <summary>Paste a list</summary>
          <textarea rows={4} value={paste} onChange={e => setPaste(e.target.value)}
            placeholder={'One ink per line:\nRani Pink 12, #D96A8E\nNavy 3 #1E2A4A'} />
          <button className="mini go" disabled={busy || !paste.trim()} onClick={addPasted}>Add these</button>
        </details>
        {note && <p className="muted">{note}</p>}

        {!!fromDesign.length && (
          <button className="secondary wide" disabled={busy}
            onClick={() => addAll(fromDesign.map(p => ({ name: p.name ?? `New ink ${p.hex}`, hex: p.hex.toUpperCase() })))}>
            Add this design's {fromDesign.length} ink{fromDesign.length > 1 ? 's' : ''} to the shelf
          </button>
        )}
      </div>
    </div>
  );
}
