import { createElement } from 'react';
import { Upload, Palette as PaletteIcon, Layers, Repeat2, Download, ChevronRight } from 'lucide-react';
import { TABS, type View } from '../types';

const ICONS = [Upload, PaletteIcon, Layers, PaletteIcon, Layers, Repeat2, PaletteIcon, Download];

export function Sidebar({ view, setView }: { view: View; setView: (v: View) => void }) {
  return (
    <aside className="left">
      <div className="navlabel">WORKFLOW</div>
      {TABS.map((t, i) => (
        <button className={view === t ? 'nav active' : 'nav'} onClick={() => setView(t)} key={t}>
          {createElement(ICONS[i], { size: 17 })}<span>{t}</span><ChevronRight size={14} />
        </button>
      ))}
      <div className="hint"><b>PRINT-READY FLOW</b><p>Import → Analyze → Reduce → Map → Separate → Repeat → Export</p></div>
    </aside>
  );
}
