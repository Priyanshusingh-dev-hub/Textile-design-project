import { describe, expect, it } from 'vitest';
import { OFFLINE_TEXT, statusText } from '../api';
import { HI } from './i18n';
import { matchVerdict } from './print';
import {
  CUE_MS, CAREFUL_MS, ENGINE_START, LINES, MASCOT_LINES, MOOD_FACE, WAIT_LINE, engineDown, errorLine, firstTip,
  formatElapsed, hostPose, modeTitle, nextEngine, nextMode, pickMood, readMode, readSeen, renderMode,
  type Cue, type Facts,
} from './mascot';

const NOW = 1_000_000;
const calm: Facts = { mode: 'on', now: NOW, engineDown: false, busy: false,
  verdict: null, dots: false, fillWarn: false, numberBad: false, enlargeBad: false };
const cue = (kind: Cue['kind'], ago = 100, vars?: Cue['vars']): Cue => ({ kind, seq: 7, at: NOW - ago, vars });

describe('pickMood: what Loomy shows', () => {
  it('is a calm idle face when nothing happened', () => {
    expect(pickMood(calm)).toEqual({ mood: 'idle' });
  });

  it('never cheers a background redraw: busy then done with no named action is just idle', () => {
    expect(pickMood({ ...calm, busy: true, busySince: NOW - 300 })).toEqual({ mood: 'idle' });
    expect(pickMood({ ...calm, busy: false })).toEqual({ mood: 'idle' });
  });

  it('works while a long run goes on, with real elapsed seconds only after 2 s', () => {
    expect(pickMood({ ...calm, busy: true, busyLabel: 'Reducing…', busySince: NOW - 1000 })).toEqual({ mood: 'working' });
    const r = pickMood({ ...calm, busy: true, busyLabel: 'Numbering the design…', busySince: NOW - 80_000 });
    expect(r).toMatchObject({ mood: 'working', line: LINES.waitNumber, vars: { s: '1 min 20 s' } });
  });

  it('shows no line for a label it has no words for (an untranslated busy label never leaks out)', () => {
    expect(pickMood({ ...calm, busy: true, busyLabel: 'Opening your last job…', busySince: NOW - 5000 })).toEqual({ mood: 'working' });
  });

  it('cheers a good reduce, but looks careful next to a match verdict (golden rule 7)', () => {
    const good = pickMood({ ...calm, cue: cue('reduced', 100, { n: 5, m: 96.2 }) });
    expect(good).toMatchObject({ mood: 'cheer', line: LINES.reducedGood, vars: { n: 5, m: 96.2 }, tone: 'ok' });
    const photo = matchVerdict(64, [{ colors: 14, accuracy: 70 }], 8, 8);
    expect(photo?.tone).toBe('warn');
    expect(pickMood({ ...calm, verdict: photo, cue: cue('reduced') })).toMatchObject({ mood: 'careful', line: LINES.photographic, tone: 'warn' });
    const loose = matchVerdict(82, [{ colors: 14, accuracy: 95 }], 8, 5);
    expect(loose?.tone).toBe('hint');
    expect(pickMood({ ...calm, verdict: loose, cue: cue('reduced') })).toMatchObject({ mood: 'careful', line: LINES.loose });
  });

  it('nods, not cheers, at dots', () => {
    expect(pickMood({ ...calm, dots: true, cue: cue('reduced') })).toMatchObject({ mood: 'idle', line: LINES.reducedDots });
  });

  it('is careful after a failed numbering check, a fill that set the line art aside, a flagged enlargement', () => {
    expect(pickMood({ ...calm, numberBad: true, cue: cue('numbered') }).mood).toBe('careful');
    expect(pickMood({ ...calm, numberBad: false, cue: cue('numbered') }).mood).toBe('cheer');
    expect(pickMood({ ...calm, fillWarn: true, cue: cue('filled') }).mood).toBe('careful');
    expect(pickMood({ ...calm, enlargeBad: true, cue: cue('enlarged') }).mood).toBe('careful');
  });

  it('always cheers the films and a saved screen', () => {
    expect(pickMood({ ...calm, cue: cue('exported') })).toMatchObject({ mood: 'cheer', line: LINES.exported });
    expect(pickMood({ ...calm, cue: cue('plates', 50, { n: 4 }) })).toMatchObject({ mood: 'cheer', vars: { n: 4 } });
    expect(pickMood({ ...calm, cue: cue('ground-cloth') }).mood).toBe('cheer');
  });

  it('lets a reaction go after its time; a careful one stays longer', () => {
    expect(pickMood({ ...calm, cue: cue('exported', CUE_MS + 1) })).toEqual({ mood: 'idle' });
    const photo = { tone: 'warn' as const, text: 'x' };
    expect(pickMood({ ...calm, verdict: photo, cue: cue('reduced', CUE_MS + 1) }).mood).toBe('careful');
    expect(pickMood({ ...calm, verdict: photo, cue: cue('reduced', CAREFUL_MS + 1) }).mood).toBe('idle');
  });

  it('explains plates dropped by a palette edit, even when quiet', () => {
    expect(pickMood({ ...calm, mode: 'quiet', cue: cue('plates-dropped') })).toMatchObject({ line: LINES.platesDropped });
    expect(pickMood({ ...calm, mode: 'quiet', cue: cue('exported') })).toEqual({ mood: 'idle' });
  });

  it('puts the engine and errors above everything, and says what to do', () => {
    const busyAndDown = { ...calm, engineDown: true, busy: true, busyLabel: 'Reducing…', busySince: NOW - 9000, cue: cue('exported') };
    expect(pickMood(busyAndDown)).toMatchObject({ mood: 'offline', line: LINES.offline, tone: 'err' });
    expect(pickMood({ ...calm, failed: OFFLINE_TEXT })).toMatchObject({ mood: 'offline', line: LINES.offline });
    expect(pickMood({ ...calm, failed: 'Bad input' })).toMatchObject({ mood: 'oops', line: LINES.failed, tone: 'err' });
  });

  it('gives a first-visit tip only when on and nothing else is going on', () => {
    expect(pickMood({ ...calm, tip: LINES.tipReduce })).toMatchObject({ mood: 'hello', line: LINES.tipReduce });
    expect(pickMood({ ...calm, mode: 'quiet', tip: LINES.tipReduce })).toEqual({ mood: 'idle' });
    expect(pickMood({ ...calm, tip: LINES.tipReduce, cue: cue('exported') }).line).toBe(LINES.exported);
  });

  it('says nothing at all when off', () => {
    expect(pickMood({ ...calm, mode: 'off', engineDown: true, failed: 'x', cue: cue('exported') })).toEqual({ mood: 'idle' });
  });

  it('keys every reaction that says something (a dismissed bubble must not hide the next one)', () => {
    const said = [
      pickMood({ ...calm, busy: true, busyLabel: 'Separating…', busySince: NOW - 5000 }),
      pickMood({ ...calm, engineDown: true }), pickMood({ ...calm, failed: 'x' }),
      pickMood({ ...calm, cue: cue('plates') }), pickMood({ ...calm, tip: LINES.tipExport }),
    ];
    for (const r of said) { expect(r.line).toBeTruthy(); expect(r.key).toBeTruthy(); }
    const next = pickMood({ ...calm, busy: true, busyLabel: 'Separating…', busySince: NOW - 3000 });
    expect(next.key).not.toBe(said[0].key);               // the next run's wait line is a new bubble
  });

  it('keys each reaction, so a dismissed bubble stays dismissed and a new one shows', () => {
    const a = pickMood({ ...calm, cue: { ...cue('exported'), seq: 1 } });
    const b = pickMood({ ...calm, cue: { ...cue('exported'), seq: 2 } });
    expect(a.key).not.toBe(b.key);
  });
});

describe('the pieces', () => {
  it('formats elapsed time', () => {
    expect(formatElapsed(0)).toBe('0 s');
    expect(formatElapsed(59.9)).toBe('59 s');
    expect(formatElapsed(125)).toBe('2 min 5 s');
  });

  it('calls the engine down after two failed looks, or one once it has answered', () => {
    let s = nextEngine(ENGINE_START, false);
    expect(engineDown(s)).toBe(false);                       // a starting engine fails its first look
    s = nextEngine(s, false);
    expect(engineDown(s)).toBe(true);
    s = nextEngine(s, true);
    expect(engineDown(s)).toBe(false);
    expect(engineDown(nextEngine(s, false))).toBe(true);
  });

  it('reads the app’s own error texts', () => {
    expect(errorLine(OFFLINE_TEXT)).toBe(LINES.offline);
    expect(errorLine(statusText(500, ''))).toBe(LINES.crashed);
    expect(errorLine(statusText(413, ''))).toBe(LINES.tooBig);
    expect(errorLine('This image is no longer available. Please import it again.')).toBe(LINES.expired);
    expect(errorLine('Inks: choose between 2 and 20.')).toBe(LINES.failed);
  });

  it('tips once per step, never on Upload (the drop zone has its own Loomy)', () => {
    expect(firstTip('Reduce', new Set())).toBe(LINES.tipReduce);
    expect(firstTip('Reduce', new Set(['Reduce']))).toBeUndefined();
    expect(firstTip('Upload', new Set())).toBeUndefined();
  });

  it('cycles on → quiet → off → on, and reads a bad saved value as on', () => {
    expect([nextMode('on'), nextMode('quiet'), nextMode('off')]).toEqual(['quiet', 'off', 'on']);
    expect(readMode(null)).toBe('on');
    expect(readMode('loud')).toBe('on');
    expect(readMode('off')).toBe('off');
    expect(modeTitle('off')).toBe(LINES.modeOff);
    expect([...readSeen('["Reduce", 3]')]).toEqual(['Reduce']);
    expect(readSeen('{broken').size).toBe(0);
  });

  it('runs the live 3D Loomy only on a PC that can clearly afford it', () => {
    const good = { webgl2: true, reducedMotion: false, cores: 8 };
    expect(renderMode('on', good)).toBe('3d');
    expect(renderMode('quiet', good)).toBe('still');
    expect(renderMode('off', good)).toBe('none');
    expect(renderMode('on', { ...good, webgl2: false })).toBe('still');
    expect(renderMode('on', { ...good, reducedMotion: true })).toBe('still');
    expect(renderMode('on', { ...good, cores: 2 })).toBe('still');
  });

  it('poses the Upload Loomy: working beats a drag, a drag beats a hello', () => {
    expect(hostPose({ dragging: true, busy: true, firstVisit: true, resumable: true }).pose).toBe('working');
    expect(hostPose({ dragging: true, busy: false, firstVisit: true, resumable: false })).toEqual({ pose: 'catch', line: LINES.dragging });
    expect(hostPose({ dragging: false, busy: false, firstVisit: false, resumable: true }).line).toBe(LINES.helloBack);
    expect(hostPose({ dragging: false, busy: false, firstVisit: false, resumable: false })).toEqual({ pose: 'idle' });
  });
});

describe('wired to the real app', () => {
  const src = import.meta.glob('/src/hooks/useLoomLab.ts', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  const hook = Object.values(src)[0];

  it('every wait line belongs to a busy label the hook really uses', () => {
    for (const label of Object.keys(WAIT_LINE)) expect(hook).toContain(`'${label}'`);
  });

  it('every line has its Hinglish with the same {values}', () => {
    for (const line of MASCOT_LINES) {
      expect(HI[line], line).toBeTruthy();
      const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
      expect(vars(HI[line])).toEqual(vars(line));
    }
  });

  it('has a picture for every mood', () => {
    const files = Object.keys(import.meta.glob('/src/assets/mascot/*.png')).map(f => f.split('/').pop()!.replace('.png', ''));
    for (const name of Object.values(MOOD_FACE)) expect(files).toContain(name);
    for (const body of ['body_hello', 'body_idle', 'body_working', 'body_cheer']) expect(files).toContain(body);
  });
});
