import { Undo2, Redo2, Save } from 'lucide-react';
import type { ImageInfo } from '../types';

export function Header({ img, canUndo, canRedo, onUndo, onRedo, onSave, onLoadProject }: {
  img?: ImageInfo; canUndo: boolean; canRedo: boolean;
  onUndo: () => void; onRedo: () => void; onSave: () => void; onLoadProject: () => void;
}) {
  return (
    <header>
      <div className="brand"><span className="loom">L</span><div>LoomLab <small>TEXTILE STUDIO</small></div></div>
      <div className="project">{img?.file_name || 'Untitled textile project'} <span>• Local workspace</span></div>
      <button className="icon" onClick={onUndo} disabled={!canUndo} title="Undo"><Undo2 /></button>
      <button className="icon" onClick={onRedo} disabled={!canRedo} title="Redo"><Redo2 /></button>
      <button className="primary" onClick={onSave}><Save /> Save Project</button>
      <button className="secondary" onClick={onLoadProject} title="Reload the saved project for this image"><Undo2 /> Load Project</button>
    </header>
  );
}
