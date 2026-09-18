export type ImageInfo = {
  image_id: string;
  width: number;
  height: number;
  url: string;
  file_name?: string;
  file_size?: number;
  layers?: Layer[];
};

export type Palette = { hex: string; rgb: number[]; pixels: number; coverage: number; locked?: boolean };

export type Layer = {
  id: string;
  name: string;
  color: string;
  coverage: number;
  url: string;
  plate_url?: string;
};

export type ReduceResult = ImageInfo & { palette: Palette[]; accuracy: number; delta_e: number; source_id: string };

export const STEPS = ['Upload', 'Reduce', 'Separate', 'Export'] as const;
export type Step = typeof STEPS[number];
