# DSP8000 / DSP8024 – MIDI & inställningar: webbresearch

Bred nätsökning 2026-09-02 om Behringer Ultra-Curve **DSP8000** (och den nära
besläktade **DSP8024 PRO**), med fokus på **MIDI-kopplingen** och alla
inställningar som går att fjärrstyra. Kompletterar `readme.md` avsnitt 6.

Allt nedan är hämtat från publika källor (manualer på archive.org, den
tyska 2001-manualen, ADRStudio:s reverse-engineerade SysEx-lista, forum,
Sound on Sound).

**Verifierat mot enheten 2026-09-02** (`rew_to_dsp8000.py sysex`): se
avsnitt 10. Kort version: **ADRStudio:s granulära DSP8024-protokoll
fungerar INTE på vår DSP8000.** Modellbyte `0E` ger noll svar. En
`F0 00 20 32 00 01 70 xx … F7`-förfrågan (valfri `xx`) svarar alltid med
**hela den packade 12110-byte-dumpen** (~5 s), inte ADRStudio:s korta svar.
Nyttan som blev kvar: dumpen kan hämtas **på begäran utan fader-nudge**.

---

## 0. TL;DR – det viktigaste

1. **MIDI-implementationen skiljer sig mellan OS-versioner:**
   - **DSP8000 med 1996-OS** (manual V1.3): fast CC-mappning **64–127**,
     `MIDI OUT` "har ingen funktion", MIDI-chart säger **ingen SysEx**,
     ingen memory dump-sida.
   - **DSP8000 med nyare OS** + **DSP8024**: justerbar **Controller
     Offset 0–64**, `MIDI OUT` skickar programdata + status, **SysEx
     skickas och tas emot**, `SND/RCV MEMORY DUMP` på MIDI-sidan.
     **Detta matchar testenheten.** (EQ-Design-mjukvaran kräver DSP8000
     OS ≥ V2.0 / DSP8024 OS ≥ V1.1 – exakt när SysEx tillkom är inte
     bekräftat, men vår enhet har det.)
   - **DSP8024** har dessutom ett granulärt realtids-SysEx-protokoll
     (ADRStudio, avsnitt 6) för limiter, gate, delay, parametriska filter
     och RTA. **Det protokollet svarar inte vår DSP8000** (avsnitt 10).

2. **CC-mappning (offset 0):** `CC 0–30` = vänster GEQ 20 Hz…20 kHz,
   `CC 31` = vänster master, `CC 32–62` = höger GEQ, `CC 63` = höger master.
   Datavärde `0–127`. Med offset N adderas N till alla nummer.
   Testenheten kör offset 0 → stämmer med `dsp8000.py`.

3. **SysEx-header:** `F0 00 20 32 <dd> <mm> <cmd…> F7`.
   `00 20 32` = Behringers manufacturer-ID. `dd` = device (00 = adresserad,
   7F = broadcast). `mm` = modell-ID (inferens): **`01` = DSP8000, `0E` =
   DSP8024**. Vår enhet svarar bara på `01` och ignorerar `0E` helt
   (testat, avsnitt 10). ADRStudio:s lista använder genomgående `0E`.

4. **ADRStudio:s DSP8024-protokoll (avsnitt 6) fungerar INTE på vår DSP8000.**
   Testat 2026-09-02: modellbyte `0E` → inget svar; `01` + valfri
   `70`-förfrågan → hela den packade minnesdumpen (~12110 byte, ~5 s), aldrig
   ADRStudio:s korta svar. Behåll avsnitt 6 som **DSP8024-referens**.
   Enda praktiska vinsten: dumpen kan hämtas **på begäran utan fader-nudge**
   med `F0 00 20 32 00 01 70 01 F7`.

---

## 1. Modellskillnader (MIDI-relevanta)

| | DSP8000 (1996-OS, manual V1.3) | DSP8000 (nyare OS) / DSP8024 |
|---|---|---|
| AD/DA | 20-bit (DSP8000) | 24-bit (DSP8024) |
| Parametriska filter | 3 per kanal (6 tot.) | 3 per kanal (6 tot.) |
| GEQ | 31-band 1/3-oktav, ±16 dB / 0,5 dB-steg | samma |
| MIDI-kanal | OFF, ALL, 1–16 | OFF, ALL (Omni), 1–16 |
| Controller offset | **fast** (motsvarar offset 64) | **justerbar 0–64** |
| MIDI OUT | "ingen funktion ännu" | skickar programdata + status |
| SysEx | **nej** (chart: X/X) | **ja** (chart: O/O) |
| Memory dump-sida | finns ej | `SND/RCV MEMORY DUMP` |
| PC-editor | – | EQ-Design / UltraCurve Design |

> Sound on Sound-recensionen (av 1996-modellen) skrev att ingen data kom
> ut via MIDI och att SysEx-dumpar därför inte gick att spara. Det gällde
> det gamla OS:et – testenheten dumpar (12110 byte), alltså nyare firmware.

**Kolla enhetens OS-version:** visas kort i displayen direkt efter påslag.
Firmware kunde bara uppdateras genom att skicka in enheten till Behringer
(EPROM-byte).

---

## 2. Fysisk MIDI-anslutning

- 3× 5-pol DIN (IN / OUT / THRU) på baksidan. Optokopplad, potentialfri.
- Standard MIDI-kabel: Pin 2 = skärm, Pin 4 + 5 = ledare, Pin 1 + 3 oanvända.
- Max kabellängd ~15 m (eng. manual: "45 feet", tysk: "15 Meter").
- **MIDI IN:** tar emot Program Change, Controller och (nyare OS) SysEx.
- **MIDI THRU:** oförändrad genomsläppning – flera enheter kan kedjas.
- **MIDI OUT (nyare OS):** skickar programdata + statusinfo till dator eller
  till andra Ultra-Curve (master/slave). På 1996-modellen: inaktiv.

Returväg fungerar på testenheten först när **båda** kablarna sitter i
(AudioBox OUT→DSP8000 IN *och* DSP8000 OUT→AudioBox IN) – verifierat
2026-09-02, se `readme.md`.

---

## 3. MIDI SETUP-sidan (nyare OS / DSP8024)

Nås via **SETUP-knappen hålld > 2 sek** → bläddra med SETUP till sida 2
(sida 1 = GLOBAL SETUP, sida 2 = MIDI SETUP). Cursor väljer fält, `+/–`
softkeys ändrar.

| Fält | Betydelse | Värden |
|---|---|---|
| **MIDI** | MIDI-funktion på/av | ON / OFF |
| **CHANNEL** | mottagningskanal. "OMNI MODE" = ta emot på alla kanaler | OFF / OMNI (ALL) / 1–16 |
| **SND MEMORY DUMP** | `+/–` utlöser dump av hela minnet ut på MIDI OUT | (tryck) |
| **RCV MEMORY DUMP** | `+/–` sätter enheten i mottagningsläge för en extern dump | (tryck) |
| **CNTL** | Controller-data sänds/tas emot. Talet = **första controller-numret** (offset). Manualen: de följande 64 numren = frekvenserna 20 Hz–20 kHz + master, först vänster kanal, sedan höger. | RCV / SND, offset **0–64** |
| **PROG** | Program Change sänds/tas emot | RCV ON/OFF, SND ON/OFF |
| **EXCL** | System Exclusive sänds/tas emot. Krävs för EQ-Design-mjukvaran (manualen: alla parametrar och funktioner blir då fjärrstyrbara) | RCV ON/OFF, SND ON/OFF |

> `CNTL` är **inte** ON/OFF utan ett **tal** (offset). RCV och SND har
> varsitt. Testenheten: `RCV = 0`, `SND = 1`. `dsp8000.CC_OFFSET` måste = `RCV`.

**Rekommenderad inställning för CC-styrning (verifierad i `readme.md`):**
MIDI ON · CHANNEL 1 · OMNI ON · CNTL RCV 0 / SND 1 · PROG RCV+SND ON ·
EXCL RCV+SND ON.

**För SysEx (memory dump på vår enhet, eller EQ-Design/StudioWare på en
DSP8024):** slå på `EXCL SND` + `RCV`. Vid rena SysEx-verktyg rekommenderar
ADRStudio att man slår **av `CNTL SND` + `RCV`** så att inte controller-ekon
nollställer inställningar av misstag. (Vår `sysex`-test gjordes med
`CNTL RCV = 0` utan problem – bara läsförfrågningar skickades.)

### GLOBAL SETUP (sida 1) – övrigt värt att känna till

| Fält | Värden |
|---|---|
| INPUT | Analog / Digital (AES/EBU-option). Samplingsfrekvens i analogläge: **44,1 / 48 kHz** enligt DSP8024-manualen (32 kHz bara via AES/EBU). 1996-DSP8000 tillät även 32 kHz analogt. Byte mutar ~1 sek. |
| VIEWING ANGLE | LCD-kontrast 0–31 (även SETUP + Cursor upp/ned) |
| RTA LOCK | spärr mot att gå in i RTA-läge |
| SECURITY | UNLOCK / LOCK med lösenord. LOCK: allt spärrat utom EQ-display och level meter – enligt manualen är då MIDI enda sättet att ändra |
| PROTECT MEM | skrivskydd för programminne, med EQ LO/HI och RTA LO/HI som gräns |

Glömt lösenord → batteriet ut en stund → **alla program raderas**.

---

## 4. MIDI Implementation Chart

Ur **DSP8024-manualen, Tab. 7.1** (förkortad – Note/Velocity/Aftertouch-
raderna är slagna ihop). Antas gälla även DSP8000 med nyare OS; ej separat
verifierat för DSP8000.

```
Function            Transmitted   Recognized   Remarks
Basic  Default          X          1-16        memorized
Channel Changed         X          1-16
Mode   Default          X          1,2,3,4
       Messages         X          X
Note / Velocity / AT    X          X
Pitch Bender            X          X
Control Change          O          O           controller-offset justerbar (se Tab 7.2)
Program Change          0-99       0-99        True # 1-100
System Exclusive        O          O
System Common / Real T. X          X
Aux Messages            X          X

O = YES   X = NO
Mode 1: OMNI ON, POLY    Mode 3: OMNI OFF, POLY
Mode 2: OMNI ON, MONO    Mode 4: OMNI OFF, MONO
```

**1996 DSP8000 V1.3-charten skiljer sig:** `System Exclusive` = `X / X`
(inget stöd), `Program Change` transmitted = `X` (`MIDI OUT` inaktiv), och
Control Change står som **fast 64–127**: 64–94 vä EQ · 95 vä master ·
96–126 hö EQ · 127 hö master.

---

## 5. Controller-implementation (Tab. 7.2) + Program Change

### Status bytes

```
Program Change:  Cn pp      n = kanal (0–F),  pp = program 0..99
Control Change:  Bn cc vv    n = kanal,  cc = controllernr,  vv = värde 0–127
                 Controller-offset justerbar 0–64  (adderas till cc)
```

*(Manualen skriver detta slarvigt som `Pcxx` / `Ccxx` – status-nibblarna
är egentligen `0xC0|n` för Program Change och `0xB0|n` för Control Change.)*

### Data bytes (offset = 0)

| Contrl.-nr | Parameter | Definition | Range |
|---|---|---|---|
| **0–30** | EQ Left | 20 Hz, 25 Hz, …, 16 kHz, 20 kHz (31 ISO-band) | 0–127 |
| **31** | Master Level Left | | 0–127 |
| **32–62** | EQ Right | 20 Hz, 25 Hz, …, 16 kHz, 20 kHz | 0–127 |
| **63** | Master Level Right | | 0–127 |

- Med **offset N**: lägg till N på alla nummer. Gamla DSP8000 = fast offset 64.
- **Värdeskala GEQ via CC:** 0–127, mitt = 64 = 0 dB. Projektet har
  kalibrerat **`CC = 64 + dB × 4`** mot displayen (0,25 dB/CC nominellt,
  men GEQ:n har 0,5 dB-upplösning så enheten rundar). ±16 dB ⇒ teoretiskt
  0…128, klipps vid 127.
- **Program Change:** 0–99 sänds/tas emot (displayen visar 1–100).
- **31 ISO-frekvenser:** 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200,
  250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000,
  5000, 6300, 8000, 10000, 12500, 16000, 20000 Hz.

> **Tre olika GEQ-värdeskalor förekommer** (håll isär):
> CC-datavärde 0–127, mitt 64 (Tab 7.2 + vår kalibrering) ·
> ADRStudio realtids-SysEx `10h` 0–64, mitt `20`h=32 (avsnitt 6, DSP8024) ·
> den packade dumpen `(dB+16)×4` ≈ 0–127, mitt 64 (`midi_captures.txt`).

### PEQ-regelområde

GEQ: +16…−16 dB i 0,5 dB-steg (Tab 7.2 / spec).
**PEQ: +16…−48 dB i 0,5 dB-steg** (DSP8024-manualen, bekräftat av ADRStudio
`21h` i avsnitt 6). PEQ går **inte** via CC – bara via SysEx (avsnitt 6,
DSP8024) eller "ställ för hand → spara program → Program Change".

---

## 6. Realtids-SysEx-protokoll (DSP8024)

Reverse-engineerat av **Adriano Ficarelli Jr, ADRStudio.com** (rev 14,
2006) genom att sniffa trafiken mellan EQ-Design och enheten. Behringer
publicerade aldrig detta.

> **Testat mot vår DSP8000 2026-09-02 – protokollet nedan gäller DSP8024,
> inte vår enhet.** Modellbyte `0E` ignoreras helt. Med `01` svarar
> enheten på *varje* `70`-läsförfrågan (`70 01`, `70 10 1F`, `70 64` …)
> med samma sak: hela den packade 12110-byte-dumpen
> (`F0 00 20 32 00 01 4F 0A …`), ~5 s efter förfrågan – aldrig ett kort,
> granulärt svar. Realtidsskrivningen `10h` (GEQ-band) är nu **testad** och
> gör **inget** – varken med modellbyte `01` eller `0E` ändras dumpen (0 byte,
> kontrollerat mot GEQ-avkodningen 2026-09-02). `21h`/`1F`/`20` (PEQ) lär vara
> lika döda. DSP8000:s OS har alltså en mycket enklare SysEx-hanterare – den
> kan bara dumpa. **Allt nedan är DSP8024-referens**, återgivet efter ADRStudio.

**Om notationen nedan:** kommandobyte anges hex. Datavärden återges som
ADRStudio skrev dem – där blandas decimalt och hex utan markering, och
listan har kända skrivfel (t.ex. "`1Eh` = 10 kHz" fast `00`–`1E` är
31 band = 20 Hz–20 kHz). Inget av detta är verifierat mot hårdvara här.

### Header

```
Skicka:   F0 00 20 32 00 0E <cmd> <data…> F7
Begära:   F0 00 20 32 00 0E 70 <param> [70 <param> …] F7
   (eller F0 00 20 32 7F 0E …  – 7F = broadcast/alla enheter)
Svar:     F0 00 20 32 00 0E <param> <värde…> F7
```

Flera kommandon kan **kedjas** i en sträng: en header, sedan flera
`<cmd><data>`-block, avsluta med ett `F7`.

### ⚠️ Skärmbegränsning
SysEx-**mottagning är avstängd** när enheten visar FEEDBACK DESTROYER,
parametrisk EQ eller LEVEL METER. Enheten måste stå på **EQ-huvudskärmen**.
Det finns inget kommando för att byta tillbaka till EQ-skärmen, och inget
för att växla mellan L/R på EQ-displayen eller nollställa RTA HOLD.

### SEND – generellt

| Kmd | Funktion | Data |
|---|---|---|
| `02` | Analyze IN/OUT (IN = bypass) | `00` = IN, `01` = OUT |
| `08` | Växla Equalizer / RTA | `00` = EQ, `01` = RTA |

`sb`-byten i PEQ-kommandona: hög nibble = kanal (`0` vä / `2` hö),
låg nibble = band (`0`–`2`). Ex: `21` = höger kanal, band 1.

| Kmd (hex) | Funktion | Data (dec om inget annat) |
|---|---|---|
| `10` | **GEQ frekvensnivå** `10 sr xx` | `sr` **hex**: `00`–`1E` vä band, `20`–`3E` hö band (`00`=20 Hz, `01`=25 Hz, …, 31 band). `xx` = 0–64, **32 = 0 dB** (ADRStudio skriver mitten som `20h`) |
| `11` | **Master volym** `11 s0 xx` | `s` = 0 vä / 2 hö. `xx` = 0–64, 32 = 0 dB (−16…+16 dB, 0,5 dB) |
| `12` | Limiter threshold (båda kanaler) | 0 = OFF, 1–37 |
| `14` | Limiter release | 0–18, 0,5 s per steg |
| `15` | Noise gate (båda kanaler) | 0 = OFF, 1–47 (≈ −96…−44 dB) |
| `19` | Delay på/av | 0 / 1 |
| `1A` | Delay tid/avstånd `1A s0 xx yy zz` | `s` = kanal. 3-byte-räknare, `zz` minst signifikant |
| `1E` | **PEQ-läge** `1E sb xx` | `xx`: 0 OFF, 1 PAR, 2 AUT, 3 SGL |
| `1F` | **PEQ-frekvens** `1F sb yy xx` | `yy` = intervall: 0 (20–87 Hz), 1 (88–379 Hz), 2 (383 Hz–1,66 kHz), 3 (1,68–7,24 kHz), 4 (7,32–20 kHz, här `xx` max `58h`). `xx` = 0–127 (icke-linjärt) |
| `20` | **PEQ-oktav (bandbredd)** `20 sb xx` | `xx` = 0–120 (1/60…120/60 oktav) |
| `21` | **PEQ-gain** `21 sb 00 xx` | `xx` = 0–127 (−48…+16 dB, 0,5 dB) |
| `23` | Crossfade-tid | 0–15 sek |
| `24` | Shelving slope | 0–10, 3 dB/oktav per steg |

### SEND – RTA

| Kmd | Funktion | Data |
|---|---|---|
| `25` | RTA sampling | 2 = 44,1 kHz, 3 = 48 kHz |
| `28` | RTA input | 0 MICRO, 1 L, 2 R, 3 L+R |
| `29` | RTA hold | 0/1 |
| `2A` | RTA upplösning | 0 = 1 dB/pix, 1 = 0,5 dB/pix |
| `2B` | RTA auto gain | 0 = manuell, 1 = auto |
| `2C` | RTA line gain | 0–16 (0–60 dB, 4 dB-steg) |
| `2D` | RTA mic gain | 0–16 (0–60 dB, 4 dB-steg) |
| `2E` | RTA mic correction `…2E yy xx F7` | 2-byte-räknare 0–200 (100/kanal) |
| `2F` | RTA mode | 0 RMS, 1 Peak |
| `30` | RTA decay | 0 = 15 ms, 1 = 65 ms, 2 = 250 ms, 3 = 1,0 s |
| `31` | RTA Q-curve | 0 = Flat, 1–100 |
| `32` | RTA output (generator) | 0 OFF, 1 Input, 2 Sine, 3 White, 4 Pink |
| `33` | RTA sine-frekvens `…33 yy xx F7` | 2-byte-räknare |
| `34` | RTA generatornivå | 0–48 |

### SEND – skriv helt program

**`46 mm` – skriv till minnesplats** `mm` = 0–63h:
header + `2× delay tid` + `62× frekvensnivå` + `2× master` + `6× PEQ-läge` +
`6× PEQ-frekvens` + `6× PEQ-oktav` + `6× PEQ-gain` + namn.

**`46 7F` – skriv arbets-/temp-minne** (EQ + RTA): som ovan men med
limiter threshold/release/noise först, och PEQ-parametrarna grupperade per
band (läge, frekvens, oktav, gain × 6), följt av *alla* RTA-inställningar,
crossfade, shelving slope, namn.

**Namnfält** `3C aa×12` – `aa` är index i teckentabellen:

```
(space) ! " # $ % & ' ( ) * + , - . /
0 1 2 3 4 5 6 7 8 9 : ; < = > ?
@ A B C D E F G H I J K L M N O
P Q R S T U V W X Y Z [ \ ] ^ _
` a b c d e f g h i j k l m n o
p q r s t u v x y z { / | } ~ (space)
Ç ü é â ä à â ç ê ë è ï î ì Ä Â
É . . ô ö ò û ù ÿ Ö Ü . . . . .
```

### REQUEST / READ (ADRStudio, DSP8024 – vår DSP8000 svarar bara med dumpen)

| Sträng | Ger |
|---|---|
| `F0 00 20 32 00 0E 70 <param> F7` | `F0 00 20 32 00 0E <param> <värde> F7` |
| `… 70 15 70 11 20 F7` | kedjad förfrågan (noise threshold + hö master) |
| **`F0 00 20 32 7F 0E 70 10 1F F7`** | **alla 31 vänster GEQ-band** (`3F` = höger). Master hämtas separat |
| `F0 00 20 32 7F 0E 70 64 F7` | realtids **EQ-meter** (endast i EQ-läge) |
| `F0 00 20 32 7F 0E 70 65 F7` | realtids **RTA-display** (endast i RTA-läge): header + line gain + mic gain + decay + statusflaggor `xxMFAGHR` + 31 par + master-par + `F7`. Andra byten i varje par = position 0–7F (7F = mitten); över mitten sätts första byten till 1 |
| `F0 00 20 32 00 0E 70 46 mm F7` | läs minnesplats `mm` (0–63h) |
| `F0 00 20 32 00 0E 70 46 7F F7` | läs arbetsminne |
| `F0 00 20 32 7F 0E 70 01 F7` | **systemversion** (read-only) |

Statusflaggor i `65h`-svaret (`xxMFAGHR`):
`R` upplösning (1 dB=0 / 0,5 dB=1) · `H` hold · `G` auto gain · `A` analyzer (RMS=0/Peak=1) ·
`F` = 1 när RTA-displayen är fryst · `M` = 1 i memory/load-läge.

### Exempel (ADRStudio)

Nolla alla vänster-band + master samtidigt:
```
F0 00 20 32 00 0E 10 00 20 10 01 20 … 10 1E 20 11 00 20 11 20 20 F7
```
Synka båda masterfaders:
```
F0 00 20 32 00 0E 11 00 xx 11 20 xx F7
```

---

## 7. Memory dump (`SND MEMORY DUMP`)

- Utlöses från MIDI SETUP-sidan med `+/–`. Skickar hela minnet på MIDI OUT,
  kan spelas in i en sekvenser och laddas tillbaka med `RCV MEMORY DUMP`.
- **Testenhetens dump:** 12110 byte (payload). Header 10 byte
  `00 20 32 00 01 4F <sub> 20 00` (`4F` = dump; `sub` = `12` från knappen,
  `0A` från `70`-förfrågan), sedan 12100 databyte, alla < 128 men
  **bit-packat**. 12100 = 100 × 121 går jämnt ut, men en signatur upprepas
  med delta 160 (inte 121) → "100 × 121"-blockhypotesen är **inte**
  bekräftad. ~95 % nollor i de committade dumparna (nästan tom enhet).
- **Samma dump via SysEx-förfrågan** (`F0 00 20 32 00 01 70 xx F7`, se
  avsnitt 10) men med sub-kod `4F 0A` istället för `4F 12`. Skiljer sig
  annars bara på ~84 byte i header + första programblocket; de 100 sparade
  programmen är bit-identiska. Sparad: `dsp8000_sysex_ondemand.syx`.
- **GEQ-bandformatet avkodat** (`rew_to_dsp8000.py probe`, verifierat mot
  enheten 2026-09-02, se `syx_tools.py`): databyten packas upp **MSB-först**
  till en bitström; från **bit-offset 373** ligger **64 tecknade
  8-bitarsvärden** — 31 vä band, vä master, 31 hö band, hö master. Bandvärde
  = **CC − 64** (kvarts-dB, `dB = värde/4`, −16,00…+15,75). Samma för `4F 0A`
  och `4F 12`. Den tidigare "8 byte/band med bitvikter"-tolkningen var fel.
  PEQ/delay/master-skala/de 100 programmen är **inte** kartlagda.
- Den **läsbara** GEQ-statusframen (skickas vid fader-rörelse, inte på
  begäran): `F0 00 20 32 00 01 33 09 <32 vä> <32 hö> F7`, position 0–30 =
  band, 31 = master, `64` (0x40) = 0 dB.
- Ingen officiell dokumentation av dump-formatet finns (Behringer lämnar
  inte ut det). ADRStudio-listan (avsnitt 6) gäller DSP8024:s granulära
  realtidskommandon, inte den packade dumpen.

---

## 8. PC-editor: EQ-Design / "UltraCurve Design"

Uppgifterna nedan kommer från **sökträffar** (manualslib, freedownloadmanager,
software.informer, forumtrådar) – **ej förstahandsverifierat**, mjukvaran är
inte testad i det här projektet.

- Gratis Windows-program (uppges 32-bit, Win9x, ~486DX2-66 / 32 MB, MIDI-interface).
- **OS-krav (uppges):** DSP8000 OS ≥ V2.0, DSP8024 OS ≥ V1.1.
- Kommunicerar via **SysEx** (kräver `EXCL` på).
- **Inte längre nedladdningsbart från behringer.com.** Finns på
  tredjepartssidor och i Audiofanzine/diyAudio-trådar – används på egen risk.
- Givet testet i avsnitt 10 (DSP8000 svarar bara med hela dumpen) pratar
  mjukvaran troligen just `4F`-dump fram och tillbaka med vår enhet – den
  skulle alltså inte ge något som CC-vägen + REW inte redan ger.
- ADRStudio har även en **StudioWare-panel för Cakewalk/Sonar** (avsnitt 9).

---

## 9. StudioWare-panel för Cakewalk/Sonar (ADRStudio)

Styr GEQ, parametrisk EQ, RTA, limiter och noise threshold från en panel i
Cakewalk/Sonar. Setup:

**På DSP8024:** aktivera `EXCL SND` + `RCV` (panelen kör bara SysEx),
**avaktivera `CNTL SND` + `RCV`** (annars kan controller-ekon nolla
inställningar), notera MIDI-kanalen.

**I Cakewalk/Sonar:** eget spår för DSP8024, sätt spårets MIDI-utport mot
enheten, sätt spårets MIDI-kanal = enhetens, ladda panelen, välj spårnummer
via CONFIG. Panelen är gjord för minst 1024×768, Windows XP. Spara som
bundle med backup; testa i tomt projekt först.

---

## 10. Relevans för projektet – vad testet gav

Kört `rew_to_dsp8000.py sysex` mot enheten 2026-09-02 (AudioBox USB, båda
kablarna, MIDI ON, EXCL SND+RCV ON, enheten på EQ-huvudskärmen).

### Resultat

| Förfrågan | Svar |
|---|---|
| `F0 00 20 32 00 01 70 01 F7` (version) | **12110-byte packad dump** efter ~5 s |
| `F0 00 20 32 00 01 70 10 1F F7` (läs vä band) | samma 12110-byte dump |
| `F0 00 20 32 00 01 70 64 F7` (EQ-meter) | samma 12110-byte dump |
| `F0 00 20 32 00 0E …` (modellbyte 0E / 7F 0E) | **inget svar** |

- Dumpen (`F0 00 20 32 00 01 **4F 0A** …`) är identisk med `SND MEMORY
  DUMP` (`4F 12`) sånär som på **84 byte**, alla i fil-offset 7–218
  (sub-koden + de första ~200 databytena, troligen arbetsprogrammet).
  Resten – dvs. i praktiken alla 100 sparade program – är **bit för bit
  lika**. Sparad: `dsp8000_sysex_ondemand.syx`.
- Alltså: **DSP8000:s enda SysEx-svar är hela minnesdumpen.** Ingen
  granulär läsning, ingen systemversion-sträng.
- **Realtidsskrivning `10h` testad 2026-09-02** (skicka `10 11 30`, dumpa,
  avkoda GEQ): dumpen ändras **inte** – varken modellbyte `01` eller `0E`.
  ADRStudio:s `1F`/`20`/`21` (PEQ) lär vara lika döda. Att läsa/skriva PEQ
  kräver alltså den packade dumpen; `probe --manual` kartlägger den.

### Vad vi faktiskt vann

1. **Dump på begäran utan fader-nudge + GEQ-återläsning.**
   `F0 00 20 32 00 01 70 01 F7` → full dump. GEQ-blocket är nu **avkodat**
   (bit-offset 373, 64 × 8-bit tecknat, `dB = v/4` – avsnitt 7), så
   `rew_to_dsp8000.py send --verify` hämtar dumpen efter en CC-skrivning och
   rapporterar band som inte landade – utan REW-sweep. `readback` läser ut
   nuläget, `probe` gör kontrollerade captures. En REW-sweep behövs
   fortfarande för det **akustiska** resultatet, inte för att se vad enheten
   tog emot.
2. **Bekräftat att returvägen fungerar stabilt** med båda kablarna i.

### Vad som är dödt

- Realtids-PEQ via MIDI: nej (varken CC eller SysEx på denna enhet – `10h`
  testad och död). PEQ kan bara läsas ur den packade dumpen (ej kartlagd
  än – `probe --manual`) eller ställas för hand + sparas som program.
- Granulär GEQ-läsning: nej – men hela dumpen kan hämtas på begäran och
  GEQ-banden avkodas ur den (avsnitt 7), vilket räcker för `send --verify`.
- EQ-Design-mjukvaran skulle möjligen prata med enheten (den använder
  troligen just `4F`-dumpen fram och tillbaka), men mjukvaran är svår att
  få tag på och tillför inget som CC-vägen + REW inte redan ger.

### Skrivning (CC) står sig

CC-vägen (`CC = 64 + dB×4`, offset 0, `rew_to_dsp8000.py send`) är
fortfarande den enda fungerande skrivvägen och är redan verifierad.
Kör `sysex --write-test` om du vill prova ADRStudio:s `10 sr xx`-skrivning
ändå (återställer själv), men förvänta inget.

---

## 11. Källor

### Manualer (primärkällor)

- **DSP8000 User Manual V1.3 (juli 1996)** –
  [archive.org: behringer-ultra-curve-dsp-8000-user-manual-ver-1-3](https://archive.org/details/behringer-ultra-curve-dsp-8000-user-manual-ver-1-3)
  (OCR-text via `..._djvu.txt`). Speglar:
  [behringer-vintage.com PDF](http://www.behringer-vintage.com/Anleitungen/DSP8000_V1.3_1996_ENG.pdf),
  [usedstage.ru PDF](http://usedstage.ru/wp-content/uploads/2019/08/DSP8000_man.pdf).
  → äldre MIDI-implementation (fast CC 64–127, ingen SysEx).
- **DSP8024 PRO – tysk manual v1.2 (juni 2001)** –
  [tonkreis.de PDF](http://www.tonkreis.de/D%20A%20T/Bedienungsanleitungen/Behringer%20ULTRA%20CURVE%20-%20DSP%208000.pdf)
  (filnamnet säger 8000, innehållet är DSP8024; **textbaserad PDF** – bäst
  källa för MIDI SETUP-fälten och Tab 7.1/7.2).
- **DSP8024 PRO – engelsk manual** –
  [archive.org: manualzilla-id-7376194](https://archive.org/details/manualzilla-id-7376194)
  (OCR), även [manualslib.com/manual/15059](https://www.manualslib.com/manual/15059/Behringer-Ultra-Curve-Pro-Dsp8024.html).

### SysEx-protokoll & mjukvara

- **ADRStudio – "SysEx Commands for Behringer Ultra Curve Pro DSP 8024"**,
  Adriano Ficarelli Jr, rev 14 (2006):
  [adrstudio.com/8024.php](https://adrstudio.com/8024.php) ·
  [PDF](https://adrstudio.com/pdf/DSP8024-SYSEX-v13.pdf).
  Reverse-engineerat, gäller DSP8024 – **fungerar inte på vår DSP8000** (avsnitt 10).
- **ADRStudio – "DSP-8024 StudioWare panel for Cakewalk and Sonar"**:
  [adrstudio.com/studioware.php](https://adrstudio.com/studioware.php).
- **EQ-Design / UltraCurve Design** (ej förstahandsverifierat) –
  [freedownloadmanager.org](https://en.freedownloadmanager.org/Windows-PC/ULTRA-CURVE-Design-for-DSP8024-FREE.html),
  [manualslib s.33](https://www.manualslib.com/manual/15059/Behringer-Ultra-Curve-Pro-Dsp8024.html?page=33).

### Recension & community

- **Sound on Sound** – [Behringer Ultra-curve review](https://www.soundonsound.com/reviews/behringer-ultra-curve)
  (1996-modellen; "no data output over MIDI" gällde det gamla OS:et).
- diyAudio: [DSP8000 PC software](https://www.diyaudio.com/community/threads/behringer-dsp8000-download-pc-software.399835/),
  [DSP8024 midi software](https://www.diyaudio.com/community/threads/req-behringer-ultracurve-dsp8024-midi-software.356917/)
  (blockerar direkthämtning – lästa via sökträffar).
- [audiosex.pro-tråd](https://audiosex.pro/threads/behringer-ultracurve-dsp8024-midi-software.54478/),
  gearspace ([DSP8024-problem](https://gearspace.com/board/live-sound/907547-problem-behringer-ultra-curve-pro-dsp8024.html),
  [DSP8000-tråd](https://gearspace.com/threads/behringer-ultra-curve-dsp8000-vs.1296171/)),
  Audiofanzine (fransk + engelsk), hometheatershack.
- **Keith Neufeld's Electronics Blog** – "Installing a Behringer DSP8024
  Equalizer and Upgrading Firmware"
  ([neufeld.newton.ks.us/electronics/?p=575](http://www.neufeld.newton.ks.us/electronics/?p=575);
  sparad Wayback-kopia i `docs/keiths-blog-dsp8024-firmware-upgrade.html`):
  DSP8024-firmware 1.1→1.3 låg som EPROM-image (27C256) på behringer.com;
  Auto-Q-arbetsgång; hiss + kraftig pop vid på/avslag – slå på EQ:n före
  slutsteget. Gäller **DSP8024**, inte DSP8000.
