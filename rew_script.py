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

Målkurvans form (tilt/house curve, LF cutoff) sätts INTE här - ställ in den
i REW:s Target Settings innan du kör; skriptet räknar bara ut target-nivån.

Andra varvet (--refine): mät om MED EQ:n aktiv och kör
    python rew_script.py --refine
så läggs residualen (target - uppmätt) ovanpå förra JSON:ens bandvärden.
Det är så man konvergerar en grafisk EQ - grannband läcker in i varandra,
så första varvets (target - respons) överkorrigerar alltid lite.

Beroenden:
    pip install requests
"""

import base64
import json
import math
import struct
import time
from datetime import datetime

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


def run_match_target(measurement_id, peq=True):
    """Sätt equaliser + match target settings, rikta in target-nivån, och
    (om peq) kör Match target som genererar de parametriska filtren.
    Målkurvans FORM (target-settings/house curve) rörs inte - den ställs i REW."""
    api_post(f"/measurements/{measurement_id}/equaliser",
             {"manufacturer": "Generic", "model": "Generic"})
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


def graphic_band_gains(measurement_id, after_peq, base=None):
    """
    Grafisk 31-bands-EQ = (target - respons) samplat vid ISO-frekvenserna,
    1/3-oktavs utjämning, centrerat kring median, klippt till enhetens intervall.

    after_peq styr att de två EQ-stegen inte dubbelkorrigerar:
      True  -> respons = /eq/frequency-response (uppmätt EFTER de parametriska
               filtren), så grafiska EQ:n bara städar upp resten
      False -> respons = /frequency-response (rå uppmätt), grafiska EQ:n gör allt

    base: {frekvens: dB} som redan sitter på enheten (förra varvets JSON).
    Mätningen är då gjord MED den EQ:n, så residualen adderas ovanpå.
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
    return {
        f: dsp8000.clamp_band_gain(g - mid + base.get(f, 0.0))
        for f, g in zip(dsp8000.ISO_BANDS, raw)
    }


def load_previous_output(path=OUTPUT_FILE):
    """Förra varvets JSON -> (peq_filters, {frekvens: dB}) för --refine."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"--refine kräver ett tidigare {path} (kör utan --refine först).")
    gains = data.get("graphic_band_gains_db", {})
    return (data.get("peq_filters", []),
            {f: float(gains[str(f)]) for f in dsp8000.ISO_BANDS if str(f) in gains})


def save_output(measurement, filters, band_gains, path=OUTPUT_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "measurement": measurement,
            "peq_filters": filters,
            "graphic_band_gains_db": band_gains,
        }, f, indent=2, ensure_ascii=False)
    print(f"Skrev {len(filters)} PEQ-filter + {len(band_gains)} band till {path}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-peq", action="store_true",
                    help="hoppa över de parametriska filtren, bara 31-bands grafisk EQ")
    ap.add_argument("--refine", action="store_true",
                    help="andra varvet: mätning gjord MED EQ:n på, addera residualen "
                         f"till bandvärdena i {OUTPUT_FILE} (PEQ-listan följer med)")
    ap.add_argument("--measurement", metavar="ID",
                    help="REW:s mätnings-id (nyckeln i GET /measurements) i stället för att fråga")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="fråga inte, kör Match target via API direkt")
    args = ap.parse_args()

    check_api_alive()
    measurement = (find_measurement(args.measurement) if args.measurement
                   else pick_measurement_interactively())
    measurement_id = measurement["id"]

    if args.refine:
        # Enhetens EQ (grafisk + ev. PEQ) sitter redan i mätningen: räkna
        # residualen mot rå respons och lägg den ovanpå förra bandvärdena.
        prev_filters, base = load_previous_output()
        print(f"Refine: utgår från {len(base)} band + {len(prev_filters)} PEQ i {OUTPUT_FILE}.")
        api_post(f"/measurements/{measurement_id}/equaliser",
                 {"manufacturer": "Generic", "model": "Generic"})
        eq_command(measurement_id, "Calculate target level")
        save_output(measurement, prev_filters,
                    graphic_band_gains(measurement_id, after_peq=False, base=base))
        return

    if args.yes or input("Kör Match target via API nu? (j/n): ").strip().lower().startswith("j"):
        run_match_target(measurement_id, peq=not args.no_peq)
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
    save_output(measurement, filters,
                graphic_band_gains(measurement_id, after_peq=not args.no_peq))


if __name__ == "__main__":
    main()
