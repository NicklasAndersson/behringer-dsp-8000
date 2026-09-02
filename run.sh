#!/bin/sh
# Skapar .venv vid behov, installerar beroenden, kör steg 1.
set -e
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check requests
exec .venv/bin/python rew_script.py "$@"   # t.ex. ./run.sh --no-peq
