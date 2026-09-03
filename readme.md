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
20-bit AD/DA (ej 24-bit), enklare MIDI (hela minnesdumpen via SysEx, ingen
granulär styrning), delay och AES/EBU som tillval.

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
| Skriva GEQ **och** PEQ via patchad dump | dator → DSP | **verifierat** (roundtrip 2026-09-03); en `apply` med rättad PEQ-frekvens återstår |
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
Svar:       F0 00 20 32 00 01 4F <sub> <flag> 20 00  <12100 databyte>  F7
```

`00 20 32` = Behringers manufacturer-ID, `01` = modell DSP8000 (`0E`, som är
DSP8024, ignoreras helt). Oavsett `xx` svarar enheten med **hela minnet** – det
finns ingen granulär läsning och ingen versionssträng. Enheten måste stå på
EQ-huvudskärmen. Förfrågan ändrar ingenting.

Databytena är alla < 128 men **bit-packade**: de packas upp MSB-först, 7 bitar
per byte, till en bitström som fälten läses ur.

### Avkodad dump-layout

| Block | Bit-offset | Data-offset | Format |
|---|---|---|---|
| Okänt (arbetsbuffert) | 0–86 | 0–12 | lika i alla dumpar; kandidat: limiter/gate/delay/flaggor |
| **PEQ** | 87–278 | 12–39 | 6 poster à 32 bitar, ordning L1 R1 L2 R2 L3 R3 |
| Okänt mönster | ~278–340 | 39–47 | satt i knapp-dumpar, noll i förfrågnings-dumpar |
| **GEQ** | 372–883 | 53–126 | 64 tecknade 8-bitarsvärden: 31 vä band, vä master, 31 hö, hö master |
| Resten | 885– | 127– | **ej kartlagt** (delay, gate, limiter, de 100 programmen …) |

GEQ-värde: **0,5 dB per enhet**, `dB = värde / 2`, ±32 = ±16 dB – enhetens
egna steg, alltså halva CC-skalans upplösning. Master (index 31 och 63) ligger
i samma block och på samma skala. Blocket låg felkartlagt på bit 373/kvarts-dB
fram till 2026-09-03; rättelsen och vad felet ställde till med står i
[docs/midi.md 6.4](docs/midi.md#64-avkodad-layout-verifierad-med-probe--probe---manual).

PEQ-post, 32 bitar: frekvens 13 bitar (**5 bitar ISO-bandindex + 8 bitar
finsteg om 1/64 oktav**, `f = ISO[raw>>8] · 2^((raw&255)/64)`), bandbredd
8 bitar (`(raw+1)/60` oktav), gain 10 bitar tvåkomplement (`dB = raw/8`).
Postens sista bit tillhör nästa block och skrivs inte. Posten helt noll =
inga värden satta. Verifierat mot handsatta filter (1 kHz = `0x1100`) och
enhetens egna destroyer-filter avlästa på displayen (96 Hz, 17/18/19/20 kHz).
Kodningen är inte entydig – finsteget får överstiga ett tersband, och enheten
skrev själv `0x0527` (63 Hz + 39 steg) för 96 Hz – men alla varianter läses
lika; vi skriver alltid närmaste band under. FB-D-läget (ON/OFF/SGL) ligger
inte i dumpen.

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

### Dumpen: ~95 % av minnet är okartlagt

- **Data-offset 127 och framåt är inte kartlagt.** Där ligger delay, noise
  gate, limiter, RTA-inställningar och de 100 sparade programmen. Därför rör
  `apply` dem inte – de bevaras orörda från basdumpen. Metod: `probe --manual`,
  ändra *en* sak på enheten, diffa.
- **De första 12 databytena** (`80 36 00 00 00 02 33 16 …`) är lika i alla
  dumpar. Arbetsbuffert-flaggor? Limiter/gate/delay?
- **Finns en checksumma?** 9 byte vid data-offset 39–47 är satta i
  knapp-dumpar men noll i förfrågnings-dumpar, och mönstret återkommer vid
  199–207. Om det är en checksumma över något vi ändrar borde en patchad dump
  ha avvisats – det gjorde den inte, så troligen inte. Obekräftat.
- **Sub-koden i `4F`-svaret varierar:** `4F 0A`, `4F 04` och `4F 12` har alla
  setts från samma enhet. Byte 7 bär enhetsstatus snarare än format – vad `04`
  betyder är oklart, och just den varianten dök upp i den enda skrivning som
  gav röd overflow-LED.
- **12100 = 100 × 121 går jämnt ut**, men mönstret vid data 39 återkommer vid
  199 (delta 160, inte 121). "100 program × 121 byte" är alltså **inte**
  bekräftat.
- ~~**PEQ-gainets LSB.**~~ **Bredden avgjord 2026-09-03:** 10 bitar à 1/8 dB
  (bit 278 är satt i orörda dumpar, alltså nästa block). Enheten behåller ett
  udda åttondels-värde byte-exakt (−9,75 dB lästes tillbaka som −9,75), men
  när destroyern själv skrev om fem filter landade alla på 0,5 dB-steg
  (−9,75 → −10, −10,75 → −11, −11,375 → −11,5). **Okänt:** vad displayen visar
  och DSP:n gör med −9,75. Test: skriv ett filter med udda åttondel, FB-D
  OFF, läs displayen.

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
- **Nästa hårdvarutest: en `apply` med allt rättat.** Frekvenskodningen
  rättades 2026-09-03 kl. 11:22, *efter* dagens sista `apply`, så ingen
  skrivning med rätt PEQ-frekvenser är gjord ännu. Kör: FB-D **OFF** på alla
  sex filtren → `apply` → PEQ-sidan ska visa kurvans frekvenser (förra gången
  stod 96/424/269 Hz där kurvan sa 53/74/166) och de ska stå kvar → IN/OUT-LED
  grön, inte röd → REW-sweep som visar att filtren bearbetar ljudet med FB-D
  OFF. Det sista är inte verifierat: OFF *bör* betyda stillastående
  parametriskt filter, men bara en sweep avgör.

### MIDI-detaljer

- **CNTL SND-talet** – flyttar det verkligen de utgående CC-numren? Aldrig
  kontrollerat: CC 17/49 sågs med offset 0, senare tester hade SND = 1 men
  ingen ny capture togs.
- **PROG SND** – skickar enheten Program Change när man byter program för
  hand? Bör synas i `monitor`, aldrig testat.
- **CC ut vid fader-rörelse** är sett men inte systematiskt kartlagt.

### Övrigt värt att prova

- **EQ-Design 1.0** (Behringers Windows 95/NT-editor) **finns på archive.org**:
  [archive.org/details/eqdes](https://archive.org/details/eqdes), `EQDESIGN.EXE`
  846 kB daterad 1996-12-09, kräver DSP8000 OS ≥ 2.0 och ett
  MPU-401-kompatibelt interface. Arkivets beskrivning säger att den styr
  delay, gate och limiter och gör "MIDI dump requests and user memory
  updates". Kör den i en Windows 98/XP-VM med USB-MIDI genomkopplat och
  sniffa trafiken: pratar den bara `4F`-dumpar fram och tillbaka, eller finns
  kommandon vi inte hittat? Dess delay/gate/limiter-reglage ger de bitfälten
  gratis. Mer i [docs/midi.md bilaga B](docs/midi.md#bilaga-b-os-versioner-modellskillnader-pc-mjukvara).
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
- [ ] **Finns DELAY och crossfade i menyerna?** DELAY 8000 är tillval; **[G]**
  nämner programmerbar crossfade-tid vid programbyte (ADRStudio `23`, 0–15 s
  på DSP8024). Finns den: `probe --manual` för att se om den ligger i dumpen.
- [ ] **Programnamn. [G]**: 100 minnen med alfanumeriska namn. Går det att
  döpa? Då: döp ett program unikt, spara, `grab`, sök mönstret – snabbaste
  vägen till programblocken ([docs/midi.md 6.7](docs/midi.md#67-kartlägga-fler-fält)).

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
- [ ] **Device-ID = MIDI-kanal? [G]**. Vi skickar alltid `00` med CHANNEL 1.
  Sätt CHANNEL 2, skicka `70 01` med dev `00`, `01` och `7F` (`_send_sysex`
  i `rew_to_dsp8000.py`): vilka besvaras?
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
- [ ] **`apply` med allt rättat** (punkten "Nästa hårdvarutest" ovan): FB-D
  OFF ×6 → `apply` → PEQ-sidan visar kurvans frekvenser → LED grön →
  REW-sweep visar att OFF-filtren bearbetar ljudet.
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
