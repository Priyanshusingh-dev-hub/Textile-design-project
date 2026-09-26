import { useState } from 'react';
import { parseHex, quickPicks, type ColourSnapshot } from '../lib/recolour';

type Plate = { id: string; color: string; name: string; coverage: number; skip?: boolean };

type Props = {
  plates: Plate[];
  snapshot: ColourSnapshot;
  library: { name: string; hex: string }[];
  fabric: string;
  onColour: (id: string, hex: string, name?: string) => void;
  onFabric: (hex: string) => void;
  onReset: (id: string) => void;
  onDone: () => void;
  onCancel: () => void;
  changed: number;
};

/** Every plate's ink, changeable to any colour, with the preview following
 *  each change live. Nothing is sent to the engine until Done. */
export function PlateColours({ plates, snapshot, library, fabric, onColour, onFabric, onReset, onDone, onCancel, changed }: Props) {
  const [open, setOpen] = useState<string>();          // the plate whose quick picks are showing
  const [typed, setTyped] = useState<Record<string, string>>({});

  return (
    <div className="recolour">
      <div className="recolour-head">
        <h3>Plate colours</h3>
        <small>{changed ? `${changed} changed` : 'drag a colour — the preview follows'}</small>
      </div>
      <div className="recolour-cloth">
        <span>Cloth</span>
        <label className="rc-swatch" style={{ background: fabric }} title="Cloth colour">
          <input type="color" value={fabric.toLowerCase()} onChange={e => onFabric(e.target.value.toUpperCase())} />
        </label>
        <code>{fabric.toUpperCase()}</code>
      </div>
      <div className="recolour-list">
        {plates.map((p, i) => {
          const was = snapshot[p.id];
          const moved = was && was.color !== p.color.toUpperCase();
          const text = typed[p.id] ?? p.color.toUpperCase();
          return (
            <div className={'rc-row' + (p.skip ? ' off' : '')} key={p.id}>
              <span className="rc-n">{i + 1}</span>
              <label className="rc-swatch" style={{ background: p.color }} title="Pick any colour">
                <input type="color" value={p.color.toLowerCase()} aria-label={`Colour of plate ${i + 1}`}
                  onChange={e => { setTyped(t => ({ ...t, [p.id]: e.target.value.toUpperCase() })); onColour(p.id, e.target.value); }} />
              </label>
              <input className={'rc-hex' + (parseHex(text) ? '' : ' bad')} value={text} spellCheck={false} maxLength={7}
                aria-label={`Hex colour of plate ${i + 1}`}
                onChange={e => {
                  const v = e.target.value; setTyped(t => ({ ...t, [p.id]: v }));
                  const hex = parseHex(v); if (hex) onColour(p.id, hex);
                }}
                onBlur={() => setTyped(t => { const n = { ...t }; delete n[p.id]; return n; })} />
              <span className="rc-meta" title={p.name}>{p.name}<small>{p.coverage}%{p.skip ? ' · not printed' : ''}</small></span>
              <button className="mini" title="Other plates' colours and your shelf inks"
                onClick={() => setOpen(o => o === p.id ? undefined : p.id)}>{open === p.id ? '▴' : '▾'}</button>
              {moved
                ? <button className="mini" title={`Back to ${was.color}`} onClick={() => { onReset(p.id); setTyped(t => { const n = { ...t }; delete n[p.id]; return n; }); }}>↺</button>
                : <span className="rc-gap" />}
              {open === p.id && (
                <div className="rc-picks">
                  {quickPicks(plates, p.id, library).map(q => (
                    <button key={q.hex} className="rc-pick" style={{ background: q.hex }}
                      title={q.name ? `${q.name} ${q.hex}` : `${q.hex} (another plate's ink)`}
                      onClick={() => { setTyped(t => { const n = { ...t }; delete n[p.id]; return n; }); onColour(p.id, q.hex, q.name); }} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="muted rc-note">Only the ink colours change: the films stay exactly as separated. Plates, proof, job sheet and names follow when you press Done.</p>
      <div className="rc-actions">
        <button className="secondary" onClick={onCancel}>Cancel</button>
        <button className="primary" onClick={onDone}>Done{changed ? ` — keep ${changed} change${changed > 1 ? 's' : ''}` : ''}</button>
      </div>
    </div>
  );
}
