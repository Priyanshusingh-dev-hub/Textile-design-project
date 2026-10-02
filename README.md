# LoomLab — Textile Color-Separation Tool

> Hinglish me aasaan guide: **[GUIDE-HINDI.md](GUIDE-HINDI.md)**

A simple, offline tool for screen-printing mills: take a design, reduce it to a
printable number of inks, and generate clean, print-ready color-separated
plates — **without hurting the design's quality**.

LoomLab does **not** generate artwork. It processes a design you already have
(from a client, or one you made elsewhere) through four steps:

1. **Upload** — PNG, JPG, WEBP, TIFF, or PSD (up to 80 MB). Before/after preview.
2. **Reduce** — bring the colors down to a printable count (2–20 inks). LoomLab
   suggests a sensible count, shows a measured accuracy score, and decides by
   itself whether the file is grainy enough to need texture cleanup (clean and
   painterly art keeps every outline; a grainy scan is cleaned so its plates
   don't speckle). Fine-tune the palette:
   recolor, merge, or lock inks. When two inks are nearly identical it says
   which, and what merging them costs in match ("91.9% → 90.9%").
3. **Separate** — one flat screen per ink. Every pixel prints on exactly one
   plate — no overlap, no muddy fringe. The combined preview is those screens
   stacked back together, so **it is exactly what will print**. Pick your cloth
   colour and hide any ink that is the fabric itself; LoomLab spots the ground
   ink and offers, in one click, to print on cloth of that colour instead.
4. **Export** — a single `.zip` with color PNG plates, print-ready B&W TIFF
   screens (300 DPI) with registration marks and a label on every film, a
   full-color proof, a one-page **job sheet** to pin up at the press, and
   (optional) scalable **SVG** vector outlines. Screens are ordered light to
   dark, the usual press order. Set a **print width** to print larger than the
   file: the screens are redrawn at that size with smooth edges.

**Two ways in.** Upload offers **One design** (the four steps above) or
**Line art + reference**: the line art (black outlines) and a coloured
reference of the same design, same crop. Every closed area of the line art
takes the reference's majority colour (`POST /api/fill`, the textile tool's
fill: Auto by default, or Method 1 / 3 / 2; 3535 px at 300 DPI, no
smoothing); the result lands on Reduce as the
reduced design, with the alignment, the doubtful areas (shown in red) and a
pixel-by-pixel match against the reference, then Separate and Export as usual.
A pair that does not line up is refused unless the operator ticks to fill anyway.

**What was tried.** For a line art + reference pair the app does not trust
the line art: `auto` makes the design several ways (the reference alone through
Reduce, and each fill), scores each against the reference with the Reduce
step's own match, picks one, and shows the table (match, inks, edge cleanliness)
with the reason. Any other way is one click away. Every run is logged to
`data/fill-trials.jsonl` for tuning.

**Seamless repeats.** A repeat tile is printed edge to edge, so its left edge
meets its own right edge on the cloth. LoomLab detects a seamless repeat (per
axis — a border print repeats one way) and processes it wrapped round, so no
line appears at the join; the Reduce step says when it has done so.

### Printing bigger than the file

At its own size a design prints at 300 of its pixels per inch — a 1254 px
file is 4.2 in wide. Type a **print width** on the Export step and every
screen is redrawn at that size with **smooth edges** instead of enlarged
stair-steps, still one ink per pixel; the proof is drawn at that size too, so
you can zoom in and check the edges before you download. It is honest about
the limit: edges become smooth, but detail finer than the file itself (fine
texture, tiny dots) can't be invented.

How: each ink is treated as a field, the fields are blurred slightly and
resampled, and each output pixel goes to the ink whose field is highest —
smooth outlines, exactly one winner per pixel. A blur erases 1px lines, so
afterwards every ink's thin parts are painted back from the unblurred field.
Against shapes drawn at 8x, this cuts edge error to 65% of plain enlarging
while a 1px diagonal line survives 92% of its length (plain enlarging: 66%).
A bureau's pre-separated PSD is resized channel by channel, keeping its
overlaps.

### Printing on coloured or dark cloth

Set the cloth colour and the preview shows the design on that fabric. On dark
cloth LoomLab also emits a **white under-base** screen (`0-Underbase`, printed
first, choked 1px so the white never peeks past the colour above it) — without
it, inks laid straight onto dark fabric go muddy. The colour plates stay
mutually exclusive; the under-base is an additional screen.

The choke is feature-aware. A plain erosion erases anything as thin as it is,
so stems, outlines and veins would lose their base entirely and print dull
straight onto the cloth while the shapes beside them stayed bright. Where the
choke would wipe a feature out, the base is kept at full width there; solid
shapes still get their rim pulled in.

Transparent PNGs are handled correctly: a transparent background carries no
ink — it never becomes a plate or wastes an ink slot.

### Honest about fit

Screen printing needs flat artwork. If a design has smooth, photographic
shading, LoomLab says so plainly — rather than showing a low percentage and
leaving you to guess — and distinguishes that from simply needing more inks,
and points to **Print as dots**.

It also warns when a design has **soft, see-through edges** — a glow, a drop
shadow, a feathered rim. A flat ink cannot fade, so those edges print as a
hard cut, and the accuracy score won't reveal it because it measures the
pixels that do print. Ordinary anti-aliasing is not flagged: the two are told
apart by how *wide* the fade is (anti-aliasing measures about 3px whatever the
image size, a feather starts around 12px), not by how many pixels it covers.

### Print as dots, for photo-like designs

For a design flat inks can't reproduce (photo-like shading, a watercolour),
tick **Print as dots (index separation)** in Reduce. The same inks are placed
as fine dots (error diffusion) that mix into the shading seen from a step
away — still exactly one ink per pixel, so plates, proofs, colour changes and
colourways all work as usual. The match is then measured as seen (both
images blurred a little first): on a photo-like test, 64% as flat inks, 80%
as dots.

At a print width every dot is the same square of film pixels: the dotted
design is averaged onto that grid and dithered again there (scaling the dots
by, say, 2.49 would make them 2 and 3 px by turns — a beat that shows as
bands). Export says how big each dot prints and warns when a mesh won't hold
it (under 0.12 mm) or the pattern will show (over 0.45 mm; a larger file from
**High-resolution design file** gives finer dots). No trap, vectors or
tiny-dot cleaning with dots — each would destroy them. Unticking goes back to
flat inks with your palette edits kept (one undo step).

### Tiny dots a screen can't hold

A reduced painterly design leaves thousands of 1–4 px islands of ink (the
sample floral at 10 inks: 7,359 dots under 0.2 mm). A screen's mesh can't
hold them: they print as nothing, or clog and print as dirt. Export tells you
how many each design has **at the size you print it** (enlarging redraws edges
smooth, so at 12 inches the same floral has 24), and **Clean tiny dots**
(off by default; under 0.15 / 0.2 / 0.3 mm) gives each one to the ink around
it. Still one ink per pixel: the cleaned films rebuild the packaged proof
exactly. A small motif that continues across a repeat's seam is not a dot.

### Trap (optional, off by default)

Screens slip a fraction of a millimetre on any press. Where two colours meet
edge to edge, that slip can leave a thin line of bare cloth between them.
If your prints show those lines, set **Trap between colours** at Export
(1 px ≈ 0.08 mm, 2 px ≈ 0.17 mm, 3 px ≈ 0.25 mm at 300 DPI).

Each lighter ink is then spread under the darker inks it touches, on the
films only. The package already prints light to dark, so the darker ink
covers the spread and the print looks exactly like the proof: stacking the
trapped films in press order rebuilds the design pixel for pixel (tested).
Nothing spreads onto bare cloth, so no shape grows. Leave it off when your
registration is tight: the films are then exactly the separation, one ink
per pixel. Pre-separated PSDs keep the bureau's own trapping and don't
offer it.

### Change any plate's colour, with a live preview

After Separate, **🎨 Change plate colours** lists every plate. Each one gets
a colour picker, a hex box (type a mill's ink code), one-click picks from the
other plates' inks and your shelf inks, and ↺ to put it back. The preview
**follows every change instantly** in the browser, even while you drag the
picker. The cloth colour can change there too. **Done** keeps the colours
(plates, proof, job sheet and export all use them); **Cancel** puts every
plate back.

Only the ink colours change. The films are the separation's geometry and
stay exactly as they were, so this is also how to make a **colourway**: same
screens, other inks.

### Colourways: one set of screens, several colour sets

Mills sell one design in several colourways and burn its screens once. On
Export, **🎨 Colourways → + Save current colours** keeps the plates' inks (and
the cloth) as colourway A; change the plate colours (Separate → 🎨), come back
and save B, and so on (up to 8; **show** puts one back on the plates). The zip
then carries the films once, plus `colourways/<name>/proof.png` and
`job-sheet.png` for each: which ink goes on which screen (by the number on the
film), lightest first for *that* colourway, and the README lists them. A trap
is made for one set of inks, so it is off while there are colourways.

### Small inks: fewer screens, same look

An ink covering 1–2% of a design still costs a whole screen. Reduce lists
the inks under 2% (or 1% / 3%) and removes them in one click (one undo step).
Each of their pixels goes to the **remaining ink closest to its original
colour**. So a highlight ink used on both leaves and petals splits into the
leaf ink and the petal ink, instead of all going to one colour. The card
shows the match before and after.

Measured on the sample floral: 16 inks minus the small ones gives a design
closer to the original than reducing straight to that many inks (worst-case
error 16.9 vs 18.2; from 14, mean 2.84 vs 3.03). A small ink that nothing
else resembles (the only yellow of a tiny star) is **kept**, and the card
says why: removing it would visibly change the design. You can still merge
it by hand from the palette.

### Your own inks

**My inks** (in Reduce) keeps the list of inks your ink kitchen already has —
typed in, pasted from a sheet ("Rani Pink 12, #D96A8E", one per line), or
taken from the design on screen. It is saved on the PC running LoomLab
(`backend/data/inks.json`), so it is there for every job.

Next to each palette colour you see the nearest ink you own and how far off
it is (ΔE2000). Within ΔE 5 one click prints with your ink instead — or
**Use my inks** swaps every close one at once (one undo step). Further than
that, LoomLab tells you to mix a new ink rather than change your design
behind your back. Screens, plates and the job sheet then carry your ink
names. One of your inks is only ever given to one palette colour, so two
screens are never silently merged.

### Pick up where you left off

A reload, a closed tab or a browser crash doesn't lose the job: the Upload
step offers **Continue your last job** — palette edits, undo steps, plates
switched off, cloth colour and print width included. The engine keeps a
job's images for 48 hours; if some were cleared, the job resumes as far as
they reach and tells you which step to redo.

### Hinglish

The **हिं** button in the header switches the whole app to Hinglish (Roman
script, the way operators and the Telegram bot write) — steps, buttons,
labels, notes and messages; **EN** switches back. The choice is remembered on
that PC.

## Quality bar

The reduced design looks like the original — only with fewer colors: smooth
edges, no lost detail, no torn shapes. Reduction removes colors, not quality.
This is achieved with:

- an **edge-aware LAB k-means**: anti-aliased transition bands are excluded so
  no ink is wasted on a blend colour — the cause of muddy halos;
- a **thin-feature detector** so genuine fine linework (stems, outlines, veins)
  is kept even though it reads as "edge" — a smooth transition equals the local
  blur, a thin line is a spike far from it;
- **CIEDE2000** perceptual merging of near-duplicate colours; and
- a majority-filter edge cleanup that protects those thin features.

A measured reconstruction accuracy (mean ΔE2000, over printed pixels only)
scores every palette so tuning is objective, not guesswork. Verified against
five design archetypes (geometric, line art, continuous-tone, scanned-with-
grain, logo): every pixel lands on exactly one plate, and stacking the plates
reproduces the reduced design byte-for-byte.

Mill-sized files stay usable: above ~2.5 MP the palette is computed from a
downscaled proxy and the full-resolution image is assigned block-wise, so
memory and time stay bounded.

## The textile tool (`textile_project/`)

One command for the rest of the design work, built from the user's tested
scripts in `textile_project/reference_code/` (Hinglish guide:
`textile_project/CLAUDE.md`, plan: `ROADMAP.md`):

| Command | What it does |
|---|---|
| `fill --method auto` | line art + reference -> flat channels (Method 1, 3 = drifted reference, 2 = different drawing, 2 colours) |
| `repeat` | repeat type, block size, drop, shear, mirror; a panel print is named |
| `tile` | the seamless repeat block (repeat analysis first, seam-cut), upscaled, optional flat colours |
| `make` | an original repeat or panel from a JSON config (`examples/`) |
| `batch` | every `NAME_lineart` + `NAME_ref` pair in a folder |
| `edges` | cleans every ink's outline (corner- and thin-line-keeping), drawn on the 3535 px grid |
| `vector` | straightens a flat design's pixel staircases (+ SVG), on request |
| `export` / `verify` / `palette` | flat design -> mill package / check one / list its colours |

Windows: put pairs in `textile_project\input` and double-click
**`run-textile-windows.bat`**. By hand: `cd textile_project && pip install -r
requirements.txt && python -m textile --help`. Defaults are the mill's:
3535 px at 300 DPI, flat colours, no smoothing, no `#` in file names.

## Colorfill: line art + coloured reference (on trial)

A separate tool in `colorfill/`, beside LoomLab. Give it two files of the same
design: the **line art** (black outlines) and a **coloured reference** (same
crop, flat colours). Every closed area of the line art gets the reference's
most common colour there, the lines get the outline colour, and you get:
the final design (TIF for the mill, PNG), one PNG per colour channel, black &
white separations, a preview sheet and a report — 3535 px at 300 DPI
(11.78 in) by default, with no smoothing.

Windows: put `NAME_lineart.png` and `NAME_colored.png` in `colorfill/input/`
and double-click **`run-colorfill-windows.bat`**; results land in
`colorfill/output/NAME/`. By hand: `cd colorfill && pip install -r
requirements.txt && python colorfill.py --line input/a_lineart.png --ref
input/a_colored.png --out output/ --name a`. It stops if the two images don't
line up. If the report has `doubtful_regions`, open the
`*_DEBUG_doubtful_regions.png` it makes: a gap in a line lets one area's
colour flow into the next, and the fix is to close that gap in the line art.
Rules and checks: `colorfill/CLAUDE.md`.

## Run on Windows

Double-click **`run-windows.bat`**. It sets up the engine the first time,
builds the app, starts **one** server and opens the app at
`http://localhost:8003`. Node.js is needed only to build the app; a copy with
`frontend/dist` already built runs without it.

## Auto mode (no operator)

One API call takes a design to a finished production package. The engine
picks the ink count and texture cleanup, then reduces, separates and exports
exactly as the app's own steps do, and reports whether the job is safe to
print unseen:

```bash
curl -F file=@design.png -F width_in=30 localhost:8003/api/auto/upload
# or, for a design already uploaded:  POST /api/auto  {"image_id": "...", "width_in": 30}
```

The answer is a report: `status` is `auto_ok` or `needs_review`, with the
match, the inks and their coverage, the print size, how long each step took
and every warning found. Each warning has a code and says in plain words
what is wrong:

| code | means | stops the job |
|---|---|---|
| `photographic` | continuous-tone shading: flat inks print it as bands | yes |
| `low_match` | the match is under `min_accuracy` | yes |
| `soft_edges` | feathered edges a flat ink prints hard | yes |
| `tiny_dots` | too much of the print is dots the mesh can't hold | yes |
| `similar_inks` | two inks look almost the same; one screen could go | yes |
| `many_inks` | more screens than `max_inks` | yes |
| `low_resolution` | enlarged past `min_source_ppi`: fine lines come out coarse | yes |
| `grainy_source` | texture cleanup was applied | no |
| `seamless_repeat` | repeat tile, processed so the join stays invisible | no |
| `small_inks` | inks under 2% that could be dropped | no |

The thresholds and which codes stop a job live in `backend/auto-config.json`
(read on every job, so an edit needs no restart). Change them in the app under
**⚙ Settings** — every value is checked before it is saved. The zip and report stay
for 48 hours: `GET /api/auto/{job_id}/package` and `GET /api/auto/{job_id}`.

### Job dashboard

The **Jobs** button in the header lists every auto-mode job (from the
Telegram bot or scripts), newest first, with its proof, match, inks, quote and
warnings. It opens on **Needs review**: only the jobs auto mode held that
nobody has dealt with yet; the red number on the button counts them. Mark a
job **✓ Checked** or **✕ Stop**, later **Approved**, or download its package.
The bot records its own steps there too (sent to the client, approved,
changed, stopped). `GET /api/jobs` and `POST /api/jobs/{id}/stage` do the same
from a script.

Above the list, **the last 30 days**: designs, how many needed nobody,
approved, the value quoted and **time saved** — an estimate from your own
numbers in Settings (minutes a design takes by hand, minutes to check a held
one, an operator's hour), shown as one. They come from `backend/data/job-log.csv`,
one line per job and per stage change, kept for good (the jobs themselves
leave the cache after 48 h) and readable in Excel. `GET /api/stats?days=30`.

### Clients

Jobs → **👥 Clients**: every client's designs (each counted once), approved /
stopped / waiting, approved meters, repeat orders and what they brought in
(approved quotes + repeat orders), the biggest first, for 30 days, 3 months or
a year. A client with their own rates is marked. `GET /api/clients?days=90&client=`.

### Design library and repeat orders

A mill's best business is the repeat order — *the same design, 500 m more* —
and for that the screens already exist. When a job is marked **Approved** (on
the Jobs page, or by the client on Telegram) it is copied to the **📚 Library**
tab on Jobs, kept for good (`backend/data/library/`, never cleared with the
48 h cache): its proof, inks and the production zip. There you can search by
design or client, download the **films** again to burn a worn screen, and
**₹ Repeat quote**: the price for any meters from the stored ink coverage,
with no screens charged (the quote image says it is a repeat order).
`GET /api/library?q=`, `POST /api/quote {library_id, meters}`.

### Benchmark: how many designs need nobody

Drag a folder of designs onto **`run-benchmark-windows.bat`** (or run
`python -m app.benchmark <folder> [--width-in 30] [--meters 500]` in
`backend/`). Every design goes through auto mode and a report opens in the
browser: how many came out print-ready untouched, the time per design, the
match, the inks, the quote, and what held the rest. `report.csv` (Excel) and
`report.json` sit beside it in `<folder>/benchmark-<date>/`.

To prove LoomLab against the mill's own work, save the operator's separation
of a design beside it as `NAME.operator.png`: the report then compares both
with the original on the same measure (colour difference, pixel by pixel)
and counts where LoomLab is as good or better.

## High-resolution design file

On the Export step, **High-resolution design file** enlarges the design on
this PC to a print width (e.g. 30 in at 300 DPI = 9000 px wide) and offers it
as TIF, JPG or PNG with the DPI written in. It also shows a **match score**:
the enlargement shrunk back to the original's size and compared pixel by
pixel. An honest enlargement scores about 98%; under 95% the design was
changed on the way, and it says so.

It uses Lanczos (smooth edges, invents nothing) unless the **Real-ESRGAN**
upscaler is installed: download `realesrgan-ncnn-vulkan` for your system from
the Real-ESRGAN GitHub releases and unzip it into `tools/realesrgan/` (or set
`REALESRGAN` to the program). It runs on the PC's graphics card, with no
internet; if it fails, Lanczos is used and the note says why. Like any AI
upscaler it can redraw fine detail; the match score is there to catch that.

## Cost and quote

Type how many meters to print on the Export step and press **₹ Quote**: LoomLab
prices the run and makes a quote image, 1080 px wide, to send straight on
WhatsApp or Telegram. Auto mode does the same when it is given `meters`
(`-F meters=500`), and `POST /api/quote` quotes any screens or auto job.

Ink is weighed, not guessed: each screen lays ink only where it prints, so
its ink = coverage x printed area (meters x cloth width) x grams per square
metre. The prices come from `backend/rate-card.json`, read on every quote
(edit them in the app under **⚙ Settings**, or in the file):

| setting | meaning |
|---|---|
| `screen_cost` | making one screen |
| `ink_per_kg`, `ink_prices` | ink price per kg; `ink_prices` sets it per ink name ("Rani Pink 12") or hex |
| `underbase_ink_per_kg` | the white under-base ink |
| `ink_g_per_sqm` | grams of ink per m² printed at full cover |
| `fabric_width_in`, `fabric_per_meter` | cloth width; cloth price per meter (0 = the client supplies it) |
| `labour_per_meter_per_screen` | printing labour: every screen passes every meter |
| `setup_per_job` | table setup, washing, a sample |
| `wastage_percent`, `margin_percent`, `gst_percent` | extra ink and cloth for setup and rejects; your margin (spread over the lines the client sees); GST |
| `clients` | a regular client's own rates, e.g. `{"Ravi Textiles": {"margin_percent": 10, "screen_cost": 1200}}` |

**Client rates** (Settings → Quote prices → Client rates): per client, by
name as it is on the job or quote (case and spacing ignored), only what
differs — margin, screen, printing, setup, ink or cloth; a blank box is the
rate card's. Every quote for that client (the app, auto mode, the bot, repeat
orders, the AI operator) uses them and says so. GST, wastage and the ink
model are the same for everyone.

## Licence (one PC, one activation)

LoomLab can require a licence per PC, checked offline. It is **off until you,
the seller, make your key pair**, so development and demos run as before.

1. Once, on your own PC: `cd backend && python -m app.licence keygen`. It
   writes your **private key** to `~/loomlab-private.key` (keep it safe and
   secret: never on a mill PC, never in git) and `backend/licence-public.key`,
   which ships with LoomLab from then on.
2. A mill's LoomLab now opens on an activation screen showing its **machine
   code** (e.g. `7491-039B-9AAC-2E80`). They send it to you.
3. You issue a key for that PC:
   `python -m app.licence issue --machine 7491-039B-9AAC-2E80 --mill "Shree Textiles" --days 365`
   (`--days 0` never ends). They paste it in and LoomLab opens.

A key works only on the PC it was issued for, cannot be changed without
breaking its signature (Ed25519), and says when it ends. The Telegram bot, auto
mode and the benchmark go through the same engine, so they need it too.

## Receive designs on Telegram

A Telegram bot can act as the mill's inbox: anyone who sends it a design gets
it saved on the LoomLab PC, and the operator opens it in LoomLab from there.
The bot only stores files; it does no colour work.

1. In Telegram open **@BotFather**, send `/newbot`, pick a name. It replies
   with a **token** (`123456789:AA...`). Treat it like a password.
2. Double-click **`run-bot-windows.bat`**. The first time it creates
   `telegram-bot.txt` and opens it: paste the token after `TOKEN=`, save,
   and double-click the launcher again.
3. Keep that window open. Designs land in `Designs-Inbox/<date>/` (or the
   `FOLDER=` you set), named `time_sender_filename`, and every one is listed
   in `Designs-Inbox/inbox-log.csv` with its sender and caption.

Tell senders to attach the design as a **File / Document**. Sent as a
*Photo*, Telegram shrinks and recompresses it; the bot still saves it but
says so. Telegram lets a bot fetch files up to 20 MB; the bot replies when
one is bigger. To accept designs only from known people, put their Telegram
ids in `ALLOWED=` (anyone can send the bot `/id` to learn theirs). The bot
asks Telegram for new messages, so the PC needs no open port or public
address, and a design sent while the PC was off is saved when it starts.

### Proof, quote and approval on Telegram

With LoomLab running (`run-windows.bat`), every design the bot saves also goes
through [auto mode](#auto-mode-no-operator), and the client gets back, in the
same chat, the proof, the quote image and two buttons: **✅ Approve** and
**✏️ Change**.

- The client can write the job in the caption: `500 m, 30 inch, 6 inks`.
  Without it, `WIDTH_IN=` and `METERS=` in `telegram-bot.txt` are used (no
  meters, no quote).
- **Approve**: the production zip is saved in `Designs-Inbox/approved/<date>/`
  and sent to the operator (a zip over 50 MB stays on the PC, and the operator
  is told where).
- **Change**: the client writes what to change ("6 inks", "40 inch", "800
  meter") and gets a new proof. Anything else ("make the red darker") goes to
  the operator as written.
- A job auto mode holds (`needs_review`) goes to the operator first, with the
  reasons and **Send to client** / **Stop** buttons; the client is told the
  team is checking it. Put the operator's Telegram id in `OPERATOR=`. Without
  one, it goes to the client with a note that the team will check it too.
- `ENGINE=off` turns all of this off: the bot only saves designs, as before.
  If LoomLab isn't running, the design is still saved and waits in a queue
  (in `orders.json`, so a restart keeps it): the client and operator are told,
  and the proof goes out on its own once the engine answers again.
- Every order and where it stands is kept in `Designs-Inbox/orders.json`,
  so a restart loses nothing.
- **Repeat orders**: a client writes *"repeat 500 m"* (or *"wahi design
  500 m aur"*, *dobara*, *same*). The bot finds the designs that client
  approved before (in the library), asks which one if there are several
  (each with its proof and a button), sends the repeat quote — no screens
  charged — and **✅ Order pakka**; on that the order is recorded in LoomLab
  (the Library and the Jobs numbers) and the operator is told which design,
  how many meters and where the films are.
- **Other colours**: **🎨 Doosre rang me dekho** under the proof. The bot
  lists the inks by number and colour name; the client writes in their own
  words — *"pink ko neela"*, *"1 navy, 3 cream"*, *"kapda kala"*, *"halka
  hara"*, or a #code — and gets the same screens in those inks back, each
  message building on the last (*"bas"* stops). **✅ Isi rang me banao**
  makes it a job of its own: films, proof and quote in the new inks (a shelf
  ink within ΔE 5 is used and named; dark cloth gets the white under-base),
  sent for approval like any job. `POST /api/auto/{id}/colourway`.
- **Their own orders**: *"mere order"* (or `/orders`) lists the client's own
  orders and where each stands — found by their Telegram id, never by name.
- **Dots**: *"dots"* in the caption makes a photo-like design a dotted job.

## Backup

**⚙ Settings → Backup → ⬇ Download backup** gives one zip with everything the
mill has built up: the design library (with its films), the job log, the shelf
inks, the rate card and auto mode's limits. Keep it on a pen drive or in the
cloud. **⤒ Restore a backup** puts it back on any LoomLab (a new PC): every
part is checked before anything is written; the library, inks, prices and
limits are replaced and the job log is added to. `GET /api/backup`,
`POST /api/backup/restore`.

## Hot folder: drop a design, get its screens

For designs that arrive by email, WhatsApp Desktop or a pen drive. Double-click
**`run-hotfolder-windows.bat`** (LoomLab must be running too): it opens the
`Hot-Folder` folder and watches it.

| folder | what is in it |
|---|---|
| `in/` | put design files here |
| `ready/` | auto mode found nothing to worry about: `…-screens.zip` (films, plates, proof, job sheet), `proof.png`, `quote.png`, `report.txt` and the original |
| `check/` | the same, held for a person — `report.txt` says why |
| `failed/` | LoomLab could not run it, with a `.why.txt` |

Settings can ride in the file name, as a client writes them in a caption:
`rose 30in 500m 6inks.png` prints 30 inches wide, prices 500 m and uses 6
inks (add `dots` for a photo-like design); anything not written is chosen by
the engine. A file still being copied
is left until it stops growing, and if the engine is closed the files simply
wait in `in/` and go through when it is back. Every job is also on the Jobs
dashboard.

## Claude as the operator (MCP)

LoomLab's steps are tools an AI can use: the **AI decides, the engine does
every pixel on this PC**. Claude Desktop or Claude Code, connected to
LoomLab, can look in the inbox, run a design, *look at the proof* (it gets
the image), re-run it with another ink count or print width, price it, mark
the job on the dashboard and save the zip — and leave what it is unsure about
to a person.

- Windows: double-click **`setup-claude-windows.bat`** once (after
  `run-windows.bat` has run once). It adds LoomLab to Claude Desktop's
  settings (keeping a `.bak` of them) and prints the Claude Code command.
  Restart Claude Desktop.
- By hand: `cd backend && python -m app.mcp_server --setup` prints what to
  paste.
- Then ask, e.g. *"LoomLab inbox me naye designs dekho, sab chalao, aur jo
  theek na ho wo mujhe batao."*

Tools: `list_inbox`, `separate_design`, `rerun_job`, `get_job` (proof, and the
original to compare), `list_jobs`, `mark_job`, `quote_job`, `preview_colourway`
("show this design in navy and gold" on the same screens), `save_package`
(with colourways if asked), `make_colourway_job` (the same screens in other
inks as a job of its own), `find_design` and `repeat_quote` (the library),
`job_stats` and `client_summary`. `separate_design` / `rerun_job` take
`dots=true` for a photo-like design.
The server (`backend/app/mcp_server.py`, standard library, stdio) talks to
the running engine like the Telegram bot does, so the dashboard shows
everything it does. The colour work stays local and offline; only the
decisions go through the AI you connect.

## Run manually

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

Frontend (in another terminal):

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`).

## Architecture

- `backend/app/color_engine` — LAB palette analysis, reduction, CIEDE2000
  merging, measured reconstruction accuracy.
- `backend/app/separation_engine` — mutually-exclusive flat spot-color screens
  and per-plate proofs.
- `backend/app/vector_engine` — pixel-boundary contour tracing to clean,
  hole-aware (even-odd) SVG outlines.
- `backend/app/core` — image store, PSD import (including pre-separated
  multichannel PSDs), registration marks, zip packaging.
- `frontend/src` — the four-step React workspace (pure prepress helpers in
  `src/lib/print.ts`).

Everything runs locally; no external AI or API is used for color processing.

## Tests

```bash
cd backend && pytest          # engine, API and export
cd frontend && npm test       # prepress helpers and error formatting
```
