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
| Skriva GEQ + PEQ via dump | dator → DSP | GEQ **verifierat 2026-09-03**. PEQ: SysEx-återläsningen är byte-identisk med det som skrevs, men **PEQ-sidans display visar fel frekvens för post 2–6** (rätt bara för post 0) – ny, oförklarad bugg, avsnitt 7 (12:52). Master och FB-D-läget skrivs inte alls. Delay/gate/limiter: samma väg, bitfälten inte kartlagda |
| EQ-Design:s protokoll: 12 kommandon + hela minnesbilden | – | **avkodat ur EQDESIGN.EXE** 2026-09-03 (6.8); bilden verifierad mot våra dumpar (programnamn, programnummer), kommandona `21`/`22`/`43`… otestade mot enheten |
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

1. ~~PEQ-läget~~ **avgjort 2026-09-03:** FB-D-läget (ON/OFF/SGL) ligger inte i
   dumpen (6.4). Sätt **OFF** på alla sex *före* skrivningen, annars flyttar
   destroyern filtren. Att ett OFF-filter bearbetar ljudet är inte verifierat
   (REW-sweep).
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
`dB × 2` (0,5 dB/enhet – **inte** CC-skalan), PEQ `fr/bw/g` enligt formlerna
där, allt inskrivet MSB-först i den 7-bit-packade strömmen så byten förblir
< 128. Master rörs inte – avsiktligt, en rumskorrigering ska inte flytta
utnivån (skalan är känd, 6.4).

**Före en `apply`: FB-D OFF på alla sex filtren.** Läget ligger inte i dumpen,
och med ON flyttar destroyern filtren själv (testloggen 2026-09-03).

**Obs (12:52-testet, avsnitt 7):** även med FB-D OFF och en bit-exakt
SysEx-återläsning visade PEQ-sidans display fel frekvens för post 2–6.
Bandbredd och gain stämde. Oklart om det är ett displayfel (löses av att
bläddra på PEQ-sidan) eller ett verkligt gap i frekvenskodningen för post
≥ 1 – se avsnitt 7 för detaljerna och nästa test.

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

`dev` = **MIDI-kanal − 1** enligt EQ-Design (6.8): den skickar utkanalen − 1
och läser enhetens kanal ur `44`-svaret. Bekräftat 2026-09-03: `43` besvaras
med `44 00`, device-ID `00` på CHANNEL 1. Att enheten *kräver* rätt kanal är
otestat (readme:s checklista).

### 6.2 Förfrågan → dump

```
F0 00 20 32 00 01 70 <xx> F7
```

Oavsett `xx` (`01`, `10 1F`, `64` – allt testat) svarar enheten efter ~5 s
med **hela minnesdumpen**. EQ-Design begär samma dump med `40` och har
granulära kommandon (`20`–`23`, 6.8) som vi inte testat; någon versionssträng
har vi inte sett. Enheten måste stå på EQ-huvudskärmen. Förfrågan ändrar inget.
Det här är vad `grab_dump()` i `rew_to_dsp8000.py` skickar.

Gemini-rapporten (och ADRStudio, för DSP8024) säger att SysEx tas emot på
EQ- **och** RTA-skärmen men ignoreras i SETUP, LEVEL METER, FB-D och PEQ, och
att inget kommando kan ta enheten tillbaka till huvudskärmen. Det stämmer
med att enheten inte svarar från RCV-panelen efter en push; RTA-skärmen är
otestad. Rapporten hävdar också att ljudet mutas medan en dump skickas –
otestat (readme:s checklista).

### 6.3 Minnesdumpen

```
F0  00 20 32 00 01 4F  <12104 databyte>  F7      = 12112 byte
```

Efter `4F` följer direkt data – det finns **ingen header**. De fyra byte vi
tidigare läste som `<sub> <flag> 20 00` är de första packade databytena
(rättat 2026-09-03 med EQ-Design, 6.8). Uppackade blir de minnesbildens byte
0–3, och byte 0 är ett **statusflaggfält** som varierar mellan avläsningar
(`24`, `15`, `09` sedda) – det är därför "sub-koden" aldrig sa något om hur
dumpen togs. Låt `is_memory_dump` titta på `4F`.

- Databyten är alla < 128 men **7-bitars-packade** MSB-först: 8 databyte =
  7 minnesbyte. 12104 databyte ⇒ en minnesbild på **10591 byte**, layout i 6.8.
- **Offset-konvention:** `syx_tools` läser fälten ur bitströmmen räknat från
  fil-offset 11 (`GEQ_BIT_OFFSET`, `PEQ_BIT_OFFSET`); minnesbyte = (bit + 28) / 8.
  `syx_tools.py diff` skriver fil-offset och märker ändrade bit-spann med
  huvud / delay / PEQ / namn / GEQ / gap / program. `unpack_image` ger bilden
  byteinriktad.
- Knapp-dump och förfrågnings-dump skiljer sig bara i statusbyten och det som
  ändrats på enheten däremellan; programmen 1–100 är identiska.
- ~~"100 program × 121 byte"~~ – det är 10 + 104 + 76 + 100 × 104 (6.8).

### 6.4 Avkodad layout (verifierad med `probe` / `probe --manual`)

| Block | Bit-offset (`syx_tools`) | Minnesbyte | Format |
|---|---|---|---|
| Huvud | −28–51 | 0–9 | statusflaggor, crossfade, shelving, limiter, gate, program (6.8) |
| Delay | 52–83 | 10–13 | delay L, delay R, 16 bit big-endian (program 0) |
| **PEQ** | 84–275 | 14–37 | 6 poster à 4 byte, ordning **L1 R1 L2 R2 L3 R3** (nedan) |
| Namn | 276–371 | 38–49 | arbetsbuffertens namn, 12 tecken (ASCII − 0x20) – det var "mönstret vid data 39" |
| **GEQ** | 372–883 | 50–113 | 64 tecknade 8-bitarsvärden: 31 vä band, vä master, 31 hö band, hö master |
| Gap | 884–1491 | 114–189 | 76 byte EQ-Design hoppar över; testenheten har `21 35 34 00 2f 00 31` vid 178–184, annars 0 |
| Program 1–100 | 1492– | 190– | 104 byte var, samma layout som byte 10–113 (delay, PEQ, namn, GEQ) |

Bit-offset är `syx_tools`:s räkning (bitströmmen från fil-offset 11);
minnesbyte är EQ-Design:s byteinriktade bild från fil-offset 7 (6.8).
Verifierat mot `dumps/`: programnamnen läses ut i klartext och huvudets
programnummer 9 = displayens program 10.

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

**PEQ-post (4 byte, rättad 2026-09-03 med EQ-Design):**

| Byte | Fält | Tolkning |
|---|---|---|
| 0 | bandindex | 0–30 i de 31 ISO-tersbanden (0 = 20 Hz, 17 = 1 kHz, 30 = 20 kHz) |
| 1 | finsteg | tjugondelar av avståndet till nästa ISO-frekvens: `f = ISO[b] + (ISO[b+1] − ISO[b]) · fin/20` |
| 2 | bandbredd | `(raw + 1) / 60` oktav, 0–119 |
| 3 | gain | tecknad byte, `dB = raw / 2` (−48…+16 dB) |

Vår tidigare post (13 + 8 + 10 + 1 bitar från bit 87) låg **tre bitar snett**:
"5 bit bandindex" var bandindexets låga fem bitar, "10 bit gain" var
gain-byten plus två bitar av nästa posts bandindex. Alla värden på halva dB
avkodades ändå rätt, men gain på åttondels dB klottrade i nästa post – och
för R3 i **programnamnets första tecken** (`AUT O Q` blev `aUT O Q` på
enheten, `dsp8000_sysex_peq_device.syx`). Bandbredden var rätt hela tiden.

**Frekvensen är linjär mellan ISO-frekvenserna**, inte logaritmisk: EQ-Design
(`0x401430`) räknar `f = ISO[b] + (ISO[b+1] − ISO[b]) · fin/20`, och enheten
visar exakt det – `0x0527` = 63 + 17·39/20 = **96,150 Hz** (displayen visade
96,150), destroyerns `0x1D05`/`0x1D0A`/`0x1D0F` = **17/18/19 kHz** jämnt,
`0x1100` = 1 kHz, `0x1E00` = 20 kHz. Vår 1/64-oktav-modell gav 96,11 och
16,9/17,8/18,8 kHz – nära, men fel. Finsteget får överstiga 19 (enheten
skrev själv 39); `peq_freq_raw` normaliserar till 0–19 som EQ-Design gör.
Att enheten skrev om vårt `0x043C` (89 Hz) till `0x0527` (96 Hz) var alltså
**inte** samma frekvens – destroyern stod på ON och flyttade filtret.

Posten helt noll = inga värden satta. Verifierat 2026-09-02: 6 filter satta
till −6/+1/−2/+16/+12/+6 dB på enheten → exakt match i avkodningen.

**Filtrens läge ligger inte i dumpen.** På testenheten heter lägena
**ON / OFF / SGL** i FB-D-kolumnen (DSP8024-dokumentationen skriver
OFF/PAR/AUT/SGL, bilaga A `1E`). ON = feedback destroyern jagar och **flyttar
filtret själv**, SGL = single shot, OFF = filtret står still och används som
parametriskt. Verifierat
2026-09-03: en `apply` skrevs med PEQ avslaget, PEQ slogs sedan på för hand på
enheten och en ny dump hämtades – **noll byte skiljde**. Dumpen bär filtrens
*värden*, inte läget. Läget sätts på fronten: **OFF på alla sex före en
skrivning**, annars flyttar destroyern filtren (avsnitt 7). Om ett filter med
FB-D OFF bearbetar ljudet som stillastående parametriskt filter är inte
verifierat – en REW-sweep avgör.

### 6.5 Fader-statusframe (skickas vid fader-rörelse)

```
F0 00 20 32 00 01 33 <program> <32 byte vänster> <32 byte höger> F7
```

Byten efter `33` är **aktuellt program**, 0-baserat (`09` = program 10, samma
tal som minnesbildens huvud). Position 0–30 = band, 31 = master, på
**enhetens egen skala 0–64 med 32 = 0 dB i 0,5 dB-steg** – samma som
EQ-Design:s kommando `21`, **inte** CC-skalan (rättat 2026-09-03: master
`15`/`16` i ramen = −8,5/−8 dB, exakt enhetens master i dumpen två dagar
senare). EQ-Design 1.0 känner inte till `33`. `monitor` skriver ut den i dB.
Kvar att verifiera på hårdvara: ett band på känt dB mot ramens råvärde.

### 6.6 Referensdumpar i `dumps/`

| Fil | Sub-kod | Innehåll | Används av |
|---|---|---|---|
| `dsp8000_sysex_0db.syx` | `4F 12` | alla 62 GEQ-band 0 dB, PEQ OFF | `test_rew_script.py` |
| `dsp8000_sysex_p16db.syx` | `4F 12` | alla 62 GEQ-band +16 dB, PEQ OFF | `test_rew_script.py`, `push`-test |
| `dsp8000_sysex_ondemand.syx` | `4F 0A` | verklig EQ-kurva från REW-körning, PEQ OFF | exempel på förfrågnings-dump |
| `dsp8000_sysex_edges.syx` | `4F 12` | 20 Hz, 20 kHz och master satta för hand: L −0,5 dB, R +0,5 dB, allt annat 0 | `test_rew_script.py` – låser GEQ-offset + skala mot hårdvaran |
| `dsp8000_sysex_peq_device.syx` | `4F 04` | enhetens egen PEQ-kodning (= `history/reads/read-20260903-111815.syx`): L1 satt för hand till exakt 1 kHz, resten flyttade av destroyern, displayen avläst samtidigt | `test_rew_script.py` – låser PEQ-postens fältindelning och frekvenskodningen |

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

Med minnesbilden kartlagd (6.8) återstår **huvudets statusbyte** (vilka
bitar är IN/OUT, EQ/RTA, stereolink …: `probe --manual`, ändra en sak, se
byte 0), **76-bytesgapet** vid byte 114–189 (RTA-inställningar?
mic-korrektion?) och **delayens enhet** (16 bit rått; EQ-Design räknar med
48 kHz, så troligen sampel – sätt 10 ms på enheten och diffa).

### 6.8 EQ-Design-protokollet (ur `EQDESIGN.EXE`, 2026-09-03)

Behringers egen editor EQ-Design 1.0 (bilaga B) är en MFC-app länkad
1996-12-11 som pratar med DSP8000 via `midiOutLongMsg`. Disassemblerad
2026-09-03 (llvm-objdump; nyckelfunktioner: sändare `0x40b2e0`, dump
`0x403ed0`, 7→8-packning `0x403f70`/`0x4041d0`, mottagare `0x404280`,
frekvens `0x401430`). Sändaren bygger varje SysEx som

```
F0 00 20 32 <kanal−1> 01 <kommando> <data…> F7
```

**Device-ID är MIDI-utkanalen, 0-baserad** (CHANNEL 1 ⇒ `00`), och enheten
svarar med sin egen kanal i samma byte – "Search DSP8000" skickar `43` och
läser kanalen ur `44`-svaret ("DSP8000 found at channel: %d"). Modellbyte
`01`. Mottagaren kräver `00 20 32`, modell `01` och (utom för `44`) att
device-ID = inkanalen.

| Kmd | Riktning | Data | Betyder | Status hos oss |
|---|---|---|---|---|
| `43` | → DSP | – | "vem är där?" | **verifierat 2026-09-03**: `44` tillbaka inom sekunden |
| `44` | DSP → | 1 byte | svar på `43`: `F0 00 20 32 00 01 44 00 F7` – device-ID `00` = CHANNEL 1, plus en databyte `00` som EQ-Design inte läser. Skickar man `44` själv svarar enheten inte | **verifierat 2026-09-03** |
| `40` | → DSP | – | begär minnesdumpen ("Read DSP8000 Data?") | **verifierat 2026-09-03**: samma 12112-bytesdump som `70 xx` |
| `4F` | båda | 12104 packade byte | hela minnesbilden (nedan). → DSP: "Update DSP8000", efter rutan "Select MEMORY DUMP RECEIVE on DSP8000" | **verifierat** (`grab`/`push`, avsnitt 4) |
| `21` | båda | `<prog>` + 32 L + 32 R | grafisk EQ opackad: `dB·2 + 32` (0–64, 32 = 0 dB), band 0–30 + master per kanal | **verifierat 2026-09-03** → DSP: 1 kHz +8 dB landade direkt, utan knapptryck och utan svar. Samma sak som CC-vägen, men alla 64 värden atomärt i ett meddelande |
| `22` | båda | `00` + 32 packade (24 byte = 6 PEQ-poster + 4 fyll) | de sex parametriska filtren i arbetsbufferten | **verifierat 2026-09-03** → DSP: L1 = 100 Hz / 1 okt / −6 dB syntes på PEQ-sidan direkt, utan knapptryck – **granulär PEQ-skrivning finns** |
| `20` | båda | `00` + 16 packade (14 byte = huvud 10 + delay L/R) | limiter, gate, crossfade, shelving, program, delay | otestat |
| `23` | båda | `<prog>` + 120 packade (104 byte) | ett helt program 1–100 | otestat |
| `15` | → DSP | 1 byte flaggor | RTA-styrning: bit 0–3 = fyra RTA-inställningar (auto gain, detektor, max display, 1/0,5 dB – ordningen okänd), bit 4 = engångspuls. Skickas efter varje `11` ⇒ RTA-strömmen | otestat |
| `11` | DSP → | 1 byte + 80 packade (70 byte) | RTA-ram: 64 bandvärden + statusbyte (nivå/gain i 4 dB-steg) | otestat |
| `41` / `42` | båda | – | läge EQ / RTA (menyn Mode; enheten skickar samma vid byte på fronten) | **verifierat 2026-09-03**: displayen byter skärm, inget svar |
| `10` | DSP → | 16 packade | okänt – EQ-Design tar emot och ignorerar | – |
| `33` | DSP → | program + 64 byte | fader-status (6.5) – **okänt för EQ-Design 1.0** | verifierat |
| `70 xx` | → DSP | – | vår förfrågan – **finns inte i EQ-Design** men ger dumpen | verifierat |

I läget "Ctl/Pgm Change" går GEQ i stället som CC `CtrlOffset + 0…63` med
värde `(dB·2 + 32)·2` = `64 + 4·dB` (skalan vi mätte) och program som `C0`;
enheten skickar CC/PC tillbaka som EQ-Design tolkar med samma formler.

**7→8-packningen** (`0x403f70`): 7 minnesbyte i taget, MSB-först, till 8
databyte < 128 – exakt den bitström vi redan läste. Ingen checksumma: i
76-bytesgapet skickar EQ-Design oinitierat stackskräp och enheten tar emot.

**Minnesbilden** (`0x403ed0`: 1513 grupper × 7 = 10591 byte, sista byten fyll):

| Byte | Innehåll |
|---|---|
| 0 | statusflaggor: bit 1 och bit 6 modelleras av EQ-Design (betydelse okänd), resten sätter enheten (`24`/`15`/`09` sedda) |
| 1–2 | 0 |
| 3 | crossfade vid programbyte, sekunder 0–15 (testenheten: **10 s**) |
| 4 | shelving-lutning i steg om 3 dB/okt, 1–10 (testenheten: 9 = 27 dB/okt) |
| 5 | limiter: 0 = av, annars `255 − tröskel` (0–36 dB under full skala) |
| 6 | noise gate: 0 = av, annars `tröskel + 1` (−44…−96 dB) |
| 7 | okänt (0 på testenheten) |
| 8, 9 | aktuellt program, 0-baserat, två gånger (`09` = program 10) |
| 10–113 | **program 0 = arbetsbufferten**, 104 byte |
| 114–189 | 76 byte EQ-Design varken skriver eller läser |
| 190–10589 | program 1–100 à 104 byte |

**Program, 104 byte:** delay L, delay R (16 bit big-endian; enhet obekräftad,
EQ-Design räknar med 48 kHz), 6 PEQ-poster à 4 byte (L1 R1 L2 R2 L3 R3, 6.4),
namn 12 tecken lagrade som ASCII − 0x20, GEQ L 32 byte, GEQ R 32 byte
(tecknat, 0,5 dB/enhet, band 0–30 + master). Testenheten har åtta namngivna
program (`BAS  ROCK`, `MOVIE`, `EXP!`, `QUVADIS 1`, `BAS`, `MOVIE  BAS`,
`GOOD 1`, `AUT O Q`); `syx_tools.py eq` listar dem.

**Övrigt ur programmet:** menyn File / Mode (Eq, RTA) / Setup (EQ, Parametric
EQ, Delay, MIDI) / Curve (Display, Recalc L/R) / Help. Dialoger: Parametric
Equalizer (Left 1–3, Right 1–3; +16…−48 dB, 20 Hz–20 kHz, 1/60–120/60 okt),
RTA Setup (källa Microphone/left/right/mono, line gain 0–60 dB och mic gain
20–80 dB i 4 dB-steg, detektor Peak/RMS, decay 15/65/250/1000 ms, Max Display,
1/0,5 dB, Auto-Q Target Flat + värde, Mic Correction Off/Left/Right, Output
Off/Input/Sine/White Noise/Pink Noise, sinusfrekvens, nivå), EQ Parameter
(limiter 0…−36 dB, gate −44…−96 dB, crossfade 0–15 s, shelving 3–30 dB/okt,
Limiter ON, Gate ON), Delay Parameter (L/R, temperatur 0–40 °C, ms/meter/feet,
Delay ON), MIDI Setup (in/ut-enhet och kanal 1–16, Sys. Exclusive eller
Ctl/Pgm Change, Controller Offset, Update DSP8000, Search DSP8000), Program
Load/Save med namn, knappraderna PEAK HOLD / PEAK RESET / AUTOGAIN / FREEZE
(RTA) och ZERO / INVERT / PGM. CLEAR / PGM. LOAD / PGM. SAVE (EQ). Rutorna
"connect DSP8000 – Set MIDI ON – Set OMNIMODE ON – Set SYSTEMEXL RECEIVE ON"
och "Select MEMORY DUMP RECEIVE on DSP8000" bekräftar våra egna fynd om
inställningar och knapptryck. Utvecklare enligt strängarna: LAUTH
DATENVERARBEITUNG; om-rutan säger "DIGITAL 24-bit DUAL DSP MAINFRAME".
Inställningar i registret under `Software\BEHRINGER` (CtrlOffset, MIDIMode,
MIDIIn/OutDevice, MIDIIn/OutChannel), filformat `.eqd`. Transferfunktionen
räknas vid fs = 48 000 Hz.

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
  i minnesdumpen – bara filtrens värden. Läget sätts på fronten (och ska stå på
  OFF före en skrivning, se nedan). Samma par visar också att **skrivvägen nu landar exakt**:
  12112 byte tillbaka, bit för bit lika det vi skickade, med sund EQ (alla band inom
  ±16 dB på 0,5 dB-rutnätet).
- **PEQ-postens fältindelning rättad** (`history/writes/applied-20260903-105428.syx`
  → `history/reads/read-20260903-110621.syx`):
  frekvens är **13 bitar** och bandbredd **8**, inte 11 + 10. Enheten skrev om
  posterna själv medan displayen lästes av, och med den gamla indelningen blev
  fyra av sex bandbredder orimliga (13,4 oktav) medan 8-bitarsfältet ger exakt
  displayens `37/60`, `34/60`, `28/60`. De två frigjorda bitarna hör till
  frekvensen, vilket sätter enhetens eget toppfilter på råvärde 7680 = exakt
  20 kHz (då läst som 3 dekader à 2560; i den rättade kodningen nedan är det
  band 30 × 256). Fältbredden ändrade inte vad vi skrev (de 11 höga bitarna =
  samma värde × 4), bara läsningen av enhetsskrivna bandbredder – att våra
  frekvenser ändå var fel beror på kodningen, två punkter ned.
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
  Samma omskrivning satte gainen på 0,5 dB-steg för de fem filter destroyern
  flyttade (−9,75 → −10, −10,75 → −11, −11,375 → −11,5); R3 behöll −11,375.
  Enheten *lagrar* alltså åttondels-dB som vi skriver dem (återläsningen två
  minuter efter en skrivning var byte-identisk) men arbetar själv i halva dB.
  **Kvar att verifiera** – dagens sista `apply` gjordes 10:54, frekvenskodningen
  rättades 11:22, så ingen skrivning med rätt PEQ-frekvenser finns ännu: en
  `apply` med FB-D OFF på alla sex, PEQ-sidan ska visa kurvans frekvenser och
  de ska stå kvar, LED grön, och en REW-sweep som visar att OFF-filtren
  bearbetar ljudet.
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
- **NY BUGG: PEQ-displayen stämmer bara för post 0.** Efter frekvensrättelsen
  (avsnitt 6.4) kördes den efterlysta `apply`:n: FB-D OFF på alla sex,
  `rew_eq_suggestion_l_r_lampa_av_sep_2.json` (53 / 74 / 165 Hz) skrivet via
  GUI:t (`history/writes/applied-20260903-125243.syx`). GUI:ts egen
  verifiering – SysEx-läsning direkt efter pushen – var bit-exakt: rätt
  frekvens, bandbredd och gain på alla sex poster i minnesdumpen. Men
  **PEQ-sidans display** (avläst manuellt strax efter) visade:

  | Post | Skrivet råvärde | Modellens Hz | **Display Hz** | Display bw/gain |
  |---|---|---|---|---|
  | L1 | `0x0405` | 52,78 | 53,250 | 37/60, −10 dB ✓ |
  | R1 | `0x0405` | 52,78 | **0** | 37/60, −10 dB ✓ |
  | L2 | `0x050F` | 74,11 | **0** | 34/60, −11 dB ✓ |
  | R2 | `0x050F` | 74,11 | **0** | 34/60, −11 dB ✓ |
  | L3 | `0x0903` | 165,28 | **68 018** | 28/60, −11,5 dB ✓ |
  | R3 | `0x0903` | 165,28 | **0** | 28/60, −11,5 dB ✓ |

  Bandbredd och gain (avrundade till enhetens 0,5 dB-raster) är rätt på
  **samtliga sex** poster – alltså sitter `PEQ_BIT_OFFSET`/`PEQ_REC_BITS` och
  postgränserna rätt, för de fälten läses ur exakt samma 32-bitarspost
  omedelbart efter frekvensfältet. Bara frekvensen är fel, och bara för post
  1–5; post 0 (L1) stämmer inom rimlig avrundning (53,25 vs modellens 52,78 –
  samma storleksordning som avrundningen i tidigare displayavläsningar, t.ex.
  0x0527 → 96,150 mot modellens 96,11).

  R1 har **exakt samma råa 13 bitar** som L1 (samma `rec`-dict, skrivet till
  två poster) men visar 0 där L1 visar rätt frekvens – det pekar mot att
  postens *plats* (index ≥ 1), inte bitmönstret i sig, är vad som ger fel
  resultat. Två hypoteser, ingen testad än:
  1. **Displayen har inte laddat om frekvensfältet** för rader som inte är
     markerade/senast visade efter en dump-inladdning, medan bw/gain av
     någon annan anledning redan är korrekta. Skulle försvinna av att
     bläddra till varje rad på PEQ-sidan (eller lämna sidan och gå
     tillbaka) utan att ändra något.
  2. **Frekvensfältet tolkas verkligen annorlunda för post ≥ 1** än post 0 –
     en skillnad som inte skulle synas i data-offset/gain-testerna ovan
     (som alla involverade destroyer-SKRIVNA poster, inte poster vi själva
     skrev till index > 0 i isolation) och som inte skulle försvinna av att
     bara bläddra.

  **Ingen kod är ändrad för det här** – `patch_dump`/`peq_freq_raw` är
  oförändrade sedan förra commiten. Nästa steg: `apply` med *bara* L1 satt
  (övriga `None`) för att bekräfta den ensam, sedan `apply` med *bara* L2
  satt för att se om post-index 2 i isolation beter sig likadant – det
  skiljer hypotes 1 från 2.

- **EQDESIGN.EXE disassemblerad** (archive.org, 846 kB, MFC/Win95, 6.8).
  Sändaren bygger `F0 00 20 32 <kanal−1> 01 …`; tolv kommandon; 7→8-packningen
  är identisk med vår bitström; minnesbilden är 10 + 104 + 76 + 100 × 104
  byte. Validerat mot `dumps/`: programnamn i klartext (`AUT O Q`,
  `BAS  ROCK`, `MOVIE` …), programnummer 9 = display 10, huvudets crossfade
  10 s / shelving 27 dB/okt, PEQ-posten byteinriktad (vår låg tre bitar snett
  – därav `aUT O Q`), frekvensen linjär i tjugondelar (96,150 Hz och 17/18/19
  kHz exakt). `33`-ramen är 32 = 0 dB, inte CC-skalan. Nytt `./run.sh raw
  <hex…>` för att prova kommandona mot enheten.
- **EQ-Design:s kommandon mot enheten** (`./run.sh raw`): `43` → `44 00` på
  under en sekund, device-ID `00` (CHANNEL 1) – identifieringen fungerar. `40`
  → hela dumpen (12112 byte; statusbyte `09`, program 10, crossfade 10 s),
  samma som `70 xx`. `44` och `41` ger inget svar – väntat, `44` är ett svar
  och `41` ett lägesbyte utan kvittens; om displayen bytte vid `41` är inte
  noterat. Arbetsbuffertens namn läses nu ` UT O Q` – första tecknet har
  blivit blankt sedan `aUT O Q`. `21 00` + enhetens egna 64 värden med 1 kHz
  vänster = `30` → displayen visade +8 dB, inget svar. Grafisk EQ går alltså
  att skriva via SysEx utan RCV MEMORY DUMP – CC kunde det redan band för band,
  det nya är att kommandofamiljen finns i enheten och att `22` (PEQ) därmed
  är värt att prova. **`22 00` + 32 packade byte** (6 poster ur dumpen med L1
  bytt till 100 Hz / 1,00 okt / −6 dB) → PEQ-sidan visade det direkt; en andra
  `22` lade tillbaka kurvans 53/74/166 Hz på båda kanalerna, utan de
  spillbitar i bandbyten som den gamla skrivaren lämnat. **`41` och `42`**
  byter EQ-/RTA-skärm på displayen. Inget av kommandona besvaras.
  Obs: både `21` och `22` skickades med `00` som programbyte medan enheten
  stod på program 10 – arbetsbufferten ändrades; om byten betyder något
  (skrev vi också i program 1?) är inte kontrollerat.

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
| Granulär SysEx | – | ja: EQ-Design:s `20`–`23`, `41`–`44` (6.8) – DSP8024 har en annan uppsättning (bilaga A) |
| PC-editor | – | EQ-Design (DSP8000 OS ≥ 2.0 / DSP8024 OS ≥ 1.1) |

OS-versionen visas kort i displayen vid påslag – **testenhetens version är
inte antecknad** (readme:s checklista). Firmware byttes via EPROM (socklad
DIP). Sista versionen är enligt EPROM-säljarna **2.0C**
([monotanz](https://monotanz.de/product/behringer-dsp-8000-version-2-0-c-upgrade-firmware-upgrade-eprom-os-for-dsp8000-download/),
[reverb](https://reverb.com/uk/item/30262743-behringer-dsp8000-version-2-0c-update-firmware-upgrade-eprom));
säljtexten tillskriver 2.0C bättre RTA-beräkning, global styrning av
gate/limiter, optimerad SysEx och stabilare minnesdumpar. Forumuppgift via
Gemini-rapporten ([audiofanzine](https://fr.audiofanzine.com/eq-graphique/behringer/ultra-curve-dsp8000/forums/t.297918,behringer-dsp8000-eq-design-logiciel.html)):
en tidig hårdvarurevision ska ha saknat MIDI-bestyckning och socklar för
delay-minne. 1996-manualen dokumenterar dock MIDI IN, så det gäller i så fall
bara de allra första exemplaren.

**Implementation chart** (DSP8024-manualen Tab 7.1, antas gälla vår enhet):
Control Change O/O, Program Change 0–99 O/O, System Exclusive O/O, allt annat
(noter, pitch bend, system common/realtime) X/X. Mode 1–4 (OMNI on/off).

**EQ-Design 1.0** (Behringer, daterad 1996-12-09) **finns på archive.org**:
[archive.org/details/eqdes](https://archive.org/details/eqdes), `eqdes.zip` →
`EQDESIGN.EXE` (846 kB). Enligt arkivets beskrivning "a real 32-bit
application" för Windows 95/NT som kräver DSP8000 OS ≥ 2.0 och ett
MPU-401-kompatibelt MIDI-interface. **Disassemblerad 2026-09-03** – protokollet
och minnesbilden står i 6.8. Den använder både hela dumpen (`4F`) och
granulära kommandon (`20`–`23`, `40`–`44`, `15`/`11`), så DSP8000 med OS ≥ 2.0
*har* granulär SysEx – bara inte DSP8024:s. Att köra den skarpt (Windows
98/XP i en VM med USB-MIDI genomkopplat) återstår.

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
- **EQ-Design 1.0** – [archive.org/details/eqdes](https://archive.org/details/eqdes)
  (`EQDESIGN.EXE`, 846 kB, 1996-12-09). Behringers Windows 95/NT-editor,
  disassemblerad 2026-09-03 – avsnitt 6.8, bilaga B.
- **Firmware 2.0C** – EPROM-säljare [monotanz.de](https://monotanz.de/product/behringer-dsp-8000-version-2-0-c-upgrade-firmware-upgrade-eprom-os-for-dsp8000-download/),
  [reverb.com](https://reverb.com/uk/item/30262743-behringer-dsp8000-version-2-0c-update-firmware-upgrade-eprom).
- Audiofanzine (franska): [EQ-Design-tråd](https://fr.audiofanzine.com/eq-graphique/behringer/ultra-curve-dsp8000/forums/t.297918,behringer-dsp8000-eq-design-logiciel.html),
  [win editor-tråd](https://fr.audiofanzine.com/eq-graphique/behringer/ultra-curve-dsp8000/forums/t.183432,ultracurve-dsp-8000-et-dsp-8024-win-editor.html)
  (hårdvarurevisioner, batteri, EQ-Design-krav).
- [gemini-report.md](gemini-report.md) – Gemini-genererad rapport (2026-09-03);
  inleds med en tabell över vad i den som strider mot våra fynd.
- `midi_captures.txt` – rå labblogg med de ursprungliga captures (senare
  poster rättar tidigare).
