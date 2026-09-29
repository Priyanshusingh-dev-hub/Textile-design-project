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

## 2. Ek design ke chaar step

| Step | Kya hota hai |
|---|---|
| **1. Upload** | Design daalo (PNG, JPG, TIFF, PSD). |
| **2. Reduce** | Program khud batata hai kitne inks lagenge ("✨ suggested"), aur texture cleanup khud chunta hai. **Reduce design** dabao. Match % dikhega — 88% se upar achha hai. |
| **3. Separate** | Har ink ki alag plate. Neeche plates ki patti. Kapde ka rang chuno. 🎨 se kisi plate ka rang badal sakte ho. |
| **4. Export** | Print ki chaudai (inch) daalo → **⬇ Download .zip**. Zip me films (TIFF, 300 DPI, registration marks), plates, proof aur job sheet. |

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
`500 m, 30 inch, 6 inks`. Use proof + quote + **✅ Approve / ✏️ Change** milta hai.
Approve par zip `Designs-Inbox/approved/` me, aur aapko Telegram par.
Jis design me dikkat ho, wo pehle aapke paas aata hai ("Client ko bhejo / Rok do").
LoomLab band ho to design line (queue) me rehta hai — LoomLab chalu karte hi
proof apne aap client ko chala jaata hai.

## 3a. Hot Folder (email / WhatsApp / pen-drive wale designs)

1. **`run-hotfolder-windows.bat`** double-click (LoomLab bhi chalu ho). `Hot-Folder` khul jaayega.
2. Design **`in`** folder me daalo. Kuch second me:
   - **`ready`** — sab theek: zip (films), proof, quote, report.
   - **`check`** — ek baar dekho, `report.txt` me wajah likhi hai.
   - **`failed`** — nahi chala, wajah `.why.txt` me.
3. File ke naam me settings likh sakte ho: `rose 30in 500m 6inks.png`
   (30 inch chaudai, 500 meter ka quote, 6 inks).

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
hai — aakhri faisla aapka.

## 4. Jobs (header me "Jobs" button)

Bot aur auto mode ke saare kaam ek list me. Laal number = kitne kaam aapka
intezaar kar rahe hain. "✓ Checked", "✕ Stop", "Approved" dabao, ya zip lo.

Upar pichhle 30 din ka hisaab: kitne design aaye, kitne bina aadmi ke nikle,
kitne approve hue, kitne ka quote gaya, aur **kitna time/paisa bacha** (ye
andaza hai — Settings me "A design by hand" (haath se kitne minute), "Checking"
aur "Operator cost" aapke hisaab se bharo). Poora record
`backend/data/job-log.csv` me hamesha rehta hai (Excel me khulta hai) — pilot
me mill ko dikhane ke kaam aata hai.

## 4a. Library (repeat order)

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

- App nahi khul raha → "LoomLab" wali window me jo likha hai, Claude ko bhejo.
- Match kam / "needs review" → design ki file chhoti hai ya photo jaisi shading
  hai. Designer se **badi original file** mango.
- Telegram bot jawab nahi deta → bot wali window me error dekho; LoomLab chalu hai?
