import { useRef, useState } from 'react';
import { post, API } from './api';
import type { ImageInfo, Palette, Layer, Seam, View } from './types';
import { useAsyncStatus } from './hooks/useAsyncStatus';
import { StatusBadge } from './components/shared';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { CanvasPreview } from './components/CanvasPreview';
import { UploadPanel } from './components/UploadPanel';
import { ColorAnalysisPanel } from './components/ColorAnalysisPanel';
import { ColorMappingPanel } from './components/ColorMappingPanel';
import { SeparationPanel } from './components/SeparationPanel';
import { LayerPanel } from './components/LayerPanel';
import { RepeatPanel } from './components/RepeatPanel';
import { PreviewPanel } from './components/PreviewPanel';
import { ExportPanel } from './components/ExportPanel';
import { Footer } from './components/Footer';

export default function App() {
  const [view, setView] = useState<View>('Import');
  const [img, setImg] = useState<ImageInfo>();
  const [original, setOriginal] = useState<ImageInfo>();
  const [palette, setPalette] = useState<Palette[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [separationSource, setSeparationSource] = useState<ImageInfo>();
  const [colorCount, setColorCount] = useState(20);
  const [message, setMessage] = useState('Ready — import a design to begin.');
  const [history, setHistory] = useState<ImageInfo[]>([]);
  const [future, setFuture] = useState<ImageInfo[]>([]);
  const [repeatMode, setRepeatMode] = useState('grid');
  const [seam, setSeam] = useState<Seam>();
  const [mapping, setMapping] = useState({ source: '#D84876', target: '#B3203A' });
  const input = useRef<HTMLInputElement>(null);
  const { status, run, busy } = useAsyncStatus();

  const apply = (next: ImageInfo) => { if (img) setHistory(h => [...h, img]); setFuture([]); setImg(next); };

  const upload = (f: File) => run(async () => {
    const data = new FormData(); data.append('file', f);
    const r = await fetch(API + '/image/upload', { method: 'POST', body: data });
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: 'Unable to import this image.' }))).detail);
    const x = await r.json();
    setImg(x); setOriginal(x); setPalette([]); setLayers([]);
    setMessage(`Imported ${x.width} × ${x.height}px. Analyze colors next.`); setView('Color Analysis');
  });
  const loadSample = () => run(async () => {
    const x = await post<ImageInfo>('/image/sample', {});
    setImg(x); setOriginal(x); setPalette([]); setLayers([]); setView('Color Analysis');
    setMessage('Sample floral pattern loaded — analyze its palette to begin.');
  });
  const analyze = () => run(async () => {
    if (!img) return;
    const x = await post<{ palette: Palette[] }>('/colors/analyze', { image_id: img.image_id, colors: colorCount });
    setPalette(x.palette); setMessage(`${x.palette.length} dominant colors found using LAB perceptual analysis.`);
  });
  const reduce = () => run(async () => {
    if (!img) return;
    const x = await post<any>('/colors/reduce', { image_id: img.image_id, colors: colorCount });
    apply(x); setPalette(x.palette); setMessage(`Reduced to ${colorCount} print colors.`);
  });
  const map = () => run(async () => {
    if (!img) return;
    const x = await post<ImageInfo>('/colors/map', { image_id: img.image_id, mappings: [{ ...mapping, enabled: true }] });
    apply(x); setMessage('Color mapping applied non-destructively.');
  });
  const separate = () => run(async () => {
    if (!img || !palette.length) return;
    const x = await post<{ layers: Layer[] }>('/separation/create', { image_id: img.image_id, palette: palette.map(p => p.hex) });
    setSeparationSource(img); setLayers(x.layers.map(l => ({ ...l, visible: true, opacity: 100 })));
    setView('Layers'); setMessage(`${x.layers.length} exclusive spot-color layers are ready.`);
  });
  const recomposite = (next: Layer[]) => run(async () => {
    if (!separationSource) return;
    const preview = await post<ImageInfo>('/separation/composite-layers', { layers: next.filter(x => x.visible).map(x => ({ id: x.id, color: x.color, opacity: x.opacity ?? 100 })) });
    setImg(preview);
  });
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
    if (!img) return;
    const x = await post<ImageInfo>('/repeat/create', { image_id: img.image_id, columns: 4, rows: 3, mode: repeatMode });
    apply(x); setView('Preview'); setMessage('Live repeat preview created.');
  });
  const checkSeam = () => run(async () => {
    if (!img) return;
    const x = await post<Seam>('/repeat/check-seam', { image_id: img.image_id, colors: 2 });
    setSeam(x); setMessage(`Seam score ${x.score}: ${x.rating}. Lower is better.`);
  });
  const saveProject = () => run(async () => {
    await post('/project/save', { image_id: img?.image_id, palette: palette.map(p => p.hex), mappings: [], repeat: { mode: repeatMode } });
    setMessage('Project saved as a portable .textileproj file.');
  });
  const loadProject = () => run(async () => {
    if (!img) return;
    const p = await post<{ palette: string[]; repeat: { mode?: string } }>('/project/load', { image_id: img.image_id });
    if (p.palette) setPalette(p.palette.map(hex => ({ hex, rgb: [0, 0, 0], pixels: 0, coverage: 0 })));
    if (p.repeat?.mode) setRepeatMode(p.repeat.mode);
    setMessage('Project reloaded from its saved .textileproj file.');
  });
  const undo = () => { if (!history.length) return; const prior = history[history.length - 1]; if (img) setFuture(f => [img, ...f]); setHistory(h => h.slice(0, -1)); setImg(prior); setMessage('Reverted last image operation.'); };
  const redo = () => { if (!future.length) return; const next = future[0]; if (img) setHistory(h => [...h, img]); setFuture(f => f.slice(1)); setImg(next); };

  return (
    <div className="app">
      <Header img={img} canUndo={!!history.length} canRedo={!!future.length} onUndo={undo} onRedo={redo} onSave={saveProject} onLoadProject={loadProject} />
      <Sidebar view={view} setView={setView} />
      <CanvasPreview img={img} original={original} view={view} onImportClick={() => input.current?.click()} />
      <aside className="right">
        <div className="panel-title">{view.toUpperCase()} <StatusBadge status={status} /></div>
        {view === 'Import' && <UploadPanel img={img} inputRef={input} onLoadSample={loadSample} />}
        {view === 'Color Analysis' && <ColorAnalysisPanel colorCount={colorCount} setColorCount={setColorCount} onAnalyze={analyze} onReduce={reduce} palette={palette} />}
        {view === 'Color Mapping' && <ColorMappingPanel mapping={mapping} setMapping={setMapping} onApply={map} onReset={() => setMapping({ source: '#D84876', target: '#B3203A' })} />}
        {view === 'Color Separation' && <SeparationPanel palette={palette} onSeparate={separate} />}
        {view === 'Layers' && <LayerPanel layers={layers} palette={palette} img={img} onToggle={toggleLayer} onOpacityChange={setLayerOpacity} />}
        {view === 'Repeat' && <RepeatPanel repeatMode={repeatMode} setRepeatMode={setRepeatMode} onMakeRepeat={makeRepeat} onCheckSeam={checkSeam} seam={seam} />}
        {view === 'Preview' && <PreviewPanel onCheckSeam={checkSeam} seam={seam} />}
        {view === 'Export' && <ExportPanel img={img} layers={layers} />}
      </aside>
      <Footer status={status} message={message} img={img} palette={palette} />
      <input ref={input} hidden type="file" accept="image/png,image/jpeg,image/webp,image/tiff,.psd,image/vnd.adobe.photoshop" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} disabled={busy} />
    </div>
  );
}
