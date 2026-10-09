import type { RefObject } from 'react';
import { Upload } from 'lucide-react';
import type { ImageInfo } from '../types';
import { Meta } from './shared';

export function UploadPanel({ img, inputRef, onLoadSample }: {
  img?: ImageInfo; inputRef: RefObject<HTMLInputElement | null>; onLoadSample: () => void;
}) {
  return (
    <>
      <button className="drop" onClick={() => inputRef.current?.click()}><Upload /><b>Import artwork</b><small>Click or drop · PNG, JPG, WEBP, TIFF, PSD · up to 80 MB</small><small>A saved .textileproj opens as a project</small></button>
      <button className="secondary wide" onClick={onLoadSample}>Load sample floral pattern</button>
      {img && <Meta img={img} />}
    </>
  );
}
