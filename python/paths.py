"""Var genererade filer hamnar. Allt under history/ (gitignorerad), sorterat
per typ i stället för strött i repo-roten. Committade exempel
(rew_eq_suggestion.json, dumps/) ligger kvar där de är.

    history/
      reads/        read-<ts>.syx        avläsningar av enhetens minne
      writes/       applied-<ts>.syx     patchade dumpar som pushades
      suggestions/  suggestion-<ts>-*.json   EQ-förslag från REW
      captures/     *.syx                råa monitor/sysex/probe/roundtrip-dumpar
      config/       config-<ts>.html     show_config.py

Sökvägarna är relativa arbetskatalogen - `run.sh` kör alltid från repo-roten,
precis som de andra skripten (JSON_FILE m.m.). Ren stdlib.
"""
import time
from pathlib import Path

HISTORY = Path("history")

READS = HISTORY / "reads"
WRITES = HISTORY / "writes"
SUGGESTIONS = HISTORY / "suggestions"
CAPTURES = HISTORY / "captures"
CONFIG = HISTORY / "config"

ALL = (READS, WRITES, SUGGESTIONS, CAPTURES, CONFIG)


def ts():
    """Sorterbar tidsstämpel för filnamn."""
    return time.strftime("%Y%m%d-%H%M%S")


def new(directory, name):
    """directory / name, med katalogen (och history/) skapad. `name` får redan
    innehålla en ts()."""
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


if __name__ == "__main__":       # ponytail: en körbar koll räcker
    import contextlib
    import tempfile
    assert all(d.parent == HISTORY for d in ALL)
    assert len(ts()) == 15 and ts().replace("-", "").isdigit()
    with tempfile.TemporaryDirectory() as d, contextlib.chdir(d):
        p = new(CAPTURES, f"probe-{ts()}.syx")
        assert p == CAPTURES / p.name and CAPTURES.is_dir() and not p.exists()
    print("paths: självtest ok")
