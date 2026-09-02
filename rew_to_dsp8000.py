"""
Steg 2: rew_eq_suggestion.json -> MIDI CC till DSP8000:s grafiska EQ.

Bara den grafiska 31-bands-EQ:n kan fjärrstyras (via CC). De parametriska
filtren måste ställas för hand - kör show_config.py och läs av dem där.

CC->dB-skalan (dsp8000.db_to_cc, CC = 64 + dB*4) är verifierad mot
testenheten 2026-09-02. Kör `calibrate` en gång om du har en annan enhet.
Enhetens CNTL RCV-tal måste vara = dsp8000.CC_OFFSET (0 på testenheten).

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

try:
    import mido
except ImportError:  # fit_scale m.m. är ren matte; bara MIDI-kommandona behöver mido
    mido = None

import dsp8000
import syx_tools

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
    fader eller tryck + på SND MEMORY DUMP. Kräver DSP8000 OUT -> interface IN,
    EXCL SND ON, och BÅDA MIDI-kablarna inkopplade (verifierat 2026-09-02).

    OBS: SND MEMORY DUMP ger 100 program x 121 byte BIT-PACKAT / proprietärt -
    se midi_captures.txt och syx_tools.py. Fader-rörelse ger en läsbar 64-byte
    GEQ-status (64 = 0 dB) som skrivs ut i dB här. En SysEx-forfragan
    (`sysex`-kommandot) triggar samma packade dump. Verifiera hellre
    skrivningar med en REW-sweep."""
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
                    for line in geq_status_lines(d):
                        print("   ", line)
                else:
                    print(f"  {m}")
            time.sleep(0.02)
    print(f"\n{n} meddelanden. " +
          ("OK - returvägen funkar." if n else
           "INGET - kolla DSP8000 OUT -> interface IN (inte THRU), EXCL SND ON, bada kablarna i."))


def geq_status_lines(data):
    """Tolka den läsbara GEQ-statusframen (fader-rörelse):
    00 20 32 00 01 33 09 + 32 byte L + 32 byte R, pos 0-30 = band, 31 = master.
    -> rader med dB per kanal, tom lista för andra meddelanden."""
    if len(data) != 7 + 64 or list(data[:7]) != [0, 0x20, 0x32, 0, 1, 0x33, 9]:
        return []
    lines = []
    for name, chunk in (("L", data[7:39]), ("R", data[39:71])):
        bands = " ".join(f"{dsp8000.cc_to_db(v):+.1f}" for v in chunk[:31])
        lines.append(f"GEQ {name}: {bands}  master={chunk[31]}")
    return lines


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


def grab_dump(out, inp, req=(0x70, 0x01)):
    """Skicka en SysEx-förfrågan (modell 0x01) och returnera dumpens databyte
    (utan F0/F7), eller None om enheten inte svarade. Ändrar inget på enheten."""
    list(inp.iter_pending())
    _send_sysex(out, 0x00, 0x01, list(req))
    for m in _collect(inp, wait_s=12.0):
        if m.type == "sysex" and len(m.data) > 1000:
            return bytes(m.data)
    return None


GEQ_DATA_SPAN = (52, 128)   # data-offset-spann för GEQ-blocket (bit 373 .. 373+64*8, /7)


def _report_dump_diff(before, after):
    """Skriv ut vilka byte + vilka GEQ-band som skiljer mellan två dumpar.
    Byte utanför GEQ_DATA_SPAN = kandidat för PEQ/delay/övrigt."""
    n = min(len(before), len(after))
    diff = [i for i in range(n) if before[i] != after[i]]
    if len(before) != len(after):
        print(f"OBS olika längd: {len(before)} vs {len(after)}")
    if not diff:
        print("\nIngen byte ändrades.")
        return
    hdr = 10  # 10-byte dump-header före databyten
    lo, hi = GEQ_DATA_SPAN
    print(f"\n{len(diff)} byte ändrades:")
    for i in diff:
        d = i - hdr
        tag = "" if lo <= d < hi else "   <- utanför GEQ-blocket"
        print(f"  data[{d:5d}]  {before[i]:3d} -> {after[i]:3d}{tag}")
    ga = syx_tools.decode_geq(b"\xf0" + before + b"\xf7")
    gb = syx_tools.decode_geq(b"\xf0" + after + b"\xf7")
    for name in ("L", "R"):
        for j, (x, y) in enumerate(zip(ga[name], gb[name])):
            if x != y:
                print(f"  GEQ {name} {dsp8000.ISO_BANDS[j]:g} Hz: {x:+.2f} -> {y:+.2f} dB")


def grab(path):
    """Hämta en dump på begäran och spara den. Ändrar inget på enheten.
    Bygg upp ett bibliotek av kända tillstånd att diffa med syx_tools."""
    with open_output() as out, open_input() as inp:
        d = grab_dump(out, inp)
    if d is None:
        raise SystemExit("Inget svar. Kolla EXCL SND/RCV ON, båda kablarna i, "
                         "enheten på EQ-huvudskärmen.")
    Path(path).write_bytes(b"\xf0" + d + b"\xf7")
    print(f"{len(d)} databyte -> {path}  (sub-kod {d[5]:02x} {d[6]:02x})")


def probe_band(band_freq, value, channel="left", midi_channel=1, restore=64,
               manual=False):
    """Kontrollerad capture: dumpa, ändra EN sak, dumpa igen, visa vilka byte
    + GEQ-band som ändrades. Kartlägger den packade dumpens layout.

    manual=False: ändringen är ett GEQ-band satt via CC (restore = CC att
        skicka tillbaka efteråt, 64 = 0 dB, None = lämna kvar).
    manual=True:  ingen CC - skriptet pausar och du gör EN ändring på enheten
        själv (PEQ-gain, delay, gate ...). Så kartläggs de delar som inte går
        via MIDI. Enheten hamnar inte tillbaka automatiskt."""
    ts = time.strftime("%H%M%S")
    if manual:
        before_f, after_f = Path(f"probe_manual_before_{ts}.syx"), Path(f"probe_manual_after_{ts}.syx")
    else:
        cc_num = cc_map(channel)[band_freq]
        before_f = Path(f"probe_{band_freq:g}Hz_{channel}_before_{ts}.syx")
        after_f = Path(f"probe_{band_freq:g}Hz_{channel}_after_cc{value}_{ts}.syx")
    with open_output() as out, open_input() as inp:
        print("Dump 1/2 (före)...")
        before = grab_dump(out, inp)
        if before is None:
            raise SystemExit("Inget svar. Kolla EXCL SND/RCV ON, båda kablarna i, "
                             "enheten på EQ-huvudskärmen.")
        if manual:
            input("  Gör EN ändring på enheten nu (t.ex. PEQ 1 gain -6 dB), "
                  "tryck Enter när klar: ")
        else:
            print(f"  CC {cc_num} = {value}  ({band_freq:g} Hz {channel}, "
                  f"{dsp8000.cc_to_db(value):+.2f} dB)")
            out.send(mido.Message("control_change", channel=midi_channel - 1,
                                  control=cc_num, value=value))
            time.sleep(0.3)
        print("Dump 2/2 (efter)...")
        after = grab_dump(out, inp)
        if after is None:
            raise SystemExit("Andra dumpen kom inte. Enheten kanske bytte skärm.")
        if not manual and restore is not None:
            out.send(mido.Message("control_change", channel=midi_channel - 1,
                                  control=cc_num, value=restore))
            print(f"  återställde CC {cc_num} = {restore}")
    before_f.write_bytes(b"\xf0" + before + b"\xf7")
    after_f.write_bytes(b"\xf0" + after + b"\xf7")
    print(f"\n{before_f}\n{after_f}")
    _report_dump_diff(before, after)


def _geq_from_dump(payload):
    return syx_tools.decode_geq(b"\xf0" + payload + b"\xf7")


def readback():
    """Hämta dumpen på begäran (ingen fader-nudge) och skriv ut de 31+31
    grafiska banden i dB. Ändrar inget. Kräver båda MIDI-kablarna."""
    with open_output() as out, open_input() as inp:
        d = grab_dump(out, inp)
    if d is None:
        raise SystemExit("Inget svar. Kolla EXCL SND/RCV ON, båda kablarna i, "
                         "enheten på EQ-huvudskärmen.")
    g = _geq_from_dump(d)
    for name in ("L", "R"):
        cells = "  ".join(f"{f:g}:{db:+.2f}" for f, db in zip(dsp8000.ISO_BANDS, g[name]))
        print(f"{name} (master {g[name+'_master']:+d}): {cells}")
    return g


def sysex_probe(write_test=False):
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


def send(channel="both", midi_channel=1, dry_run=False, verify=False):
    """channel: left/right/both. Med Stereolink AV måste båda kanalerna
    skickas (samma kurva - REW-mätningen är L+R kombinerad).

    verify: hämta dumpen efteråt och jämför varje band mot det skickade
    (fångar tappade CC direkt - annars syns det först i en REW-sweep).
    Kräver att returvägen är inkopplad (båda MIDI-kablarna)."""
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
            plan.append((ch, f, cc_num, cc_val))
            print(f"  {f:>7} Hz  {db:+5.1f} dB  ->  CC {cc_num:>3} = {cc_val:>3}")

    if dry_run:
        print("\n(dry-run, inget skickades)")
        return
    if input(f"\nSkicka {len(plan)} CC till enheten? (ja/nej): ").strip().lower() != "ja":
        raise SystemExit("Avbrutet.")

    with open_output() as out, open_input() as inp:
        for _, _, cc_num, cc_val in plan:
            out.send(mido.Message("control_change", channel=midi_channel - 1,
                                  control=cc_num, value=cc_val))
            time.sleep(SEND_GAP_S)
        print(f"Skickade {len(plan)} CC.")
        if not verify:
            print("Verifiera med en ny REW-sweep.")
            return
        time.sleep(0.4)
        d = grab_dump(out, inp)
    if d is None:
        raise SystemExit("--verify: ingen dump kom tillbaka (returväg inkopplad?).")
    g = _geq_from_dump(d)
    bad = 0
    for ch, f, _, cc_val in plan:
        want = dsp8000.cc_to_db(cc_val)
        got = g["L" if ch == "left" else "R"][dsp8000.ISO_BANDS.index(f)]
        if abs(got - want) > 0.5:       # >1 enhetssteg = tappat CC
            bad += 1
            print(f"  MISS {ch:5} {f:>7g} Hz: skickade {want:+.2f}, enheten har {got:+.2f} dB")
    print(f"--verify: {len(plan)-bad}/{len(plan)} band stämmer"
          + ("" if not bad else f" - {bad} tappade, kör send igen") + ".")


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
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    sub.add_parser("monitor").add_argument("--seconds", type=int, default=30)
    sub.add_parser("sysex").add_argument("--write-test", action="store_true")
    sub.add_parser("readback")
    sub.add_parser("grab").add_argument("path", help="filnamn att spara dumpen som")
    pb = sub.add_parser("probe")
    pb.add_argument("--band", type=float, default=1000)
    pb.add_argument("--value", type=int, default=127, metavar="CC-0-127")
    pb.add_argument("--channel", choices=["left", "right"], default="left")
    pb.add_argument("--midi-channel", type=int, default=1, choices=range(1, 17),
                    metavar="1-16")
    pb.add_argument("--no-restore", action="store_true",
                    help="lämna bandet på --value i stället för att skicka 0 dB")
    pb.add_argument("--manual", action="store_true",
                    help="ingen CC - pausa och gör ändringen på enheten själv (PEQ m.m.)")
    for name in ("send", "calibrate"):
        sp = sub.add_parser(name)
        sp.add_argument("--midi-channel", type=int, default=1, choices=range(1, 17),
                        metavar="1-16")
        if name == "send":
            sp.add_argument("--channel", choices=["left", "right", "both"],
                            default="both")  # Stereolink av -> both
            sp.add_argument("--dry-run", action="store_true")
            sp.add_argument("--verify", action="store_true",
                            help="hämta dumpen efteråt och kolla att banden landade")
        else:
            sp.add_argument("--channel", choices=["left", "right"], default="left")
            sp.add_argument("--band", type=float, default=1000)
    args = p.parse_args()
    if mido is None:
        raise SystemExit("mido saknas: pip install mido python-rtmidi "
                         "(eller ./run.sh som installerar requirements.txt).")

    if args.cmd == "ports":
        print("out:", mido.get_output_names())
        print("in :", mido.get_input_names())
    elif args.cmd == "monitor":
        monitor(args.seconds)
    elif args.cmd == "sysex":
        sysex_probe(args.write_test)
    elif args.cmd == "readback":
        readback()
    elif args.cmd == "grab":
        grab(args.path)
    elif args.cmd == "probe":
        probe_band(args.band, args.value, args.channel, args.midi_channel,
                   restore=None if args.no_restore else 64, manual=args.manual)
    elif args.cmd == "send":
        send(args.channel, args.midi_channel, args.dry_run, args.verify)
    elif args.cmd == "calibrate":
        calibrate(args.band, args.channel, args.midi_channel)


if __name__ == "__main__":
    main()
