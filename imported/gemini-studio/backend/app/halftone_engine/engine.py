import math
import numpy as np
from PIL import Image, ImageDraw

def _intensity(mask: Image.Image) -> np.ndarray:
    """Use the alpha channel as ink intensity when the mask actually carries
    one (the normal case: a separation layer's alpha mask), otherwise fall
    back to grayscale luminance for a plain RGB/L image."""
    if 'A' in mask.getbands():
        return np.asarray(mask.convert('RGBA'))[:, :, 3].astype(float)
    return np.asarray(mask.convert('L')).astype(float)

def apply(mask: Image.Image, cell_size: int = 8, angle: float = 45, dot_color=(0, 0, 0)) -> Image.Image:
    """Classic amplitude-modulated dot halftone: a rotated grid of circular
    dots whose radius is driven by the local mean tone, turning a
    continuous-tone mask into a printable dot pattern."""
    intensity = _intensity(mask)
    h, w = intensity.shape
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    cell_size = max(2, int(cell_size))
    theta = math.radians(angle)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    half = cell_size / 2
    diag = int(math.hypot(w, h)) + cell_size * 2
    for u in range(-diag, diag, cell_size):
        for v in range(-diag, diag, cell_size):
            x = u * cos_t - v * sin_t + w / 2
            y = u * sin_t + v * cos_t + h / 2
            xi, yi = int(round(x)), int(round(y))
            if xi < 0 or yi < 0 or xi >= w or yi >= h:
                continue
            x0, x1 = max(0, xi - int(half)), min(w, xi + int(half) + 1)
            y0, y1 = max(0, yi - int(half)), min(h, yi + int(half) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            tone = intensity[y0:y1, x0:x1].mean() / 255.0
            radius = tone * half
            if radius < 0.5:
                continue
            draw.ellipse((xi - radius, yi - radius, xi + radius, yi + radius), fill=(*dot_color, 255))
    return out
