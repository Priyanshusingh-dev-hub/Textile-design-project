import type { SimilarPair } from './lib/print';
export type ImageInfo = {
  image_id: string;
  width: number;
  height: number;
  url: string;
  file_name?: string;
  file_size?: number;
  layers?: Layer[];
  overlap?: number;     // pre-separated PSD: % of the inked area on 2+ screens
};

export type Palette = { hex: string; rgb: number[]; pixels: number; coverage: number; locked?: boolean };

export type Layer = {
  id: string;
  name: string;
  color: string;
  coverage: number;
  edge?: number;        // % of the design's outer edge this ink covers (the ground owns most)
  url: string;
  plate_url?: string;
  skip?: boolean;   // true = this ink is the fabric colour, don't print / export it
};

export type ReduceResult = ImageInfo & {
  palette: Palette[]; accuracy: number; delta_e: number; source_id: string;
  soft_edge?: number;   // px width of any part-transparent rim; a flat ink can't fade
  similar?: SimilarPair[];   // near-identical ink pairs, with the match if merged
};

export const STEPS = ['Upload', 'Reduce', 'Separate', 'Export'] as const;
export type Step = typeof STEPS[number];
