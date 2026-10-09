import { createElement } from 'react';
import { Upload, Palette as PaletteIcon, Layers, Repeat2, Download, ChevronRight, LayoutGrid, Sparkles, SwatchBook, Pipette, ScanEye, type LucideIcon } from 'lucide-react';
import { TABS, type View } from '../types';

const ICONS: Record<View, LucideIcon> = {
  'Import': Upload, 'Color Analysis': PaletteIcon, 'AI Instructions': Sparkles, 'Color Separation': SwatchBook,
  'Color Mapping': Pipette, 'Layers': Layers, 'Plates': LayoutGrid, 'Repeat': Repeat2, 'Preview': ScanEye, 'Export': Download,
};

export function Sidebar({ view, setView }: { view: View; setView: (v: View) => void }) {
  return (
    <aside className="left">
      <div className="navlabel">WORKFLOW</div>
      {TABS.map(t => (
        <button className={view === t ? 'nav active' : 'nav'} onClick={() => setView(t)} key={t}>
          {createElement(ICONS[t], { size: 17 })}<span>{t}</span><ChevronRight size={14} />
        </button>
      ))}
      <div className="hint"><b>PRINT-READY FLOW</b><p>Import → Analyze → Reduce → Map → Separate → Repeat → Export</p></div>
    </aside>
  );
}
