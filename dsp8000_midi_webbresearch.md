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

1. **Tre olika MIDI-implementationer finns**, beroende på operativsystem:
   - **DSP8000 OS < 2.0** (manual V1.3, 1996): fast CC-mappning **64–127**,
     `MIDI OUT` "har ingen funktion", **ingen SysEx**, ingen memory dump-sida.
   - **DSP8000 OS ≥ 2.0** och **DSP8024 OS ≥ 1.1**: justerbar
     **Controller Offset 0–64**, `MIDI OUT` skickar programdata + status,
     **SysEx skickas och tas emot**, `SND/RCV MEMORY DUMP` på MIDI-sidan,
     fungerar med EQ-Design-mjukvaran. **Detta matchar testenheten.**
   - **DSP8024** har dessutom ett fullständigt realtids-SysEx-protokoll
     (reverse-engineerat av ADRStudio, se avsnitt 6) som når limiter, gate,
     delay, parametriska filter och hela RTA-sektionen – långt mer än CC.

2. **CC-mappning (offset 0):** `CC 0–30` = vänster GEQ 20 Hz…20 kHz,
   `CC 31` = vänster master, `CC 32–62` = höger GEQ, `CC 63` = höger master.
   Datavärde `0–127`. Med offset N adderas N till alla nummer.
   Testenheten kör offset 0 → stämmer med `dsp8000.py`.

3. **SysEx-header:** `F0 00 20 32 <dd> <mm> <cmd…> F7`.
   `00 20 32` = Behringers manufacturer-ID. `dd` = device (00 = adresserad,
   7F = broadcast). `mm` = **modell-ID: `0E` = DSP8024, `01` = DSP8000**
   (enligt våra egna captures – ADRStudio:s lista använder genomgående `0E`).
   → ADRStudio:s DSP8024-kommandon är värda att prova mot DSP8000 med `0E`
   utbytt mot `01`.

4. **Störst nytta för projektet** (se avsnitt 10): ADRStudio dokumenterar
   `F0 00 20 32 7F 0E 70 10 1F F7` = "läs alla 31 vänster-band" **utan
   fader-nudge**, plus realtidsskrivning av parametriska filter. Om samma
   sak funkar med `01` slipper vi både den packade dumpen och fader-nudgen.

---

## 1. Modellskillnader (MIDI-relevanta)

| | DSP8000 (V1.3, 1996) | DSP8000 OS ≥ 2.0 / DSP8024 |
|---|---|---|
| AD/DA | 20-bit | 24-bit (8024) |
| Parametriska filter | 3 per kanal (6 tot.) | 3 per kanal (6 tot.) |
| GEQ | 31-band 1/3-oktav, ±16 dB / 0,5 dB-steg | samma |
| MIDI-kanal | OFF, ALL, 1–16 | OFF, ALL (Omni), 1–16 |
| Controller offset | **fast** (motsvarar offset 64) | **justerbar 0–64** |
| MIDI OUT | "ingen funktion ännu" | skickar programdata + status |
| SysEx | **nej** (chart: X/X) | **ja** (chart: O/O) |
| Memory dump-sida | finns ej | `SND/RCV MEMORY DUMP` |
| PC-editor | – | EQ-Design / UltraCurve Design |

> Sound on Sound-recensionen (av 1996-modellen) skrev *"no data is output
> over MIDI, so there is no way to store SysEx dumps"*. Det gäller det
> gamla OS:et – testenheten dumpar (12110 byte), alltså nyare firmware.

**Kolla enhetens OS-version:** visas kort i displayen direkt efter påslag.
Firmware kunde bara uppdateras genom att skicka in enheten till Behringer
(EPROM-byte).

---

## 2. Fysisk MIDI-anslutning

- 3× 5-pol DIN (IN / OUT / THRU) på baksidan. Optokopplad, potentialfri.
- Standard MIDI-kabel: Pin 2 = skärm, Pin 4 + 5 = ledare, Pin 1 + 3 oanvända.
- Max kabellängd 15 m (45 ft).
- **MIDI IN:** tar emot Program Change, Controller och (nyare OS) SysEx.
- **MIDI THRU:** oförändrad genomsläppning – flera enheter kan kedjas.
- **MIDI OUT (nyare OS):** skickar programdata + statusinfo till dator eller
  till andra Ultra-Curve (master/slave). På 1996-modellen: inaktiv.

Retursväg fungerar på testenheten först när **båda** kablarna sitter i
(IN och OUT) – se `readme.md`.

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
| **CNTL** | Controller-data sänds/tas emot. Talet = **första controller-numret** (offset). "De följande 64 numren är frekvenserna 20 Hz–20 kHz + master, först vänster sedan höger kanal." | RCV / SND, offset **0–64** |
| **PROG** | Program Change sänds/tas emot | RCV ON/OFF, SND ON/OFF |
| **EXCL** | System Exclusive sänds/tas emot. Krävs för EQ-Design-mjukvaran ("alla parametrar och funktioner fjärrbedienbara") | RCV ON/OFF, SND ON/OFF |

> `CNTL` är **inte** ON/OFF utan ett **tal** (offset). RCV och SND har
> varsitt. Testenheten: `RCV = 0`, `SND = 1`. `dsp8000.CC_OFFSET` måste = `RCV`.

**Rekommenderad inställning för CC-styrning (verifierad i `readme.md`):**
MIDI ON · CHANNEL 1 · OMNI ON · CNTL RCV 0 / SND 1 · PROG RCV+SND ON ·
EXCL RCV+SND ON.

**För SysEx-styrning (ADRStudio / StudioWare):** slå på `EXCL SND` + `RCV`,
och slå **av `CNTL SND` + `RCV`** så att inte controller-ekon nollställer
inställningar av misstag.

### GLOBAL SETUP (sida 1) – övrigt värt att känna till

| Fält | Värden |
|---|---|
| INPUT | Analog / Digital (AES/EBU-option). I analogläge väljs samplingsfrekvens här: **44,1 / 48 kHz** (32 kHz endast via AES/EBU). Byte av frekvens mutar ~1 sek. |
| VIEWING ANGLE | LCD-kontrast 0–31 (även SETUP + Cursor upp/ned) |
| RTA LOCK | spärr mot att gå in i RTA-läge |
| SECURITY | UNLOCK / LOCK med lösenord. LOCK: allt spärrat utom EQ-display och level meter – *"enda sättet att ändra är via MIDI"* |
| PROTECT MEM | skrivskydd för programminne, med EQ LO/HI och RTA LO/HI som gräns |

Glömt lösenord → batteriet ut en stund → **alla program raderas**.

---

## 4. MIDI Implementation Chart (Tab. 7.1, DSP8024 / DSP8000 nyare OS)

```
Function            Transmitted   Recognized   Remarks
Basic  Default          X          1-16        memorized
Channel Changed         X          1-16
Mode   Default          X          1,2,3,4
       Messages         X          X
Note Number             X          X
Velocity                X          X
Aftertouch              X          X
Pitch Bender            X          X
Control Change          O          O           offset of the first controller adjustable (se Tab 7.2)
Program Change          0-99       0-99        True # 1-100
System Exclusive        O          O
System Common / RT      X          X
Aux Messages            X          X

O = YES   X = NO
Mode 1: OMNI ON, POLY    Mode 3: OMNI OFF, POLY
Mode 2: OMNI ON, MONO    Mode 4: OMNI OFF, MONO
```

**1996 DSP8000 V1.3-charten skiljer sig:** `System Exclusive` = `X / X`
(inget stöd), och Control Change står som fast **64–94** (vä EQ) /
**95** (vä master) / **96–126** (hö EQ) / **127** (hö master).

---

## 5. Controller-implementation (Tab. 7.2) + Program Change

### Status bytes

```
Program Change:  Cc xx      c = kanal,  xx = program 0..99
Controller:      Bc nn vv   c = kanal,  nn = controllernr,  vv = värde
                 Controller Offset justerbar 0–64  (adderas till nn)
```

### Data bytes (offset = 0)

| Contrl.-nr | Parameter | Definition | Range |
|---|---|---|---|
| **0–30** | EQ Left | 20 Hz, 25 Hz, …, 16 kHz, 20 kHz (31 ISO-band) | 0–127 |
| **31** | Master Level Left | | 0–127 |
| **32–62** | EQ Right | 20 Hz, 25 Hz, …, 16 kHz, 20 kHz | 0–127 |
| **63** | Master Level Right | | 0–127 |

- Med **offset N**: lägg till N på alla nummer. Gamla DSP8000 = fast offset 64.
- **Värdeskala GEQ via CC:** 0–127, mitt = 64 = 0 dB. Projektet har
  kalibrerat **`CC = 64 + dB × 4`** mot displayen (0,25 dB/steg nominellt,
  enheten rundar till 0,5). ±16 dB ⇒ teoretiskt 0…128, klipps vid 127.
- **Program Change:** 0–99 sänds/tas emot (displayen visar 1–100).
- **31 ISO-frekvenser:** 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200,
  250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000,
  5000, 6300, 8000, 10000, 12500, 16000, 20000 Hz.

### PEQ-regelområde (från 1996-manualens tyska text / midi_captures)
GEQ: +16…−16 dB i 0,5 dB-steg. **PEQ: +16…−48 dB i 0,5 dB-steg.**
PEQ går **inte** via CC – bara via SysEx (avsnitt 6) eller "ställ för
hand → spara program → Program Change".

---

## 6. Realtids-SysEx-protokoll (DSP8024)

Reverse-engineerat av **Adriano Ficarelli Jr, ADRStudio.com** (rev 14,
2006) genom att sniffa trafiken mellan EQ-Design och enheten. Behringer
publicerade aldrig detta.

> **Testat mot vår DSP8000 2026-09-02 – funkar INTE som beskrivet.**
> Modellbyte `0E` (DSP8024) ignoreras helt. Med `01` svarar enheten på
> *varje* `70`-förfrågan (`70 01`, `70 10 1F`, `70 64` …) med samma sak:
> hela den packade 12110-byte-dumpen (`F0 00 20 32 00 01 4F 0A …`),
> ~5 s efter förfrågan. Ingen av de granulära läsningarna eller
> realtidsskrivningarna nedan gav något gensvar. DSP8000:s OS har alltså
> en mycket enklare SysEx-hanterare än DSP8024. Behåll listan som
> DSP8024-referens.

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

### SEND – Equalizer

| Kmd | Funktion | Data |
|---|---|---|
| `10` | **GEQ frekvensnivå** `F0…0E 10 sr xx F7` | `sr` = `00`–`1E` vänster band, `20`–`3E` höger band (00 = 20 Hz, 01 = 25 Hz, …). `xx` = 0–64, **`20`h (32) = 0 dB** |
| `11` | **Master volym** `…11 s0 xx F7` | `s` = 0 vä / 2 hö. `xx` = 0–64, `20`h = 0 dB (−16…+16 dB, 0,5 dB) |
| `12` | Limiter threshold (båda kanaler) | `00` = OFF, `01`–`37` = −dB |
| `14` | Limiter release | `00`–`18`, 0,5 s per steg |
| `15` | Noise gate (båda kanaler) | `00` = OFF, `01`–`2F` (−96…−44 dB) |
| `19` | Delay på/av | `00` / `01` |
| `1A` | Delay tid/avstånd `…1A s0 xx yy zz F7` | `s` = kanal. 3-byte-räknare, `zz` minst signifikant |
| `1E` | **PEQ-läge** `…1E sb xx F7` | `s` = 0 vä / 2 hö, `b` = band 0–2. `xx`: 0 OFF, 1 PAR, 2 AUT, 3 SGL |
| `1F` | **PEQ-frekvens** `…1F sb yy xx F7` | `yy` = band: 00 (20–87 Hz), 01 (88–378 Hz), 02 (383 Hz–1.66 kHz), 03 (1.68–7.235 kHz), 04 (7.32–20 kHz). `xx` = 0–127 (icke-linjärt) |
| `20` | **PEQ-oktav (bandbredd)** `…20 sb xx F7` | `xx` = 0–120 (1/60…120/60 oktav) |
| `21` | **PEQ-gain** `…21 sb 00 xx F7` | `xx` = 0–127 (−48…+16 dB, 0,5 dB) |
| `23` | Crossfade-tid | `00`–`0F` sek |
| `24` | Shelving slope | `00`–`0A`, 3 dB/oktav per steg |

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

### REQUEST / READ

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
- **Testenhetens dump:** 12110 byte. Header 10 byte
  `00 20 32 00 01 4F 12 00 20 00`, sedan 100 program × 121 byte,
  **bit-packat / proprietärt**. `readme.md`/`midi_captures.txt` har knäckt
  GEQ-bandformatet (8 byte/band, bitvikter `[64,32,16,8,4,2,1]` + separator,
  värde = `(dB+16)×4`) men inte hela blocklayouten.
- Den **läsbara** GEQ-statusframen (vid fader-rörelse):
  `F0 00 20 32 00 01 33 09 <32 vä> <32 hö> F7`, position 0–30 = band,
  31 = master, `64` (0x40) = 0 dB.
- Ingen officiell dokumentation av dump-formatet existerar (Behringer
  lämnar inte ut det). ADRStudio-listan gäller realtidskommandon, inte
  den packade dumpen.

---

## 8. PC-editor: EQ-Design / "UltraCurve Design"

- **Gratis** Windows-program (32-bit, Win9x/XP), krävde IBM-PC ≥ 486DX2-66,
  32 MB RAM och ett MIDI-interface. Fullt MIDI-I/O.
- **OS-krav:** DSP8000 **OS ≥ V2.0**, DSP8024 **OS ≥ V1.1**.
- Kommunicerar via **SysEx** (kräver `EXCL` på).
- **Inte längre nedladdningsbart från behringer.com.** Finns kvar på
  tredjepartssidor (freedownloadmanager, software.informer m.fl.) och i
  Audiofanzine/diyAudio-trådar – används på egen risk.
- ADRStudio har även en **StudioWare-panel för Cakewalk/Sonar** som
  alternativ (avsnitt 9).

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

- Dumpen är `F0 00 20 32 00 01 **4F 0A** …` – identisk med `SND MEMORY
  DUMP` (`4F 12`) sånär som på **84 byte** i span offset 7–218 (header +
  working buffer). De 100 sparade programmen (offset 219→) är **bit för
  bit lika**. Sparad: `dsp8000_sysex_ondemand.syx`.
- Alltså: **DSP8000:s enda SysEx-svar är hela minnesdumpen.** Ingen
  granulär läsning, ingen systemversion-sträng, inga realtidsskrivningar
  (ADRStudio:s `10h`/`21h` osv. – oprövat men chanslöst givet att `0E`
  ignoreras och `01`+`70` bara dumpar).

### Vad vi faktiskt vann

1. **Dump på begäran utan fader-nudge.** `F0 00 20 32 00 01 70 01 F7` →
   full dump. `rew_to_dsp8000.py` skulle kunna hämta dumpen *efter* en
   CC-skrivning och jämföra GEQ-banden mot det skickade – men bara om det
   8-byte/band-packade GEQ-formatet (delvis knäckt i `midi_captures.txt`)
   avkodas helt. **Fortfarande sannolikt inte värt det** – en REW-sweep
   säger mer och är redan arbetsflödet.
2. **Bekräftat att returvägen fungerar stabilt** med båda kablarna i.

### Vad som är dödt

- Realtids-PEQ via MIDI: nej (varken CC eller SysEx på denna enhet).
- Granulär GEQ-läsning: nej.
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

- **DSP8000 User Manual Ver. 1.3 (juli 1996)** – archive.org, item
  `behringer-ultra-curve-dsp-8000-user-manual-ver-1-3`
  (OCR-text: `…_djvu.txt`). Även `behringer-vintage.com/Anleitungen/DSP8000_V1.3_1996_ENG.pdf`
  och `usedstage.ru/wp-content/uploads/2019/08/DSP8000_man.pdf`.
- **DSP8024 PRO Bedienungsanleitung, Version 1.2 (juni 2001, tyska)** –
  `tonkreis.de` … `Behringer ULTRA CURVE - DSP 8000.pdf` (innehållet är
  DSP8024, textbaserad PDF – bäst källa för MIDI SETUP-fälten och Tab 7.1/7.2).
- **DSP8024 PRO User's Manual (engelska)** – archive.org
  `manualzilla-id-7376194` (`7376194_djvu.txt`); även manualslib.com/manual/15059.
- **ADRStudio.com – "SysEx Commands for Behringer Ultra Curve Pro DSP 8024"**
  (Adriano Ficarelli Jr, rev 14, 2006): <https://adrstudio.com/8024.php>
  (PDF: `adrstudio.com/pdf/DSP8024-SYSEX-v13.pdf`).
- **ADRStudio.com – "DSP-8024 StudioWare panel for Cakewalk and Sonar"**:
  <https://adrstudio.com/studioware.php>
- **Sound on Sound – Behringer Ultra-curve review**:
  <https://www.soundonsound.com/reviews/behringer-ultra-curve>
- **EQ-Design / UltraCurve Design (OS-krav V2.0 / V1.1)** – manualslib s.33,
  freedownloadmanager.org, software.informer.com, diyAudio-trådar
  (`behringer-dsp8000-download-pc-software.399835`,
  `req-behringer-ultracurve-dsp8024-midi-software.356917`).
- **Övrigt community**: gearspace ("Problem with Behringer ULTRA-CURVE PRO
  DSP8024", "behringer ultra curve dsp8000 vs"), audiosex.pro,
  Audiofanzine (fransk + engelsk), hometheatershack, Keith Neufeld's
  Electronics Blog ("Installing a Behringer DSP8024 Equalizer and Upgrading
  Firmware", `neufeld.newton.ks.us/electronics/?p=575` – sparad Wayback-kopia
  i `docs/keiths-blog-dsp8024-firmware-upgrade.html`: DSP8024-firmware
  1.1→1.3 låg som EPROM-image (27C256) på behringer.com; Auto-Q-arbetsgång;
  hiss + kraftig pop vid på/avslag – slå på EQ:n före slutsteget).
