#!/bin/sh
# Skapar .venv vid behov, installerar beroenden (requirements.txt), kör steg 1.
#   ./run.sh                 -> rew_script.py (flaggor skickas vidare, t.ex. --no-peq)
#   ./run.sh send --dry-run  -> rew_to_dsp8000.py send --dry-run
#   ./run.sh show            -> show_config.py
#   ./run.sh test            -> test_rew_script.py
set -e
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

case "$1" in
  ports|monitor|sysex|calibrate|send) exec .venv/bin/python rew_to_dsp8000.py "$@" ;;
  show)  shift; exec .venv/bin/python show_config.py "$@" ;;
  test)  shift; exec .venv/bin/python test_rew_script.py "$@" ;;
  *)     exec .venv/bin/python rew_script.py "$@" ;;
esac
