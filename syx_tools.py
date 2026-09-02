"""
Hjälpverktyg för DSP8000:s SysEx-dumpar (.syx från `rew_to_dsp8000.py
monitor`/`sysex`/`probe`/`grab`). Ren stdlib, ingen MIDI.

    python syx_tools.py hex  dump.syx [--start 0 --length 256]
    python syx_tools.py eq   dump.syx            # 31+31 grafiska band + de 6 PEQ-filtren
    python syx_tools.py diff a.syx b.syx         # råa byte + GEQ/PEQ som ändrats

SND MEMORY DUMP / SysEx-svar (`F0 00 20 32 00 01 4F 0A|12 …  F7`):
  * 10-byte header, sedan 12100 databyte, alla < 128 (7-bit-safe) men BIT-PACKAT.
    Databyten packas MSB-först till en bitström; fälten läses ur den. Verifierat
    mot enheten 2026-09-02 (`probe`, `probe --manual`). Samma för 4F 0A / 4F 12.
  * GEQ: från bit GEQ_BIT_OFFSET, 64 tecknade 8-bitarsvärden — 31 vä band
    (20 Hz–20 kHz), vä master, 31 hö band, hö master. Värde = CC − 64 =
    kvarts-dB ⇒ −16,00…+15,75 dB (dB = värde / 4).
  * PEQ: 6 poster à 32 bitar från bit PEQ_BIT_OFFSET, ordning L1 R1 L2 R2 L3 R3.
    Per post: frekvens (11 bit, f = 20·10^(raw/640) Hz, 20 Hz = 0),
    bandbredd (10 bit, (raw+1)/60 oktav), gain (11-bit tvåkomplement, dB = raw/16).
    OFF = posten helt noll. Läget PAR/AUT/SGL lagras INTE i dumpen.
  * Resten (master-skala, delay, gate, limiter, 100 program) är inte kartlagt.
"""
import argparse
from pathlib import Path

import dsp8000

DUMP_HEADER_LEN = 10          # 00 20 32 00 01 4F xx yy 20 00
GEQ_BIT_OFFSET = 373          # bit-offset till första bandet i den MSB-packade strömmen
GEQ_COUNT = 64               # 31 vä band + vä master + 31 hö band + hö master
PEQ_BIT_OFFSET = 87          # bit-offset till första PEQ-posten (L1)
PEQ_REC_BITS = 32            # bitar per PEQ-post
PEQ_LABELS = ["L1", "R1", "L2", "R2", "L3", "R3"]


def load(path):
    b = Path(path).read_bytes()
    if b[:1] != b"\xf0" or b[-1:] != b"\xf7":
        raise SystemExit(f"{path}: inte en komplett SysEx (F0 ... F7).")
    return b


def is_memory_dump(b):
    return b[1:6].hex() == "0020320001" and b[6] == 0x4F


def _msb_bits(data):
    """7-bitars MIDI-byte -> bitlista, MSB först per byte."""
    return [(byte >> i) & 1 for byte in data for i in (6, 5, 4, 3, 2, 1, 0)]


def decode_geq(b):
    """Komplett SysEx (med F0/F7) -> {'L': [31 dB], 'L_master': v, 'R': [...], 'R_master': v}.
    dB, redan delat med 4. master returneras rått (CC-lik skala, ej verifierad)."""
    bits = _msb_bits(b[1 + DUMP_HEADER_LEN:-1])
    vals = []
    for n in range(GEQ_COUNT):
        p = GEQ_BIT_OFFSET + 8 * n
        v = 0
        for i in range(8):
            v = (v << 1) | bits[p + i]
        vals.append(v - 256 if v >= 128 else v)
    return {"L": [v / 4 for v in vals[:31]], "L_master": vals[31],
            "R": [v / 4 for v in vals[32:63]], "R_master": vals[63]}


def _read_uint(bits, pos, width):
    v = 0
    for i in range(width):
        v = (v << 1) | bits[pos + i]
    return v


def decode_peq(b):
    """Komplett SysEx -> lista med 6 dicts (ordning L1 R1 L2 R2 L3 R3), var och en
    {'freq_hz', 'bw_oct', 'gain_db', 'on'}. on=False betyder posten är noll (OFF)."""
    bits = _msb_bits(b[1 + DUMP_HEADER_LEN:-1])
    out = []
    for k in range(6):
        base = PEQ_BIT_OFFSET + PEQ_REC_BITS * k
        fr = _read_uint(bits, base, 11)
        bw = _read_uint(bits, base + 11, 10)
        g = _read_uint(bits, base + 21, 11)
        g = g - 2048 if g >= 1024 else g
        out.append({
            "freq_hz": 20.0 * 10 ** (fr / 640),
            "bw_oct": (bw + 1) / 60,
            "gain_db": g / 16,
            "on": bool(fr or bw or g),
        })
    return out


def hexdump(b, start=0, length=None, width=16):
    end = len(b) if length is None else min(len(b), start + length)
    for off in range(start, end, width):
        chunk = b[off:off + width]
        print(f"{off:6d}: " + " ".join(f"{x:02x}" for x in chunk).ljust(width * 3)
              + "  " + " ".join(f"{x:3d}" for x in chunk))


def _print_geq(g):
    for name in ("L", "R"):
        cells = " ".join(f"{d:+5.2f}" for d in g[name])
        print(f"  {name} ({g[name + '_master']:+d} master): {cells}")


def peq_str(f):
    return (f"{f['freq_hz']:.0f} Hz  {f['bw_oct']:.3f} okt  {f['gain_db']:+.2f} dB"
            if f["on"] else "OFF")


def _print_peq(filters):
    for lbl, f in zip(PEQ_LABELS, filters):
        print(f"  PEQ {lbl}: {peq_str(f)}")


def cmd_hex(args):
    hexdump(load(args.file), args.start, args.length)


def cmd_eq(args):
    b = load(args.file)
    if not is_memory_dump(b):
        raise SystemExit("Inte en minnesdump (F0 00 20 32 00 01 4F …). "
                         "Fader-frames (33 09) läses av rew_to_dsp8000.py monitor.")
    print(f"{args.file}: {len(b)} byte, sub-kod {b[6]:02x} {b[7]:02x}")
    print(f"31 ISO-band: {', '.join(f'{f:g}' for f in dsp8000.ISO_BANDS)} Hz")
    _print_geq(decode_geq(b))
    _print_peq(decode_peq(b))


def cmd_diff(args):
    a, b = load(args.a), load(args.b)
    if len(a) != len(b):
        print(f"olika längd: {len(a)} vs {len(b)}")
    n = min(len(a), len(b))
    idx = [i for i in range(n) if a[i] != b[i]]
    if not idx:
        print("identiska")
        return
    print(f"{len(idx)} byte skiljer, offset {idx[0]}..{idx[-1]}")
    for i in idx[: args.max]:
        print(f"  {i:6d}: {a[i]:3d} -> {b[i]:3d}")
    if len(idx) > args.max:
        print(f"  ... ({len(idx) - args.max} till, --max höjer)")
    if is_memory_dump(a) and is_memory_dump(b):
        ga, gb = decode_geq(a), decode_geq(b)
        pa, pb = decode_peq(a), decode_peq(b)
        print("\nGEQ/PEQ som ändrats:")
        hit = False
        for name in ("L", "R"):
            for j, (x, y) in enumerate(zip(ga[name], gb[name])):
                if x != y:
                    hit = True
                    print(f"  GEQ {name} {dsp8000.ISO_BANDS[j]:>7g} Hz: {x:+.2f} -> {y:+.2f} dB")
            if ga[name + "_master"] != gb[name + "_master"]:
                hit = True
                print(f"  GEQ {name} master: {ga[name+'_master']} -> {gb[name+'_master']}")
        for lbl, x, y in zip(PEQ_LABELS, pa, pb):
            if x != y:
                hit = True
                print(f"  PEQ {lbl}: {peq_str(x)}  ->  {peq_str(y)}")
        if not hit:
            print("  (inga - ändringen ligger utanför GEQ/PEQ-blocken)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hex"); h.add_argument("file")
    h.add_argument("--start", type=int, default=0); h.add_argument("--length", type=int)
    e = sub.add_parser("eq"); e.add_argument("file")
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b")
    d.add_argument("--max", type=int, default=80)
    args = p.parse_args()
    {"hex": cmd_hex, "eq": cmd_eq, "diff": cmd_diff}[args.cmd](args)


if __name__ == "__main__":
    main()
