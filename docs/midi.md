# DSP8000 – MIDI-referens

Allt som är känt om MIDI-kopplingen till Behringer Ultra-Curve **DSP8000**
(originalmodellen, med nyare OS än 1996-manualen beskriver). Det här dokumentet
ersätter den tidigare webbresearch-filen, readme:ns gamla MIDI-avsnitt och
slutsatserna i `midi_captures.txt` (som ligger kvar bredvid som rå labblogg).

**Verifierat mot enheten 2026-08-31 och 2026-09-02** med en PreSonus AudioBox
USB som MIDI-interface. Det som *inte* är testat står uttryckligen markerat.

---

## 0. Sammanfattning

| Vad | Riktning | Status |
|---|---|---|
| Program Change 0–99 → byt program | dator → DSP | **fungerar** |
| CC → grafisk EQ (31+31 band, 2 master) | dator → DSP | **fungerar** – `CC = 64 + dB×4`, CC-nummer = CNTL RCV-offset + 0…63 |
| CC ut vid fader-rörelse | DSP → dator | sett i capture (CC 17/49), ej systematiskt testat |
| SysEx-förfrågan `70 xx` → hela minnesdumpen | dator → DSP → dator | **fungerar** – 12110 byte efter ~5 s, utan att röra enheten |
| SND MEMORY DUMP (knapp) → hela minnesdumpen | DSP → dator | **fungerar** |
| Fader-rörelse → läsbar GEQ-status (`33 09`) | DSP → dator | **fungerar** |
| Läsa GEQ + PEQ ur dumpen | – | **avkodat** (`syx_tools.py eq`, `rew_to_dsp8000.py readback`) |
| RCV MEMORY DUMP (ladda en dump tillbaka) | dator → DSP | **ej testat** – se avsnitt 4, `rew_to_dsp8000.py push` |
| Skriva PEQ, delay, gate, limiter via MIDI | dator → DSP | **går inte** med CC eller ADRStudio-SysEx. Enda kandidaten är RCV MEMORY DUMP |
| ADRStudio:s granulära DSP8024-SysEx | – | **dött** på DSP8000 (bilaga A) |

Returvägen kräver **båda** MIDI-kablarna (interface OUT → DSP IN *och*
DSP OUT → interface IN). Enheten ekar inte mottagna CC.

---

## 1. Fysisk anslutning

- 3× 5-pol DIN på baksidan: **IN**, **OUT**, **THRU**. Optokopplad, potentialfri.
- Standardkabel (pin 4+5 ledare, pin 2 skärm). Max ~15 m.
- **IN** tar emot Program Change, Control Change och SysEx.
- **THRU** släpper igenom oförändrat – för kedjning av flera enheter.
- **OUT** skickar CC (fader-rörelse), Program Change och SysEx (dump, status).
  På 1996-OS:et var OUT inaktiv; vår enhet skickar.
- Testuppkoppling: AudioBox MIDI OUT → DSP8000 MIDI **IN** (inte THRU),
  DSP8000 MIDI OUT → AudioBox MIDI IN. Utan returkabeln kommer ingen dump.

---

## 2. MIDI SETUP-sidan

Håll **SETUP** > 2 s → bläddra till sida 2 (sida 1 = GLOBAL SETUP). Cursor
väljer fält, `+/–` ändrar.

| Fält | Testenheten | Betydelse |
|---|---|---|
| **MIDI** | ON | MIDI på/av |
| **CHANNEL** | 1 | Mottagningskanal 1–16, OFF, eller OMNI (alla) |
| **OMNI MODE** | ON | Ta emot på alla kanaler. Funkar även OFF om kanalen matchar |
| **CNTL** | RCV **0** / SND **1** | **Inte ON/OFF – ett tal.** Controller Offset 0–64, dvs. första CC-numret. RCV och SND har varsitt tal |
| **PROG** | RCV ON / SND ON | Program Change tas emot / skickas |
| **EXCL** | RCV ON / SND ON | System Exclusive tas emot / skickas |
| **SND MEMORY DUMP** | (knapp) | `+/–` skickar hela minnet på MIDI OUT |
| **RCV MEMORY DUMP** | (knapp) | `+/–` sätter enheten i mottagningsläge för en dump (ej testat) |

`dsp8000.CC_OFFSET` i koden måste vara lika med **CNTL RCV**-talet. Om du
sätter offset 64 får du 1996-manualens fasta mappning (CC 64–127).

### GLOBAL SETUP (sida 1), det som spelar roll här

| Fält | Not |
|---|---|
| INPUT | Analog / Digital (AES/EBU-kort). 44,1 / 48 kHz analogt. Byte mutar ~1 s |
| SECURITY | LOCK spärrar allt utom EQ-display + meter – MIDI är då enda sättet att ändra |
| PROTECT MEM | Skrivskydd för programminnet (relevant om RCV MEMORY DUMP ska skriva) |

---

## 3. Send och receive – vad varje RCV/SND-inställning styr

MIDI-sidan har tre par av RCV/SND (CNTL, PROG, EXCL) plus två dump-knappar.
Så här hänger de ihop, och vad som är verifierat:

| Inställning | Riktning | Effekt | Status |
|---|---|---|---|
| CNTL **RCV** = n | in | CC n…n+63 tolkas som GEQ-band/master (avsnitt 5) | **verifierad**: RCV 0, `CC 17 = 96` → display `L 1 kHz +8 dB` |
| CNTL **SND** = n | ut | Enheten skickar CC när en fader rörs | CC 17 och 49 sågs 2026-08-31 vid fader 1 kHz (dvs. offset 0). Om SND-talet verkligen flyttar de utgående numren är **inte** kontrollerat – SND stod på 1 vid senare test men ingen ny capture togs |
| PROG **RCV** | in | Program Change 0–99 byter program | **verifierad** (PC 1, 5, 10) |
| PROG **SND** | ut | Program Change skickas när man byter program på enheten | ej testad (bör synas i `monitor`) |
| EXCL **RCV** | in | Enheten tar emot SysEx | **verifierad**: `70`-förfrågan besvaras |
| EXCL **SND** | ut | Enheten skickar SysEx | **verifierad**: dump + fader-frame `33 09` |
| SND MEMORY DUMP | ut | Hela minnet som `4F 12`-dump | **verifierad** |
| RCV MEMORY DUMP | in | Laddar en dump från MIDI IN tillbaka i minnet | **ej testad** – avsnitt 4 |

Praktiskt: för skriptkedjan räcker `CNTL RCV = 0`, `PROG RCV ON`, `EXCL RCV +
SND ON`. `CNTL SND` behövs bara om du vill se fader-rörelser i `monitor`.
ADRStudio rekommenderar att stänga av CNTL SND/RCV när man bara kör SysEx så
att inte controller-ekon nollställer något – det problemet har vi inte sett.

---

## 4. RCV MEMORY DUMP – outrett, och varför det är intressant

**Vad manualen säger** (DSP8024-manualen, gäller nyare OS): dumpen från SND
MEMORY DUMP "kan spelas in i en sequencer och laddas tillbaka med RCV MEMORY
DUMP". Alltså en backup/restore-funktion för hela minnet.

**Varför det spelar roll:** allt som *inte* går att styra med CC – de 6
parametriska filtren, delay, gate, limiter, master-skalan och de 100 programmen
– ligger i dumpen. GEQ- och PEQ-blocken är avkodade (avsnitt 6.4). Om enheten
tar emot en dump och lägger in den i minnet kan vi **skriva PEQ via MIDI**
genom att hämta dumpen, patcha PEQ-bitarna och skicka tillbaka den. Det är den
enda kvarvarande vägen till fjärrstyrd PEQ på DSP8000.

**Öppna frågor:**

1. Tar enheten emot en `4F`-dump på MIDI IN överhuvudtaget bara för att EXCL
   RCV är ON, eller måste man trycka `+` på RCV MEMORY DUMP först?
2. Vilken sub-kod accepteras: `4F 12 00` (som knappen skickar) eller
   `4F 0A 40` (som förfrågan ger)? Se avsnitt 6.3.
3. Finns en checksumma? De 9 bytena vid data-offset 39–47 (och igen vid
   199–207) är satta i `4F 12`-dumparna men noll i `4F 0A` – kan vara
   namn, checksumma eller flaggor.
4. Hamnar dumpen i arbetsbufferten (syns direkt på displayen) eller bara i
   de 100 programplatserna (syns först efter Program Change)?
5. Måste enheten stå på EQ-huvudskärmen (som för förfrågan)?
6. Blockerar PROTECT MEM?

**Testprotokoll** – `./run.sh push FIL.syx` visar en checklista (Enter), tar
före-dumpen, väntar på `ja` när enheten är i rätt läge, skickar filen, väntar
6 s (12 kB @ 31 250 baud ≈ 4 s), tar efter-dumpen och diffar. Uteblivet svar
ger "Enter = försök igen", inte avbrott. Före-dumpen sparas alltid som
`probe_push_before_<tid>.syx` (återställningspunkt).

*Förkrav:* båda MIDI-kablarna i, MIDI ON, EXCL RCV + SND ON, PROTECT MEM av,
enheten på EQ-huvudskärmen. Extra backup först: `./run.sh grab dumps/backup.syx`.

| Steg | Gör | Tolkning |
|---|---|---|
| 0 | **Pre-flight utan enheten:** koppla interface OUT → interface IN. Fönster 1: `./run.sh monitor --seconds 90`. Fönster 2: `./run.sh push --send-only dumps/dsp8000_sysex_p16db.syx` | `monitor` ska rapportera **en SysEx på 12110 byte**. Kortare eller ingen = interfacet tappar långa SysEx, och inget nedan säger då något om enheten |
| 1 | `./run.sh readback` | Notera GEQ-läget. Står allt redan på +16 dB: ställ om något band så förändringen syns |
| 2 | `./run.sh push dumps/dsp8000_sysex_p16db.syx`: Enter vid checklistan, före-dumpen tas, tryck **inte** på enheten, svara `ja` | **A:** diffen visar GEQ → +16 och displayen visar +16: enheten tar emot dumpar spontant, EXCL RCV räcker. **B:** "Ingen byte ändrades": gå till 3. **C:** "Andra dumpen kom inte": enheten bytte läge – kolla displayen, tryck OK/EQ, kör `readback` |
| 3 | Samma, men tryck `+` på **RCV MEMORY DUMP** innan du svarar `ja` | Som ovan. Notera vad displayen visar efter `+` (väntar den? timeout?) |
| 4 | Inget i 2–3: `./run.sh push dumps/dsp8000_sysex_ondemand.syx` (förfrågnings-format `4F 0A 40`), utan och med knappen | Innehållet är en annan kurva (inte +16), så diffen blir stor om det tar |
| 5 | Ändrades dumpen men inte displayen: Program Change till aktuellt program, sedan `./run.sh readback` | Skiljer på arbetsbuffert (syns direkt) och programminne (syns efter PC) |
| 6 | Återställ: `./run.sh push probe_push_before_<tid>.syx` (eller ställ tillbaka för hand), sedan `./run.sh readback` | |

Anteckna i testloggen (avsnitt 7): vilket steg som gav effekt, knapp eller
inte, vilket format, och om det landade i arbetsbufferten eller programminnet.

**Om det fungerar:** nästa steg är ett `syx_tools.py`-kommando som patchar en
PEQ-post (och GEQ) in i en dump – då kan PEQ skrivas via MIDI. Bygg det först
då; vad som måste patchas (header, mönstret vid data 39–47) beror på svaren
på frågorna 2–4.

**Risk:** en mottagen dump kan skriva över arbetsbufferten och de 100
programmen. Använd bara dumpar från samma enhet. Testenheten är nästan tom
(~95 % nollor), så förlusten är liten – men ta backupen först.

---

## 5. Control Change (grafisk EQ)

```
Control Change:  Bn cc vv    n = kanal 0–F, cc = offset + nummer nedan, vv = 0–127
Program Change:  Cn pp       pp = program 0–99 (displayen visar 1–100)
```

| Nummer (offset 0) | Styr |
|---|---|
| 0–30 | vänster 31 band: 20 Hz = 0, 1 kHz = 17, 20 kHz = 30 |
| 31 | vänster master |
| 32–62 | höger 31 band |
| 63 | höger master |

**Värdeskala (verifierad):** `CC = 64 + dB × 4` → 64 = 0 dB, 96 = +8 dB,
0 = −16 dB, 127 = +15,75 dB (+16 vore 128, klipps). Nominellt 0,25 dB/steg,
men GEQ:n har 0,5 dB-upplösning så enheten rundar. `dsp8000.db_to_cc` /
`cc_to_db` implementerar detta.

**Master-fadern** tar CC 0–127 men skalan är inte verifierad (troligen samma).

**Stereolink** på enheten: då räcker vänsterkanalen (`send --channel left`).
Med Stereolink av skickar `send` båda (default).

**Timing:** enheten tappar CC om 62 stycken kommer i en klump. `send` pausar
20 ms mellan meddelanden, GUI:t 3 ms. `send --verify` läser tillbaka och
rapporterar band som inte landade.

**31 ISO-band:** 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315,
400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300,
8000, 10000, 12500, 16000, 20000 Hz.

---

## 6. SysEx

### 6.1 Header och modellbyte

```
F0 00 20 32 <dev> <model> <cmd …> F7
```

`00 20 32` = Behringers manufacturer-ID. `dev` = `00` (adresserad) eller `7F`
(broadcast). `model` = **`01` = DSP8000**. `0E` (DSP8024, som ADRStudio
använder) ignoreras helt av vår enhet.

### 6.2 Förfrågan → dump

```
F0 00 20 32 00 01 70 <xx> F7
```

Oavsett `xx` (`01`, `10 1F`, `64` – allt testat) svarar enheten efter ~5 s
med **hela minnesdumpen**. Det finns ingen granulär läsning och ingen
versionssträng. Enheten måste stå på EQ-huvudskärmen. Förfrågan ändrar inget.
Det här är vad `grab_dump()` i `rew_to_dsp8000.py` skickar.

### 6.3 Minnesdumpen

```
F0  00 20 32 00 01 4F <sub> <flag> 20 00  <12100 databyte>  F7      = 12112 byte
```

| Utlöst av | sub | flag |
|---|---|---|
| SND MEMORY DUMP-knappen | `12` | `00` |
| `70`-förfrågan | `0A` | `40` |

- Databyten är alla < 128 (7-bit-safe) men **bit-packade**: de packas upp
  MSB-först, 7 bitar per byte, till en bitström som fälten läses ur.
- **Offset-konvention:** *data-offset* = index i de 12100 databytena.
  Fil-offset = data-offset + 11 (F0 + 10-byte header). `syx_tools.py diff`
  skriver fil-offset, `probe`/`push` skriver data-offset.
- ~95 % nollor på testenheten (nästan tom).
- Knapp-dumpen och förfrågnings-dumpen skiljer sig på 84 byte, alla inom
  fil-offset 7–218: header-bytena, GEQ-blocket (annan EQ vid capture) och
  det 9-byte-mönster som beskrivs under 6.4. Från fil-offset 219 och framåt –
  i praktiken de 100 sparade programmen – är de bit-identiska.
- 12100 = 100 × 121 går jämnt ut, men mönstret vid data 39 återkommer vid 199
  (delta 160, inte 121), så "100 program × 121 byte" är **inte** bekräftat.

### 6.4 Avkodad layout (verifierad med `probe` / `probe --manual`)

| Block | Bit-offset | Data-offset | Format |
|---|---|---|---|
| Okänt (arbetsbuffert) | 0–86 | 0–12 | `80 36 00 00 00 02 33 16 00 00 …` – lika i alla dumpar. Kandidat: limiter/gate/delay/flaggor |
| **PEQ** | 87–278 | 12–39 | 6 poster à 32 bitar, ordning **L1 R1 L2 R2 L3 R3** (nedan) |
| Okänt mönster | ~278–340 | 39–47 | `02 09 54 68 00 17 40 06 10` i `4F 12`-dumpar, noll i `4F 0A`. Återkommer vid data 199–207 |
| **GEQ** | 373–884 | 53–126 | 64 tecknade 8-bitarsvärden: 31 vä band, vä master, 31 hö band, hö master |
| Resten | 885– | 127– | ej kartlagt (delay, gate, limiter, 100 program …) |

**GEQ-värde** = CC − 64, dvs. kvarts-dB: `dB = värde / 4`, −64…+63 ⇒
−16,00…+15,75 dB. Master returneras rått (0-centrerat, skala ej verifierad).

**PEQ-post (32 bitar):**

| Fält | Bitar | Tolkning |
|---|---|---|
| frekvens | 11 | `f = 20 · 10^(raw/640)` Hz (20 Hz = 0, 20 kHz = 1920) |
| bandbredd | 10 | `(raw + 1) / 60` oktav |
| gain | 11 | tvåkomplement, `dB = raw / 16` |

OFF = posten helt noll. Läget PAR/AUT/SGL lagras **inte** (SGL == PAR i
dumpen). Verifierat 2026-09-02: 6 filter satta till −6/+1/−2/+16/+12/+6 dB på
enheten → exakt match i avkodningen.

**Förbehåll om gain-fältets LSB:** alla testvärden var hela 0,5 dB-steg, dvs.
de tre lägsta gain-bitarna var alltid 0. I `4F 12`-dumparna är bit 278 (sista
biten i R3:s gain) satt även med PEQ OFF, direkt följt av 9-byte-mönstret
ovan. Så antingen är gain-fältet 10 bitar (1/8 dB) och bit 278 tillhör nästa
fält, eller så är arbetsbufferten i knapp-dumpen bara annorlunda. `decode_peq`
räknar en post som OFF om |gain| < 0,5 dB och frekvens/bandbredd är noll, så
det syns inte i utskriften. Avgörs med en `probe --manual` där ett PEQ-filter
sätts till ett udda värde och dumpen tas med **knappen** (`monitor`) i stället
för förfrågan.

### 6.5 Fader-statusframe (skickas vid fader-rörelse)

```
F0 00 20 32 00 01 33 09 <32 byte vänster> <32 byte höger> F7
```

Position 0–30 = band (samma CC-skala, 64 = 0 dB), 31 = master. Direkt läsbar,
men kräver att någon rör en fader – `monitor` skriver ut den i dB.

### 6.6 Referensdumpar i `dumps/`

| Fil | Sub-kod | Innehåll | Används av |
|---|---|---|---|
| `dsp8000_sysex_0db.syx` | `4F 12` | alla 62 GEQ-band 0 dB, PEQ OFF | `test_rew_script.py` |
| `dsp8000_sysex_p16db.syx` | `4F 12` | alla 62 GEQ-band +16 dB, PEQ OFF | `test_rew_script.py`, `push`-test |
| `dsp8000_sysex_ondemand.syx` | `4F 0A` | verklig EQ-kurva från REW-körning, PEQ OFF | exempel på förfrågnings-dump |

(En fjärde fil, `_m16db.syx`, var byte-identisk med `_p16db.syx` – en
felnamngiven capture – och är borttagen.)

---

## 7. Testlogg

**2026-08-31** (AudioBox, kanal 1, kanalerna länkade på enheten)
- Loopback AudioBox OUT→IN: CC 81 = 0/64/127 kom tillbaka exakt. Interfacet OK.
- Program Change 1, 5, 10: displayen bytte program.
- Fader 1 kHz vänster svep: CC 17 (59 st, 0–66) och CC 49 (59 st, 32–98) + tre
  `33 09`-frames. 49 = 17 + 32 = höger kanal (länkad), inte "LSB" som först antogs.

**2026-09-02**
- MIDI-sidan dokumenterad (CNTL = offset-tal). `CC 17 = 96` → `L 1 kHz +8 dB`.
  Skalan `CC = 64 + dB×4` fastslagen.
- Returväg: SND MEMORY DUMP gav 12110-byte dump först när **båda** kablarna satt i.
- SysEx-förfrågan `70 01` / `70 10 1F` / `70 64` med modell `01`: alltid full
  dump (`4F 0A`). Modell `0E` och `7F 0E`: inget svar.
- ADRStudio-skrivning `10 11 30` (1 kHz vä → +8 dB) med modell `01` och `0E`:
  dumpen ändrades inte (0 byte). Dött.
- `probe` (dumpa, CC på ett band, dumpa, diffa): GEQ-blocket lokaliserat till
  bit 373, 8-bit tecknat. Den tidigare "8 byte/band med bitvikter"-tolkningen
  (i `midi_captures.txt`) var fel; "stor överföringsbugg" var ett avkodningsfel.
- `probe --manual` + alla 6 PEQ satta: PEQ-blocket lokaliserat till bit 87,
  32 bitar/post, fält enligt 6.4.
- Genomgång av committade dumpar: `_m16db` == `_p16db` byte för byte;
  `_ondemand` vs `_0db` skiljer 84 byte i fil-offset 7–218.

---

## 8. Verktyg

| Kommando | Gör |
|---|---|
| `python rew_to_dsp8000.py ports` | listar MIDI-portar |
| `python rew_to_dsp8000.py monitor [--seconds N]` | lyssnar; sparar varje SysEx som `.syx`, skriver fader-frames i dB |
| `python rew_to_dsp8000.py sysex [--write-test]` | skickar `70 01` med modell `01` och `0E`, sparar svar. `--write-test` provar ADRStudio `10h` |
| `python rew_to_dsp8000.py readback` | hämtar dumpen och skriver ut 31+31 GEQ-band + 6 PEQ |
| `python rew_to_dsp8000.py grab FIL.syx` | hämtar dumpen och sparar den |
| `python rew_to_dsp8000.py probe [--band Hz --value CC --channel left]` | dumpa, sätt ett band via CC, dumpa, diffa (återställer bandet) |
| `python rew_to_dsp8000.py probe --manual` | dumpa, pausa medan du ändrar EN sak på enheten, dumpa, diffa |
| `python rew_to_dsp8000.py push [--send-only] FIL.syx` | skicka en dump till enheten (RCV-test, protokoll i avsnitt 4); dumpar före/efter och diffar. `--send-only`: bara skicka, för loopback-testet av interfacet |
| `python rew_to_dsp8000.py calibrate [--band Hz]` | verifiera CC→dB mot displayen |
| `python rew_to_dsp8000.py send [--dry-run] [--verify] [--channel left\|right\|both]` | skicka de 31 banden ur `rew_eq_suggestion.json` |
| `python syx_tools.py eq FIL.syx` | avkoda GEQ + PEQ ur en sparad dump (stdlib, ingen MIDI) |
| `python syx_tools.py diff A.syx B.syx` | råa byte som skiljer + GEQ/PEQ som ändrats |
| `python syx_tools.py hex FIL.syx [--start N --length N]` | hexdump |

Alla finns även som `./run.sh <kommando>`.

---

## Bilaga A: ADRStudio:s DSP8024-protokoll (fungerar INTE på DSP8000)

Reverse-engineerat av Adriano Ficarelli Jr (ADRStudio, rev 14, 2006) genom
att sniffa EQ-Design ↔ DSP8024. Testat mot vår DSP8000 2026-09-02: modellbyte
`0E` ignoreras, och med `01` svarar enheten på varje `70`-förfrågan med hela
dumpen. Realtidsskrivning `10h` gör inget. **Behålls som referens** för den
som har en DSP8024. Datavärden återges som ADRStudio skrev dem (blandat
decimalt/hex, kända skrivfel).

```
Skicka:   F0 00 20 32 00 0E <cmd> <data…> F7          (flera cmd kan kedjas före F7)
Begära:   F0 00 20 32 00 0E 70 <param> [70 <param> …] F7
Svar:     F0 00 20 32 00 0E <param> <värde…> F7
```

SysEx-mottagning är avstängd när DSP8024 visar FEEDBACK DESTROYER, PEQ eller
LEVEL METER – enheten måste stå på EQ-huvudskärmen.

`sb` i PEQ-kommandon: hög nibble = kanal (`0` vä / `2` hö), låg nibble = band 0–2.

| Kmd | Funktion | Data |
|---|---|---|
| `02` | Analyze IN/OUT (bypass) | `00` IN, `01` OUT |
| `08` | Equalizer / RTA | `00` EQ, `01` RTA |
| `10` | GEQ band `10 sr xx` | `sr` `00`–`1E` vä, `20`–`3E` hö; `xx` 0–64, **32 = 0 dB** |
| `11` | Master `11 s0 xx` | `s` 0 vä / 2 hö; 0–64, 32 = 0 dB |
| `12` | Limiter threshold | 0 OFF, 1–37 |
| `14` | Limiter release | 0–18 (0,5 s/steg) |
| `15` | Noise gate | 0 OFF, 1–47 (≈ −96…−44 dB) |
| `19` | Delay på/av | 0/1 |
| `1A` | Delay `1A s0 xx yy zz` | 3-byte-räknare |
| `1E` | PEQ-läge `1E sb xx` | 0 OFF, 1 PAR, 2 AUT, 3 SGL |
| `1F` | PEQ-frekvens `1F sb yy xx` | `yy` intervall 0–4, `xx` 0–127 (icke-linjärt) |
| `20` | PEQ-bandbredd `20 sb xx` | 0–120 (1/60 okt/steg) |
| `21` | PEQ-gain `21 sb 00 xx` | 0–127 (−48…+16 dB, 0,5 dB) |
| `23` | Crossfade | 0–15 s |
| `24` | Shelving slope | 0–10 (3 dB/okt per steg) |
| `25`–`34` | RTA (sampling, input, hold, upplösning, auto gain, gains, mic corr, mode, decay, Q-curve, generator, sinus, nivå) | se ADRStudio |
| `46 mm` | skriv hel programplats `mm` (0–63h) | header + 2 delay + 62 band + 2 master + 6×(läge, frekv, okt, gain) + namn |
| `46 7F` | skriv arbetsminne | som ovan + limiter/gate + alla RTA-inställningar |
| `3C aa×12` | programnamn | index i ADRStudios teckentabell |

Läsförfrågningar (DSP8024): `70 10 1F` alla vä band, `70 64` EQ-meter,
`70 65` RTA-display, `70 46 mm` programplats, `70 46 7F` arbetsminne,
`70 01` systemversion.

Notera de **tre olika GEQ-skalorna**: CC 0–127 (mitt 64), ADRStudio `10h`
0–64 (mitt 32), dumpens tecknade 8-bit (mitt 0).

---

## Bilaga B: OS-versioner, modellskillnader, PC-mjukvara

| | DSP8000 1996-OS (manual V1.3) | DSP8000 nyare OS (testenheten) / DSP8024 |
|---|---|---|
| Controller offset | fast (= 64) | justerbar 0–64 |
| MIDI OUT | "ingen funktion" | CC, PC, SysEx |
| SysEx | nej | ja |
| Memory dump | – | SND/RCV MEMORY DUMP |
| Granulär realtids-SysEx | – | bara DSP8024 |
| PC-editor | – | EQ-Design (DSP8000 OS ≥ 2.0 / DSP8024 OS ≥ 1.1) |

OS-versionen visas kort i displayen vid påslag. Firmware byttes via EPROM.

**Implementation chart** (DSP8024-manualen Tab 7.1, antas gälla vår enhet):
Control Change O/O, Program Change 0–99 O/O, System Exclusive O/O, allt annat
(noter, pitch bend, system common/realtime) X/X. Mode 1–4 (OMNI on/off).

**EQ-Design / UltraCurve Design** (Windows 9x, gratis, ej längre på
behringer.com, ej testad här): pratar SysEx med enheten. Givet att DSP8000
bara kan dumpa allt talar den troligen `4F`-dump fram och tillbaka – vilket
i så fall är ett bevis på att RCV-vägen (avsnitt 4) finns.

**ADRStudio StudioWare-panel** för Cakewalk/Sonar: DSP8024-only, SysEx.

---

## Källor

- **DSP8000 User Manual V1.3 (1996)** – [archive.org](https://archive.org/details/behringer-ultra-curve-dsp-8000-user-manual-ver-1-3),
  spegel [behringer-vintage.com](http://www.behringer-vintage.com/Anleitungen/DSP8000_V1.3_1996_ENG.pdf).
  Äldre MIDI-implementation (fast CC 64–127, ingen SysEx).
- **DSP8024 PRO-manual v1.2 (2001), tyska** – [tonkreis.de](http://www.tonkreis.de/D%20A%20T/Bedienungsanleitungen/Behringer%20ULTRA%20CURVE%20-%20DSP%208000.pdf)
  (textbaserad PDF, bästa källan för MIDI SETUP-fälten och Tab 7.1/7.2);
  engelska på [archive.org](https://archive.org/details/manualzilla-id-7376194) /
  [manualslib](https://www.manualslib.com/manual/15059/Behringer-Ultra-Curve-Pro-Dsp8024.html).
- **ADRStudio – SysEx Commands for DSP8024** – [adrstudio.com/8024.php](https://adrstudio.com/8024.php),
  [PDF](https://adrstudio.com/pdf/DSP8024-SYSEX-v13.pdf); [StudioWare](https://adrstudio.com/studioware.php).
- **Sound on Sound** – [Ultra-Curve review](https://www.soundonsound.com/reviews/behringer-ultra-curve)
  ("no data output over MIDI" gällde 1996-OS:et).
- Forum: diyAudio ([DSP8000 PC software](https://www.diyaudio.com/community/threads/behringer-dsp8000-download-pc-software.399835/),
  [DSP8024 midi software](https://www.diyaudio.com/community/threads/req-behringer-ultracurve-dsp8024-midi-software.356917/)),
  [audiosex.pro](https://audiosex.pro/threads/behringer-ultracurve-dsp8024-midi-software.54478/),
  gearspace ([1](https://gearspace.com/board/live-sound/907547-problem-behringer-ultra-curve-pro-dsp8024.html),
  [2](https://gearspace.com/threads/behringer-ultra-curve-dsp8000-vs.1296171/)).
- **Keith Neufeld's Electronics Blog** – DSP8024-installation + firmware 1.1→1.3
  via EPROM; sparad Wayback-kopia: `keiths-blog-dsp8024-firmware-upgrade.html`.
  Gäller DSP8024, inte DSP8000.
- `midi_captures.txt` – rå labblogg med de ursprungliga captures (senare
  poster rättar tidigare).
