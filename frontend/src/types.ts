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
};

/** What a line art + reference fill measured (POST /api/fill). */
export type FillAuto = {
  chosen: 1 | 2 | 3;
  method1: { alignment_score: number; coverage_diff: number };
  method3?: { alignment_score: number; coverage_diff: number };
  coverage_diff: number;      // the chosen fill's colour shares vs the reference, points
  limit: number;
  only_two?: boolean;         // Method 2 because 1 and 3 both failed: two colours only
};
export type FillInfo = {
  method: 1 | 2 | 3;
  auto: FillAuto | null;
  alignment: number | null;   // share of the reference's colour edges on the line art's lines (null: Method 2)
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
