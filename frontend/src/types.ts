export type ImageInfo = { image_id: string; width: number; height: number; url: string; file_name?: string };
export type View = 'Import' | 'Color Analysis' | 'Color Separation' | 'Color Mapping' | 'Layers' | 'Repeat' | 'Preview' | 'Export';
export const TABS: View[] = ['Import', 'Color Analysis', 'Color Separation', 'Color Mapping', 'Layers', 'Repeat', 'Preview', 'Export'];
export type Palette = { hex: string; rgb: number[]; pixels: number; coverage: number };
export type Layer = { id: string; name: string; color: string; coverage: number; url: string; mask_url?: string; visible?: boolean; opacity?: number };
export type Seam = { left_right: number; top_bottom: number; score: number; rating: string };
export type SeparationMode = 'flat' | 'gradient';
