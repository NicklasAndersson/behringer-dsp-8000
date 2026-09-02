"""Självtest utan ramverk (bara stdlib + requests-import):
    .venv/bin/python test_rew_script.py
Kör även dsp8000.py:s självtest. Behöver INTE mido/REW/enheten."""
import base64
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import dsp8000
import rew_script as r
import rew_to_dsp8000 as m   # importerbar utan mido (mido = None då)
import syx_tools

r.time.sleep = lambda s: None  # inga riktiga väntetider
_ORIG = (r.api_get, r.api_post, r.api_delete)


def _reset():
    r.api_get, r.api_post, r.api_delete = _ORIG


def _curve(points, ppo=48):
    """Bygg ett REW-svar: {startFreq, ppo, magnitude(base64 be-float32)}
    från [(freq, dB)] - dB sätts per punkt via linjär interpolation i log-f."""
    f0, f1 = 10.0, 30000.0
    n = int(math.log2(f1 / f0) * ppo)
    vals = []
    for i in range(n):
        f = f0 * 2 ** (i / ppo)
        vals.append(_interp(points, f))
    return {"startFreq": f0, "ppo": ppo,
            "magnitude": base64.b64encode(struct.pack(f">{n}f", *vals)).decode()}


def _interp(points, f):
    if f <= points[0][0]:
        return points[0][1]
    for (fa, va), (fb, vb) in zip(points, points[1:]):
        if fa <= f <= fb:
            t = (math.log(f) - math.log(fa)) / (math.log(fb) - math.log(fa))
            return va + t * (vb - va)
    return points[-1][1]


def test_list_measurements_flattens_and_sorts():
    r.api_get = lambda p: {"2": {"title": "B"}, "1": {"title": "A"}, "10": {"title": "C"}}
    out = r.list_measurements()
    assert [x["id"] for x in out] == ["1", "2", "10"], out   # numerisk, inte lexikal
    assert out[0]["title"] == "A"


def test_find_measurement_by_id():
    r.api_get = lambda p: {"1": {"title": "A"}, "7": {"title": "G"}}
    assert r.find_measurement(7)["title"] == "G"
    try:
        r.find_measurement("99")
        assert False, "skulle ha kastat SystemExit"
    except SystemExit:
        pass


def test_get_filters_drops_empty_slots():
    r.api_get = lambda p: [
        {"index": 1, "type": "PK", "frequency": 44.0, "gaindB": -11.0, "q": 3.5},
        {"index": 2, "type": "None"},
        {"index": 3, "type": None},
    ]
    assert [f["index"] for f in r.get_filters("1")] == [1]


def test_eq_command_waits_for_matching_process():
    r.api_post = lambda p, b: {"message": "Match target ID 5 in progress"}
    seen = []
    # först ett gammalt resultat, sedan vårt
    results = iter([
        {"processName": "Match target ID 4", "message": "Completed"},
        {"processName": "Match target ID 5", "message": "Completed"},
    ])
    r.api_get = lambda p: seen.append(1) or next(results)
    r.eq_command("1", "Match target")
    assert len(seen) == 2, seen  # väntade förbi det gamla resultatet


def test_eq_command_sync_returns_immediately():
    r.api_post = lambda p, b: {"message": "Calculate target level done"}
    r.api_get = lambda p: (_ for _ in ()).throw(AssertionError("skulle inte polla"))
    r.eq_command("1", "Calculate target level")


def test_keep_top_filters_picks_biggest_and_reorders():
    sent = {}
    r.api_post = lambda p, b: sent.update(b) or {}
    r.api_get = lambda p: [{"type": "None"}] * 22  # 22 platser (Generic/Generic)
    fs = [
        {"type": "PK", "frequency": 300, "gaindB": -3, "q": 5},
        {"type": "PK", "frequency": 44, "gaindB": -12, "q": 3},
        {"type": "PK", "frequency": 160, "gaindB": -8, "q": 6},
        {"type": "PK", "frequency": 80, "gaindB": -10, "q": 2},
    ]
    r.keep_top_filters("1", fs, n=3)
    kept = [x for x in sent["filters"] if x["type"] != "None"]
    assert [x["frequency"] for x in kept] == [44, 80, 160]  # 3 största |gain|, sorterade på freq
    assert [x["index"] for x in kept] == [1, 2, 3]
    assert len(sent["filters"]) == 22  # resten None, lika många platser som REW har


def test_keep_top_filters_skips_shelf_filters():
    """Shelf-filter saknar q och kan inte göras på DSP8000:s PEQ - de ska
    varken krascha (KeyError) eller ta en av de 3 platserna."""
    sent = {}
    r.api_post = lambda p, b: sent.update(b) or {}
    r.api_get = lambda p: [{"type": "None"}] * 20
    fs = [
        {"type": "LS", "frequency": 100, "gaindB": -14},           # ingen q
        {"type": "PK", "frequency": 44, "gaindB": -12, "q": 3},
        {"type": "PK", "frequency": 80, "gaindB": -2, "q": 2},
    ]
    r.keep_top_filters("1", fs, n=3)
    kept = [x for x in sent["filters"] if x["type"] != "None"]
    assert [x["frequency"] for x in kept] == [44, 80], kept


def test_keep_top_filters_noop_when_few_enough():
    r.api_post = lambda p, b: (_ for _ in ()).throw(AssertionError("skulle inte skriva"))
    fs = [{"type": "PK", "frequency": 44, "gaindB": -12, "q": 3}]
    assert r.keep_top_filters("1", fs, n=3) == fs


def test_decode_curve_and_value_at():
    c = r._decode_curve(_curve([(10, 0.0), (100, 10.0), (30000, 10.0)]))
    assert abs(r._value_at(c, 10) - 0.0) < 0.2
    assert abs(r._value_at(c, 100) - 10.0) < 0.2
    assert abs(r._value_at(c, math.sqrt(10 * 100)) - 5.0) < 0.3  # log-mitt
    assert r._value_at(c, 1) == c[0][1] and r._value_at(c, 1e6) == c[-1][1]


def test_decode_curve_drops_nan():
    d = _curve([(10, 0.0), (30000, 0.0)])
    raw = bytearray(base64.b64decode(d["magnitude"]))
    raw[:8] = struct.pack(">2f", float("nan"), float("inf"))
    d["magnitude"] = base64.b64encode(bytes(raw)).decode()
    c = r._decode_curve(d)
    assert all(math.isfinite(v) for _, v in c) and len(c) == len(raw) // 4 - 2


def test_graphic_band_gains_clamps_and_centres():
    # respons: +10 dB puckel vid 63 Hz, -10 dB dipp vid 2 kHz, annars 80 dB
    meas = [(10, 80), (50, 80), (63, 90), (80, 80), (1600, 80), (2000, 70),
            (2500, 80), (30000, 80)]
    tgt = [(10, 80), (30000, 80)]
    r.api_get = lambda p: _curve(tgt) if "target-response" in p else _curve(meas)
    g = r.graphic_band_gains("1", after_peq=False)
    assert set(g) == set(dsp8000.ISO_BANDS)
    assert -10.5 <= g[63] <= -9.5, g[63]              # puckel -> cut (63 Hz ligger
                                                      # inte exakt på ppo-gridet)
    assert g[2000] == dsp8000.SAFE_BOOST_DB, g[2000]  # dipp -> boost, kapad till +3
    assert g[1000] == 0.0                             # median = 0 -> orörd
    assert all(v == round(v * 2) / 2 for v in g.values())  # 0,5 dB-steg


def test_graphic_band_gains_refine_adds_base():
    meas = [(10, 80), (30000, 80)]
    r.api_get = lambda p: _curve(meas)
    base = {63: -6.0, 2000: 2.5}
    g = r.graphic_band_gains("1", after_peq=False, base=base)
    assert g[63] == -6.0 and g[2000] == 2.5 and g[1000] == 0.0


def test_graphic_band_gains_uses_eq_response_after_peq():
    urls = []
    r.api_get = lambda p: urls.append(p) or _curve([(10, 80), (30000, 80)])
    r.graphic_band_gains("1", after_peq=True)
    assert any("/eq/frequency-response" in u for u in urls), urls
    urls.clear()
    r.graphic_band_gains("1", after_peq=False)
    assert not any("/eq/frequency-response" in u for u in urls), urls


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.json"
        gains = {f: 0.0 for f in dsp8000.ISO_BANDS}
        gains[31.5] = -2.5
        gains[20] = 3.0
        r.save_output({"id": "1"}, [{"type": "PK", "frequency": 44, "gaindB": -12, "q": 3}],
                      gains, path=path)
        peq, back = r.load_previous_output(path)
        assert back == gains, back                 # "31.5"/"20" -> 31.5/20
        assert peq[0]["frequency"] == 44
        m.JSON_FILE = path
        assert m.load_band_gains() == gains


def test_coerce_types():
    assert r._coerce("25") == 25 and isinstance(r._coerce("25"), int)
    assert r._coerce("1.5") == 1.5
    assert r._coerce("true") is True and r._coerce("False") is False
    assert r._coerce("Room") == "Room"


def test_parse_kv():
    import argparse
    assert r._parse_kv("lowFreqCutoffHz=25") == ("lowFreqCutoffHz", 25)
    assert r._parse_kv("shape=Manual") == ("shape", "Manual")
    try:
        r._parse_kv("no-equals-sign")
        assert False, "skulle ha kastat ArgumentTypeError"
    except argparse.ArgumentTypeError:
        pass


def test_set_target_settings_merges_onto_existing():
    sent = {}
    r.api_get = lambda p: {"shape": "Manual", "lowFreqCutoffHz": 20, "slopedBOct": 0.0}
    r.api_post = lambda p, b: sent.update({"path": p, "body": b}) or {}
    merged = r.set_target_settings("1", {"lowFreqCutoffHz": 25})
    assert merged == {"shape": "Manual", "lowFreqCutoffHz": 25, "slopedBOct": 0.0}
    assert sent["path"] == "/measurements/1/target-settings"
    assert sent["body"] == merged


def test_set_target_settings_noop_without_overrides():
    r.api_get = lambda p: (_ for _ in ()).throw(AssertionError("skulle inte läsa"))
    r.api_post = lambda p, b: (_ for _ in ()).throw(AssertionError("skulle inte skriva"))
    assert r.set_target_settings("1", {}) is None
    assert r.set_target_settings("1", None) is None


def test_set_house_curve_order_and_endpoints():
    calls = []
    r.api_post = lambda p, b: calls.append(("POST", p, b)) or {}
    r.api_delete = lambda p: calls.append(("DELETE", p, None))
    r.set_house_curve(path="/tmp/curve.txt", clear=True, log_interpolation=True)
    # log-interpolation ska sättas FÖRE filen (REW:s dokumenterade ordning)
    assert calls == [
        ("POST", "/eq/house-curve-log-interpolation", True),
        ("DELETE", "/eq/house-curve", None),
        ("POST", "/eq/house-curve", "/tmp/curve.txt"),
    ], calls


def test_run_match_target_applies_target_overrides():
    calls = []
    r.api_post = lambda p, b: calls.append((p, b)) or {"message": "done"}
    r.api_get = lambda p: {"shape": "Manual"}
    r.run_match_target("1", peq=False, target_overrides={"shape": "Room"})
    posted_paths = [p for p, _ in calls]
    assert "/measurements/1/target-settings" in posted_paths
    target_body = dict(calls)["/measurements/1/target-settings"]
    assert target_body == {"shape": "Room"}


def test_fit_scale_recovers_known_line():
    # dB = 0.25*cc - 16  -> CC 0 = -16, CC 127 = +15.75
    readings = [(cc, 0.25 * cc - 16) for cc in (0, 32, 64, 127)]
    lo, hi, step = m.fit_scale(readings)
    assert abs(lo - (-16)) < 1e-9, lo
    assert abs(hi - 15.75) < 1e-9, hi
    assert abs(step - 0.25) < 1e-9, step


def test_geq_status_lines_decodes_fader_frame():
    hdr = [0, 0x20, 0x32, 0, 1, 0x33, 9]
    left = [64] * 31 + [15]
    left[17] = 96                       # 1 kHz = +8 dB
    right = [64] * 31 + [16]
    lines = m.geq_status_lines(bytes(hdr + left + right))
    assert len(lines) == 2 and "+8.0" in lines[0] and "master=15" in lines[0], lines
    assert m.geq_status_lines(bytes(hdr[:5] + [0x4F, 0x12] + [0] * 64)) == []


def test_cc_roundtrip():
    for db in (-16, -12.5, -0.5, 0, 0.5, 3, 8, 15.5):
        assert dsp8000.cc_to_db(dsp8000.db_to_cc(db)) == db, db


def test_decode_geq_known_dumps():
    """De committade dumparna har känt GEQ-innehåll: _0db = allt 0 dB,
    _p16db = allt +16 dB. Fångar om bitström-offset/bredd/tecken går sönder."""
    here = Path(__file__).parent
    raw0 = (here / "dumps" / "dsp8000_sysex_0db.syx").read_bytes()
    zero = syx_tools.decode_geq(raw0)
    assert zero["L"] == [0.0] * 31 and zero["R"] == [0.0] * 31, zero
    # 4F 12-dumpen har bit 278 satt (R3 gain raw 1) - ska ändå visas som OFF
    assert all(not f["on"] for f in syx_tools.decode_peq(raw0)), syx_tools.decode_peq(raw0)
    mx = syx_tools.decode_geq((here / "dumps" / "dsp8000_sysex_p16db.syx").read_bytes())
    assert mx["L"] == [16.0] * 31 and mx["R"] == [16.0] * 31, mx


def test_decode_peq_roundtrips_a_record():
    """Bygg en dump med PEQ L1 = 1 kHz, 1 okt, -6 dB och läs tillbaka."""
    payload = bytearray(10 + 12100)
    payload[5:8] = b"\x4f\x0a\x40"
    bits = []
    fr = round(640 * math.log10(1000 / 20))          # ~1088
    bw = 60 - 1                                        # 1,000 okt -> raw 59
    g = -6 * 16                                        # -96
    for val, w in ((fr, 11), (bw, 10), (g & 0x7FF, 11)):
        for i in range(w):
            bits.append((val >> (w - 1 - i)) & 1)
    for i, bit in enumerate(bits):                     # posten börjar på bit 87
        pos = syx_tools.PEQ_BIT_OFFSET + i
        payload[10 + pos // 7] |= bit << (6 - pos % 7)
    fs = syx_tools.decode_peq(b"\xf0" + bytes(payload) + b"\xf7")
    assert fs[0]["on"] and abs(fs[0]["freq_hz"] - 1000) < 15, fs[0]
    assert abs(fs[0]["bw_oct"] - 1.0) < 0.02 and fs[0]["gain_db"] == -6.0, fs[0]
    assert all(not f["on"] for f in fs[1:]), fs


def test_decode_geq_roundtrips_a_single_band():
    """Bygg en dump med bara ett band satt, avkoda tillbaka samma dB."""
    payload = bytearray(10 + 12100)                     # header + nollor
    payload[5:8] = b"\x4f\x0a\x40"
    # band 5 vänster (63 Hz) = -8 dB -> s = -32; MSB-först i bit-strömmen
    n, s = 5, dsp8000.db_to_cc(-8.0) - 64
    for i in range(8):
        bit = (s >> (7 - i)) & 1
        pos = syx_tools.GEQ_BIT_OFFSET + 8 * n + i
        byte, off = pos // 7, 6 - (pos % 7)
        payload[10 + byte] |= bit << off
    g = syx_tools.decode_geq(b"\xf0" + bytes(payload) + b"\xf7")
    assert g["L"][5] == -8.0 and g["L"][4] == 0.0 and g["L"][6] == 0.0, g["L"][:8]


def test_push_sends_dump_and_saves_before_after():
    """push med fejkad MIDI: hela filen (utan F0/F7) ska gå ut som EN sysex,
    före-dumpen sparas som återställningspunkt, efter-dumpen diffas.
    --send-only: ingen dump hämtas, inga filer skrivs."""
    import builtins
    import contextlib
    import io
    import types
    here = Path(__file__).parent
    dump_path = here / "dumps" / "dsp8000_sysex_p16db.syx"
    dump = dump_path.read_bytes()
    zero = (here / "dumps" / "dsp8000_sysex_0db.syx").read_bytes()[1:-1]
    sent = []

    class FakePort:
        def send(self, msg): sent.append(msg)
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    saved = (m.mido, m.open_output, m.open_input, m.grab_dump, builtins.input)
    m.mido = types.SimpleNamespace(
        Message=lambda type, data: types.SimpleNamespace(type=type, data=data))
    m.open_output = m.open_input = FakePort
    try:
        grabs = iter([zero, dump[1:-1]])
        m.grab_dump = lambda out, inp: next(grabs)
        answers = iter(["", "ja"])   # Enter vid checklistan, ja vid sändning
        builtins.input = lambda prompt="": next(answers)
        log = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), \
             contextlib.redirect_stdout(log):
            m.push(str(dump_path))
            before = list(Path(d).glob("probe_push_before_*.syx"))
            after = list(Path(d).glob("probe_push_after_*.syx"))
            assert len(before) == 1 and before[0].read_bytes() == b"\xf0" + zero + b"\xf7"
            assert len(after) == 1 and after[0].read_bytes() == dump
        assert "GEQ L 20 Hz: +0.00 -> +16.00 dB" in log.getvalue(), log.getvalue()[-600:]
        assert len(sent) == 1 and sent[0].type == "sysex", sent
        assert bytes(sent[0].data) == dump[1:-1] and len(sent[0].data) == 12110

        # --send-only: ingen grab, inga filer
        sent.clear()
        m.grab_dump = lambda *a: (_ for _ in ()).throw(AssertionError("skulle inte dumpa"))
        answers = iter(["", "ja"])   # Enter vid checklistan, ja vid sändning
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), \
             contextlib.redirect_stdout(io.StringIO()):
            m.push(str(dump_path), send_only=True)
            assert not list(Path(d).glob("*.syx"))
        assert len(sent) == 1 and bytes(sent[0].data) == dump[1:-1]
    finally:
        m.mido, m.open_output, m.open_input, m.grab_dump, builtins.input = saved


def test_grab_with_retry_retries_on_enter_and_aborts_on_a():
    import builtins
    import contextlib
    import io
    saved = (m.grab_dump, builtins.input)
    try:
        grabs = iter([None, b"\x00" * 12110])
        m.grab_dump = lambda out, inp: next(grabs)
        builtins.input = lambda prompt="": ""          # Enter = försök igen
        with contextlib.redirect_stdout(io.StringIO()):
            assert m._grab_with_retry(None, None, "x") == b"\x00" * 12110
        m.grab_dump = lambda out, inp: None
        builtins.input = lambda prompt="": "a"         # a = avbryt
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                m._grab_with_retry(None, None, "x")
            assert False, "skulle ha avbrutit"
        except SystemExit:
            pass
    finally:
        m.grab_dump, builtins.input = saved


def test_patch_dump_roundtrips_and_stays_7bit():
    """Patcha en riktig 0 dB-dump med känd GEQ + PEQ, avkoda tillbaka samma
    värden, och kontrollera att inget vi inte skrev ändrades + 7-bit-safe."""
    here = Path(__file__).parent
    base = (here / "dumps" / "dsp8000_sysex_0db.syx").read_bytes()
    L = [0.0] * 31; L[5] = -8.0; L[17] = 3.0          # 63 Hz, 1 kHz
    R = [0.0] * 31; R[0] = -16.0; R[30] = 15.75       # 20 Hz, 20 kHz
    peqs = [{"freq_hz": 1000, "bw_oct": 1.0, "gain_db": -6.0}, None,
            None, None, None, {"freq_hz": 80, "bw_oct": 0.5, "gain_db": 4.0}]
    out = syx_tools.patch_dump(base, geq_L=L, geq_R=R, peqs=peqs)

    assert len(out) == len(base) and out[:1] == b"\xf0" and out[-1:] == b"\xf7"
    assert all(x < 128 for x in out[1:-1]), "databyte >= 128 - inte 7-bit-safe"
    g = syx_tools.decode_geq(out)
    assert g["L"] == L and g["R"] == R, (g["L"][:6], g["R"][:2])
    pq = syx_tools.decode_peq(out)
    assert pq[0]["on"] and abs(pq[0]["freq_hz"] - 1000) < 15 and pq[0]["gain_db"] == -6.0, pq[0]
    assert abs(pq[0]["bw_oct"] - 1.0) < 0.02, pq[0]
    assert pq[5]["on"] and pq[5]["gain_db"] == 4.0 and abs(pq[5]["freq_hz"] - 80) < 3, pq[5]
    assert all(not pq[k]["on"] for k in (1, 2, 3, 4)), pq
    # master orört: L/R-master samma som basen
    gb = syx_tools.decode_geq(base)
    assert g["L_master"] == gb["L_master"] and g["R_master"] == gb["R_master"]


def test_patch_dump_leaves_untouched_channel_and_bytes():
    here = Path(__file__).parent
    base = (here / "dumps" / "dsp8000_sysex_p16db.syx").read_bytes()   # allt +16
    out = syx_tools.patch_dump(base, geq_L=[0.0] * 31)                 # bara L -> 0
    g = syx_tools.decode_geq(out)
    assert g["L"] == [0.0] * 31 and g["R"] == [16.0] * 31, (g["L"][:3], g["R"][:3])
    # bara GEQ L-blocket ska skilja mot basen; PEQ + programblock orörda
    assert syx_tools.decode_peq(out) == syx_tools.decode_peq(base)
    assert out[2000:] == base[2000:]        # långt bortom GEQ/PEQ = programminne, orört


def test_suggestion_to_geq_peq_maps_json():
    data = {
        "graphic_band_gains_db": {"20": -0.5, "1000": 3.0, "20000": 2.5},
        "peq_filters": [
            {"frequency": 44, "gaindB": -3, "q": 3},
            {"frequency": 80, "gaindB": -12, "q": 2},   # störst |gain|
            {"frequency": 160, "gaindB": -8, "q": 6},
        ],
    }
    geq, peqs = m.suggestion_to_geq_peq(data)
    assert len(geq) == 31 and geq[0] == -0.5 and geq[17] == 3.0 and geq[30] == 2.5
    assert geq[dsp8000.ISO_BANDS.index(25)] == 0.0        # saknas i JSON -> 0
    # 3 filter, sorterade på frekvens, samma på L och R (L1 R1 L2 R2 L3 R3)
    assert len(peqs) == 6 and peqs[0] == peqs[1] and peqs[2] == peqs[3] and peqs[4] == peqs[5]
    assert [round(peqs[i]["freq_hz"]) for i in (0, 2, 4)] == [44, 80, 160]
    assert peqs[2]["gain_db"] == -12
    assert abs(peqs[0]["bw_oct"] - dsp8000.q_to_octaves(3)) < 1e-9


def test_suggestion_to_geq_peq_pads_missing_peq():
    data = {"graphic_band_gains_db": {}, "peq_filters": [
        {"frequency": 60, "gaindB": -5, "q": 4}]}
    geq, peqs = m.suggestion_to_geq_peq(data)
    assert geq == [0.0] * 31
    assert peqs[0] and peqs[1] and all(peqs[k] is None for k in (2, 3, 4, 5)), peqs


def test_apply_end_to_end_with_fake_midi():
    """apply med fejkad MIDI: bas hämtas, JSON patchas in, patchad dump pushas
    som EN sysex, återläsning verifieras. Bygger JSON + bas i en temp-katalog."""
    import builtins
    import contextlib
    import io
    import types
    here = Path(__file__).parent
    base = (here / "dumps" / "dsp8000_sysex_0db.syx").read_bytes()
    sent = []

    class FakePort:
        def send(self, msg): sent.append(msg)
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    saved = (m.mido, m.open_output, m.open_input, m.grab_dump, m.JSON_FILE, builtins.input)
    m.mido = types.SimpleNamespace(
        Message=lambda type, data: types.SimpleNamespace(type=type, data=list(data)))
    m.open_output = m.open_input = FakePort
    try:
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), \
             contextlib.redirect_stdout(io.StringIO()):
            gains = {str(f): 0.0 for f in dsp8000.ISO_BANDS}
            gains["1000"] = 3.0
            Path("rew_eq_suggestion.json").write_text(json.dumps({
                "graphic_band_gains_db": gains,
                "peq_filters": [{"frequency": 50, "gaindB": -6, "q": 4}]}))
            m.JSON_FILE = Path("rew_eq_suggestion.json")
            # bas hämtas först, sedan återläsning = den patchade (device tog emot)
            grabs = iter([base[1:-1]])
            m.grab_dump = lambda out, inp: (next(grabs) if sent == []
                                            else bytes(sent[-1].data))
            answers = iter(["", "ja"])                    # checklista, bekräfta
            builtins.input = lambda prompt="": next(answers)
            m.apply()
            applied = Path("dsp8000_applied.syx").read_bytes()
            g = syx_tools.decode_geq(applied)
            assert g["L"][17] == 3.0 and g["R"][17] == 3.0
            pq = syx_tools.decode_peq(applied)
            assert pq[0]["on"] and pq[0]["gain_db"] == -6.0 and pq[1] == pq[0]
        assert len(sent) == 1 and sent[0].type == "sysex" and len(sent[0].data) == 12110
        assert bytes(sent[0].data) == applied[1:-1]
    finally:
        m.mido, m.open_output, m.open_input, m.grab_dump, m.JSON_FILE, builtins.input = saved


def test_apply_dry_run_with_base_needs_no_device():
    import builtins
    import contextlib
    import io
    here = Path(__file__).parent
    base_src = here / "dumps" / "dsp8000_sysex_0db.syx"
    saved = (m.open_output, m.open_input, m.JSON_FILE, builtins.input)
    m.open_output = m.open_input = lambda *a: (_ for _ in ()).throw(
        AssertionError("dry-run med --base ska inte röra MIDI"))
    try:
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), \
             contextlib.redirect_stdout(io.StringIO()):
            (Path(d) / "base.syx").write_bytes(base_src.read_bytes())
            Path("rew_eq_suggestion.json").write_text(json.dumps({
                "graphic_band_gains_db": {"1000": -4.0}, "peq_filters": []}))
            m.JSON_FILE = Path("rew_eq_suggestion.json")
            builtins.input = lambda *a: (_ for _ in ()).throw(AssertionError("ska inte fråga"))
            m.apply(base_path="base.syx", dry_run=True)
            g = syx_tools.decode_geq(Path("dsp8000_applied.syx").read_bytes())
            assert g["L"][17] == -4.0 and g["R"][17] == -4.0
    finally:
        m.open_output, m.open_input, m.JSON_FILE, builtins.input = saved


def test_run_gui_allowlist_and_streams_help():
    """Starta panelen på en ledig port, avvisa okänt kommando, kör `help`,
    se att utskriften strömmas och exit-koden landar."""
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    import run_gui
    srv = ThreadingHTTPServer(("127.0.0.1", 0), run_gui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
        try:
            return json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    assert "error" in post("/run", {"cmdline": "ls"}), "okänt kommando ska avvisas"
    assert post("/run", {"cmdline": "help"}) == {"ok": True}
    run_gui.state["proc"].wait(timeout=10)
    for _ in range(50):                      # pump-tråden ska hinna skriva exit-raden
        if run_gui.state["exit"] is not None:
            break
        threading.Event().wait(0.05)         # time.sleep är bortpatchad ovan
    j = json.loads(urllib.request.urlopen(base + "/out?since=0&gen=0").read())
    assert not j["running"] and j["exit"] == 0, j
    assert "REW -> DSP8000" in j["text"] and "[klar, exit 0]" in j["text"], j["text"][:200]
    assert "error" in post("/stdin", {"line": "x"}), "stdin utan process ska ge fel"
    srv.shutdown()


def test_run_gui_device_read_write_and_suggestion():
    """run_gui:s enhetsendpoints med fejkad MIDI: read avkodar en dump, write
    patchar en färsk bas + skickar EN sysex + verifierar, suggestion läser JSON."""
    import builtins
    import contextlib
    import io
    import types
    import run_gui
    import rew_to_dsp8000 as rmod
    here = Path(__file__).parent
    base = (here / "dumps" / "dsp8000_sysex_0db.syx").read_bytes()
    sent = []

    class FakePort:
        def send(self, msg): sent.append(msg)
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    saved = (rmod.mido, rmod.open_output, rmod.open_input, rmod.grab_dump, rmod.JSON_FILE)
    rmod.mido = types.SimpleNamespace(
        Message=lambda type, data: types.SimpleNamespace(type=type, data=list(data)))
    rmod.open_output = rmod.open_input = FakePort
    try:
        # read
        rmod.grab_dump = lambda out, inp: base[1:-1]
        d = run_gui.device_read()
        assert d["geq_L"] == [0.0] * 31 and len(d["peq"]) == 3 and d["sub"] == "4f 12"

        # write: bas hämtas, patchad skickas, återläsning = det skickade
        sent.clear()
        rmod.grab_dump = lambda out, inp: base[1:-1] if not sent else bytes(sent[-1].data)
        with tempfile.TemporaryDirectory() as td, contextlib.chdir(td):
            geq = [0.0] * 31; geq[17] = 3.0
            peq = [{"on": True, "freq_hz": 50, "bw_oct": 0.33, "gain_db": -6.0},
                   {"on": False, "freq_hz": 60, "bw_oct": 0.3, "gain_db": 0},
                   {"on": False, "freq_hz": 60, "bw_oct": 0.3, "gain_db": 0}]
            res = run_gui.device_write(geq, peq)
            assert res["mismatches"] == [], res["mismatches"]
            applied = Path("dsp8000_applied.syx").read_bytes()
        assert len(sent) == 1 and sent[0].type == "sysex" and len(sent[0].data) == 12110
        g = syx_tools.decode_geq(applied); pq = syx_tools.decode_peq(applied)
        assert g["L"][17] == 3.0 and g["R"][17] == 3.0
        assert pq[0]["on"] and pq[0]["gain_db"] == -6.0 and pq[2]["on"] is False

        # suggestion
        with tempfile.TemporaryDirectory() as td, contextlib.chdir(td):
            Path("s.json").write_text(json.dumps({
                "graphic_band_gains_db": {"1000": -2.0},
                "peq_filters": [{"frequency": 44, "gaindB": -5, "q": 4}]}))
            rmod.JSON_FILE = Path("s.json")
            sug = run_gui.suggestion()
            assert sug["geq"][17] == -2.0 and sug["peq"][0]["on"] and round(sug["peq"][0]["freq_hz"]) == 44
            assert sug["peq"][1] is None
    finally:
        rmod.mido, rmod.open_output, rmod.open_input, rmod.grab_dump, rmod.JSON_FILE = saved


def test_run_gui_device_read_errors_without_mido():
    import run_gui
    import rew_to_dsp8000 as rmod
    saved = rmod.mido
    rmod.mido = None
    try:
        try:
            run_gui.device_read()
            assert False, "skulle ha kastat DeviceError"
        except run_gui.DeviceError:
            pass
    finally:
        rmod.mido = saved


def test_dsp8000_selftest():
    subprocess.run([sys.executable, "dsp8000.py"], check=True,
                   cwd=Path(__file__).parent, capture_output=True)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            _reset()
            fn()
            print("ok", name)
    print("alla självtester gick igenom")
