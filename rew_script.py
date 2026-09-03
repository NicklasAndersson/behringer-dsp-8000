"""
Steg 1: REW -> fil med föreslagna EQ-inställningar

Du kör själv sweepen i REW (den vill du göra med koll på nivåer ändå).
Skriptet kan sedan, via REW:s HTTP-API:

  1. sätta equaliser till Generic
  2. sätta match target settings (DSP8000-vänliga defaults: 20-300 Hz,
     försiktig max boost) och räkna ut target-nivån
  3. köra "Match target"
  4. läsa ut filterlistan och spara den till rew_eq_suggestion.json

Allt utom sweepen går alltså via API:t - ingen GUI-klickning behövs efter
mätningen. Verifierat mot REW API 0.9.0 (V5.40 beta 101). Kräver INTE REW Pro.

Målkurvans form (tilt/house curve, LF cutoff) sätts som DEFAULT inte här -
skriptet räknar bara ut target-nivån mot vad som redan står i REW:s Target
Settings. Men för snabbare iteration går den att sätta via API också:

    python rew_script.py --show-target              # se REW:s riktiga fältnamn
    python rew_script.py --target lowFreqCutoffHz=25 --target slopedBOct=1.0 --yes
    python rew_script.py --house-curve /path/till/kurva.txt --yes
    python rew_script.py --clear-house-curve --yes

`--target` är en generisk KEY=VÄRDE-overlay ovanpå det REW redan har (GET,
uppdatera nycklarna, POST) - fältnamnen är REW:s egna och skiljer sig
troligen mellan REW-versioner, därför gissar vi inte på dem här. Kör
`--show-target` en gång mot din REW-installation för att se exakt vad
som finns att sätta.

Andra varvet (--refine): mät om MED EQ:n aktiv och kör
    python rew_script.py --refine
så läggs residualen (target - uppmätt), dämpad med --refine-damping (default
0,5 = halva felet per varv), ovanpå förra JSON:ens bandvärden. Det är så man
konvergerar en grafisk EQ - grannband läcker in i varandra, så första varvets
(target - respons) överkorrigerar alltid lite, och fullt steg per varv kan
svänga över. Hela kedjan i ett svep (mät alla varv i förväg, varje med
föregående varvs EQ på enheten):
    python rew_script.py --measurement <baslinje> --refine-measurement <med-EQ>

--refine behöver BARA den nya mätningen (gjord med EQ:n på) + förra
förslagsfilen (--refine-from) - inte den ursprungliga mätningen. Den
ursprungliga mätningens identitet bevaras ändå automatiskt genom hela
--refine-kedjan (origin_measurement i JSON:en, för spårbarhet), och varje
körning skriver en diff_from_previous_db som visar exakt hur mycket den
nya mätningen ändrade varje band jämfört med förra varvet.

Beroenden:
    pip install requests
"""

import base64
import json
import math
import struct
import time
from datetime import datetime
from pathlib import Path

import requests

import dsp8000

REW = "http://localhost:4735"
OUTPUT_FILE = "rew_eq_suggestion.json"

# DSP8000: 3 parametriska filter, korrigera bara basen, snåla med boost.
MATCH_TARGET_SETTINGS = {
    "startFrequency": 20,
    "endFrequency": 300,
    "individualMaxBoostdB": 3,
    "overallMaxBoostdB": 0,
    "flatnessTargetdB": 3,
}


def api_get(path, **kw):
    r = requests.get(f"{REW}{path}", timeout=10, **kw)
    r.raise_for_status()
    return r.json()


def api_post(path, body):
    r = requests.post(f"{REW}{path}", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def api_delete(path):
    r = requests.delete(f"{REW}{path}", timeout=10)
    r.raise_for_status()
    return r.json() if r.content else None


def check_api_alive():
    try:
        info = api_get("/version")
    except requests.exceptions.ConnectionError:
        raise SystemExit(
            f"Ingen kontakt med REW på {REW}.\n"
            "Starta REW och slå på API:t: Preferences -> API -> 'Start server'."
        )
    print(f"Ansluten till REW: {info}")


def list_measurements():
    """REW ger {"1": {...}, "2": {...}}; platta ut, lägg tillbaka id."""
    data = api_get("/measurements")
    return [
        {"id": k, **v}
        for k, v in sorted(data.items(), key=lambda kv: int(kv[0]))
    ]


def pick_measurement_interactively():
    measurements = list_measurements()
    if not measurements:
        raise SystemExit("Inga mätningar hittades i REW - kör en sweep först.")

    print("Tillgängliga mätningar:")
    for i, m in enumerate(measurements):
        print(f"  [{i}] {m['id']}: {m.get('title', '?')}  ({m.get('date', '')})")
    last = len(measurements) - 1
    while True:
        ans = input(f"Välj mätning (index, enter = {last}): ").strip()
        if not ans:
            return measurements[last]
        if ans.isdigit() and int(ans) <= last:
            return measurements[int(ans)]
        print(f"Ange ett tal 0..{last}.")


def find_measurement(measurement_id):
    """Slå upp en mätning på REW-id (nyckeln i GET /measurements)."""
    for m in list_measurements():
        if m["id"] == str(measurement_id):
            return m
    raise SystemExit(f"Ingen mätning med id {measurement_id} i REW.")


EQ_COMMANDS = [
    "Calculate target level", "Match target", "Optimise gains",
    "Optimise gains and Qs", "Optimise gains, Qs and Fcs",
    "Generate predicted measurement", "Generate filters measurement",
    "Generate target measurement",
]


def eq_command(measurement_id, command):
    """
    Kör ett EQ-kommando och väntar på att det blir klart.

    Kommandona kör asynkront: POST svarar "<command> ID N in progress",
    och GET /measurements/process-result har processName "<command> ID N"
    + message "Completed" när just den körningen är klar. Vi matchar exakt
    "ID N" så vi inte råkar läsa av ett gammalt resultat.
    """
    msg = api_post(f"/measurements/{measurement_id}/eq/command",
                   {"command": command}).get("message", "")
    print(msg)
    if "in progress" not in msg:
        return  # kördes synkront
    process_name = msg.split(" in progress")[0]  # "<command> ID N"
    for _ in range(120):  # 120 x 0,5 s = 60 s tak; höj om Match target är trögt
        result = api_get("/measurements/process-result")
        if result.get("processName") == process_name:
            if result.get("message") == "Completed":
                return
            raise SystemExit(f"{process_name}: {result.get('message')}")
        time.sleep(0.5)
    raise SystemExit(f"'{command}' blev inte klar inom tidsgränsen.")


def get_target_settings(measurement_id):
    return api_get(f"/measurements/{measurement_id}/target-settings")


def set_target_settings(measurement_id, overrides):
    """Läs mätningens nuvarande target-settings, skriv in overrides ovanpå
    (bevarar allt annat REW redan satt), skicka tillbaka. Overrides fältnamn
    är REW:s egna - se --show-target. Returnerar det sammanslagna objektet."""
    if not overrides:
        return None
    merged = {**get_target_settings(measurement_id), **overrides}
    api_post(f"/measurements/{measurement_id}/target-settings", merged)
    print(f"Target settings uppdaterade: {json.dumps(overrides, ensure_ascii=False)}")
    return merged


def set_house_curve(path=None, clear=False, log_interpolation=None):
    """/eq/house-curve (global, inte per mätning). log_interpolation måste
    sättas INNAN filen enligt REW:s dokumentation."""
    if log_interpolation is not None:
        api_post("/eq/house-curve-log-interpolation", log_interpolation)
    if clear:
        api_delete("/eq/house-curve")
        print("House curve borttagen.")
    if path:
        api_post("/eq/house-curve", path)
        print(f"House curve satt: {path}")


def run_match_target(measurement_id, peq=True, target_overrides=None):
    """Sätt equaliser + ev. target-settings-overlay + match target settings,
    rikta in target-nivån, och (om peq) kör Match target som genererar de
    parametriska filtren. Utan target_overrides rörs målkurvans FORM inte -
    den är då vad REW redan hade satt (GUI eller tidigare API-anrop)."""
    api_post(f"/measurements/{measurement_id}/equaliser",
             {"manufacturer": "Generic", "model": "Generic"})
    set_target_settings(measurement_id, target_overrides)
    api_post("/eq/match-target-settings", MATCH_TARGET_SETTINGS)
    eq_command(measurement_id, "Calculate target level")
    if peq:
        eq_command(measurement_id, "Match target")


def get_filter_slots(measurement_id):
    """GET /measurements/{id}/filters: alla platser (Generic/Generic ger 20-22),
    satta filter har type (PK...), frequency, gaindB, q. "None" = tom plats."""
    return api_get(f"/measurements/{measurement_id}/filters")


def get_filters(measurement_id):
    """Bara de satta filtren (tomma platser bortfiltrerade)."""
    return [
        f for f in get_filter_slots(measurement_id)
        if f.get("type") not in (None, "None")
    ]


def keep_top_filters(measurement_id, filters, n=dsp8000.PEQ_COUNT):
    """
    REW:s Match target ger fler filter än DSP8000:s 3 PEQ. Behåll de n
    peaking-filter (PK) med störst |gain|, skriv tillbaka till REW så
    /eq/frequency-response speglar exakt det som faktiskt hamnar på enheten
    (annars blir grafiska EQ:n fel). Shelf-filter (LS/HS) och annat som
    DSP8000:s PEQ inte kan göra slängs - grafiska EQ:n får ta den delen.
    """
    peaking = [f for f in filters if f.get("type") == "PK" and "q" in f]
    dropped = len(filters) - len(peaking)
    if dropped:
        print(f"Hoppar över {dropped} filter som inte är PK (shelf o.dyl.).")
    if len(peaking) == len(filters) and len(filters) <= n:
        return filters
    kept = sorted(peaking, key=lambda f: abs(f.get("gaindB", 0)), reverse=True)[:n]
    kept = sorted(kept, key=lambda f: f.get("frequency", 0))
    slots = max(len(get_filter_slots(measurement_id)), len(kept))
    body = [
        {"index": i, "type": "PK", "enabled": True,
         "frequency": f["frequency"], "gaindB": f["gaindB"], "q": f["q"]}
        for i, f in enumerate(kept, 1)
    ]
    body += [{"index": i, "type": "None"} for i in range(len(kept) + 1, slots + 1)]
    api_post(f"/measurements/{measurement_id}/filters", {"filters": body})
    print(f"Behöll {len(kept)} av {len(filters)} filter (störst gain), "
          "skrev tillbaka till REW.")
    return get_filters(measurement_id)


def _decode_curve(d):
    """REW ger magnitude som base64 big-endian float32 + startFreq + ppo
    (punkter per oktav, log-spaced). -> lista [(frekvens_hz, dB)]."""
    raw = base64.b64decode(d["magnitude"])
    vals = struct.unpack(f">{len(raw) // 4}f", raw)
    f0, ppo = d["startFreq"], d["ppo"]
    # NaN/inf utanför mätområdet skulle annars krascha median + round()
    curve = [(f0 * 2 ** (i / ppo), v) for i, v in enumerate(vals)
             if math.isfinite(v)]
    if not curve:
        raise SystemExit("REW gav en tom kurva - är mätningen fullständig?")
    return curve


def _value_at(curve, freq):
    """Linjär interpolation i log-frekvens."""
    if freq <= curve[0][0]:
        return curve[0][1]
    for (fa, va), (fb, vb) in zip(curve, curve[1:]):
        if fa <= freq <= fb:
            t = (math.log(freq) - math.log(fa)) / (math.log(fb) - math.log(fa))
            return va + t * (vb - va)
    return curve[-1][1]


def graphic_band_gains(measurement_id, after_peq, base=None, damping=1.0):
    """
    Grafisk 31-bands-EQ = (target - respons) samplat vid ISO-frekvenserna,
    1/3-oktavs utjämning, centrerat kring median, klippt till enhetens intervall.

    after_peq styr att de två EQ-stegen inte dubbelkorrigerar:
      True  -> respons = /eq/frequency-response (uppmätt EFTER de parametriska
               filtren), så grafiska EQ:n bara städar upp resten
      False -> respons = /frequency-response (rå uppmätt), grafiska EQ:n gör allt

    base: {frekvens: dB} som redan sitter på enheten (förra varvets värden).
    Mätningen är då gjord MED den EQ:n, så residualen adderas ovanpå.
    damping: hur stor del av residualen som läggs på (1.0 = fullt steg). < 1 för
    förfiningsvarv så grannbandsläckaget inte får kurvan att svänga över; utan
    base är residualen hela korrigeringen och damping saknar mening.
    """
    endpoint = ("eq/frequency-response" if after_peq else "frequency-response")
    meas = _decode_curve(api_get(
        f"/measurements/{measurement_id}/{endpoint}"
        "?ppo=48&smoothing=1/3&unit=SPL"))
    tgt = _decode_curve(api_get(
        f"/measurements/{measurement_id}/target-response?ppo=48&unit=SPL"))
    raw = [_value_at(tgt, f) - _value_at(meas, f) for f in dsp8000.ISO_BANDS]
    mid = sorted(raw)[len(raw) // 2]
    base = base or {}
    step = damping if base else 1.0
    return {
        f: dsp8000.clamp_band_gain(base.get(f, 0.0) + step * (g - mid))
        for f, g in zip(dsp8000.ISO_BANDS, raw)
    }


def refine_pass(measurement, base_gains, target_overrides, damping):
    """Ett förfiningsvarv. `measurement` ska vara mätt MED föregående stegs EQ
    aktiv på enheten: residualen (target - uppmätt), dämpad med `damping`, läggs
    på base_gains. PEQ-filtren rörs inte. -> nya {frekvens: dB}."""
    mid = measurement["id"]
    api_post(f"/measurements/{mid}/equaliser",
             {"manufacturer": "Generic", "model": "Generic"})
    set_target_settings(mid, target_overrides)
    eq_command(mid, "Calculate target level")
    return graphic_band_gains(mid, after_peq=False, base=base_gains, damping=damping)


def load_previous_output(path=OUTPUT_FILE):
    """Förra varvets JSON -> (peq_filters, {frekvens: dB}, origin_measurement)
    för --refine. origin_measurement är mätningen från VARV 1 - den bevaras
    genom hela --refine-kedjan (se save_output) i stället för att skrivas
    över av varje ny mätning. Filer från innan detta fanns saknar fältet;
    då faller vi tillbaka på "measurement" (bättre än inget)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"--refine kräver ett tidigare {path} (kör utan --refine först).")
    gains = data.get("graphic_band_gains_db", {})
    origin = data.get("origin_measurement") or data.get("measurement")
    return (data.get("peq_filters", []),
            {f: float(gains[str(f)]) for f in dsp8000.ISO_BANDS if str(f) in gains},
            origin)


def save_output(measurement, filters, band_gains, path=OUTPUT_FILE,
                 origin_measurement=None, previous_band_gains=None):
    """origin_measurement: mätningen från VARV 1 i en --refine-kedja (annars
    samma som measurement) - så den inte tappas bort när nästa refine sparar
    över "measurement" med den NYA mätningen.

    previous_band_gains: förra varvets bandvärden, om det här är en refine.
    Sparas då som diff_from_previous_db: hur mycket DEN HÄR mätningen ändrade
    varje band jämfört med förra varvet."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)   # t.ex. history/suggestions/
    payload = {
        "generated_at": datetime.now().isoformat(),
        "measurement": measurement,
        "origin_measurement": origin_measurement or measurement,
        "peq_filters": filters,
        "graphic_band_gains_db": band_gains,
    }
    if previous_band_gains is not None:
        payload["diff_from_previous_db"] = {
            f: round(band_gains.get(f, 0.0) - previous_band_gains.get(f, 0.0), 3)
            for f in dsp8000.ISO_BANDS
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Skrev {len(filters)} PEQ-filter + {len(band_gains)} band till {path}")


def _parse_kv(s):
    """'KEY=VÄRDE' -> (KEY, värde), värdet typat (bool/int/float/sträng)."""
    import argparse
    key, sep, raw = s.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"förväntade KEY=VÄRDE, fick {s!r}")
    return key, _coerce(raw)


def _coerce(raw):
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    for kind in (int, float):
        try:
            return kind(raw)
        except ValueError:
            pass
    return raw


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-peq", action="store_true",
                    help="hoppa över de parametriska filtren, bara 31-bands grafisk EQ")
    ap.add_argument("--refine", action="store_true",
                    help="andra varvet: mätning gjord MED EQ:n på, addera residualen "
                         f"till bandvärdena i {OUTPUT_FILE} (PEQ-listan följer med)")
    ap.add_argument("--measurement", metavar="ID",
                    help="REW:s mätnings-id (nyckeln i GET /measurements) i stället för att fråga")
    ap.add_argument("--output", metavar="FIL", default=OUTPUT_FILE,
                    help=f"skriv förslaget hit i stället för {OUTPUT_FILE}. GUI:t sätter "
                         "history/suggestion-<tid>-<mätning>.json så varje körning ligger "
                         "kvar tidsstämplad.")
    ap.add_argument("--refine-from", metavar="FIL",
                    help="--refine: läs föregående förslag härifrån (--output är ändå "
                         "vart det nya skrivs). Utan flaggan läses/skrivs --output.")
    ap.add_argument("--refine-measurement", action="append", default=[], metavar="ID",
                    help="förfiningsvarv direkt efter steg 1: REW-mätning gjord MED "
                         "steg 1:s EQ aktiv. Kan upprepas - varje mätning ska då vara "
                         "gjord med föregående varvs EQ på enheten.")
    ap.add_argument("--refine-damping", type=float, default=0.5, metavar="0-1",
                    help="andel av residualen ett förfiningsvarv lägger på (default "
                         "0.5: halva felet per varv, stabilt; 1.0 = fullt steg, "
                         "snabbare men kan svänga över vid grannbandsläckage).")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="fråga inte, kör Match target via API direkt")
    ap.add_argument("--show-target", action="store_true",
                    help="skriv ut mätningens nuvarande target-settings (REW:s egna "
                         "fältnamn) som JSON och avsluta - kör en gång innan --target")
    ap.add_argument("--target", action="append", default=[], metavar="KEY=VÄRDE",
                    type=_parse_kv,
                    help="sätt ett fält i target-settings via API (GET, uppdatera, POST) "
                         "innan Calculate target level. Kan upprepas. Se --show-target "
                         "för giltiga fältnamn.")
    ap.add_argument("--house-curve", metavar="PATH",
                    help="sökväg till en house curve-fil (/eq/house-curve, global)")
    ap.add_argument("--clear-house-curve", action="store_true",
                    help="ta bort ev. house curve (DELETE /eq/house-curve)")
    ap.add_argument("--house-curve-log-interp", choices=["true", "false"],
                    help="/eq/house-curve-log-interpolation - sätts före --house-curve")
    args = ap.parse_args()
    target_overrides = dict(args.target)

    check_api_alive()

    if args.house_curve or args.clear_house_curve or args.house_curve_log_interp:
        set_house_curve(args.house_curve, args.clear_house_curve,
                        None if args.house_curve_log_interp is None
                        else args.house_curve_log_interp == "true")

    measurement = (find_measurement(args.measurement) if args.measurement
                   else pick_measurement_interactively())
    measurement_id = measurement["id"]

    if args.show_target:
        print(json.dumps(get_target_settings(measurement_id), indent=2, ensure_ascii=False))
        return

    if args.refine and args.refine_measurement:
        raise SystemExit("--refine och --refine-measurement är två sätt att göra "
                         "samma sak; använd det ena.")
    if str(measurement_id) in {str(x) for x in args.refine_measurement}:
        raise SystemExit(f"--refine-measurement {measurement_id} är baslinjemätningen "
                         "själv - förfiningen ska vara en NY sweep gjord med EQ:n aktiv.")

    if args.refine:
        # residualen mot rå respons och lägg den, dämpad, ovanpå förra bandvärdena.
        # Ursprungsmätningen (varv 1) behövs INTE här - bara den NYA mätningen
        # (measurement, vald ovan) och förra varvets bandvärden (base, ur src).
        # origin bevaras bara som spårbarhet i JSON:en.
        src = args.refine_from or args.output
        prev_filters, base, origin = load_previous_output(src)
        print(f"Refine (dämpning {args.refine_damping:g}): utgår från {len(base)} band "
              f"+ {len(prev_filters)} PEQ i {src}"
              + (f" (ursprungsmätning {origin.get('id')}: {origin.get('title', '?')})"
                 if origin else "")
              + (f", skriver {args.output}." if args.output != src else "."))
        new_gains = refine_pass(measurement, base, target_overrides, args.refine_damping)
        save_output(measurement, prev_filters, new_gains, path=args.output,
                    origin_measurement=origin, previous_band_gains=base)
        changed = {f: d for f, d in
                   {f: round(new_gains.get(f, 0.0) - base.get(f, 0.0), 3)
                    for f in dsp8000.ISO_BANDS}.items() if abs(d) >= 0.05}
        if changed:
            biggest = sorted(changed.items(), key=lambda kv: -abs(kv[1]))[:5]
            print("Största ändringarna mot förra varvet (Hz: dB): "
                  + ", ".join(f"{f}: {d:+.1f}" for f, d in biggest))
        else:
            print("Inga band ändrade ≥0,05 dB mot förra varvet.")
        return

    if args.yes or input("Kör Match target via API nu? (j/n): ").strip().lower().startswith("j"):
        run_match_target(measurement_id, peq=not args.no_peq, target_overrides=target_overrides)
    elif not args.no_peq:
        print("Antar att du redan kört Match target i REW.")

    filters = []
    if not args.no_peq:
        filters = get_filters(measurement_id)
        if not filters:
            raise SystemExit(
                f"Mätning {measurement_id} har inga EQ-filter satta. "
                "Kör Match target (svara j ovan), gör det i REW först, "
                "eller kör med --no-peq. (Skrev inget.)"
            )
        filters = keep_top_filters(measurement_id, filters)
    # after_peq=False läser rå /frequency-response -> struntar i ev. gamla filter
    band_gains = graphic_band_gains(measurement_id, after_peq=not args.no_peq)

    origin, prev_gains = measurement, None
    for rid in args.refine_measurement:
        rm = find_measurement(rid)
        print(f"Förfiningsvarv mot mätning {rid} ({rm.get('title', '?')}), "
              f"dämpning {args.refine_damping:g} - mätningen måste vara gjord MED "
              "föregående stegs EQ aktiv på enheten.")
        prev_gains = band_gains
        band_gains = refine_pass(rm, band_gains, target_overrides, args.refine_damping)
        measurement = rm

    save_output(measurement, filters, band_gains, path=args.output,
                origin_measurement=origin, previous_band_gains=prev_gains)


if __name__ == "__main__":
    main()
