import numpy as np
from PIL import Image, ImageOps
def create(image, columns, rows, mode, offset_x=0, offset_y=0):
    image=image.convert('RGBA')
    w,h=image.size; out=Image.new('RGBA',(w*columns,h*rows))
    for y in range(rows):
      for x in range(columns):
        tile=image
        if mode=='mirror' and (x+y)%2: tile=ImageOps.mirror(image)
        dx=x*w+offset_x; dy=y*h+offset_y
        if mode in ('half-drop','brick') and y%2: dx+=w//2
        out.alpha_composite(tile,(dx,dy))
    return out
def seam_score(image):
    a=np.asarray(image.convert('RGB'),dtype=float); lr=np.abs(a[:,0]-a[:,-1]).mean(); tb=np.abs(a[0]-a[-1]).mean()
    return {'left_right':round(float(lr),2),'top_bottom':round(float(tb),2),'score':round(float((lr+tb)/2),2),'rating':'good' if (lr+tb)/2<18 else 'needs attention'}
