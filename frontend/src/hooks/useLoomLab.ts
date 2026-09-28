import { useEffect, useRef, useState } from 'react';
import { type LicenceStatus } from '../components/Activation';
import { post, getJson, putJson, uploadFile, downloadPackage, downloadSvg, SCREEN_SIDE } from '../api';
import { type ImageInfo, type Palette, type Layer, type ReduceResult, type Step, STEPS } from '../types';
import { type SimilarPair, EXPORT_DPI, groundSuggestion, isDarkCloth as darkCloth, matchVerdict, cleanupNote, money, enlargeNote, type Enlarged, mergeSuggestion, printAt, printWidthNote, trapLabel, smallInkNote, type SmallInkReport, DOT_REPORT_MM, dotLabel, dotNote, type SpeckReport, softEdgeNote, tinyInks as pickTiny } from '../lib/print';
import { popEntry, pushEntry, type Entry } from '../lib/history';
import { inkOwner, planSwap, swapPalette, type InkMatch, type LibraryInk } from '../lib/inks';
import { renamed, snapshotColours, type ColourSnapshot } from '../lib/recolour';
import { JOB_KEY, packJob, unpackJob, type SavedJob } from '../lib/job';
import { useAsyncStatus } from './useAsyncStatus';

/** Everything the four steps share: the job, its settings and every action.
 *  The steps are only views of it (components/steps). */
export function useLoomLab() {
  const [step, setStep] = useState<Step>('Upload');
  const [reached, setReached] = useState(0);              // furthest unlocked step index
  const [original, setOriginal] = useState<ImageInfo>();
  const [reducedId, setReducedId] = useState<string>();   // current flat image id
  const [reducedUrl, setReducedUrl] = useState<string>();
  const [palette, setPalette] = useState<Palette[]>([]);
  const [accuracy, setAccuracy] = useState<{ accuracy: number; deltaE: number }>();
  const [softEdge, setSoftEdge] = useState<number>();   // width of any part-transparent rim
  const [similar, setSimilar] = useState<SimilarPair[]>();  // near-identical inks, with merge cost
  const [repeat, setRepeat] = useState<{ x: boolean; y: boolean }>();   // seamless repeat axes
  // palette edits make a new reduced image each time; undo points back at the old one
  type PaletteState = { reducedId?: string; reducedUrl?: string; palette: Palette[];
    accuracy?: { accuracy: number; deltaE: number }; similar?: SimilarPair[] };
  const [history, setHistory] = useState<Entry<PaletteState>[]>([]);
  // the mill's own inks, and the nearest one to each palette colour
  const [library, setLibrary] = useState<LibraryInk[]>([]);
  const [matches, setMatches] = useState<InkMatch[]>([]);
  const [showLibrary, setShowLibrary] = useState(false);
  // inks covering under `smallBelow`% (each a whole screen), and what removing them costs
  const [small, setSmall] = useState<SmallInkReport>();
  const [smallBelow, setSmallBelow] = useState(2);
  const [colorCount, setColorCount] = useState(6);
  const [smoothing, setSmoothing] = useState(0);
  const [view, setView] = useState<'wizard' | 'jobs'>('wizard');   // the job dashboard sits beside the four steps
  const [held, setHeld] = useState(0);                             // jobs waiting for a person
  const [licence, setLicence] = useState<LicenceStatus>();        // this PC's activation
  const [autoCleanup, setAutoCleanup] = useState<{ level: number; grain: number }>();
  const [suggested, setSuggested] = useState<number>();
  const [curve, setCurve] = useState<{ colors: number; accuracy: number }[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [mergeFrom, setMergeFrom] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [previewId, setPreviewId] = useState<string>();   // the proof that goes in the zip
  const [includeVector, setIncludeVector] = useState(false);
  const [fabric, setFabric] = useState('#FFFFFF');     // the cloth being printed on
  const [underbase, setUnderbase] = useState(false);   // white base under the colours
  const [trapPx, setTrapPx] = useState(0);   // films only: lighter inks spread under darker ones; 0 = off
  const [minDot, setMinDot] = useState(0);   // mm: dots smaller than this go to the ink around them; 0 = off
  const [specks, setSpecks] = useState<SpeckReport>();   // dots too small for the mesh, at the print size
  // print width in inches, as typed; empty = the design's own size
  const [widthText, setWidthText] = useState('');
  const [bigProof, setBigProof] = useState<string>();
  const [quoteMeters, setQuoteMeters] = useState('');   // a print run to price
  const [quoteClient, setQuoteClient] = useState('');
  const [hiWidth, setHiWidth] = useState('');             // a high-resolution file of the design
  const [hiRes, setHiRes] = useState<Enlarged>();
  const [quote, setQuote] = useState<{ image_url: string; total: number; per_meter: number; currency: string; quote_no: string }>();     // proof drawn at that width
  const [message, setMessage] = useState('Upload a design to begin.');
  const input = useRef<HTMLInputElement>(null);
  const { status, run, busy, busyLabel } = useAsyncStatus();

  const go = (s: Step) => { const i = STEPS.indexOf(s); setReached(r => Math.max(r, i)); setStep(s); };

  // The job in progress, saved in this browser as it changes: a reload or a
  // closed tab offers to pick it up again (the engine keeps its images 48 h).
  type JobState = { original?: ImageInfo; reached: number; reducedId?: string; reducedUrl?: string; palette: Palette[];
    accuracy?: { accuracy: number; deltaE: number }; softEdge?: number; similar?: SimilarPair[]; repeat?: { x: boolean; y: boolean };
    history: Entry<PaletteState>[]; colorCount: number; smoothing: number; suggested?: number;
    curve: { colors: number; accuracy: number }[]; layers: Layer[]; fabric: string; underbase: boolean;
    widthText: string; includeVector: boolean; trapPx?: number; minDot?: number };
  const [resumable, setResumable] = useState<SavedJob<JobState> | null>(() => {
    try { return unpackJob<JobState>(localStorage.getItem(JOB_KEY), Date.now()); } catch { return null; }
  });
  useEffect(() => {
    if (!original) return;
    const job: JobState = { original, reached, reducedId, reducedUrl, palette, accuracy, softEdge, similar, repeat, history,
      colorCount, smoothing, suggested, curve, layers, fabric, underbase, widthText, includeVector, trapPx, minDot };
    try { localStorage.setItem(JOB_KEY, packJob(step, job, Date.now())); } catch { /* private window / full: just not saved */ }
  }, [original, step, reached, reducedId, reducedUrl, palette, accuracy, softEdge, similar, repeat, history,
      colorCount, smoothing, suggested, curve, layers, fabric, underbase, widthText, includeVector, trapPx, minDot]);

  const forgetJob = () => { setResumable(null); try { localStorage.removeItem(JOB_KEY); } catch { /* nothing kept */ } };
  /** Put the saved job back, as far as its images still exist in the engine. */
  const resumeJob = () => run(async () => {
    if (!resumable) return;
    const j = resumable.state, orig = j.original!;
    const ids = [orig.image_id, j.reducedId, ...j.layers.map(l => l.id), ...j.history.map(h => h.state.reducedId)]
      .filter((x): x is string => !!x);
    const { missing } = await post<{ missing: string[] }>('/image/exists', { ids });
    setResumable(null);
    if (missing.includes(orig.image_id)) {
      forgetJob();
      setMessage('That job’s images have been cleared from the engine (they are kept 48 hours) — import the design again.');
      return;
    }
    const gone = new Set(missing);
    const reducedOk = !!j.reducedId && !gone.has(j.reducedId);
    const layersOk = j.layers.every(l => !gone.has(l.id));
    setOriginal(orig); setColorCount(j.colorCount); setSmoothing(j.smoothing); setSuggested(j.suggested); setCurve(j.curve);
    setFabric(j.fabric); setUnderbase(j.underbase); setWidthText(j.widthText); setIncludeVector(j.includeVector); setTrapPx(j.trapPx ?? 0); setMinDot(j.minDot ?? 0);
    if (reducedOk || orig.layers?.length) {
      setReducedId(j.reducedId); setReducedUrl(j.reducedUrl); setPalette(j.palette); setAccuracy(j.accuracy);
      setSoftEdge(j.softEdge); setSimilar(j.similar); setRepeat(j.repeat);
      setHistory(j.history.filter(h => !h.state.reducedId || !gone.has(h.state.reducedId)));
    }
    const plates = (reducedOk || orig.layers?.length) && layersOk ? j.layers : [];
    setLayers(plates);
    const upTo = Math.min(j.reached, STEPS.indexOf(plates.length ? 'Export' : 'Reduce'));
    setReached(upTo); setStep(STEPS[Math.max(0, Math.min(STEPS.indexOf(resumable.step as Step), upTo))]);
    setMessage(upTo < j.reached
      ? 'Picked up your last job — some of its later steps had been cleared, so redo them from here.'
      : 'Picked up your last job where you left off.');
  }, 'Opening your last job…');

  function loadImported(x: ImageInfo) {
    setOriginal(x); setReducedId(undefined); setReducedUrl(undefined); setAutoCleanup(undefined); setSmoothing(0); setHiRes(undefined);
    setPalette([]); setAccuracy(undefined); setSoftEdge(undefined); setSimilar(undefined); setRepeat(undefined); setHistory([]); setWidthText(''); setBigProof(undefined);
    if (x.layers && x.layers.length) {
      // A multichannel PSD arrives already separated — skip reduce.
      setLayers(x.layers); setReached(STEPS.indexOf('Export')); setStep('Export');
      setMessage(`Imported ${x.layers.length} ready-made screens from this PSD — go straight to export.`);
    } else {
      setLayers([]); go('Reduce');
      setMessage(`Imported ${x.file_name || 'design'} (${x.width}×${x.height}). Choose an ink count and reduce.`);
    }
  }

  type Suggestion = { suggested: number; curve: { colors: number; accuracy: number }[]; smoothing: number; grain: number };
  const autoSuggest = async (x: ImageInfo) => {
    if (x.layers) return;
    try {
      const sug = await post<Suggestion>('/colors/suggest', { image_id: x.image_id });
      setSuggested(sug.suggested); setColorCount(sug.suggested); setCurve(sug.curve || []);
      setAutoCleanup({ level: sug.smoothing, grain: sug.grain }); setSmoothing(sug.smoothing);
    } catch { /* suggestion is best-effort */ }
  };
  const onUpload = (f: File) => run(async () => { const x = await uploadFile<ImageInfo>(f); loadImported(x); await autoSuggest(x); });
  const loadSample = () => run(async () => { const x = await post<ImageInfo>('/image/sample', {}); loadImported(x); await autoSuggest(x); });

  const suggestCount = () => run(async () => {
    if (!original) return;
    const sug = await post<Suggestion>('/colors/suggest', { image_id: original.image_id });
    setSuggested(sug.suggested); setColorCount(sug.suggested); setCurve(sug.curve || []);
    setAutoCleanup({ level: sug.smoothing, grain: sug.grain }); setSmoothing(sug.smoothing);
    setMessage(`Suggested ${sug.suggested} inks — best balance of match vs number of screens.`);
  }, 'Analysing…');

  const doReduce = () => run(async () => {
    if (!original) return;
    const x = await post<ReduceResult>('/colors/reduce', { image_id: original.image_id, colors: colorCount, smoothing });
    setReducedId(x.image_id); setReducedUrl(x.url);
    setPalette(x.palette.map(p => ({ ...p, locked: false })));
    setAccuracy({ accuracy: x.accuracy, deltaE: x.delta_e }); setSoftEdge(x.soft_edge); setSimilar(x.similar); setRepeat(x.repeat); setMergeFrom(null); setHistory([]);
    setMessage(`Reduced to ${x.palette.length} inks — ${x.accuracy}% match (ΔE2000 ${x.delta_e}). Fine-tune the palette or continue.`);
  }, 'Reducing…');

  const refreshAccuracy = async (pal: Palette[]) => {
    if (!original) return;
    const a = await post<{ accuracy: number; delta_e: number; similar?: SimilarPair[] }>('/colors/accuracy',
      { image_id: original.image_id, palette: pal.map(p => p.hex) });
    setAccuracy({ accuracy: a.accuracy, deltaE: a.delta_e }); setSimilar(a.similar);
  };

  const recolor = (i: number, hex: string, name?: string) => run(async () => {
    if (!reducedId || palette[i].locked || hex.toUpperCase() === palette[i].hex.toUpperCase()) return;
    const before = paletteState();
    const x = await post<ImageInfo>('/colors/remap', { image_id: reducedId, source: palette[i].hex, target: hex });
    setHistory(h => pushEntry(h, before, `recolour of ink ${i + 1}`));
    setReducedId(x.image_id); setReducedUrl(x.url);
    // a colour another ink already prints makes them one ink, not two plates of the same colour
    const owner = inkOwner(palette, hex, i);
    const next = swapPalette(palette, palette.map((_, idx) => idx === i ? { name: name ?? '', hex, delta_e: 0 } : null))
      .map(p => p.name === '' ? { ...p, name: undefined } : p);
    setPalette(next); setSimilar(undefined); await refreshAccuracy(next);   // old pairs index the old palette
    setMessage(owner >= 0 ? `Ink ${i + 1} now matches ink ${owner + 1}, so they print as one — ${next.length} inks.`
      : name ? `Ink ${i + 1} is now your ${name}.` : `Ink ${i + 1} recoloured to ${hex.toUpperCase()}.`);
  });

  const mergeInto = (target: number) => {
    if (mergeFrom !== null) mergePair(mergeFrom, target);
  };

  /** Fold ink `from` into ink `target`: every pixel of `from` takes `target`'s colour. */
  const mergePair = (from: number, target: number) => run(async () => {
    if (!reducedId) return;
    if (from === target || palette[target].locked || palette[from].locked) { setMergeFrom(null); return; }
    const before = paletteState();
    const x = await post<ImageInfo>('/colors/remap',
      { image_id: reducedId, source: palette[from].hex, target: palette[target].hex });
    setHistory(h => pushEntry(h, before, `merge of inks ${from + 1} and ${target + 1}`));
    setReducedId(x.image_id); setReducedUrl(x.url);
    const next = palette
      .map((p, idx) => idx === target
        ? { ...p, coverage: Math.round((p.coverage + palette[from].coverage) * 100) / 100, pixels: p.pixels + palette[from].pixels }
        : p)
      .filter((_, idx) => idx !== from);
    setPalette(next); setMergeFrom(null); setSimilar(undefined); await refreshAccuracy(next);
    setMessage(`Merged into one ink — ${next.length} inks now.`);
  });

  const paletteState = (): PaletteState => ({ reducedId, reducedUrl, palette, accuracy, similar });

  useEffect(() => { getJson<{ inks: LibraryInk[] }>('/inks').then(r => setLibrary(r.inks)).catch(() => {}); }, []);
  const paletteKey = palette.map(p => p.hex).join(',');
  useEffect(() => {
    if (!library.length || !palette.length) { setMatches([]); return; }
    let live = true;
    post<{ matches: InkMatch[] }>('/inks/match', { palette: palette.map(p => p.hex) })
      .then(r => { if (live) setMatches(r.matches); }).catch(() => {});
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paletteKey, library]);

  // Small inks: re-priced whenever the palette changes (a merge or a recolour
  // changes what is small and what is close to what).
  const lockKey = palette.map(p => (p.locked ? 1 : 0)).join('');
  useEffect(() => {
    setSmall(undefined);
    if (!reducedId || !original || original.layers?.length || palette.length < 3) return;
    let live = true;
    const t = setTimeout(() => {
      post<SmallInkReport>('/colors/small', { image_id: reducedId, source_id: original.image_id,
        palette: palette.map(p => p.hex), below: smallBelow, locked: palette.filter(p => p.locked).map(p => p.hex) })
        .then(r => { if (live) setSmall(r); }).catch(() => { /* a suggestion only */ });
    }, 400);
    return () => { live = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedId, paletteKey, lockKey, smallBelow]);

  /** Remove the small inks that can go: each of their pixels goes to the
   *  remaining ink closest to its original colour. One undo step. */
  const removeSmall = () => run(async () => {
    if (!small || !reducedId || !original || !small.drop.length) return;
    const before = paletteState();
    const drop = small.drop.map(i => palette[i].hex);
    const x = await post<ImageInfo & { palette: { hex: string; pixels: number; coverage: number }[] }>('/colors/drop',
      { image_id: reducedId, source_id: original.image_id, palette: palette.map(p => p.hex), drop });
    setHistory(h => pushEntry(h, before, `removal of ${drop.length} small ink${drop.length > 1 ? 's' : ''}`));
    setReducedId(x.image_id); setReducedUrl(x.url);
    const cover = new Map(x.palette.map(p => [p.hex.toUpperCase(), p]));
    const next = palette.filter(p => cover.has(p.hex.toUpperCase()))
      .map(p => ({ ...p, pixels: cover.get(p.hex.toUpperCase())!.pixels, coverage: cover.get(p.hex.toUpperCase())!.coverage }));
    setPalette(next); setSimilar(undefined); setMergeFrom(null); await refreshAccuracy(next);
    setMessage(`Removed ${drop.length} small ink${drop.length > 1 ? 's' : ''} — ${next.length} inks now. Undo brings ${drop.length > 1 ? 'them' : 'it'} back.`);
  }, 'Removing small inks…');
  const smallNote = smallInkNote(small, accuracy?.accuracy, palette.length);

  /** The mill's name for ink i: set when it was swapped to a shelf ink, or
   *  when it already is one (within ΔE 1). */
  const inkName = (i: number) => palette[i]?.name
    ?? (matches[i] && matches[i]!.delta_e <= 1 ? matches[i]!.name : undefined);

  const swap = planSwap(palette, matches);
  /** Every unlocked ink with a close shelf ink becomes that ink, in one pass
   *  and one undo step. Inks that land on the same shelf ink become one. */
  const useMyInks = () => run(async () => {
    if (!reducedId || !swap.count) return;
    const before = paletteState();
    const x = await post<ImageInfo>('/colors/repaint', { image_id: reducedId, palette: palette.map(p => p.hex),
      targets: palette.map((p, i) => swap.targets[i]?.hex ?? p.hex) });
    setHistory(h => pushEntry(h, before, 'switch to your inks'));
    setReducedId(x.image_id); setReducedUrl(x.url);
    const next = swapPalette(palette, swap.targets);
    setPalette(next); setSimilar(undefined); setMergeFrom(null); await refreshAccuracy(next);
    setMessage(`${swap.count} ink${swap.count > 1 ? 's' : ''} switched to your own — ${next.length} inks now.`);
  }, 'Switching to your inks…');

  const saveLibrary = (inks: LibraryInk[]) => run(async () => {
    const r = await putJson<{ inks: LibraryInk[] }>('/inks', { inks });
    setLibrary(r.inks);
  });

  /** Step back one palette edit. The engine still has the earlier image, so
   *  this is instant and exact — the score and suggestions come back too. */
  const undo = () => {
    const popped = popEntry(history);
    if (!popped || busy) return;
    const [{ state, label }, rest] = popped;
    setReducedId(state.reducedId); setReducedUrl(state.reducedUrl); setPalette(state.palette);
    setAccuracy(state.accuracy); setSimilar(state.similar); setMergeFrom(null); setHistory(rest);
    setMessage(`Undid the ${label}.`);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // only where Ctrl+Z means "undo my typing": sliders, colour pickers and
      // checkboxes (the before/after slider takes focus on click) don't count
      const t = e.target;
      const typing = (t instanceof HTMLInputElement && ['text', 'number', 'search'].includes(t.type))
        || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey && step === 'Reduce' && !typing) {
        e.preventDefault(); undo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const toggleLock = (i: number) =>
    setPalette(p => p.map((s, idx) => idx === i ? { ...s, locked: !s.locked } : s));

  const doSeparate = () => run(async () => {
    if (!reducedId) return;
    const x = await post<{ layers: Layer[] }>('/separation/create',
      { image_id: reducedId, palette: palette.map(p => p.hex), cleanup: 0 });
    // a screen printing one of the mill's inks is named after it, so the films,
    // plates and job sheet say "Rani Pink 12" instead of "Ink 3"
    setLayers(x.layers.map(l => {
      const i = palette.findIndex(p => p.hex.toUpperCase() === l.color.toUpperCase());
      return { ...l, name: (i >= 0 && inkName(i)) || l.name };
    }));
    go('Separate');
    setMessage(`${x.layers.length} clean plates ready — one ink per screen, no overlap. This preview is exactly what they print.`);
  }, 'Separating…');

  // Toggling is a pure state flip; the combined preview is derived from it by
  // the effect below, so rapid clicks can't drop a toggle or race each other.
  const toggleSkip = (id: string) =>
    setLayers(prev => prev.map(l => l.id === id ? { ...l, skip: !l.skip } : l));

  /** Which ink a screen prints in. The separation is geometry; the colour is a
   *  label on it, so changing it never disturbs the masks. Essential for a
   *  pre-separated PSD, where channel names ("GOLD", "BROWN 120") are all we
   *  have to go on and the Reduce step is skipped entirely. */
  // one debounce per ink: a shared timer let recolouring ink B cancel ink A's
  // pending refresh, leaving A's chip in its old colour
  const thumbTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const setInkColor = (id: string, hex: string) => {
    const color = hex.toUpperCase();
    setLayers(prev => prev.map(l => l.id === id ? { ...l, color } : l));
    clearTimeout(thumbTimers.current[id]);
    thumbTimers.current[id] = setTimeout(async () => {
      try {   // one ink over white == that ink's plate proof, so reuse preview
        const pv = await post<ImageInfo>('/separation/preview', { layers: [{ id, color }], fabric: '#FFFFFF', thumb: true });
        // only if the ink still has this colour — a slow reply for an older
        // pick must not overwrite a newer one
        setLayers(prev => prev.map(l => l.id === id && l.color === color ? { ...l, plate_url: pv.url } : l));
      } catch { /* the swatch already shows the new ink; a stale thumb is cosmetic */ }
    }, 400);
  };

  // Plate colours: any plate's ink changed to any colour, previewed live in the
  // browser (small copies of the screens, tinted and stacked) and handed to the
  // engine only when the operator is done — so dragging a picker never waits.
  const [recolouring, setRecolouring] = useState(false);
  const [snap, setSnap] = useState<ColourSnapshot>({});
  const [live, setLive] = useState<{ width: number; height: number; masks: string[] }>();
  const openRecolour = () => run(async () => {
    setSnap(snapshotColours(layers));
    const r = await post<{ width: number; height: number; masks: string[] }>('/separation/live-masks', { ids: layers.map(l => l.id) });
    setLive(r); setRecolouring(true);
    setMessage('Change any plate to any colour — the preview follows as you pick. Done keeps it, Cancel puts every colour back.');
  }, 'Preparing the live preview…');
  const liveColour = (id: string, hex: string, pickedName?: string) =>
    setLayers(prev => prev.map((l, i) => l.id === id ? { ...l, color: hex.toUpperCase(), name: renamed(l.name, i, pickedName, library) } : l));
  const resetColour = (id: string) =>
    setLayers(prev => prev.map(l => l.id === id && snap[id] ? { ...l, color: snap[id].color, name: snap[id].name } : l));
  const doneRecolour = () => {
    const moved = layers.filter(l => snap[l.id] && snap[l.id].color !== l.color.toUpperCase());
    setRecolouring(false);
    moved.forEach(l => setInkColor(l.id, l.color));          // plate thumbnails in the new inks
    setMessage(moved.length ? `${moved.length} plate${moved.length > 1 ? 's' : ''} recoloured — the proof, plates and job sheet use the new inks.`
      : 'No colours changed.');
  };
  const cancelRecolour = () => {
    setLayers(prev => prev.map(l => snap[l.id] ? { ...l, color: snap[l.id].color, name: snap[l.id].name } : l));
    setRecolouring(false);
    setMessage('Colour changes cancelled — every plate is back to its ink.');
  };
  useEffect(() => { if (step !== 'Separate' && recolouring) doneRecolour(); }, [step]);   // eslint-disable-line react-hooks/exhaustive-deps

  const printing = layers.filter(l => !l.skip);
  // trap is for LoomLab's own separations; a bureau's PSD keeps the trapping it was made with
  const canTrap = !original?.layers?.length && printing.length > 1;
  // likewise tiny-dot cleaning: a bureau's screens are kept exactly as made
  const canClean = !original?.layers?.length;
  const cleaning = canClean && minDot > 0;
  const printingKey = printing.map(l => l.id + l.color).join(',');
  // a locked PC shows the activation screen instead of the steps. The engine
  // may still be starting when the page opens: keep asking until it answers,
  // then look again now and then (a licence can end while the app is open).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const check = () => getJson<LicenceStatus>('/licence')
      .then(st => { setLicence(st); if (!stopped) timer = setTimeout(check, 5 * 60_000); })
      .catch(() => { if (!stopped) timer = setTimeout(check, 3000); });
    check();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  // how many jobs wait for a person, on the header's Jobs button
  useEffect(() => {
    const check = () => getJson<{ total: number }>('/jobs?status=needs_review&stage=new&limit=1')
      .then(r => setHeld(r.total)).catch(() => { /* the engine may be starting */ });
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, [view]);
  // a quote is for these screens: a changed plate or base makes it stale
  useEffect(() => setQuote(undefined), [printingKey, underbase]);
  const previewSeq = useRef(0);

  useEffect(() => {
    if (!layers.length || !printing.length) { setPreviewUrl(undefined); setPreviewId(undefined); return; }
    if (recolouring) return;              // the live preview stands in until Done
    const seq = ++previewSeq.current;
    run(async () => {
      const pv = await post<ImageInfo>('/separation/preview',
        { layers: printing.map(l => ({ id: l.id, color: l.color })), fabric, max_side: SCREEN_SIDE });
      if (seq === previewSeq.current) { setPreviewUrl(pv.url); setPreviewId(pv.image_id); }   // drop out-of-order replies
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printingKey, fabric, recolouring]);

  const cleanup = cleanupNote(autoCleanup?.level, smoothing, autoCleanup?.grain);
  const matchVerdictNote = matchVerdict(accuracy?.accuracy, curve, suggested, colorCount);
  const softEdgeWarning = softEdgeNote(softEdge);
  const merge = mergeSuggestion(similar, palette);
  // how big it prints: the design's own size unless a print width is set, in
  // which case every screen is redrawn at that size with smooth edges
  const widthIn = Number(widthText) > 0 ? Number(widthText) : undefined;
  const at = printAt(original?.width, original?.height, widthIn);
  const widthNote = printWidthNote(original?.width, original?.height, widthIn);
  const resizedWidth = at?.resized && !at.tooLarge ? widthIn : undefined;
  const isDarkCloth = darkCloth(fabric);

  const pickFabric = (hex: string) => {
    setFabric(hex);
    setUnderbase(darkCloth(hex));      // sensible default, still overridable
  };

  // An ink covering almost nothing still costs a whole screen to burn and a
  // pass on the press, so surface it — merging or dropping it saves real money.
  const tinyInks = pickTiny(printing);

  // The ground (the ink the motifs sit on) is usually the cloth itself: print
  // on cloth dyed that colour and its screen — the biggest one — isn't needed.
  const ground = groundSuggestion(layers, fabric);
  const useGroundAsCloth = () => {
    if (!ground) return;
    if (!ground.matches) pickFabric(ground.ink.color);
    setLayers(prev => prev.map(l => l.id === ground.ink.id ? { ...l, skip: true } : l));
    setMessage(`Ink ${layers.indexOf(ground.ink) + 1} left unprinted — the ${ground.ink.color} cloth shows through. One screen fewer.`);
  };

  const exportLayers = () => printing.map(l => ({ id: l.id, name: l.name, color: l.color }));

  const doExport = () => run(async () => {
    if (!printing.length) return;
    await downloadPackage(
      { layers: exportLayers(), dpi: EXPORT_DPI, reg_marks: true, vector: includeVector,
        fabric, underbase, composite_image_id: previewId || reducedId, width_in: resizedWidth, trap_px: canTrap ? trapPx : 0, min_dot_mm: cleaning ? minDot : 0 },
      'loomlab-production.zip');
    setMessage(`Production package downloaded — ${printing.length} plate${printing.length > 1 ? 's' : ''}${underbase ? ' + white under-base' : ''}, ${EXPORT_DPI} DPI TIFF screens at ${at?.inches.join(' × ')} in${includeVector ? ', vector SVG' : ''}${cleaning ? `, tiny dots ${dotLabel(minDot)} cleaned` : ''}${canTrap && trapPx ? `, trap ${trapLabel(trapPx, EXPORT_DPI)}` : ''} and a colour proof.`);
  }, includeVector ? 'Building zip + vectors…' : 'Building zip…');

  const doQuote = () => run(async () => {
    const meters = Number(quoteMeters);
    if (!printing.length || !(meters > 0)) return;
    const q = await post<{ image_url: string; total: number; per_meter: number; currency: string; quote_no: string }>('/quote', {
      meters, client: quoteClient.trim(), underbase, proof_id: previewId || reducedId,
      inks: printing.map(l => ({ name: l.name, hex: l.color, coverage: l.coverage })) });
    setQuote(q);
    setMessage(`Quote ${q.quote_no}: ${money(q.total, q.currency)} for ${meters} m (${money(q.per_meter, q.currency)} per meter).`);
  }, 'Pricing…');

  const doEnlarge = () => run(async () => {
    const w = Number(hiWidth || resizedWidth);
    if (!original || !(w > 0)) return;
    const e = await post<Enlarged>('/image/enlarge', { image_id: original.image_id, width_in: w, dpi: EXPORT_DPI });
    setHiRes(e);
    setMessage(enlargeNote(e).text);
  }, 'Enlarging…');

  const doExportSvg = () => run(async () => {
    if (!printing.length) return;
    await downloadSvg({ layers: exportLayers(), width_in: resizedWidth }, 'loomlab-design.svg');
    setMessage('Vector SVG downloaded — scalable outlines of every ink.');
  }, 'Tracing vectors…');

  const proofSeq = useRef(0);
  useEffect(() => {
    const seq = ++proofSeq.current;
    setBigProof(undefined);
    if (step !== 'Export' || !(resizedWidth || cleaning) || !printing.length) return;
    const t = setTimeout(() => run(async () => {
      const pv = await post<ImageInfo>('/separation/preview',
        { layers: printing.map(l => ({ id: l.id, color: l.color })), fabric, width_in: resizedWidth,
          min_dot_mm: cleaning ? minDot : 0, max_side: SCREEN_SIDE });
      if (seq === proofSeq.current) setBigProof(pv.url);
    }, resizedWidth ? `Drawing at ${resizedWidth} in…` : 'Cleaning tiny dots…'), 700);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, resizedWidth, printingKey, fabric, cleaning, minDot]);

  // How many dots each screen has that the mesh can't hold, at the print size.
  // Informational, so it never blocks the page; the latest request wins.
  const speckSeq = useRef(0);
  useEffect(() => {
    const seq = ++speckSeq.current;
    setSpecks(undefined);
    if (step !== 'Export' || !canClean || !printing.length || at?.tooLarge) return;
    const t = setTimeout(() => {
      post<SpeckReport>('/separation/specks', { layers: printing.map(l => ({ id: l.id, color: l.color })),
        width_in: resizedWidth, min_dot_mm: minDot || DOT_REPORT_MM })
        .then(r => { if (seq === speckSeq.current) setSpecks(r); })
        .catch(() => { /* a hint only */ });
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, canClean, resizedWidth, printingKey, minDot, at?.tooLarge]);
  const dots = dotNote(specks, cleaning);

  const proofUrl = bigProof || (resizedWidth || cleaning ? undefined : previewUrl || (original?.layers ? original.url : reducedUrl));

  return {
    step,
    setStep,
    reached,
    original,
    reducedUrl,
    palette,
    accuracy,
    repeat,
    history,
    library,
    matches,
    showLibrary,
    setShowLibrary,
    small,
    smallBelow,
    setSmallBelow,
    colorCount,
    setColorCount,
    smoothing,
    setSmoothing,
    view,
    setView,
    held,
    setHeld,
    licence,
    setLicence,
    suggested,
    layers,
    mergeFrom,
    setMergeFrom,
    previewUrl,
    includeVector,
    setIncludeVector,
    fabric,
    underbase,
    setUnderbase,
    trapPx,
    setTrapPx,
    minDot,
    setMinDot,
    widthText,
    setWidthText,
    quoteMeters,
    setQuoteMeters,
    quoteClient,
    setQuoteClient,
    hiWidth,
    setHiWidth,
    hiRes,
    setHiRes,
    quote,
    setQuote,
    message,
    input,
    status,
    run,
    busy,
    busyLabel,
    go,
    resumable,
    forgetJob,
    resumeJob,
    onUpload,
    loadSample,
    suggestCount,
    doReduce,
    recolor,
    mergeInto,
    mergePair,
    removeSmall,
    smallNote,
    inkName,
    swap,
    useMyInks,
    saveLibrary,
    undo,
    toggleLock,
    doSeparate,
    toggleSkip,
    setInkColor,
    recolouring,
    snap,
    live,
    openRecolour,
    liveColour,
    resetColour,
    doneRecolour,
    cancelRecolour,
    printing,
    canTrap,
    canClean,
    cleanup,
    matchVerdictNote,
    softEdgeWarning,
    merge,
    at,
    widthNote,
    resizedWidth,
    isDarkCloth,
    pickFabric,
    tinyInks,
    ground,
    useGroundAsCloth,
    doExport,
    doQuote,
    doEnlarge,
    doExportSvg,
    dots,
    proofUrl,
  };
}

export type LoomLab = ReturnType<typeof useLoomLab>;
