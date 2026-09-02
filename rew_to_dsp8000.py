"""
Steg 2: rew_eq_suggestion.json -> MIDI CC till DSP8000:s grafiska EQ.

Bara den grafiska 31-bands-EQ:n kan fjärrstyras (via CC). De parametriska
filtren måste ställas för hand - kör show_config.py och läs av dem där.

VIKTIGT: CC->dB-skalan (dsp8000.db_to_cc) är en OKALIBRERAD gissning.
Kör `calibrate` en gång mot din enhet innan du litar på `send`.

Beroenden:
    pip install mido python-rtmidi

Användning:
    python rew_to_dsp8000.py ports              # lista MIDI-portar
    python rew_to_dsp8000.py monitor            # lyssna på vad DSP8000 skickar
    python rew_to_dsp8000.py sysex              # prova ADRStudio-SysEx mot enheten
    python rew_to_dsp8000.py sysex --write-test  # + testa en realtidsskrivning
    python rew_to_dsp8000.py calibrate           # interaktiv kalibrering
    python rew_to_dsp8000.py send --dry-run      # visa vad som skulle skickas
    python rew_to_dsp8000.py send                # skicka på riktigt (frågar först)
    python rew_to_dsp8000.py send --channel right --midi-channel 2
"""
import argparse
import json
import sys
import time
from pathlib import Path

import mido

import dsp8000

JSON_FILE = Path("rew_eq_suggestion.json")
PORT_HINT = "AudioBox"   # delsträng; DSP8000 hänger på AudioBoxens MIDI-ut
SEND_GAP_S = 0.02        # liten paus mellan meddelanden så enheten hinner med


def open_output(hint=PORT_HINT):
    names = mido.get_output_names()
    if not names:
        raise SystemExit("Inga MIDI-utgångar. Koppla in gränssnittet.")
    match = [n for n in names if hint.lower() in n.lower()]
    name = (match or names)[0]
    print(f"MIDI-ut: {name}")
    return mido.open_output(name)


def open_input(hint=PORT_HINT):
    names = mido.get_input_names()
    if not names:
        raise SystemExit("Inga MIDI-ingångar.")
    match = [n for n in names if hint.lower() in n.lower()]
    name = (match or names)[0]
    print(f"MIDI-in: {name}")
    return mido.open_input(name)


def monitor(seconds=30):
    """Lyssna på vad DSP8000 skickar och spara varje SysEx till fil. Rör en
    fader eller tryck + på SND MEMORY DUMP. Kräver DSP8000 OUT -> interface IN
    + CNTL/EXCL SND, och (verkar det som) bara EN kabel - båda ihop = MIDI-loop.

    OBS: SND MEMORY DUMP ger 100 program x 121 byte BIT-PACKAT - inte värt att
    avkoda. Fader-rörelse ger en läsbar 64-byte GEQ-status (64 = 0 dB). Verifiera
    hellre skrivningar med en REW-sweep."""
    n = 0
    with open_input() as inp:
        for _ in inp.iter_pending():
            pass
        print(f"Lyssnar {seconds}s - rör en fader eller kör SND MEMORY DUMP...")
        t0 = time.time()
        while time.time() - t0 < seconds:
            for m in inp.iter_pending():
                n += 1
                if m.type == "sysex":
                    d = bytes(m.data)
                    out = Path(f"dsp8000_sysex_{len(d)}_{time.strftime('%H%M%S')}.syx")
                    out.write_bytes(b"\xf0" + d + b"\xf7")
                    print(f"  SysEx {len(d)}b -> {out}  (header {list(d[:9])})")
                else:
                    print(f"  {m}")
            time.sleep(0.02)
    print(f"\n{n} meddelanden. " +
          ("OK - returvägen funkar." if n else
           "INGET - kolla DSP8000 OUT -> interface IN (inte THRU), CNTL SND / EXCL SND."))


BEHRINGER_ID = [0x00, 0x20, 0x32]
# dev: 0x00 = adresserad, 0x7F = broadcast.  model: 0x01 = DSP8000 (vår enhet),
# 0x0E = DSP8024 (ADRStudio:s protokoll - gav INGET svar 2026-09-02).
SYSEX_HEADERS = [(0x00, 0x01), (0x00, 0x0E)]


def _send_sysex(out, dev, model, payload):
    out.send(mido.Message("sysex", data=BEHRINGER_ID + [dev, model] + payload))


def _collect(inp, wait_s=8.0, quiet_s=1.0):
    """Samla tills det varit tyst i quiet_s efter att data börjat komma
    (en 12 kB SysEx tar ~4 s @ 31250 baud, svaret dröjer ~5 s), max wait_s."""
    msgs, t0, last = [], time.time(), None
    while time.time() - t0 < wait_s:
        got = list(inp.iter_pending())
        if got:
            msgs.extend(got)
            last = time.time()
        if last and time.time() - last >= quiet_s:
            break
        time.sleep(0.02)
    return msgs


def sysex_probe(write_test=False, midi_channel=1):
    """Fråga enheten via SysEx. Se dsp8000_midi_webbresearch.md avsnitt 6/10.

    Resultat 2026-09-02: DSP8000 svarar bara på modellbyte 0x01, och bara med
    HELA minnesdumpen (~12110 byte) oavsett vilken 70-förfrågan man skickar.
    ADRStudio:s granulära DSP8024-kommandon (modellbyte 0x0E) gör inget.

    Enheten måste stå på EQ-huvudskärmen. Kräver DSP8000 OUT -> interface IN,
    MIDI ON, EXCL SND/RCV ON. Läsförfrågan ändrar inget på enheten."""
    hit = False
    with open_output() as out, open_input() as inp:
        for dev, model in SYSEX_HEADERS:
            tag = f"F0 00 20 32 {dev:02X} {model:02X} 70 01 F7"
            print(f"\n{tag}  ...")
            list(inp.iter_pending())
            _send_sysex(out, dev, model, [0x70, 0x01])
            replies = [bytes(m.data) for m in _collect(inp) if m.type == "sysex"]
            for d in replies:
                hit = True
                f = Path(f"dsp8000_sysex_reply_{len(d)}_{time.strftime('%H%M%S')}.syx")
                f.write_bytes(b"\xf0" + d + b"\xf7")
                print(f"  SVAR {len(d)}b  head {d[:12].hex(' ')}…  -> {f}")
            if not replies:
                print("  (inget svar)")

    if not hit:
        print("\nInget svar alls. Kolla EXCL SND+RCV ON, DSP8000 OUT -> interface IN "
              "(ej THRU), enheten på EQ-huvudskärmen, MIDI ON, båda kablarna i.")
        return

    if not write_test:
        return
    # ADRStudio:s realtidsskrivning (DSP8024): 10h sr xx. sr=0x11 = 1 kHz vä,
    # 0x20 = 0 dB, 0x30 borde ge +8 dB. Förväntas INTE fungera på DSP8000.
    print("\nSkrivtest (ADRStudio 10h, väntas ej fungera på DSP8000):")
    print("  1 kHz vänster -> 0x30. Titta på displayen.")
    with open_output() as out:
        _send_sysex(out, 0x00, 0x01, [0x10, 0x11, 0x30])
        ans = input("  Vad visar displayen för 1 kHz vänster? (enter när avläst) ")
        _send_sysex(out, 0x00, 0x01, [0x10, 0x11, 0x20])  # återställ
        print(f"  -> {ans.strip()!r}. Skickade tillbaka 0x20. "
              "Ändrades inget = bekräftar att 10h inte når DSP8000.")


def load_band_gains():
    if not JSON_FILE.exists():
        raise SystemExit(f"{JSON_FILE} saknas - kör rew_script.py först.")
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    gains = data.get("graphic_band_gains_db", {})
    # JSON-nycklar är strängar; mappa tillbaka till ISO-frekvenserna
    return {f: float(gains[str(f)]) for f in dsp8000.ISO_BANDS if str(f) in gains}


def cc_map(channel):
    return (dsp8000.CC_GRAPHIC_LEFT if channel == "left"
            else dsp8000.CC_GRAPHIC_RIGHT)


def send(channel="both", midi_channel=1, dry_run=False):
    """channel: left/right/both. Med Stereolink AV måste båda kanalerna
    skickas (samma kurva - REW-mätningen är L+R kombinerad)."""
    gains = load_band_gains()
    if not gains:
        raise SystemExit("Inga bandvärden i JSON:en.")
    channels = ["left", "right"] if channel == "both" else [channel]

    plan = []
    for ch in channels:
        ccs = cc_map(ch)
        print(f"\n{ch.upper()} kanal, MIDI-kanal {midi_channel}:")
        for f, db in gains.items():
            cc_num, cc_val = ccs[f], dsp8000.db_to_cc(db)
            plan.append((cc_num, cc_val))
            print(f"  {f:>7} Hz  {db:+5.1f} dB  ->  CC {cc_num:>3} = {cc_val:>3}")

    if dry_run:
        print("\n(dry-run, inget skickades)")
        return
    if input(f"\nSkicka {len(plan)} CC till enheten? (ja/nej): ").strip().lower() != "ja":
        raise SystemExit("Avbrutet.")

    with open_output() as out:
        for cc_num, cc_val in plan:
            out.send(mido.Message("control_change", channel=midi_channel - 1,
                                  control=cc_num, value=cc_val))
            time.sleep(SEND_GAP_S)
    print(f"Skickade {len(plan)} CC. Verifiera med en ny REW-sweep.")


def fit_scale(readings):
    """Linjär minstakvadrat dB = a*cc + b över (cc, dB)-par.
    -> (dB vid CC 0, dB vid CC 127, dB per CC-steg)."""
    n = len(readings)
    sx = sum(v for v, _ in readings)
    sy = sum(d for _, d in readings)
    sxx = sum(v * v for v, _ in readings)
    sxy = sum(v * d for v, d in readings)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    b = (sy - a * sx) / n
    return b, b + a * 127, a


def calibrate(band_freq=1000, channel="left", midi_channel=1):
    """
    Skicka en serie CC-värden på ett band, läs av dB på DSP8000:s display,
    verifiera att db_to_cc-formeln stämmer. (Redan bekräftad 2026-09-02:
    CC 64 = 0 dB, CC 96 = +8 dB. Kör om ifall en annan enhet beter sig annorlunda.)
    """
    cc_num = cc_map(channel)[band_freq]
    print(f"Kalibrerar CC {cc_num} ({band_freq} Hz, {channel}). "
          "Titta på bandets dB-värde i DSP8000:s display.\n")
    probes = [0, 16, 32, 48, 64, 80, 96, 112, 127]
    readings = []
    with open_output() as out:
        for v in probes:
            out.send(mido.Message("control_change", channel=midi_channel - 1,
                                  control=cc_num, value=v))
            ans = input(f"  CC {v:>3} -> avläst dB (enter = hoppa): ").strip()
            if ans:
                readings.append((v, float(ans.replace(",", "."))))

    if len(readings) < 2:
        raise SystemExit("För få avläsningar för att räkna ut en skala.")
    lo, hi, a = fit_scale(readings)
    cc0 = -lo / a  # CC-värde där dB = 0
    print(f"\nUppmätt: {a:.3f} dB/CC, 0 dB vid CC {cc0:.1f}")
    print(f"dsp8000.db_to_cc antar CC = 64 + dB*4 (0.25 dB/CC, 0 dB @ 64). "
          f"{'STÄMMER' if abs(a - 0.25) < 0.03 and abs(cc0 - 64) < 3 else 'AVVIKER - justera formeln'}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    sub.add_parser("monitor").add_argument("--seconds", type=int, default=30)
    sub.add_parser("sysex").add_argument("--write-test", action="store_true")
    for name in ("send", "calibrate"):
        sp = sub.add_parser(name)
        sp.add_argument("--midi-channel", type=int, default=1)
        if name == "send":
            sp.add_argument("--channel", choices=["left", "right", "both"],
                            default="both")  # Stereolink av -> both
            sp.add_argument("--dry-run", action="store_true")
        else:
            sp.add_argument("--channel", choices=["left", "right"], default="left")
            sp.add_argument("--band", type=float, default=1000)
    args = p.parse_args()

    if args.cmd == "ports":
        print("out:", mido.get_output_names())
        print("in :", mido.get_input_names())
    elif args.cmd == "monitor":
        monitor(args.seconds)
    elif args.cmd == "sysex":
        sysex_probe(args.write_test)
    elif args.cmd == "send":
        send(args.channel, args.midi_channel, args.dry_run)
    elif args.cmd == "calibrate":
        calibrate(args.band, args.channel, args.midi_channel)


if __name__ == "__main__":
    main()
