import { Suspense, lazy, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { LoomLab } from '../hooks/useLoomLab';
import { useT } from '../lib/i18n';
import { fillCautions, trialSummary } from '../lib/fill';
import { numberCautions, numberFailed } from '../lib/numbering';
import {
  CAREFUL_MS, MASCOT_KEY, MOOD_FACE, SMALL_SCREEN, TIPS_KEY, TIP_MS, firstTip, hostPose, judge, modeTitle, nextMode,
  pickMood, readMode, readSeen, renderMode, type Capability, type HostPose, type Honesty, type Judged, type MascotMode,
} from '../lib/mascot';

/** LOOMY DADA in the app: a face in the header that reacts to what the operator does (lib/mascot.ts
 *  decides, this only draws), the live 3D Loomy on the empty Upload screen, and small stills on
 *  empty pages. Never on anything that prints: films, plates, proofs, job sheets, quotes. */

// the stills: brand/loomy-dada/render_previews.py --set app (one camera, so moods swap in place)
const PICS = Object.fromEntries(Object.entries(
  import.meta.glob('../assets/mascot/*.png', { eager: true, import: 'default', query: '?url' }) as Record<string, string>,
).map(([path, url]) => [path.split('/').pop()!.replace('.png', ''), url]));
const BODY: Record<HostPose | 'cheer', string> = {
  hello: PICS.body_hello, catch: PICS.body_hello, idle: PICS.body_idle, working: PICS.body_working, cheer: PICS.body_cheer,
};
const Mascot3D = lazy(() => import('./Mascot3D'));

const read = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const write = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* just not remembered */ } };

// on / quiet / off, shared by every Loomy on the page and remembered on this PC
let mode: MascotMode = readMode(read(MASCOT_KEY));
const listeners = new Set<() => void>();
export function useMascotMode(): [MascotMode, (m: MascotMode) => void] {
  const m = useSyncExternalStore(cb => { listeners.add(cb); return () => { listeners.delete(cb); }; }, () => mode);
  return [m, next => { mode = next; write(MASCOT_KEY, next); listeners.forEach(f => f()); }];
}

/** Re-render every second while something on screen depends on the clock. */
function useTick(active: boolean) {
  const [, set] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => set(n => n + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
}

/** The header face and its one- or two-line bubble. Clicking the face: on → quiet → off. */
export function MascotAvatar({ w }: { w: LoomLab }) {
  const t = useT();
  const [m, setMode] = useMascotMode();
  const { status, busy, busyLabel, cue, engineDown, step, view, licence, matchVerdictNote, printDots, fillInfo, numberInfo, hiRes,
    softEdgeWarning, cleanup, accuracy } = w;
  const since = useRef<number | undefined>(undefined);
  useEffect(() => { since.current = busy ? Date.now() : undefined; }, [busy]);
  const [seen, setSeen] = useState(() => readSeen(read(TIPS_KEY)));
  const [dismissed, setDismissed] = useState<string>();
  const locked = licence?.required && !licence.valid;
  const now = Date.now();
  const failed = status.state === 'failed' ? status.message ?? '' : undefined;
  // every warning line the panel or card shows: he never cheers beside one
  const honesty: Honesty = {
    verdict: matchVerdictNote, dots: printDots, softEdge: !!softEdgeWarning, cleanupWarn: cleanup?.tone === 'warn',
    noVerdict: !!fillInfo || !!numberInfo,
    fillRef: fillInfo?.method === 0 && !(fillInfo.trials && trialSummary(fillInfo).warn),
    fillSetAside: !!fillInfo?.trials && trialSummary(fillInfo).warn,
    fillWarn: !!fillInfo && fillCautions(fillInfo, accuracy?.accuracy),
    numberBad: !!numberInfo && numberFailed(numberInfo), numberWarn: !!numberInfo && numberCautions(numberInfo),
    enlargeBad: !!hiRes && !hiRes.ok,
  };
  const judged = useRef<Judged | undefined>(undefined);
  if (cue) judged.current = judge(cue, honesty, judged.current);   // judged on the render that first saw it
  // the Reduce tip is about the reduce controls: not while a fill's or numbering's card stands there
  const tipHere = view === 'wizard' && !locked && !(step === 'Reduce' && (numberInfo || (fillInfo && fillInfo.method !== 0)));
  const r = pickMood({
    ...honesty, mode: m, now, engineDown, failed, busy, busyLabel, busySince: since.current, cue,
    judged: judged.current, tip: tipHere ? firstTip(step, seen) : undefined,
  });
  useTick(m !== 'off' && (busy || (!!cue && now - cue.at < CAREFUL_MS)));
  const tipStep = r.key?.startsWith('tip:') ? step : undefined;
  const markSeen = (s: string) => setSeen(prev => {
    const next = new Set(prev).add(s);
    write(TIPS_KEY, JSON.stringify([...next]));
    return next;
  });
  // a tip counts as seen once it has been on screen for a while (a cue can hold it back)
  useEffect(() => {
    if (!tipStep) return;
    const id = setTimeout(() => markSeen(tipStep), TIP_MS);
    return () => clearTimeout(id);
  }, [tipStep]);   // eslint-disable-line react-hooks/exhaustive-deps
  // a dismissal holds while its bubble is the current one; a later outage or error shows again
  useEffect(() => { if (dismissed !== undefined && r.key !== dismissed) setDismissed(undefined); }, [r.key, dismissed]);
  const line = m !== 'off' && r.line && (!r.key || r.key !== dismissed) ? r.line : undefined;
  const dot = m !== 'off' && r.tone && r.tone !== 'info' ? r.tone : undefined;
  return (
    <div className={`mascot mood-${r.mood} mode-${m}`}>
      <button type="button" className="mascot-face" onClick={() => setMode(nextMode(m))}
        title={t(modeTitle(m))} aria-label={t(modeTitle(m))}>
        {r.mood === 'working' && m !== 'off'
          ? <span className="mascot-sprite" style={{ backgroundImage: `url(${PICS[MOOD_FACE.working]})` }} />
          : <img src={PICS[MOOD_FACE[m === 'off' ? 'idle' : r.mood]]} alt="" />}
        {dot && <i className={'mascot-dot ' + dot} />}
      </button>
      <div className="mascot-say" role="status" aria-live="polite">
        {line && <p key={r.key} className={'mascot-bubble ' + (r.tone ?? 'info')}>
          <span title={t(line, r.vars)}>{t(line, r.vars)}</span>
          <button type="button" className="mascot-x" aria-label={t('Close')} title={t('Close')}
            onClick={() => { setDismissed(r.key); if (tipStep) markSeen(tipStep); }}>✕</button>
        </p>}
      </div>
    </div>
  );
}

/** What this PC can afford, asked once: WebGL 2 without a software fallback, the motion wish, cores. */
function probe(): Capability {
  let webgl2 = false;
  try {
    const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
    webgl2 = !!gl;
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
  } catch { /* no WebGL */ }
  const reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  return { webgl2, reducedMotion, cores: navigator.hardwareConcurrency || 2 };
}
let capability: Capability | undefined;
const HELLO_KEY = 'loomlab-mascot-hello';

/** Whether the screen is too small for the Upload screen's Loomy (SMALL_SCREEN), followed live. */
function useSmallScreen() {
  return useSyncExternalStore(cb => {
    if (typeof matchMedia !== 'function') return () => {};
    const q = matchMedia(SMALL_SCREEN);
    q.addEventListener('change', cb);
    return () => q.removeEventListener('change', cb);
  }, () => typeof matchMedia === 'function' && matchMedia(SMALL_SCREEN).matches);
}

/** The empty Upload screen's Loomy: waves the first time, follows the pointer, catches a dragged
 *  file, works while it uploads, and waves when the drop zone is clicked (the click still opens the
 *  file picker: he adds no control of his own). 3D where the PC can afford it (lazy: three.js loads
 *  only here, and not at all on a small screen), else a still of the same pose. */
export function UploadMascot({ dragging, busy, resumable }: { dragging: boolean; busy: boolean; resumable: boolean }) {
  const t = useT();
  const [m] = useMascotMode();
  const small = useSmallScreen();
  const [cap] = useState(() => (capability ??= probe()));
  const [broken, setBroken] = useState(false);
  const [firstVisit] = useState(() => !read(HELLO_KEY));
  useEffect(() => { write(HELLO_KEY, '1'); }, []);
  const [poke, setPoke] = useState(0);
  const how = renderMode(m, cap);
  if (how === 'none' || small) return null;
  const { pose, line } = hostPose({ dragging, busy, firstVisit, resumable });
  const still = <img className="loomy-still" src={BODY[pose]} alt="" />;
  return (
    <div className="loomy-host" onClick={() => setPoke(n => n + 1)}>
      {how === '3d' && !broken
        ? <Suspense fallback={still}><Mascot3D pose={pose} poke={poke} still={BODY[pose]} onFail={() => setBroken(true)} /></Suspense>
        : still}
      {line && m === 'on' && <p className="loomy-say">{t(line)}</p>}
    </div>
  );
}

/** A small decorative Loomy beside an empty page's hint (only for plainly good facts). */
export function MascotStill({ pose }: { pose: 'cheer' | 'hello' | 'idle' }) {
  const [m] = useMascotMode();
  return m === 'off' ? null : <img className="mascot-still" src={BODY[pose]} alt="" />;
}
