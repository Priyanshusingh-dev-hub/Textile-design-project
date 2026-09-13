export function PreviewPanel({ onCheckSeam }: { onCheckSeam: () => void }) {
  return (
    <>
      <p className="muted">Use the center canvas to inspect your repeat. The image is a preview; export keeps native resolution.</p>
      <button className="secondary wide" onClick={onCheckSeam}>Check Seam</button>
    </>
  );
}
