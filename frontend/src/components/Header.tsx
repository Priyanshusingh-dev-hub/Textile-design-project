import { Undo2, Redo2, Save, FolderOpen } from 'lucide-react';

export function Header({ projectName, canUndo, canRedo, onUndo, onRedo, onSave, onOpenProject, busy }: {
  projectName: string; canUndo: boolean; canRedo: boolean;
  onUndo: () => void; onRedo: () => void; onSave: () => void; onOpenProject: () => void; busy: boolean;
}) {
  return (
    <header>
      <div className="brand"><span className="loom">L</span><div>LoomLab <small>TEXTILE STUDIO</small></div></div>
      <div className="project">{projectName || 'Untitled textile project'} <span>• Local workspace</span></div>
      <button className="icon" onClick={onUndo} disabled={!canUndo} title="Undo (Ctrl+Z)"><Undo2 /></button>
      <button className="icon" onClick={onRedo} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)"><Redo2 /></button>
      <button className="primary" onClick={onSave} disabled={busy || !projectName} title="Download the whole workspace as a portable .textileproj file"><Save /> Save Project</button>
      <button className="secondary" onClick={onOpenProject} disabled={busy} title="Open a saved .textileproj file"><FolderOpen /> Open Project</button>
    </header>
  );
}
