# Skripten och kontrollpanelen

Verktygen i repot: hur man installerar dem, arbetsflödet från mätning till
skriven EQ, och vad varje skript gör. Enheten och MIDI-protokollet beskrivs i
[readme.md](../readme.md) och [midi.md](midi.md); REW-halvan i [rew.md](rew.md).

> **Allt Python ligger i `python/`** (arkiverat 2026-09-09), tillsammans med
> `dumps/`, `history/` och exempel-JSON:erna. **Alla kommandon i det här
> dokumentet körs därifrån** – `cd python` först, så stämmer sökvägarna rakt av
> (`./run.sh …`, `dumps/…`). `run.sh` `cd`:ar själv till sin egen katalog, så
> `python/run.sh apply` fungerar också från roten – men bygger då sin `.venv`
> och `history/` under `python/`.
>
> Kvar i roten ligger det som faktiskt används dagligen: `dsp8000_gui.html`
> (kontrollpanelen, publicerad på GitHub Pages), `index.html` och `docs/`.
> Python-sidan är referens och REW-flödets motor – den kommer tillbaka den dag
> panelen ska prata med REW:s API.

---

## Kom igång (macOS)

macOS har inget `python`-kommando, bara `python3`. Homebrews Python tillåter
inte `pip install` globalt (PEP 668), så kör i en virtuell miljö. `run.sh`
skapar `.venv` och installerar `requirements.txt` vid behov:

```sh
./run.sh help               # full kommandolista
./run.sh gui                # webb-kontrollpanel (http://127.0.0.1:8765)
./run.sh test               # självtester, kräver varken REW, mido eller enheten
```

För hand:

```sh
python3 -m venv .venv
source .venv/bin/activate          # varje ny terminal
pip install -r requirements.txt    # requests (REW) + mido/python-rtmidi (MIDI)
python rew_script.py
```

`ModuleNotFoundError: No module named 'requests'` = `.venv` är inte aktiverad.

**Krav för REW-delen:** REW körs på samma dator med API:t på (Preferences →
API → "Start server", port 4735; testa med `curl http://localhost:4735/version`)
och en färdig mätning. Du kör sweepen själv i REW:s GUI, skripten gör resten.

**Krav för MIDI-delen:** MIDI-interface (testat: PreSonus AudioBox USB), **båda**
kablarna i, och enhetens MIDI-sida inställd enligt [midi.md avsnitt 2](midi.md#2-midi-setup-sidan).
`dsp8000.CC_OFFSET` måste vara lika med enhetens `CNTL RCV`.

---

## Arbetsflöde

1. Sweep i REW med EQ:n i **bypass** (IN/OUT-LED släckt) → `./run.sh` →
   ett EQ-förslag ([rew.md](rew.md))
2. `./run.sh show` → se vad förslaget faktiskt innehåller
3. Annan enhet än testenheten? `./run.sh calibrate` en gång: kolla att
   `CC = 64 + dB×4` stämmer och att `dsp8000.CC_OFFSET` = enhetens `CNTL RCV`
4. Sätt **FB-D OFF** på alla sex PEQ-filtren (PEQ-sidan på enheten) – med ON
   flyttar feedback destroyern filtren själv. `./run.sh apply --verify` →
   GEQ **och** PEQ skickas direkt till enheten (SysEx `21` + `22`, inget
   knapptryck, [midi.md 5b](midi.md#5b-skriva-geq-och-peq-direkt-apply)) och läses tillbaka.
   **Master sätts till 0 dB.** `--dry-run` visar de två meddelandena.
   Alternativ, bara grafisk EQ via CC: `./run.sh send --verify`
5. Ny sweep med EQ:n **aktiv** (LED tänd) → det akustiska resultatet
6. `./run.sh refine` på den nya mätningen → skriv igen → mät igen. Ett–två
   varv räcker normalt

Eller gör steg 1–4 i kontrollpanelen (`./run.sh gui`).

---

## Kontrollpanelen (`run_gui.py`)

`./run.sh gui` öppnar en panel på `http://127.0.0.1:8765`. Ren stdlib, bara
localhost. Tre numrerade val, inget implicit:

1. **Bas-dump** – dropdown med dina avläsningar (`history/reads/*.syx`) och
   `dumps/`-referenserna. *Läs av enheten* sparar en ny
   `history/reads/read-<tid>.syx` och väljer den. Basen fyller redigeraren
   (*Basens EQ →*) och ritar den streckade kurvan – skrivningen behöver den
   inte.
2. **Fyll redigeraren** – från ett valt förslag (`history/suggestions/*.json`
   plus committade `rew_eq_suggestion*.json`) eller *Basens EQ →*. GEQ:n är 31
   lodräta reglage; en **EQ-kurva** ovanför visar summan av GEQ+PEQ, var för
   sig, och den valda basen (streckad), live medan du drar. Raden under
   redigeraren visar vilken fil värdena kom från.
3. **Skriv** – redigerarens GEQ + PEQ skickas direkt (SysEx `21` + `22`),
   inget knapptryck, master 0 dB. *Verifiera skrivningen* läser tillbaka
   dumpen (enheten på EQ-huvudskärmen) och jämför GEQ, PEQ och master.

**Direktredigering** (kryssruta): GEQ-reglagen skickar ett Control Change
direkt till enheten per band – samma väg som `send`, snabb finjustering utan
dump-cykel. Ändrar bara enhetens grafiska EQ, *inte* bas-filen, PEQ eller
master; en skrivning efteråt skickar redigerarens värden, inte enhetens.

Att skapa förslag ur en REW-mätning och hela `run.sh`-kommandopanelen ligger i
varsin hopfällbar sektion.

---

## `rew_to_dsp8000.py` – skriva till enheten

**Tre skrivvägar** ([midi.md 5b](midi.md#5b-skriva-geq-och-peq-direkt-apply)):

- **CC, ett band i taget** (`send`): de 31 grafiska banden som var sitt Control
  Change. Inkrementellt och snabbt, men bara GEQ, och enheten tappar
  meddelanden om de kommer i en klump – `send --verify` läser tillbaka och
  rapporterar vad som inte landade.
- **Direkt via SysEx `21` + `22`** (`apply`): GEQ **+ PEQ** i två meddelanden
  till arbetsbufferten, inget knapptryck, ingen bas-dump. Master sätts till
  0 dB (varning). `--verify` läser tillbaka.
- **Hel minnesdump** (`push`, `roundtrip`): skriver hela minnesbilden inklusive
  de 100 programmen, kräver + på RCV MEMORY DUMP. Backup och återställning.

| Kommando | Gör |
|---|---|
| `send --dry-run` | visar alla CC utan att skicka |
| `send [--channel left\|right\|both] [--verify]` | CC-vägen: skickar de 31 banden (frågar först); `--verify` rapporterar band som inte landade |
| `apply [--dry-run] [--verify]` | skriv GEQ **+ PEQ** ur JSON:en direkt (SysEx `21` + `22`, master 0 dB); `--verify` läser tillbaka och jämför |
| `roundtrip [--keep]` | hårdvarutest av dump-vägen: backup → skriv känt GEQ+PEQ-mönster → läs tillbaka + jämför → återställ |
| `readback` | hämtar dumpen och skriver ut 31+31 GEQ-band + 6 PEQ-filter |
| `grab FIL.syx` | hämta en dump och spara den |
| `raw HEX…` | skicka `F0 00 20 32 00 01 <hex…> F7` och visa/spara svaren – hårdvarutest av EQ-Design:s kommandon ([midi.md 6.8](midi.md#68-eq-design-protokollet-ur-eqdesignexe-2026-09-03)) |
| `probe [--band Hz --value CC]` / `probe --manual` | kartlägg dumpen: dumpa, ändra en sak, dumpa, diffa |
| `push [--send-only] FIL.syx` | skicka en dump till enheten (RCV-testet) |
| `calibrate` | verifiera `CC = 64 + dB×4` mot displayen |
| `monitor` / `sysex` / `ports` | lyssna / SysEx-förfrågan / lista portar |

Fullständig tabell med flaggor: [midi.md avsnitt 8](midi.md#8-verktyg). Alla
finns även som `./run.sh <kommando>`.

`send` skickar **båda kanalerna** som default (Stereolink av på enheten). Med
Stereolink på räcker `--channel left`.

Dump-vägen **kräver ett tryck på RCV MEMORY DUMP** precis före sändning –
`roundtrip` och `push` pausar för det, och även återställningen i `roundtrip`
behöver ett till tryck. `apply` behöver inget.

---

## `syx_tools.py` – läsa och patcha dumpar

Ren stdlib, ingen MIDI, ingen enhet:

- `eq FIL.syx` – avkoda huvud (program, crossfade, shelving, limiter, gate),
  GEQ + PEQ och programnamnen ur en sparad dump
- `diff A.syx B.syx` – råa byte som skiljer, plus GEQ/PEQ som ändrats
- `hex FIL.syx [--start N --length N]` – hexdump
- som modul: `patch_dump(base, geq_L, geq_R, peqs)` skriver GEQ/PEQ i en dump
  (inversen av avkodningen), 7-bit-safe; `unpack_image(dump)` ger hela
  minnesbilden byteinriktad (10591 byte), `program_name(img, n)` namnet

Det här är verktyget för att kartlägga resten av dumpen: `probe --manual`,
ändra en sak på enheten, `diff`.

---

## `dsp8000.py` – modellen av enheten

ISO-banden, gain-gränserna, CC-mappningen, `db_to_cc` / `cc_to_db`,
`PEQ_COUNT`, `SAFE_BOOST_DB`, `CC_OFFSET`. Ändra `CC_OFFSET` om din enhets
`CNTL RCV` inte är 0.

---

## `rew_export.py` – REW → förslagsfil, med graf

Litet localhost-GUI vars enda jobb är att ta en mätning ur REW och lägga den på
disk i det format kontrollpanelen importerar.

```sh
./run.sh export            # http://127.0.0.1:8767, öppnar webbläsaren
```

- **Mätningslista** hämtad ur REW:s API; nyaste vald direkt, "Uppdatera listan"
  hämtar om utan omstart
- **Att välja en mätning läser bara** – REW:s tillstånd rörs inte. Sidan visar
  uppmätt svar (1/3-oktav) mot målkurvan som SVG, den preliminära
  korrigeringen som 31 staplar (±16 dB), snittet och största bandet, hur många
  band som klipps mot enhetens gränser, och alla fält REW ger om mätningen
  (titel, datum, uuid, REW-version, SPL-offset, frekvensområde …)
- **Antal PEQ-filter (0–3)** + **Räkna om**: kör kedjan i `rew_script.py` –
  Match target (skriver filter i REW), behåller de valda filtren efter
  `dsp8000.filter_priority` (**smala djupa först**, se
  [rew.md](rew.md#4-rew_scriptpy)) och räknar om de 31 bandvärdena mot responsen
  *efter* filtren, så stegen inte dubbelkorrigerar. 0 filter = banden gör allt
  och REW rörs inte alls. Resultatet visas innan något sparas: de behållna
  filtren med bandbredd och prioritet, hur många REW föreslog och hur många som
  valdes bort, och **hur mycket jobb banden får** (snitt per band, största
  bandet) jämfört med utan filter. Kurvan "efter de valda filtren" ritas
  streckad i SPL-grafen och staplarna uppdateras till de omräknade banden
- **Spara förslag…** öppnar en riktig filväljare (`showSaveFilePicker`,
  Chrome/Edge) där du bestämmer var filen hamnar; rutan bredvid är bara det
  föreslagna namnet. Saknas API:t (Firefox/Safari) blir det webbläsarens vanliga
  nedladdning i stället. En **arkivkopia** skrivs alltid till
  `history/suggestions/` – körningen ska lämna spår som allt annat genererat
- Efter sparandet står det vart filen tog vägen, med arkivkopians sökväg och en
  länk för att hämta den igen – importera den i `dsp8000_gui.html` under
  **Importera från REW**

Räknandet är `rew_script.py`:s, sidan är bara ett fönster mot det. Andra varvet
behöver ingen `--refine` här: exportera mätningen (gjord med EQ:n på) rakt av
och välj **Merga** i panelen – samma räkning, och andelen där är
`--refine-damping`.

---

## `dsp8000_gui.html` – manuell kontroll utan REW

Fristående sida som pratar MIDI direkt från webbläsaren – behöver varken
`run_gui.py` eller `.venv`. Kontrollpanelens direktredigeringsläge gör samma
sak via servern; den här filen finns kvar för master/program, avläsning och
offline-bruk.

Publicerad på GitHub Pages (main/root, `index.html` skickar vidare hit):
**<https://nicklasandersson.github.io/behringer-dsp-8000/>**. Web MIDI med
SysEx kräver secure context, så https-versionen funkar där `file://` blockeras.
Öppna i **Chrome/Edge**. Lokalt: `python3 -m http.server` →
`http://localhost:8000/dsp8000_gui.html`.

- 31-bands GEQ ±16 dB, läge Länkad / Endast L / Endast R. Under draget går
  varje band som CC (live); **"Skriv GEQ + PEQ"** skickar hela kurvan atomärt
  som SysEx `21` + de sex parametriska filtren som `22` (midi.md 6.8) – inget
  knapptryck på enheten, inget utanför arbetsbufferten rörs
- **PEQ-tabell**: 6 rader (L1 R1 L2 R2 L3 R3) med frekvens, bandbredd i oktaver
  och gain. Gain 0 = filtret stängs av. Q visas beräknat. Ställ Feedback
  Destroyer på OFF först – annars flyttar den filtren själv
- **"Hämta från enheten"**: SysEx-förfrågan `70 01` → hela minnesdumpen avkodas
  i webbläsaren (samma bitfält som `syx_tools.py`) och fyller reglagen,
  masterfaders och kolumnen "På enheten". Kräver `EXCL SND/RCV` ON och båda
  kablarna i
- **Kurvan**: GEQ interpolerad i log-frekvens plus de parametriska filtrens
  magnitud, L och R var för sig. Heldragen = det du redigerar, streckad = det
  som senast hämtades från enheten (eller valt program / importerad fil),
  **prickad lila = läget före senaste importen** – den ritas så fort du
  importerar ett REW-förslag eller en SysEx-fil, så skillnaden syns direkt i
  grafen, och försvinner när du ångrar importen
- **SysEx-fil (export/import)**: **Exportera EQ till fil…** öppnar en filväljare
  (Chrome/Edge, annars vanlig nedladdning) och skriver en JSON med de 31 bandens
  dB per kanal, masterfaders, de 6 PEQ-posterna och de exakta SysEx-byten
  (`21` = GEQ, `22` = PEQ) som panelen skulle skicka – läsbar och diffbar, inte
  enhetens binära format. **Importera** tar tillbaka den filen *eller* en riktig
  `.syx`-minnesdump (`run.sh grab`, eller säkerhetskopian från "Nolla alla
  program"); dumpen fyller även programlistan. Importen skriver aldrig till
  enheten. Den senast importerade filen är också basen för REW-importens tredje
  läge
- **Program (minnesplatser 1–100)**: dumpen innehåller alla 100 programmen, så
  listan visar namnen direkt efter en hämtning. Väljer man en plats laddas dess
  GEQ, PEQ och namn in i reglagen och blir den streckade "enheten"-kurvan –
  ingen extra MIDI-trafik, allt kommer ur dumpen. "Byt till på enheten" skickar
  Program Change (plats *n* = PC *n*−1). **"Skriv till platsen"** skickar SysEx
  `23` (helt program, 104 byte) – **avkodat ur EQ-Design, ännu inte verifierat
  mot hårdvara**: det skriver över programmet, bekräftas i en dialog, kräver en
  hämtning först (delay och övriga byte behålls från den) och bör följas av en
  ny hämtning för att se att rätt plats ändrades. Plats 0 = arbetsbufferten,
  den skrivs med "Skriv GEQ + PEQ"
- **"Nolla platsen" / "Nolla alla program"**: skriver 104 nollbyte (samma sak som
  enheten själv har i en oanvänd plats) till valda platsen respektive alla 100,
  ~50 ms isär via Web MIDI:s tidsstämplar. Båda frågar först. Massraderingen
  kräver en hämtning och **laddar ner dumpen som `.syx`** innan den skriver –
  den filen är enda vägen tillbaka (`./run.sh push dumpen.syx`, med RCV MEMORY
  DUMP-knappen). Efteråt töms listan: panelen vet inte längre vad som står i
  enheten förrän du hämtar igen
- masterfaders L/R i dB (SysEx `21` skriver alltid master)
- MIDI-kanal (= SysEx device-ID) + Controller offset (= enhetens `CNTL RCV`)
- **Importera från REW**: ladda ett EQ-förslag (`rew_script.py`:s JSON, se
  [rew.md](rew.md)) med två val:
  - **Ersätt** – mätningen gjordes *utan* EQ i kedjan: banden = förslaget ×
    andelen, och PEQ ersätts av REW:s 3 viktigaste filter – smala djupa först,
    samma rankning som `rew_export.py` (samma filter på L och R)
  - **Merga** – mätningen gjordes *med* EQ:n på: banden = nuvarande + förslaget ×
    andelen. Exakt vad `./run.sh refine` gör, där andelen är `--refine-damping`
    (0,5 = halva felet per varv, stabilt). PEQ sätts från filens `peq_filters`
    utan dämpning – `--refine` bär med dem oförändrade, så det är filtren som
    satt i kedjan under mätningen. Har du hämtat en dump jämför panelen med den
    och varnar om enheten hade andra filter
  - **Merga mot importerad SysEx-fil** – samma räkning, men basen är den
    exporterade filens band i stället för reglagen, och filens PEQ och master
    följer med. Använd den när filen är exakt det som satt på enheten under
    mätningen: då spelar det ingen roll vad som råkar stå i reglagen just nu
  - **Andel av förslaget**, 0–100 %: 0 % ändrar ingenting, 100 % är hela
    förslaget och största förändringen. Skjutreglaget räknar om direkt från
    läget före importen, så det går att pröva sig fram
  - Efter importen visas **snittförändringen** (medelvärdet av \|Δ\| över de 31
    banden, i procent av ±16 dB och i dB per band) plus största enskilda
    ändringen och var – och två knappar: **Skriv till DSP** (samma sak som
    "Skriv GEQ + PEQ") eller **Ångra**, som lägger tillbaka reglagen som de var.
    Importen skickar ingenting till enheten av sig själv
  - Hjälptexten "Hur får jag ut datan ur REW?" beskriver formatet; panelen läser
    filen lokalt och har **inget REW-API** ännu

Reglagen sparas i `localStorage`; tryck "Skriv GEQ + PEQ" efter omladdning.

`#selftest` i URL:en kör sidans egen kontroll av SysEx-kodningen. Samma
kodning låses mot `syx_tools.py` av `test_gui_html_sysex_matches_syx_tools`
(kör JS-blocket i `node`, hoppas över om `node` saknas): programnamnen ska bli
identiska med `syx_tools.program_name`, och avkoda→koda ska ge tillbaka exakt
samma 104 byte för alla 100 programmen i `dumps/dsp8000_sysex_peq_device.syx`
– skrivvägen rör alltså bara namn, PEQ och GEQ.

---

## Var filerna hamnar

Allt genererat går under `history/` (gitignorerad), tidsstämplat och sorterat
per typ – aldrig i repo-roten. Sökvägarna definieras i `paths.py`:

| Katalog | Innehåll |
|---|---|
| `history/reads/` | `read-<tid>.syx` – avläsningar av enhetens minne |
| `history/writes/` | `applied-<tid>.syx` – patchade dumpar som pushades |
| `history/suggestions/` | `suggestion-<tid>-<mätning>.json` – EQ-förslag från REW |
| `history/captures/` | råa monitor/sysex/probe/roundtrip-dumpar |
| `history/config/` | `config-<tid>.html` från `show_config.py` |

Committat ligger kvar där det är: `dumps/*.syx` (referensdumpar med känt
innehåll, tabell i [midi.md 6.6](midi.md#66-referensdumpar-i-dumps)) och
`rew_eq_suggestion.json` (exempel på förslagsformatet). En capture som är värd
att spara: döp om och flytta till `dumps/`.

---

## Filöversikt

| Fil | Vad |
|---|---|
| `run.sh` | skapar `.venv`, installerar beroenden, kör valfritt steg (`./run.sh help`) |
| `run_gui.py` | webb-kontrollpanelen |
| `rew_script.py` | REW → EQ-förslag (se [rew.md](rew.md)) |
| `rew_export.py` | litet REW-GUI: välj mätning, se kurvorna, spara förslag åt panelen |
| `show_config.py` | EQ-förslag → HTML som visar vad som ska ställas in |
| `rew_to_dsp8000.py` | skriva till och läsa ur enheten via MIDI |
| `dsp8000.py` | modell av enheten: band, gränser, CC-mappning |
| `syx_tools.py` | avkoda/diffa/patcha `.syx`-dumpar (ren stdlib) |
| `dsp8000_gui.html` | fristående GEQ + PEQ-kontroll och avläsning via Web MIDI |
| `paths.py` | var genererade filer hamnar |
| `test_rew_script.py` | självtester utan REW/enhet (`./run.sh test`); låser också JS-kodningen i `../dsp8000_gui.html` |

Roten: `dsp8000_gui.html` (kontrollpanelen), `index.html` (GitHub Pages-omdirigering),
`docs/`. Allt annat i tabellen ovan ligger i `python/`.

Utan `mido` installerat går `test_rew_script.py` fortfarande att köra.
