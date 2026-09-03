"""
Webb-GUI för DSP8000-kedjan. Tre delar på en localhost-sida:

  1. REW-flödet steg för steg (mät -> steg 1 -> ladda förslag -> skriv -> mät igen)
  2. Enhetens EQ: välj en bas-dump (en avläsning eller en dumps/-referens) för
     att fylla redigeraren och rita kurvan, redigera, skriv till enheten direkt
     med EQ-Design:s SysEx 21 (grafisk EQ) + 22 (PEQ) - inget knapptryck, ingen
     dump-push (docs/midi.md 6.8). Master sätts till 0 dB. "Verifiera
     skrivningen" läser tillbaka dumpen och jämför.
  3. Kommandopanel: en knapp per ./run.sh-kommando, strömmad utskrift, svara
     på skriptens frågor i sidan

    python run_gui.py        # http://127.0.0.1:8765, öppnar webbläsaren
    ./run.sh gui

Ren stdlib. Lyssnar bara på localhost. Enhetsdelen kräver mido + interfacet;
kommandopanelen kör ./run.sh precis som terminalen.
"""
import fnmatch
import json
import os
import shlex
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import dsp8000
import syx_tools

HERE = Path(__file__).resolve().parent
PORT = 8765

COMMANDS = [
    ("REW → DSP8000 (steg 1)", [
        ("", "Kör steg 1", "mät i REW, Match target, spara ett EQ-förslag"),
        ("--no-peq", "Steg 1 utan PEQ", "bara 31-bands grafisk EQ"),
        ("refine", "Refine", "andra varvet: mätning gjord MED EQ:n på"),
        ("target", "Visa target-fält", "REW:s riktiga target-settings-fältnamn"),
        ("show", "Visa konfig", "config-HTML ur rew_eq_suggestion.json (annan fil: show --input FIL)"),
    ]),
    ("DSP8000 via MIDI (steg 2)", [
        ("ports", "MIDI-portar", "lista in/ut"),
        ("send --dry-run", "Send (dry-run)", "visa CC utan att skicka"),
        ("send --verify", "Send + verify", "skicka 31 band, läs tillbaka ur dumpen"),
        ("apply --dry-run", "Apply (dry-run)", "visa de två SysEx-meddelandena (21+22), skicka inte"),
        ("apply --verify", "Apply (GEQ+PEQ)", "skriv förslaget direkt (21+22, inget knapptryck), läs tillbaka"),
        ("readback", "Readback", "GEQ + PEQ ur enhetens dump, ändrar inget"),
        ("monitor", "Monitor", "lyssna 30 s på returvägen"),
        ("sysex", "SysEx-förfrågan", "hämta dumpen, spara som .syx"),
        ("probe", "Probe", "dumpa, CC på ett band, dumpa, diffa"),
        ("probe --manual", "Probe manuell", "pausa medan du ändrar EN sak på enheten"),
        ("roundtrip", "Roundtrip-test", "skriv känt GEQ+PEQ-mönster via dump, läs tillbaka, återställ"),
        ("push dumps/dsp8000_sysex_p16db.syx", "Push +16 dB-dump", "test av RCV MEMORY DUMP"),
        ("calibrate", "Kalibrera", "CC→dB mot displayen"),
    ]),
    ("Övrigt", [
        ("test", "Självtester", "kräver varken REW eller enheten"),
        ("help", "Hjälp", "./run.sh help"),
    ]),
]
SUBCOMMANDS = {"help", "ports", "monitor", "sysex", "readback", "grab", "push",
               "apply", "roundtrip", "probe", "calibrate", "send", "show", "test",
               "refine", "target", "house-curve", "gui"}

state = {"proc": None, "out": "", "cmd": "", "exit": None, "gen": 0}
lock = threading.Lock()
devlock = threading.Lock()      # ett MIDI-jobb åt gången


class DeviceError(Exception):
    """Fel som ska visas för användaren (ingen enhet, ingen dump, ingen JSON …)."""


# ---------------------------------------------------------------- kommandopanel
def start(cmdline):
    argv = shlex.split(cmdline)
    if argv and argv[0] == "gui":
        raise ValueError("gui i gui - nej")
    if argv and not (argv[0] in SUBCOMMANDS or argv[0].startswith("-")):
        raise ValueError(f"okänt kommando: {argv[0]} (se Hjälp)")
    with lock:
        if state["proc"] and state["proc"].poll() is None:
            raise RuntimeError("ett kommando kör redan - stoppa det först")
        proc = subprocess.Popen(
            ["./run.sh", *argv], cwd=HERE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0)
        state.update(proc=proc, out=f"$ ./run.sh {cmdline}\n", cmd=cmdline,
                     exit=None, gen=state["gen"] + 1)
    threading.Thread(target=_pump, args=(proc,), daemon=True).start()


def _pump(proc):
    fd = proc.stdout.fileno()
    while chunk := os.read(fd, 4096):        # chunkar, inte rader: prompter saknar \n
        with lock:
            state["out"] += chunk.decode("utf-8", "replace")
    code = proc.wait()
    with lock:
        state["exit"] = code
        state["out"] += f"\n[klar, exit {code}]\n"


def send_line(line):
    with lock:
        proc = state["proc"]
        if not proc or proc.poll() is not None:
            raise RuntimeError("inget kommando kör")
        proc.stdin.write((line + "\n").encode())
        proc.stdin.flush()
        state["out"] += line + "\n"          # eka, som i en terminal


def stop():
    with lock:
        proc = state["proc"]
        if proc and proc.poll() is None:
            proc.terminate()


# ---------------------------------------------------------------- enhet (MIDI)
def _midi():
    import rew_to_dsp8000 as d
    if d.mido is None:
        raise DeviceError("mido saknas: pip install mido python-rtmidi "
                          "(eller kör ./run.sh en gång).")
    return d


# --- Fil-modell ---------------------------------------------------------------
# Allt tidsstämplas och sorteras i history/ (paths.py), inte strött i repo-roten.
# Inget kommando använder en "senaste" eller hårdkodad fil implicit - GUI:t
# skickar alltid ett explicit filnamn och skrivningen patchar exakt den bas man
# valt.
#   history/reads/read-<ts>.syx           en avläsning av enhetens minne
#   history/writes/applied-<ts>.syx       en patchad dump = det som pushas
#   history/suggestions/suggestion-<ts>-<slug>.json   ett EQ-förslag
# Committade referensdumpar ligger kvar i dumps/ och går också att välja som bas.
TS_FMT = "%Y%m%d-%H%M%S"


def _root():
    return HERE.resolve()          # HERE kan sättas till en osymlänkad sökväg i test


def _dir(name):
    """history/<name>/ (skapad). name: reads | writes | suggestions."""
    d = _root() / "history" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rel(p):
    return str(Path(p).resolve().relative_to(_root()))


def _resolve(name, *globs):
    """name (relativt HERE) -> Path. Måste ligga i history/{reads,writes,
    suggestions}/, dumps/ eller HERE, och matcha ett av globs. Filnamnen kommer
    från webbläsaren."""
    if not name:
        raise DeviceError("Inget filnamn angivet.")
    root = _root()
    p = (root / name).resolve()
    ok_parents = {root, root / "dumps",
                  root / "history" / "reads", root / "history" / "writes",
                  root / "history" / "suggestions"}
    if p.parent not in ok_parents:
        raise DeviceError(f"oväntad sökväg: {name}")
    if not any(fnmatch.fnmatch(p.name, g) for g in globs):
        raise DeviceError(f"oväntat filnamn: {name}")
    if not p.is_file():
        raise DeviceError(f"{name} finns inte.")
    return p


def _load_dump(name, *globs):
    full = _resolve(name, *globs).read_bytes()
    if not (syx_tools.is_memory_dump(full) and len(full) == 12112):
        raise DeviceError(f"{name}: inte en giltig minnesdump "
                          "(F0 00 20 32 00 01 4F … , 12112 byte).")
    return full


def _dump_summary(full):
    g = syx_tools.decode_geq(full)
    npeq = sum(1 for r in syx_tools.decode_peq(full) if r["on"])
    gmax = max((abs(x) for x in g["L"] + g["R"]), default=0)
    return f"sub {full[6]:02x} {full[7]:02x} · GEQ ±{gmax:g} dB · PEQ {npeq}/6 på"


def _editor_view(full):
    """Full dump -> redigerarens fält (31 band L/R, master, L1/L2/L3-PEQ)."""
    g = syx_tools.decode_geq(full)
    pq = syx_tools.decode_peq(full)
    return {"bands": [f"{f:g}" for f in dsp8000.ISO_BANDS],
            "geq_L": g["L"], "geq_R": g["R"],
            "master_L": g["L_master"], "master_R": g["R_master"],
            "peq": [pq[i] for i in (0, 2, 4)]}      # L1 L2 L3 (R = samma vid mono)


def device_read():
    """Läs enhetens minne, spara som history/reads/read-<ts>.syx och returnera
    filnamnet + avkodad GEQ/PEQ. Ändrar inget. Enheten måste stå på EQ-skärmen."""
    d = _midi()
    with devlock:
        with d.open_output() as out, d.open_input() as inp:
            dump = d.grab_dump(out, inp)
    if dump is None:
        raise DeviceError("Ingen dump. Kolla EXCL SND/RCV ON, båda MIDI-kablarna i, "
                          "enheten på EQ-huvudskärmen.")
    full = b"\xf0" + dump + b"\xf7"
    p = _dir("reads") / f"read-{time.strftime(TS_FMT)}.syx"
    p.write_bytes(full)
    return {"name": _rel(p), "summary": _dump_summary(full), **_editor_view(full)}


def read_base(name):
    """Avkoda en vald bas-fil (history/reads/*.syx eller dumps/*.syx) för
    redigeraren - så "Basens EQ →" och kolumnerna funkar utan enheten."""
    full = _load_dump(name, "*.syx")
    return {"name": name, "summary": _dump_summary(full), **_editor_view(full)}


def bases():
    """Valbara bas-dumpar, nyaste först: dina avläsningar + committade referenser."""
    out = [{"name": _rel(p), "kind": "avläsning"}
           for p in sorted(_dir("reads").glob("*.syx"), reverse=True)]
    out += [{"name": _rel(p), "kind": "referens"}
            for p in sorted((_root() / "dumps").glob("*.syx"))]
    return {"bases": out}


def device_cc(idx, db, channel="both"):
    """Skicka ETT GEQ-band som Control Change direkt till enheten (samma väg som
    rew_to_dsp8000 send, fast ett band). För direktredigering - ingen dump, ingen
    verifiering, rör inte master/PEQ eller någon bas-fil."""
    d = _midi()
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        raise DeviceError("ogiltigt bandindex")
    if not 0 <= idx < 31:
        raise DeviceError(f"band {idx} utanför 0-30")
    chans = ["left", "right"] if channel == "both" else [channel]
    if any(c not in ("left", "right") for c in chans):
        raise DeviceError(f"okänd kanal: {channel}")
    freq = dsp8000.ISO_BANDS[idx]
    val = dsp8000.db_to_cc(float(db))
    with devlock:
        with d.open_output() as out:
            for c in chans:
                cc = (dsp8000.CC_GRAPHIC_LEFT if c == "left"
                      else dsp8000.CC_GRAPHIC_RIGHT)[freq]
                out.send(d.mido.Message("control_change", channel=0,
                                        control=cc, value=val))
                time.sleep(d.SEND_GAP_S)
    return {"band": f"{freq:g}", "cc_value": val, "db": dsp8000.cc_to_db(val)}


def _peqs6(peq3):
    """3 redigerbara filter -> 6 dump-poster L1 R1 L2 R2 L3 R3 (samma på L/R)."""
    out = []
    for i in range(dsp8000.PEQ_COUNT):
        r = peq3[i] if i < len(peq3) else None
        rec = None if not r or not r.get("on") else {
            "freq_hz": float(r["freq_hz"]), "bw_oct": float(r["bw_oct"]),
            "gain_db": float(r["gain_db"])}
        out += [rec, rec]
    return out


# Skrivvägen: EQ-Design:s SysEx 21 (grafisk EQ) + 22 (de sex PEQ-posterna) direkt
# till arbetsbufferten - inget knapptryck, ingen bas-dump (docs/midi.md 6.8).
# 21 skriver även master; den sätts till 0 dB. Det senast skrivna mellanlagras
# så "Verifiera skrivningen" kan läsa tillbaka och jämföra.
_written = {}


def device_write(geq, peq3):
    """Skriv redigerarens GEQ (31 dB, samma på L och R) + peq3 till enheten med
    21 + 22. Master 0 dB. Ingen återläsning - det är device_verify."""
    if len(geq) != 31:
        raise DeviceError(f"GEQ behöver 31 värden, fick {len(geq)}.")
    geq = [float(x) for x in geq]
    peqs = _peqs6(peq3)
    d = _midi()
    msgs = d.eq_messages(geq, peqs)
    with devlock:
        with d.open_output() as out:
            for payload in msgs:
                d._send_sysex(out, 0x00, 0x01, list(payload))
                time.sleep(0.1)
    _written.clear()
    _written.update(geq=geq, peqs=peqs)
    return {"sent": [len(m) for m in msgs], "master_db": 0.0,
            "peq_on": any(r is not None for r in peqs)}


def device_verify():
    """Hämta dumpen och jämför GEQ + PEQ + master mot det senast skrivna.
    {mismatches:[...], peq_on: bool}. Enheten måste stå på EQ-huvudskärmen."""
    if not _written:
        raise DeviceError("Inget att verifiera - skriv först.")
    d = _midi()
    with devlock:
        with d.open_output() as out, d.open_input() as inp:
            after = d.grab_dump(out, inp)
    if after is None:
        raise DeviceError("Ingen återläsning. Ställ enheten på EQ-huvudskärmen "
                          "(SysEx-förfrågan besvaras bara därifrån) och klicka "
                          "Verifiera skrivningen igen.")
    bad = d.verify_written(_written["geq"], _written["peqs"], (0.0, 0.0),
                           b"\xf0" + after + b"\xf7")
    return {"mismatches": bad, "peq_on": any(r is not None for r in _written["peqs"])}


SUGGESTION_GLOBS = ("suggestion-*.json", "rew_eq_suggestion*.json")


def rew_measurements():
    """[{id,title,date}] från REW:s API. Kräver REW igång med API:t på."""
    import rew_script
    try:
        ms = rew_script.list_measurements()
    except Exception as e:      # ConnectionError, timeout, HTTP-fel ...
        raise DeviceError(f"Når inte REW:s API ({type(e).__name__}). Starta REW och "
                          "slå på servern: Preferences → API → Start server.")
    return [{"id": m["id"], "title": m.get("title", "?"), "date": m.get("date", "")}
            for m in ms]


def suggestions():
    """Valbara EQ-förslag, nyaste först: history/suggestions/*.json (dina
    körningar) + committade rew_eq_suggestion*.json i repo-roten."""
    hist = sorted(_dir("suggestions").glob("*.json"), reverse=True)
    rootfs = sorted(_root().glob("rew_eq_suggestion*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    return {"files": [_rel(p) for p in hist] + [p.name for p in rootfs]}


def suggestion(name):
    """Ett valt EQ-förslag -> {geq:[31], peq:[≤3], name, generated_at} för
    redigeraren. Ingen MIDI. `name` är explicit (välj i Förslag-listan)."""
    import rew_to_dsp8000 as r
    p = _resolve(name, *SUGGESTION_GLOBS)
    data = json.loads(p.read_text(encoding="utf-8"))
    geq, peqs6 = r.suggestion_to_geq_peq(data)
    peq3 = [None if peqs6[i] is None else {**peqs6[i], "on": True} for i in (0, 2, 4)]
    return {"geq": geq, "peq": peq3, "name": name,
            "generated_at": data.get("generated_at", "")}


# ---------------------------------------------------------------- HTTP
HTML = r"""<!doctype html><meta charset="utf-8"><title>DSP8000 kontrollpanel</title>
<style>
 :root{color-scheme:light dark}
 body{font:14px system-ui,sans-serif;margin:1rem;max-width:70rem}
 h1{font-size:1.15rem} h2{font-size:.95rem;margin:1.4rem 0 .4rem}
 h3{font-size:.8rem;margin:1rem 0 .3rem;opacity:.7;text-transform:uppercase;letter-spacing:.04em}
 button,select{font:inherit;padding:.3rem .5rem;cursor:pointer}
 .grp{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
 ol.steps{margin:.3rem 0;padding-left:1.3rem} ol.steps li{margin:.35rem 0}
 .bar{display:flex;gap:.4rem;margin:.6rem 0;flex-wrap:wrap;align-items:center}
 #status2{opacity:.8} .err{color:#d44} .ok{color:#2a8}
 table{border-collapse:collapse} th,td{padding:.15rem .4rem;text-align:right}
 th{font-weight:600;opacity:.7} td.hz{text-align:left;white-space:nowrap}
 input[type=number]{font:inherit;width:4.2rem;padding:.1rem .2rem;text-align:right}
 label.tgl{display:flex;gap:.35rem;align-items:center;cursor:pointer}
 label.tgl.on{color:#c80;font-weight:600}
 .editrow{display:flex;gap:2rem;flex-wrap:wrap;align-items:flex-start}
 /* GEQ som lodräta reglage, likt dsp8000_gui.html */
 .strip{display:flex;gap:1px;overflow-x:auto;padding-bottom:.4rem;max-width:100%}
 .band{display:flex;flex-direction:column;align-items:center;min-width:20px}
 .band .dbv{font-size:10px;font-variant-numeric:tabular-nums;min-height:1.1em}
 .band input[type=range]{writing-mode:vertical-lr;direction:rtl;width:15px;height:150px;margin:2px 0}
 .band .bhz{font-size:9px;opacity:.65;writing-mode:vertical-rl;height:3.4em;white-space:nowrap}
 .band.dirty .dbv{color:#c80;font-weight:600}
 #curve{width:100%;max-width:640px;aspect-ratio:600/220;height:auto;background:#8881;border-radius:4px;display:block;margin:.4rem 0}
 #curve .grid{stroke:#8883} #curve .grid0{stroke:#8887}
 #curve .gl{fill:#888;font-size:9px}
 #curve path{fill:none;stroke-linejoin:round}
 #curve .c-sum{stroke:#e35d8a;stroke-width:2.3}
 #curve .c-geq{stroke:#2a9d6b;stroke-width:1.4}
 #curve .c-peq{stroke:#4c86e6;stroke-width:1.4}
 #curve .c-bas{stroke:#8a8a8a;stroke-width:1.2;stroke-dasharray:3 3}
 .leg span{margin-right:1rem;white-space:nowrap} .leg b{font-weight:400}
 #peq input[type=number]{width:5rem}
 form.runf{display:flex;gap:.4rem;margin:.5rem 0} form.runf input[type=text]{flex:1;font:inherit;padding:.3rem}
 #status{opacity:.7;margin:-.2rem 0 .3rem} .run{color:#c80}
 pre{background:#8881;padding:.6rem;min-height:9rem;max-height:42vh;overflow:auto;white-space:pre-wrap}
 details{margin-top:1.2rem} summary{cursor:pointer;font-weight:600}
 .muted{opacity:.6;font-size:.85em}
</style>
<h1>DSP8000 – kontrollpanel</h1>

<h2>Skriv EQ till enheten (GEQ + PEQ via minnesdumpen)</h2>

<div class="bar">
 <b>1. Bas-dump:</b>
 <select id="baseSel"><option value="">… läser history/ …</option></select>
 <button id="read">Läs av enheten (ny bas)</button>
 <span id="baseInfo" class="muted"></span>
</div>
<div class="bar">
 <b>2. Fyll redigeraren:</b>
 <select id="sugSel"><option value="">…</option></select>
 <button id="loadSug">Ladda valt förslag</button>
 <button id="fromCur">Basens EQ →</button>
 <button id="flat">Nolla</button>
</div>
<div class="bar">
 <b>3.</b>
 <button id="write"><b>Skriv till enheten</b></button>
 <button id="verify">Verifiera skrivningen</button>
 <span id="status2">&nbsp;</span>
</div>
<p class="muted">Skrivningen skickar redigerarens GEQ + PEQ <b>direkt</b> till enhetens
 arbetsbuffert (SysEx <code>21</code> + <code>22</code>, docs/midi.md 6.8) – inget
 knapptryck, ingen bas-dump. <b>Master sätts till 0 dB.</b> FB-D ska stå på OFF på alla
 sex filtren. "Verifiera skrivningen" läser tillbaka dumpen och jämför. Basen i steg 1
 används bara för att fylla redigeraren och rita den streckade kurvan.</p>
<p class="muted" id="editorFrom">Redigeraren: tom</p>

<div class="bar">
 <label class="tgl" id="directLbl"><input type="checkbox" id="direct">
  <b>Direktredigering</b> – GEQ-reglaget skickar CC direkt till enheten (ingen dump)</label>
 <select id="directCh" disabled title="vilken kanal CC går till">
  <option value="both">L + R</option><option value="left">bara L</option><option value="right">bara R</option>
 </select>
</div>
<p class="muted" id="directNote" hidden>CC-läge: reglagen ändrar enheten direkt men
 <b>inte</b> bas-dumpen. Master, PEQ och verifiering är kvar på dump-vägen. Läs av
 enheten igen innan du gör en dump-skrivning ovanpå.</p>

<svg id="curve" viewBox="0 0 600 220"></svg>
<div class="muted leg">
 <span style="color:#e35d8a">■ <b>Summa (GEQ+PEQ)</b></span>
 <span style="color:#2a9d6b">■ <b>GEQ</b></span>
 <span style="color:#4c86e6">■ <b>PEQ</b></span>
 <span style="color:#8a8a8a">▪ <b>Vald bas</b></span>
</div>

<div class="editrow">
 <div>
  <h3>Grafisk EQ (31 band)</h3>
  <div class="strip" id="strip"></div>
  <div class="muted" id="master">&nbsp;</div>
 </div>
 <div>
  <h3>Parametriska filter (max 3)</h3>
  <table id="peq"><thead><tr>
    <th>#</th><th>På</th><th>Frekvens (Hz)</th><th>Bandbredd (okt)</th><th>Gain (dB)</th><th>Bas</th>
   </tr></thead><tbody id="peqRows"></tbody></table>
  <p class="muted">Skrivs till <b>både L och R</b> (mätningen är L+R). Dumpen sätter
   filtrets frekvens/bandbredd/gain, men <b>inte</b> FB-D-läget (ON/OFF/SGL). Sätt
   <b>OFF</b> på alla sex filtren på enhetens PEQ-sida <b>före</b> skrivningen – med ON
   flyttar feedback destroyern filtren själv.</p>
 </div>
</div>

<details>
 <summary>Skapa / uppdatera ett EQ-förslag från en REW-mätning</summary>
 <ol class="steps">
  <li>Starta REW med API:t på (Preferences → API → <i>Start server</i>) och kör en
      sweep med EQ:n i <b>bypass</b> (IN/OUT-LED släckt).</li>
  <li>Välj mätning:
      <select id="measSel"><option value="">… läser från REW …</option></select>
      <button id="measRefresh" title="hämta listan från REW igen">↻</button>
      <button id="runStep1">Kör steg 1</button>.
      Kör Match target och skriver <code>history/suggestions/suggestion-&lt;tid&gt;-&lt;mätning&gt;.json</code>
      (ingen vald mätning = välj i kommandopanelen).</li>
  <li>Utskrift och ev. frågor hamnar i <b>Kommandopanelen</b> nedan – den öppnas
      automatiskt, svara i rutan där. När den är klar:
      <button id="loadSug3">Ladda in senaste förslaget</button>.</li>
  <li>Andra varvet (ny mätning gjord <b>med</b> EQ:n aktiv): välj den nya mätningen
      och det förslag du vill förfina, <button id="runRefine">Refine → nytt förslag</button>,
      ladda in, skriv igen.</li>
 </ol>
</details>

<details id="cmdpanel">
 <summary>Kommandopanel (./run.sh)</summary>
 <div id="groups"></div>
 <form class="runf" id="runf"><input type="text" id="cmdline"
   placeholder="kommando + flaggor, t.ex. send --verify  eller  grab dumps/x.syx">
  <button>Kör</button><button type="button" id="stop">Stoppa</button></form>
 <div id="status">&nbsp;</div>
 <pre id="out"></pre>
 <form class="runf" id="inf"><input type="text" id="line"
   placeholder="svar på fråga (Enter = tom rad, t.ex. välj default)"><button>Skicka</button></form>
</details>

<script>
const COMMANDS = __COMMANDS__;
const BANDS = __BANDS__;
const $ = id => document.getElementById(id);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ---- redigerare: lodrätt GEQ-reglage per band + 3 PEQ-rader ----
const hzLbl = hz => (+hz >= 1000 ? (+hz / 1000) + 'k' : hz);
$('strip').innerHTML = BANDS.map((hz, i) =>
  `<div class="band" id="bd${i}"><span class="dbv" id="dv${i}">0.0</span>`
  + `<input type="range" id="eg${i}" min="-16" max="16" step="0.5" value="0" title="${hz} Hz">`
  + `<span class="bhz">${hzLbl(hz)}</span></div>`).join('');
$('peqRows').innerHTML = [0,1,2].map(i =>
  `<tr><td>${i+1}</td>`
  + `<td><input type="checkbox" id="pon${i}"></td>`
  + `<td><input type="number" id="pf${i}" min="20" max="20000" step="1" value="60"></td>`
  + `<td><input type="number" id="pb${i}" min="0.05" max="2" step="0.05" value="0.33"></td>`
  + `<td><input type="number" id="pg${i}" min="-48" max="16" step="0.5" value="0"></td>`
  + `<td id="pnow${i}" class="muted">–</td></tr>`).join('');

let ccT = {};
function onGeqInput(i) {
  const v = +$('eg'+i).value;
  $('dv'+i).textContent = v.toFixed(1);
  $('bd'+i).classList.toggle('dirty', Math.abs(v) > 0.01);
  drawCurve();
  if (!$('direct').checked) return;
  clearTimeout(ccT[i]);
  ccT[i] = setTimeout(async () => {
    try { const d = await jpost('/device/cc', {idx: i, db: v, channel: $('directCh').value});
      say(`CC → ${d.band} Hz ${(+d.db).toFixed(2)} dB`, 'ok'); }
    catch (e) { say(e, 'err'); }
  }, 70);
}
BANDS.forEach((_, i) => $('eg'+i).addEventListener('input', () => onGeqInput(i)));
[0,1,2].forEach(i => ['pon','pf','pb','pg'].forEach(k =>
  $(k+i).addEventListener('input', drawCurve)));

function setEditorGeq(arr) {
  BANDS.forEach((_, i) => {
    const v = clamp(+(arr[i] || 0), -16, 16);
    $('eg'+i).value = v; $('dv'+i).textContent = v.toFixed(1);
    $('bd'+i).classList.toggle('dirty', Math.abs(v) > 0.01);
  });
  drawCurve();
}
function getEditorGeq() { return BANDS.map((_, i) => +$('eg'+i).value); }
function setEditorPeq(peq) {
  [0,1,2].forEach(i => {
    const r = (peq || [])[i];
    $('pon'+i).checked = !!(r && r.on);
    if (r) { $('pf'+i).value = Math.round(r.freq_hz); $('pb'+i).value = (+r.bw_oct).toFixed(2); $('pg'+i).value = (+r.gain_db).toFixed(1); }
  });
  drawCurve();
}
function getEditorPeq() {
  return [0,1,2].map(i => ({on: $('pon'+i).checked, freq_hz: +$('pf'+i).value,
    bw_oct: +$('pb'+i).value, gain_db: +$('pg'+i).value}));
}
const peqStr = r => r.on ? `${Math.round(r.freq_hz)} Hz ${(+r.bw_oct).toFixed(2)} okt ${(+r.gain_db).toFixed(1)} dB` : 'OFF';

// ---- EQ-kurva: RBJ peaking-biquad per band/filter, kaskad, magnitud i dB ----
const FS = 48000;
const FREQS = Array.from({length: 168}, (_, i) => 20 * Math.pow(1000, i / 167));
function peakBiquad(f0, Q, gainDb) {
  const A = Math.pow(10, gainDb / 40), w0 = 2 * Math.PI * f0 / FS;
  const cw = Math.cos(w0), alpha = Math.sin(w0) / (2 * Q);
  const a0 = 1 + alpha / A;
  return [(1 + alpha * A) / a0, -2 * cw / a0, (1 - alpha * A) / a0,
          -2 * cw / a0, (1 - alpha / A) / a0];
}
function magDb(cascade, f) {
  const w = 2 * Math.PI * f / FS;
  const c1 = Math.cos(-w), s1 = Math.sin(-w), c2 = Math.cos(-2 * w), s2 = Math.sin(-2 * w);
  let db = 0;
  for (const [b0, b1, b2, a1, a2] of cascade) {
    const nr = b0 + b1 * c1 + b2 * c2, ni = b1 * s1 + b2 * s2;
    const dr = 1 + a1 * c1 + a2 * c2, di = a1 * s1 + a2 * s2;
    db += 10 * Math.log10((nr * nr + ni * ni) / (dr * dr + di * di));
  }
  return db;
}
function geqCascade(g) {
  const c = [];
  BANDS.forEach((hz, i) => { if (Math.abs(g[i]) > 0.01) c.push(peakBiquad(+hz, 4.32, g[i])); });
  return c;
}
function peqCascade(ps) {
  const c = [];
  (ps || []).forEach(p => {
    if (!p.on || Math.abs(p.gain_db) < 0.01 || !(p.bw_oct > 0)) return;
    const r = Math.pow(2, p.bw_oct);
    c.push(peakBiquad(p.freq_hz, Math.sqrt(r) / (r - 1), p.gain_db));
  });
  return c;
}
const CW = 600, CH = 220, PL = 32, PR = 6, PT = 10, PB = 20;
const fx = f => PL + Math.log10(f / 20) / 3 * (CW - PL - PR);
function drawCurve() {
  const gc = geqCascade(getEditorGeq()), pc = peqCascade(getEditorPeq());
  const S = {
    bas: curBase ? geqCascade(curBase.geq_L).concat(peqCascade(curBase.peq)) : null,
    geq: gc, peq: pc, sum: gc.concat(pc),
  };
  const resp = {};
  let lo = -6, hi = 6;
  for (const k in S) if (S[k]) {
    resp[k] = FREQS.map(f => magDb(S[k], f));
    for (const v of resp[k]) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  }
  lo = Math.max(-30, Math.floor(lo / 3) * 3); hi = Math.min(30, Math.ceil(hi / 3) * 3);
  const fy = db => PT + (hi - db) / (hi - lo) * (CH - PT - PB);
  const d = a => 'M' + a.map((v, i) => fx(FREQS[i]).toFixed(1) + ' ' + fy(v).toFixed(1)).join(' L');
  let s = '';
  for (const f of [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
    s += `<line class="grid" x1="${fx(f).toFixed(1)}" y1="${PT}" x2="${fx(f).toFixed(1)}" y2="${CH - PB}"/>`
       + `<text class="gl" x="${fx(f).toFixed(1)}" y="${CH - 6}" text-anchor="middle">${f >= 1000 ? f / 1000 + 'k' : f}</text>`;
  for (let db = Math.ceil(lo / 6) * 6; db <= hi; db += 6)
    s += `<line class="${db === 0 ? 'grid0' : 'grid'}" x1="${PL}" y1="${fy(db).toFixed(1)}" x2="${CW - PR}" y2="${fy(db).toFixed(1)}"/>`
       + `<text class="gl" x="2" y="${(fy(db) + 3).toFixed(1)}">${db > 0 ? '+' + db : db}</text>`;
  if (resp.bas) s += `<path class="c-bas" d="${d(resp.bas)}"/>`;
  s += `<path class="c-geq" d="${d(resp.geq)}"/><path class="c-peq" d="${d(resp.peq)}"/><path class="c-sum" d="${d(resp.sum)}"/>`;
  $('curve').innerHTML = s;
}

async function jget(p) { const r = await fetch(p); const j = await r.json(); if (j.error) throw j.error; return j; }
async function jpost(p, b) { const r = await fetch(p,{method:'POST',body:JSON.stringify(b||{})}); const j = await r.json(); if (j.error) throw j.error; return j; }
function say(msg, cls) { $('status2').textContent = msg; $('status2').className = cls || ''; }

let curBase = null;                 // avkodad vald bas-dump {name, geq_L, ...}
function setEditorFrom(s) { $('editorFrom').textContent = 'Redigeraren: ' + s; }
function showBase(d) {
  [0,1,2].forEach(i => $('pnow'+i).textContent = d ? peqStr(d.peq[i]) : '–');
  $('master').textContent = d ? `Bas-master L ${(d.master_L/2).toFixed(2)} dB, R ${(d.master_R/2).toFixed(2)} dB (skrivs inte)` : ' ';
  $('baseInfo').textContent = d ? d.summary : '';
  drawCurve();
}

$('direct').onchange = () => {
  const on = $('direct').checked;
  $('directCh').disabled = !on;
  $('directLbl').classList.toggle('on', on);
  $('directNote').hidden = !on;
  say(on ? 'Direktredigering PÅ – GEQ-reglagen skickar CC direkt till enheten.'
        : 'Direktredigering av.', on ? 'ok' : '');
};

async function loadBaseList(select) {
  const sel = $('baseSel');
  try {
    const d = await jget('/bases');
    sel.innerHTML = d.bases.map(b => `<option value="${b.name}">${b.name}  (${b.kind})</option>`).join('')
      || '<option value="">(inga – "Läs av enheten")</option>';
    if (select) sel.value = select;
  } catch (e) { sel.innerHTML = `<option value="">${e}</option>`; }
  await useBase();
}
async function useBase() {
  const name = $('baseSel').value;
  curBase = null; showBase(null);
  if (!name) return;
  try { curBase = await jpost('/device/read-base', {name}); showBase(curBase); }
  catch (e) { $('baseInfo').textContent = e; }
}
$('baseSel').onchange = useBase;

const readDialog = 'Ställ enheten på EQ-huvudskärmen.\n\nSysEx-läsningen besvaras '
  + 'bara därifrån. Klicka OK när enheten står där.';
$('read').onclick = async () => {
  if (!confirm(readDialog)) return;
  say('läser av enheten …');
  try {
    const d = await jpost('/device/read');
    say('avläst → ' + d.name, 'ok');
    await loadBaseList(d.name);
  } catch (e) { say(e, 'err'); }
};
$('fromCur').onclick = () => {
  if (!curBase) return say('välj en bas-dump först', 'err');
  setEditorGeq(curBase.geq_L);
  setEditorPeq(curBase.peq.map(r => ({...r, on: r.on})));
  setEditorFrom('bas ' + curBase.name + ' (vänster kanal)');
  say('redigeraren fylld från basen', 'ok');
};
const slug = s => (s||'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'') || 'matning';
function nowTs() {
  const d = new Date(), p = n => String(n).padStart(2,'0');
  return `${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

async function loadMeasList() {
  const sel = $('measSel');
  try {
    const d = await jget('/measurements');
    sel.innerHTML = d.map(m =>
      `<option value="${m.id}|${slug(m.title)}">${m.id}: ${m.title}${m.date ? ' ('+m.date+')' : ''}</option>`
    ).join('') || '<option value="">(inga mätningar i REW)</option>';
  } catch (e) { sel.innerHTML = `<option value="">${e}</option>`; }
}
async function loadSugList(select) {
  const sel = $('sugSel');
  try {
    const d = await jget('/suggestions');
    sel.innerHTML = d.files.map(f => `<option>${f}</option>`).join('')
      || '<option value="">(inga – kör steg 1)</option>';
    if (select) sel.value = select; else if (d.files.length) sel.selectedIndex = 0;
  } catch (e) { sel.innerHTML = `<option value="">${e}</option>`; }
}
async function loadSug() {
  const f = $('sugSel').value;
  if (!f) return say('inget förslag valt – kör steg 1 först', 'err');
  say('läser ' + f + ' …');
  try {
    const d = await jget('/suggestion?file=' + encodeURIComponent(f));
    setEditorGeq(d.geq); setEditorPeq(d.peq);
    setEditorFrom('förslag ' + d.name
      + (d.generated_at ? ' (' + d.generated_at.slice(0,16).replace('T',' ') + ')' : ''));
    say(f + ' inläst i redigeraren', 'ok');
  } catch (e) { say(e, 'err'); }
}
$('loadSug').onclick = loadSug;
$('loadSug3').onclick = async () => { await loadSugList(); await loadSug(); };
$('measRefresh').onclick = loadMeasList;
$('flat').onclick = () => { setEditorGeq(BANDS.map(() => 0)); setEditorPeq([null,null,null]); setEditorFrom('nollad'); say('redigeringen nollad'); };
$('runStep1').onclick = () => {
  const v = $('measSel').value;
  if (!v) { $('cmdline').value = ''; return runCmd(); }
  const [id, sl] = v.split('|');
  $('cmdline').value = `--measurement ${id} --output history/suggestions/suggestion-${nowTs()}-${sl}.json --yes`;
  runCmd();
};
$('runRefine').onclick = () => {
  const v = $('measSel').value, f = $('sugSel').value;
  if (!v || !f) return alert('välj både en (ny) mätning och det förslag du vill förfina');
  const sl = v.split('|')[1] || 'matning';
  $('cmdline').value = `refine --refine-from ${f} --measurement ${v.split('|')[0]}`
    + ` --output history/suggestions/suggestion-${nowTs()}-${sl}.json`;
  runCmd();
};
loadMeasList(); loadSugList(); loadBaseList();

async function writeDevice() {
  if (!confirm('Skriv till enheten.\n\nRedigerarens GEQ + PEQ skickas direkt (SysEx 21 + 22), '
      + 'inget knapptryck behövs.\n\nMaster sätts till 0 dB på båda kanalerna.\n'
      + 'FB-D OFF på alla sex PEQ-filter?')) return;
  say('skickar 21 + 22 …');
  try {
    const r = await jpost('/device/write', {geq: getEditorGeq(), peq: getEditorPeq()});
    say('skickat (' + r.sent.join(' + ') + ' byte), master 0 dB. '
      + (r.peq_on ? 'FB-D-läget ligger inte i kommandot – står det på ON flyttar destroyern filtren. ' : '')
      + 'Kolla displayen, eller klicka "Verifiera skrivningen" (läser tillbaka, ~5 s).', 'ok');
  } catch (e) { say(e, 'err'); }
}

async function verifyWrite() {
  say('läser tillbaka och jämför … (~5 s)');
  try {
    const d = await jpost('/device/verify');
    if (!d.mismatches.length) {
      say('OK: enheten har exakt det som skrevs (GEQ + PEQ + master 0 dB). '
        + 'Verifiera akustiskt med en REW-sweep. "Läs av enheten" ger en ny bas att utgå från.', 'ok');
    } else {
      say(d.mismatches.length + ' avvikelser: ' + d.mismatches.slice(0,3).join(' · ')
        + ' – står enheten på EQ-huvudskärmen och FB-D OFF? Skriv igen.', 'err');
    }
  } catch (e) { say(e, 'err'); }
}
$('write').onclick = writeDevice;
$('verify').onclick = verifyWrite;

// ---- kommandopanel ----
for (const [title, items] of COMMANDS) {
  const h = document.createElement('h3'); h.textContent = title; $('groups').append(h);
  const g = document.createElement('div'); g.className = 'grp'; $('groups').append(g);
  for (const [cmd, label, desc] of items) {
    const b = document.createElement('button'); b.textContent = label; b.title = desc || cmd;
    b.onclick = () => { $('cmdline').value = cmd; runCmd(); }; g.append(b);
  }
}

async function postCmd(path, body) {
  const r = await fetch(path, {method:'POST', body: JSON.stringify(body)});
  const j = await r.json(); if (j.error) { $('status').textContent = 'fel: ' + j.error; $('status').className = 'err'; } return j;
}
const runCmd = () => { $('cmdpanel').open = true; return postCmd('/run', {cmdline: $('cmdline').value}); };
$('runf').onsubmit = e => { e.preventDefault(); runCmd(); };
$('stop').onclick = () => postCmd('/stop', {});
$('inf').onsubmit = e => { e.preventDefault(); postCmd('/stdin', {line: $('line').value}); $('line').value = ''; };
let seen = 0, gen = 0, errGen = -1;
setInterval(async () => {
  const j = await (await fetch('/out?since=' + seen + '&gen=' + gen)).json();
  if (j.gen !== gen) { gen = j.gen; seen = 0; $('out').textContent = ''; }
  if (j.text) { $('out').textContent += j.text; seen = j.len; $('out').scrollTop = 1e9; }
  if ($('status').className === 'err' && j.gen === errGen) return;
  errGen = j.gen;
  $('status').textContent = j.cmd ? (j.running ? 'kör: ' + j.cmd : 'klar: ' + j.cmd + ' (exit ' + j.exit + ')') : '';
  $('status').className = j.running ? 'run' : '';
}, 300);
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            page = (HTML.replace("__COMMANDS__", json.dumps(COMMANDS, ensure_ascii=False))
                        .replace("__BANDS__", json.dumps([f"{f:g}" for f in dsp8000.ISO_BANDS])))
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/out":
            q = parse_qs(u.query)
            since = int(q.get("since", ["0"])[0])
            with lock:
                gen = state["gen"]
                if int(q.get("gen", ["0"])[0]) != gen:
                    since = 0
                proc = state["proc"]
                reply = {"text": state["out"][since:], "len": len(state["out"]),
                         "gen": gen, "cmd": state["cmd"], "exit": state["exit"],
                         "running": bool(proc) and proc.poll() is None}
            self._json(reply)
        elif u.path == "/suggestion":
            q = parse_qs(u.query)
            self._device(suggestion, (q.get("file") or [None])[0])
        elif u.path == "/suggestions":
            self._device(suggestions)
        elif u.path == "/bases":
            self._device(bases)
        elif u.path == "/measurements":
            self._device(rew_measurements)
        else:
            self._json({"error": "404"}, 404)

    def _device(self, fn, *a):
        try:
            self._json(fn(*a))
        except DeviceError as e:
            self._json({"error": str(e)}, 400)
        except SystemExit as e:                     # rew_to_dsp8000 kastar SystemExit vid t.ex. ingen MIDI-port
            self._json({"error": str(e) or "avbröt"}, 400)
        except Exception as e:                      # oväntat: visa i GUI:t, krascha inte servern
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path == "/run":
                start(body.get("cmdline", "")); self._json({"ok": True})
            elif self.path == "/stdin":
                send_line(body.get("line", "")); self._json({"ok": True})
            elif self.path == "/stop":
                stop(); self._json({"ok": True})
            elif self.path == "/device/read":
                self._device(device_read)
            elif self.path == "/device/read-base":
                self._device(read_base, body.get("name"))
            elif self.path == "/device/cc":
                self._device(device_cc, body.get("idx"), body.get("db"),
                             body.get("channel", "both"))
            elif self.path == "/device/verify":
                self._device(device_verify)
            elif self.path == "/device/write":
                self._device(device_write, body.get("geq", []), body.get("peq", []))
            else:
                self._json({"error": "404"}, 404)
        except (ValueError, RuntimeError) as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, *a):   # tyst
        pass


def serve(port=PORT, open_browser=True):
    for name in ("reads", "writes", "suggestions"):
        _dir(name)      # så steg 1 / kommandopanelen kan skriva dit direkt
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"DSP8000 kontrollpanel: http://127.0.0.1:{srv.server_port}/  (Ctrl-C avslutar)")
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{srv.server_port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop()
    return srv


if __name__ == "__main__":
    serve()
