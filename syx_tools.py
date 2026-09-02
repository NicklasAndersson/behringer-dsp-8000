"""
Hjälpverktyg för DSP8000:s SysEx-dumpar (.syx från `rew_to_dsp8000.py
monitor`/`sysex`/`probe`). Ren stdlib, ingen MIDI.

    python syx_tools.py hex  dump.syx [--start 0 --length 256]
    python syx_tools.py geq  dump.syx            # de 31+31 grafiska banden i dB
    python syx_tools.py diff a.syx b.syx         # råa byte + GEQ-banden som ändrats

SND MEMORY DUMP / SysEx-svar (`F0 00 20 32 00 01 4F 0A|12 …  F7`):
  * 10-byte header, sedan 12100 databyte, alla < 128 (7-bit-safe) men BIT-PACKAT.
  * GEQ-blocket är avkodat (verifierat mot enheten 2026-09-02, `probe`):
    databyten packas MSB-först till en bitström; från bit-offset GEQ_BIT_OFFSET
    ligger 64 tecknade 8-bitarsvärden: 31 vänster band (20 Hz–20 kHz), vänster
    master, 31 höger band, höger master. Värde = CC − 64 = kvarts-dB-steg,
    −64…+63 ⇒ −16,00…+15,75 dB (dB = värde / 4). Samma för sub-kod 4F 0A och 4F 12.
  * Resten (PEQ, delay, gate, limiter, 100 program) är inte kartlagt - men
    `probe` gör fler kontrollerade captures reproducerbara om det behövs.
"""
import argparse
from pathlib import Path

import dsp8000

DUMP_HEADER_LEN = 10          # 00 20 32 00 01 4F xx yy 20 00
GEQ_BIT_OFFSET = 373          # bit-offset till första bandet i den MSB-packade strömmen
GEQ_COUNT = 64               # 31 vä band + vä master + 31 hö band + hö master


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


def cmd_hex(args):
    hexdump(load(args.file), args.start, args.length)


def cmd_geq(args):
    b = load(args.file)
    if not is_memory_dump(b):
        raise SystemExit("Inte en minnesdump (F0 00 20 32 00 01 4F …). "
                         "Fader-frames (33 09) läses av rew_to_dsp8000.py monitor.")
    print(f"{args.file}: {len(b)} byte, sub-kod {b[6]:02x} {b[7]:02x}")
    print(f"31 ISO-band: {', '.join(f'{f:g}' for f in dsp8000.ISO_BANDS)} Hz")
    _print_geq(decode_geq(b))


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
        print("\nGEQ-band som ändrats (dB):")
        hit = False
        for name in ("L", "R"):
            for j, (x, y) in enumerate(zip(ga[name], gb[name])):
                if x != y:
                    hit = True
                    print(f"  {name} {dsp8000.ISO_BANDS[j]:>7g} Hz: {x:+.2f} -> {y:+.2f}")
            if ga[name + "_master"] != gb[name + "_master"]:
                hit = True
                print(f"  {name} master: {ga[name+'_master']} -> {gb[name+'_master']}")
        if not hit:
            print("  (inga - ändringen ligger utanför GEQ-blocket)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hex"); h.add_argument("file")
    h.add_argument("--start", type=int, default=0); h.add_argument("--length", type=int)
    g = sub.add_parser("geq"); g.add_argument("file")
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b")
    d.add_argument("--max", type=int, default=80)
    args = p.parse_args()
    {"hex": cmd_hex, "geq": cmd_geq, "diff": cmd_diff}[args.cmd](args)


if __name__ == "__main__":
    main()
