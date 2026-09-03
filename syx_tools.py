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

Minnesdumpen (`F0 00 20 32 00 01 4F <12104 databyte> F7` = 12112 byte):
  * Efter kommandobyten 4F följer 12104 databyte, 7-bitars-packade MSB-först:
    8 databyte = 7 minnesbyte (avkodat ur Behringers EQ-Design, docs/midi.md 6.8
    - den packar och packar upp exakt så). Uppackat: en minnesbild på 10591 byte:
      byte 0-9     huvud: [0] statusflaggor, [3] crossfade (s), [4] shelving-lutning
                   (steg om 3 dB/okt), [5] limiter (0 = av, annars 255-tröskel),
                   [6] gate (0 = av, annars +1), [8] = [9] = aktuellt program (0-baserat)
      byte 10-113  program 0 = arbetsbufferten (104 byte, nedan)
      byte 114-189 76 byte som EQ-Design hoppar över (okänt innehåll)
      byte 190-    program 1..100 à 104 byte
    Program (104 byte): delay L, delay R (16 bit big-endian), 6 PEQ-poster à 4 byte
    i ordning L1 R1 L2 R2 L3 R3, namn 12 tecken (ASCII - 0x20), GEQ L 32 byte
    (31 band + master, tecknat, 0,5 dB/enhet), GEQ R 32 byte.
    PEQ-post: [ISO-bandindex 0-30][finsteg][bandbredd: (raw+1)/60 okt][gain: dB*2, tecknat].
    Frekvens = ISO[band] + (ISO[band+1] - ISO[band]) * finsteg/20 - linjär
    interpolation, exakt vad enhetens display visar (0x0527 -> 96,150 Hz).
    Verifierat mot enhetens dumpar (programnamn, programnummer, displayvärden).
  * Fälten läses här ur bitströmmen räknat från fil-offset 11 (GEQ_BIT_OFFSET,
    PEQ_BIT_OFFSET): samma bitar, bara 28 bitar (4 packade byte) in i bilden.
    unpack_image() ger hela bilden byteinriktad.
  * FB-D-läget per filter (ON/OFF/SGL på enheten) lagras INTE i dumpen
    (verifierat 2026-09-03 åt båda hållen: noll byte skiljer). Med ON flyttar
    feedback destroyern filtret själv - sätt OFF före en skrivning.
  * Master (index 31 och 63) har samma skala som banden, verifierat 2026-09-03
    (−0,5 dB -> −1, +1 dB -> +2). decode_geq returnerar den rått.
"""
import argparse
from pathlib import Path

import dsp8000

DUMP_HEADER_LEN = 10          # 00 20 32 00 01 4F + 4 packade databyte; bitströmmen nedan börjar på fil-offset 11
GEQ_BIT_OFFSET = 372          # = minnesbyte 50 (huvud 10 + 40 in i program 0), 0,5 dB/enhet
GEQ_DB_PER_UNIT = 0.5         # dumpens steg (INTE CC:ts 0,25 dB) - verifierat 2026-09-03
GEQ_COUNT = 64               # 31 vä band + vä master + 31 hö band + hö master
PEQ_BIT_OFFSET = 84          # = minnesbyte 14 (program 0 byte 4). Var 87 (3 bitar fel) till 2026-09-03
PEQ_REC_BITS = 32            # 4 byte per post: bandindex, finsteg, bandbredd, gain
PEQ_FINE_PER_BAND = 20       # finsteg per tersband: linjär interpolation mellan ISO-frekvenserna
PEQ_LABELS = ["L1", "R1", "L2", "R2", "L3", "R3"]
IMAGE_LEN = 10591            # uppackad minnesbild
PROG_LEN = 104               # byte per program i bilden
PROG_OFFSET = {0: 10}        # program 0 (arbetsbufferten) på byte 10, program n på 190 + 104*(n-1)
for _n in range(1, 101):
    PROG_OFFSET[_n] = 190 + PROG_LEN * (_n - 1)


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
    """PEQ-frekvensens två byte (bandindex << 8 | finsteg) -> Hz.

    Höga byten = index i de 31 ISO-tersbanden (0 = 20 Hz, 17 = 1 kHz, 30 = 20 kHz),
    låga byten = finsteg i tjugondelar av avståndet till NÄSTA ISO-frekvens,
    linjärt (EQ-Design 0x401430; enheten räknar likadant: 0x0527 = 63 + 17*39/20
    = 96,150 Hz på displayen, 0x1D05/0x1D0A/0x1D0F = 17/18/19 kHz exakt).
    Finsteget får överstiga 19 - enheten skrev själv 39."""
    iso = dsp8000.ISO_BANDS
    band, fine = min(raw >> 8, len(iso) - 1), raw & 0xFF
    if band >= len(iso) - 1:
        return float(iso[-1])
    return iso[band] + (iso[band + 1] - iso[band]) * fine / PEQ_FINE_PER_BAND


def peq_freq_raw(freq_hz):
    """Hz -> (bandindex << 8 | finsteg). Inversen av peq_freq_hz, normaliserad
    så finsteget blir 0-19 (samma kodning som EQ-Design skriver). Klipps till
    enhetens spann 20 Hz-20 kHz."""
    iso = dsp8000.ISO_BANDS
    f = min(max(freq_hz, iso[0]), iso[-1])
    band = max(i for i, b in enumerate(iso) if b <= f)
    if band >= len(iso) - 1:
        return band << 8
    fine = round((f - iso[band]) / (iso[band + 1] - iso[band]) * PEQ_FINE_PER_BAND)
    if fine >= PEQ_FINE_PER_BAND:
        band, fine = band + 1, 0
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
        hi, lo, bw, g = (_read_uint(bits, base + 8 * i, 8) for i in range(4))
        g = g - 256 if g >= 128 else g
        out.append({
            "freq_hz": peq_freq_hz(hi << 8 | lo),
            "bw_oct": (bw + 1) / 60,
            "gain_db": g / 2,
            "on": bool(hi or lo or bw or g),
        })
    return out


def unpack7(packed):
    """8 packade 7-bitarsbyte -> 7 byte, MSB-först (EQ-Design 0x4041d0)."""
    bits = _msb_bits(packed)
    return bytes(_read_uint(bits, i, 8) for i in range(0, len(bits) - 7, 8))


def pack7(data):
    """Inversen: 7 byte -> 8 databyte < 128, MSB-först (EQ-Design 0x403f70).
    Fylls ut med nollor till jämn 7-grupp."""
    data = list(data) + [0] * (-len(data) % 7)
    bits = "".join(f"{x:08b}" for x in data)
    return bytes(int(bits[i:i + 7], 2) for i in range(0, len(bits), 7))


def unpack_image(b):
    """Komplett minnesdump (F0…F7) -> minnesbilden på IMAGE_LEN byte, byteinriktad."""
    return unpack7(b[7:-1])


def program_name(image, n):
    """Programnamnet (12 tecken, lagrade som ASCII - 0x20) för program n (0 = arbetsbufferten)."""
    o = PROG_OFFSET[n] + 28
    return "".join(chr(c + 0x20) for c in image[o:o + 12])


def current_program(image):
    """Aktuellt program, 0-baserat (displayen visar +1). Ligger dubbelt i huvudet."""
    return image[8]


def geq_message(geq_L, geq_R, master_L_db=0.0, master_R_db=0.0, prog=0):
    """EQ-Design:s kommando 21 (payload efter modellbyten): [21, prog, 32 L, 32 R],
    värde = dB*2 + 32 (0-64, 32 = 0 dB), band 0-30 + master per kanal, opackat.
    Skriver alltid master - därför tas den i dB, default 0. Verifierat mot
    enheten 2026-09-03 (docs/midi.md 6.8)."""
    if len(geq_L) != 31 or len(geq_R) != 31:
        raise SystemExit("geq_message: 31 bandvärden per kanal.")

    def v(db):
        return max(0, min(64, round(db * 2) + 32))
    return bytes([0x21, prog] + [v(x) for x in geq_L] + [v(master_L_db)]
                 + [v(x) for x in geq_R] + [v(master_R_db)])


def peq_message(peqs):
    """EQ-Design:s kommando 22: [22, 00] + 32 packade byte = 6 poster à 4 byte
    (L1 R1 L2 R2 L3 R3, None = OFF/noll) + 4 byte fyll. Verifierat 2026-09-03."""
    if len(peqs) != 6:
        raise SystemExit("peq_message: 6 poster (L1 R1 L2 R2 L3 R3).")
    recs = []
    for rec in peqs:
        fr, bw, g = ((0, 0, 0) if rec is None
                     else peq_raw(rec["freq_hz"], rec["bw_oct"], rec["gain_db"]))
        recs += [fr >> 8, fr & 0xFF, bw, g]
    return bytes([0x22, 0x00]) + pack7(recs + [0, 0, 0, 0])


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
    tb = (start + 28) // 8            # minnesbyte (bitströmmen börjar 4 packade byte in)
    if tb < 10:
        return "huvud"
    if tb < 14:
        return "delay"
    if 38 <= tb < 50:
        return "namn"
    if 114 <= tb < 190:
        return "gap (okänt)"
    if tb >= 190:
        return f"program {(tb - 190) // PROG_LEN + 1}"
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
    """(frekvens, bandbredd okt, gain dB) -> (fr, bw, g) råvärden för dumpen:
    fr = bandindex << 8 | finsteg, bw 0-119, g = dB*2 tecknat (enhetens spann
    -48..+16 dB). Inversen av avkodningen i decode_peq."""
    fr = peq_freq_raw(freq_hz)
    bw = max(0, min(119, round(bw_oct * 60) - 1))
    g = max(-96, min(32, round(gain_db * 2))) & 0xFF
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
            for i, v in enumerate((fr >> 8, fr & 0xFF, bw, g)):
                _set_bits(data, base_bit + 8 * i, 8, v)
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
    img = unpack_image(b)
    print(f"{args.file}: {len(b)} byte, statusbyte {img[0]:08b}, program {current_program(img) + 1} "
          f"({program_name(img, 0).strip() or '-'}), crossfade {img[3]} s, shelving {img[4] * 3} dB/okt, "
          f"limiter {'av' if img[5] == 0 else img[5]}, gate {'av' if img[6] == 0 else img[6]}")
    print(f"31 ISO-band: {', '.join(f'{f:g}' for f in dsp8000.ISO_BANDS)} Hz")
    _print_geq(decode_geq(b))
    _print_peq(decode_peq(b))
    names = [(n, program_name(img, n).strip()) for n in range(1, 101)]
    used = [f"{n}:{nm}" for n, nm in names if nm]
    print(f"program med namn ({len(used)}): " + (", ".join(used) if used else "-"))


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
