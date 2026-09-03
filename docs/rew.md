# REW-flödet

Hur en mätning i Room EQ Wizard blir ett EQ-förslag för DSP8000: uppkoppling,
målkurva, Match Target, REW:s HTTP-API och `rew_script.py`. Enheten beskrivs i
[readme.md](../readme.md), skripten i stort i [verktyg.md](verktyg.md).

---

## 1. Uppkoppling och grundinställningar

```
Dator (REW) → Ljudkortets utgång → DSP8000 analog in
DSP8000 analog out → Förstärkare → Högtalare
Mätmikrofon → Dator (REW), på lyssningsposition
```

- **Soundcard preferences:** rätt in/out, 48 kHz för att matcha DSP8000
- **Mic-kalibrering:** ladda .cal-fil om UMIK-1 eller liknande används
- **Check Levels:** justera tills input ligger runt **−12 till −18 dB**
- **Sweep length:** 1M eller längre (bättre lågfrekvensupplösning)
- **Frekvensspann:** 10–20 Hz till 20 000 Hz

Mät baseline med DSP8000:s IN/OUT-LED **släckt** (bypass) och resultatet med
den **tänd**.

### Smoothing (visningsinställning, ändrar inte data)

| Nivå | Användning |
|---|---|
| 1/3 oktav | Motsvarar DSP8000:s 31 tersband – bra för jämförelse |
| 1/6 oktav / Var | Bra allmän känsla för rummet |
| 1/12–1/24 / None | Rådata, bäst för att se smala rumsmoder i basen |

---

## 2. Målkurvan

**Grundform:** rak linje på högtalarnas mellanregisternivå. REW sätter **Target
level** automatiskt; dra ner den några dB manuellt så korrigeringen blir mest
*sänkningar*. Boosta aldrig upp djupa nullor – de är positionsberoende
utsläckningar, EQ fixar dem inte och du bränner headroom.

**Tilt / house curve:** rakt uppmätt i rummet låter ljust. Lägg en svag
nedåtlutning, ca **−0,8 till −1 dB/oktav** från ~1 kHz och uppåt, eller ladda
en house curve-fil (Target Settings → *House curve*, eller `--house-curve`).

**Bas:** valfritt, +3 till +6 dB mjuk höjning under ~80–120 Hz. Sätt **LF
cutoff** till vad högtalaren faktiskt klarar.

**Frekvensområde att EQ:a:** bara upp till rummets transitionsfrekvens,
~200–400 Hz i ett normalt rum. Ovanför det gör enpunkts-EQ mer skada än nytta.

| Mål | Match range | Max filters | Max boost |
|---|---|---|---|
| 3 parametriska (rumsmoder) | 20–300 Hz | 3 | +3 dB |
| 31-band grafisk | 20 Hz–20 kHz | (31 fasta) | +3 dB (`SAFE_BOOST_DB`) |

---

## 3. Match Target i GUI:t

> Hela det här flödet skriptas av `rew_script.py` (avsnitt 4). Nedan är
> GUI-motsvarigheten, för den som vill göra det för hand eller förstå vad
> skriptet gör.

1. Markera mätningen i vänsterlistan → klicka **EQ** i verktygsraden.
2. Panel **Equaliser**: välj **Generic**.
   - Parametriska DSP8000-filtren → **Max filters = 3**.
   - 31-bandaren → också Generic, lägg in de 31 fasta frekvenserna med Q 4.32.
3. Panel **Target Settings**: ställ in målkurvan (avsnitt 2).
4. Panel **Filter Tasks**:
   - **Match range**: t.ex. 20–300 Hz (bara basen).
   - **Individual max boost** / **Overall max boost**: 0 till +3 dB.
   - **Max cut**: generöst, −12 till −20 dB.
   - Klicka **Match response to target**.
5. Filtren dyker upp i **EQ Filters** – det är listan `rew_script.py` läser.

### 31-band grafisk EQ

REW har ingen "Match graphic EQ"-knapp för 31-bands EQ:er. I GUI:t: Generic,
filter type PK, **Q = 4.32** (= 1/3-oktavs bandbredd), de 31 ISO-frekvenserna
som fasta frekvenser. `rew_script.py` räknar i stället banden själv ur kurvorna.

**Enklare alternativ:** kör RTA i REW (Spectrum-fliken, 1/3-oktav) medan du
justerar DSP8000:s band live.

### Egen equaliser-modell i REW?

**Går inte.** REW:s equaliser-lista är inbyggd; API:t kan bara *välja*
`{manufacturer, model}`. Därför modelleras DSP8000 i `dsp8000.py` och REW:s
korrigeringskurva mappas mot den i skriptet.

---

## 4. `rew_script.py`

Kräver **inte** REW Pro. Du kör själv sweepen i REW. Sedan:

1. välj mätning i listan (eller `--measurement ID`; `--yes` hoppar över frågan)
   – `--output FIL` styr vart förslaget skrivs
2. skriptet sätter equaliser → Generic och match target settings
   (`20–300 Hz`, `individualMaxBoost 3 dB`, `overallMaxBoost 0 dB`), kör
   `Calculate target level` + `Match target` via API. **Målkurvans form**
   (tilt/house curve/LF cutoff) rörs inte som default men kan sättas med
   `--target` / `--house-curve`
3. läser ut de parametriska filtren, **behåller de 3 PK-filter med störst
   |gain|** (`dsp8000.PEQ_COUNT`; shelf-filter kastas, enheten har inga) och
   skriver tillbaka dem till REW så `/eq/frequency-response` speglar exakt det
   som hamnar på enheten
4. beräknar 31 grafiska bandvärden: `(target − respons)` med 1/3-oktavs
   utjämning vid ISO-frekvenserna, centrerat kring median, klippt till
   `SAFE_BOOST_DB` (+3) upp / −16 ner
5. sparar allt till `--output`-filen (default `rew_eq_suggestion.json`).
   Kontrollpanelen sätter `history/suggestions/suggestion-<tid>-<mätning>.json`
   så varje körning ligger kvar tidsstämplad och valbar

**Ingen dubbel-EQ:** med PEQ räknas de grafiska banden mot
`/eq/frequency-response` (responsen *efter* de 3 filtren). Med `--no-peq`
räknas de mot rå `/frequency-response` och gör allt själva.

Svarar du `n` på "Kör Match target via API nu?" antas du redan ha kört
matchningen i REW:s GUI.

### `--refine`, andra varvet

Mät om *med* EQ:n aktiv, välj den nya mätningen, kör `./run.sh refine`
(`--refine-from` = förra förslaget, `--output` = det nya; utan flaggan läses
och skrivs `--output`). Residualen (target − uppmätt) adderas ovanpå
bandvärdena; PEQ-listan följer med oförändrad.

Grannband i en 1/3-oktavs-EQ läcker in i varandra, så första varvet
överkorrigerar alltid lite – ett eller två refine-varv är hur man konvergerar.

### Målkurvan via API

```sh
python rew_script.py --show-target                     # REW:s riktiga fältnamn
python rew_script.py --target lowFreqCutoffHz=25 --target slopedBOct=1.0 --yes
python rew_script.py --house-curve /sökväg/till/kurva.txt --yes
python rew_script.py --clear-house-curve --yes
```

`--target KEY=VÄRDE` (upprepningsbar) läser mätningens `target-settings`,
lägger dina nycklar ovanpå och skickar tillbaka innan `Calculate target level`.
Fältnamnen är REW:s egna och kan skilja mellan versioner – kör `--show-target`
en gång mot din installation. Värden typas automatiskt (`25` → int, `1.0` →
float, `true`/`false` → bool). `--house-curve PATH` / `--clear-house-curve` /
`--house-curve-log-interp` styr `/eq/house-curve` (globalt) –
log-interpolation sätts alltid före filen.

### `show_config.py`

Läser ett EQ-förslag (`--input FIL`, default `rew_eq_suggestion.json`), skriver
`history/config/config-<tid>.html` och öppnar den: de 31 banden med
målförstärkning, stapel ±16 dB, CC-nummer och CC-värde, plus de ≤3 parametriska
filtren med Q **och** bandbredd i oktaver (enheten vill ha oktaver). Ren
stdlib; `--no-open` hoppar över webbläsaren.

---

## 5. REW:s HTTP-API

Verifierat mot **0.9.0 / V5.40 beta 101**. Swagger-UI + spec:
`http://localhost:4735/`. Slå på: Preferences → API → "Start server".

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

**Två begränsningar i API:t:**

- **Filterantalet** styrs av equaliser-modellen (Generic/Generic ger upp till
  22) och det finns ingen API-väg att tvinga 3 – `rew_script.py` behåller de 3
  största själv.
- **Sweep-triggning kräver REW Pro** (`POST /measure/command`). Allt annat
  skriptet gör är fritt. Kör sweepen i GUI:t.

---

## 6. Vad flödet inte löser

- Bandvärdena bygger på en **enpunktsmätning** och räknas band för band utan
  modell av hur 1/3-oktavsfiltren överlappar – därför +3 dB-taket och
  `--refine`. Mät på fler positioner och medelvärdesbilda i REW innan
  matchningen.
- Det **akustiska** resultatet verifieras bara med en ny REW-sweep. `--verify`
  och `readback` visar vad enheten tog emot, inte hur det låter.
- Grafisk EQ är trubbig för smala rumsmoder i basen – det är vad de 3
  parametriska filtren är till för, och de kan bara skrivas via
  dump-vägen ([midi.md avsnitt 4](midi.md#4-rcv-memory-dump--skriva-hela-minnet-fungerar-med-knapptryck)).
