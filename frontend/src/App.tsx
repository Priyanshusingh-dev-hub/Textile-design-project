import { useEffect, useRef, useState } from 'react';
import { post, postFile, download } from './api';
import type { ImageInfo, Palette, Layer, Seam, View, SeparationMode, Intent, DesignDna, UploadResult, ReduceResult, MapResult, ProjectFile, Mapping } from './types';
import { useAsyncStatus } from './hooks/useAsyncStatus';
import { StatusBadge } from './components/shared';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { CanvasPreview } from './components/CanvasPreview';
import { PlatesGallery } from './components/PlatesGallery';
import { AiInstructionsView } from './components/AiInstructionsView';
import { UploadPanel } from './components/UploadPanel';
import { ColorAnalysisPanel } from './components/ColorAnalysisPanel';
import { ColorMappingPanel } from './components/ColorMappingPanel';
import { SeparationPanel } from './components/SeparationPanel';
import { LayerPanel } from './components/LayerPanel';
import { RepeatPanel } from './components/RepeatPanel';
import { PreviewPanel } from './components/PreviewPanel';
import { ExportPanel } from './components/ExportPanel';
import { Footer } from './components/Footer';

// One undo step: the image plus the palette that belongs to it, so undoing a
// Reduce or a colour mapping also restores the inks Separation will use.
type Snapshot = { img: ImageInfo; palette: Palette[] };

const DEFAULT_MAPPING: Mapping = { source: '#d84876', target: '#b3203a' };
const SEPARATION_MODES: SeparationMode[] = ['flat', 'gradient', 'region'];
const INTENTS: Intent[] = ['exact_recreation', 'premium_improvement', 'color_change', 'new_variation', 'same_style_new', 'print_optimization'];
const REPEAT_MODES = ['grid', 'half-drop', 'brick', 'mirror'];

const need = <T,>(value: T | undefined | null, message: string): T => { if (!value) throw new Error(message); return value; };
const baseName = (fileName: string) => fileName.replace(/\.[^.]+$/, '') || 'loomlab-project';
const safeFileName = (name: string) => name.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '') || 'loomlab-project';
const hexToRgb = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
const sameHex = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

// After source -> target is painted onto the image, the palette has to follow,
// otherwise Separation would still look for the old ink. A target that is
// already in the palette absorbs the source instead of becoming a duplicate.
function mapPalette(palette: Palette[], source: string, target: string): Palette[] {
  const hit = palette.find(p => sameHex(p.hex, source));
  if (!hit) return palette;
  const existing = palette.find(p => p !== hit && sameHex(p.hex, target));
  if (existing) return palette.filter(p => p !== hit).map(p => p === existing ? { ...p, pixels: p.pixels + hit.pixels, coverage: +(p.coverage + hit.coverage).toFixed(2) } : p);
  return palette.map(p => p === hit ? { ...p, hex: target.toUpperCase(), rgb: hexToRgb(target) } : p);
}

export default function App() {
  const [view, setView] = useState<View>('Import');
  const [img, setImg] = useState<ImageInfo>();
  const [original, setOriginal] = useState<ImageInfo>();
  const [projectName, setProjectName] = useState('');
  const [palette, setPalette] = useState<Palette[]>([]);
  const [accuracy, setAccuracy] = useState<{ accuracy: number; deltaE: number } | null>(null);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [colorCount, setColorCount] = useState(6);
  const [message, setMessage] = useState('Ready — import a design to begin.');
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [future, setFuture] = useState<Snapshot[]>([]);
  const [repeatMode, setRepeatMode] = useState('grid');
  const [seam, setSeam] = useState<Seam>();
  const [mapping, setMapping] = useState<Mapping>(DEFAULT_MAPPING);
  const [mapTolerance, setMapTolerance] = useState(10);
  const [separationMode, setSeparationMode] = useState<SeparationMode>('flat');
  const [cleanup, setCleanup] = useState(2);
  const [edgeStrength, setEdgeStrength] = useState(12);
  const [minRegion, setMinRegion] = useState(40);
  const [regionReduce, setRegionReduce] = useState(false);
  const [aiIntent, setAiIntent] = useState<Intent>('premium_improvement');
  const [fidelity, setFidelity] = useState(85);
  const [userRequest, setUserRequest] = useState('');
  const [aiDescription, setAiDescription] = useState('');
  const [dna, setDna] = useState<DesignDna>();
  const [brief, setBrief] = useState('');
  const [instruction, setInstruction] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const projectInput = useRef<HTMLInputElement>(null);
  const compositeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const compositeSeq = useRef(0);
  const { status, run, busy } = useAsyncStatus();

  const apply = (next: ImageInfo, nextPalette: Palette[] = palette) => {
    if (img) setHistory(h => [...h, { img, palette }]);
    setFuture([]); setImg(next); setPalette(nextPalette);
  };

  // A new design (import, sample or project) starts a clean workspace: no
  // undo back into the previous design, no stale palette, layers or analysis.
  const startWith = (next: ImageInfo, first: ImageInfo = next) => {
    clearTimeout(compositeTimer.current); compositeSeq.current++;
    setImg(next); setOriginal(first); setHistory([]); setFuture([]);
    setPalette([]); setAccuracy(null); setLayers([]); setSeam(undefined);
    setDna(undefined); setBrief(''); setInstruction('');
  };

  const settings = { colorCount, regionReduce, separationMode, cleanup, edgeStrength, minRegion, repeatMode, mapping, mapTolerance, aiIntent, fidelity, userRequest, aiDescription };
  const restoreSettings = (s: Record<string, unknown>) => {
    const num = (key: string, set: (n: number) => void) => { if (typeof s[key] === 'number') set(s[key] as number); };
    const str = (key: string, set: (v: string) => void) => { if (typeof s[key] === 'string') set(s[key] as string); };
    num('colorCount', setColorCount); num('cleanup', setCleanup); num('edgeStrength', setEdgeStrength);
    num('minRegion', setMinRegion); num('mapTolerance', setMapTolerance); num('fidelity', setFidelity);
    str('userRequest', setUserRequest); str('aiDescription', setAiDescription);
    if (typeof s.regionReduce === 'boolean') setRegionReduce(s.regionReduce);
    if (SEPARATION_MODES.includes(s.separationMode as SeparationMode)) setSeparationMode(s.separationMode as SeparationMode);
    if (INTENTS.includes(s.aiIntent as Intent)) setAiIntent(s.aiIntent as Intent);
    if (REPEAT_MODES.includes(s.repeatMode as string)) setRepeatMode(s.repeatMode as string);
    const m = s.mapping as Mapping | undefined;
    if (m && /^#[0-9a-f]{6}$/i.test(m.source) && /^#[0-9a-f]{6}$/i.test(m.target)) setMapping({ source: m.source.toLowerCase(), target: m.target.toLowerCase() });
  };

  const upload = (f: File) => run(async () => {
    const x = await postFile<UploadResult>('/image/upload', f);
    startWith(x); setProjectName(baseName(f.name));
    if (x.layers?.length) {
      setLayers(x.layers.map(l => ({ ...l, visible: true, opacity: 100 }))); setView('Layers');
      setMessage(`Imported ${x.layers.length} pre-separated screens from this multichannel PSD — no color analysis needed.`);
    } else {
      setMessage(`Imported ${x.width} × ${x.height}px. Analyze colors next.`); setView('Color Analysis');
    }
  });
  const openProject = (f: File) => run(async () => {
    const p = await postFile<ProjectFile>('/project/import', f);
    startWith(p.image, p.original);
    setProjectName(p.name); setPalette(p.palette); restoreSettings(p.settings);
    setLayers(p.layers.map(l => ({ ...l, visible: l.visible !== false, opacity: l.opacity ?? 100 })));
    setView(p.layers.length ? 'Layers' : 'Color Analysis');
    setMessage(`Opened project “${p.name}”.`);
  });
  const openFile = (f: File) => f.name.toLowerCase().endsWith('.textileproj') ? openProject(f) : upload(f);
  const loadSample = () => run(async () => {
    const x = await post<ImageInfo>('/image/sample', {});
    startWith(x); setProjectName('loomlab-sample-floral'); setView('Color Analysis');
    setMessage('Sample floral pattern loaded — analyze its palette to begin.');
  });
  const analyze = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const x = await post<{ palette: Palette[]; accuracy: number; delta_e: number }>('/colors/analyze', { image_id: cur.image_id, colors: colorCount });
    setPalette(x.palette); setAccuracy({ accuracy: x.accuracy, deltaE: x.delta_e });
    setMessage(`${x.palette.length} dominant colors found — ${x.accuracy}% match (ΔE2000 ${x.delta_e}).`);
  });
  const reduce = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const x = await post<ReduceResult>('/colors/reduce', { image_id: cur.image_id, colors: colorCount, region: regionReduce, edge_strength: edgeStrength, min_region: minRegion });
    apply(x, x.palette); setAccuracy({ accuracy: x.accuracy, deltaE: x.delta_e });
    setMessage(`Reduced to ${x.palette.length} print colors${regionReduce ? ' (region-flattened)' : ''} — ${x.accuracy}% match (ΔE2000 ${x.delta_e}).`);
  });
  const map = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const x = await post<MapResult>('/colors/map', { image_id: cur.image_id, mappings: [{ ...mapping, enabled: true }], threshold: mapTolerance });
    if (!x.changed_pixels) throw new Error(`No pixels are within tolerance ${mapTolerance} of ${mapping.source.toUpperCase()} — pick the source from the palette or raise the tolerance.`);
    apply(x, mapPalette(palette, mapping.source, mapping.target));
    setMessage(`Mapped ${x.changed_percent}% of the design from ${mapping.source.toUpperCase()} to ${mapping.target.toUpperCase()}.`);
  });
  const analyzeDesign = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const d = await post<DesignDna>('/design/dna', { image_id: cur.image_id, description: aiDescription });
    setDna(d); setMessage('Design DNA ready — set your goal and generate instructions.');
  });
  const generateInstructions = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const o = await post<{ dna: DesignDna; brief: string; instruction: string }>('/design/instructions', { image_id: cur.image_id, intent: aiIntent, fidelity, user_request: userRequest, description: aiDescription });
    setDna(o.dna); setBrief(o.brief); setInstruction(o.instruction);
    setMessage('AI instructions generated — edit if needed, then copy.');
  });
  const separate = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    need(palette.length, 'Analyze or reduce colors first — separations are made from the palette.');
    const x = await post<{ layers: Layer[] }>('/separation/create', { image_id: cur.image_id, palette: palette.map(p => p.hex), mode: separationMode, cleanup, edge_strength: edgeStrength, min_region: minRegion });
    clearTimeout(compositeTimer.current); compositeSeq.current++;
    setLayers(x.layers.map(l => ({ ...l, visible: true, opacity: 100 })));
    setView('Layers');
    setMessage(separationMode === 'gradient' ? `${x.layers.length} soft tonal ink layers are ready.` : separationMode === 'region' ? `${x.layers.length} region-flattened ink layers are ready — one flat colour per shape.` : `${x.layers.length} exclusive spot-color layers are ready.`);
  });
  const halftonePreview = (index: number) => run(async () => {
    const layer = layers[index]; if (!layer) return;
    const x = await post<ImageInfo>('/halftone/preview', { image_id: layer.id, cell_size: 8, angle: 45 });
    setLayers(ls => ls.map(l => l.id === layer.id ? { ...l, halftonePreviewUrl: x.url } : l));
    setMessage(`Halftone dot preview generated for ${layer.name}.`);
  });
  // Layer toggles and opacity drags fire rapidly: debounce them and only let
  // the newest request update the canvas, so an older response that arrives
  // late can never overwrite the latest state.
  const recomposite = (next: Layer[]) => {
    clearTimeout(compositeTimer.current);
    const seq = ++compositeSeq.current;
    compositeTimer.current = setTimeout(async () => {
      try {
        const preview = await post<ImageInfo>('/separation/composite-layers', { layers: next.map(x => ({ id: x.id, color: x.color, opacity: x.visible ? (x.opacity ?? 100) : 0 })) });
        if (seq === compositeSeq.current) setImg(preview);
      } catch (e) {
        if (seq === compositeSeq.current) setMessage(e instanceof Error ? e.message : 'Could not update the layer preview.');
      }
    }, 120);
  };
  const toggleLayer = (index: number) => {
    const next = layers.map((x, i) => i === index ? { ...x, visible: !x.visible } : x);
    setLayers(next); recomposite(next);
    setMessage(`${next.filter(x => x.visible).length} of ${next.length} locked color layers visible.`);
  };
  const setLayerOpacity = (index: number, value: number) => {
    const next = layers.map((x, i) => i === index ? { ...x, opacity: value } : x);
    setLayers(next); recomposite(next);
  };
  const makeRepeat = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const x = await post<ImageInfo>('/repeat/create', { image_id: cur.image_id, columns: 4, rows: 3, mode: repeatMode });
    apply(x); setView('Preview'); setMessage('Live repeat preview created.');
  });
  const checkSeam = () => run(async () => {
    const cur = need(img, 'Import a design first.');
    const x = await post<Seam>('/repeat/check-seam', { image_id: cur.image_id, colors: 2 });
    setSeam(x); setMessage(`Seam score ${x.score}: ${x.rating}. Lower is better.`);
  });
  const exportFile = (url: string, payload: unknown, filename: string) => run(async () => {
    await download(url, payload, filename);
    setMessage(`Downloaded ${filename}.`);
  });
  const saveProject = () => run(async () => {
    const cur = need(img, 'Import a design before saving a project.');
    const filename = `${safeFileName(projectName)}.textileproj`;
    await download('/project/export', {
      name: projectName || 'loomlab-project', original_id: original?.image_id, image_id: cur.image_id, palette, settings,
      layers: layers.map(l => ({ id: l.id, name: l.name, color: l.color, coverage: l.coverage, visible: l.visible !== false, opacity: l.opacity ?? 100 })),
    }, filename);
    setMessage(`Saved ${filename} — reopen it any time with Open Project.`);
  });
  const undo = () => {
    if (!history.length) return;
    const prior = history[history.length - 1];
    if (img) setFuture(f => [{ img, palette }, ...f]);
    setHistory(h => h.slice(0, -1)); setImg(prior.img); setPalette(prior.palette); setMessage('Reverted last image operation.');
  };
  const redo = () => {
    if (!future.length) return;
    const next = future[0];
    if (img) setHistory(h => [...h, { img, palette }]);
    setFuture(f => f.slice(1)); setImg(next.img); setPalette(next.palette); setMessage('Re-applied image operation.');
  };

  // Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z and Ctrl/Cmd+Y -- except while typing, where
  // the text field's own undo should win.
  const shortcuts = useRef({ undo, redo });
  shortcuts.current = { undo, redo };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      if (e.target instanceof Element && e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
      const k = e.key.toLowerCase();
      if (k === 'z' && !e.shiftKey) { e.preventDefault(); shortcuts.current.undo(); }
      else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); shortcuts.current.redo(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Dropping a file anywhere imports it (an image/PSD, or a .textileproj).
  // Without this the browser would open the dropped file itself and the
  // whole session would be lost.
  const hasFiles = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes('Files');
  const onDragOver = (e: React.DragEvent) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = busy ? 'none' : 'copy'; if (!dragOver) setDragOver(true); };
  const onDragLeave = (e: React.DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false); };
  const onDrop = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && !busy) openFile(f);
  };

  return (
    <div className={'app' + (dragOver ? ' drag-over' : '')} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <Header projectName={img ? projectName : ''} canUndo={!!history.length} canRedo={!!future.length} onUndo={undo} onRedo={redo} onSave={saveProject} onOpenProject={() => projectInput.current?.click()} busy={busy} />
      <Sidebar view={view} setView={setView} />
      {view === 'Plates'
        ? <PlatesGallery layers={layers} onDownload={exportFile} busy={busy} />
        : view === 'AI Instructions'
        ? <AiInstructionsView img={img} dna={dna} brief={brief} instruction={instruction} setInstruction={setInstruction} intent={aiIntent} setIntent={setAiIntent} fidelity={fidelity} setFidelity={setFidelity} userRequest={userRequest} setUserRequest={setUserRequest} description={aiDescription} setDescription={setAiDescription} onAnalyze={analyzeDesign} onGenerate={generateInstructions} busy={busy} />
        : <CanvasPreview img={img} original={original} view={view} onImportClick={() => input.current?.click()} />}
      <aside className="right">
        <div className="panel-title">{view.toUpperCase()} <StatusBadge status={status} /></div>
        <fieldset className="panel-body" disabled={busy}>
          {view === 'Import' && <UploadPanel img={img} inputRef={input} onLoadSample={loadSample} />}
          {view === 'Color Analysis' && <ColorAnalysisPanel colorCount={colorCount} setColorCount={setColorCount} onAnalyze={analyze} onReduce={reduce} palette={palette} accuracy={accuracy} regionReduce={regionReduce} setRegionReduce={setRegionReduce} />}
          {view === 'AI Instructions' && <div className="muted"><p>LoomLab reads your imported <b>client design</b> and helps you write precise instructions for an external AI image generator — it does <b>not</b> generate a design here.</p><p style={{ marginTop: 10 }}>Workflow: <b>Analyze</b> → review the <b>Design DNA</b> → pick a <b>goal</b> and <b>fidelity</b> → describe your change → <b>Generate</b> → edit → <b>Copy</b>. Take the generated design into Color Separation afterward.</p></div>}
          {view === 'Color Mapping' && <ColorMappingPanel mapping={mapping} setMapping={setMapping} palette={palette} tolerance={mapTolerance} setTolerance={setMapTolerance} onApply={map} onReset={() => { setMapping(DEFAULT_MAPPING); setMapTolerance(10); }} />}
          {view === 'Color Separation' && <SeparationPanel palette={palette} mode={separationMode} setMode={setSeparationMode} cleanup={cleanup} setCleanup={setCleanup} edgeStrength={edgeStrength} setEdgeStrength={setEdgeStrength} minRegion={minRegion} setMinRegion={setMinRegion} onSeparate={separate} />}
          {view === 'Layers' && <LayerPanel layers={layers} palette={palette} img={img} onToggle={toggleLayer} onOpacityChange={setLayerOpacity} onHalftonePreview={halftonePreview} onDownload={exportFile} />}
          {view === 'Plates' && <ExportPanel img={img} layers={layers} onDownload={exportFile} />}
          {view === 'Repeat' && <RepeatPanel repeatMode={repeatMode} setRepeatMode={setRepeatMode} onMakeRepeat={makeRepeat} onCheckSeam={checkSeam} seam={seam} />}
          {view === 'Preview' && <PreviewPanel onCheckSeam={checkSeam} seam={seam} />}
          {view === 'Export' && <ExportPanel img={img} layers={layers} onDownload={exportFile} />}
        </fieldset>
      </aside>
      <Footer status={status} message={message} img={img} palette={palette} />
      <input ref={input} hidden type="file" accept="image/png,image/jpeg,image/webp,image/tiff,.tif,.tiff,.psd,image/vnd.adobe.photoshop,.textileproj" onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) openFile(f); }} disabled={busy} />
      <input ref={projectInput} hidden type="file" accept=".textileproj" onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) openProject(f); }} disabled={busy} />
    </div>
  );
}
