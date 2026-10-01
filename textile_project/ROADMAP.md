# ROADMAP: project ko kis taraf le jaana hai

Goal: ek **single command-line tool** (`textile`) jo user ke 4 kaam (CLAUDE.md me A–D) reliable tarike se kare, aur har baar same mill rules follow kare. `reference_code/` me prototypes hain jo kaam karte hain par alag-alag scripts hain, hardcoded paths aur thresholds ke saath.

## Target structure
```
textile/
  cli.py              # textile fill | repeat | tile | export ...
  io_utils.py         # load, DPI save, TIFF LZW, naming (no '#'), zip
  palette.py          # flat palette, k-means, stray color merge, nearest map
  fill_method1.py     # aligned majority-vote fill
  fill_method2.py     # structure/depth fill (misaligned refs)
  repeat_analyze.py   # repeat type detection
  tile.py             # deshear + crop search + seam quilting + upscale
  export.py           # final png/tif, colored channels, B/W seps, preview, report
  verify.py           # color count, channel overlap, DPI, seamless check
tests/
  samples/            # user ke test designs + expected stats
  test_*.py
```

## Phase 1: Common foundation (sabse pehle)
- [ ] `export.py` + `verify.py`: abhi har script me ye logic copy-paste hai. Ek jagah lao.
- [ ] `palette.py`: stray color merge function (threshold: < 0.05% pixels → nearest big color).
- [ ] `cli.py` with `--size` (default 3535), `--dpi` (default 300), `--out`, `--name`.
- [ ] Har command ke end me short **Hinglish report**: size, inch, DPI, colors + coverage %, verify pass/fail.

## Phase 2: Color fill (`textile fill`)
- [ ] Method 1 ko module banao (`method1_colorfill.py` se).
- [ ] Method 2 ko generalize karo:
  - hardcoded paths aur thresholds hatao, args banao
  - reference se palette auto (ground = sabse common color, motif = baaki)
  - 2 se zyada colors: har region ko (depth, reference ka local majority color in a **dilated / tolerant window**) se color do, taaki thodi misalignment chal jaaye
- [ ] `--method auto`: pehle Method 1 chalao, phir quality check karo:
  - alignment score
  - motif-coverage compare: reference me motif color ka % vs output me % (tree case me Method 1 ne 10% diya jabki reference ~31% tha → fail signal)
  - fail ho to Method 2 par switch karo aur log karo kyun
- [ ] Debug images: doubtful regions red me, side-by-side (reference | output).

## Phase 3: Repeat (`textile repeat` + `textile tile`)
- [ ] `repeat_analyze.py` ko module banao, JSON output (type, W, H, drop, shear, mirror, avg_match).
- [ ] `tile.py`: deshear → crop search (W, H ±8, position) → seam quilting → 3×3 preview → upscale (wrap pad) → export.
- [ ] Rule: `tile` command andar se pehle `repeat` chalaye. Bina analysis tile kabhi na bane.
- [ ] Panel print detection: agar strong vertical repeat hai par horizontal nahi, to "panel print" bolo aur tile mat kaato.

## Phase 4: Original designs (`textile make`)
- [ ] Motif library: phool (layered petals), buti, patti, sprig, bel/vine (sine stem + spirals), dots, borders, haathi. PIL drawing, no AA.
- [ ] Layout engine: half-drop grid, all-over scatter, vertical panel (center + side borders), wrap-safe drawing.
- [ ] Config file (YAML/JSON): palette, motif sizes, density, layout. User sirf config badle.

## Phase 5: Quality-of-life
- [ ] Batch mode: `input/` folder ke saare pairs.
- [ ] Optional: vector trace (potrace) per channel → re-raster at 300 DPI **bina AA**. Sirf jab user saaf edges maange. Kabhi Gaussian smoothing nahi.
- [ ] Optional 600 DPI export, par default kabhi nahi, aur warning ke saath (mill 300 DPI).

## Tests (har phase ke saath)
Samples me ye cases rakho aur expected stats check karo:
| Case | Expected |
|---|---|
| Floral peony/hibiscus (aligned) | Method 1, 9 colors, align ~0.96 |
| Tree panel cream/black (misaligned) | Method 2, 2 colors, cream ~31% |
| Star mandala (aligned, AI ref) | Method 1, 4 colors after stray merge |
| AI floral all-over | half-drop, ~502×316, shear ~5°, mirror nahi |

## Kya NAHI karna
- Boundary smoothing / Gaussian label smoothing.
- Colored image ka bilinear/bicubic resize.
- Mill ko 600 DPI bhejna.
- Repeat analysis ke bina tile kaatna.
- Brand/third-party designs ditto copy karna.
