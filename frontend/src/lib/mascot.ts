/** LOOMY DADA, the mascot: what he shows and says, worked out from what the
 *  app already knows. Pure, so it is tested here; the components only draw it.
 *
 *  Rules (do not loosen):
 *  - he reacts to NAMED actions (a cue set beside setMessage), never to the
 *    shared status turning 'done': plate toggles and preview redraws end in
 *    'done' too, and he would cheer every click;
 *  - a thumbs-up only when the result is honestly good (golden rule 7): a
 *    match verdict, a fill that set the line art aside, a failed numbering
 *    check or a flagged enlargement turn it into a careful look and a pointer
 *    to the note — the note itself stays the source of truth;
 *  - waits show real elapsed seconds, never a made-up percentage;
 *  - he points at controls that exist; he adds none. */
import { OFFLINE_TEXT } from '../api';
import type { Verdict } from './print';
import type { Step } from '../types';

export type Mood = 'hello' | 'idle' | 'working' | 'cheer' | 'careful' | 'oops' | 'offline';
/** on: everything · quiet: only waits, errors and the engine · off: a small grey face, nothing else */
export type MascotMode = 'on' | 'quiet' | 'off';
export const MASCOT_KEY = 'loomlab-mascot';
export const TIPS_KEY = 'loomlab-mascot-tips';
export const MODES: MascotMode[] = ['on', 'quiet', 'off'];

export type CueKind = 'reduced' | 'plates' | 'exported' | 'numbered' | 'filled' | 'ground-cloth' | 'enlarged'
  | 'resumed' | 'plates-dropped' | 'engine-back';
export type Cue = { kind: CueKind; seq: number; at: number; vars?: Record<string, string | number> };
/** The still for each mood (src/assets/mascot/<name>.png, rendered by brand/loomy-dada/render_previews.py
 *  --set app); working is the sprite strip. Offline wears the calm face, greyed by CSS. */
export const MOOD_FACE: Record<Mood, string> = {
  hello: 'face_hello', idle: 'face_idle', working: 'sprite_working', cheer: 'face_cheer',
  careful: 'face_careful', oops: 'face_oops', offline: 'face_calm',
};
export const SPRITE_FRAMES = 12;            // styles.css .mascot-sprite: steps(12) over 12 x 46 px
export type Tone = 'ok' | 'warn' | 'err' | 'info';
export type Reaction = { mood: Mood; line?: string; vars?: Record<string, string | number>; tone?: Tone;
  /** what dismissing the bubble hides: the same key is not shown again */
  key?: string };

/** How long a reaction to a named action stays up. */
export const CUE_MS = 6000;
export const CAREFUL_MS = 9000;
export const TIP_MS = 7000;
/** A wait shorter than this shows no line: quick runs must not flash. */
export const WAIT_LINE_AFTER_S = 2;

// Every line he says. English is the key; the Hinglish is in i18n.ts (HI), checked by i18n-coverage.test.ts.
export const LINES = {
  offline: 'Engine closed: run run-windows.bat again. Your work is kept.',
  engineBack: 'The engine is back.',
  expired: 'This design has left the engine (kept 48 h). Import it again.',
  crashed: 'The engine hit a problem. Try again; Settings → Help has a report.',
  tooBig: 'This file is over 80 MB.',
  failed: 'That did not work. The red line at the bottom says why.',
  reducedGood: '{n} inks, {m}% match. Looks good!',
  reducedDots: 'Dots placed. Judge it from a step away.',
  photographic: 'Photo-like shading: flat inks will band it. Read the note.',
  loose: 'A loose match. Read the note before making screens.',
  plates: '{n} screens ready: one ink each, no overlap.',
  exported: 'Films ready! The zip is in your Downloads.',
  numbered: 'Numbered! Every file is in the zip.',
  numberBad: 'A check failed: do not send these files to the mill.',
  filled: 'Filled from your line art.',
  fillWarn: 'The line art did not fit, so the reference alone was used.',
  groundCloth: 'One screen fewer: the cloth is the ground.',
  enlarged: 'High-resolution file ready.',
  enlargeBad: 'The enlargement changed the design. Check it closely.',
  resumed: 'Welcome back! Your job is where you left it.',
  platesDropped: 'Colours changed, so the old screens were cleared. Make them again.',
  tipReduce: 'Pick the ink count, then reduce. Drag the middle line to compare.',
  tipSeparate: 'Click a plate to leave it unprinted. The biggest can be the cloth.',
  tipExport: 'Type the print width, then download the zip.',
  hello: 'Namaste! I’m Loomy. Drop a design here, or try the sample.',
  helloBack: 'Your last job is waiting: Continue picks it up.',
  dragging: 'Drop it here!',
  poke: 'Upload → Reduce → Separate → Export. I’ll keep an eye on each step.',
  waitReduce: 'Reducing the colours… {s}',
  waitSeparate: 'Making the screens… {s}',
  waitZip: 'Packing the films… {s}',
  waitVectors: 'Packing the films and vectors… {s}',
  waitNumber: 'Numbering the design… {s} (1–3 min)',
  waitFill: 'Trying every way to fill… {s}',
  waitEnlarge: 'Enlarging… {s}',
  waitTrace: 'Tracing the vectors… {s}',
  modeOn: 'Loomy is on. Click for quiet (only waits and problems).',
  modeQuiet: 'Loomy is quiet. Click to switch him off.',
  modeOff: 'Loomy is off. Click to switch him on.',
} as const;
export const MASCOT_LINES: string[] = Object.values(LINES);

/** The long named runs (useLoomLab's busy labels) and what he says while one goes on. Labels not
 *  listed get the working face and no line, so an untranslated label is never shown. */
export const WAIT_LINE: Record<string, string> = {
  'Reducing…': LINES.waitReduce,
  'Separating…': LINES.waitSeparate,
  'Building zip…': LINES.waitZip,
  'Building zip + vectors…': LINES.waitVectors,
  'Numbering the design…': LINES.waitNumber,
  'Making the design…': LINES.waitFill,
  'Enlarging…': LINES.waitEnlarge,
  'Tracing vectors…': LINES.waitTrace,
};

export const TIP_FOR: Partial<Record<Step, string>> = {
  Reduce: LINES.tipReduce, Separate: LINES.tipSeparate, Export: LINES.tipExport,
};

/** 7 s, 1 min 20 s. */
export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

/** The engine is "down" after two failed looks in a row, or one once it has answered before
 *  (a starting engine fails its first look through the dev proxy). */
export type EngineState = { fails: number; everOk: boolean };
export const ENGINE_START: EngineState = { fails: 0, everOk: false };
export const nextEngine = (s: EngineState, ok: boolean): EngineState =>
  ok ? { fails: 0, everOk: true } : { fails: s.fails + 1, everOk: s.everOk };
export const engineDown = (s: EngineState) => s.fails >= (s.everOk ? 1 : 2);

/** Which of the app's own error texts a failure is, so the line leads with what to do. */
export function errorLine(message: string): string {
  if (message === OFFLINE_TEXT) return LINES.offline;
  if (/no longer available/i.test(message)) return LINES.expired;
  if (/\(error 5\d\d\)/.test(message)) return LINES.crashed;
  if (/80 MB/.test(message)) return LINES.tooBig;
  return LINES.failed;
}

/** Everything that would make a thumbs-up dishonest right now. */
export type Honesty = {
  verdict: Verdict | null;      // matchVerdictNote (null for dots, fills and numbering)
  dots: boolean;
  fillWarn: boolean;            // trialSummary(fillInfo).warn
  numberBad: boolean;           // numbering: plates did not stack back, or the mill check failed
  enlargeBad: boolean;          // hiRes && !hiRes.ok
};

export type Facts = Honesty & {
  mode: MascotMode;
  now: number;
  engineDown: boolean;
  failed?: string;              // status.message while status.state === 'failed'
  busy: boolean;
  busyLabel?: string;
  busySince?: number;
  cue?: Cue;
  tip?: string;                 // a first-visit tip still to show (see firstTip)
};

/** One reaction for the header avatar, in priority order: the engine, an error, work in progress,
 *  a fresh named action, a first-visit tip, else a calm idle face. */
export function pickMood(f: Facts): Reaction {
  if (f.mode === 'off') return { mood: 'idle' };
  if (f.engineDown) return { mood: 'offline', line: LINES.offline, tone: 'err', key: 'offline' };
  if (f.failed !== undefined) {
    const line = errorLine(f.failed);
    return { mood: line === LINES.offline ? 'offline' : 'oops', line, tone: 'err', key: 'failed:' + f.failed };
  }
  if (f.busy) {
    const since = f.busySince ?? f.now;
    const s = (f.now - since) / 1000;
    const wait = f.busyLabel ? WAIT_LINE[f.busyLabel] : undefined;
    // a preview redraw or a plate toggle is over in a blink: no face swap for those
    if (!wait && s < 1) return { mood: 'idle' };
    if (!wait || s < WAIT_LINE_AFTER_S) return { mood: 'working' };
    return { mood: 'working', line: wait, vars: { s: formatElapsed(s) }, tone: 'info', key: `wait:${since}` };
  }
  const cue = f.cue;
  if (cue) {
    const r = cueReaction(cue, f);
    const age = f.now - cue.at;
    const keep = r.tone === 'warn' ? CAREFUL_MS : CUE_MS;
    const quietOk = cue.kind === 'plates-dropped' || cue.kind === 'engine-back';
    if (age >= 0 && age < keep && (f.mode === 'on' || quietOk)) return { ...r, key: `cue:${cue.seq}` };
  }
  if (f.tip && f.mode === 'on') return { mood: 'hello', line: f.tip, tone: 'info', key: 'tip:' + f.tip };
  return { mood: 'idle' };
}

/** What a named action earns, judged on the facts as they are now. */
export function cueReaction(cue: Cue, h: Honesty): Reaction {
  const v = cue.vars;
  switch (cue.kind) {
    case 'reduced':
      if (h.verdict?.tone === 'warn') return { mood: 'careful', line: LINES.photographic, tone: 'warn' };
      if (h.verdict) return { mood: 'careful', line: LINES.loose, tone: 'warn' };
      if (h.dots) return { mood: 'idle', line: LINES.reducedDots, tone: 'info' };
      return { mood: 'cheer', line: LINES.reducedGood, vars: v, tone: 'ok' };
    case 'plates': return { mood: 'cheer', line: LINES.plates, vars: v, tone: 'ok' };
    case 'exported': return { mood: 'cheer', line: LINES.exported, tone: 'ok' };
    case 'numbered':
      return h.numberBad ? { mood: 'careful', line: LINES.numberBad, tone: 'warn' } : { mood: 'cheer', line: LINES.numbered, tone: 'ok' };
    case 'filled':
      return h.fillWarn ? { mood: 'careful', line: LINES.fillWarn, tone: 'warn' } : { mood: 'cheer', line: LINES.filled, tone: 'ok' };
    case 'ground-cloth': return { mood: 'cheer', line: LINES.groundCloth, tone: 'ok' };
    case 'enlarged':
      return h.enlargeBad ? { mood: 'careful', line: LINES.enlargeBad, tone: 'warn' } : { mood: 'cheer', line: LINES.enlarged, tone: 'ok' };
    case 'resumed': return { mood: 'hello', line: LINES.resumed, tone: 'info' };
    case 'plates-dropped': return { mood: 'careful', line: LINES.platesDropped, tone: 'info' };
    case 'engine-back': return { mood: 'cheer', line: LINES.engineBack, tone: 'ok' };
  }
}

/** The tip for a step the operator reaches for the first time on this PC, else undefined. */
export function firstTip(step: Step, seen: ReadonlySet<string>): string | undefined {
  const tip = TIP_FOR[step];
  return tip && !seen.has(step) ? tip : undefined;
}

export const nextMode = (m: MascotMode): MascotMode => MODES[(MODES.indexOf(m) + 1) % MODES.length];
export const modeTitle = (m: MascotMode) => (m === 'on' ? LINES.modeOn : m === 'quiet' ? LINES.modeQuiet : LINES.modeOff);

/** The saved setting; anything unreadable (private window, an old value) is 'on'. */
export function readMode(raw: string | null): MascotMode {
  return raw === 'quiet' || raw === 'off' ? raw : 'on';
}
export function readSeen(raw: string | null): Set<string> {
  try {
    const v = JSON.parse(raw ?? '[]');
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
  } catch {
    return new Set();
  }
}

/** Whether the Upload screen gets the live 3D Loomy, a still, or nothing. 3D only when the PC can
 *  clearly afford it: WebGL 2 without a software fallback, no reduced-motion wish, more than two
 *  cores (the engine runs on the same PC), and the mascot fully on. */
export type Capability = { webgl2: boolean; reducedMotion: boolean; cores: number };
export function renderMode(mode: MascotMode, c: Capability): '3d' | 'still' | 'none' {
  if (mode === 'off') return 'none';
  if (mode === 'quiet' || c.reducedMotion || !c.webgl2 || c.cores <= 2) return 'still';
  return '3d';
}

/** What the Upload screen's Loomy does: catch a dragged file, work while it uploads, wave at a
 *  first visit or a waiting job, else idle. */
export type HostPose = 'hello' | 'idle' | 'working' | 'catch';
export function hostPose(o: { dragging: boolean; busy: boolean; firstVisit: boolean; resumable: boolean }): { pose: HostPose; line?: string } {
  if (o.busy) return { pose: 'working' };
  if (o.dragging) return { pose: 'catch', line: LINES.dragging };
  if (o.resumable) return { pose: 'hello', line: LINES.helloBack };
  if (o.firstVisit) return { pose: 'hello', line: LINES.hello };
  return { pose: 'idle' };
}
