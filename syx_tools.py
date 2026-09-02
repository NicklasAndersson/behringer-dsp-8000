"""
Hjälpverktyg för DSP8000:s SysEx-dumpar (.syx från `rew_to_dsp8000.py
monitor`/`sysex`). Ren stdlib, ingen MIDI.

    python syx_tools.py hex  dump.syx [--start 0 --length 256]
    python syx_tools.py diff a.syx b.syx          # vilka byte skiljer + 8-bytegrupper
    python syx_tools.py geq  dump.syx [--offset 61]  # tolka 8-byte/band-grupper

Vad vi vet om SND MEMORY DUMP (00 20 32 00 01 4F 12 ...), se midi_captures.txt:
  * 12110 databyte, alla < 128.
  * Grupper om 8 byte: 7 byte med bitvikter [64,32,16,8,4,2,1] + 1 separator (0).
    Bandvärde = summan = 0..127, samma skala som CC (64 = 0 dB, 0,25 dB/steg).
  * Bara ~9 sådana grupper (offset 61..135 i filen) har hittills setts ändras,
    så hela blocklayouten (31+31 band, master, PEQ, 100 program) är INTE känd.
Verktyget finns för att nästa capture-omgång ska gå att analysera reproducerbart
i stället för för hand.
"""
import argparse
from pathlib import Path

import dsp8000

BIT_WEIGHTS = [64, 32, 16, 8, 4, 2, 1]


def load(path):
    b = Path(path).read_bytes()
    if b[:1] != b"\xf0" or b[-1:] != b"\xf7":
        raise SystemExit(f"{path}: inte en komplett SysEx (F0 ... F7).")
    return b


def hexdump(b, start=0, length=None, width=16):
    end = len(b) if length is None else min(len(b), start + length)
    for off in range(start, end, width):
        chunk = b[off:off + width]
        print(f"{off:6d}: " + " ".join(f"{x:02x}" for x in chunk).ljust(width * 3)
              + "  " + " ".join(f"{x:3d}" for x in chunk))


def decode_groups(b, offset, count=None):
    """Tolka 8-byte-grupper från offset: -> [(offset, värde, ok)]. ok = False om
    någon byte inte är exakt sin bitvikt (då är det inte ett packat bandvärde)."""
    out = []
    pos = offset
    while pos + 8 <= len(b) - 1 and (count is None or len(out) < count):
        g = b[pos:pos + 8]
        ok = all(x in (0, w) for x, w in zip(g[:7], BIT_WEIGHTS)) and g[7] == 0
        out.append((pos, sum(g[:7]), ok))
        pos += 8
    return out


def cmd_hex(args):
    hexdump(load(args.file), args.start, args.length)


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
    # 8-byte-grupper i det ändrade spannet, båda tolkningarna
    start = idx[0] - (idx[0] - args.offset) % 8
    print(f"\n8-byte-grupper från offset {start} (a -> b), värde 0..127 = CC-skala:")
    for (pa, va, oka), (pb, vb, okb) in zip(
            decode_groups(a, start), decode_groups(b, start)):
        if pa > idx[-1]:
            break
        flag = "" if oka and okb else "  (ej ren bitviktsgrupp)"
        print(f"  {pa:6d}: {va:3d} -> {vb:3d}   "
              f"{dsp8000.cc_to_db(va):+6.2f} -> {dsp8000.cc_to_db(vb):+6.2f} dB{flag}")


def cmd_geq(args):
    b = load(args.file)
    print(f"{args.file}: {len(b)} byte, header {b[1:11].hex(' ')}")
    for pos, val, ok in decode_groups(b, args.offset, args.count):
        if not ok and not args.all:
            continue
        print(f"  {pos:6d}: {val:3d}  {dsp8000.cc_to_db(val):+6.2f} dB"
              + ("" if ok else "  (ej ren bitviktsgrupp)"))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hex"); h.add_argument("file")
    h.add_argument("--start", type=int, default=0); h.add_argument("--length", type=int)
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b")
    d.add_argument("--max", type=int, default=80)
    d.add_argument("--offset", type=int, default=61, help="första kända gruppstart")
    g = sub.add_parser("geq"); g.add_argument("file")
    g.add_argument("--offset", type=int, default=61); g.add_argument("--count", type=int)
    g.add_argument("--all", action="store_true", help="visa även icke-bitviktsgrupper")
    args = p.parse_args()
    {"hex": cmd_hex, "diff": cmd_diff, "geq": cmd_geq}[args.cmd](args)


if __name__ == "__main__":
    main()
