# Skripten och kontrollpanelen

Verktygen i repot: hur man installerar dem, arbetsflödet från mätning till
skriven EQ, och vad varje skript gör. Enheten och MIDI-protokollet beskrivs i
[readme.md](../readme.md) och [midi.md](midi.md); REW-halvan i [rew.md](rew.md).

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
  som senast hämtades från enheten
- masterfaders L/R i dB (SysEx `21` skriver alltid master), programval
  (Program Change 0–99)
- MIDI-kanal (= SysEx device-ID) + Controller offset (= enhetens `CNTL RCV`)
- "REW-JSON" drar in banden och lägger de 3 starkaste filtren på både L och R

Reglagen sparas i `localStorage`; tryck "Skriv GEQ + PEQ" efter omladdning.

`#selftest` i URL:en kör sidans egen kontroll av SysEx-kodningen. Samma
kodning låses mot `syx_tools.py` av `test_gui_html_sysex_matches_syx_tools`
(kör JS-blocket i `node`, hoppas över om `node` saknas).

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
| `show_config.py` | EQ-förslag → HTML som visar vad som ska ställas in |
| `rew_to_dsp8000.py` | skriva till och läsa ur enheten via MIDI |
| `dsp8000.py` | modell av enheten: band, gränser, CC-mappning |
| `syx_tools.py` | avkoda/diffa/patcha `.syx`-dumpar (ren stdlib) |
| `dsp8000_gui.html` | fristående GEQ + PEQ-kontroll och avläsning via Web MIDI |
| `paths.py` | var genererade filer hamnar |
| `test_rew_script.py` | självtester utan REW/enhet (`./run.sh test`) |

Utan `mido` installerat går `test_rew_script.py` fortfarande att köra.
