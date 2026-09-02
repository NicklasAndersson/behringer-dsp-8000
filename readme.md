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
pip install requests               # steg 1
pip install requests mido python-rtmidi   # steg 2 (när det finns)
```

Kör skriptet:

```sh
python rew_script.py               # med .venv aktiverad
# eller utan att aktivera:
.venv/bin/python rew_script.py
```

Eller allt på en gång (skapar venv, installerar, kör):

```sh
./run.sh              # flaggor skickas vidare, t.ex. ./run.sh --no-peq
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

## 6. MIDI-implementation (DSP8000, grundmodell)

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
| SysEx: enheten skickar full dump | sett (fader‑rörelse) men returvägen krånglar nu, ej återupptagen |

### CC-mappning (bekräftad, offset 0)

| CC | Styr |
|---|---|
| 0–30 | vänster 31 band: 20 Hz = 0 … 1 kHz = 17 … 20 kHz = 30 |
| 31 | vänster master |
| 32–62 | höger 31 band |
| 63 | höger master |

`CC_OFFSET` i `dsp8000.py` måste = enhetens **CNTL RCV**‑tal. Testenheten: 0.
Med **Stereolink** på räcker vänsterkanalen (`--channel left`).

**dB → CC (verifierat):** `CC = 64 + dB × 4` — 64 = 0 dB, 96 = +8 dB,
0,25 dB/steg, 0–127 = −16 … +15,75 dB. `dsp8000.db_to_cc` gör detta.

### Returväg / SysEx (DSP8000 → dator)

Fungerar (`rew_to_dsp8000.py monitor`) med **båda kablarna inkopplade**
(AudioBox OUT→DSP8000 IN och DSP8000 OUT→AudioBox IN):

- Enheten ekar **inte** på CC‑mottagning, bara på fysisk fader‑rörelse,
  `+` på **SND MEMORY DUMP**, eller en **SysEx‑förfrågan** (se nedan).
- **SysEx‑förfrågan (verifierat 2026‑09‑02, `rew_to_dsp8000.py sysex`):**
  `F0 00 20 32 00 01 70 <xx> F7` med *valfri* `xx` (`01`, `10 1F`, `64` …)
  → enheten svarar med **hela minnesdumpen** (`… 4F 0A …`, 12110 byte,
  ~5 s). Modellbyte `0E` (DSP8024/ADRStudio) ger **inget svar**. DSP8000:s
  OS har alltså ingen granulär SysEx‑läsning eller realtidsskrivning – bara
  hela dumpen. Detaljer + ADRStudio:s DSP8024‑protokoll: `dsp8000_midi_webbresearch.md`.
  Praktisk vinst: dumpen kan hämtas **utan fader‑nudge**.
- `SND MEMORY DUMP` = 10‑byte header (`00 20 32 00 01 4F 12 00 20 00`) +
  working buffer + 100 program × 121 byte. **GEQ‑formatet delvis knäckt**
  (diff `dsp8000_sysex_min.syx` vs `..._max.syx`): varje band = 8 byte,
  7 st med bitvikter `64,32,16,8,4,2,1` + 1 separator; bandvärde = summan,
  0–127, skala `(dB+16)×4`. Bara 9 band skiljde mellan exporterna →
  **överföringsbuggen är stor**. Full blocklayout kräver en capture till
  (alla 31 band max, sparat till ett program, sedan dump).
- Fader‑rörelse ger en **läsbar** 64‑byte GEQ‑status:
  `F0 00 20 32 00 01 33 09 <32 vä> <32 hö> F7`, position 0–30 = band,
  31 = master, `64` = 0 dB. Kräver en fader‑nudge för hand.

**Slutsats:** skriv EQ via CC (funkar, kalibrerat). Verifiera med en
**REW‑sweep** — den visar faktiskt akustiskt resultat, inte bara vad enheten
tror. Ingen anledning att avkoda den packade dumpen.

### Parametrisk EQ via MIDI
Ligger i den packade dumpen (ej avkodad). Realtids‑CC för PEQ finns inte.
Reservväg: ställ in PEQ för hand → spara program → Program Change.

### Källor
- Manual (DSP8024 PRO, samma MIDI/GEQ): archive.org “behringer-ultra-curve-dsp-8000-user-manual-ver-1-3”, behringer-vintage.com `DSP8000_V1.3_1996_ENG.pdf`
- Sound on Sound-recension (påstod “no data output over MIDI” — motbevisat av vår capture)
- **`dsp8000_midi_webbresearch.md`** — bred webbresearch: MIDI SETUP-fälten,
  MIDI implementation chart (Tab 7.1/7.2), tre olika MIDI-OS-nivåer, och
  ADRStudio:s reverse-engineerade SysEx-protokoll för DSP8024. Testat mot
  vår enhet: DSP8024-protokollet fungerar **inte** här (se Returväg ovan).

---

## 7. Skriptkedjan

| Fil | Gör | Status |
|---|---|---|
| `dsp8000.py` | modell av enheten (31 ISO-band, gain-intervall, CC-mappning, `db_to_cc`) | klar |
| `rew_script.py` | REW → `rew_eq_suggestion.json` (parametriska filter + 31 bandvärden) | klar |
| `show_config.py` | JSON → `dsp8000_config.html`, visar vad som ska ställas in | klar |
| `rew_to_dsp8000.py` | skickar de 31 banden som MIDI CC + monitor/kalibrering | CC-vägen verifierad |
| `dsp8000_gui.html` | manuell EQ-kontroll i webbläsaren (Web MIDI), utan REW | klar |

### Steg 1: `rew_script.py`
Kräver **inte** REW Pro. Du kör själv sweepen i REW (vill du göra med koll
på nivåer ändå). Sedan:

1. välj mätning i listan
2. skriptet sätter equaliser → Generic, target settings + match target
   settings (`20–300 Hz`, `individualMaxBoost 3 dB`, `overallMaxBoost 0 dB`),
   kör `Calculate target level` + `Match target` — allt via API
3. läser ut de parametriska filtren, **behåller de 3 med störst |gain|**
   (`dsp8000.PEQ_COUNT`) och skriver tillbaka dem till REW — DSP8000 har bara
   3 PEQ, och `/eq/frequency-response` måste spegla exakt det som hamnar på
   enheten
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

Beroenden: `pip install requests`

### Steg 1b: `show_config.py`
Läser `rew_eq_suggestion.json`, skriver `dsp8000_config.html` och öppnar
den. Tabell över de 31 banden (målförstärkning, stapel, CC-nummer per
kanal, okalibrerat CC-värde) + de ≤3 parametriska filtren. Ren stdlib —
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

**Sweep-triggning via API** (`POST /measure/command`) är möjlig men
oprövad här — den skickar brus/sweep genom högtalarna och kräver att
nivåer är inställda. Kör sweepen i GUI:t.

### Steg 2: `rew_to_dsp8000.py` *(CC-vägen verifierad mot enheten 2026-09-02)*
Läser `rew_eq_suggestion.json` och skickar de 31 bandvärdena som MIDI CC.

| Kommando | Gör |
|---|---|
| `python rew_to_dsp8000.py ports` | listar MIDI-portar |
| `python rew_to_dsp8000.py monitor` | lyssnar på vad DSP8000 skickar (retur­väg) |
| `python rew_to_dsp8000.py calibrate [--band 1000]` | verifierar `db_to_cc` mot displayen |
| `python rew_to_dsp8000.py send --dry-run` | visar alla CC utan att skicka |
| `python rew_to_dsp8000.py send [--channel left\|right\|both] [--midi-channel N]` | skickar (frågar "ja" först) |

`send` skickar **båda kanalerna** som default (Stereolink av). `--channel left`
räcker om Stereolink är på.

Före skarp körning:

- **`dsp8000.CC_OFFSET`** måste = enhetens `CNTL RCV`-tal (MIDI-sidan). 0 på
  testenheten. Var den ursprungliga buggen.
- parametriska filter går **inte** via MIDI — `show_config.py` visar dem,
  ställ in för hand
- verifiera resultatet med en REW-sweep, inte via returvägen (den packade
  dumpen är inte avkodad — se avsnitt 6)

Beroenden: `pip install mido python-rtmidi` (funkade direkt på python 3.14)

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

1. Kör en sweep i REW → kör `rew_script.py` → `rew_eq_suggestion.json`
2. Kör `show_config.py` → se vad som ska ställas in
3. Kalibrera CC→dB mot enheten (`calibrate()` i steg 2), en gång
4. Kör steg 2 → skriv de 31 banden till DSP8000 via MIDI
5. Ställ in de parametriska filtren för hand, spara som program
6. Verifiera med en ny REW-sweep (enheten kan inte bekräfta sig själv
   via MIDI)

---

## 8. Kända begränsningar att komma ihåg

- DSP8000:s minnesdump går att ta emot men är **bit‑packad/proprietär** —
  verifiera EQ‑skrivningar med en REW‑sweep, inte via returvägen
- Parametrisk EQ kan inte fjärrstyras (bara programbyten) — ställ för hand
- MIDI CC→dB **verifierat**: `CC = 64 + dB×4`. `CC_OFFSET` måste matcha
  enhetens `CNTL RCV`‑tal
- Returväg verkar kräva **bara en MIDI‑kabel** — sänd+retur ihop = tyst
- Hela EQ-kedjan (target settings + Match target + läsa filter) går via
  REW:s API, verifierad mot 0.9.0 — kräver **inte** REW Pro
- Bara **sweepen** körs manuellt i GUI:t (medvetet — nivåer)
- REW:s API kan inte begränsa matchningen till 3 filter; `rew_script.py`
  behåller de 3 största och räknar grafiska EQ:n mot dem
- De 31 bandvärdena bygger på en **enpunktsmätning** — boost kapas till
  +3 dB (`dsp8000.SAFE_BOOST_DB`) med flit, fyll aldrig upp nullor. Mät
  på fler positioner och medelvärdesbilda i REW innan matchningen
