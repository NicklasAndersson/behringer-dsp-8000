# Behringer Ultra-Curve DSP8000 – vad vi vet om enheten

Reverse-engineerad MIDI-styrning av en **Behringer Ultra-Curve DSP8000**
(originalmodellen från 1996, *inte* DSP8024 PRO), plus skripten som mäter
rummet med Room EQ Wizard och skriver korrigeringen till enheten.

1996-manualen säger att DSP8000 inte klarar System Exclusive och att MIDI OUT
är död. Det gäller inte enheter med nyare OS. Vår enhet dumpar hela sitt minne
på begäran, tar emot en patchad dump tillbaka och låter sig styras band för
band via Control Change. Grafisk EQ, de parametriska filtren och dumpens
layout är avkodade och verifierade mot hårdvara. Det här repot dokumenterar
vad som fungerar, hur, och vad som fortfarande är okänt.

| | |
|---|---|
| **[Vad som fungerar](#vad-som-fungerar)** | CC-skalan, SysEx-dumpen, dump-layouten – kort version |
| **[Vad vi inte vet](#vad-vi-inte-vet)** | öppna frågor och kvarvarande arbete |
| **[Checklista](#checklista-verifiera-på-hårdvara)** | allt som bara enheten kan svara på, inklusive Gemini-rapportens påståenden |
| **[docs/midi.md](docs/midi.md)** | full MIDI-referens: inställningar, byte för byte, testlogg, källor |
| **[docs/verktyg.md](docs/verktyg.md)** | skripten, kontrollpanelen, hur man kör dem |
| **[docs/rew.md](docs/rew.md)** | REW-flödet: mätning, målkurva, Match Target, API |

**In English:** This repository documents the MIDI implementation of a
Behringer Ultra-Curve **DSP8000** (the original 1996 model, not the DSP8024
PRO), reverse-engineered against real hardware. Control Change writes the
31-band graphic EQ (`CC = 64 + dB×4`); a SysEx request returns the complete
12112-byte memory dump; the graphic and parametric EQ blocks inside that dump
are decoded, so a patched dump can be pushed back to write both at once. The
byte-level reference, the test log and what remains unknown are in
[docs/midi.md](docs/midi.md). The repo also contains scripts that drive Room EQ
Wizard's HTTP API to produce a room correction and push it to the unit
([docs/rew.md](docs/rew.md), [docs/verktyg.md](docs/verktyg.md)). Everything
except this summary is in Swedish.

**Auf Deutsch:** Dieses Repository dokumentiert die MIDI-Implementierung eines
Behringer Ultra-Curve **DSP8000** (Originalmodell von 1996, nicht der DSP8024
PRO), per Reverse Engineering an echter Hardware ermittelt. Control Change
schreibt den 31-Band-Grafik-EQ (`CC = 64 + dB×4`); eine SysEx-Abfrage liefert
den kompletten Speicher-Dump von 12112 Byte; die Blöcke für grafischen und
parametrischen EQ darin sind entschlüsselt, ein gepatchter Dump lässt sich also
zurückschreiben und setzt beide auf einmal. Die Byte-Referenz, das Testprotokoll
und die offenen Fragen stehen in [docs/midi.md](docs/midi.md). Dazu kommen
Skripte, die über die HTTP-API von Room EQ Wizard eine Raumkorrektur erzeugen
und an das Gerät schicken ([docs/rew.md](docs/rew.md),
[docs/verktyg.md](docs/verktyg.md)). Alles außer dieser Zusammenfassung ist auf
Schwedisch.

---

## Enheten i korthet

**Behringer Ultra-Curve DSP8000**, originalmodellen. Skillnad mot PRO/DSP8024:
20-bit AD/DA (ej 24-bit), en annan SysEx-uppsättning än DSP8024:s
(EQ-Design:s, [docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03)),
delay och AES/EBU som tillval.

- 31-bands grafisk EQ per kanal (ISO-tersband, 20 Hz–20 kHz), ±16 dB i 0,5 dB-steg
- 3 fullparametriska filter per kanal (+16…−48 dB) – **delas med Feedback Destroyer**
- Real Time Analyzer (RTA), 31 tersband, med Auto-Q
- Digital delay (tillval, "DELAY 8000"-kort), AES/EBU in/ut (tillval, "AES 8000")
- 100 minnesplatser för program

**De 31 ISO-tersbandsfrekvenserna:**

```
20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400,
500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000,
6300, 8000, 10000, 12500, 16000, 20000  (Hz)
```

**IN/OUT-knappen** (viktig när man mäter):

| LED | Betyder |
|---|---|
| Lyser grönt | EQ aktiv, signalen bearbetas |
| Släckt | Bypass, signalen går orört igenom |
| Blinkar rött | Overflow/clipping internt i DSP:n – sänk ingångsnivån |

Vid REW-mätning: baseline med LED **släckt**, korrigerad mätning med LED **tänd**.

**OS-version spelar roll.** 1996-OS:et har fast controller-offset (CC 64–127),
död MIDI OUT och ingen SysEx. Nyare OS (testenheten) har justerbar offset
0–64, skickar på MIDI OUT och klarar SND/RCV MEMORY DUMP. Versionen visas kort
i displayen vid påslag; firmware byttes via EPROM. Jämförelsetabell i
[docs/midi.md bilaga B](docs/midi.md#bilaga-b-os-versioner-modellskillnader-pc-mjukvara).

---

## Vad som fungerar

Verifierat mot enheten 2026-08-31, 2026-09-02 och 2026-09-03 med en PreSonus
AudioBox USB som MIDI-interface. Full referens och testlogg: [docs/midi.md](docs/midi.md).

| Vad | Riktning | Status |
|---|---|---|
| Program Change 0–99 → byt program | dator → DSP | **fungerar** |
| CC → grafisk EQ (31+31 band + 2 master) | dator → DSP | **fungerar**, `CC = 64 + dB×4` |
| SysEx-förfrågan → hela minnesdumpen | dator → DSP → dator | **fungerar**, 12112 byte efter ~5 s |
| SND MEMORY DUMP (knapp) → dumpen | DSP → dator | **fungerar** |
| Fader-rörelse → läsbar GEQ-status | DSP → dator | **fungerar** (`33 09`-frame) |
| Avkoda GEQ + PEQ ur dumpen | – | **avkodat och verifierat** |
| RCV MEMORY DUMP (skriva en dump tillbaka) | dator → DSP | **fungerar med knapptryck** på enheten |
| Skriva GEQ **och** PEQ via patchad dump | dator → DSP | GEQ **verifierat**; PEQ-**värdena** i dumpen stämmer (SysEx-återläsning bit-exakt), men PEQ-**displayen** visar fel frekvens för post 2–6 (se "Vad vi inte vet") |
| EQ-Design:s protokoll: 12 kommandon + hela minnesbilden | – | **avkodat ur EQDESIGN.EXE** 2026-09-03; bilden verifierad mot våra dumpar, kommandona (`21` GEQ, `22` PEQ, `43`/`44` …) otestade |
| CC ut vid fader-rörelse | DSP → dator | sett i capture, ej systematiskt testat |
| DSP8024:s granulära SysEx (ADRStudio) | – | **dött** på DSP8000 |

Returvägen kräver **båda** MIDI-kablarna (interface OUT → DSP IN *och* DSP OUT
→ interface IN). Enheten ekar inte mottagna CC.

### MIDI SETUP på enheten

Håll **SETUP** > 2 s → sida 2. Testenheten: MIDI ON · CHANNEL 1 · OMNI ON ·
CNTL **RCV 0** / SND 1 · PROG RCV+SND ON · EXCL RCV+SND ON.

`CNTL` är inte ON/OFF utan ett **tal** – Controller Offset 0–64, alltså första
CC-numret. Sätt offset 64 och du får 1996-manualens fasta mappning.

### Skriva grafisk EQ: Control Change

```
Bn cc vv        n = kanal 0–F, cc = CNTL RCV-offset + nummer nedan, vv = 0–127
```

| Nummer (offset 0) | Styr |
|---|---|
| 0–30 | vänster 31 band: 20 Hz = 0, 1 kHz = 17, 20 kHz = 30 |
| 31 | vänster master |
| 32–62 | höger 31 band |
| 63 | höger master |

**Värdeskalan är verifierad:** `CC = 64 + dB × 4` → 64 = 0 dB, 96 = +8 dB,
0 = −16 dB, 127 = +15,75 dB. Nominellt 0,25 dB/steg, men GEQ:n har 0,5 dB
upplösning så enheten rundar.

Enheten **tappar CC** om 62 stycken kommer i en klump – pausa ~20 ms mellan
meddelanden och läs tillbaka efteråt.

### Läsa allt: SysEx-dump

```
Förfrågan:  F0 00 20 32 00 01 70 <xx> F7
Svar:       F0 00 20 32 00 01 4F <12104 databyte> F7
```

`00 20 32` = Behringers manufacturer-ID, `00` = device-ID = MIDI-kanal − 1
(enligt EQ-Design), `01` = modell DSP8000 (`0E`, som är DSP8024, ignoreras
helt). Oavsett `xx` svarar enheten med **hela minnet**; EQ-Design begär samma
sak med `40` och har därtill granulära kommandon vi inte provat
([docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03)).
Enheten måste stå på EQ-huvudskärmen. Förfrågan ändrar ingenting.

Databytena är alla < 128 och **7-bitars-packade** MSB-först: 8 databyte =
7 minnesbyte, en minnesbild på 10591 byte. Det finns ingen header efter `4F`
– det vi kallade sub-kod är statusflaggor i bildens första byte.

### Avkodad dump-layout

| Minnesbyte | Innehåll |
|---|---|
| 0–9 | huvud: statusflaggor, crossfade (s), shelving (×3 dB/okt), limiter, gate, aktuellt program |
| 10–113 | **program 0 = arbetsbufferten**: delay L/R (2+2), 6 PEQ-poster à 4 byte (L1 R1 L2 R2 L3 R3), namn 12 tecken, GEQ L 32, GEQ R 32 |
| 114–189 | 76 byte som EQ-Design hoppar över – okänt |
| 190– | program 1–100 à 104 byte, samma layout som arbetsbufferten |

Kartlagt ur EQ-Design 2026-09-03 och verifierat mot våra dumpar: programnamnen
läses i klartext (`BAS  ROCK`, `MOVIE`, `AUT O Q` …) och huvudets
programnummer stämmer med displayen. Fullständig tabell:
[docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03).

GEQ-värde: **0,5 dB per enhet**, tecknad byte, `dB = värde / 2` – enhetens
egna steg, halva CC-skalans upplösning. Master (index 31) i samma block och
skala. `apply` skriver inte master: en rumskorrigering ska inte flytta utnivån.

PEQ-post, 4 byte: **ISO-bandindex**, **finsteg** (tjugondelar av avståndet
till nästa ISO-frekvens, linjärt: `0x0527` = 63 + 17·39/20 = 96,150 Hz, exakt
vad displayen visar), **bandbredd** (`(raw+1)/60` oktav), **gain** (tecknad
byte, 0,5 dB). Posten helt noll = inga värden satta. FB-D-läget (ON/OFF/SGL)
ligger inte i dumpen. Fram till 2026-09-03 låg vår post tre bitar snett med
10-bitars gain – halva dB blev rätt ändå, åttondelar skrev över nästa posts
bandindex och programnamnets första tecken.

### Skriva allt: RCV MEMORY DUMP

Eftersom GEQ- och PEQ-blocken är avkodade går det att ta en färsk dump, patcha
in nya värden och pusha tillbaka den – enda kända vägen att skriva de
parametriska filtren.

- **Kräver ett tryck på RCV MEMORY DUMP (+)** precis före sändningen. Utan det
  landar ingenting, trots EXCL RCV ON (verifierat båda vägarna 2026-09-03).
- Förfrågnings-formatet (`4F 0A`) duger som bas – det var formatet i det
  lyckade testet.
- Enheten är långsam att svara direkt efter en inkommande dump; vänta ~6 s.
- **Ta basdumpen som en egen, ren avläsning** medan enheten står på
  EQ-huvudskärmen. En bas grabbad mitt i ett lägesbyte innehåller skeva värden
  utanför GEQ/PEQ, som då pushas tillbaka.
- **Risk:** en pushad dump skriver över arbetsbufferten och kan röra de 100
  programmen. Ta backup först, och använd bara dumpar från *samma* enhet.

Protokoll, hårdvarutest och exakt patchningsformat:
[docs/midi.md avsnitt 4 och 5b](docs/midi.md#4-rcv-memory-dump--skriva-hela-minnet-fungerar-med-knapptryck).

---

## Vad vi inte vet

Det här är vad som återstår. Var och en är körbar med verktygen i repot –
`probe --manual`, `grab`, `syx_tools.py diff` – och de flesta kräver bara ett
knapptryck på enheten och två dumpar. Det som kräver enheten står också som
bockbar lista i [checklistan](#checklista-verifiera-på-hårdvara) nedan,
tillsammans med det Gemini-rapporten påstår men inte kan belägga.

### Dumpen: kartlagd via EQ-Design, några hål kvar

- ~~Data-offset 127 och framåt är inte kartlagt~~ **Kartlagt 2026-09-03** ur
  EQ-Design: huvud 10 byte, arbetsbuffert 104, gap 76, program 1–100 à 104
  byte med delay, PEQ, namn och GEQ. `apply` rör fortfarande bara GEQ/PEQ i
  arbetsbufferten.
- **Huvudets statusbyte** (byte 0) varierar mellan avläsningar (`24`, `15`,
  `09`). EQ-Design modellerar bit 1 och 6; vad bitarna betyder (IN/OUT?
  EQ/RTA-skärm? stereolink?) är okänt. `probe --manual`, ändra en sak, se
  byte 0.
- **Gapet på 76 byte** (minnesbyte 114–189) som EQ-Design hoppar över:
  `21 35 34 00 2f 00 31` på testenheten. RTA-inställningar? Mic-korrektion?
- **Delayens enhet:** 16 bit rått per kanal; EQ-Design räknar med 48 kHz så
  troligen sampel. Sätt 10 ms på enheten, `probe --manual`.
- ~~Finns en checksumma?~~ Nej – EQ-Design skickar oinitierat stackskräp i
  gapet och enheten tar emot dumpen.
- ~~12100 = 100 × 121~~ – det är 10 + 104 + 76 + 100 × 104 (+ 1 byte fyll).
- ~~Sub-koden i `4F`-svaret varierar~~ – det är statusbyten ovan, ingen header.
- ~~PEQ-gainets LSB~~ – gain är en tecknad byte i 0,5 dB; de "extra bitarna"
  var nästa posts bandindex och, för R3, programnamnets första tecken.

### Skrivvägen

- ~~**PEQ-läget ligger inte i dumpen**~~ **Avgjort 2026-09-03:** varken
  läget *eller* på/av ligger i dumpen. En `apply` skrevs med PEQ av, PEQ slogs på
  för hand, ny dump hämtades – **noll byte skiljde**. Dumpen bär filtrens värden;
  läget (ON/OFF/SGL i FB-D-kolumnen) sätts på fronten. Med **ON** jagar feedback
  destroyern och flyttar filtren själv – sätt OFF före en `apply`.
- **Arbetsbuffert kontra programminne.** Readback läser arbetsbufferten och
  den stämmer, men syns en pushad dump direkt på displayen eller först efter
  en Program Change? Och skrivs de 100 programplatserna över?
- **Blockerar PROTECT MEM?** Testat bara med skyddet av.
- **Master-fadern:** ~~skalan okänd~~ **avklarad 2026-09-03** – samma skala som
  banden (0,5 dB/enhet), index 31 och 63. `apply` skriver ändå inte master: en
  rumskorrigering ska inte flytta utnivån.
- ~~**Röd overflow-LED efter en skrivning.**~~ **Förklarad 2026-09-03:** GEQ-blocket
  låg en bit fel i `patch_dump`, så varje sänkning skrevs som en stor höjning
  (−1 dB blev +63 dB, 28 av 62 band över +16 dB). Rättat och låst av ett test
  mot hårdvarudumpen `dumps/dsp8000_sysex_edges.syx`. Skrivningen efter
  rättelsen landade bit för bit och gav sund EQ (alla band inom ±16 dB).
- **NY BUGG 2026-09-03 12:52: PEQ-frekvensen på displayen stämmer bara för
  post 0 (L1).** Kördes med FB-D OFF på alla sex, precis som ovan. Dumpen som
  skickades (`history/writes/applied-20260903-125243.syx`) och den omedelbara
  SysEx-återläsningen är bit-identiska – enheten tog emot exakt det vi
  avsåg (L1/R1 53 Hz, L2/R2 74 Hz, L3/R3 165 Hz, alla med rätt bandbredd och
  gain). Men **PEQ-sidans display** visade något helt annat:

  | Post | Skrivet (raw) | Display frekvens | Display bw/gain |
  |---|---|---|---|
  | L1 | `0x0405` (band 4=50 Hz, fin 5 → 52,78 Hz) | 53,250 Hz | 37/60, −10 dB – **rätt** |
  | R1 | `0x0405` (samma) | **0 Hz** | 37/60, −10 dB – rätt |
  | L2 | `0x050F` (band 5=63 Hz, fin 15 → 74,11 Hz) | **0 Hz** | 34/60, −11 dB – rätt |
  | R2 | `0x050F` (samma) | **0 Hz** | 34/60, −11 dB – rätt |
  | L3 | `0x0903` (band 9=160 Hz, fin 3 → 165,28 Hz) | **68,018 kHz** | 28/60, −11,5 dB – rätt |
  | R3 | `0x0903` (samma) | **0 Hz** | 28/60, −11,5 dB – rätt |

  Bandbredd och gain (avrundat till enhetens 0,5 dB-raster) stämmer på **alla
  sex** poster. Bara frekvensen är fel, och bara för post 1–5 – post 0 (L1)
  visar rätt (inom rimlig avrundning). Eftersom bw/gain sitter i samma
  32-bitarspost direkt efter frekvensfältet är postgränserna och
  `PEQ_BIT_OFFSET`/`PEQ_REC_BITS` alltså rätt – felet sitter isolerat i hur
  displayen tolkar frekvensbitarna för post ≥ 1, inte i var posten börjar.

  **Två hypoteser, ingen bekräftad:**
  1. Displayen har inte ritat om frekvensfältet för orörda rader efter en
     dump-inladdning (bara den markerade/senast visade raden uppdateras;
     bw/gain "råkar" ändå vara rätt av någon annan anledning) – skulle
     försvinna av att bläddra till varje rad på PEQ-sidan utan att ändra
     något, eller lämna och gå tillbaka till sidan.
  2. Frekvensfältet kodas/tolkas verkligen annorlunda för post ≥ 1 än post 0 –
     skulle inte försvinna av att bläddra.
  Går inte att skilja utan ett nytt hårdvarutest. **Kvar:** skriv *bara* L1
  (övriga OFF/None) och bekräfta den ensam; skriv sedan *bara* L2 (övriga
  OFF) och se om den är rätt i isolation – det avgör om det är radordningen
  eller postindexet som spökar. `apply`/`patch_dump` är **inte** ändrade för
  detta – ingen kod är rättad, bara observationen dokumenterad.

- **EQ-Design:s granulära kommandon** `21` (GEQ, 66 byte opackat) och `22`
  (PEQ, 32 packade byte) skulle ge skrivning **utan RCV MEMORY DUMP-knappen**,
  och `20` sätter limiter/gate/crossfade/delay. Otestade:
  `./run.sh raw 21 00 <32 L> <32 R>` med 32 = 0 dB
  ([docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03)).

### MIDI-detaljer

- **CNTL SND-talet** – flyttar det verkligen de utgående CC-numren? Aldrig
  kontrollerat: CC 17/49 sågs med offset 0, senare tester hade SND = 1 men
  ingen ny capture togs.
- **PROG SND** – skickar enheten Program Change när man byter program för
  hand? Bör synas i `monitor`, aldrig testat.
- **CC ut vid fader-rörelse** är sett men inte systematiskt kartlagt.
- **`33`-ramens skala** är satt till 32 = 0 dB i 0,5 dB-steg (EQ-Design:s
  `21`-format; master 15/16 = −8,5/−8 dB stämmer med dumpen), inte CC-skalan
  som `monitor` visade förut. Verifiera: sätt 1 kHz till +8 dB på fronten,
  `monitor` ska visa +8.0 (råvärde 48).

### Övrigt värt att prova

- **EQ-Design 1.0** är disassemblerad – protokoll och minnesbild i
  [docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03).
  Kvar: köra den skarpt i en Windows 98/XP-VM mot enheten, främst för
  RTA-strömmen (`15`/`11`) och för att se om den skriver `21`/`22` live när
  man drar reglagen.
- **Bandvärdena bygger på en enpunktsmätning** och räknas band för band utan
  modell av hur 1/3-oktavsfiltren överlappar. Mät på fler positioner och
  medelvärdesbilda i REW – och kör `refine`-varvet.

---

## Checklista: verifiera på hårdvara

Allt som bara enheten kan svara på, på ett ställe. Punkter märkta **[G]**
kommer ur [Gemini-rapporten](docs/gemini-report.md) (2026-09-03), som är
skriven utan vår enhet och blandar DSP8000 med DSP8024/DEQ2496 – inget av det
räknas som känt förrän det är bockat här. Resten är de öppna frågorna ovan i
körbar form. Resultat skrivs in i [docs/midi.md testlogg](docs/midi.md#7-testlogg).

**Bara ögonen och ett påslag**

- [ ] **OS-versionen.** Visas kort i displayen vid påslag och är aldrig
  antecknad. **[G]**: 2.0C är sista versionen; EQ-Design kräver ≥ 2.0. Skriv
  in den i [docs/midi.md bilaga B](docs/midi.md#bilaga-b-os-versioner-modellskillnader-pc-mjukvara).
- [ ] **MIC INPUT: fram [G] eller bak (readme)?** Och är +15 V-fantomen
  brytbar?
- [ ] **Omvandlare 20 eller 24 bit?** Frontpanelens tryck / manualens
  spec-sida. readme säger 20, **[G]** 24-bit sigma-delta (ser ut som
  DSP8024-spec).
- [ ] **Samplingsfrekvens.** GLOBAL SETUP → INPUT: finns 44,1/48 kHz
  ([docs/midi.md 2](docs/midi.md#2-midi-setup-sidan)) eller är den fast 44,1
  **[G]**? Avgör om rew.md:s "48 kHz" stämmer.
- [ ] **Crossfade och shelving i menyerna.** Dumpens huvud säger crossfade
  **10 s** och shelving **27 dB/okt** på testenheten (EQ-Design:s tolkning).
  Finns inställningarna i SETUP, och stämmer värdena? DELAY 8000-kortet:
  finns DELAY-sidan alls?
- [ ] **Programnamn på fronten.** Dumpen har 12-teckensnamn (`BAS  ROCK`,
  `MOVIE`, `AUT O Q` … – `syx_tools.py eq` listar dem). Var döper man om, och
  visar displayen namnet vid programbyte?

**En signal och öronen**

- [ ] **Fail-safe-relä. [G]**: vid strömbortfall kopplar reläer in → ut
  direkt. Musik genom enheten, dra nätsladden: går ljudet igenom?
- [ ] **Mutar en dump ljudet? [G]**: "ljudfunktionerna inaktiveras
  temporärt" under en minnesdump. Musik genom enheten, `./run.sh grab x.syx`:
  tystnar det i ~5 s? Samma vid RCV MEMORY DUMP. Avgör om `apply` kan köras
  mitt i lyssning.

**MIDI**

- [ ] **Svarar enheten från RTA-skärmen? [G]** (och ADRStudio för DSP8024):
  SysEx tas emot på EQ- *och* RTA-skärmen, inte i SETUP, LEVEL METER, FB-D,
  PEQ. Bara EQ-skärmen är testad. `./run.sh grab` från varje skärm.
- [ ] **Device-ID = MIDI-kanal − 1.** Så gör EQ-Design, och `44`-svaret ska
  bära enhetens kanal. Vi har bara kört `00` med CHANNEL 1. Sätt CHANNEL 2:
  `./run.sh raw 43` med `00` (ska tigas ihjäl?) – och ändra `_send_sysex`:s
  dev till `01`.
- [ ] **EQ-Design:s kommandon**, alla otestade
  ([docs/midi.md 6.8](docs/midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03)):
  `./run.sh raw 43` ska ge ett `44`-svar; `raw 40` dumpen; `raw 41` / `raw 42`
  ska byta EQ/RTA på displayen; `raw 15 00` ska ge en `11`-RTA-ram; `raw 21 00`
  + 64 byte (32 = 0 dB) ska skriva GEQ **utan knapptryck**; `raw 22 00` + 32
  packade byte ska skriva PEQ. Lyckas `21`/`22` blir `apply` knappfri.
- [ ] **`33`-ramens skala:** 1 kHz till +8 dB på fronten, `monitor` ska visa
  +8.0 (råvärde 48, inte 96).
- [ ] **CC utanför 0–63. [G]**: master, bypass och limiter kan styras via CC.
  Med CNTL RCV 0 är CC 64–127 lediga: skicka dem ett i taget med displayen i
  ögonvrån. Bypass via MIDI vore guld för REW-mätningen.
- [ ] **CNTL SND-talet:** SND = 1, rör 1 kHz-fadern, `monitor` ska visa CC
  18/50 (inte 17/49).
- [ ] **PROG SND:** byt program på fronten, syns Program Change i `monitor`?
- [ ] **PROTECT MEM ON:** blockeras RCV MEMORY DUMP? (`roundtrip` med skyddet på.)
- [ ] **Programminne kontra arbetsbuffert:** spara ett känt program, `roundtrip
  --keep`, byt till programmet och tillbaka – vad står kvar? Syns pushen
  direkt på displayen?
- [x] **`apply` med allt rättat**, kört 2026-09-03 12:52 – avslöjade i stället
  "NY BUGG"-punkten ovan (PEQ-displayen fel för post 2–6). REW-sweepen och
  LED-kollen är därför inte meningsfulla förrän den bilagd.
- [ ] **Isolera PEQ-displaybuggen ("NY BUGG" ovan):** `apply` med *bara* L1
  satt (L2/L3/R1–R3 = None/OFF) → stämmer L1 ensam? Sedan `apply` med *bara*
  L2 satt → stämmer den i post-index 2, eller är felet knutet till
  rad-ordningen på displayen snarare än postindexet? Testar om det försvinner
  av att bläddra till raden på PEQ-sidan utan att ändra något.
- [ ] **PEQ-gain på udda åttondel** (−9,75 dB, FB-D OFF): vad visar displayen,
  och hörs/mäts −9,75 eller −10?

**Locket av** (gör det vid batteribytet – backup först)

- [ ] **Batteriet. [G]**: CR2032-typ, ~5 år, minnet korrumperas under ~2,6 V
  och är helt borta när batteriet är ur. Mät spänningen, anteckna typ och om
  det sitter i hållare eller är lött.
- [ ] **Backup → byte → återställning** är det skarpa RCV-testet:
  `./run.sh grab dumps/backup-<datum>.syx` före, factory reset **[G]** vid
  påslag efteråt (knappkombinationen finns inte i rapporten – leta i
  manualen V1.3 *innan*), sedan RCV MEMORY DUMP (+) och `./run.sh push`.
  Kommer de 100 programmen tillbaka?
- [ ] **EPROM-etiketten** (OS-version) och om den är socklad **[G]**.
- [ ] **Kretskortet:** revision, tomma socklar (delay-minne **[G]**),
  AES-expansionsplats, nätdel (linjär med trafo **[G]** – kolla
  glättningskondensatorerna).

---

## Enhetens egna funktioner

### Auto-Q (inbyggd rumskorrigering)

Mätmikrofon (t.ex. ECM8000) i **MIC INPUT** på baksidan (inbyggd +15 V
fantommatning), mikrofonen på lyssningspositionen.

| RTA SETUP-parameter | Rekommenderat värde |
|---|---|
| SOURCE | MICRO |
| GAIN MODE | AUTO |
| MIC CORR | NONE |
| AUTO-Q CURVE | FLAT |
| RTA OUTPUT | PINK |
| LEVEL | ca −20 dB |

RTA-läge → Softkey B (TOOLBOX) → Softkey A (AUTO-Q) → välj vänster, höger
eller båda. Enheten spelar rosa brus, mäter och justerar den grafiska EQ:n.

- Höjer aldrig ett band mer än 12 dB (skyddar högtalare från orealistiska boostar)
- Börjar alltid från nuvarande EQ-inställning – förbehandla manuellt om du vill
  styra vilket område som justeras
- Avbryt med OK-knappen; det som redan justerats behålls
- "NO SIGNAL DETECTED" = för svag mikrofonkänslighet, byt mick eller använd
  extern förförstärkare

**Begränsning:** grafisk EQ är ett trubbigt verktyg för smala rumsmoder i
basen. Använd de 3 parametriska filtren för sådana.

### FB-D (Feedback Destroyer)

Automatisk detektering och dämpning av rundgång, med **samma tre parametriska
filter** som annars används för rumskorrigering – de konkurrerar om samma
resurs. Läget ställs per filter i FB-D-kolumnen på PEQ-sidan och heter på
testenheten **ON / OFF / SGL** (DSP8024-dokumentationen säger AUT / PAR / SGL):
**ON** = destroyern letar kontinuerligt och flyttar filtret själv, **SGL** =
single shot, filtret fixeras på hittad frekvens, **OFF** = filtret står still
med sina värden. Läget ligger inte i dumpen. Fungerar bäst på dynamiskt
signalinnehåll (tal, sång), inte stationära toner. Primärt för PA/scen. För
rumskorrigering: **OFF på alla sex innan en `apply`**, annars skriver
destroyern över frekvenserna (2026-09-03 blev 53/74/166 Hz till 16–20 kHz på
tolv minuter).

### Underhåll

Ur [Gemini-rapporten](docs/gemini-report.md), inte verifierat på vår enhet
(checklistan ovan):

- **Batteriet** (CR2032-typ, ~5 år) håller de 100 programmen vid liv. Symptom
  på slut: slumptecken i displayen, krascher vid start, förlorade kurvor.
  Ordning vid byte: `./run.sh grab dumps/backup-<datum>.syx` → byt → factory
  reset vid påslag → RCV MEMORY DUMP (+) → `./run.sh push dumps/backup-<datum>.syx`.
  Dumpen är hela minnet, även det vi inte tolkar, så den duger som backup –
  om de 100 programmen följer med är dock obekräftat.
- **Pulsgivaren** slits: hoppande värden vid vridning. Kontaktspray hjälper
  tillfälligt, byte är fixen.
- **Nätdelen** är linjär (trafo + regulatorer): 100 Hz-brum = kolla
  elektrolyterna.

---

## Repot

Verktygen som producerade allt ovan, och som kör hela kedjan REW → mätning →
EQ-förslag → enheten:

```sh
./run.sh help               # full kommandolista
./run.sh gui                # webb-kontrollpanel: läs enheten, redigera EQ, skriv
./run.sh readback           # läs enhetens GEQ + PEQ (ändrar inget, kräver bara MIDI)
./run.sh test               # självtester, kräver varken REW eller enheten
```

| Var | Vad |
|---|---|
| [docs/midi.md](docs/midi.md) | **MIDI-referensen**: inställningar, CC, SysEx, dump-layout byte för byte, testlogg, ADRStudio-protokollet, källor |
| [docs/verktyg.md](docs/verktyg.md) | skripten och kontrollpanelen: installation, `run.sh`, arbetsflöde, filöversikt |
| [docs/rew.md](docs/rew.md) | REW-flödet: mätning, målkurva, Match Target, HTTP-API, `rew_script.py` |
| [docs/midi_captures.txt](docs/midi_captures.txt) | rå labblogg från captures (historik; senare poster rättar tidigare) |
| `dumps/*.syx` | referensdumpar från enheten med känt innehåll |
| `docs/keiths-blog-…html` | sparad blogg om DSP8024 (Auto-Q, firmware via EPROM) |
| [docs/gemini-report.md](docs/gemini-report.md) | Gemini-genererad rapport om DSP8000 (2026-09-03); inleds med vad i den som strider mot våra fynd |

Källor (manualer, ADRStudio, forum) längst ned i [docs/midi.md](docs/midi.md#källor).
