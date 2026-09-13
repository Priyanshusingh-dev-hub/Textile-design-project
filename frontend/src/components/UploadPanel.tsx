import type { RefObject } from 'react';
import { Upload } from 'lucide-react';
import type { ImageInfo } from '../types';
import { Meta } from './shared';

export function UploadPanel({ img, inputRef, onLoadSample }: {
  img?: ImageInfo; inputRef: RefObject<HTMLInputElement | null>; onLoadSample: () => void;
}) {
  return (
    <>
      <div className="drop" onClick={() => inputRef.current?.click()}><Upload /><b>Import artwork</b><small>PNG, JPG, WEBP, TIFF, PSD · up to 80 MB</small></div>
      <button className="secondary wide" onClick={onLoadSample}>Load sample floral pattern</button>
      {img && <Meta img={img} />}
    </>
  );
}
