# Behringer Ultra-Curve DSP8000 + REW: rumskorrigering och skriptad EQ-överföring

Mät rummet i Room EQ Wizard (REW), låt REW räkna ut korrigeringen, skicka den
till DSP8000 via MIDI och läs tillbaka vad enheten faktiskt tog emot. Repot
innehåller skripten, en webb-kontrollpanel, den reverse-engineerade MIDI-implementationen
och referensdumpar från enheten.

**In English:** This repository documents and automates room correction with a
Behringer Ultra-Curve DSP8000 (the original 1996 model, not the DSP8024 PRO)
together with Room EQ Wizard (REW). `rew_script.py` reads a measurement through
REW's HTTP API, runs Match Target and turns the result into up to 3 parametric
filters plus 31 graphic-EQ band values. `rew_to_dsp8000.py` sends the 31 bands
to the unit as MIDI Control Change messages, or writes graphic **and**
parametric EQ at once by patching the unit's memory dump and pushing it back
(`apply`), and reads the dump back over SysEx to verify what landed. The MIDI implementation (CC map,
SysEx request, decoded dump layout for the graphic and parametric EQ) was
reverse-engineered and is documented in `docs/midi.md`. Everything else is in
Swedish.

**Auf Deutsch:** Dieses Repository dokumentiert und automatisiert die
Raumkorrektur mit einem Behringer Ultra-Curve DSP8000 (Originalmodell von 1996,
nicht der DSP8024 PRO) zusammen mit Room EQ Wizard (REW). `rew_script.py` liest
eine Messung über die HTTP-API von REW, führt „Match Target" aus und macht
daraus bis zu 3 parametrische Filter plus 31 Bandwerte für den grafischen EQ.
`rew_to_dsp8000.py` schickt die 31 Bänder als MIDI-Control-Change an das Gerät
oder schreibt grafischen **und** parametrischen EQ auf einmal, indem es den
Speicher-Dump des Geräts patcht und zurückschickt (`apply`), und liest den Dump
per SysEx zurück, um zu prüfen, was angekommen ist. Die MIDI-Implementierung (CC-Belegung, SysEx-Abfrage,
entschlüsseltes Dump-Layout für grafischen und parametrischen EQ) wurde per
Reverse Engineering ermittelt und ist in `docs/midi.md` beschrieben. Alles
Weitere ist auf Schwedisch.

---

## Innehåll i repot

| Fil / katalog | Vad |
|---|---|
| `readme.md` | den här filen: enheten, REW-arbetsflödet, skripten |
| `run.sh` | skapar `.venv`, installerar `requirements.txt`, kör valfritt steg (`./run.sh help`) |
| `run_gui.py` | webb-kontrollpanel (`./run.sh gui`): **1.** välj bas-dump (en avläsning eller en `dumps/`-referens) – "Läs av enheten" sparar en ny `history/reads/read-<tid>.syx`; **2.** fyll redigeraren (lodräta GEQ-reglage + PEQ-tabell + live EQ-kurva) från ett valt förslag eller basens egen EQ; **3.** skriv GEQ+PEQ genom att patcha *exakt den valda basen* (→ `history/writes/applied-<tid>.syx`) och pusha, i tre dialogsteg. **Direktredigering**-läge: GEQ-reglagen skickar CC direkt till enheten (ingen dump). Allt tidsstämplas i `history/`, inget val är implicit. Hopfällbart: skapa förslag per mätning + `run.sh`-kommandopanel |
| `rew_script.py` | **steg 1**: REW → EQ-förslag (PEQ-filter + 31 bandvärden); `--output FIL` styr vart (GUI:t: `history/suggestions/suggestion-<tid>-<mätning>.json`), `--refine-from FIL` för andra varvet |
| `show_config.py` | **steg 1b**: EQ-förslag → `history/config/config-<tid>.html`, visar vad som ska ställas in (`--input FIL`) |
| `rew_to_dsp8000.py` | **steg 2**: två skrivvägar – `send` (CC, ett band i taget, bara GEQ) och `apply` (hel dump, GEQ+PEQ); `roundtrip`/`readback`/`probe`/`grab`/`push` |
| `dsp8000.py` | modell av enheten: ISO-band, gain-gränser, CC-mappning, `db_to_cc` |
| `syx_tools.py` | avkoda/diffa `.syx`-dumpar (ren stdlib) |
| `dsp8000_gui.html` | fristående manuell GEQ-kontroll via Web MIDI (Chrome/Edge), utan REW eller servern |
| `paths.py` | var genererade filer hamnar: `history/{reads,writes,suggestions,captures,config}/` |
| `test_rew_script.py` | självtester utan REW/enhet (`./run.sh test`) |
| `rew_eq_suggestion.json` | exempel på förslagsformatet (GUI-körningar hamnar i `history/`) |
| `history/` | allt genererat, tidsstämplat och sorterat: `reads/` (avläsningar), `writes/` (patchade/pushade dumpar), `suggestions/` (EQ-förslag), `captures/` (råa monitor/sysex/probe-dumpar), `config/` (show_config-HTML). Gitignorerad |
| `docs/midi.md` | **MIDI-referensen**: inställningar, CC, SysEx, dump-layout, vad som är testat |
| `docs/midi_captures.txt` | rå labblogg från captures (historik, senare poster rättar tidigare) |
| `docs/keiths-blog-…html` | sparad blogg om DSP8024 (Auto-Q, firmware) |
| `dumps/*.syx` | referensdumpar från enheten med känt innehåll (tabell i `docs/midi.md` 6.6) |

---

## 0. Kom igång (macOS)

macOS har inget `python`-kommando, bara `python3`. Homebrews Python tillåter
inte `pip install` globalt (PEP 668), så kör i en virtuell miljö. Enklast:

```sh
./run.sh help               # full kommandolista
./run.sh gui                # webb-kontrollpanel: läs/redigera EQ + REW-flöde + kommandon (localhost)
./run.sh                    # = rew_script.py (steg 1), flaggor skickas vidare
./run.sh refine             # = rew_script.py --refine --yes (andra varvet)
./run.sh target             # = rew_script.py --show-target (REW:s fältnamn)
./run.sh target K=V …       # = rew_script.py --target K=V … --yes
./run.sh house-curve PATH|--clear
./run.sh show               # = show_config.py
./run.sh send --dry-run     # = rew_to_dsp8000.py send --dry-run (CC-vägen, bara GEQ)
./run.sh readback           # läs GEQ + PEQ ur enheten
./run.sh roundtrip          # hårdvarutest av dump-vägen: skriv känt GEQ+PEQ-mönster, läs tillbaka, återställ
./run.sh test               # självtester, kräver varken REW eller enheten
```

`run.sh` skapar `.venv` och installerar beroendena vid behov. `./run.sh gui`
öppnar en kontrollpanel på `http://127.0.0.1:8765`. Tre numrerade val, inget
implicit:

1. **Bas-dump** – dropdown med dina avläsningar (`history/reads/*.syx`) och
   `dumps/`-referenserna. *Läs av enheten* sparar en ny `history/reads/read-<tid>.syx`
   och väljer den. Skrivningen patchar *exakt* den valda filen – aldrig en dump
   som hämtas i skrivögonblicket (då riskerar man att fånga enheten mitt i ett
   lägesbyte och pusha tillbaka en trasig bild av master/limiter/gate).
2. **Fyll redigeraren** – från ett valt förslag (`history/suggestions/*.json` +
   committade `rew_eq_suggestion*.json`) eller *Basens EQ →*. GEQ:n är 31 lodräta
   reglage (som `dsp8000_gui.html`); en **EQ-kurva** ovanför visar summan av
   GEQ+PEQ, var för sig, och den valda basen (streckad), live medan du drar.
   Raden under redigeraren visar vilken fil den kom från.
3. **Skriv** i tre steg med paus: (1) patcha basen → `history/writes/applied-<tid>.syx`,
   (2) tryck + på RCV MEMORY DUMP → skicka, (3) enheten tillbaka på
   EQ-huvudskärmen → läs tillbaka och jämför (efter en push står enheten på
   RCV-panelen och svarar inte på läsförfrågan därifrån; *Verifiera skrivningen*
   kör om steg 3). Nästa varv: *Läs av enheten* igen för en färsk bas.

**Direktredigering** (kryssruta): GEQ-reglagen skickar då ett Control Change
direkt till enheten per band (samma väg som `send`) – snabb finjustering utan
dump-cykel. Det ändrar bara enhetens grafiska EQ, *inte* bas-filen, PEQ eller
master; läs av enheten igen innan en dump-skrivning ovanpå.

Att skapa förslag ur en REW-mätning och hela `run.sh`-kommandopanelen ligger i
varsin hopfällbar sektion. Ren stdlib, bara localhost. För hand:

```sh
python3 -m venv .venv
source .venv/bin/activate          # varje ny terminal
pip install -r requirements.txt    # requests (steg 1) + mido/python-rtmidi (steg 2)
python rew_script.py
```

**Krav innan steg 1 fungerar:**
- REW körs på samma dator med API:t på (Preferences → API → "Start server",
  port 4735). Testa: `curl http://localhost:4735/version`
- En färdig mätning i REW (du kör sweepen själv i REW:s GUI, skriptet gör resten)

**Krav innan steg 2 fungerar:** MIDI-interface (testat: PreSonus AudioBox USB),
båda MIDI-kablarna i, enhetens MIDI-sida inställd enligt `docs/midi.md` avsnitt 2.

`ModuleNotFoundError: No module named 'requests'` = `.venv` är inte aktiverad.

---

## 1. Arbetsflöde, rekommenderad ordning

1. Sweep i REW med EQ:n i **bypass** (IN/OUT-LED släckt) → `./run.sh` →
   `rew_eq_suggestion.json`
2. `./run.sh show` → se vad som ska ställas in
3. (Annan enhet än testenheten? `./run.sh calibrate` en gång, kolla att
   `CC = 64 + dB×4` stämmer och att `dsp8000.CC_OFFSET` = enhetens `CNTL RCV`.)
4. `./run.sh apply` → GEQ **och** PEQ skrivs i ett svep genom att patcha
   enhetens dump och pusha tillbaka. **Tryck + på RCV MEMORY DUMP** när skriptet
   pausar (utan det landar dumpen inte). `apply` läser tillbaka och bekräftar.
   (`./run.sh apply --dry-run` visar och sparar `history/writes/applied-*.syx` först.)
   Alternativ, bara grafisk EQ via CC: `./run.sh send --verify`, och ställ då
   de ≤3 parametriska filtren för hand (`show_config.py` visar dem)
6. Ny sweep med EQ:n **aktiv** (LED tänd) → det akustiska resultatet
7. `./run.sh refine` på den nya mätningen → `send --verify` igen → mät igen.
   Ett–två varv räcker normalt

---

## 2. Om enheten

**Modell:** Behringer Ultra-Curve **DSP8000** (originalmodellen, *inte*
PRO/DSP8024). Skillnad mot PRO: 20-bit AD/DA (ej 24-bit), enklare MIDI (hela
minnesdumpen via SysEx, ingen granulär styrning), delay/AES-EBU som tillval.
1996-manualens MIDI-chart säger "ingen SysEx" – vår enhet kör nyare OS och
dumpar. Se `docs/midi.md` bilaga B.

### Grundfunktioner
- 31-bands grafisk EQ per kanal (ISO-tersband, 20 Hz–20 kHz), ±16 dB i 0,5 dB-steg
- 3 fullparametriska filter per kanal (delas med Feedback Destroyer), +16…−48 dB
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
| Blinkar rött | Overflow/clipping internt i DSP:n – sänk ingångsnivå |

**Vid REW-mätning:** baseline med LED **släckt**, korrigerad mätning med LED **tänd**.

### DSP8000:s 31 ISO-tersbandsfrekvenser
```
20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400,
500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000,
6300, 8000, 10000, 12500, 16000, 20000  (Hz)
```

---

## 3. Auto-Q (enhetens egen rumskorrigering)

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
5. Börjar alltid från nuvarande EQ-inställning – förbehandla manuellt om du
   vill styra vilket område som justeras
6. Avbryt i förtid med OK-knappen, då behålls det som redan justerats
7. "NO SIGNAL DETECTED" → för svag mikrofonkänslighet, byt mick eller använd
   extern förförstärkare

**Begränsning:** grafisk EQ är ett trubbigt verktyg för smala rumsmoder i
basen. Använd de 3 parametriska filtren manuellt för sådana problem.

---

## 4. FB-D (Feedback Destroyer)

Automatisk detektering och dämpning av rundgång. Använder **samma tre
parametriska filter** som du annars kan använda för manuell rumskorrigering
– de konkurrerar om samma resurs.

- **AUT** (sökläge): filtren letar kontinuerligt efter ny feedback
- **SGL** (låst läge): filtret fixeras permanent på hittad frekvens
- Fungerar bäst på dynamiskt signalinnehåll (tal, sång), inte stationära toner
- Primärt tänkt för PA/scenbruk, mindre relevant vid hemma-rumskorrigering

---

## 5. Verifiering med REW

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
| 1/3 oktav | Motsvarar DSP8000:s 31 tersband – bra för jämförelse |
| 1/6 oktav / Var | Bra allmän känsla för rummet |
| 1/12–1/24 / None | Rådata, bäst för att se smala rumsmoder i basen |

---

## 6. Generera EQ-förslag i REW (Match Target)

> Hela det här flödet skriptas av `rew_script.py` via REW:s API (avsnitt 8).
> Nedan är GUI-motsvarigheten och förklaringen av vad målkurvan ska vara.

### Kör Match Target (GUI)

1. Markera mätningen i vänsterlistan → klicka **EQ** i verktygsraden.
2. Panel **Equaliser**: välj **Generic**.
   - Parametriska DSP8000-filtren → **Max filters = 3**.
   - 31-bandaren → också Generic, lägg in de 31 fasta frekvenserna med Q 4.32.
3. Panel **Target Settings**: ställ in målkurvan (nedan).
4. Panel **Filter Tasks**:
   - **Match range**: t.ex. 20–300 Hz (bara basen, se nedan).
   - **Individual max boost** / **Overall max boost**: 0 till +3 dB.
   - **Max cut**: generöst, -12 till -20 dB.
   - Klicka **Match response to target**.
5. Filtren dyker upp i **EQ Filters** – det är listan `rew_script.py` läser.

### Vad target ska vara

**Grundform:** rak linje på högtalarnas mellanregisternivå. REW sätter
**Target level** automatiskt; dra ner den några dB manuellt så korrigeringen
blir mest *sänkningar*. Boosta aldrig upp djupa nullor – de är
positionsberoende utsläckningar, EQ fixar dem inte och du bränner headroom.

**Tilt / house curve:** rakt uppmätt i rummet låter ljust. Lägg en svag
nedåtlutning, ca **-0,8 till -1 dB/oktav** från ~1 kHz och uppåt, eller ladda
en house curve-fil (Target Settings → *House curve*, eller `--house-curve`).

**Bas:** valfritt, +3 till +6 dB mjuk höjning under ~80–120 Hz. Sätt **LF
cutoff** till vad högtalaren faktiskt klarar.

**Frekvensområde att EQ:a:** bara upp till rummets transitionsfrekvens,
~200–400 Hz i ett normalt rum. Ovanför det gör enpunkts-EQ mer skada än nytta.

| Mål | Match range | Max filters | Max boost |
|---|---|---|---|
| 3 parametriska (rumsmoder) | 20–300 Hz | 3 | +3 dB |
| 31-band grafisk | 20 Hz–20 kHz | (31 fasta) | +3 dB (`SAFE_BOOST_DB`) |

### 31-band grafisk EQ (Generic-metoden)

REW har ingen "Match graphic EQ"-knapp för 31-bands EQ:er. I GUI:t: Generic,
filter type PK, **Q = 4.32** (= 1/3-oktavs bandbredd), de 31 ISO-frekvenserna
som fasta frekvenser. `rew_script.py` räknar i stället banden själv ur
kurvorna (avsnitt 8, steg 1 punkt 4).

**Enklare alternativ:** kör RTA i REW (Spectrum-fliken, 1/3-oktav) medan du
justerar DSP8000:s band live.

---

## 7. MIDI, kort version

Fullständig referens: **`docs/midi.md`** (inställningar, CC, SysEx, dump-layout,
testlogg, vad som återstår).

- **Enhetens MIDI-sida:** MIDI ON · CHANNEL 1 · OMNI ON · CNTL **RCV 0** / SND 1
  · PROG RCV+SND ON · EXCL RCV+SND ON. `CNTL` är ett tal (Controller Offset
  0–64), inte ON/OFF. `dsp8000.CC_OFFSET` måste vara = CNTL RCV.
- **Skriva GEQ:** CC 0–30 = vänster band, 31 = vä master, 32–62 = höger band,
  63 = hö master (+ offset). `CC = 64 + dB×4`, verifierat.
- **Läsa allt:** `F0 00 20 32 00 01 70 01 F7` → enheten svarar med hela
  minnesdumpen (12112 byte). GEQ- och PEQ-blocken är avkodade, så `readback`
  och `send --verify` visar exakt vad enheten har. Kräver båda MIDI-kablarna.
- **Skriva PEQ/delay/gate/limiter:** går **inte** via CC, och DSP8024:s
  granulära SysEx svarar enheten inte på. Enda outredda vägen är **RCV MEMORY
  DUMP** (skicka en patchad dump tillbaka) – testplan och `push`-kommando i
  `docs/midi.md` avsnitt 4.
- **Referensdumpar:** `dumps/` (0 dB, +16 dB, verklig kurva).

---

## 8. Skripten i detalj

### Steg 1: `rew_script.py`
Kräver **inte** REW Pro. Du kör själv sweepen i REW. Sedan:

1. välj mätning i listan (eller `--measurement ID`; `--yes` hoppar över frågan)
   – `--output FIL` styr vart förslaget skrivs
2. skriptet sätter equaliser → Generic och match target settings
   (`20–300 Hz`, `individualMaxBoost 3 dB`, `overallMaxBoost 0 dB`), kör
   `Calculate target level` + `Match target` via API. **Målkurvans form**
   (tilt/house curve/LF cutoff) rörs inte som default men kan sättas med
   `--target`/`--house-curve` (nedan)
3. läser ut de parametriska filtren, **behåller de 3 PK-filter med störst
   |gain|** (`dsp8000.PEQ_COUNT`; shelf-filter kastas, enheten har inga) och
   skriver tillbaka dem till REW så `/eq/frequency-response` speglar exakt
   det som hamnar på enheten
4. beräknar 31 grafiska bandvärden: `(target − respons)` med 1/3-oktavs
   utjämning vid ISO-frekvenserna, centrerat kring median, klippt till
   `SAFE_BOOST_DB` (+3) upp / −16 ner
5. sparar allt till `--output`-filen (default `rew_eq_suggestion.json`). GUI:t
   sätter `history/suggestions/suggestion-<tid>-<mätning>.json` så varje körning
   ligger kvar tidsstämplad och valbar; `--refine` skriver en ny sådan och läser
   den gamla via `--refine-from FIL` (utan flaggan: läser och skriver `--output`)

**Ingen dubbel-EQ:** med PEQ räknas de grafiska banden mot
`/eq/frequency-response` (responsen *efter* de 3 filtren). Med `--no-peq`
räknas de mot rå `/frequency-response` och gör allt själva.

Svarar du `n` på "Kör Match target via API nu?" antas du redan ha kört
matchningen i REW:s GUI.

`--refine` (**andra varvet**): mät om *med* EQ:n aktiv, välj den nya
mätningen, kör `--refine` (`--refine-from` = förra förslaget, `--output` = det
nya). Residualen (target − uppmätt) adderas ovanpå bandvärdena; PEQ-listan följer
med oförändrad. Grannband i en 1/3-oktavs-EQ läcker in i varandra, så första
varvet överkorrigerar alltid lite – ett eller två refine-varv är hur man
konvergerar.

**Målkurvan via API:**

```sh
python rew_script.py --show-target                     # REW:s riktiga fältnamn
python rew_script.py --target lowFreqCutoffHz=25 --target slopedBOct=1.0 --yes
python rew_script.py --house-curve /sökväg/till/kurva.txt --yes
python rew_script.py --clear-house-curve --yes
```

`--target KEY=VÄRDE` (upprepningsbar) läser mätningens `target-settings`,
lägger dina nycklar ovanpå och skickar tillbaka innan `Calculate target
level`. Fältnamnen är REW:s egna och kan skilja mellan versioner – kör
`--show-target` en gång mot din installation. Värden typas automatiskt
(`25` → int, `1.0` → float, `true`/`false` → bool). `--house-curve PATH` /
`--clear-house-curve` / `--house-curve-log-interp` styr `/eq/house-curve`
(globalt) – log-interpolation sätts alltid före filen.

### Steg 1b: `show_config.py`
Läser ett EQ-förslag (`--input FIL`, default `rew_eq_suggestion.json`), skriver
`history/config/config-<tid>.html` och öppnar den: de 31 banden med
målförstärkning, stapel ±16 dB, CC-nummer och CC-värde, plus de ≤3 parametriska
filtren med Q **och** bandbredd i oktaver (enheten vill ha oktaver). Ren stdlib.
`--no-open` hoppar över webbläsaren.

### Egen equaliser-modell i REW?
**Går inte.** REW:s equaliser-lista är inbyggd; API:t kan bara *välja*
`{manufacturer, model}`. Därför modellerar vi DSP8000 i `dsp8000.py` och
mappar REW:s korrigeringskurva mot den själva.

### REW HTTP-API (verifierat mot 0.9.0 / V5.40 beta 101)

Swagger-UI + spec: `http://localhost:4735/`. Slå på: Preferences → API → "Start server".

| Endpoint | Gör |
|---|---|
| `GET /version` | `{"message": "5.40 Beta 101 API 0.9.0"}` |
| `GET /measurements` | objekt `{"1": {...}}`, nyckeln är id |
| `GET/POST /measurements/{id}/equaliser` | `{"manufacturer": "Generic", "model": "Generic"}` |
| `GET/POST/PUT /measurements/{id}/target-settings` | målkurvan (`shape`, `lowFreqCutoffHz`, slopes, crossover) |
| `GET/POST/PUT /eq/match-target-settings` | `startFrequency`, `endFrequency`, `individualMaxBoostdB`, `overallMaxBoostdB`, `flatnessTargetdB` |
| `GET/POST/DELETE /eq/house-curve` | house curve-fil |
| `POST /measurements/{id}/eq/command` | `{"command": "..."}`, kör asynkront |
| `GET /measurements/process-result` | `{"processName": "Match target ID N", "message": "Completed"}`, pollas |
| `GET/POST/PUT /measurements/{id}/filters` | filterlista; satta filter har `type` (`PK`…), `frequency`, `gaindB`, `q` |
| `GET /measurements/{id}/eq/frequency-response` | förväntad kurva efter EQ |
| `GET /measurements/{id}/target-response` | målkurvan som frekvenssvar |

EQ-kommandon: `Calculate target level`, `Match target`, `Optimise gains`,
`Optimise gains and Qs`, `Optimise gains, Qs and Fcs`, `Generate predicted
measurement`, `Generate filters measurement`, `Generate target measurement`.

**Filterantal** styrs av equaliser-modellen (Generic/Generic ger upp till 22),
ingen API-väg att tvinga 3 – `rew_script.py` behåller de 3 största själv.

**Sweep-triggning via API kräver REW Pro** (`POST /measure/command`). Allt
annat skriptet gör är fritt. Kör sweepen i GUI:t.

### Steg 2: `rew_to_dsp8000.py`
Läser `rew_eq_suggestion.json` och skriver till enheten. **Två separata
skrivvägar** (se `docs/midi.md` avsnitt 5b):

- **CC, ett band i taget** (`send`): de 31 grafiska banden som var sitt Control
  Change. Inkrementellt och snabbt, men bara GEQ, och enheten tappar meddelanden
  om de kommer i en klump – `send --verify` läser tillbaka och rapporterar.
- **Hel minnesdump** (`apply`): patchar enhetens dump med GEQ **+ PEQ** och
  pushar tillbaka i ett svep (RCV MEMORY DUMP). Atomiskt, skriver båda, men
  skriver över hela minnesbilden. `roundtrip` är hårdvarutestet av den vägen.

Kommandotabell i `docs/midi.md` avsnitt 8; de viktigaste:

| Kommando | Gör |
|---|---|
| `send --dry-run` | visar alla CC utan att skicka |
| `send [--channel left\|right\|both] [--verify]` | CC-vägen: skickar de 31 banden (frågar först); `--verify` läser tillbaka och rapporterar band som inte landade |
| `apply [--dry-run] [--base FIL]` | dump-vägen: patcha enhetens dump med GEQ **+ PEQ** ur JSON:en och pusha tillbaka, läs tillbaka och bekräfta |
| `roundtrip [--keep]` | hårdvarutest av dump-vägen: backup → skriv känt GEQ+PEQ-mönster → läs tillbaka + jämför → återställ. Rör inte JSON/CC |
| `readback` | hämtar dumpen och skriver ut 31+31 GEQ-band + 6 PEQ-filter |
| `grab FIL.syx` / `probe` / `probe --manual` | spara dump / kartlägg dumpen (dumpa, ändra en sak, dumpa, diffa) |
| `push [--send-only] FIL.syx` | skicka en dump till enheten – testet av RCV MEMORY DUMP, protokoll i `docs/midi.md` avsnitt 4 |
| `calibrate` | verifiera `CC = 64 + dB×4` mot displayen |
| `monitor` / `sysex` / `ports` | lyssna / SysEx-förfrågan / lista portar |

`send` skickar **båda kanalerna** som default (Stereolink av). Före skarp
körning: `dsp8000.CC_OFFSET` = enhetens `CNTL RCV`.

Dump-vägen fungerar men **kräver ett tryck på RCV MEMORY DUMP** precis före
sändning – både `roundtrip`, `apply` och `push` pausar för det, och även
återställningen i `roundtrip` behöver ett till tryck. `roundtrip` 2026-09-03
skrev en GEQ-ramp + 3 PEQ-filter och läste tillbaka dem exakt. Kvar att avgöra:
om PEQ-*läget* (PAR/AUT/SGL) måste sättas för hand efteråt – kolla PEQ-sidan.

Utan `mido` går `test_rew_script.py` fortfarande att köra.

### Manuell kontroll utan REW: `dsp8000_gui.html`
Fristående sida, pratar MIDI direkt från webbläsaren – behöver varken servern
(`run_gui.py`) eller `.venv`. `run_gui.py`:s direktredigeringsläge gör samma sak
via servern; den här filen finns kvar för master/program och offline-bruk.
Öppna i **Chrome/Edge** (Web MIDI). Blockeras `file://`:
`python3 -m http.server` → `http://localhost:8000/dsp8000_gui.html`.

- 31-bands GEQ ±16 dB, läge Länkad / Endast L / Endast R
- **"Skicka alla"** återsänder alla band (drag-events tappas ibland)
- masterfaders L/R (0–127 rått), programval (Program Change 0–99)
- MIDI-kanal + Controller offset (= enhetens `CNTL RCV`)
- "Ladda REW-JSON" drar in band + PEQ-tabell (frekvens/gain/Q/bandbredd i
  oktaver) att ställa för hand

Reglagen sparas i `localStorage`; tryck "Skicka alla" efter omladdning.

### `syx_tools.py`
`eq FIL.syx` avkodar GEQ + PEQ ur en sparad dump, `diff A B` visar råa byte
och GEQ/PEQ som ändrats, `hex` hexdumpar. Ren stdlib, ingen MIDI.

---

## 9. Kända begränsningar

- **GEQ** skrivs via CC (`send`) eller minnesdump (`apply`). **PEQ** skrivs bara
  via dumpen. Dump-skrivvägen fungerar men **kräver ett tryck på RCV MEMORY
  DUMP-knappen** precis före sändning – utan det landar inget (`roundtrip`
  2026-09-03, `docs/midi.md` avsnitt 4/7). `roundtrip` verifierade att GEQ + PEQ
  skrivs och läses tillbaka exakt. **Öppet:** PEQ-*läget* PAR/AUT/SGL ligger inte
  i dumpen – kolla PEQ-sidan efter en skrivning. Delay, gate, limiter och
  master-skalan ligger också i dumpen men bitfälten är **inte kartlagda**, så
  `apply` rör dem inte (bevaras från basdumpen). PEQ + GEQ kan **läsas**
  (`readback`)
- Returväg kräver **båda MIDI-kablarna**. Enheten ekar inte CC, bara
  fader-rörelse / dump / förfrågan
- `CC_OFFSET` måste matcha enhetens `CNTL RCV`. Master-faderns CC-skala är
  inte verifierad
- Hela EQ-kedjan går via REW:s API utan Pro; bara sweepen körs för hand
- REW:s API kan inte begränsa matchningen till 3 filter; skriptet behåller de
  3 största
- Bandvärdena bygger på en **enpunktsmätning** och räknas band för band utan
  modell av hur 1/3-oktavsfiltren överlappar – därför +3 dB-taket och
  `--refine`. Mät på fler positioner och medelvärdesbilda i REW innan
  matchningen
- Det **akustiska** resultatet verifieras med REW-sweep; `--verify` visar
  bara vad enheten tog emot
