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

export type Palette = { hex: string; rgb: number[]; pixels: number; coverage: number; locked?: boolean;
  name?: string };   // the mill's name for this ink, once it is one of theirs

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
  repeat?: { x: boolean; y: boolean };   // seamless repeat axes (processed wrapped round)
  dots?: boolean;   // placed as dots (index separation); accuracy is as seen from a step away
  smoothing?: number;   // the texture cleanup the reduce used
};

/** One thing the judge tried: Reduce of the reference alone, or a fill, drawn at the
 *  reference's own size and scored against it with the Reduce step's own match. */
export type FillTrial = {
  name: 'reduce' | 'method1' | 'method4' | 'method3' | 'method2';
  status: 'ok' | 'failed';
  match?: number;             // 0-100, pixel by pixel against the reference
  delta_e?: number;
  inks?: number;
  edge_share?: number;        // % of pixels with another ink beside them: a noisy edge has more
  alignment?: number;         // fills only: how well the line art lies on the reference's edges
  seconds: number;
  why?: string;
  chosen?: boolean;
};
export type FillTrials = {
  rows: FillTrial[];
  chosen: FillTrial['name'];
  reason: 'fill_close' | 'fill_far' | 'no_fill' | 'operator';   // operator: they took another way than the judge's
  auto?: FillTrial['name'];   // what the judge had chosen, once the operator has taken another
  margin: number | null;      // the best fill's match minus plain Reduce's
  tolerance: number;          // how far behind a fill may be and still win (clean edges are worth it)
  inks: number;
  trial_px: number;
  seconds: number;
};
/** What a line art + reference fill measured (POST /api/fill). */
export type FillInfo = {
  method: 0 | 1 | 2 | 3 | 4;  // 0: the line art set aside, the reference alone through Reduce
  trials: FillTrials | null;  // null when the operator asked for a method by hand
  alignment: number | null;   // share of the reference's colour edges on the line art's lines (null: Methods 0 and 2)
  regions: number;
  doubtful: number;           // big areas where the reference has several colours (often a broken line)
  debug_url: string | null;   // those areas in red
  line_color: string | null;
  stray_merged: { hex: string; pixels: number; into: string }[];
  size_px: number[];
  line_file?: string;
};
export type LineFillResult = { original: ImageInfo; reduced: ReduceResult; fill: FillInfo };

export const STEPS = ['Upload', 'Reduce', 'Separate', 'Export'] as const;
export type Step = typeof STEPS[number];
