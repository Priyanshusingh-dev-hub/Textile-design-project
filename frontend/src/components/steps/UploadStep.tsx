import { screenUrl } from '../../api';
import { jobSummary } from '../../lib/job';
import type { LoomLab } from '../../hooks/useLoomLab';

/** Step 1: drop a design, or continue the last job. */
export function UploadStep({ w }: { w: LoomLab }) {
  const {
    original,
    input,
    busy,
    go,
    resumable,
    forgetJob,
    resumeJob,
    onUpload,
    loadSample,
  } = w;
  return (
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
  );
}
