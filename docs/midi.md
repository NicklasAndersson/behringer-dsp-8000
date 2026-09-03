# DSP8000 – MIDI-referens

Allt som är känt om MIDI-kopplingen till Behringer Ultra-Curve **DSP8000**
(originalmodellen, med nyare OS än 1996-manualen beskriver). Det här dokumentet
ersätter den tidigare webbresearch-filen och slutsatserna i
`midi_captures.txt` (som ligger kvar bredvid som rå labblogg).

Kort version av det viktigaste, plus de öppna frågorna samlade:
[readme.md](../readme.md). Skripten som använder allt det här:
[verktyg.md](verktyg.md). REW-halvan: [rew.md](rew.md).

**Verifierat mot enheten 2026-08-31, 2026-09-02 och 2026-09-03** med en PreSonus AudioBox
USB som MIDI-interface. Det som *inte* är testat står uttryckligen markerat.

---

## 0. Sammanfattning

| Vad | Riktning | Status |
|---|---|---|
| Program Change 0–99 → byt program | dator → DSP | **fungerar** |
| CC → grafisk EQ (31+31 band, 2 master) | dator → DSP | **fungerar** – `CC = 64 + dB×4`, CC-nummer = CNTL RCV-offset + 0…63 |
| CC ut vid fader-rörelse | DSP → dator | sett i capture (CC 17/49), ej systematiskt testat |
| SysEx-förfrågan `70 xx` → hela minnesdumpen | dator → DSP → dator | **fungerar** – 12112 byte (12110 databyte + `F0`/`F7`) efter ~5 s, utan att röra enheten |
| SND MEMORY DUMP (knapp) → hela minnesdumpen | DSP → dator | **fungerar** |
| Fader-rörelse → läsbar GEQ-status (`33 09`) | DSP → dator | **fungerar** |
| Läsa GEQ + PEQ ur dumpen | – | **avkodat** (`syx_tools.py eq`, `rew_to_dsp8000.py readback`) |
| RCV MEMORY DUMP (ladda en dump tillbaka) | dator → DSP | **fungerar med knapptryck** – tryck + på RCV MEMORY DUMP precis före sändning; utan det landar inget (2026-09-03). `push` / `apply` / `roundtrip`, avsnitt 4 |
| Skriva GEQ + PEQ via dump | dator → DSP | **verifierat 2026-09-03** – återläsningen är byte-identisk med det vi skickade. GEQ-blocket låg felkartlagt fram till dess (6.4); master och PEQ-läget skrivs inte alls. Delay/gate/limiter: samma väg, bitfälten inte kartlagda |
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
| **RCV MEMORY DUMP** | (knapp) | `+/–` sätter enheten i mottagningsläge för en dump. **Krävs** – en push med bara EXCL RCV ON landar inte (2026-09-03, avsnitt 4) |

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
| RCV MEMORY DUMP | in | Laddar en dump från MIDI IN tillbaka i minnet | **fungerar** – tryck + på knappen precis före sändning. Utan knapptryck landar inget (2026-09-03). Avsnitt 4 |

Praktiskt: för skriptkedjan räcker `CNTL RCV = 0`, `PROG RCV ON`, `EXCL RCV +
SND ON`. `CNTL SND` behövs bara om du vill se fader-rörelser i `monitor`.
ADRStudio rekommenderar att stänga av CNTL SND/RCV när man bara kör SysEx så
att inte controller-ekon nollställer något – det problemet har vi inte sett.

---

## 4. RCV MEMORY DUMP – skriva hela minnet (fungerar med knapptryck)

Vägen till att skriva allt som CC inte når – de 6 parametriska filtren i första
hand, men också GEQ, master och de 100 programmen. GEQ- och PEQ-blocken är
avkodade (avsnitt 6.4), så vi kan patcha en dump och pusha tillbaka den (`apply`
/ `roundtrip`, avsnitt 5b).

**Status (`roundtrip` 2026-09-03):**

- **Kräver knappen RCV MEMORY DUMP (+).** En push med **bara** EXCL RCV ON, utan
  knapptryck, landade **inte** (återläsningen var oförändrad utgångsdata). Med
  ett tryck på `+` precis före sändningen tog enheten emot dumpen och läste
  tillbaka exakt det som skrevs, GEQ **och** PEQ. `roundtrip`/`apply`/`push`
  pausar och säger till innan de skickar; även återställningen (en push) behöver
  knapptryck.
- **Format:** `4F 0A` (grabbens förfrågnings-format) duger – det var formatet i
  det lyckade testet. `roundtrip --base KNAPPDUMP.syx` / `apply --base …` finns
  om en enhet skulle vara kräsen och bara ta `4F 12`.
- Enheten är **långsam att svara** direkt efter en inkommande dump – skripten
  väntar 6 s, och `_grab_with_retry` låter dig trycka Enter för nytt försök.

**Fortfarande inte fastställt:**

1. ~~PEQ-läget~~ **avgjort 2026-09-03:** varken läge eller på/av ligger i dumpen
   (6.4) – slå på PEQ från fronten efter en dump-skrivning.
2. Arbetsbuffert kontra programminne: syns en pushad dump direkt på displayen,
   eller först efter Program Change? (Readback läser arbetsbufferten och den
   stämde, så åtminstone den skrivs.)
3. Finns en checksumma? De 9 bytena vid data-offset 39–47 (och igen vid
   199–207) är satta i `4F 12`-dumpar men noll i `4F 0A` (avsnitt 6.3). `apply`
   /`roundtrip` utgår från en *befintlig* dump och ändrar bara GEQ/PEQ-bitarna,
   så de här bytena följer med orörda från patch-basen.
4. Blockerar PROTECT MEM? (Ha det av vid skrivning.)
5. **Sub-koden i `4F`-svaret varierar:** `4F 0A 40` respektive `4F 04 40` har
   båda setts på `70`-förfrågan (samma enhet, olika tillfällen). Byte 7 verkar
   bära enhetsstatus, inte format – oklart vad `04` vs `0A` betyder. En patchad
   dump pushar tillbaka headern orörd. Grabbas basen medan enheten *inte* står
   rent på EQ-huvudskärmen (t.ex. direkt efter en tidigare push) kan även
   områden utanför GEQ/PEQ vara skeva, och då pushas de skeva värdena tillbaka.
   Därför: ta basen som en **egen, ren avläsning** och patcha *den*. GUI:t sparar
   varje avläsning som `history/reads/read-<tid>.syx` och skrivningen väljer
   den explicit; för CLI: `apply --base history/reads/read-<tid>.syx`.

**Risk:** en pushad dump skriver över arbetsbufferten och kan röra de 100
programmen. `apply`/`push` sparar alltid en före-dump (`history/reads/push-before-*` /
en färsk bas) som återställningspunkt. Använd bara dumpar från **samma** enhet.
Ta gärna en extra backup först: `./run.sh grab dumps/backup.syx`.

**Verifieringssteg:** `./run.sh roundtrip` gör hela testet – säkerhetskopierar
enhetens läge, patchar in ett känt GEQ+PEQ-mönster (L och R rampar åt var sitt
håll, 3 PEQ-filter med kända värden), pausar för RCV MEMORY DUMP-knappen, pushar,
läser tillbaka och jämför bit för bit, pushar sedan tillbaka säkerhetskopian.
`--keep` hoppar återställningen, `--base FIL` patchar en sparad knapp-dump.
Skriptet säger själv till om mönstret landade, inte landade, eller om
återläsningen är tvetydig.

Vill du köra det för hand: `./run.sh readback` (notera läget) → tryck + på RCV
MEMORY DUMP → `./run.sh push dumps/dsp8000_sysex_0db.syx` → kolla displayen och
kör `readback` igen. `push --send-only` mot en loopback (interface OUT → IN,
`monitor` i ett annat fönster) bekräftar att interfacet klarar 12 kB SysEx.

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

**Master-fadern** tar CC 0–127 på samma skala som banden (dumpen visar
−0,5 dB → −1 och +0,5 dB → +1, avsnitt 6.4).

**Stereolink** på enheten: då räcker vänsterkanalen (`send --channel left`).
Med Stereolink av skickar `send` båda (default).

**Timing:** enheten tappar CC om 62 stycken kommer i en klump. `send` pausar
20 ms mellan meddelanden, GUI:t 3 ms. `send --verify` läser tillbaka och
rapporterar band som inte landade.

**31 ISO-band:** 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315,
400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300,
8000, 10000, 12500, 16000, 20000 Hz.

---

## 5b. Skriva via dump (`apply`)

`apply` är den kompletta skrivvägen och skriver **både** grafisk och parametrisk
EQ, till skillnad från `send` (CC, bara GEQ):

1. hämtar en färsk dump från enheten (eller `--base FIL`) som utgångspunkt, så
   allt vi inte förstår bevaras exakt;
2. patchar in de 31 GEQ-banden och upp till 3 PEQ-filter ur
   `rew_eq_suggestion.json` (samma kurva och filter på L och R – mätningen är
   L+R kombinerad), via `syx_tools.patch_dump`;
3. sparar resultatet som `history/writes/applied-<tid>.syx` och visar diffen mot basen;
4. pushar dumpen och läser tillbaka för att bekräfta att GEQ + PEQ landade.

`apply --dry-run` gör steg 1–3 utan att skriva (med `--base` behövs ingen enhet
alls). Kodningen är inversen av avkodningen i avsnitt 6.4: GEQ-värde =
`db_to_cc(dB) − 64`, PEQ `fr/bw/g` enligt formlerna där, allt inskrivet MSB-först
i den 7-bit-packade strömmen så byten förblir < 128. Master rörs inte (skalan
inte verifierad).

**Skilj på de två skrivvägarna:** `send` (CC, ett band i taget) och dump-pushen
(`apply` / `push` / `roundtrip`) är olika mekanismer. CC är inkrementellt men
bara GEQ och kan tappa meddelanden; dumpen är atomisk och skriver GEQ + PEQ men
skriver över hela minnesbilden. `roundtrip` testar bara dump-vägen; `send
--verify` är motsvarigheten för CC-vägen.

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

**Sub-koden säger inte hur dumpen togs.** 2026-09-03 gav två `70`-förfrågningar
(GUI:ts läsning, 43 s isär) `02 40` respektive `12 00` – samma par som
knapp-dumpen. Sedan tidigare finns även `0A 40` och `04`. Byte 7 verkar vara
ett flaggfält (bitarna `08`/`10` varierar, `02` alltid satt), inte en
källmarkör. Låt `is_memory_dump` fortsätta titta på `4F`, inte på sub-koden.

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
| **GEQ** | 372–883 | 53–126 | 64 tecknade 8-bitarsvärden: 31 vä band, vä master, 31 hö band, hö master |
| Resten | 885– | 127– | ej kartlagt (delay, gate, limiter, 100 program …) |

**GEQ-värde: 0,5 dB per enhet** – `dB = värde / 2`, ±32 ⇒ ±16,0 dB, alltså
enhetens egna 0,5 dB-steg. **Inte** CC-skalan: CC har 0,25 dB/steg
(`CC = 64 + dB×4`, verifierad mot displayen) och enheten halverar när den
lagrar. Dumpens värde = (CC − 64) / 2.

**Master** (index 31 och 63, bit 620–627 och 876–883) har exakt samma skala
som banden. `decode_geq` returnerar master rått – multiplicera med 0,5 för dB.
`apply` skriver ändå inte master: en rumskorrigering ska inte flytta utnivån.

> **Rättelse 2026-09-03.** Fram till nu stod här bit 373 och kvarts-dB. Det var
> en bit fel, och felet tog ut sig självt vid avläsning (ett steg åt vänster
> ⇒ dubbla värdet ⇒ samma dB) så länge *nästa* fält var positivt. Vid
> **skrivning** tog det inte ut sig: `patch_dump` la varje bands teckenbit i
> grannens LSB och nollade bandets egen teckenbit, så varje **sänkning blev en
> stor höjning** (−1 dB skrevs som +63 dB). Det var det som fick IN/OUT att
> blinka rött efter en GUI-skrivning. Fixat; låst av
> `test_geq_offset_and_scale_against_hardware` mot `dumps/dsp8000_sysex_edges.syx`.

**PEQ-post (32 bitar):**

| Fält | Bitar | Tolkning |
|---|---|---|
| frekvens | 13 | **5 bit ISO-bandindex + 8 bit finsteg**: `f = ISO_BANDS[raw >> 8] · 2^((raw & 255)/64)` |
| bandbredd | 8 | `(raw + 1) / 60` oktav, 0–120 |
| gain | 10 | tvåkomplement, `dB = raw / 8` |
| (oanvänd) | 1 | postens sista bit – **tillhör nästa block, skriv den inte** |

**Frekvensfältet är inte ett logaritmiskt tal** utan två delar: höga 5 bitar
är index i de 31 ISO-tersbanden (0 = 20 Hz, 17 = 1 kHz, 29 = 16 kHz,
30 = 20 kHz), låga 8 bitar är finsteg om **1/64 oktav** uppåt från bandet.
Verifierat 2026-09-03: ett filter satt för hand till exakt 1 kHz gav `0x1100`
(band 17, finsteg 0), enhetens egna destroyer-filter gav `0x1D00`, `0x1D05`,
`0x1D0A`, `0x1D0F` (16 kHz plus 5, 10 och 15 finsteg = 16,9 / 17,8 / 18,8 kHz,
avläst som "17/18/19 kHz") och `0x1E00` = 20 kHz. Kontrollpunkt: `0x0527`
(band 5 = 63 Hz, finsteg 39) visades som 96,150 Hz, modellen ger 96,11.

Frekvens- och bandbreddsbredden är rättade 2026-09-03 (var 11 + 10). Enheten
skrev själv om posterna medan feedback destroyern var på, och de värdena lästes
av på displayen samtidigt: med 10-bitars bandbredd blev fyra av sex poster
orimliga (13,4 oktav), med 8 bitar stämmer alla sex exakt mot displayens
`37/60`, `34/60`, `28/60`. De två bitar som frigörs hör till frekvensfältet,
och då landar enhetens eget toppfilter på råvärde 7680 = exakt 20 kHz.
Gain-fältet ligger kvar på bit 21–30, oförändrat och verifierat två gånger.

Posten helt noll = inga värden satta. Verifierat 2026-09-02: 6 filter satta
till −6/+1/−2/+16/+12/+6 dB på enheten → exakt match i avkodningen.

**Filtrens läge ligger inte i dumpen.** På testenheten heter lägena
**ON / OFF / SGL** i FB-D-kolumnen (DSP8024-dokumentationen skriver
OFF/PAR/AUT/SGL, bilaga A `1E`). ON = feedback destroyern jagar och **flyttar
filtret själv**, SGL = single shot, OFF = filtret står still och används som
parametriskt. Verifierat
2026-09-03: en `apply` skrevs med PEQ avslaget, PEQ slogs sedan på för hand på
enheten och en ny dump hämtades – **noll byte skiljde**. Dumpen bär filtrens
*värden*, inte om de är inkopplade. Efter en dump-skrivning måste PEQ alltså
slås på från fronten.

**Gain-fältet är 10 bitar, inte 11** (rättat 2026-09-03). Båda bredderna ger
samma dB för alla handsatta testvärden (10 bitar med `raw/8` ⇔ 11 bitar med
`raw/16`), men i `dumps/dsp8000_sysex_0db.syx` och `_p16db.syx` – där PEQ-posterna
är helt orörda – är bit 278 ändå satt. Under 11-bitarsmodellen vore det en
gain på +1/16 dB i ett tomt filter; under 10-bitarsmodellen är det första biten
i 9-byte-mönstret som börjar på data 39. `patch_dump` skriver därför bara 10
bitar och lämnar postens sista bit i fred (`test_patch_dump_leaves_the_bit_after_the_peq_gain_alone`).
Samma off-by-one-fälla som GEQ-blocket hade, men här höll offset 87: enhetens
egen dump med ett handsatt **−2 dB**-filter avkodas rätt på 87 och som +126 dB
på 86 – ett negativt värde vid en fältgräns är det som avgör.

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
| `dsp8000_sysex_edges.syx` | `4F 12` | 20 Hz, 20 kHz och master satta för hand: L −0,5 dB, R +0,5 dB, allt annat 0 | `test_rew_script.py` – låser GEQ-offset + skala mot hårdvaran |
| `dsp8000_sysex_peq_device.syx` | `4F 12` | enhetens egen PEQ-kodning: L1 satt för hand till exakt 1 kHz, resten flyttade av destroyern, displayen avläst samtidigt | `test_rew_script.py` – låser PEQ-postens fältindelning och frekvenskodningen |

(En fjärde fil, `_m16db.syx`, var byte-identisk med `_p16db.syx` – en
felnamngiven capture – och är borttagen.)

### 6.7 Kartlägga fler fält

Recept, ett fält i taget:

1. **Ändra EN sak** och ta två dumpar. Går ändringen via CC:
   `./run.sh probe --cc 31 --value 40` (dumpa → CC → dumpa → återställ).
   Annars `./run.sh probe --manual` (dumpa → pausa medan du ändrar på
   enheten → dumpa).
2. Läs **bit-spannen** i rapporten, inte byten. Databyten är bit-packade, så
   ett fält kan ligga tvärs över en byte-gräns; `probe` och
   `syx_tools.py diff` skriver därför ut vilka bit-spann som ändrats, deras
   råvärde före/efter och vilket känt block de tillhör (`okänt` = nytt fält).
3. Upprepa med ett andra värde för att få skalan (två punkter ger lutning och
   tecken; tvåkomplement syns som ett stort råvärde vid negativa dB).
4. Skriv in fältet i `syx_tools` (`decode_*`/`patch_dump`) och i 6.4.

**Master-fadern** är klar (6.4): samma 0,5 dB-skala som banden, index 31 och
63. Det avslöjade också att hela GEQ-blocket låg en bit fel – därför punkt 2
ovan: läs *bit*-spannen, och misstro ett fält som bara råkar ge rätt dB.
Ett fält som gränsar till ett annat avslöjar sig när grannen är **negativ** –
sätt därför alltid ett negativt provvärde, inte bara ett positivt.

Kandidater i tur och ordning: **limiter/gate/delay** (`probe --manual`, data
0–12 och mönstret vid data 39/199), **PEQ-läget** ON/OFF/SGL, och
**programplatserna** (byt program på enheten, diffa).

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
- Returväg: SND MEMORY DUMP gav dump (12110 databyte, 12112 i filen) först när **båda**
  kablarna satt i.
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

**2026-09-03**
- `syx_tools.patch_dump` + `rew_to_dsp8000.py apply`: patcha GEQ + PEQ in i
  en färsk dump och pusha tillbaka. Round-trip (patcha → avkoda) verifierad
  i `test_rew_script.py`.
- **`roundtrip` mot enheten:**
  - Försök 1, **ingen knapptryckning**: patchade en färsk `4F 0A`-dump
    (GEQ-ramp L −8..+7 / R +8..−7, 3 PEQ) och pushade med bara EXCL RCV ON.
    Återläsningen: 68 avvikelser, GEQ + PEQ oförändrat utgångsläge → dumpen togs
    inte in.
  - Försök 2, **+ på RCV MEMORY DUMP** precis före sändningen: `_verify_applied`
    → "enheten har exakt det som skrevs (GEQ + PEQ)". **Både** GEQ-rampen och de
    3 PEQ-filtren (63/−6, 250/+3, 1k/−4) lästes tillbaka exakt. Dump-skrivvägen
    fungerar med knapptryck, `4F 0A`-formatet (grabben) duger.
  - Återställningen behöver också knapptryck – `roundtrip` pausar nu för det.
  - Slutsats: den tidigare noteringen "RCV bekräftad utan knapp" var fel.
- **PEQ-läget avgjort** (`history/writes/applied-20260903-104243.syx` skriven med
  PEQ av, `history/reads/read-20260903-104416.syx` läst efter att PEQ slagits på
  för hand): dumparna är **byte-identiska**. Varken på/av eller PAR/AUT/SGL finns
  i minnesdumpen – bara filtrens värden. PEQ måste alltså kopplas in från fronten
  efter en dump-skrivning. Samma par visar också att **skrivvägen nu landar exakt**:
  12112 byte tillbaka, bit för bit lika det vi skickade, med sund EQ (alla band inom
  ±16 dB på 0,5 dB-rutnätet).
- **PEQ-postens fältindelning rättad** (`history/writes/applied-20260903-105428.syx`
  → `history/reads/read-20260903-110621.syx`, sparad som `dumps/dsp8000_sysex_peq_device.syx`):
  frekvens är **13 bitar** och bandbredd **8**, inte 11 + 10. Enheten skrev om
  posterna själv medan displayen lästes av, och med den gamla indelningen blev
  fyra av sex bandbredder orimliga (13,4 oktav) medan 8-bitarsfältet ger exakt
  displayens `37/60`, `34/60`, `28/60`. De två frigjorda bitarna hör till
  frekvensen, vilket sätter enhetens eget toppfilter på råvärde 7680 = exakt
  20 kHz (3 dekader à 2560). Vår skrivning blev därmed rätt frekvens ändå
  (vi skrev de 11 höga bitarna, dvs. samma värde × 4) men fel bandbredd vid
  *läsning* av enhetsskrivna poster.
- **Läget ligger inte i dumpen – verifierat åt båda hållen.** Först PEQ av →
  på för hand (noll byte skiljde), sedan alla sex filtren från ON/SGL → **OFF**
  (`history/reads/read-20260903-111815.syx` vs `…-112416.syx`): **byte-identiska**.
  Varken läge eller på/av lagras, och ett avslaget filter behåller sina värden
  i minnet. Med destroyern av står värdena dessutom stilla mellan avläsningar –
  de vandrade bara medan den var ON.
- **PEQ-frekvensen är ISO-band + finsteg, inte ett logaritmiskt tal**
  (`history/reads/read-20260903-111815.syx`, sparad som referensdump): L1 sattes
  för hand till exakt 1 kHz och gav `0x1100` = band 17, finsteg 0. Alla
  avlästa punkter faller på plats (16 kHz = `0x1D00`, 20 kHz = `0x1E00`,
  96,150 Hz = `0x0527`). **Konsekvens:** våra tidigare PEQ-skrivningar räknade
  fram ett log-värde och landade därför på fel frekvens – den senaste
  `apply`:n satte 96 / 424 / 269 Hz där kurvan sa 53 / 74 / 166 Hz. Bandbredd
  och gain var rätt hela tiden. Rättat i `peq_freq_hz`/`peq_freq_raw`.
- **Feedback destroyern äger filtren.** Samma experiment visade att enheten
  flyttade våra tre filter (53/74/166 Hz) till ~15,9–16,1 kHz och 20 kHz mellan
  skrivningen och avläsningen 12 minuter senare, och att FB-D-sidans
  FREQUENCY-kolumn visade värden som inte fanns i dumpen (två bit-identiska
  poster visade 89 Hz respektive 9,2 kHz). Alla sex filtren stod på **ON** i
  FB-D-kolumnen, dvs. i jaktläge. **Sätt FB-D till OFF på alla sex innan en
  `apply`** (lägena är ON/OFF/SGL), annars skriver enheten över frekvenserna.
  Kvar att verifiera: att våra frekvenser står kvar när destroyern är av.
- **Master rörs inte av en skrivning** – bekräftat på riktig data: basen hade master
  −8,5 / −8 dB (enhetens eget läge, bekräftat av användaren) och de värdena står kvar
  efter `apply`. Med den gamla, felskjutna modellen hamnade sista bandets skrivning
  i masters teckenbit och hade gjort −8,5 dB till **+55,5 dB**; det är nu låst av
  `test_patch_dump_never_touches_master`.
- **Master-fadern kartlagd – och hela GEQ-blocket rättat.** Fyra avläsningar:
  allt 0 dB (`read-…100544`), master L −1 / R +1 (`…100627`), master L −0,5 /
  R +0,5 (`…102927`), och till sist L −0,5 / R +0,5 på **20 Hz, 20 kHz och
  master samtidigt** (`…103416`, sparad som `dumps/dsp8000_sysex_edges.syx`).
  - De två första gav master rätt dB men satte också en bit i grannbandet
    (20 kHz "+0,25 dB" utan att någon rört 20 kHz). Kontrollprovet med −0,5 dB
    satte samma bit igen → biten hörde inte till bandet.
  - Kant-dumpen avgjorde saken: 20 Hz vänster −0,5 dB ligger som **åtta ettor
    på bit 372–379**, inte 373–380. Alltså börjar GEQ-blocket på **bit 372**
    och varje värde är **0,5 dB per enhet**, inte 0,25. Alla sex satta värden
    avkodas nu exakt, och de 56 orörda banden är exakt 0.
  - **Varför det inte syntes förut:** en bit åt vänster dubblar värdet, och
    dividerat med 4 i stället för 2 blev dB rätt ändå – så länge nästa fält var
    positivt. Referensdumparna (allt 0 dB / allt +16 dB) och `roundtrip`
    (skrev och läste med samma felaktiga modell) kunde därför aldrig fånga det.
    Det som avslöjade modellen var enhetens *egna* kurvor: 26 av 62 band låg på
    kvarts-dB-värden som enheten varken kan visa eller ta emot, och tre band
    stod på −15,75 dB där REW-korrigeringen klipper på exakt −16.
  - **Konsekvens (allvarlig):** `patch_dump` skrev en bit fel, så varje bands
    teckenbit hamnade i grannens LSB och bandets egen teckenbit nollades →
    **alla sänkningar skrevs som stora höjningar**. Sista `apply`-filen
    (`history/writes/dsp8000_applied.syx`) gav enheten +63 dB där kurvan sa
    −1 dB; 28 av 62 band hamnade över +16 dB. Det förklarar den röda
    overflow-LED:en efter GUI-skrivningen (som tidigare skylldes på en skev
    `4F 04`-basdump). CC-vägen (`send`) var aldrig drabbad – den går genom
    enhetens egen tolkning.
  - **Bekräftat på hårdvara, inte bara i teorin:** `history/writes/dsp8000_applied.syx`
    (det vi skickade) och `history/reads/dsp8000_base.syx` (vad enheten lämnade ut
    efteråt) har *identiska* GEQ-block, och med rätt modell står det +63 / +58,5 /
    +60,5 / +62,5 dB där kurvan sa −1 / −5,5 / −3,5 / −1,5. Enheten tog alltså emot
    och behöll de orimliga värdena – återläsningen "stämde" bara för att den
    avkodades med samma felaktiga modell som skrev dem.
  - Fixat i `syx_tools` (`GEQ_BIT_OFFSET = 372`, `GEQ_DB_PER_UNIT = 0,5`) och
    låst av `test_geq_offset_and_scale_against_hardware` mot kant-dumpen.
    **Gör om varje `apply`/GUI-skrivning som gjordes före det här.**
- **Två `70`-förfrågningar gav olika header:** `4F 02 40` och `4F 12 00` (samma
  enhet, 43 s isär, båda via GUI:ts läsning). Sub-koden är alltså inget bevis
  för hur dumpen togs – se 6.3.
- **IN/OUT blinkade rött efter en GUI-skrivning** trots att EQ:n bara innehöll
  sänkningar (rött = intern overflow/clipping, inte EQ-matematik). Basdumpen i det
  fallet hade header `4F 04` (inte `4F 0A`) – grabbad medan enheten inte stod rent
  på EQ-skärmen, så något utanför GEQ/PEQ pushades tillbaka skevt. Åtgärd: GUI:t
  läser nu enheten i ett eget steg och sparar varje avläsning tidsstämplat
  (`history/reads/read-<tid>.syx`); skrivningen väljer en sådan explicit och hämtar
  ingen egen dump. Kvar att verifiera på hårdvara att rött försvinner med den
  ordningen, och vilken byte som orsakade overflowen.

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
| `python rew_to_dsp8000.py probe --cc N [--value CC]` | samma men ett rått CC-nummer i stället för ett ISO-band: `--cc 31` = vä master, `--cc 63` = hö master |
| `python rew_to_dsp8000.py probe --manual [--note TEXT]` | dumpa, pausa medan du ändrar EN sak på enheten, dumpa, diffa. `--note` hamnar i filnamnet |
| `python rew_to_dsp8000.py push [--send-only] FIL.syx` | skicka en dump till enheten (RCV-test, protokoll i avsnitt 4); dumpar före/efter och diffar. `--send-only`: bara skicka, för loopback-testet av interfacet |
| `python rew_to_dsp8000.py apply [--dry-run] [--base FIL]` | patcha en dump (färsk eller `--base`) med GEQ + PEQ ur `rew_eq_suggestion.json`, pusha och läs tillbaka. Avsnitt 5b |
| `python rew_to_dsp8000.py roundtrip [--keep]` | hårdvarutest av dump-vägen: backup → skriv känt GEQ+PEQ-mönster → läs tillbaka + jämför → återställ. Rör inte JSON/CC. Avsnitt 4 |
| `python rew_to_dsp8000.py calibrate [--band Hz]` | verifiera CC→dB mot displayen |
| `python rew_to_dsp8000.py send [--dry-run] [--verify] [--channel left\|right\|both]` | skicka de 31 banden ur `rew_eq_suggestion.json` |
| `python syx_tools.py eq FIL.syx` | avkoda GEQ + PEQ ur en sparad dump (stdlib, ingen MIDI) |
| `python syx_tools.py diff A.syx B.syx` | råa byte som skiljer + GEQ/PEQ som ändrats + **ändrade bit-spann** (kartläggning av nya fält) |
| `python syx_tools.py hex FIL.syx [--start N --length N]` | hexdump |
| `python syx_tools.py` (modul) `patch_dump(base, geq_L, geq_R, peqs)` | skriv GEQ/PEQ i en dump (inversen av `decode_*`), 7-bit-safe |

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
