// The app in the mill's own words. English is the source text and the key;
// Hinglish (Roman script, the way operators and the Telegram bot write) is the
// other choice, picked in the header and remembered in this browser. A string
// not in the list shows in English, so a new label is never blank. {name}
// marks a value put in at run time; both sides must carry the same ones
// (tested).
import { createContext, useContext } from 'react';

export type Lang = 'en' | 'hi';
export const LANG_KEY = 'loomlab-lang';

export const HI: Record<string, string> = {
  // header and steps
  'Upload': 'Design daalo', 'Reduce': 'Rang kam karo', 'Separate': 'Screens banao', 'Export': 'Films nikalo',
  'Jobs': 'Kaam', '⚙ Settings': '⚙ Settings', 'READY': 'TAIYAAR', 'WORKING': 'CHAL RAHA', 'DONE': 'HO GAYA', 'ERROR': 'GADBAD',
  'COLOR SEPARATION': 'RANG ALAG KARNA',
  'Jobs from auto mode and the Telegram bot': 'Telegram bot aur auto mode ke saare kaam',
  "Quote prices and auto mode's limits": 'Quote ke daam aur auto mode ki seemayein',

  // Upload
  'Drop a design here': 'Design yahan chhodo',
  'PNG · JPG · WEBP · TIFF · PSD — up to 80 MB': 'PNG · JPG · WEBP · TIFF · PSD — 80 MB tak',
  'Continue your last job': 'Pichhla kaam jaari rakho',
  'Continue': 'Jaari rakho', 'Choose file': 'File chuno', 'Try a sample': 'Sample se dekho',
  // the second way in: line art + a coloured reference
  'One design': 'Ek design', 'LoomLab picks the inks': 'LoomLab khud inks chunega',
  'Line art + reference': 'Line art + reference', 'your outlines, the reference’s colours': 'aapki outline, reference ke rang',
  'Line art': 'Line art', 'black outlines on white': 'safed par kaali outline',
  'Coloured reference': 'Rangeen reference', 'the same design, same crop, in colour': 'wahi design, wahi crop, rang me',
  'Max colours': 'Zyada se zyada rang', 'used only when the reference has shading': 'sirf tab kaam aata hai jab reference me shading ho',
  'Outline colour': 'Outline ka rang',
  'auto = the colour under the lines in the reference, or a code like #120F06': 'auto = reference me lines ke neeche ka rang, ya #120F06 jaisa code',
  'Fill even if the two images do not line up well': 'Dono images theek se na bhi milein to bhi bharo',
  'Made at 3535 × 3535 px, 300 DPI (11.78 in), with no smoothing: every corner and dot stays as drawn.':
    '3535 × 3535 px, 300 DPI (11.78 inch) par banega, bina smoothing ke: har kona aur dot waisa hi rahega jaisa bana hai.',
  'The shapes come from the line art, so where the two drawings differ the colours differ too. Compare the before/after closely.':
    'Shapes line art se aate hain, isliye jahan dono drawings alag hain wahan rang bhi alag honge. Pehle/baad dhyan se milao.',
  'Fill colours →': 'Rang bharo →', 'Filling colours…': 'Rang bhar rahe hain…', 'Could not fill this pair.': 'Ye jodi bhar nahi paaye.',
  'Filled from line art': 'Line art se bhara gaya',
  'Alignment {a} ({v})': 'Alignment {a} ({v})', 'good': 'achha', 'low: check the result closely': 'kam hai: result dhyan se dekho',
  'very low: the two images may not be the same design': 'bahut kam: shayad dono alag design hain',
  '{n} areas where the reference has several colours (often a gap in a line, so a colour leaks).':
    '{n} hisson me reference ke kai rang mile (aksar line me gap hota hai, to rang beh jaata hai).',
  'See them in red': 'Laal me dekho',
  '{n} tiny colours (a few hundred pixels) joined the nearest ink.': '{n} bahut chhote rang (kuch sau pixel) paas wali ink me mila diye.',
  'Outline colour {c} · {w} × {h} px at 300 DPI': 'Outline ka rang {c} · {w} × {h} px, 300 DPI',
  '← Change the files or settings': '← Files ya settings badlo',
  'Filled from the line art: {n} inks, alignment {a}. Check the result, then separate.':
    'Line art se bhara: {n} inks, alignment {a}. Result dekho, phir separate karo.',
  'Colours: choose between 2 and 20.': 'Rang: 2 se 20 ke beech chuno.',
  'Size: choose between 256 and 12000 px.': 'Size: 256 se 12000 px ke beech chuno.',
  'Outline colour: "auto" or a code like #1A1A1A.': 'Outline ka rang: "auto" ya #1A1A1A jaisa code.',
  'The line art is not a valid image.': 'Line art sahi image nahi hai.',
  'The reference is not a valid image.': 'Reference sahi image nahi hai.',
  'The two images are not the same shape (width to height). Use the same crop for both.':
    'Dono images ka aakaar (chaudai/lambai) alag hai. Dono ka crop same rakho.',
  'The line art and the reference do not line up (crop, shift, rotation or a different design). Tick "Fill even if the two images do not line up well" to fill anyway.':
    'Line art aur reference mil nahi rahe (crop, khisakna, ghoomna ya alag design). Phir bhi bharna ho to "Dono images theek se na bhi milein to bhi bharo" tick karo.',
  'Continue to Reduce →': 'Aage: rang kam karo →', 'Replace': 'Doosri file',
  'Forget it and start a new design': 'Chhodo, naya design shuru karo',
  'Your design file — PNG, JPG, TIFF or a layered PSD.': 'Aapki design file — PNG, JPG, TIFF ya layered PSD.',
  'Down to the inks you will print. LoomLab suggests how many.': 'Utne rang jitne chhapne hain. Kitne — LoomLab batata hai.',
  'One screen per ink. Pick the cloth colour, change any ink.': 'Har ink ki ek screen. Kapde ka rang chuno, koi bhi ink badlo.',
  'Films at print size, proof, job sheet — and a quote.': 'Print size ki films, proof, job sheet — aur quote.',

  // Reduce
  'Upload a design first.': 'Pehle design daalo.',
  'Reduce colors': 'Rang kam karo', 'Print inks': 'Kitni inks', 'Texture cleanup': 'Daane (grain) saaf karna',
  'Off — keeps every outline and dot': 'Band — har line aur bindi rahegi',
  'Light — grainy scans': 'Halka — daanedaar scan',
  'Medium — heavy grain, fabric weave': 'Madhyam — zyada daane, kapde ki bunai',
  'Strong — very noisy': 'Tez — bahut kharab file',
  'Reduce design': 'Rang kam karo', 'Re-reduce': 'Dobara karo', 'Reducing…': 'Rang kam ho rahe hain…',
  'Separate into plates →': 'Aage: screens banao →', 'Separating…': 'Screens ban rahi hain…',
  'suggested: {n}': 'sujhaav: {n}', 're-suggest': 'dobara sujhao', '✨ suggest count': '✨ kitni inks sujhao',
  'Recommended balance of match vs number of screens': 'Milaan aur screens ki ginti ka sahi santulan',
  '{n}% match': '{n}% milaan', 'mean ΔE2000 {d} vs original': 'original se ausat ΔE2000 {d}',
  'Merge them': 'Ek kar do', 'pick an ink to merge into…': 'kis ink me milana hai, wo chuno…',
  '↶ Undo': '↶ Wapas', 'merge': 'milao', 'cancel': 'rehne do', '→ here': '→ isme',
  'My inks ({n})': 'Meri inks ({n})', 'Palette · {n} inks': 'Rang · {n} inks',
  'Use my inks for {n} of {m}': '{m} me se {n} ke liye meri inks lagao',
  'The inks your mill already has — match the palette to them': 'Mill me pehle se rakhi inks — rang unse milao',
  'Using it here would print both as one ink': 'Yahan lagane se dono ek hi ink ban jaayengi',
  'Merge this ink into another': 'Is ink ko doosri me milao',
  'Click to recolor this ink': 'Is ink ka rang badalne ke liye click karo', 'Locked': 'Band (lock)',
  'Lock': 'Lock karo', 'Unlock': 'Lock kholo',
  'Click a swatch to recolor · merge combines two inks · 🔓 locks an ink. Re-reduce to start the palette over.':
    'Rang badalne ke liye dabba dabao · "milao" do inks ek karta hai · 🔓 ink ko lock karta hai. Shuru se ke liye "Dobara karo".',
  'small = under': 'chhoti = isse kam',
  'Inks {a} and {b} look almost the same (ΔE {d}). Merging them saves a screen; the match goes from {x}% to {y}%.':
    'Ink {a} aur {b} lagbhag ek jaisi hain (ΔE {d}). Ek karne se ek screen bachegi; milaan {x}% se {y}% hoga.',

  // Separate
  'Every ink hidden — nothing prints.': 'Saari inks chhupi hain — kuch nahi chhapega.',
  'Separation': 'Screens', 'PRINTING': 'CHHAPENGI', 'MATCH': 'MILAAN', 'Cloth colour': 'Kapde ka rang',
  'Pick any cloth colour': 'Koi bhi kapde ka rang chuno',
  'Dark cloth — a white under-base is included so the inks stay bright.': 'Gehra kapda — neeche safed under-base judega taaki rang chamkein.',
  '🎨 Change plate colours': '🎨 Screens ke rang badlo',
  "Change any plate's ink to any colour, with a live preview": 'Kisi bhi screen ki ink ka rang badlo, turant dikhega',
  'Continue to Export →': 'Aage: films nikalo →', '← Back to palette': '← Wapas rangon par',
  "Don't print it": 'Ise mat chhapo', 'Use as cloth colour': 'Isko kapde ka rang banao',
  'Click a plate to hide your fabric colour (it won\'t be printed).': 'Kapde wala rang chhupane ke liye us screen par click karo (wo nahi chhapegi).',
  'Combined result — exactly what your {n} screens will print': 'Poora nateeja — aapki {n} screens bilkul yahi chhapengi',
  'Hidden (fabric) — click to print': 'Chhupi (kapde ka rang) — chhapne ke liye click karo',
  'Printing — click to mark as fabric': 'Chhapegi — kapde ka rang banane ke liye click karo',
  'Ink {n} is the ground ({c}% of the design) and matches your cloth. Leave it unprinted — the cloth shows through — and save the biggest screen.':
    'Ink {n} zameen (ground) hai — design ka {c}% — aur kapde se milti hai. Ise mat chhapo, kapda hi dikhega, aur sabse badi screen bachegi.',
  "Ink {n} is the ground — {c}% of the design. Print on cloth already dyed this colour and that screen, the biggest, isn't needed.":
    'Ink {n} zameen (ground) hai — design ka {c}%. Isi rang me range kapde par chhapo to ye sabse badi screen nahi chahiye.',
  'Ink {n} covers only {c}% — a whole screen for almost nothing. Hide it here, or merge in the palette, to save a screen.':
    'Ink {n} sirf {c}% me hai — lagbhag kuch nahi ke liye poori screen. Yahan chhupao ya rangon me milao, ek screen bachegi.',
  '{n} inks cover under 0.5% each — whole screens for almost nothing. Hide them here, or merge in the palette, to save a screen.':
    '{n} inks 0.5% se bhi kam me hain — kuch nahi ke liye poori screens. Yahan chhupao ya rangon me milao, screens bachengi.',
  'Live preview — your {n} screens in the colours you are picking': 'Turant dikh raha hai — {n} screens aapke chune rangon me',

  // Plate colours
  'Plate colours': 'Screens ke rang', 'Cloth': 'Kapda', 'Cancel': 'Rehne do', 'Done': 'Ho gaya',
  'Pick any colour': 'Koi bhi rang chuno', "Other plates' colours and your shelf inks": 'Doosri screens ke rang aur aapki inks',
  'Only the ink colours change: the films stay exactly as separated. Plates, proof, job sheet and names follow when you press Done.':
    'Sirf ink ka rang badalta hai, films wahi rehti hain. "Ho gaya" dabate hi plates, proof, job sheet aur naam badal jaate hain.',

  // Export
  'Export production package': 'Production package nikalo', 'PLATES': 'SCREENS', 'PRINTS AT': 'CHHAPAI SIZE',
  'Print settings': 'Chhapai ki settings', 'Print width': 'Chhapai ki chaudai', 'own size': 'asli size',
  'White under-base screen (for non-white cloth)': 'Safed under-base screen (rangeen kapde ke liye)',
  'Clean tiny dots': 'Chhoti bindiyan saaf karo', 'Trap between colours': 'Rangon ke beech trap',
  'Download': 'Download', 'Include scalable vector (SVG) outlines': 'Vector (SVG) outlines bhi do',
  '⬇ Download .zip': '⬇ Zip download karo', '⬇ Vector SVG only': '⬇ Sirf vector SVG',
  'Building zip…': 'Zip ban rahi hai…', 'Building zip + vectors…': 'Zip aur vector ban rahe hain…', 'Tracing vectors…': 'Vector ban rahe hain…',
  'Extras': 'Aur', '🎨 Colourways': '🎨 Colourways (rang ke set)',
  'The same screens printed in other inks — no new screens. Save these colours, change the plate colours (Separate → 🎨) and save again: the zip gets a proof and a job sheet for every colourway.':
    'Wahi screens, doosre rang — nayi screen nahi. Ye rang save karo, "Screens banao → 🎨" me rang badlo aur phir save karo: zip me har colourway ka proof aur job sheet aayega.',
  'show': 'dikhao', '+ Save current colours': '+ Abhi ke rang save karo',
  'Put these inks on the plates': 'Ye rang screens par lagao', 'Colourway name': 'Colourway ka naam',
  'Trap is off while there are colourways (it is made for one set of inks).': 'Colourways ke saath trap band rehta hai (trap ek hi rang-set ke liye banta hai).',
  '₹ Quote a print run': '₹ Chhapai ka quote', '₹ Quote': '₹ Quote', 'client (optional)': 'client (zaroori nahi)',
  'meters': 'meter', 'Pricing…': 'Daam nikal rahe hain…',
  '⤢ High-resolution design file': '⤢ Badi (high-resolution) design file', '⤢ Enlarge': '⤢ Bada karo', 'Enlarging…': 'Bada ho raha hai…',
  '← Back to plates': '← Wapas screens par', 'inches': 'inch',
  "A screen's mesh can't hold very small dots: they print as nothing or clog and print as dirt. Cleaning gives each one to the ink around it (still one ink per pixel).":
    'Screen ki jaali bahut chhoti bindi nahi pakad paati: wo ya to chhapti nahi ya gandagi banti hai. Saaf karne par har bindi aas-paas ki ink me mil jaati hai.',
  'Only if your prints show thin lines of cloth between colours: each lighter ink is spread under the darker inks it touches, on the films only. Printed light to dark, the print looks exactly like the proof.':
    'Sirf tab jab rangon ke beech kapde ki patli line dikhe: halki ink gehri ink ke neeche thodi faila di jaati hai (sirf films me). Halke se gehre chhapo to print proof jaisa hi aata hai.',

  'Final proof — {n} inks, print-ready': 'Aakhri proof — {n} inks, chhapne ke liye taiyaar',
  ', drawn at {size} in (zoom in to check edges)': ', {size} inch par bana (kinare dekhne ke liye zoom karo)',
  'Drawing the screens at {w} in…': 'Screens {w} inch par ban rahi hain…', 'Separate a design first.': 'Pehle screens banao.',
  "{n} ink marked as fabric won't be printed.": '{n} ink kapde ka rang hai, nahi chhapegi.',
  "Lighter inks spread {w} under darker ones on the films — print in the job sheet's order.":
    'Halki inks films par gehri ke neeche {w} faili hain — job sheet ke order me chhapo.',
  'quote image ⬇': 'quote ki photo ⬇',

  // messages the steps show at the bottom, with their numbers
  'Upload a design to begin.': 'Shuru karne ke liye design daalo.',
  'Imported {name} ({w}×{h}). Choose an ink count and reduce.': 'Design aa gaya: {name} ({w}×{h}). Kitni inks chahiye chuno aur rang kam karo.',
  'Suggested {n} inks — best balance of match vs number of screens.': '{n} inks sujhayi — milaan aur screens ka sabse achha santulan.',
  'Reduced to {n} inks — {a}% match (ΔE2000 {d}). Fine-tune the palette or continue.': '{n} inks me ho gaya — {a}% milaan (ΔE2000 {d}). Rang theek karo ya aage badho.',
  'Merged into one ink — {n} inks now.': 'Ek ink ban gayi — ab {n} inks.',
  'Ink {i} recoloured to {hex}.': 'Ink {i} ka rang {hex} kar diya.',
  'Undid the {what}.': 'Wapas le liya: {what}.',
  '{n} clean plates ready — one ink per screen, no overlap. This preview is exactly what they print.':
    '{n} saaf screens taiyaar — har screen ek ink, koi overlap nahi. Ye preview bilkul wahi hai jo chhapega.',
  'Change any plate to any colour — the preview follows as you pick. Done keeps it, Cancel puts every colour back.':
    'Kisi bhi screen ka rang badlo — preview saath-saath badlega. "Ho gaya" rakhta hai, "Rehne do" sab wapas karta hai.',
  'Colour changes cancelled — every plate is back to its ink.': 'Rang ke badlav hata diye — har screen apni ink par wapas.',
  'No colours changed.': 'Koi rang nahi badla.',
  'Ink {i} left unprinted — the {hex} cloth shows through. One screen fewer.': 'Ink {i} nahi chhapegi — {hex} kapda dikhega. Ek screen kam.',
  'Picked up your last job where you left off.': 'Pichhla kaam wahin se shuru jahan chhoda tha.',
  'Picked up your last job — some of its later steps had been cleared, so redo them from here.':
    'Pichhla kaam khul gaya — aage ke kuch step mit gaye the, unhe yahan se dobara karo.',
  'Production package downloaded — {rest}': 'Production package download ho gaya — {rest}',
  'Quote {no}: {total} for {m} m ({pm} per meter).': 'Quote {no}: {m} m ke {total} ({pm} prati meter).',
  'Vector SVG downloaded — scalable outlines of every ink.': 'Vector SVG download ho gaya — har ink ki outlines.',
  'Showing colourway {n}.': 'Colourway {n} dikh raha hai.',
  // notes on the steps
  'Chosen for this design: off. It has no grain, so every outline, dot and vein is kept.':
    'Is design ke liye band chuna: isme daane nahi hain, to har line, bindi aur nas bachi rahegi.',
  'Chosen for this design: the source is grainy ({g}), and cleanup keeps the plates from speckling.':
    'Is design ke liye chuna: file daanedaar hai ({g}), safai se screens par chhote daag nahi aayenge.',
  'More cleanup than this design needs: it erases thin outlines, dots and veins.': 'Design ki zaroorat se zyada safai: patli lines, bindiyan aur nasein mit jaayengi.',
  'This source is grainy: with less cleanup the plates will speckle.': 'File daanedaar hai: kam safai se screens par daag aayenge.',
  'Every pixel prints on exactly one plate — no overlap, no gaps. The preview above is these screens stacked back together, so it is your final print.':
    'Har pixel theek ek screen par chhapta hai — na overlap, na khaali jagah. Upar ka preview in screens ko jod kar bana hai, yahi aapka print hai.',
  '{n} dots under {mm} mm on {s} screens: too small for the mesh to hold, they print as nothing or as dirt. Clean them here.':
    '{s} screens par {mm} mm se chhoti {n} bindiyan: jaali inhe nahi pakad paati, ye chhapti nahi ya gandagi banti hain. Yahan saaf karo.',
  '{n} dots under {mm} mm on {s} screens go to the ink around them — the proof shows the result.':
    '{s} screens par {mm} mm se chhoti {n} bindiyan aas-paas ki ink me mil gayi — proof me nateeja dikh raha hai.',
  '{a}% is a loose match — more inks will tighten it. Check the before/after above before you commit to screens.':
    '{a}% milaan dheela hai — zyada inks se behtar hoga. Screens banane se pehle upar pehle/baad dekh lo.',
  '{a}% is a loose match — try {n} inks. Check the before/after above before you commit to screens.':
    '{a}% milaan dheela hai — {n} inks try karo. Screens banane se pehle upar pehle/baad dekh lo.',
  '{a}% is about as close as flat inks get for this design — even {n} inks reach only {c}%. Its fine shading prints as flat areas; check the before/after above.':
    'Is design me flat inks se lagbhag {a}% tak hi milaan hota hai — {n} inks se bhi sirf {c}%. Iski halki shading flat chhapegi; upar pehle/baad dekh lo.',
  "This design has smooth, photographic shading — flat spot colours can't reproduce it. Even at {n} inks the match only reaches about {c}%. It will print as visible bands of flat colour. Tick Print as dots above, or get halftones from a bureau.":
    'Is design me photo jaisi shading hai — flat rang ise nahi bana sakte. {n} inks par bhi milaan sirf lagbhag {c}% hai. Print me rang ki patti (bands) dikhengi. Upar "Dots me chhaapo" chuno, ya bureau se halftone lo.',
  'Print as dots (index separation)': 'Dots me chhaapo (index separation)',
  'Printed as dots — {a}% match seen from a step away.': 'Dots me — thodi door se {a}% milaan.',
  'Back to flat inks — {a}% match.': 'Wapas flat inks — {a}% milaan.', 'Placing dots…': 'Dots lag rahe hain…', 'Back to flat inks…': 'Wapas flat inks…',
  'A trap would spread every dot of an index separation into its neighbours: print dots without a trap.':
    'Trap index separation ke har dot ko pados me faila dega: dots bina trap ke chhaapo.',
  'The dots of an index separation make no useful outlines: use the TIFF films.':
    'Index separation ke dots se kaam ki outline nahi banti: TIFF films use karo.',
  'For photo-like shading: the inks are placed as fine dots that mix into the shading seen from a step away. Still one ink per pixel; needs a fine mesh.':
    'Photo jaisi shading ke liye: inks baareek dots me lagti hain jo thodi door se shading ban jaati hain. Har pixel par phir bhi ek hi ink; baareek jaali chahiye.',
  'seen from a step away (dots)': 'thodi door se dekhne par (dots)',
  'Printed as dots, each {mm} mm: finer than most textile mesh holds. Print it wider, or use a very fine mesh.':
    'Dots me chhapega, har dot {mm} mm: zyadatar kapde ki jaali itna baareek nahi pakadti. Chauda chhaapo, ya bahut baareek jaali lo.',
  'Printed as dots, each {mm} mm: the dot pattern will show. A larger file (Extras → High-resolution design file) gives finer dots.':
    'Dots me chhapega, har dot {mm} mm: dots ka pattern dikhega. Badi file (Extras → High-resolution design file) se dots baareek honge.',
  'Printed as dots, each {mm} mm square: they mix into the shading seen from a step away. Use a fine mesh; no trap or tiny-dot cleaning (the dots are the design).':
    'Dots me chhapega, har dot {mm} mm ka: thodi door se shading ban jaate hain. Baareek jaali lo; trap ya chhoti bindiyon ki safai nahi (dots hi design hain).',
  'At its own size this design prints only {size}. Set a larger print width above: the screens are redrawn at that size with smooth edges.':
    'Apne size par ye design sirf {size} chhapega. Upar badi chaudai daalo: screens us size par saaf kinaron ke saath dobara banengi.',
  "Enlarged {x}×: every screen is redrawn at this size with smooth edges, still one ink per pixel. Detail finer than the file itself — fine texture, tiny dots — can't be added, so it stays as it is in the file.{more}":
    '{x}× bada kiya: har screen is size par saaf kinaron ke saath dobara bani, har pixel ek hi ink. File se zyada baareek detail (texture, chhoti bindiyan) nahi jud sakti, wo file jaisi hi rahegi.{more}',

  "This design has soft, see-through edges (about {n}px of fade). Flat inks can't fade, so those edges will print as a clean hard cut roughly halfway through the fade — a glow or drop shadow will not survive. Flatten the design onto its background first if you want to choose exactly where the edge lands.":
    'Is design ke kinare mulayam, aar-paar dikhne wale hain (lagbhag {n}px ka fade). Flat ink fade nahi kar sakti, isliye ye kinare fade ke beech se ek saaf kataav ki tarah chhapenge — glow ya drop shadow nahi bachega. Kinara theek kahan aaye ye khud chunna ho to design ko pehle uske background par flatten kar lo.',
  'That is too large to render here — this design can go up to {n} in wide. For anything bigger, use the vector SVG, which scales to any size.':
    'Ye yahan banane ke liye bahut bada hai — ye design {n} inch chauda tak ja sakta hai. Isse bade ke liye vector SVG lo, wo kisi bhi size par chalta hai.',
  'That is only {n} pixels of the file per inch, so fine texture will look coarse up close.':
    'File ke sirf {n} pixel prati inch hain, isliye baareek texture paas se mota dikhega.',
  'Reduced to {p}%: lines thinner than {n} px in the file may break up at this size.':
    '{p}% tak chhota kiya: file me {n} px se patli lines is size par toot sakti hain.',
  'These screens come from your PSD exactly as it was separated — LoomLab has not changed them.':
    'Ye screens aapki PSD se bilkul waise hi aayi hain jaise separate ki gayi thi — LoomLab ne inhe nahi badla.',
  'No two screens print on the same spot.': 'Koi do screens ek hi jagah nahi chhaapti.',
  '{p}% of the design is printed by more than one screen (trapping or overprint), kept as in your file. Where screens overlap, the preview shows the later one on top.':
    'Design ka {p}% ek se zyada screen se chhapta hai (trapping ya overprint), file jaisa hi rakha. Jahan screens milti hain, preview me baad wali upar dikhti hai.',
  'Under 0.1': '0.1 se kam',
  'both ways': 'dono taraf', 'left to right': 'baayein se daayein', 'top to bottom': 'upar se neeche',
  'Seamless repeat ({way}): the edges were processed as they meet when the tile repeats, so the reduced design stays seamless — no line at the join.':
    'Seamless repeat ({way}): kinaron ko waise process kiya jaise tile repeat hone par milte hain, isliye design seamless rahega — jod par koi line nahi.',
  'Off': 'Band', 'under {mm} mm': '{mm} mm se chhoti',
  '1 dot under {mm} mm on 1 screen: too small for the mesh to hold, it prints as nothing or as dirt. Clean it here.':
    '1 screen par {mm} mm se chhoti 1 bindi: jaali ise nahi pakad paati, ye chhapti nahi ya gandagi banti hai. Yahan saaf karo.',
  '{n} dots under {mm} mm on 1 screen: too small for the mesh to hold, they print as nothing or as dirt. Clean them here.':
    '1 screen par {mm} mm se chhoti {n} bindiyan: jaali inhe nahi pakad paati, ye chhapti nahi ya gandagi banti hain. Yahan saaf karo.',
  '1 dot under {mm} mm on 1 screen goes to the ink around it — the proof shows the result.':
    '1 screen par {mm} mm se chhoti 1 bindi aas-paas ki ink me mil gayi — proof me nateeja dikh raha hai.',
  '{n} dots under {mm} mm on 1 screen go to the ink around them — the proof shows the result.':
    '1 screen par {mm} mm se chhoti {n} bindiyan aas-paas ki ink me mil gayi — proof me nateeja dikh raha hai.',
  'ink {n} ({c}%)': 'ink {n} ({c}%)',
  'Kept: {list} — unlike any other ink, they would visibly change.': 'Rakhi: {list} — ye kisi aur ink jaisi nahi, hatane par farak dikhega.',
  'Kept: {list} — unlike any other ink, it would visibly change.': 'Rakhi: {list} — ye kisi aur ink jaisi nahi, hatane par farak dikhega.',
  '(match {a}% → {b}%)': '(milaan {a}% → {b}%)',
  '{n} inks cover under {b}% each. Removing them leaves {k} inks{score}: each pixel moves to the closest remaining ink.':
    '{n} inks har ek {b}% se kam jagah leti hain. Inhe hatane se {k} inks bachengi{score}: har pixel sabse paas wali bachi ink me chala jaayega.',
  '1 ink covers under {b}%. Removing it leaves {k} inks{score}: each pixel moves to the closest remaining ink.':
    '1 ink {b}% se kam jagah leti hai. Ise hatane se {k} inks bachengi{score}: har pixel sabse paas wali bachi ink me chala jaayega.',
  'Remove {n} small inks': '{n} chhoti inks hatao', 'Remove 1 small ink': '1 chhoti ink hatao',
  '{size} by {how}, but only a {m}% match with the original: the enlargement changed the design. Check it closely, or use Lanczos.':
    '{size}, {how} se — lekin original se sirf {m}% milaan: bada karne me design badal gaya. Dhyan se dekho, ya Lanczos lo.',
  "{size} by {how} · {m}% match with the original · from only {p} px per inch: edges are smooth, but fine detail can't be added.":
    '{size}, {how} se · original se {m}% milaan · sirf {p} px prati inch se: kinare saaf hain, par baareek detail nahi jud sakti.',
  '{size} by {how} · {m}% match with the original.': '{size}, {how} se · original se {m}% milaan.',
  'Real-ESRGAN is not installed (tools/realesrgan/); used Lanczos.': 'Real-ESRGAN install nahi hai (tools/realesrgan/); Lanczos lagaya.',
  'Real-ESRGAN did not run ({e}); used Lanczos.': 'Real-ESRGAN nahi chala ({e}); Lanczos lagaya.',

  // the engine's own messages (errors it answers with)
  "Can't reach the LoomLab engine. Check the window called \"LoomLab Backend\" is still open (if you closed it, double-click run-windows.bat again), then retry. Your work so far is kept.":
    'LoomLab engine se baat nahi ho pa rahi. Dekho "LoomLab Backend" wali window khuli hai (band kar di ho to run-windows.bat par phir double-click karo), phir dobara try karo. Ab tak ka kaam bacha hua hai.',
  'This file is too large to import (the limit is 80 MB).': 'Ye file bahut badi hai (seema 80 MB hai).',
  'The engine hit a problem with this design (error {n}). Try again; if it keeps happening, try fewer inks or a smaller file.':
    'Is design par engine me dikkat aayi (error {n}). Dobara try karo; baar baar ho to kam inks ya chhoti file lo.',
  'This image is no longer available. Please import it again.': 'Ye image ab nahi rahi. Design dobara daalo.',
  'This job is no longer available. Run it again.': 'Ye job ab nahi raha. Dobara chalao.',
  'No such design in the library.': 'Library me aisa design nahi hai.',
  'This design has no production package kept.': 'Is design ki production zip nahi rakhi gayi.',
  'This design has no proof kept.': 'Is design ka proof nahi rakha gaya.',
  'This library design is damaged. Approve the job again, or restore a backup.': 'Library ka ye design kharab hai. Job dobara approve karo, ya backup wapas lagao.',
  'No ink screens selected.': 'Koi ink screen nahi chuni.',
  'Nothing to export — separate the design into inks first.': 'Export ke liye kuch nahi — pehle design ko inks me alag karo.',
  'Image is larger than the 80 MB import limit.': 'Image 80 MB ki seema se badi hai.',
  'Please choose a PNG, JPG, WEBP, TIFF, or PSD image.': 'PNG, JPG, WEBP, TIFF ya PSD image chuno.',
  'At least one ink has to stay.': 'Kam se kam ek ink rehni chahiye.',
  'The selected file is not a valid image.': 'Chuni hui file sahi image nahi hai.',
  'This PSD is already separated into screens; export it directly.': 'Ye PSD pehle se screens me alag hai; seedha export karo.',
  'This design is empty — every pixel is transparent. Export it again with the artwork visible.':
    'Ye design khaali hai — har pixel transparent hai. Artwork dikhte hue dobara export karo.',
  'This PSD has no visible layers to import.': 'Is PSD me daalne layak koi dikhti layer nahi hai.',
  'Could not read this PSD file: {e}': 'Ye PSD file padh nahi paaye: {e}',
  'Multichannel PSDs with {n}-bit channels are not supported yet (only 8-bit).': '{n}-bit channel wali multichannel PSD abhi nahi chalti (sirf 8-bit).',
  'This is not a zip file. Choose the loomlab-backup-….zip that Backup downloaded.': 'Ye zip file nahi hai. Backup se download hui loomlab-backup-….zip chuno.',
  'This zip is not a LoomLab backup (it has no manifest.json).': 'Ye zip LoomLab ka backup nahi hai (isme manifest.json nahi hai).',
  'This backup was made by a different LoomLab version and cannot be read here.': 'Ye backup LoomLab ke doosre version ka hai, yahan nahi padh sakte.',
  'This backup is larger than LoomLab restores.': 'Ye backup LoomLab ki seema se bada hai.',
  'The ink list in the backup is damaged.': 'Backup me inks ki list kharab hai.',
  'Library entry {id} in the backup is damaged.': 'Backup me library ka design {id} kharab hai.',
  'Library entry {id} in the backup has no report.': 'Backup me library ke design {id} ki report nahi hai.',
  'A trap wider than {n} px is not supported.': '{n} px se chauda trap nahi chalta.',
  'Two colourways are called {name}.': 'Do colourways ka naam {name} hai.',
  'Colourway {name} must give one ink for each of the {n} screens.': 'Colourway {name} me {n} screens me se har ek ki ink chahiye.',
  'Send one target colour for every palette colour.': 'Har palette rang ke liye ek naya rang bhejo.',

  // Jobs and library
  'Needs review': 'Dekhna hai', 'Open': 'Chalu', 'Finished': 'Poore', 'All': 'Sab', '📚 Library': '📚 Library',
  '↻ Refresh': '↻ Taaza karo', '⬇ Package': '⬇ Zip', '✓ Checked': '✓ Dekh liya', '✕ Stop': '✕ Roko', 'Approved': 'Pakka',
  'Nothing waiting: every held job has been dealt with.': 'Kuch baaki nahi: har ruka kaam dekh liya gaya.',
  'No jobs here yet.': 'Abhi yahan koi kaam nahi.',
  'Approved designs, kept for good: films and repeat-order quotes': 'Pakke designs, hamesha ke liye: films aur repeat order ka quote',
  'Find a design or client…': 'Design ya client dhoondho…', '₹ Repeat quote': '₹ Repeat quote', '⬇ Films': '⬇ Films',
  'Designs': 'Designs', 'Needed nobody': 'Bina aadmi ke', 'Quoted': 'Quote kiya', 'Time saved': 'Time bacha',
  'Client rates': 'Client ke rate', "a regular client's own prices — blank = the rate card's; the name as on the job or quote":
    'pakke client ke apne daam — khaali = rate card wala; naam wahi jo job ya quote par hai',
  'client name': 'client ka naam', '+ client': '+ client', 'Every client row needs the client name.': 'Har client wali line me client ka naam chahiye.',
  "{name}: fill in at least one of their own rates (blank = the rate card's).": '{name}: kam se kam ek apna rate bharo (khaali = rate card wala).',
  '{name} is listed twice.': '{name} do baar likha hai.', '{name}: {field} must be {what}.': '{name}: {field} — {what}.',
  '{n} at most': 'zyada se zyada {n}', 'Every ink price needs the ink name.': 'Har ink ke daam ke saath ink ka naam chahiye.',
  '{name}: the price must be a number, 0 or more.': '{name}: daam number hona chahiye, 0 ya zyada.',
  "{name}'s own rates": '{name} ke apne rate',
  'Repeat orders': 'Repeat order',
  'Help': 'Madad', 'Check the engine': 'Engine jaancho',
  'a report for whoever helps you: versions, space, settings and the last errors — no designs, prices or clients':
    'madad karne wale ke liye report: version, jagah, settings aur aakhri errors — koi design, daam ya client nahi',
  'LoomLab {c} · running {m} min · {g} GB free · cache {mb} MB · {d} library designs':
    'LoomLab {c} · {m} min se chalu · {g} GB khaali · cache {mb} MB · library me {d} design',
  'Under 2 GB free on this disk: big designs and packages may fail. Free some space.':
    'Disk par 2 GB se kam jagah: bade design aur zip fail ho sakte hain. Thodi jagah khaali karo.',
  '{n} errors since the engine started (newest first):': 'Engine chalu hone ke baad {n} errors (naye pehle):',
  '⊞ See the repeat': '⊞ Repeat dekho',
  '⊞ Straight repeat': '⊞ Seedha repeat',
  '⊞ Half-drop repeat': '⊞ Half-drop repeat',
  'See the design as it runs on the cloth: straight, then half-drop (every other column dropped by half). Only a view — the films are the design once.':
    'Design kapde par kaise chalega dekho: pehle seedha, phir half-drop (har doosri line aadha design neeche). Sirf dekhne ke liye — films me design ek hi baar hai.',
  'The repeat could not be drawn here.': 'Repeat yahan nahi ban paaya.',
  'Laying out the repeat…': 'Repeat bichha rahe hain…',
  'half-drop repeat': 'half-drop repeat',
  'straight repeat': 'seedha repeat',
  'No errors since the engine started.': 'Engine chalu hone ke baad koi error nahi.',
  'Rate card': 'Rate card',
  'Auto limits': 'Auto ki limits',
  'Not activated': 'Activate nahi hua',
  '📋 Copy report': '📋 Report copy karo', '⬇ Download report': '⬇ Report download karo',
  'Copied — paste it into WhatsApp or an email.': 'Copy ho gaya — WhatsApp ya email me paste karo.',
  'Could not copy here: use Download instead.': 'Yahan copy nahi hua: Download use karo.', 'no design': 'koi design nahi', '%': '%',
  'just now': 'abhi', '{n} min ago': '{n} min pehle', '{n} h ago': '{n} ghante pehle', '1 day ago': '1 din pehle', '{n} days ago': '{n} din pehle',
  '👥 Clients': '👥 Clients', "Each client's designs, approvals and business": 'Har client ke design, pakke order aur kamaai',
  'Find a client…': 'Client dhoondo…', '30 days': '30 din', '3 months': '3 mahine', '1 year': '1 saal',
  'No client orders in this period yet. Jobs with a client name (the Telegram bot fills it in) show here.':
    'Is samay me kisi client ka order nahi. Client ke naam wale jobs (Telegram bot naam bhar deta hai) yahan dikhte hain.',
  'Client': 'Client', 'Waiting': 'Baaki', 'Approved meters': 'Pakke meter', 'Business': 'Kamaai', 'Last': 'Aakhri',
  'Has its own rates (Settings)': 'Iske apne rate hain (Settings)', 'own rates': 'apne rate',
  'Quoted but not approved yet': 'Quote diya, abhi pakka nahi', '{m} quoted': '{m} quote me',
  'Business = approved runs + repeat orders, as quoted. Each design counts once, by its latest run.':
    'Kamaai = pakke order + repeat order, quote ke hisaab se. Har design ek hi baar gina jaata hai, uske aakhri run se.', 'colourway': 'naye rang', 'The screens of job {id}, printed in other inks': 'Job {id} ki screens, doosre rangon me', 'last {n} days': 'pichhle {n} din', '{n} runs': '{n} baar chala',
  '{a} auto OK · {b} checked by a person': '{a} apne aap theek · {b} aadmi ne dekhe', '{n} stopped': '{n} roke',
  '≈ {money} · estimate: {a} min by hand, {b} min to check (Settings)': '≈ {money} · andaaza: haath se {a} min, jaanch {b} min (Settings)',

  'Showing the newest {n} of {m} jobs.': 'Naye {n} kaam dikh rahe hain, kul {m}.',
  'needs review': 'dekhna hai', 'auto OK': 'auto OK',
  'New': 'Naya', 'Checked': 'Dekh liya', 'With client': 'Client ke paas', 'Stopped': 'Roka', 'Changed': 'Badla',
  '{n} inks · {a}% match · {w} × {h} in': '{n} inks · {a}% milaan · {w} × {h} inch',
  '{money} for {m} m': '{m} m ke {money}',
  'photo-like shading': 'photo jaisi shading', 'low match': 'kam milaan', 'soft edges': 'dhundhle kinare',
  'tiny dots': 'chhoti bindiyan', 'near-duplicate inks': 'ek jaisi do inks', 'many screens': 'bahut screens',
  'file too small for the size': 'file is size ke liye chhoti', 'grainy file': 'daanedaar file',
  'seamless repeat': 'seamless repeat', 'inks under 2%': '2% se kam wali inks',
  '{n} approved designs, kept for repeat orders': '{n} pakke designs, repeat order ke liye rakhe hain',
  'Nothing matches.': 'Kuch nahi mila.',
  'Designs land here when a job is marked Approved (on this page or by the client on Telegram).':
    'Kaam "Pakka" hote hi design yahan aa jaata hai (is page se ya client Telegram par approve kare).',
  'no client': 'client nahi', 'approved {d}': 'pakka {d}', '{n} screens · {w} × {h} in': '{n} screens · {w} × {h} inch',
  'white under-base': 'safed under-base', 'last run {m} m': 'pichhli baar {m} m', 'no new screens': 'nayi screen nahi',

  // Settings
  'Settings': 'Settings', 'Loading…': 'Khul raha hai…', 'Quote prices': 'Quote ke daam', 'rate card': 'rate card',
  'Mill name': 'Mill ka naam', 'on the quote': 'quote par', 'Currency': 'Currency',
  'Ink prices by name': 'Ink ke naam se daam', 'per kg — the name as on the plate, or its hex': 'prati kg — screen par jo naam hai, ya hex',
  '+ ink price': '+ ink ka daam', 'Save prices': 'Daam save karo', 'Saving…': 'Save ho raha hai…',
  'Auto mode': 'Auto mode', 'when a job waits for a person': 'kaam kab aadmi ke liye ruke',
  'Stop the job for': 'Kaam kin cheezon par ruke',
  'ticked: it waits for review · unticked: only reported': 'tick: aapke dekhne tak rukega · bina tick: sirf bataya jaayega',
  'Save limits': 'Seemayein save karo',
  "Restore {file}? The library, rate card, limits and inks on this PC are replaced by the backup's; the job log is added to.":
    '{file} wapas lagayein? Is PC ki library, rate card, seemayein aur inks backup wali se badal jaayengi; kaam ka hisaab jud jaayega.',
  'Restored the backup from {d}: {l} library designs, {i} shelf inks, {n} job-log lines added, prices and limits.':
    '{d} ka backup wapas lag gaya: {l} library designs, {i} inks, {n} hisaab ki lines judi, daam aur seemayein.',
  '{n} repeat orders': '{n} repeat order', '1 repeat order': '1 repeat order','last {m} m on {d}': 'pichhla {m} m, {d}',
  'keep {n} changes': '{n} badlav rakho',
  'Fix the boxes marked in red.': 'Laal dabbe theek karo.',
  'Saved — the next quote uses these prices.': 'Save ho gaya — agla quote inhi daamon se banega.',
  'Saved — the next auto job (and the Telegram bot) uses these limits.': 'Save ho gaya — agla auto kaam (aur Telegram bot) inhi seemaon se chalega.',
  'ink name, e.g. Rani Pink 12': 'ink ka naam, jaise Rani Pink 12', 'per kg': 'prati kg', 'Remove': 'Hatao',
  // Settings fields (lib/settings.ts) and the checks' messages
  'One screen': 'Ek screen', 'per screen': 'prati screen', 'making one screen for a design': 'ek design ki ek screen banana',
  'Ink': 'Ink', 'any ink not priced by name below': 'jin inks ka naam se daam neeche nahi diya',
  'White under-base ink': 'Safed under-base ink', 'Ink laid down': 'Kitni ink lagti hai', 'g per m²': 'gram prati m²',
  'at full cover': 'poora dhakne par', 'Cloth width': 'Kapde ki chaudai', 'inch': 'inch', 'per meter': 'prati meter',
  "0 = the client's own cloth": '0 = client ka apna kapda', 'Printing': 'Chhapai', 'per meter per screen': 'prati meter prati screen',
  'Setup': 'Setup', 'per job': 'prati kaam', 'table setup, washing, a sample': 'table lagana, dhulai, sample',
  'Wastage': 'Barbaadi', 'Your margin': 'Aapka munafa', 'GST': 'GST', 'Quote valid for': 'Quote kitne din chalega', 'days': 'din',
  'A design by hand': 'Ek design haath se', 'minutes': 'minute', 'for the time-saved estimate on Jobs': 'Kaam page par time-bachat ke andaze ke liye',
  'Checking a held design': 'Ruka design check karna', 'for the time-saved estimate': 'time-bachat ke andaze ke liye',
  'Operator cost': 'Operator ka kharcha', 'per hour': 'prati ghanta', 'for the money-saved estimate': 'paisa-bachat ke andaze ke liye',
  'Lowest match': 'Kam se kam milaan', 'below it a job waits for a person': 'isse kam par kaam aadmi ke liye rukega',
  'Photo-like below': 'Isse kam = photo jaisa', 'best match any ink count reaches': 'kisi bhi ink ginti ka sabse achha milaan',
  'Most screens': 'Zyada se zyada screens', 'screens': 'screens', 'Tiny dot': 'Chhoti bindi', 'mm': 'mm',
  'smaller than this will not hold on the mesh': 'isse chhoti jaali par nahi tikegi',
  'Tiny dots allowed': 'Kitni chhoti bindiyan chalengi', '% of the print': 'print ka %',
  'Clean dots under': 'Isse chhoti bindiyan saaf karo', '0 = leave them': '0 = rehne do',
  'Lowest file resolution': 'File ka kam se kam resolution', 'pixels per inch': 'pixel prati inch',
  'a number': 'number chahiye', '0 or more': '0 ya zyada', 'a whole number': 'poora number',
  // auto mode's warnings (the Settings ticks)
  'photo-like shading (flat inks print it as bands)': 'photo jaisi shading (flat ink me patte dikhenge)',
  'match with the original too low': 'original se milaan bahut kam', 'soft, feathered edges': 'dhundhle, faile kinare',
  'dots too small for the mesh': 'jaali ke liye bahut chhoti bindiyan', 'two inks almost the same': 'do inks lagbhag ek jaisi',
  'more screens than the limit': 'seema se zyada screens', 'file too small for the print size': 'print size ke liye file chhoti',
  'grainy file, texture cleanup applied': 'daanedaar file, safai lagayi', 'inks under 2% could be dropped': '2% se kam wali inks hata sakte hain', 'Backup': 'Backup',
  'the design library with its films, the job log, your inks, prices and limits': 'Library (films ke saath), kaam ka hisaab, inks, daam aur seemayein',
  '⬇ Download backup': '⬇ Backup download karo', '⤒ Restore a backup': '⤒ Backup wapas lagao', 'Restoring…': 'Wapas lag raha hai…',
  'Keep a copy somewhere else (a pen drive, Google Drive): a dead disk or a new PC then costs nothing. Restore puts it back on any LoomLab.':
    'Ek copy kahin aur rakho (pen drive, Google Drive): PC kharab ho ya naya aaye, kuch nahi khoyega. "Wapas lagao" kisi bhi LoomLab par sab laga deta hai.',
};

// Messages built elsewhere with their numbers already in ("Reduced to 7 inks —
// 88% match…") are found by their template: every key with {values} also
// matches any text of that shape, and its values go into the Hinglish.
const PATTERNS: [RegExp, string, string[]][] = Object.entries(HI)
  .filter(([en]) => /\{\w+\}/.test(en))
  .map(([en, hi]) => {
    const names: string[] = [];
    const re = en.split(/(\{\w+\})/).map(part => {
      const m = part.match(/^\{(\w+)\}$/);
      if (m) { names.push(m[1]); return '(.*?)'; }
      return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('');
    return [new RegExp(`^${re}$`, 's'), hi, names];
  });

export function translate(lang: Lang, text: string, vars?: Record<string, string | number>): string {
  let out = text;
  if (lang === 'hi') {
    if (text in HI) out = HI[text];
    else if (!vars) {
      for (const [re, hi, names] of PATTERNS) {
        const m = text.match(re);
        if (m) { out = names.reduce((o, n, i) => o.split(`{${n}}`).join(m[i + 1]), hi); break; }
      }
    }
  }
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

export const LangContext = createContext<Lang>('en');
/** Switches the language (the header's EN/हिं). */
export const SetLangContext = createContext<(lang: Lang) => void>(() => {});

/** A translator: t from useT(), or `english` (the values filled in, nothing
 *  translated) — what the note builders in lib/ take, so they stay pure. */
export type Tr = (text: string, vars?: Record<string, string | number>) => string;
export const english: Tr = (text, vars) => translate('en', text, vars);

/** t('Upload') — the text in the chosen language. */
export function useT(): Tr {
  const lang = useContext(LangContext);
  return (text: string, vars?: Record<string, string | number>) => translate(lang, text, vars);
}

/** The chosen language, for text that comes already translated (an auto
 *  job's warnings carry their own Hinglish, `hi`). */
export function useLang(): Lang {
  return useContext(LangContext);
}

export function savedLang(): Lang {
  try { return localStorage.getItem(LANG_KEY) === 'hi' ? 'hi' : 'en'; } catch { return 'en'; }
}
