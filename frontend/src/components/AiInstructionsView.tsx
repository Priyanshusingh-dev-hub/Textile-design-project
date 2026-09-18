import { useState } from 'react';
import { Sparkles, Copy, Check, Search } from 'lucide-react';
import type { DesignDna, Intent, ImageInfo } from '../types';

const INTENTS: { value: Intent; label: string; hint: string }[] = [
  { value: 'exact_recreation', label: 'Exact recreation', hint: 'Keep it as close to the reference as possible' },
  { value: 'premium_improvement', label: 'Premium improvement', hint: 'Same identity, better quality' },
  { value: 'color_change', label: 'Color change', hint: 'Keep motifs, change the palette' },
  { value: 'new_variation', label: 'New variation', hint: 'Same motifs, fresh arrangement' },
  { value: 'same_style_new', label: 'Same style — new design', hint: 'A new design in the same language' },
  { value: 'print_optimization', label: 'Print optimization', hint: 'Tune for clean color separation' },
];

function fidelityLabel(f: number) {
  if (f >= 90) return 'Near recreation';
  if (f >= 75) return 'Very close variation';
  if (f >= 50) return 'Strong variation';
  if (f >= 20) return 'Style reference';
  return 'Loose inspiration';
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard blocked */ }
    setDone(true); setTimeout(() => setDone(false), 1500);
  };
  return <button className="primary" onClick={copy} disabled={!text}>{done ? <Check size={15} /> : <Copy size={15} />} {done ? 'Copied' : label}</button>;
}

export function AiInstructionsView({
  img, dna, brief, instruction, setInstruction, intent, setIntent, fidelity, setFidelity,
  userRequest, setUserRequest, description, setDescription, onAnalyze, onGenerate, busy,
}: {
  img?: ImageInfo; dna?: DesignDna; brief: string; instruction: string; setInstruction: (s: string) => void;
  intent: Intent; setIntent: (i: Intent) => void; fidelity: number; setFidelity: (n: number) => void;
  userRequest: string; setUserRequest: (s: string) => void; description: string; setDescription: (s: string) => void;
  onAnalyze: () => void; onGenerate: () => void; busy: boolean;
}) {
  if (!img) {
    return <main><div className="canvas empty"><div><Sparkles size={46} /><h2>AI Design Instructions</h2><p>Import a client design first. LoomLab will read it and help you write precise instructions for an external AI image generator.</p></div></div></main>;
  }
  return (
    <main>
      <div className="canvasbar"><b>AI Design Instructions</b><span className="muted">Reference-anchored · no design is generated here</span></div>
      <div className="ai-body">
        <section className="ai-col ai-inputs">
          <button className="secondary wide" onClick={onAnalyze} disabled={busy}><Search size={15} /> Analyze this design</button>

          <label>What do you want to change?</label>
          <textarea rows={3} value={userRequest} onChange={e => setUserRequest(e.target.value)} placeholder={'e.g. Make the flowers more premium and slightly less crowded, reduce to 5 print colors'} />

          <label>Goal</label>
          <select value={intent} onChange={e => setIntent(e.target.value as Intent)}>
            {INTENTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <p className="muted">{INTENTS.find(o => o.value === intent)?.hint}</p>

          <label>Reference fidelity <output>{fidelity}% · {fidelityLabel(fidelity)}</output></label>
          <input type="range" min={0} max={100} value={fidelity} onChange={e => setFidelity(+e.target.value)} />
          <div className="ai-fidelity-ends"><span>New design</span><span>Recreation</span></div>

          <label>Describe the design (optional)</label>
          <textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder={'Helps where the computer cannot see meaning, e.g. "Traditional Mughal floral with roses, leaves and small fillers; dark red flowers, green leaves, beige ground."'} />

          <button className="primary wide" onClick={onGenerate} disabled={busy}><Sparkles size={16} /> Generate instructions</button>

          {dna && (
            <div className="ai-dna">
              <div className="ai-dna-head">DESIGN DNA</div>
              <DnaRow k="Style" v={`${dna.style.category}${dna.style.sub_style !== 'unspecified' ? ' · ' + dna.style.sub_style : ''}`} src={dna.style.source} />
              <DnaRow k="Motif family" v={dna.motif_family.join(', ')} src={dna.motif_family_source} />
              <DnaRow k="Density" v={dna.composition.density} src="auto" />
              <DnaRow k="Symmetry" v={dna.composition.symmetry} src="auto" />
              <DnaRow k="Negative space" v={dna.composition.negative_space} src="auto" />
              <DnaRow k="Contrast" v={dna.composition.contrast} src="auto" />
              <DnaRow k="Detail" v={dna.composition.detail} src="auto" />
              <DnaRow k="Distinct colors" v={String(dna.distinct_colors)} src="auto" />
              <div className="ai-dna-swatches">{dna.colors.map((c, i) => <span key={i} title={`${c.role} ${c.hex} · ${c.coverage}%`} style={{ background: c.hex }} />)}</div>
              {!!dna.mergeable_colors.length && <p className="muted">{dna.mergeable_colors.length} near-identical color pair(s) — candidates for merging.</p>}
              <p className="ai-src-note">Grey = measured from the image · Amber = from your description</p>
            </div>
          )}
        </section>

        <section className="ai-col ai-outputs">
          {brief && (
            <div className="ai-out">
              <div className="ai-out-head"><b>Design brief</b><CopyButton text={brief} label="Copy analysis" /></div>
              <pre className="ai-brief">{brief}</pre>
            </div>
          )}
          <div className="ai-out">
            <div className="ai-out-head"><b>AI instructions (editable)</b><CopyButton text={instruction} label="Copy instructions" /></div>
            <textarea className="ai-instruction" rows={20} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="Set your goal and request on the left, then Generate instructions. The copy-ready prompt appears here and can be edited before copying." />
          </div>
        </section>
      </div>
    </main>
  );
}

function DnaRow({ k, v, src }: { k: string; v: string; src: string }) {
  return <div className="ai-dna-row"><span className="ai-dna-k">{k}</span><span className={'ai-dna-v ' + (src === 'user' ? 'from-user' : src === 'unspecified' ? 'unspec' : 'from-auto')}>{v}</span></div>;
}
