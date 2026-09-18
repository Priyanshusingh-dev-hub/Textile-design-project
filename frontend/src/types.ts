export type ImageInfo = { image_id: string; width: number; height: number; url: string; file_name?: string };
export type View = 'Import' | 'Color Analysis' | 'AI Instructions' | 'Color Separation' | 'Color Mapping' | 'Layers' | 'Plates' | 'Repeat' | 'Preview' | 'Export';
export const TABS: View[] = ['Import', 'Color Analysis', 'AI Instructions', 'Color Separation', 'Color Mapping', 'Layers', 'Plates', 'Repeat', 'Preview', 'Export'];
export type Intent = 'exact_recreation' | 'premium_improvement' | 'color_change' | 'new_variation' | 'same_style_new' | 'print_optimization';
export type DesignDna = {
  style: { category: string; sub_style: string; source: string };
  motif_family: string[]; motif_family_source: string;
  composition: { density: string; symmetry: string; negative_space: string; contrast: string; detail: string };
  scale: { dimensions: string; aspect_ratio: number };
  colors: { role: string; hex: string; coverage: number }[];
  background: { hex: string; coverage: number };
  distinct_colors: number; mergeable_colors: string[][];
  visual_character: string; production_notes: string[];
  detected: string[]; from_description: string[];
};
export type Palette = { hex: string; rgb: number[]; pixels: number; coverage: number };
export type Layer = { id: string; name: string; color: string; coverage: number; url: string; mask_url?: string; plate_url?: string; visible?: boolean; opacity?: number; halftonePreviewUrl?: string };
export type Seam = { left_right: number; top_bottom: number; score: number; rating: string };
export type SeparationMode = 'flat' | 'gradient' | 'region';
