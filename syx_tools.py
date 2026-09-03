"""
Hjälpverktyg för DSP8000:s SysEx-dumpar (.syx från `rew_to_dsp8000.py
monitor`/`sysex`/`probe`/`grab`/`push`, referensdumpar i dumps/). Ren stdlib,
ingen MIDI. Dump-layouten i detalj: docs/midi.md avsnitt 6.

    python syx_tools.py hex  dump.syx [--start 0 --length 256]
    python syx_tools.py eq   dump.syx            # 31+31 grafiska band + de 6 PEQ-filtren
    python syx_tools.py diff a.syx b.syx         # råa byte, GEQ/PEQ + ändrade bit-spann

patch_dump() gör inversen av decode_*: skriver in GEQ-band och PEQ-poster i
en befintlig dump (allt annat - header, master, okartlagda block - bevaras),
så en patchad dump kan pushas tillbaka till enheten. Se rew_to_dsp8000.py apply.

SND MEMORY DUMP / SysEx-svar (`F0 00 20 32 00 01 4F 0A|12 …  F7`):
  * 10-byte header, sedan 12100 databyte, alla < 128 (7-bit-safe) men BIT-PACKAT.
    Databyten packas MSB-först till en bitström; fälten läses ur den. Verifierat
    mot enheten 2026-09-02 (`probe`, `probe --manual`). Samma för 4F 0A / 4F 12.
  * GEQ: från bit GEQ_BIT_OFFSET (372), 64 tecknade 8-bitarsvärden — 31 vä band
    (20 Hz–20 kHz), vä master, 31 hö band, hö master. **0,5 dB per enhet**
    (dB = värde / 2, ±16 dB = ±32) — enhetens egna steg, inte CC:ts 0,25 dB.
  * PEQ: 6 poster à 32 bitar från bit PEQ_BIT_OFFSET, ordning L1 R1 L2 R2 L3 R3.
    Per post: frekvens (13 bit = 5 bit ISO-bandindex + 8 bit finsteg om
    1/64 oktav, se peq_freq_hz),
    bandbredd (8 bit, (raw+1)/60 oktav), gain (10-bit tvåkomplement, dB = raw/8).
    Postens sista bit tillhör nästa (okartlagda) block - skriv den inte.
    FB-D-läget per filter (ON/OFF/SGL på enheten) lagras INTE i dumpen
    (verifierat 2026-09-03 åt båda hållen: noll byte skiljer). Med ON flyttar
    feedback destroyern filtret själv - sätt OFF före en skrivning.
  * Master (index 31 och 63) har samma skala som banden, verifierat 2026-09-03
    (−0,5 dB -> −1, +1 dB -> +2). decode_geq returnerar den rått.
  * Resten (delay, gate, limiter, 100 program) är inte kartlagt.
"""
import argparse
from pathlib import Path

import dsp8000

DUMP_HEADER_LEN = 10          # 00 20 32 00 01 4F xx yy 20 00
GEQ_BIT_OFFSET = 372          # bit-offset till första bandet i den MSB-packade strömmen
GEQ_DB_PER_UNIT = 0.5         # dumpens steg (INTE CC:ts 0,25 dB) - verifierat 2026-09-03
GEQ_COUNT = 64               # 31 vä band + vä master + 31 hö band + hö master
PEQ_BIT_OFFSET = 87          # bit-offset till första PEQ-posten (L1)
PEQ_REC_BITS = 32            # bitar per PEQ-post: 13 frekvens + 8 bandbredd + 10 gain + 1 oanvänd
PEQ_FREQ_BITS = 13           # 5 bit ISO-bandindex + 8 bit finsteg (se peq_freq_hz)
PEQ_BW_BITS = 8              # 0-120 (1/60 oktav per steg) ryms i 8 bitar
PEQ_GAIN_BITS = 10           # den 32:a biten i posten tillhör NÄSTA block - rör den inte
PEQ_FINE_PER_OCT = 64        # finstegets upplösning: 1/64 oktav över bandets ISO-frekvens
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
    dB, redan skalat. master returneras rått i samma skala (0,5 dB/enhet)
    - multiplicera med GEQ_DB_PER_UNIT för dB."""
    bits = _msb_bits(b[1 + DUMP_HEADER_LEN:-1])
    vals = []
    for n in range(GEQ_COUNT):
        p = GEQ_BIT_OFFSET + 8 * n
        v = 0
        for i in range(8):
            v = (v << 1) | bits[p + i]
        vals.append(v - 256 if v >= 128 else v)
    return {"L": [v * GEQ_DB_PER_UNIT for v in vals[:31]], "L_master": vals[31],
            "R": [v * GEQ_DB_PER_UNIT for v in vals[32:63]], "R_master": vals[63]}


def peq_freq_hz(raw):
    """PEQ-frekvensfältets 13 bitar -> Hz.

    Fältet är INTE ett logaritmiskt tal utan två delar: höga 5 bitar = index i
    de 31 ISO-tersbanden (0 = 20 Hz, 17 = 1 kHz, 30 = 20 kHz), låga 8 bitar =
    finsteg om 1/64 oktav uppåt från bandet. Verifierat 2026-09-03 mot enheten:
    ett handsatt 1 kHz-filter gav 0x1100 (band 17, fin 0), enhetens egna
    destroyer-filter 0x1D00/0x1D05/0x1D0A/0x1D0F (16 kHz + 5, 10, 15 finsteg)
    och 0x1E00 = 20 kHz, och 0x0527 (band 5 = 63 Hz, fin 39) visades som
    96,150 Hz mot modellens 96,11."""
    band = min(raw >> 8, len(dsp8000.ISO_BANDS) - 1)
    return dsp8000.ISO_BANDS[band] * 2 ** ((raw & 0xFF) / PEQ_FINE_PER_OCT)


def peq_freq_raw(freq_hz):
    """Hz -> frekvensfältets 13 bitar. Inversen av peq_freq_hz: närmaste
    ISO-band under frekvensen + finsteg om 1/64 oktav (blir högst 23, eftersom
    ISO-banden inte är exakta tersband). Kodningen är inte entydig - enheten
    själv skrev 0x0527 (63 Hz + 39 steg) för 96 Hz - men alla varianter läses
    lika av peq_freq_hz. Klipps till enhetens spann 20 Hz-20 kHz."""
    import math
    f = min(max(freq_hz, dsp8000.ISO_BANDS[0]), dsp8000.ISO_BANDS[-1])
    band = max(i for i, b in enumerate(dsp8000.ISO_BANDS) if b <= f)
    fine = min(255, max(0, round(PEQ_FINE_PER_OCT * math.log2(f / dsp8000.ISO_BANDS[band]))))
    return (band << 8) | fine


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
        fr = _read_uint(bits, base, PEQ_FREQ_BITS)
        bw = _read_uint(bits, base + PEQ_FREQ_BITS, PEQ_BW_BITS)
        g = _read_uint(bits, base + 21, PEQ_GAIN_BITS)
        g = g - 1024 if g >= 512 else g
        out.append({
            "freq_hz": peq_freq_hz(fr),
            "bw_oct": (bw + 1) / 60,
            "gain_db": g / 8,
            "on": bool(fr or bw or g),
        })
    return out


def bit_diff(a, b, gap=8):
    """Bit-spann som skiljer två dumpar: [(start, bredd, före, efter)].

    Databyten är bit-packade, så ett fält ligger sällan på byte-gränser - en
    byte-diff pekar ut fel ställe. Bit-offset här är samma skala som
    GEQ_BIT_OFFSET/PEQ_BIT_OFFSET och docs/midi.md 6.4. Spann med färre än
    `gap` oförändrade bitar emellan slås ihop (ett fält som byter värde rör
    sällan alla sina bitar). Verktyget för att kartlägga nya fält: dumpa,
    ändra EN sak, dumpa, se vilket spann som rörde sig."""
    x = _msb_bits(a[1 + DUMP_HEADER_LEN:-1])
    y = _msb_bits(b[1 + DUMP_HEADER_LEN:-1])
    spans = []
    for i in range(min(len(x), len(y))):
        if x[i] == y[i]:
            continue
        if spans and i - spans[-1][1] < gap:
            spans[-1][1] = i + 1
        else:
            spans.append([i, i + 1])
    return [(s, e - s, _read_uint(x, s, e - s), _read_uint(y, s, e - s))
            for s, e in spans]


def bit_label(start):
    """Vilket känt block en bit-position ligger i - 'okänt' = kandidat till
    ett nytt fält (delay, limiter, gate, program ...)."""
    n = (start - GEQ_BIT_OFFSET) // 8
    if 0 <= n < GEQ_COUNT:
        band = n % 32
        ch = "L" if n < 32 else "R"
        return f"GEQ {ch} " + (f"{dsp8000.ISO_BANDS[band]:g} Hz" if band < 31 else "master")
    k = (start - PEQ_BIT_OFFSET) // PEQ_REC_BITS
    if 0 <= k < len(PEQ_LABELS):
        return f"PEQ {PEQ_LABELS[k]}"
    return "okänt"


def print_bit_diff(a, b):
    for start, width, x, y in bit_diff(a, b):
        d = start // 7
        print(f"  bit {start}-{start + width - 1} ({width} b, data[{d}]): "
              f"{x} -> {y}   ({bit_label(start)})")


def _set_bits(data, pos, width, value):
    """Skriv `width` bitar av `value` (MSB först) i den 7-bit-packade bitströmmen
    `data` (bytearray av databyte utan F0/header/F7), med start på bit `pos`.
    Rör bara bit 0-6 i varje byte -> resultatet förblir < 128 (7-bit-safe)."""
    for i in range(width):
        bit = (value >> (width - 1 - i)) & 1
        byte, off = (pos + i) // 7, 6 - ((pos + i) % 7)
        if bit:
            data[byte] |= 1 << off
        else:
            data[byte] &= ~(1 << off)


def geq_value(db):
    """dB -> det tecknade 8-bitarsvärde dumpen lagrar (0,5 dB/enhet, ±16 dB = ±32).
    OBS: inte samma skala som CC (0,25 dB/steg) - enheten lagrar halva."""
    return max(-32, min(32, round(db / GEQ_DB_PER_UNIT))) & 0xFF


def peq_raw(freq_hz, bw_oct, gain_db):
    """(frekvens, bandbredd okt, gain dB) -> (fr, bw, g) råvärden för dumpen,
    klippta till fältbredderna. Inversen av avkodningen i decode_peq."""
    import math
    fr = peq_freq_raw(freq_hz)
    bw = max(0, min(255, round(bw_oct * 60) - 1))
    g = max(-512, min(511, round(gain_db * 8))) & 0x3FF
    return fr, bw, g


def patch_dump(base, geq_L=None, geq_R=None, peqs=None):
    """Skriv GEQ och/eller PEQ i en befintlig dump och returnera den nya (F0…F7).

    base:   komplett minnesdump (bytes, F0…F7) att utgå från - allt som inte
            skrivs bevaras exakt (header, master, delay/gate/limiter, 100 program).
    geq_L/geq_R: lista med 31 dB (ISO-bandordning), eller None för att lämna kanalen.
    peqs:   lista med 6 poster i ordning L1 R1 L2 R2 L3 R3, var och en None (=OFF,
            nollställs) eller {'freq_hz','bw_oct','gain_db'}. None hela listan = rör inte PEQ.

    Master lämnas orört - avsiktligt: en rumskorrigering ska inte flytta
    utnivån. (Skalan är känd sedan 2026-09-03.) 7-bit-safe: se _set_bits."""
    if not is_memory_dump(base):
        raise SystemExit("patch_dump: base är inte en minnesdump (F0 00 20 32 00 01 4F …).")
    data = bytearray(base[1 + DUMP_HEADER_LEN:-1])
    for ch, gains in (("L", geq_L), ("R", geq_R)):
        if gains is None:
            continue
        if len(gains) != 31:
            raise SystemExit(f"patch_dump: {ch} behöver 31 bandvärden, fick {len(gains)}.")
        first = 0 if ch == "L" else 32          # 31 band + master mellan kanalerna
        for n, db in enumerate(gains):
            _set_bits(data, GEQ_BIT_OFFSET + 8 * (first + n), 8, geq_value(db))
    if peqs is not None:
        if len(peqs) != 6:
            raise SystemExit(f"patch_dump: peqs behöver 6 poster (L1 R1 L2 R2 L3 R3), fick {len(peqs)}.")
        for k, rec in enumerate(peqs):
            base_bit = PEQ_BIT_OFFSET + PEQ_REC_BITS * k
            fr, bw, g = ((0, 0, 0) if rec is None
                         else peq_raw(rec["freq_hz"], rec["bw_oct"], rec["gain_db"]))
            _set_bits(data, base_bit, PEQ_FREQ_BITS, fr)
            _set_bits(data, base_bit + PEQ_FREQ_BITS, PEQ_BW_BITS, bw)
            _set_bits(data, base_bit + 21, PEQ_GAIN_BITS, g)   # rör inte postens 32:a bit
    return base[:1 + DUMP_HEADER_LEN] + bytes(data) + base[-1:]


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
        print("\nÄndrade bit-spann (bit-offset som i docs/midi.md 6.4):")
        print_bit_diff(a, b)


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
