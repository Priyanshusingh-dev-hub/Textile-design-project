import { useEffect, useRef, useState } from 'react';
import { post, getJson, putJson, uploadFile, downloadPackage, downloadSvg, imageUrl, screenUrl, SCREEN_SIDE } from './api';
import type { ImageInfo, Palette, Layer, ReduceResult, Step } from './types';
import type { SimilarPair } from './lib/print';
import { popEntry, pushEntry, type Entry } from './lib/history';
import { inkOwner, matchLabel, parseInkList, planSwap, swapPalette, type InkMatch, type LibraryInk } from './lib/inks';
import { InkLibrary } from './components/InkLibrary';
import { LivePreview } from './components/LivePreview';
import { PlateColours } from './components/PlateColours';
import { changedCount, renamed, snapshotColours, type ColourSnapshot } from './lib/recolour';
import { JOB_KEY, jobSummary, packJob, unpackJob, type SavedJob } from './lib/job';
import { STEPS } from './types';
import { useAsyncStatus } from './hooks/useAsyncStatus';
import { BeforeAfter } from './components/BeforeAfter';
import { Zoomable } from './components/Zoomable';
import { EXPORT_DPI, groundSuggestion, isDarkCloth as darkCloth, matchVerdict, cleanupNote, mergeSuggestion, printAt, printWidthNote, repeatNote, TRAP_CHOICES, trapLabel, SMALL_CHOICES, smallInkNote, type SmallInkReport, DOT_CHOICES, DOT_REPORT_MM, dotLabel, dotNote, type SpeckReport,
         separationNote, softEdgeNote, tinyInks as pickTiny } from './lib/print';

export default function App() {
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
  const [bigProof, setBigProof] = useState<string>();     // proof drawn at that width
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
    setOriginal(x); setReducedId(undefined); setReducedUrl(undefined); setAutoCleanup(undefined); setSmoothing(0);
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

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="loom">L</span><div>LoomLab<small>COLOR SEPARATION</small></div></div>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s} className={s === step ? 'on' : i <= reached ? 'done' : ''}>
              <button disabled={i > reached || busy} onClick={() => setStep(s)}><b>{i + 1}</b><span>{s}</span></button>
            </li>
          ))}
        </ol>
        <div className={'badge s-' + status.state}>{status.state === 'processing' ? 'WORKING' : status.state === 'failed' ? 'ERROR' : status.state === 'done' ? 'DONE' : 'READY'}</div>
      </header>

      <main>
        {step === 'Upload' && (
          <section className="stage">
            {original && !original.layers
              ? <div className="canvas"><img src={screenUrl(original.url)} alt="design" /></div>
              : <div className="drop" onClick={() => input.current?.click()}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) onUpload(f); }}>
                  <h2>Drop a design here</h2>
                  <p>PNG · JPG · WEBP · TIFF · PSD — up to 80 MB</p>
                  {resumable && !original && (
                    <div className="resume" onClick={e => e.stopPropagation()}>
                      <span>Continue your last job<small>{jobSummary(resumable, Date.now())}</small></span>
                      <button className="primary" disabled={busy} onClick={resumeJob}>Continue</button>
                      <button className="mini" disabled={busy} onClick={forgetJob} title="Forget it and start a new design">✕</button>
                    </div>
                  )}
                  <div className="row">
                    <button className="primary" disabled={busy} onClick={e => { e.stopPropagation(); input.current?.click(); }}>Choose file</button>
                    <button className="secondary" disabled={busy} onClick={e => { e.stopPropagation(); loadSample(); }}>Try a sample</button>
                  </div>
                </div>}
            {original && !original.layers && <div className="row center"><button className="primary" onClick={() => go('Reduce')}>Continue to Reduce →</button><button className="secondary" onClick={() => input.current?.click()}>Replace</button></div>}
          </section>
        )}

        {step === 'Reduce' && (
          <section className="stage two">
            <div className="stage-main">
              {reducedUrl && original
                ? <BeforeAfter before={screenUrl(original.url)} after={screenUrl(reducedUrl)} />
                : original ? <div className="canvas"><img src={screenUrl(original.url)} alt="design" /></div>
                : <div className="canvas empty">Upload a design first.</div>}
            </div>
            <aside className="panel">
              <h3>Reduce colors</h3>
              <label>Print inks<output>{colorCount}</output></label>
              <input type="range" min={1} max={20} value={colorCount} disabled={busy}
                onChange={e => setColorCount(Number(e.target.value))} />
              <div className="suggest-row">
                {suggested ? <span className="suggest-chip" title="Recommended balance of match vs number of screens">✨ suggested: {suggested}</span> : <span />}
                <button className="mini" disabled={busy || !original} onClick={suggestCount}>{suggested ? 're-suggest' : '✨ suggest count'}</button>
              </div>
              <label>Texture cleanup</label>
              <select className="select" value={smoothing} disabled={busy}
                onChange={e => setSmoothing(Number(e.target.value))}>
                <option value={0}>Off — keeps every outline and dot</option>
                <option value={1}>Light — grainy scans</option>
                <option value={2}>Medium — heavy grain, fabric weave</option>
                <option value={3}>Strong — very noisy</option>
              </select>
              {cleanup && <p className={cleanup.tone + ' cleanup-note'}>{cleanup.text}</p>}
              <button className={(reducedUrl ? 'secondary' : 'primary') + ' wide'} disabled={busy || !original} onClick={doReduce}>
                {busy && busyLabel === 'Reducing…' ? busyLabel : reducedUrl ? 'Re-reduce' : 'Reduce design'}
              </button>
              {accuracy && (
                <div className="accuracy">
                  <div className="accuracy-bar"><span style={{ width: accuracy.accuracy + '%' }} /></div>
                  <b>{accuracy.accuracy}% match</b>
                  <small>mean ΔE2000 {accuracy.deltaE} vs original</small>
                </div>
              )}
              {matchVerdictNote && <p className={matchVerdictNote.tone === 'warn' ? 'warn' : 'hint'}>{matchVerdictNote.text}</p>}
              {softEdgeWarning && <p className="warn">{softEdgeWarning}</p>}
              {repeatNote(repeat) && <p className="hint">{repeatNote(repeat)}</p>}
              {merge && (
                <div className="hint merge-hint">
                  <span className="pair">
                    <span className="plate-swatch" style={{ background: palette[merge.keep].hex }} />
                    <span className="plate-swatch" style={{ background: palette[merge.drop].hex }} />
                  </span>
                  <p>
                    Inks <b>{merge.keep + 1}</b> and <b>{merge.drop + 1}</b> look almost the same (ΔE {merge.delta_e}).
                    Merging them saves a screen; the match goes from {accuracy?.accuracy}% to {merge.accuracy}%.
                  </p>
                  <button className="mini go" disabled={busy} onClick={() => mergePair(merge.drop, merge.keep)}>Merge them</button>
                </div>
              )}
              {/* the way forward sits under the score, not below every palette
                  row — at 10 inks on a laptop screen it was off the bottom */}
              {!!palette.length && (
                <button className="primary wide" disabled={busy} onClick={doSeparate}>
                  {busy && busyLabel === 'Separating…' ? busyLabel : 'Separate into plates →'}
                </button>
              )}
              {smallNote && (
                <div className="hint small-hint">
                  <p>{smallNote.text}</p>
                  <div className="small-row">
                    {smallNote.action && <button className="mini go" disabled={busy} onClick={removeSmall}>{smallNote.action}</button>}
                    <label>small = under
                      <select className="select mini-select" value={smallBelow} disabled={busy}
                        onChange={e => setSmallBelow(Number(e.target.value))}>
                        {SMALL_CHOICES.map(v => <option key={v} value={v}>{v}%</option>)}
                      </select>
                    </label>
                  </div>
                </div>
              )}
              {!!palette.length && (
                <>
                  <div className="palette-head">
                    <span>Palette · {palette.length} inks</span>
                    {mergeFrom !== null && <em>pick an ink to merge into…</em>}
                    {mergeFrom === null && !!history.length && (
                      <button className="mini" disabled={busy} onClick={undo}
                        title={`Undo the ${history[history.length - 1].label} (Ctrl+Z)`}>↶ Undo</button>
                    )}
                    <button className="mini" onClick={() => setShowLibrary(true)}
                      title="The inks your mill already has — match the palette to them">My inks ({library.length})</button>
                  </div>
                  {swap.count > 0 && (
                    <button className="secondary wide lib-all" disabled={busy} onClick={useMyInks}>
                      Use my inks for {swap.count} of {palette.length}
                    </button>
                  )}
                  <div className="palette">
                    {palette.map((p, i) => (
                      <div className={'swatch' + (mergeFrom === i ? ' picking' : '')} key={p.hex + i}>
                        <label className="swatch-color" style={{ background: p.hex }} title={p.locked ? 'Locked' : 'Click to recolor this ink'}>
                          {!p.locked && <span className="swatch-edit">✎</span>}
                          <input type="color" value="#000000" disabled={busy || p.locked}
                            onChange={e => recolor(i, e.target.value)} />
                        </label>
                        <div className="swatch-info">
                          <b>{p.hex}</b>
                          <small>{p.coverage}% · {inkName(i) ?? `Ink ${i + 1}`}</small>
                          {(() => {
                            const m = matches[i], label = matchLabel(m);
                            if (!m || !label || label.tone === 'same' || p.name) return null;
                            const owner = inkOwner(palette, m.hex, i);
                            if (label.tone === 'close' && owner >= 0)
                              return <span className="lib-match far" title="Using it here would print both as one ink">
                                <span className="dot" style={{ background: m.hex }} />≈ {m.name} · already ink {owner + 1}</span>;
                            return label.tone === 'close' && !p.locked
                              ? <button className="lib-match close" disabled={busy} title={`Use ${m.name} (${m.hex})`}
                                  onClick={() => recolor(i, m.hex, m.name)}>
                                  <span className="dot" style={{ background: m.hex }} />{label.text}</button>
                              : <span className={'lib-match ' + label.tone}>
                                  <span className="dot" style={{ background: m.hex }} />{label.text}</span>;
                          })()}
                          <div className="coverage-bar"><span style={{ width: Math.min(100, p.coverage) + '%' }} /></div>
                        </div>
                        <div className="swatch-tools">
                          <button className="mini" title={p.locked ? 'Unlock' : 'Lock'} onClick={() => toggleLock(i)}>{p.locked ? '🔒' : '🔓'}</button>
                          {palette.length > 2 && !p.locked && (
                            mergeFrom === null
                              ? <button className="mini" title="Merge this ink into another" disabled={busy} onClick={() => setMergeFrom(i)}>merge</button>
                              : mergeFrom === i
                                ? <button className="mini" onClick={() => setMergeFrom(null)}>cancel</button>
                                : <button className="mini go" disabled={busy} onClick={() => mergeInto(i)}>→ here</button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="hint">Click a swatch to recolor · <b>merge</b> combines two inks · <b>🔓</b> locks an ink. Re-reduce to start the palette over.</p>
                </>
              )}
            </aside>
          </section>
        )}

        {showLibrary && (
          <InkLibrary inks={library} palette={palette.map((p, i) => ({ hex: p.hex, name: inkName(i) }))}
            busy={busy} parse={parseInkList} onSave={saveLibrary} onClose={() => setShowLibrary(false)} />
        )}
        {step === 'Separate' && (
          <section className="stage two with-strip">
            <div className="stage-main">
              <div className="preview-head">{recolouring
                ? <>Live preview — your {printing.length} screen{printing.length !== 1 ? 's' : ''} in the colours you are picking</>
                : <>Combined result — exactly what your {printing.length} screen{printing.length !== 1 ? 's' : ''} will print</>}</div>
              <Zoomable>
                {recolouring && live
                  ? <LivePreview masks={live.masks.map(imageUrl)} colors={layers.map(l => (l.skip ? null : l.color))}
                      fabric={fabric} width={live.width} height={live.height} exclusive={!original?.layers?.length} />
                  : previewUrl ? <img src={screenUrl(previewUrl)} alt="combined print preview" />
                  : <div className="canvas empty">Every ink hidden — nothing prints.</div>}
              </Zoomable>
              <div className="plate-strip">
                {layers.map((l, i) => (
                  <figure className={'plate-chip' + (l.skip ? ' skipped' : '')} key={l.id}
                    role="switch" aria-checked={!l.skip} tabIndex={0}
                    aria-label={`Ink ${i + 1}${l.name && l.name !== `Ink ${i + 1}` ? ` (${l.name})` : ''}, ${l.coverage}% coverage — ${l.skip ? 'not printed (fabric)' : 'printing'}`}
                    title={l.skip ? 'Hidden (fabric) — click to print' : 'Printing — click to mark as fabric'}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSkip(l.id); } }}
                    onClick={() => toggleSkip(l.id)}>
                    <div className="plate-chip-img"><img src={l.plate_url ? imageUrl(l.plate_url) : screenUrl(l.url)} alt={l.name} /></div>
                    <figcaption>
                      <span className="plate-line">
                        {/* the chip itself is a switch that takes Enter/Space, so the
                            picker must keep its own keys — otherwise opening it with
                            the keyboard also drops the ink from the print */}
                        <label className="plate-swatch editable" style={{ background: l.color }}
                          title={`Ink colour ${l.color} — click to change`}
                          onClick={e => e.stopPropagation()}
                          onKeyDown={e => e.stopPropagation()}>
                          <input type="color" value={l.color} disabled={busy}
                            aria-label={`Ink colour for ${l.name || `ink ${i + 1}`}`}
                            onClick={e => e.stopPropagation()}
                            onKeyDown={e => e.stopPropagation()}
                            onChange={e => (recolouring ? liveColour(l.id, e.target.value) : setInkColor(l.id, e.target.value))} />
                        </label>
                        {i + 1}<small>{l.coverage}%</small>
                      </span>
                      {l.name && l.name !== `Ink ${i + 1}` &&
                        <span className="plate-ink-name" title={l.name}>{l.name}</span>}
                    </figcaption>
                  </figure>
                ))}
              </div>
            </div>
            {recolouring ? (
            <aside className="panel">
              <PlateColours plates={layers} snapshot={snap} library={library} fabric={fabric}
                onColour={liveColour} onFabric={pickFabric} onReset={resetColour}
                onDone={doneRecolour} onCancel={cancelRecolour} changed={changedCount(layers, snap)} />
            </aside>
            ) : (
            <aside className="panel">
              <h3>Separation</h3>
              <p className="muted">{separationNote(!!original?.layers, original?.overlap)} Click a plate to hide your <b>fabric</b> colour (it won't be printed).</p>
              <div className="summary">
                <div><small>PRINTING</small><b>{printing.length}{printing.length !== layers.length ? ` / ${layers.length}` : ''}</b></div>
                <div><small>MATCH</small><b>{accuracy ? accuracy.accuracy + '%' : '—'}</b></div>
              </div>
              <label>Cloth colour</label>
              <div className="cloth-row">
                {['#FFFFFF', '#EDE3CC', '#1B2A1F', '#16202E', '#221A16'].map(hx => (
                  <button key={hx} className={'cloth-swatch' + (fabric.toUpperCase() === hx ? ' on' : '')}
                    style={{ background: hx }} title={hx} aria-label={`Cloth ${hx}`}
                    onClick={() => pickFabric(hx)} />
                ))}
                <label className="cloth-swatch custom" style={{ background: fabric }} title="Pick any cloth colour">
                  ✎<input type="color" value={fabric} onChange={e => pickFabric(e.target.value.toUpperCase())} />
                </label>
              </div>
              {isDarkCloth && <p className="muted">Dark cloth — a white under-base is included so the inks stay bright.</p>}
              {ground && (
                <div className="hint ground-hint">
                  <span className="plate-swatch" style={{ background: ground.ink.color }} />
                  <p>
                    {ground.matches
                      ? <>Ink <b>{layers.indexOf(ground.ink) + 1}</b> is the ground ({ground.ink.coverage}% of the design) and matches your cloth. Leave it unprinted — the cloth shows through — and save the biggest screen.</>
                      : <>Ink <b>{layers.indexOf(ground.ink) + 1}</b> is the ground — {ground.ink.coverage}% of the design. Print on cloth already dyed this colour and that screen, the biggest, isn't needed.</>}
                  </p>
                  <button className="mini go" disabled={busy} onClick={useGroundAsCloth}>
                    {ground.matches ? "Don't print it" : 'Use as cloth colour'}
                  </button>
                </div>
              )}
              {!!tinyInks.length && (
                <p className="warn">
                  {tinyInks.length === 1
                    ? <>Ink <b>{layers.indexOf(tinyInks[0]) + 1}</b> covers only {tinyInks[0].coverage}% — a whole screen for almost nothing.</>
                    : <><b>{tinyInks.length} inks</b> cover under 0.5% each — whole screens for almost nothing.</>}
                  {' '}Hide {tinyInks.length === 1 ? 'it' : 'them'} here, or merge in the palette, to save a screen.
                </p>
              )}
              <button className="secondary wide recolour-open" disabled={busy || !layers.length} onClick={openRecolour}
                title="Change any plate's ink to any colour, with a live preview">🎨 Change plate colours</button>
              <button className="primary wide" disabled={busy || !printing.length} onClick={() => go('Export')}>Continue to Export →</button>
              {!original?.layers && <button className="secondary wide" disabled={busy} onClick={() => go('Reduce')}>← Back to palette</button>}
            </aside>
            )}
          </section>
        )}

        {step === 'Export' && (
          <section className="stage two">
            <div className="stage-main">
              <div className="preview-head">Final proof — {printing.length} ink{printing.length !== 1 ? 's' : ''}, print-ready{resizedWidth ? `, drawn at ${at?.inches.join(' × ')} in (zoom in to check edges)` : ''}</div>
              <Zoomable>
                {proofUrl ? <img src={screenUrl(proofUrl)} alt="proof" />
                  : <div className="canvas empty">{resizedWidth ? `Drawing the screens at ${resizedWidth} in…` : 'Separate a design first.'}</div>}
              </Zoomable>
            </div>
            <aside className="panel">
              <h3>Export production package</h3>
              <p className="pack-line">
                <b>screens/</b> B&amp;W TIFF films, {EXPORT_DPI} DPI, registration marks · <b>plates/</b> colour proof per ink
                · <b>proof.png</b> · <b>job-sheet.png</b> to pin up at the press
                {underbase && <> · <b>0-Underbase</b> printed first</>}
                {includeVector && <> · <b>vector/</b> SVG outlines</>}
              </p>
              <div className="summary">
                <div><small>PLATES</small><b>{printing.length}</b></div>
                <div><small>DPI</small><b>{EXPORT_DPI}</b></div>
                {at && <div className="wide-cell"><small>PRINTS AT</small><b>{at.label}</b></div>}
              </div>
              <label htmlFor="print-width">Print width</label>
              <div className="width-row">
                {/* never locked while busy: the proof redraws after a pause in typing,
                    and locking the box then would trap "1" on the way to "12" */}
                <input id="print-width" className="width-input" type="number" min={0.5} max={200} step={0.1}
                  inputMode="decimal"
                  placeholder={at ? String(printAt(original?.width, original?.height)!.inches[0]) : ''}
                  value={widthText} onChange={e => setWidthText(e.target.value)} />
                <span className="unit">in</span>
                {widthText && <button className="mini" disabled={busy} onClick={() => setWidthText('')}>own size</button>}
              </div>
              {widthNote && <p className={widthNote.tone}>{widthNote.text}</p>}
              {printing.length !== layers.length && <p className="muted">{layers.length - printing.length} ink marked as fabric won't be printed.</p>}
              <label className="check">
                <input type="checkbox" checked={underbase} disabled={busy} onChange={e => setUnderbase(e.target.checked)} />
                White under-base screen (for non-white cloth)
              </label>
              <label className="check">
                <input type="checkbox" checked={includeVector} disabled={busy} onChange={e => setIncludeVector(e.target.checked)} />
                Include scalable vector (SVG) outlines
              </label>
              {canClean && (
                <>
                  <label className="check trap-row" title="A screen's mesh can't hold very small dots: they print as nothing or clog and print as dirt. Cleaning gives each one to the ink around it (still one ink per pixel).">
                    Clean tiny dots
                    <select className="select mini-select" value={minDot} disabled={busy} onChange={e => setMinDot(Number(e.target.value))}>
                      {DOT_CHOICES.map(mm => <option key={mm} value={mm}>{dotLabel(mm)}</option>)}
                    </select>
                  </label>
                  {dots && <p className={(dots.tone === 'hint' ? 'hint-note' : 'muted') + ' small-note'}>{dots.text}</p>}
                </>
              )}
              {canTrap && (
                <>
                  <label className="check trap-row" title="Only if your prints show thin lines of cloth between colours: each lighter ink is spread under the darker inks it touches, on the films only. Printed light to dark, the print looks exactly like the proof.">
                    Trap between colours
                    <select className="select mini-select" value={trapPx} disabled={busy} onChange={e => setTrapPx(Number(e.target.value))}>
                      {TRAP_CHOICES.map(px => <option key={px} value={px}>{trapLabel(px, EXPORT_DPI)}</option>)}
                    </select>
                  </label>
                  {!!trapPx && <p className="muted small-note">Lighter inks spread {trapLabel(trapPx, EXPORT_DPI)} under darker ones on the films — print in the job sheet's order.</p>}
                </>
              )}
              <button className="primary wide" disabled={busy || !printing.length || !!at?.tooLarge} onClick={doExport}>{busy && busyLabel ? busyLabel : '⬇ Download .zip'}</button>
              <button className="secondary wide" disabled={busy || !printing.length} onClick={doExportSvg}>{busy && busyLabel === 'Tracing vectors…' ? busyLabel : '⬇ Vector SVG only'}</button>
              <button className="secondary wide" disabled={busy} onClick={() => go('Separate')}>← Back to plates</button>
            </aside>
          </section>
        )}
      </main>

      <footer>
        <span className={status.state === 'failed' ? 'err' : ''}>{status.state === 'failed' ? status.message : message}</span>
        <span>{original ? `${original.width}×${original.height}` : 'no design'}{palette.length ? ` · ${palette.length} inks` : ''}</span>
      </footer>

      <input ref={input} hidden type="file"
        accept="image/png,image/jpeg,image/webp,image/tiff,.psd,image/vnd.adobe.photoshop"
        onChange={e => e.target.files?.[0] && onUpload(e.target.files[0])} disabled={busy} />
    </div>
  );
}
