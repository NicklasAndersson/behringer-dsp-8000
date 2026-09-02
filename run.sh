#!/bin/sh
# Skapar .venv vid behov, installerar beroenden (requirements.txt), kör önskat steg.
# ./run.sh help visar den här listan.
set -e
cd "$(dirname "$0")"

usage() {
  cat <<'EOF'
REW -> DSP8000 (steg 1, rew_script.py):
  ./run.sh                        mät i REW, kör Match target, spara rew_eq_suggestion.json (frågar först)
  ./run.sh --no-peq               hoppa parametriska filter, bara 31-bands grafisk EQ
  ./run.sh --measurement ID       välj REW-mätning direkt i stället för att fråga
  ./run.sh --yes                  fråga inte, kör Match target direkt
  ./run.sh refine [flaggor]       andra varvet (mätning MED EQ:n på): --refine --yes + flaggorna vidare
  ./run.sh target                 visa REW:s riktiga target-settings-fältnamn (--show-target)
  ./run.sh target K=V [K=V ...]   sätt target-settings-fält + kör Match target direkt (--yes)
  ./run.sh house-curve PATH       sätt house curve-fil + kör Match target direkt (--yes)
  ./run.sh house-curve --clear    ta bort house curve + kör Match target direkt (--yes)

DSP8000 via MIDI (steg 2, rew_to_dsp8000.py):
  ./run.sh ports                  lista MIDI-portar
  ./run.sh monitor                lyssna på vad DSP8000 skickar (returväg)
  ./run.sh sysex                  fråga enheten via SysEx (dumpar minnet, se readme avsnitt 6)
  ./run.sh calibrate              kalibrera CC->dB mot enhetens display, en gång per enhet
  ./run.sh send --dry-run         visa vilka CC som skulle skickas, utan att skicka
  ./run.sh send                   skicka de 31 bandvärdena till DSP8000 (frågar först)

Övrigt:
  ./run.sh show                   generera + öppna dsp8000_config.html ur rew_eq_suggestion.json
  ./run.sh test                   självtester, kräver varken REW, mido eller enheten
  ./run.sh help                   den här listan

Alla underkommandon tar emot ytterligare flaggor efter sig, t.ex.
./run.sh refine --target slopedBOct=0.8  eller  ./run.sh send --channel left.
EOF
}

if [ "$1" = "help" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 0
fi

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

case "$1" in
  ports|monitor|sysex|calibrate|send)
    exec .venv/bin/python rew_to_dsp8000.py "$@" ;;
  show)
    shift; exec .venv/bin/python show_config.py "$@" ;;
  test)
    shift; exec .venv/bin/python test_rew_script.py "$@" ;;
  refine)
    # snabbt varv: mätning gjord MED EQ:n på, addera residualen, fråga inte
    shift; exec .venv/bin/python rew_script.py --refine --yes "$@" ;;
  target)
    shift
    if [ "$#" -eq 0 ]; then
      # utan KEY=VÄRDE: bara visa REW:s riktiga fältnamn, kör inget
      exec .venv/bin/python rew_script.py --show-target
    fi
    args=""
    for kv in "$@"; do
      args="$args --target $kv"
    done
    # shellcheck disable=SC2086  (ordsplittring är avsiktlig: en --target per KEY=VÄRDE)
    exec .venv/bin/python rew_script.py $args --yes ;;
  house-curve)
    shift
    case "$1" in
      --clear) exec .venv/bin/python rew_script.py --clear-house-curve --yes ;;
      "")      echo "Ange en sökväg: ./run.sh house-curve PATH  (eller --clear)" >&2; exit 1 ;;
      *)       exec .venv/bin/python rew_script.py --house-curve "$1" --yes ;;
    esac ;;
  *)
    exec .venv/bin/python rew_script.py "$@" ;;
esac
