import { afterEach, describe, expect, it, vi } from 'vitest';
import { OFFLINE_TEXT, request, setOnReach, statusText } from '../api';
import { HI } from './i18n';
import { matchVerdict } from './print';
import { fillCautions } from './fill';
import { numberCautions, numberFailed } from './numbering';
import type { FillInfo, NumberInfo } from '../types';
import {
  CUE_MS, CAREFUL_MS, ENGINE_START, LINES, MASCOT_LINES, MOOD_FACE, WAIT_LINE,
  cueReaction, engineDown, errorLine, firstTip, formatElapsed, hostPose, judge, modeTitle, nextEngine, nextMode,
  pickMood, readMode, readSeen, renderMode, type Cue, type Facts, type Honesty,
} from './mascot';

const NOW = 1_000_000;
const honest: Honesty = { verdict: null, dots: false, softEdge: false, cleanupWarn: false, noVerdict: false, fillRef: false,
  fillSetAside: false, fillWarn: false, numberBad: false, numberWarn: false, enlargeBad: false };
const calm: Facts = { ...honest, mode: 'on', now: NOW, engineDown: false, busy: false };
const cue = (kind: Cue['kind'], ago = 100, vars?: Cue['vars']): Cue => ({ kind, seq: 7, at: NOW - ago, vars });

describe('pickMood: what Loomy shows', () => {
  it('is a calm idle face when nothing happened', () => {
    expect(pickMood(calm)).toEqual({ mood: 'idle' });
  });

  it('a background redraw (the preview after Separate) does not swallow a fresh reaction', () => {
    const r = pickMood({ ...calm, busy: true, busySince: NOW - 3000, cue: cue('plates', 100, { n: 3 }) });
    expect(r).toMatchObject({ mood: 'cheer', line: LINES.plates });
    // a long NAMED run still shows its wait
    expect(pickMood({ ...calm, busy: true, busyLabel: 'Reducing…', busySince: NOW - 3000, cue: cue('plates') }).mood).toBe('working');
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

  it('is careful beside the soft-edge or cleanup warning, plain after a fill or numbering re-reduce', () => {
    const c = cue('reduced', 100, { n: 7, m: 93 });
    expect(pickMood({ ...calm, softEdge: true, cue: c })).toMatchObject({ mood: 'careful', line: LINES.softEdge, tone: 'warn' });
    expect(pickMood({ ...calm, cleanupWarn: true, cue: c })).toMatchObject({ mood: 'careful', line: LINES.cleanupWarn });
    expect(pickMood({ ...calm, noVerdict: true, cue: c })).toMatchObject({ mood: 'idle', line: LINES.reducedPlain, tone: 'info' });
  });

  it('a re-reduce that cleared the plates says so, but a warning still comes first', () => {
    const c = cue('reduced', 100, { n: 4, m: 97, dropped: 1 });
    expect(pickMood({ ...calm, cue: c })).toMatchObject({ mood: 'cheer', line: LINES.reducedDropped });
    expect(pickMood({ ...calm, verdict: { tone: 'warn', text: 'x' }, cue: c }).line).toBe(LINES.photographic);
  });

  it('a fill: reference picked by hand is plain, set aside by the judge or any card warning is careful', () => {
    expect(pickMood({ ...calm, fillRef: true, fillWarn: true, cue: cue('filled') })).toMatchObject({ mood: 'idle', line: LINES.fillReference });
    expect(pickMood({ ...calm, fillSetAside: true, fillWarn: true, cue: cue('filled') }).line).toBe(LINES.fillWarn);
    expect(pickMood({ ...calm, fillWarn: true, cue: cue('filled') })).toMatchObject({ mood: 'careful', line: LINES.fillCheck });
    expect(pickMood({ ...calm, numberWarn: true, cue: cue('numbered') })).toMatchObject({ mood: 'careful', line: LINES.numberCheck });
  });

  it('judges a reaction once: a warning cleared a moment later does not turn it into a cheer', () => {
    const c = cue('enlarged');
    const first = judge(c, { ...honest, enlargeBad: true });
    expect(first.r.mood).toBe('careful');
    expect(judge(c, honest, first)).toBe(first);                                    // same cue: kept
    expect(pickMood({ ...calm, enlargeBad: false, cue: c, judged: first }).mood).toBe('careful');
    expect(judge({ ...c, seq: c.seq + 1 }, honest, first).r.mood).toBe('cheer');   // a new cue: judged anew
    expect(cueReaction(c, honest).mood).toBe('cheer');
  });

  it('a zip rebuilt with the palette edits: a cheer only with no warning on the card', () => {
    expect(pickMood({ ...calm, cue: cue('rebuilt', 100, { n: 2 }) })).toMatchObject({ mood: 'cheer', line: LINES.rebuilt });
    expect(pickMood({ ...calm, numberWarn: true, cue: cue('rebuilt') })).toMatchObject({ mood: 'careful', line: LINES.rebuiltCheck });
    expect(pickMood({ ...calm, numberBad: true, numberWarn: true, cue: cue('rebuilt') })).toMatchObject({ mood: 'careful', line: LINES.numberBad });
  });

  it('is careful after a failed numbering check, a fill that set the line art aside, a flagged enlargement', () => {
    expect(pickMood({ ...calm, numberBad: true, cue: cue('numbered') }).mood).toBe('careful');
    expect(pickMood({ ...calm, numberBad: false, cue: cue('numbered') }).mood).toBe('cheer');
    expect(pickMood({ ...calm, fillSetAside: true, cue: cue('filled') }).mood).toBe('careful');
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

describe('the engine heartbeat', () => {
  afterEach(() => { setOnReach(undefined); vi.unstubAllGlobals(); });
  const heard = async (answer: () => Promise<Response>) => {
    const seen: boolean[] = [];
    setOnReach(ok => seen.push(ok));
    vi.stubGlobal('fetch', vi.fn(answer));
    await request('/api/x').catch(() => {});
    return seen;
  };

  it('any answer means the engine runs: a locked licence (402) or a 500 is not a closed engine', async () => {
    expect(await heard(async () => new Response('', { status: 402 }))).toEqual([true]);
    expect(await heard(async () => new Response('', { status: 500 }))).toEqual([true]);
    expect(await heard(async () => new Response('{}', { status: 200 }))).toEqual([true]);
  });

  it('a network failure or the proxy’s 502 means its window is closed', async () => {
    expect(await heard(async () => new Response('', { status: 502 }))).toEqual([false]);
    expect(await heard(async () => { throw new TypeError('Failed to fetch'); })).toEqual([false]);
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

describe('the cards’ warnings', () => {
  const fill = (over: Partial<FillInfo>): FillInfo => ({ method: 1, alignment: 0.97, doubtful: 0, trials: null,
    stray_merged: [], line_color: null, size_px: [100, 100], ...over } as unknown as FillInfo);
  const num = (over: Partial<NumberInfo>): NumberInfo => ({ verify: true, mill: null, missed: 0, ...over } as unknown as NumberInfo);

  it('a fill card warns on a low alignment, leaks, a loose match or two colours only', () => {
    expect(fillCautions(fill({}), 92)).toBe(false);
    expect(fillCautions(fill({ alignment: 0.58 }), 92)).toBe(true);
    expect(fillCautions(fill({ doubtful: 3 }), 92)).toBe(true);
    expect(fillCautions(fill({}), 72)).toBe(true);
    expect(fillCautions(fill({ method: 2 }), 92)).toBe(true);
  });

  it('a numbering card warns on a failed check, a repeat cut to shape, numbers with no room', () => {
    expect(numberCautions(num({}))).toBe(false);
    expect(numberFailed(num({ verify: false }))).toBe(true);
    const mill = { passed: true, cropped: false } as NumberInfo['mill'];
    expect(numberCautions(num({ mill: { ...mill!, cropped: true } }))).toBe(true);
    expect(numberFailed(num({ mill: { ...mill!, cropped: true } }))).toBe(false);
    expect(numberCautions(num({ missed: 2 }))).toBe(true);
    // after a rebuild: a mill ink that kept its colour, or a change the mill has no screen for
    expect(numberCautions(num({ mill: { ...mill!, left: [], missing: [] } }))).toBe(false);
    expect(numberCautions(num({ mill: { ...mill!, left: ['#123456'] } }))).toBe(true);
    expect(numberCautions(num({ mill: { ...mill!, missing: ['#123456'] } }))).toBe(true);
    expect(numberCautions(num({ mill: { ...mill!, shared: ['#123456'] } }))).toBe(true);
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
