# Textile Pattern Color-Fill Project

User se baat **Hinglish** (Roman Hindi + English) me karo, simple aur short. User textile mill ke liye designs banata hai.

## Kaam kya hai
User do images deta hai:
1. **Line art**: black & white outline wala design.
2. **Reference**: wahi design, colored (same layout, same alignment).

Kaam: line art ke har band hisse me reference ke hisaab se sahi color bharna, aur mill ke liye print-ready files dena.

**Hamesha `colorfill.py` use karo.** Apna naya tarika mat banao. Ye method user ke saath test aur approve ho chuka hai.

```bash
pip install -r requirements.txt
python colorfill.py --line input/lineart.png --ref input/colored.png --out output/ --name design01
```

## Pakke rules (inhe kabhi mat todna)

1. **Channel-wise flat colors.** Final image me sirf reference ke flat colors (jaise 9). Koi shading, gradient, anti-aliasing ya mixed pixel nahi. Har pixel exactly ek channel ka ho.
2. **Koi smoothing NAHI.** Gaussian blur karke boundaries smooth karna, label smoothing, ya morphological rounding sab mana hai. User ne test kiya tha: isse kone gol ho jaate hain, dots pighal jaate hain, aur design "ganda" lagta hai. Zoom par dikhne wali halki seedhiyan (jaggies) theek hain, kyunki print par 1/300 inch hoti hain aur nazar nahi aati.
3. **Default 3535 × 3535 px @ 300 DPI = 11.78 inch.** Mill ka working format 300 DPI hai.
   - 600 DPI file mill ko mat bhejo. Mill ka software 7070 px ko 300 DPI maan le to design **23.57 inch** ka ho jayega.
   - Kabhi bhi bilinear/bicubic se color image resize mat karo, isse naye mixed colors bante hain. Colored/index image ke liye sirf `INTER_NEAREST`.
   - Size formula: `pixels = inch × DPI`.
4. **Resize sirf line art ka** (Lanczos + halka 3×3 blur, phir threshold). Ye script already karti hai.
5. **File names me `#` nahi** (kuch phone/zip apps aisi files skip karte hain). Format: `channel_01_374C13.png`.

## Script kya karti hai (Method 1)
1. Reference se exact flat palette nikaalti hai. Reference flat na ho to k-means karti hai aur warning deti hai.
2. Reference ko palette index me map karke target size par NEAREST resize karti hai.
3. Line art ko upscale karke threshold karti hai, isse line mask milta hai.
4. **Alignment check:** reference ke color-boundaries line art ki lines par padte hain ya nahi. Score < 0.55 ho to STOP karti hai.
5. Line mask ke bahar ke band hisse (4-connectivity) label karti hai. Har hisse ko reference me usi jagah ka **sabse zyada aane wala color** milta hai (majority vote). Ye pure pixel maths hai, AI guess nahi.
6. Line pixels ko reference me lines ke neeche sabse common color milta hai (is design me gold outline).
7. Outputs banati hai aur verify karti hai.

## Outputs (har design ke liye)
| File | Use |
|---|---|
| `*_final_3535px_300dpi.tif` | **Mill ko yahi bhejo** (LZW, lossless, DPI embedded) |
| `*_final_3535px_300dpi.png` | Dekhne/share karne ke liye |
| `*_colored_channels_*.zip` | Har color ka alag layer, asli color + transparent background (Photopea/Photoshop me overlap ke liye) |
| `*_bw_separations_*.zip` | Black/white 1-bit separations (screen printing) |
| `*_channels_preview.png` | Saare channels ek sheet par |
| `*_report.json` | Colors, coverage %, alignment score, verification |
| `*_DEBUG_doubtful_regions.png` | Sirf tab banta hai jab kuch regions me reference ke multiple colors mile (red me highlight) |

## Har run ke baad check (user ko report do)
- `colors_in_final` == channels ki ginti (jaise 9)
- `channels_overlap_equals_final` == true
- `tif_dpi` == [300, 300], `size_px` == [3535, 3535]
- `alignment_score` ≥ 0.55 (achha design ~0.9+)
- `doubtful_regions` ho to DEBUG image khud dekho aur user ko batao kahan check karna hai. Patli stems ya double-line hisse aksar flag hote hain aur wahan aksar sab theek hota hai. Line tooti ho aur color background me beh gaya ho, wo asli problem hai.
- Preview image khud dekho: chhote dots, leaf stripes, patli lines sahi hain ya nahi.

## Problems aur solutions
- **Alignment fail:** images alag crop/size/rotation ki hain. User se same crop wali images maango. Agar sirf shift/scale ka farak ho to OpenCV feature matching (ORB + homography) se reference ko line art par align karke phir script chalao. Alag design ho to ye method kaam nahi karega, user ko saaf batao.
- **Color leak (tooti line):** threshold badhao (`--line-threshold 170`) taaki patli/halki lines pakdi jaayein, ya user ko batao ki line art me wo gap band karna padega.
- **Reference flat nahi (shading/gradient):** `--max-colors N` do (user se poocho kitne channels chahiye), aur result dhyan se check karo.
- **Patli lines gayab:** threshold badhao. Blur mat badhao.
- **Badi file / batch:** `input/` folder ke har pair par loop chalao. Har design ka alag `--name` do.

## Agar user aur saaf edges maange (bina design bigaade)
Smoothing ke bajaye ye options suggest karo:
1. **Vector trace** (potrace / Illustrator Image Trace) har channel ka, phir 300 DPI par bina anti-aliasing rasterize. Corners bache rehte hain.
2. **Line art AI upscale** (Upscayl / Real-ESRGAN) pehle, phir script.
3. Original high-res / vector line art.

Inme se koi bhi karo to output phir bhi upar ke saare rules follow kare (flat colors, 300 DPI, verify).

## Background (is project me ab tak kya hua)
- Floral design (purple peony, pink hibiscus, striped leaves, dark green ground) par Method 1 se 9 channels bane: 374C13 dark green, F0CF6A gold (outline), 771684 purple, E63C85 pink, E2A03F mustard, F6DE88 light cream, B75639 rust, 2699A6 teal, F685AC light pink.
- Smoothing aur 600 DPI try kiye gaye. User ne smoothing reject ki, aur mill 300 DPI par chalti hai. **Final decision: Method 1, 300 DPI, no smoothing.**
- User Photopea (phone) me layers overlap karke check karta hai: canvas 3535×3535, 300 DPI, RGB, 8 bit, sRGB, Transparent background; File → Open & Place se channels add karta hai.
- Kaam PNG me, mill ko TIFF. Mill se RGB/CMYK confirm karna user ki zimmedari hai. Poocha jaaye to yaad dilao.
