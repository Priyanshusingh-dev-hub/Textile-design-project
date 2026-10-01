# LoomLab — aasaan guide (Hinglish)

Screen printing mill ke liye design ko kam inks me todna, har ink ki screen
(film) banana, aur poora production package dena. Sab kuch mill ke PC par,
bina internet ke.

---

## 1. Chalu kaise karein (Windows)

1. Python aur Node.js install hone chahiye (pehli baar).
2. LoomLab folder me **`run-windows.bat`** par double-click.
3. Ek window khulegi ("LoomLab") — ise **khula rakhna**. Browser me app apne
   aap khul jaayega: `http://localhost:8003`.

Pehli baar setup me thoda time lagta hai, baad me jaldi khulta hai.

**App Hinglish me:** upar header me **हिं** button dabao — saare button, naam
aur sandesh Hinglish me aa jaayenge (English ke liye **EN**). PC yaad rakhta hai.

## 2. Ek design ke chaar step

| Step | Kya hota hai |
|---|---|
| **1. Upload** | Design daalo (PNG, JPG, TIFF, PSD). |
| **2. Reduce** | Program khud batata hai kitne inks lagenge ("✨ suggested"), aur texture cleanup khud chunta hai. **Reduce design** dabao. Match % dikhega — 88% se upar achha hai. |
| **3. Separate** | Har ink ki alag plate. Neeche plates ki patti. Kapde ka rang chuno. 🎨 se kisi plate ka rang badal sakte ho. |
| **4. Export** | Print ki chaudai (inch) daalo → **⬇ Download .zip**. Zip me films (TIFF, 300 DPI, registration marks), plates, proof aur job sheet. |

**Photo jaisa design** (mulayam shading, jaise photo ya watercolour): flat inks
me ye patte (bands) ban ke chhapta hai — app khud bata deta hai. Reduce me
**☐ Dots me chhaapo (index separation)** tick karo: wahi inks baareek dots me
lagti hain jo thodi door se shading ban jaati hain (har pixel par phir bhi ek
hi ink). Export par likha aata hai har dot kitne mm ka chhapega — 0.12 se 0.45 mm
ke beech theek hai; baareek jaali (mesh) chahiye. Dots ke saath trap, vector
aur bindiyon ki safai nahi hoti (dots hi design hain). Tick hatao to wapas
flat — aapke badle hue rang waise hi rehte hain, aur Undo bhi chalta hai.

Export step par neeche **Extras** me do cheezein aur (naam par click karke kholo):
- **Quote a print run**: meter daalo → **₹ Quote** → WhatsApp par bhejne layak quote image.
- **🎨 Colourways**: ek hi screens se alag rang ke set. "+ Save current colours"
  se abhi ke rang A ban jaate hain; Separate me 🎨 se rang badlo, wapas aake
  B save karo. Zip me har colourway ka proof aur job sheet (kaunsi ink kis
  screen number par) — nayi screen nahi banani padti.
- **High-resolution design file**: design ko bada karke TIF/JPG/PNG (300 DPI).
  "Match" 95% se kam aaye to design badal gaya — dhyan se dekho.

## 3. Telegram bot (design lena + proof + quote + approval)

1. Telegram me **@BotFather** → `/newbot` → token milega.
2. **`run-bot-windows.bat`** double-click → Notepad khulega (`telegram-bot.txt`):
   - `TOKEN=` ke aage token (kisi ko mat dikhana).
   - `OPERATOR=` ke aage apni Telegram id (bot ko `/id` bhejo, wo batayega).
   - `METERS=` default meter (quote ke liye), `WIDTH_IN=` default print chaudai.
3. Save karke bat dobara chalao. **LoomLab (`run-windows.bat`) bhi chalu rehna chahiye.**

Client design **File** ki tarah bheje (Photo nahi), caption me likh sakta hai:
`500 m, 30 inch, 6 inks` (photo jaisa design ho to `dots` bhi). Use proof +
quote + **✅ Approve / ✏️ Change / 🎨 Doosre rang me dekho** milta hai.
Approve par zip `Designs-Inbox/approved/` me, aur aapko Telegram par.
Jis design me dikkat ho, wo pehle aapke paas aata hai ("Client ko bhejo / Rok do").
LoomLab band ho to design line (queue) me rehta hai — LoomLab chalu karte hi
proof apne aap client ko chala jaata hai.

**Repeat order**: client likhe `repeat 500 m` (ya "wahi design 500 m aur").
Bot uske pehle approve kiye design dhoondhta hai, quote bhejta hai (screen ka
kharcha nahi), client "✅ Order pakka" dabaye to order LoomLab me (Library aur
Jobs ke hisaab me) likha jaata hai aur aapko Telegram par batata hai.

**Doosre rang (colourway)**: client **🎨 Doosre rang me dekho** dabaye. Bot
design ke rang number ke saath batata hai (1) beige, 2) brown…). Client apni
bhasha me likhe: `pink ko neela`, `1 navy, 3 cream`, `kapda kala`,
`halka hara`, ya `#1B2A4A` — bot wahi screens naye rang me dikhata hai. Har
naya sandesh pichhle badlav par judta hai; `bas` likhne se band. **✅ Isi rang
me banao** dabaye to naye rang ka alag job ban jaata hai (films, proof, quote
naye rang me; kapda gehra ho to safed under-base apne aap) aur client ko
Approve/Change ke saath jaata hai. Aapki shelf ki koi ink paas ho (My inks) to
wahi ink aur uska naam lagta hai.

**Apne order**: client `mere order` (ya `/orders`) likhe to use sirf uske apne
order aur har ek ki haalat milti hai.

## 3a. Hot Folder (email / WhatsApp / pen-drive wale designs)

1. **`run-hotfolder-windows.bat`** double-click (LoomLab bhi chalu ho). `Hot-Folder` khul jaayega.
2. Design **`in`** folder me daalo. Kuch second me:
   - **`ready`** — sab theek: zip (films), proof, quote, report.
   - **`check`** — ek baar dekho, `report.txt` me wajah likhi hai.
   - **`failed`** — nahi chala, wajah `.why.txt` me.
3. File ke naam me settings likh sakte ho: `rose 30in 500m 6inks.png`
   (30 inch chaudai, 500 meter ka quote, 6 inks). Photo jaisa design:
   naam me `dots` bhi (`photo 12in dots.jpg`).

LoomLab band ho to files `in` me intezaar karti hain — chalu hote hi chal jaati hain.

## 3b. Claude ko operator banao

Claude (Desktop ya Code) LoomLab khud chala sakta hai: inbox dekhe, design
chalaye, **proof dekh ke** faisla kare, inks badal ke dobara chalaye, quote
banaye, job "Checked/Stop" kare, zip save kare. Rang ka saara kaam PC par hi
hota hai; Claude sirf faisle leta hai.

1. `run-windows.bat` ek baar chal chuka ho.
2. **`setup-claude-windows.bat`** double-click → Claude Desktop band karke dobara kholo.
3. Claude se bolo: *"LoomLab inbox me naye designs dekho, sab chalao, jo theek
   na ho wo mujhe batao."*

Jis design par Claude ko shaq ho, wo Jobs list me "Needs review" me hi rehta
hai — aakhri faisla aapka. Claude photo jaisa design dots me dobara chala
sakta hai, naye rang ka job bana sakta hai ("ise navy ground me banao"), aur
client ka hisaab bata sakta hai ("Ravi Textiles ka is mahine ka kaam?").

## 3c. Colorfill (line art + rangeen reference) — trial par

LoomLab ke saath ek alag tool: ek hi design ki do files do.
- `NAAM_lineart.png`: kaali outline wala design
- `NAAM_colored.png`: wahi design flat rangon me (same crop)

1. Dono files `colorfill\input` folder me daalo.
2. **`run-colorfill-windows.bat`** par double-click karo. Pehli baar setup me internet aur thoda samay lagega.
3. Nateeje `colorfill\output\NAAM\` me milenge. Mill ko `*_final_3535px_300dpi.tif` bhejo. Har rang ka alag channel aur black & white separations zip me hain.

Agar `DEBUG_doubtful_regions.png` bane, use kholo: laal hisson me rang galat ho sakta hai. Aksar line art me koi line tooti hoti hai, aur us gap ko band karna padega. Dono images ek-doosre par na baithein to script ruk jaati hai (alignment).

## 4. Jobs (header me "Jobs" button)

Bot aur auto mode ke saare kaam ek list me. Laal number = kitne kaam aapka
intezaar kar rahe hain. "✓ Checked", "✕ Stop", "Approved" dabao, ya zip lo.

Upar pichhle 30 din ka hisaab: kitne design aaye, kitne bina aadmi ke nikle,
kitne approve hue, kitne ka quote gaya, aur **kitna time/paisa bacha** (ye
andaza hai — Settings me "A design by hand" (haath se kitne minute), "Checking"
aur "Operator cost" aapke hisaab se bharo). Poora record
`backend/data/job-log.csv` me hamesha rehta hai (Excel me khulta hai) — pilot
me mill ko dikhane ke kaam aata hai.

## 4a. Clients (kis client se kitna kaam)

Jobs page par **👥 Clients** tab: har client ke design, kitne pakke, kitne
baaki, pakke meter, repeat order, aur **kamaai** (pakke order + repeat order,
quote ke hisaab se) — sabse bada client sabse upar. 30 din / 3 mahine / 1 saal
chuno, ya naam se dhoondo. Jis client ke apne rate hain uspe "apne rate" likha
aata hai.

## 4b. Library (repeat order)

Jo job **Approved** hoti hai, wo Jobs page ke **📚 Library** tab me hamesha
ke liye save ho jaati hai. Client bole "wahi design 500 m aur":
Library me naam ya client se dhoondo → meter daalo → **₹ Repeat quote**. Screens
pehle se bani hain, isliye screen ka kharcha nahi judta. Screen ghis gayi ho
to **⬇ Films** se film dobara nikaalo.

## 5. Rate card (quote ke daam)

Header me **⚙ Settings** → "Quote prices" me daam badlo → **Save prices**.
Agla quote naye daam se banega. Galat number (jaise minus) daaloge to wo
dabba laal ho jaayega aur save nahi hoga. (Chaho to `backend/rate-card.json`
Notepad me bhi badal sakte ho.) Kuch mukhya:

| Setting | Matlab |
|---|---|
| `screen_cost` | ek screen banane ka kharcha |
| `ink_per_kg` | ink ₹ prati kg (`ink_prices` me har ink ka alag, jaise `"Rani Pink 12": 620`) |
| `ink_g_per_sqm` | poora dhakne par 1 m² me kitne gram ink |
| `fabric_width_in`, `fabric_per_meter` | kapde ki chaudai; kapda aapka ho to meter ka daam (0 = client ka kapda) |
| `labour_per_meter_per_screen` | chhapai: har screen har meter par |
| `wastage_percent`, `margin_percent`, `gst_percent` | wastage, aapka margin, GST |

**Client ke rate**: pakke client ko alag daam dena ho to Settings → Quote
prices ke neeche **Client ke rate** → **+ client** → client ka naam (jaise job
ya quote par hota hai) aur sirf jo alag hai wo bharo — munafa, screen,
chhapai, setup, ink ya kapda. Khaali dabba = rate card wala daam. Us client ka
har quote (app, bot, repeat order, Claude) apne aap uske rate se banta hai, aur
quote par likha aata hai "Ravi Textiles ke apne rate". GST aur wastage sabke
liye same.

## 5a. Backup (PC kharab ho jaaye to)

**⚙ Settings → ⬇ Download backup**: Library (films ke saath), job ka hisaab,
inks, daam aur limits — sab ek zip me. Hafte me ek baar pen drive ya Google
Drive par rakh do. Naye PC par LoomLab chalao → Settings → **⤒ Restore a
backup** → wahi zip chuno. Sab wapas aa jaata hai.

## 6. Auto mode ki seemayein

**⚙ Settings** → "Auto mode": kitna match chahiye, zyada se zyada kitni
screens, file kitni chhoti chalegi — aur neeche tick karo kaunsi dikkat par
kaam ruke (tick = aapke review ke liye rukega, bina tick = sirf bataya
jaayega). **Save limits** dabao; bot bhi agle design se yahi maanega.

## 7. Benchmark (pilot ke liye saboot)

Designs ka folder **`run-benchmark-windows.bat`** par kheench kar chhodo.
Report browser me: kitne design bina haath lagaye taiyaar, kitna time, kya
dikkat. Operator ki apni file `NAAM.operator.png` rakhoge to dono ki tulna bhi.

## 8. Licence (bechne ke liye)

Abhi band hai. Chalu karna ho to (sirf aapke apne PC par, ek baar):

```
cd backend
python -m app.licence keygen
```

**Private key** (`loomlab-private.key`) sambhal ke rakhna — kisi mill ke PC par
nahi, GitHub par nahi. Kho gayi to di hui saari keys bekaar.

Mill ka LoomLab "machine code" dikhayega → aap key banao:

```
python -m app.licence issue --machine 7491-039B-9AAC-2E80 --mill "Shree Textiles" --days 365
```

Wo key mill wale app me paste karenge.

## 9. Dikkat aaye to

- Koi kaam error de raha hai → **⚙ Settings → Madad → Engine jaancho → 📋 Report
  copy karo**, aur WhatsApp par bhej do (isme koi design, daam ya client nahi
  hota). Errors `backend/data/loomlab-errors.log` me bhi likhe rehte hain.
- App nahi khul raha → "LoomLab" wali window me jo likha hai, Claude ko bhejo.
- Match kam / "needs review" → design ki file chhoti hai ya photo jaisi shading
  hai. Designer se **badi original file** mango, ya photo jaisa ho to
  **Dots me chhaapo** try karo.
- Telegram bot jawab nahi deta → bot wali window me error dekho; LoomLab chalu hai?
