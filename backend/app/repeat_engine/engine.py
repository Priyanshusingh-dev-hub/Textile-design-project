import numpy as np
from PIL import Image, ImageOps

def create(image, columns, rows, mode, offset_x=0, offset_y=0):
    """Lay out a columns x rows repeat preview.

    - grid: straight repeat.
    - brick: every other ROW slides sideways by half a tile.
    - half-drop: every other COLUMN drops down by half a tile (the classic
      textile half-drop -- it is a vertical shift, not a horizontal one).
    - mirror: every other column flipped left-right and every other row
      flipped top-bottom, so each tile meets its neighbour as a reflection
      and every seam is continuous by construction.

    Shifted rows/columns are wrapped, with one extra ring of tiles drawn
    around the grid, so the output is completely covered instead of leaving
    a transparent half-tile gap at one edge."""
    image=image.convert('RGBA')
    w,h=image.size; out=Image.new('RGBA',(w*columns,h*rows))
    if mode=='mirror':
      flip_x=ImageOps.mirror(image)
      tiles={(0,0):image,(1,0):flip_x,(0,1):ImageOps.flip(image),(1,1):ImageOps.flip(flip_x)}
    ox=offset_x % w; oy=offset_y % h
    for row in range(-1,rows+1):
      for col in range(-1,columns+1):
        dx=col*w+ox; dy=row*h+oy
        if mode=='brick' and row%2: dx+=w//2
        if mode=='half-drop' and col%2: dy+=h//2
        if dx>=out.width or dy>=out.height or dx+w<=0 or dy+h<=0: continue
        # tiles never overlap, so a plain paste (which clips negative
        # offsets, unlike alpha_composite) places each one exactly
        out.paste(tiles[(col%2,row%2)] if mode=='mirror' else image,(dx,dy))
    return out
def seam_score(image):
    a=np.asarray(image.convert('RGB'),dtype=float); lr=np.abs(a[:,0]-a[:,-1]).mean(); tb=np.abs(a[0]-a[-1]).mean()
    return {'left_right':round(float(lr),2),'top_bottom':round(float(tb),2),'score':round(float((lr+tb)/2),2),'rating':'good' if (lr+tb)/2<18 else 'needs attention'}
