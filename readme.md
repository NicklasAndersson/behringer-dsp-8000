# Behringer Ultra-Curve DSP8000 + REW: rumskorrigering och skriptad EQ-överföring

Sammanställd referens över enhetens funktioner, REW-mätning och skriptkedjan
för att flytta EQ-förslag från REW till DSP8000.

---

## 0. Kom igång (macOS)

macOS har inget `python`-kommando, bara `python3`. Homebrews Python tillåter
inte `pip install` globalt (PEP 668), så kör i en virtuell miljö:

```sh
cd ~/dev/ljud
python3 -m venv .venv
source .venv/bin/activate          # varje ny terminal
pip install -r requirements.txt    # requests (steg 1) + mido/python-rtmidi (steg 2)
```

Kör skriptet:

```sh
python rew_script.py               # med .venv aktiverad
# eller utan att aktivera:
.venv/bin/python rew_script.py
```

Eller allt på en gång (skapar venv, installerar, kör):

```sh
./run.sh                    # = rew_script.py, flaggor skickas vidare (--no-peq, --refine …)
./run.sh refine             # = rew_script.py --refine --yes (snabbt andra varv, ingen fråga)
./run.sh target                       # = rew_script.py --show-target (visa REW:s fältnamn)
./run.sh target K=V [K=V ...]         # = rew_script.py --target K=V ... --yes
./run.sh house-curve PATH|--clear     # = rew_script.py --house-curve PATH --yes / --clear-house-curve --yes
./run.sh send --dry-run     # = rew_to_dsp8000.py send --dry-run (ports/monitor/sysex/calibrate också)
./run.sh show               # = show_config.py
./run.sh test               # = test_rew_script.py (kräver varken REW eller enheten)
./run.sh help               # full kommandolista med beskrivningar
```

**Krav innan steg 1 fungerar:**
- REW körs på samma dator med API:t på (Preferences → API → "Start server",
  port 4735). Testa: `curl http://localhost:4735/version`
- En färdig mätning i REW (MANUAL-läge kör du sweep + "Match target" själv
  i REW:s GUI, skriptet läser bara ut resultatet)

`ModuleNotFoundError: No module named 'requests'` = du glömde aktivera
`.venv` eller köra `pip install requests`.

---

## 1. Om enheten

**Modell:** Behringer Ultra-Curve **DSP8000** (originalmodellen, *inte* PRO/DSP8024).
Skillnad mot PRO-versionen: 20-bit AD/DA (ej 24-bit), enklare MIDI (bara
hela minnesdumpen via SysEx — ingen granulär styrning som DSP8024, se
avsnitt 6), ingen praktiskt tillgänglig PC-editeringsmjukvara, delay/AES-EBU
är tillval snarare än standard. (1996-manualens MIDI-chart säger "ingen
SysEx" — vår enhet kör nyare OS och dumpar.)

### Grundfunktioner
- 31-bands grafisk EQ per kanal (ISO-tersband, 20 Hz–20 kHz)
- 3 fullparametriska filter per kanal (även använda av Feedback Destroyer)
- Real Time Analyzer (RTA), 31 tersband
- Feedback Destroyer (FB-D)
- Digital delay (tillval, "DELAY 8000"-kort)
- Digital AES/EBU in/ut (tillval, "AES 8000"-kort)
- 100 minnesplatser för sparade program

### IN/OUT-knappen (viktig för mätning)
| LED | Betyder |
|---|---|
| Lyser grönt | EQ aktiv, signalen bearbetas |
| Släckt | Bypass, signalen går orört igenom |
| Blinkar rött | Overflow/clipping internt i DSP:n — sänk ingångsnivå |

**Vid REW-mätning:** baseline-mätning ska göras med LED **släckt**,
korrigerad mätning med LED **tänd**.

---

## 2. Auto-Q (enhetens egen rumskorrigering)

### Förberedelser
- Mätmikrofon (t.ex. ECM8000) i **MIC INPUT** på baksidan (inbyggd +15V fantommatning)
- Placera mikrofonen på lyssningspositionen

### Rekommenderade RTA SETUP-värden
| Parameter | Värde |
|---|---|
| SOURCE | MICRO |
| GAIN MODE | AUTO |
| MIC CORR | NONE |
| AUTO-Q CURVE | FLAT |
| RTA OUTPUT | PINK |
| LEVEL | ca. -20 dB |

### Körning
1. RTA-läge → Softkey B (TOOLBOX) → Softkey A (AUTO-Q)
2. Välj vänster, höger eller båda kanaler
3. Enheten spelar rosa brus, mäter, justerar grafisk EQ automatiskt
4. Höjer aldrig ett band mer än 12 dB (skyddar högtalare från orealistiska boost-krav)
5. Börjar alltid från nuvarande EQ-inställning — förbehandla manuellt om du
   vill styra vilket område som justeras
6. Avbryt i förtid med OK-knappen, då behålls det som redan justerats
7. "NO SIGNAL DETECTED" → för svag mikrofonkänslighet, byt mick eller använd
   extern förförstärkare

**Begränsning:** grafisk EQ är ett trubbigt verktyg för smala rumsmoder i
basen. Använd de 3 parametriska filtren manuellt för sådana problem.

---

## 3. FB-D (Feedback Destroyer)

Automatisk detektering och dämpning av rundgång. Använder **samma tre
parametriska filter** som du annars kan använda för manuell rumskorrigering
— de konkurrerar om samma resurs.

- **AUT** (sökläge): filtren letar kontinuerligt efter ny feedback
- **SGL** (låst läge): filtret fixeras permanent på hittad frekvens, bra för
  statiska problem
- Fungerar bäst på dynamiskt signalinnehåll (tal, sång) — inte stationära
  toner (synth, flöjt)
- Primärt tänkt för PA/scenbruk, mindre relevant vid ren hemma-rumskorrigering

---

## 4. Verifiering med REW

### Uppkoppling
```
Dator (REW) → Ljudkortets utgång → DSP8000 analog in
DSP8000 analog out → Förstärkare → Högtalare
Mätmikrofon → Dator (REW), på lyssningsposition
```

### Grundinställningar i REW
- **Soundcard preferences:** rätt in/out, 48 kHz för att matcha DSP8000
- **Mic-kalibrering:** ladda .cal-fil om UMIK-1 eller liknande används
- **Check Levels:** justera tills input ligger runt **-12 till -18 dB**
- **Sweep length:** 1M eller längre (bättre lågfrekvensupplösning)
- **Frekvensspann:** 10–20 Hz till 20 000 Hz

### Smoothing (visningsinställning, ändrar inte data)
| Nivå | Användning |
|---|---|
| 1/3 oktav | Motsvarar DSP8000:s 31 tersband — bra för jämförelse |
| 1/6 oktav / Var | Bra allmän känsla för rummet |
| 1/12–1/24 / None | Rådata, bäst för att se smala rumsmoder i basen |

### Arbetsflöde
1. Mät **baseline** utan EQ (bypass, LED släckt)
2. Aktivera Auto-Q-korrigeringen (LED tänd)
3. Mät igen, jämför kurvorna i REW

---

## 5. Generera EQ-förslag i REW (Match Target)

> Hela det här flödet går att skripta via REW:s API — det är precis vad
> `rew_script.py` gör (se avsnitt 7). Nedan är GUI-motsvarigheten och
> förklaringen av vad målkurvan ska vara.

### Kör Match Target (GUI)

1. Markera mätningen i vänsterlistan → klicka **EQ** i verktygsraden
   (öppnar EQ-fönstret).
2. Panel **Equaliser** (uppe till höger): välj equalizer-typ.
   - Parametriska DSP8000-filtren → **Generic**, sätt **Max filters = 3**.
   - 31-bandaren → också **Generic**, men lägg in de 31 fasta frekvenserna
     med Q 4.32 (se nedan).
3. Panel **Target Settings**: ställ in målkurvan (nästa avsnitt).
4. Panel **Filter Tasks**:
   - **Match range**: t.ex. 20–300 Hz (bara basen — se nedan).
   - **Individual max boost** / **Overall max boost**: håll lågt, 0 till +3 dB.
   - **Max cut**: generöst, -12 till -20 dB.
   - Klicka **Match response to target**.
5. Filtren dyker upp i panelen **EQ Filters** — det är listan `rew_script.py`
   läser (`GET /measurements/{id}/filters`).

### Vad target ska vara

**Grundform:** rak linje på högtalarnas mellanregisternivå. REW sätter
**Target level** automatiskt; dra ner den några dB manuellt så korrigeringen
blir mest *sänkningar*. Boosta aldrig upp djupa nullor — de är
positionsberoende utsläckningar, EQ fixar dem inte och du bränner headroom.

**Tilt / house curve:** rakt uppmätt i rummet låter ljust. Lägg en svag
nedåtlutning:

- ca **-0,8 till -1 dB/oktav** från ~1 kHz och uppåt (slutar runt -4 till
  -5 dB vid 20 kHz), eller
- ladda en färdig house curve-fil (Target Settings → *House curve*).

**Bas:** valfritt, +3 till +6 dB mjuk höjning under ~80–120 Hz om du gillar
fylligare bas hemma. Sätt **LF cutoff** i target till vad högtalaren faktiskt
klarar — begär inte +12 dB vid 25 Hz på en liten låda.

**Frekvensområde att EQ:a:** bara upp till rummets transitionsfrekvens,
~200–400 Hz i ett normalt rum. Ovanför det gör enpunkts-EQ mer skada än
nytta — låt Auto-Q/grafiska EQ:n eller ingenting sköta diskanten.

### Sammanfattning för din kedja

| Mål | Match range | Max filters | Max boost |
|---|---|---|---|
| 3 parametriska (rumsmoder) | 20–300 Hz | 3 | +3 dB |
| 31-band grafisk | 20 Hz–20 kHz | (31 fasta) | +6 dB |

### 31-band grafisk EQ (Generic-metoden)

REW har ingen dedikerad "Match graphic EQ"-knapp för 31-bands EQ:er.

1. Equaliser → **Generic**, Filter type **PK**
2. **Q = 4.32** (motsvarar exakt 1/3-oktavs bandbredd)
3. Ange DSP8000:s 31 ISO-band manuellt som fasta frekvenser
4. REW räknar ut gain per band

**Enklare alternativ:** kör RTA i REW (Spectrum-fliken, 1/3-oktav) medan du
justerar DSP8000:s band live och ser resultatet i realtid.

### DSP8000:s 31 ISO-tersbandsfrekvenser
```
20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400,
500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000,
6300, 8000, 10000, 12500, 16000, 20000  (Hz)
```

---

## 6. MIDI-implementation (DSP8000, ej PRO)

Vår enhet kör ett **nyare OS** än 1996-manualen beskriver: justerbar
controller-offset, SysEx-dump, MIDI OUT aktiv. Full jämförelse mellan
OS-nivåer och DSP8024 finns i `dsp8000_midi_webbresearch.md`.

### Verifierat mot enheten 2026-09-02 — CC-styrning FUNGERAR

**MIDI‑sidan (SET UP → PAGE 2), inställningar som funkar:**

| Fält | Värde | Not |
|---|---|---|
| MIDI | ON | |
| CHANNEL | 1 | |
| OMNI‑MODE | ON | tar bort kanal‑frågan; funkar även med OFF om kanal matchar |
| CNTL | **RCV = 0**, SND = 1 | **inte ON/OFF — ett tal = Controller Offset (0–64)**. RCV och SND har varsitt |
| PROG | RCV ON, SND ON | |
| EXCL | RCV ON, SND ON | |

| Funktion | Status |
|---|---|
| Program Change (0–99) | **fungerar** |
| CC → grafisk EQ | **fungerar** — `CC 17 = 96` gav `L: +8 dB` på 1 kHz |
| SysEx: enheten skickar full dump | **fungerar** — via fader‑rörelse, `SND MEMORY DUMP`, eller en SysEx‑förfrågan (se *Returväg* nedan). Kräver **båda** MIDI‑kablarna inkopplade |

### CC-mappning (bekräftad, offset 0)

| CC | Styr |
|---|---|
| 0–30 | vänster 31 band: 20 Hz = 0 … 1 kHz = 17 … 20 kHz = 30 |
| 31 | vänster master |
| 32–62 | höger 31 band |
| 63 | höger master |

`CC_OFFSET` i `dsp8000.py` måste = enhetens **CNTL RCV**‑tal. Testenheten: 0.
Med **Stereolink** på räcker vänsterkanalen (`--channel left`).

**dB → CC (verifierat):** `CC = 64 + dB × 4` — 64 = 0 dB, 96 = +8 dB.
Nominellt 0,25 dB/CC-steg, men GEQ:n har 0,5 dB-upplösning så enheten rundar.
`CC 0–127` = −16 … +15,75 dB (+16 dB skulle vara CC 128 → klipps till 127).
`dsp8000.db_to_cc` gör detta.

### Returväg / SysEx (DSP8000 → dator)

Fungerar (`rew_to_dsp8000.py monitor`) med **båda kablarna inkopplade**
(AudioBox OUT→DSP8000 IN och DSP8000 OUT→AudioBox IN):

- Enheten ekar **inte** på CC‑mottagning, bara på fysisk fader‑rörelse,
  `+` på **SND MEMORY DUMP**, eller en **SysEx‑förfrågan** (se nedan).
- **SysEx‑förfrågan (verifierat 2026‑09‑02, `rew_to_dsp8000.py sysex`):**
  `F0 00 20 32 00 01 70 <xx> F7` med *valfri* `xx` (`01`, `10 1F`, `64` …)
  → enheten svarar med **hela minnesdumpen** (`… 4F 0A …`, 12110 byte,
  ~5 s). Modellbyte `0E` (DSP8024/ADRStudio) ger **inget svar**, och
  ADRStudios realtidsskrivning `10h` gör **inget** (testad 2026‑09‑02 —
  dumpen ändras inte). DSP8000:s OS kan alltså bara dumpa allt. Detaljer +
  ADRStudio:s DSP8024‑protokoll: `dsp8000_midi_webbresearch.md`.
  Praktisk vinst: dumpen kan hämtas **utan fader‑nudge**.
- Dumpen = 10‑byte header (`00 20 32 00 01 4F <sub> 20 00`, `4F` = dump;
  `sub` = `12` från knappen, `0A` från `70`‑förfrågan) + 12100 databyte,
  alla < 128 (7‑bit‑safe) men **bit‑packade**. ~95 % nollor i de committade
  dumparna (nästan tom enhet).
- **GEQ‑blocket är avkodat** (verifierat mot enheten 2026‑09‑02 med
  `rew_to_dsp8000.py probe`, se `syx_tools.py`): databyten packas upp
  **MSB‑först** till en bitström; från **bit‑offset 373** ligger **64
  tecknade 8‑bitarsvärden** — 31 vänster band (20 Hz–20 kHz), vänster master,
  31 höger band, höger master. Bandvärde = **CC − 64** = kvarts‑dB‑steg
  (−64…+63 ⇒ **−16,00…+15,75 dB**, `dB = värde / 4`). Samma layout för
  `4F 0A` och `4F 12`.
  ```sh
  python syx_tools.py eq dsp8000_sysex_ondemand.syx       # GEQ-band + PEQ-filter
  python syx_tools.py diff före.syx efter.syx             # råa byte + GEQ/PEQ som ändrats
  python rew_to_dsp8000.py readback                       # hämta från enheten, skriv ut
  ```
  De committade `dsp8000_sysex_m16db.syx` / `_p16db.syx` är byte‑identiska
  men avkodas till en **ren +16 dB‑dump** (alla band `64/4`), och `_0db.syx`
  till ren 0 dB. Den gamla "8 byte/band med bitvikter"‑tolkningen och
  slutsatsen "stor överföringsbugg" var **avkodningsfel**, inte tappade CC.
- **PEQ‑blocket är avkodat** (verifierat mot enheten 2026‑09‑02 med
  `probe --manual`): **6 poster à 32 bitar** i samma MSB‑packade bitström,
  från **bit‑offset 87**, ordning **L1 R1 L2 R2 L3 R3**. Per post:
  frekvens (11 bit, `f = 20·10^(raw/640)` Hz, 20 Hz = 0),
  bandbredd (10 bit, `(raw+1)/60` oktav),
  gain (11‑bit tvåkomplement, `dB = raw/16`, dvs 1/16 dB i dumpen).
  **OFF = posten helt noll.** Läget **PAR/AUT/SGL lagras inte** i dumpen (bara
  filtret). `syx_tools.py eq` och `readback` visar de 6 filtren.
- Resten (master‑skala, delay, gate, limiter, 100 program) är **inte
  kartlagt**. Working buffer ligger i data‑offset ~0–27 (PEQ + limiter/gate).
  Master‑värdet läses rått (verkar 0‑centrerat, skalan ej verifierad).
  `probe --manual` kartlägger fler delar: dumpa, ändra EN sak på enheten, dumpa, diff.
- Fader‑rörelse ger dessutom en **direkt läsbar** 64‑byte GEQ‑status:
  `F0 00 20 32 00 01 33 09 <32 vä> <32 hö> F7`, position 0–30 = band,
  31 = master, `64` = 0 dB. Kräver en fader‑nudge för hand.

**Slutsats:** skriv GEQ via CC (funkar, kalibrerat). `send --verify` hämtar
dumpen efteråt och kollar att varje band landade (fångar tappade CC utan
sweep). Verifiera det **akustiska** resultatet med en **REW‑sweep** — den
visar vad rummet gör, inte bara vad enheten tror. PEQ går att **läsa** ur
dumpen (`readback`) men inte skriva via MIDI.

### Parametrisk EQ via MIDI
**Läsning:** de 6 filtren (frekvens/bandbredd/gain) avkodas ur den packade
dumpen — se avsnitt 6 och `syx_tools.py eq` / `rew_to_dsp8000.py readback`.
**Skrivning:** går inte. Realtids‑CC för PEQ finns inte.
DSP8024 har realtids‑**SysEx** för PEQ (ADRStudio) — men vår DSP8000 svarar
inte på det protokollet (testat 2026‑09‑02, se `dsp8000_midi_webbresearch.md`).
Reservväg: ställ in PEQ för hand → spara program → Program Change.

### Källor

- **DSP8000 User Manual V1.3 (1996)** — [archive.org](https://archive.org/details/behringer-ultra-curve-dsp-8000-user-manual-ver-1-3)
  (OCR-text via `..._djvu.txt`), spegel: [behringer-vintage.com](http://www.behringer-vintage.com/Anleitungen/DSP8000_V1.3_1996_ENG.pdf).
  Beskriver den **äldre** MIDI-implementationen (fast CC 64–127, ingen SysEx).
- **DSP8024 PRO-manual (v1.2, 2001)** — tysk textbaserad PDF på
  [tonkreis.de](http://www.tonkreis.de/D%20A%20T/Bedienungsanleitungen/Behringer%20ULTRA%20CURVE%20-%20DSP%208000.pdf),
  engelsk OCR på [archive.org](https://archive.org/details/manualzilla-id-7376194).
  Matchar vår enhets MIDI-beteende (justerbar offset, SysEx, memory dump).
- **Sound on Sound-recension** — [soundonsound.com](https://www.soundonsound.com/reviews/behringer-ultra-curve)
  (påstod "no data output over MIDI" — gällde 1996-OS:et, vår enhet dumpar).
- **ADRStudio: SysEx-kommandon för DSP8024** — [adrstudio.com/8024.php](https://adrstudio.com/8024.php).
  Fungerar **inte** på vår DSP8000 (se *Returväg* ovan).
- **`dsp8000_midi_webbresearch.md`** — full sammanställning: alla MIDI SETUP-fält,
  implementation charts, de tre MIDI-OS-nivåerna, ADRStudio-protokollet, testresultat.
- `docs/keiths-blog-dsp8024-firmware-upgrade.html` — sparad kopia (Wayback)
  av Keith Neufelds blogg om DSP8024: Auto‑Q‑arbetsgång, brus/pop‑problem,
  firmware 1.1→1.3 via ny 27C256‑EPROM (gäller **DSP8024**, inte DSP8000).

---

## 7. Skriptkedjan

| Fil | Gör | Status |
|---|---|---|
| `dsp8000.py` | modell av enheten (31 ISO-band, gain-intervall, CC-mappning, `db_to_cc`) | klar |
| `rew_script.py` | REW → `rew_eq_suggestion.json` (parametriska filter + 31 bandvärden) | klar |
| `show_config.py` | JSON → `dsp8000_config.html`, visar vad som ska ställas in | klar |
| `rew_to_dsp8000.py` | skickar de 31 banden som MIDI CC + `readback`/`probe`/`send --verify` | CC-vägen + GEQ-återläsning verifierad |
| `dsp8000_gui.html` | manuell EQ-kontroll i webbläsaren (Web MIDI), utan REW | klar |
| `syx_tools.py` | `hex`/`eq`/`diff` för `.syx`-dumpar — GEQ- + PEQ-blocken avkodade (stdlib) | klar |
| `test_rew_script.py` | självtester utan REW/enhet (`./run.sh test`) | klar |

### Steg 1: `rew_script.py`
Kräver **inte** REW Pro. Du kör själv sweepen i REW (vill du göra med koll
på nivåer ändå). Sedan:

1. välj mätning i listan (eller `--measurement ID`; `--yes` hoppar över frågan)
2. skriptet sätter equaliser → Generic och match target settings
   (`20–300 Hz`, `individualMaxBoost 3 dB`, `overallMaxBoost 0 dB`), kör
   `Calculate target level` + `Match target` — allt via API. **Målkurvans
   form** (tilt/house curve/LF cutoff, avsnitt 5) sätts som *default* inte
   av skriptet — men går att sätta via API i stället för att klicka i REW:s
   GUI varje varv, se `--show-target`/`--target`/`--house-curve` nedan
3. läser ut de parametriska filtren, **behåller de 3 PK‑filter med störst
   |gain|** (`dsp8000.PEQ_COUNT`; shelf‑filter kastas, de kan inte göras på
   enheten) och skriver tillbaka dem till REW — DSP8000 har bara 3 PEQ, och
   `/eq/frequency-response` måste spegla exakt det som hamnar på enheten
4. beräknar 31 grafiska bandvärden: `(target − respons)` med 1/3-oktavs
   utjämning vid ISO-frekvenserna, centrerat kring median, klippt till
   `SAFE_BOOST_DB` (+3) upp / −12 ner
5. sparar allt till `rew_eq_suggestion.json`

**Ingen dubbel-EQ, ingen underkorrigering:** med PEQ räknas de grafiska banden
mot `/eq/frequency-response` (responsen *efter* de 3 filtren) — grafiska EQ:n
städar upp exakt det som 3 PEQ inte hann med. Med `--no-peq` räknas de mot rå
`/frequency-response` och gör allt själva.

Svarar du `n` på "Kör Match target via API nu?" antas du redan ha kört
matchningen i REW:s GUI.

`--no-peq`: hoppa över de parametriska filtren helt, bara 31-bands grafisk EQ
(kör `Calculate target level` men inte `Match target`). `peq_filters` blir tom.

`--refine` (**andra varvet**): mät om *med* EQ:n aktiv (LED tänd), välj den
nya mätningen och kör `rew_script.py --refine`. Residualen (target − uppmätt,
mot rå `/frequency-response`) adderas ovanpå bandvärdena i befintlig
`rew_eq_suggestion.json`; PEQ‑listan följer med oförändrad. Grannband i en
1/3‑oktavs‑EQ läcker in i varandra, så första varvets (target − respons)
överkorrigerar alltid lite — ett eller två refine‑varv är hur man konvergerar.

**Sätta målkurvan via API (snabbare iteration, slipp REW:s GUI varje varv):**

```sh
python rew_script.py --show-target                     # skriv ut REW:s riktiga fältnamn, avsluta
python rew_script.py --target lowFreqCutoffHz=25 --target slopedBOct=1.0 --yes
python rew_script.py --house-curve /sökväg/till/kurva.txt --yes
python rew_script.py --clear-house-curve --yes
```

`--target KEY=VÄRDE` (kan upprepas) läser mätningens nuvarande
`target-settings` (GET), skriver in nycklarna du anger ovanpå (allt annat
REW redan satt bevaras) och skickar tillbaka (POST) — innan
`Calculate target level` körs. Fälten är **REW:s egna** och API:t
dokumenterar dem inte i klartext (`shape`, `lowFreqCutoffHz`, slopes,
crossover enligt tabellen i avsnitt 7, men den exakta stavningen kan skilja
mellan REW-versioner) — kör `--show-target` **en gång** mot din egen
REW-installation för att se de riktiga namnen i stället för att gissa.
Värden typas automatiskt: `25` → int, `1.0` → float, `true`/`false` → bool,
annat → sträng.

`--house-curve PATH` / `--clear-house-curve` / `--house-curve-log-interp
{true,false}` styr `/eq/house-curve` (globalt, inte per mätning) —
log-interpolation sätts alltid före filen, i den ordning REW:s dokumentation
anger. Alla tre går att kombinera med `--target`, `--refine` och den
vanliga körningen i samma kommando.

Beroenden: `pip install requests`

### Steg 1b: `show_config.py`
Läser `rew_eq_suggestion.json`, skriver `dsp8000_config.html` (genererad,
gitignorerad) och öppnar den. Tabell över de 31 banden (målförstärkning,
stapel ±16 dB, CC-nummer per kanal, CC-värde) + de ≤3 parametriska filtren
med Q **och** bandbredd i oktaver (det är oktaver enheten vill ha). Ren stdlib —
ingen GUI-toolkit (Homebrews python 3.14 har inte tkinter, och en
HTML-sida räcker för att bara visa värden). `--no-open` hoppar över
webbläsaren.

### Egen equaliser-modell i REW?
**Går inte.** REW:s equaliser-lista är inbyggd i appen; API:t kan bara
*välja* `{manufacturer, model}`, inte definiera en ny. Närmast är
`Generic/Configurable PEQ`. Därför modellerar vi DSP8000 i `dsp8000.py`
och mappar REW:s korrigeringskurva mot den själva (steg 1 punkt 4).

### REW HTTP-API (verifierat mot 0.9.0 / V5.40 beta 101)

Swagger-UI + spec: öppna `http://localhost:4735/` i webbläsaren.
Slå på servern i REW: Preferences → API → "Start server".

| Endpoint | Gör |
|---|---|
| `GET /version` | `{"message": "5.40 Beta 101 API 0.9.0"}` |
| `GET /measurements` | objekt `{"1": {...}}`, nyckeln är id (index från 1) |
| `GET/POST /measurements/{id}/equaliser` | `{"manufacturer": "Generic", "model": "Generic"}` |
| `GET/POST/PUT /measurements/{id}/target-settings` | målkurvan (`shape`, `lowFreqCutoffHz`, slopes, crossover) |
| `GET/POST/PUT /eq/match-target-settings` | `startFrequency`, `endFrequency`, `individualMaxBoostdB`, `overallMaxBoostdB`, `flatnessTargetdB`, shelf-flaggor |
| `GET/POST/DELETE /eq/house-curve` | house curve-fil |
| `POST /measurements/{id}/eq/command` | `{"command": "..."}` — kör asynkront |
| `GET /measurements/process-result` | `{"processName": "Match target ID N", "message": "Completed"}` — pollas för att veta när kommandot är klart |
| `GET/POST/PUT /measurements/{id}/filters` | filterlista; satta filter har `type` (`PK`…), `frequency`, `gaindB`, `q` |
| `GET /measurements/{id}/eq/frequency-response` | förväntad kurva efter EQ |
| `GET /measurements/{id}/target-response` | målkurvan som frekvenssvar |

Giltiga EQ-kommandon (`/eq/command`): `Calculate target level`,
`Match target`, `Optimise gains`, `Optimise gains and Qs`,
`Optimise gains, Qs and Fcs`, `Generate predicted measurement`,
`Generate filters measurement`, `Generate target measurement`.

**Filterantal:** styrs av equaliser-modellen, inte av API-parametrar.
`Generic/Generic` ger upp till 22 filter. Ingen API-väg att tvinga exakt 3 —
`rew_script.py` behåller själv de 3 största och skriver tillbaka dem (steg 1,
punkt 3) så resten av kedjan stämmer.

**Sweep-triggning via API kräver REW Pro.** `POST /measure/command` finns
och skulle utlösa sweepen (skickar brus genom högtalarna, kräver att nivåer
redan är inställda) — men REW:s egen dokumentation säger uttryckligen att
"to control REW via the API to make automated sweep measurements requires a
Pro upgrade license". Allt annat `rew_script.py` gör (läsa mätningar, sätta
equaliser/target settings, köra `Calculate target level`/`Match target`,
läsa/skriva filter) är **inte** licensbelagt — bara själva sweep-triggningen.
Kör sweepen i GUI:t (gratisversionen räcker för hela resten av kedjan).

### Steg 2: `rew_to_dsp8000.py` *(CC-vägen verifierad mot enheten 2026-09-02)*
Läser `rew_eq_suggestion.json` och skickar de 31 bandvärdena som MIDI CC.

| Kommando | Gör |
|---|---|
| `python rew_to_dsp8000.py ports` | listar MIDI-portar |
| `python rew_to_dsp8000.py monitor` | lyssnar på vad DSP8000 skickar (retur­väg); fader-framen skrivs ut i dB |
| `python rew_to_dsp8000.py sysex [--write-test]` | frågar enheten via SysEx, sparar svaret som `.syx` — bekräftar att bara hela dumpen kommer tillbaka (se avsnitt 6) |
| `python rew_to_dsp8000.py readback` | hämtar dumpen på begäran och skriver ut de 31+31 grafiska banden + de 6 PEQ-filtren (ändrar inget) |
| `python rew_to_dsp8000.py grab FIL.syx` | hämtar en dump och sparar (ändrar inget) — bygg upp ett bibliotek av kända tillstånd att diffa |
| `python rew_to_dsp8000.py probe [--band 1000] [--value 127] [--channel left]` | kontrollerad capture: dumpa, sätt ett band via CC, dumpa igen, visa vilka byte + band som ändrades. Återställer bandet till 0 dB (`--no-restore` låter bli) |
| `python rew_to_dsp8000.py probe --manual` | som `probe` men utan CC: pausar medan du ändrar EN sak på enheten (PEQ, delay, gate …), sedan diff. Så kartläggs delarna som inte går via MIDI |
| `python rew_to_dsp8000.py calibrate [--band 1000]` | verifierar `db_to_cc` mot displayen |
| `python rew_to_dsp8000.py send --dry-run` | visar alla CC utan att skicka |
| `python rew_to_dsp8000.py send [--channel left\|right\|both] [--midi-channel N] [--verify]` | skickar (frågar "ja" först). `--verify` hämtar dumpen efteråt och rapporterar band som inte landade |

`send` skickar **båda kanalerna** som default (Stereolink av). `--channel left`
räcker om Stereolink är på.

Före skarp körning:

- **`dsp8000.CC_OFFSET`** måste = enhetens `CNTL RCV`-tal (MIDI-sidan). 0 på
  testenheten. Var den ursprungliga buggen.
- parametriska filter går **inte** via MIDI — `show_config.py` visar dem,
  ställ in för hand
- `send --verify` (eller `readback`) läser tillbaka de grafiska banden ur
  dumpen och fångar tappade CC direkt (avsnitt 6). Det **akustiska**
  resultatet verifieras fortfarande bäst med en REW-sweep

Beroenden: `pip install mido python-rtmidi` (funkade direkt på python 3.14).
Utan mido går fortfarande `test_rew_script.py` att köra.

### Manuell kontroll utan REW: `dsp8000_gui.html`
Öppna filen i **Chrome/Edge** (Web MIDI). Blockeras den från `file://`:
`python3 -m http.server` → `http://localhost:8000/dsp8000_gui.html`.

Exponerar allt som går via MIDI:

- 31-bands GEQ, per band ±16 dB, läge Länkad / Endast L / Endast R
- **"Skicka alla"** – återsänder alla band (drag-events tappas ibland)
- masterfaders L/R (0–127, rå — dB-skalan okänd)
- programval (Program Change 0–99)
- MIDI-kanal + Controller offset (måste matcha enhetens `CNTL RCV`)
- "Ladda REW-JSON" drar in både grafiska band och **parametriska filter** från
  `rew_eq_suggestion.json` — PEQ-tabellen visar frekvens/gain/Q/bandbredd (okt)
  och hur man ställer dem för hand (de går inte via MIDI)

Inte via MIDI (ställ på enheten, spara program, hämta i GUI:t): parametriska
filter, delay, gate, limiter, feedback destroyer, Auto-Q, stereolink.

Reglagen sparas i `localStorage` — överlever refresh, skickas inte automatiskt
(tryck "Skicka alla" efter omladdning).

### Rekommenderad ordning att köra i

1. Kör en sweep i REW (bypass, LED släckt) → kör `rew_script.py` → `rew_eq_suggestion.json`
2. Kör `show_config.py` → se vad som ska ställas in
3. (Annan enhet än testenheten? Kör `rew_to_dsp8000.py calibrate` en gång
   och kolla att `CC = 64 + dB×4` stämmer och att `CC_OFFSET` = `CNTL RCV`.)
4. Kör steg 2 → skriv de 31 banden till DSP8000 via MIDI
5. Ställ in de parametriska filtren för hand, spara som program
6. Verifiera med en ny REW-sweep (LED tänd) — enheten kan inte bekräfta sig
   själv via MIDI
7. Kör `rew_script.py --refine` på den nya mätningen → skicka igen (steg 4)
   → mät igen. Ett–två varv räcker normalt.

---

## 8. Kända begränsningar att komma ihåg

- DSP8000:s minnesdump är bit‑packad. **GEQ‑ och PEQ‑blocken är avkodade**
  (avsnitt 6), så `send --verify` / `readback` fångar tappade CC och visar
  PEQ‑filtren. Delay/gate/limiter/master‑skala/de 100 programmen är **inte**
  kartlagda. Det **akustiska** resultatet verifieras med en REW‑sweep
- Parametrisk EQ kan **läsas** ur dumpen men inte skrivas via MIDI — ställ
  för hand, spara som program, Program Change
- MIDI CC→dB **verifierat**: `CC = 64 + dB×4`. `CC_OFFSET` måste matcha
  enhetens `CNTL RCV`‑tal
- Returväg kräver **båda MIDI‑kablarna** (AudioBox OUT→DSP8000 IN *och*
  DSP8000 OUT→AudioBox IN). Verifierat 2026‑09‑02 — tidigare gissning om att
  en kabel räckte var fel. Enheten ekar inte CC‑mottagning, bara
  fader‑rörelse/dump/förfrågan
- Hela EQ-kedjan (target settings + Match target + läsa filter) går via
  REW:s API, verifierad mot 0.9.0 — kräver **inte** REW Pro
- Bara **sweepen** körs manuellt i GUI:t (medvetet — nivåer)
- REW:s API kan inte begränsa matchningen till 3 filter; `rew_script.py`
  behåller de 3 största och räknar grafiska EQ:n mot dem
- De 31 bandvärdena bygger på en **enpunktsmätning** — boost kapas till
  +3 dB (`dsp8000.SAFE_BOOST_DB`) med flit, fyll aldrig upp nullor. Mät
  på fler positioner och medelvärdesbilda i REW innan matchningen
- Bandvärdena räknas **band för band** utan modell av hur enhetens
  1/3‑oktavsfilter överlappar — därför överkorrigerar första varvet, och
  därför finns `--refine` (mät med EQ:n på, addera residualen)
- Masterfaderns CC‑skala är **inte verifierad** (troligen samma som banden)

---

## 9. Genomgång 2026-09-02: buggar som lagades

Helhetsgranskning av kodbasen. Inget av detta kräver ombyggnad, men värt att
känna till om du satt egna skript ovanpå någon av filerna.

- `test_rew_script.py` kraschade helt utan `mido` installerat, eftersom
  `rew_to_dsp8000.py` importerade det på modulnivå. Importen är nu valfri
  (`mido = None` om den saknas) — MIDI‑kommandona kräver den fortfarande,
  men testsviten och `fit_scale` gör det inte.
- `keep_top_filters` (`rew_script.py`) kunde få `KeyError` om REW:s Match
  target gav ett shelf‑filter (LS/HS saknar `q`), och antog alltid 20
  filterplatser. Nu behålls bara `PK`‑filter (shelf kan inte göras på
  DSP8000:s PEQ ändå) och antal platser hämtas från REW.
- `_decode_curve` kraschade på `NaN`/`inf`‑värden utanför mätningens
  frekvensområde (median och `round()` går sönder på `NaN`). Sådana punkter
  filtreras bort innan de används.
- `dsp8000_gui.html`: PEQ‑tabellen försvann efter en sidladdning eftersom
  `restore()` inte satte tillbaka `peqCache` — nästa `save()` skrev då över
  den sparade listan med en tom. "Ladda REW‑JSON" och "Nolla alla band"
  skickade dessutom 62 CC i en klump utan mellanrum, samma buffertöverbelastning
  som `midi_captures.txt` redan identifierat för "Skicka alla" (nu åtgärdad
  där) — båda går nu via samma schemalagda utskick. MIDI‑kanal och
  programnummer klipps till giltiga intervall (1–16 resp. 0–99).
- `show_config.py`: stapelrubriken sa `±12` men skalan var faktiskt `±16`
  (`dsp8000.GRAPHIC_MAX_BOOST_DB`); texten kallade CC‑skalan "okalibrerad"
  trots att den är verifierad mot enheten (avsnitt 6).
- Readme motsade sig själv på två ställen: avsnitt 6 säger att returvägen
  fungerar med båda kablarna i, avsnitt 8 sa tidigare att den kräver bara
  en. Och steg 1 påstod att skriptet sätter REW:s "target settings"
  (målkurvans form) — det gjorde det inte, bara match‑target‑settings
  (matchningsområde/max boost); formen ställdes i REW:s GUI. Sedan
  `--show-target`/`--target`/`--house-curve` (nedan) går den formen också
  att sätta via API, men fortfarande inte som default.
- De committade `dsp8000_sysex_m16db.syx` / `_p16db.syx` är byte‑identiska
  (en av ±16‑captures gick aldrig igenom) — men avkodas **rätt** till en ren
  +16 dB‑dump, `_0db.syx` till ren 0 dB. Den tidigare slutsatsen "stor
  överföringsbugg, de flesta CC:n landade aldrig" var ett **avkodningsfel**
  i den gamla 8‑byte/band‑tolkningen, inte tappade CC.

Nytt sedan förra versionen: `rew_script.py --refine` (andra varvet, se
avsnitt 7 och 8), `dsp8000.cc_to_db`/`dsp8000.q_to_octaves`, `syx_tools.py`
för att analysera `.syx`‑dumpar, `requirements.txt`, samt `run.sh send|show|test`
som genvägar till `rew_to_dsp8000.py`/`show_config.py`/`test_rew_script.py`.

Nytt i denna version:
- `rew_script.py`: `--show-target`/`--target KEY=VÄRDE`/`--house-curve`/
  `--clear-house-curve`/`--house-curve-log-interp` (avsnitt 7) — sätter
  målkurvans form via API i stället för REW:s GUI.
- **GEQ‑ + PEQ‑dumpen avkodad** (avsnitt 6): `syx_tools.py eq`/`diff` och
  `rew_to_dsp8000.py readback` läser de 31+31 grafiska banden och de 6
  PEQ‑filtren ur dumpen. GEQ: MSB‑packad bitström, offset 373, 64 × 8‑bit
  tecknat, `dB = v/4`. PEQ: 6 × 32‑bitarsposter från offset 87 (L1 R1 L2 R2
  L3 R3), freq `20·10^(raw/640)` Hz, bw `(raw+1)/60` okt, gain 11‑bit
  2‑komp `dB = raw/16`; läget PAR/AUT/SGL lagras inte.
- `rew_to_dsp8000.py grab FIL.syx` (spara en dump), `probe --manual`
  (kartlägg delay/gate m.m. — pausa medan du ändrar på enheten),
  `send --verify` (läs tillbaka efter skrivning). ADRStudios realtidsskrivning
  `10h` testad och **död** på DSP8000.
