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
| Skriva GEQ **och** PEQ via patchad dump | dator → DSP | **verifierat** (roundtrip 2026-09-03) |
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

PEQ-post, 32 bitar: frekvens 13 bitar (`f = 20 · 10^(raw/2560)` Hz, 20 kHz = 7680), bandbredd
8 bitar (`(raw+1)/60` oktav), gain 10 bitar tvåkomplement (`dB = raw/8`).
Postens sista bit tillhör nästa block och skrivs inte.
OFF = posten helt noll. Verifierat mot 6 filter satta för hand på enheten.

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
knapptryck på enheten och två dumpar.

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
- **PEQ-gainets LSB.** Alla testvärden var hela 0,5 dB-steg, så de tre lägsta
  gain-bitarna var alltid noll. Fältet kan vara 10 bitar (1/8 dB) med bit 278
  tillhörande nästa fält. Avgörs med ett PEQ-filter på ett udda värde plus en
  dump tagen med **knappen**.

### Skrivvägen

- ~~**PEQ-läget PAR/AUT/SGL ligger inte i dumpen**~~ **Avgjort 2026-09-03:** varken
  läget *eller* på/av ligger i dumpen. En `apply` skrevs med PEQ av, PEQ slogs på
  för hand, ny dump hämtades – **noll byte skiljde**. Dumpen bär filtrens värden;
  inkopplingen sker på fronten. Kvar: slå på PEQ efter varje dump-skrivning.
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
  mot hårdvarudumpen `dumps/dsp8000_sysex_edges.syx`. **Kvar att verifiera på
  hårdvara:** att en `apply` nu ger tyst, korrekt EQ och ingen röd LED.

### MIDI-detaljer

- **CNTL SND-talet** – flyttar det verkligen de utgående CC-numren? Aldrig
  kontrollerat: CC 17/49 sågs med offset 0, senare tester hade SND = 1 men
  ingen ny capture togs.
- **PROG SND** – skickar enheten Program Change när man byter program för
  hand? Bör synas i `monitor`, aldrig testat.
- **CC ut vid fader-rörelse** är sett men inte systematiskt kartlagt.

### Övrigt värt att prova

- **EQ-Design / UltraCurve Design** (Behringers gamla Windows 9x-editor, ej
  längre nedladdningsbar). Givet att DSP8000 bara kan dumpa allt talar den
  troligen samma `4F`-dump fram och tillbaka. Skulle bekräfta RCV-vägen och
  eventuellt avslöja fler fält.
- **Bandvärdena bygger på en enpunktsmätning** och räknas band för band utan
  modell av hur 1/3-oktavsfiltren överlappar. Mät på fler positioner och
  medelvärdesbilda i REW – och kör `refine`-varvet.

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
resurs. **AUT** = filtren letar kontinuerligt efter ny feedback, **SGL** =
filtret fixeras på hittad frekvens. Fungerar bäst på dynamiskt signalinnehåll
(tal, sång), inte stationära toner. Primärt för PA/scen, mindre relevant vid
rumskorrigering hemma.

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

Källor (manualer, ADRStudio, forum) längst ned i [docs/midi.md](docs/midi.md#källor).
