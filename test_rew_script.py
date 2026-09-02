"""Självtest utan ramverk: .venv/bin/python test_rew_script.py"""
import rew_script as r

r.time.sleep = lambda s: None  # inga riktiga väntetider


def test_list_measurements_flattens_and_sorts():
    r.api_get = lambda p: {"2": {"title": "B"}, "1": {"title": "A"}}
    out = r.list_measurements()
    assert [m["id"] for m in out] == ["1", "2"], out
    assert out[0]["title"] == "A"


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


def test_keep_top_filters_picks_biggest_and_reorders():
    sent = {}
    r.api_post = lambda p, b: sent.update(b) or {}
    r.api_get = lambda p: []  # get_filters efter skrivning, oviktigt här
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
    assert len(sent["filters"]) == 20  # resten None


def test_fit_scale_recovers_known_line():
    import rew_to_dsp8000 as m
    # dB = 0.25*cc - 16  -> CC 0 = -16, CC 127 = +15.75
    readings = [(cc, 0.25 * cc - 16) for cc in (0, 32, 64, 127)]
    lo, hi, step = m.fit_scale(readings)
    assert abs(lo - (-16)) < 1e-9, lo
    assert abs(hi - 15.75) < 1e-9, hi
    assert abs(step - 0.25) < 1e-9, step


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("alla självtester gick igenom")
