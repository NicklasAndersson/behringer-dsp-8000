"""
Webb-GUI för DSP8000-kedjan. Tre delar på en localhost-sida:

  1. REW-flödet steg för steg (mät -> steg 1 -> ladda förslag -> skriv -> mät igen)
  2. Enhetens EQ: läs av nuläget (GEQ + PEQ), redigera och skriv tillbaka via
     minnesdumpen (apply-vägen - GEQ *och* PEQ, inte bara CC)
  3. Kommandopanel: en knapp per ./run.sh-kommando, strömmad utskrift, svara
     på skriptens frågor i sidan

    python run_gui.py        # http://127.0.0.1:8765, öppnar webbläsaren
    ./run.sh gui

Ren stdlib. Lyssnar bara på localhost. Enhetsdelen kräver mido + interfacet;
kommandopanelen kör ./run.sh precis som terminalen.
"""
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
        ("", "Kör steg 1", "mät i REW, Match target, spara rew_eq_suggestion.json"),
        ("--no-peq", "Steg 1 utan PEQ", "bara 31-bands grafisk EQ"),
        ("refine", "Refine", "andra varvet: mätning gjord MED EQ:n på"),
        ("target", "Visa target-fält", "REW:s riktiga target-settings-fältnamn"),
        ("show", "Visa konfig", "generera + öppna dsp8000_config.html"),
    ]),
    ("DSP8000 via MIDI (steg 2)", [
        ("ports", "MIDI-portar", "lista in/ut"),
        ("send --dry-run", "Send (dry-run)", "visa CC utan att skicka"),
        ("send --verify", "Send + verify", "skicka 31 band, läs tillbaka ur dumpen"),
        ("apply --dry-run", "Apply (dry-run)", "patcha dumpen med GEQ+PEQ, pusha inte"),
        ("apply", "Apply (GEQ+PEQ)", "patcha enhetens dump och pusha tillbaka"),
        ("readback", "Readback", "GEQ + PEQ ur enhetens dump, ändrar inget"),
        ("monitor", "Monitor", "lyssna 30 s på returvägen"),
        ("sysex", "SysEx-förfrågan", "hämta dumpen, spara som .syx"),
        ("probe", "Probe", "dumpa, CC på ett band, dumpa, diffa"),
        ("probe --manual", "Probe manuell", "pausa medan du ändrar EN sak på enheten"),
        ("push dumps/dsp8000_sysex_p16db.syx", "Push +16 dB-dump", "test av RCV MEMORY DUMP"),
        ("calibrate", "Kalibrera", "CC→dB mot displayen"),
    ]),
    ("Övrigt", [
        ("test", "Självtester", "kräver varken REW eller enheten"),
        ("help", "Hjälp", "./run.sh help"),
    ]),
]
SUBCOMMANDS = {"help", "ports", "monitor", "sysex", "readback", "grab", "push",
               "apply", "probe", "calibrate", "send", "show", "test", "refine",
               "target", "house-curve", "gui"}

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


def device_read():
    """Hämta enhetens dump och returnera GEQ + PEQ som JSON. Ändrar inget."""
    d = _midi()
    with devlock:
        with d.open_output() as out, d.open_input() as inp:
            dump = d.grab_dump(out, inp)
    if dump is None:
        raise DeviceError("Ingen dump. Kolla EXCL SND/RCV ON, båda MIDI-kablarna i, "
                          "enheten på EQ-huvudskärmen.")
    full = b"\xf0" + dump + b"\xf7"
    g = syx_tools.decode_geq(full)
    pq = syx_tools.decode_peq(full)
    return {"bands": [f"{f:g}" for f in dsp8000.ISO_BANDS],
            "geq_L": g["L"], "geq_R": g["R"],
            "master_L": g["L_master"], "master_R": g["R_master"],
            "peq": [pq[i] for i in (0, 2, 4)],      # L1 L2 L3 (R = samma vid mono)
            "sub": f"{full[6]:02x} {full[7]:02x}"}


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


def device_write(geq, peq3):
    """Patcha en färsk dump med geq (31 dB, på L och R) + peq3 och pusha tillbaka,
    läs tillbaka och verifiera. Returnerar {applied, mismatches:[...]}"""
    if len(geq) != 31:
        raise DeviceError(f"GEQ behöver 31 värden, fick {len(geq)}.")
    geq = [float(x) for x in geq]
    peqs = _peqs6(peq3)
    d = _midi()
    with devlock:
        with d.open_output() as out, d.open_input() as inp:
            base = d.grab_dump(out, inp)
            if base is None:
                raise DeviceError("Ingen bas-dump. Kolla kablar/EXCL/skärm.")
            patched = syx_tools.patch_dump(b"\xf0" + base + b"\xf7", geq, geq, peqs)
            Path("dsp8000_applied.syx").write_bytes(patched)
            out.send(d.mido.Message("sysex", data=list(patched[1:-1])))
            time.sleep(6)                       # 12 kB @ 31250 baud ≈ 4 s + marginal
            after = d.grab_dump(out, inp)
    if after is None:
        raise DeviceError("Skrev, men ingen återläsning kom. Enheten kanske bytte "
                          "skärm - kolla displayen, kör Läs av igen.")
    got = b"\xf0" + after + b"\xf7"
    gw, gg = syx_tools.decode_geq(patched), syx_tools.decode_geq(got)
    pw, pg = syx_tools.decode_peq(patched), syx_tools.decode_peq(got)
    bad = []
    for ch in ("L", "R"):
        for f, x, y in zip(dsp8000.ISO_BANDS, gw[ch], gg[ch]):
            if abs(x - y) > 0.25:
                bad.append(f"GEQ {ch} {f:g} Hz: ville {x:+.2f}, fick {y:+.2f}")
    for lbl, x, y in zip(syx_tools.PEQ_LABELS, pw, pg):
        if x != y:
            bad.append(f"PEQ {lbl}: ville {syx_tools.peq_str(x)}, fick {syx_tools.peq_str(y)}")
    return {"applied": "dsp8000_applied.syx", "mismatches": bad}


def suggestion():
    """rew_eq_suggestion.json -> {geq:[31], peq:[≤3]} för redigeraren. Ingen MIDI."""
    import rew_to_dsp8000 as r
    if not r.JSON_FILE.exists():
        raise DeviceError(f"{r.JSON_FILE} saknas - kör steg 1 först.")
    data = json.loads(r.JSON_FILE.read_text(encoding="utf-8"))
    geq, peqs6 = r.suggestion_to_geq_peq(data)
    peq3 = []
    for i in (0, 2, 4):                          # L1 L2 L3
        rec = peqs6[i]
        peq3.append(None if rec is None else {**rec, "on": True})
    return {"geq": geq, "peq": peq3}


# ---------------------------------------------------------------- HTTP
HTML = r"""<!doctype html><meta charset="utf-8"><title>DSP8000 kontrollpanel</title>
<style>
 :root{color-scheme:light dark}
 body{font:14px system-ui,sans-serif;margin:1rem;max-width:70rem}
 h1{font-size:1.15rem} h2{font-size:.95rem;margin:1.4rem 0 .4rem}
 h3{font-size:.8rem;margin:1rem 0 .3rem;opacity:.7;text-transform:uppercase;letter-spacing:.04em}
 button{font:inherit;padding:.3rem .6rem;cursor:pointer}
 .grp{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
 ol.steps{margin:.3rem 0;padding-left:1.3rem} ol.steps li{margin:.35rem 0}
 .bar{display:flex;gap:.4rem;margin:.6rem 0;flex-wrap:wrap;align-items:center}
 #status2{opacity:.8} .err{color:#d44} .ok{color:#2a8}
 table{border-collapse:collapse} th,td{padding:.15rem .4rem;text-align:right}
 th{font-weight:600;opacity:.7} td.hz{text-align:left;white-space:nowrap}
 input[type=number]{font:inherit;width:4.2rem;padding:.1rem .2rem;text-align:right}
 .meter{position:relative;display:inline-block;width:130px;height:11px;background:#8882;vertical-align:middle}
 .meter::before{content:"";position:absolute;left:50%;top:0;bottom:0;border-left:1px solid #8886}
 .meter i{position:absolute;top:0;bottom:0}
 .meter .pos{left:50%;background:#3a8} .meter .neg{background:#c66}
 #geq{max-height:60vh;overflow:auto;display:inline-block;vertical-align:top}
 #peq input[type=number]{width:5rem}
 form.runf{display:flex;gap:.4rem;margin:.5rem 0} form.runf input[type=text]{flex:1;font:inherit;padding:.3rem}
 #status{opacity:.7;margin:-.2rem 0 .3rem} .run{color:#c80}
 pre{background:#8881;padding:.6rem;min-height:9rem;max-height:42vh;overflow:auto;white-space:pre-wrap}
 details{margin-top:1.2rem} summary{cursor:pointer;font-weight:600}
 .muted{opacity:.6;font-size:.85em}
</style>
<h1>DSP8000 – kontrollpanel</h1>

<h2>1. REW-flödet, steg för steg</h2>
<ol class="steps">
 <li>Mät i REW med EQ:n i <b>bypass</b> (IN/OUT-LED släckt).</li>
 <li><button data-run="">Kör steg 1</button> läser mätningen, kör Match target,
     sparar <code>rew_eq_suggestion.json</code>. <span class="muted">(REW måste köra med API:t på.)</span></li>
 <li><button id="loadSug">Ladda REW-förslag → redigeraren</button> nedan.</li>
 <li>Granska/justera och <button id="write2">Skriv till enheten</button> (GEQ + PEQ via dumpen).</li>
 <li>Mät igen med EQ:n <b>aktiv</b> (LED tänd), sedan <button data-run="refine">Refine</button> → skriv igen. Ett–två varv räcker.</li>
</ol>

<h2>2. Enhetens EQ</h2>
<div class="bar">
 <button id="read">Läs av enheten</button>
 <button id="loadSug2">Ladda REW-förslag</button>
 <button id="fromCur">Nuläge → redigera</button>
 <button id="write">Skriv till enheten (apply)</button>
 <button id="flat">Nolla redigering</button>
 <span id="status2">&nbsp;</span>
</div>

<div style="display:flex;gap:2rem;flex-wrap:wrap">
 <div>
  <h3>Grafisk EQ (31 band)</h3>
  <div id="geq"><table><thead><tr>
    <th class="hz">Band</th><th>Nu L</th><th>Nu R</th><th></th><th>Redigera</th>
   </tr></thead><tbody id="geqRows"></tbody></table></div>
  <div class="muted" id="master">&nbsp;</div>
 </div>
 <div>
  <h3>Parametriska filter (max 3)</h3>
  <table id="peq"><thead><tr>
    <th>#</th><th>På</th><th>Frekvens (Hz)</th><th>Bandbredd (okt)</th><th>Gain (dB)</th><th>Nu</th>
   </tr></thead><tbody id="peqRows"></tbody></table>
  <p class="muted">Skrivs till <b>både L och R</b> (mätningen är L+R). Enheten lagrar
   inte läget PAR/AUT/SGL i dumpen – sätt det för hand om du vill ha AUT/SGL.</p>
 </div>
</div>

<details>
 <summary>3. Kommandopanel (./run.sh)</summary>
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

// ---- redigerare: bygg 31 GEQ-rader + 3 PEQ-rader ----
$('geqRows').innerHTML = BANDS.map((hz, i) =>
  `<tr><td class="hz">${hz} Hz</td>`
  + `<td id="nl${i}" class="muted">–</td><td id="nr${i}" class="muted">–</td>`
  + `<td><span class="meter"><i id="mb${i}"></i></span></td>`
  + `<td><input type="number" id="eg${i}" min="-16" max="16" step="0.5" value="0"></td></tr>`).join('');
$('peqRows').innerHTML = [0,1,2].map(i =>
  `<tr><td>${i+1}</td>`
  + `<td><input type="checkbox" id="pon${i}"></td>`
  + `<td><input type="number" id="pf${i}" min="20" max="20000" step="1" value="60"></td>`
  + `<td><input type="number" id="pb${i}" min="0.05" max="2" step="0.05" value="0.33"></td>`
  + `<td><input type="number" id="pg${i}" min="-48" max="16" step="0.5" value="0"></td>`
  + `<td id="pnow${i}" class="muted">–</td></tr>`).join('');

function drawMeter(i, db) {
  const f = clamp(db / 16, -1, 1), el = $('mb'+i);
  if (f >= 0) { el.className = 'pos'; el.style.left = '50%'; el.style.width = (f*50)+'%'; }
  else { el.className = 'neg'; el.style.width = (-f*50)+'%'; el.style.left = (50+f*50)+'%'; }
}
BANDS.forEach((_, i) => { $('eg'+i).addEventListener('input', () => drawMeter(i, +$('eg'+i).value)); drawMeter(i, 0); });

function setEditorGeq(arr) { BANDS.forEach((_, i) => { const v = +(arr[i]||0); $('eg'+i).value = v; drawMeter(i, v); }); }
function getEditorGeq() { return BANDS.map((_, i) => +$('eg'+i).value); }
function setEditorPeq(peq) {
  [0,1,2].forEach(i => {
    const r = (peq||[])[i];
    $('pon'+i).checked = !!(r && r.on);
    if (r) { $('pf'+i).value = Math.round(r.freq_hz); $('pb'+i).value = (+r.bw_oct).toFixed(2); $('pg'+i).value = (+r.gain_db).toFixed(1); }
  });
}
function getEditorPeq() {
  return [0,1,2].map(i => ({on: $('pon'+i).checked, freq_hz: +$('pf'+i).value,
    bw_oct: +$('pb'+i).value, gain_db: +$('pg'+i).value}));
}
const peqStr = r => r.on ? `${Math.round(r.freq_hz)} Hz ${(+r.bw_oct).toFixed(2)} okt ${(+r.gain_db).toFixed(1)} dB` : 'OFF';

async function jget(p) { const r = await fetch(p); const j = await r.json(); if (j.error) throw j.error; return j; }
async function jpost(p, b) { const r = await fetch(p,{method:'POST',body:JSON.stringify(b||{})}); const j = await r.json(); if (j.error) throw j.error; return j; }
function say(msg, cls) { $('status2').textContent = msg; $('status2').className = cls || ''; }

let lastRead = null;
$('read').onclick = async () => {
  say('läser av enheten …'); try {
    const d = await jpost('/device/read'); lastRead = d;
    BANDS.forEach((_, i) => {
      $('nl'+i).textContent = d.geq_L[i].toFixed(1); $('nr'+i).textContent = d.geq_R[i].toFixed(1);
    });
    [0,1,2].forEach(i => $('pnow'+i).textContent = peqStr(d.peq[i]));
    $('master').textContent = `Master L ${d.master_L}, R ${d.master_R} (rått) · dump ${d.sub}`;
    say('avläst – tryck "Nuläge → redigera" för att utgå från detta', 'ok');
  } catch (e) { say(e, 'err'); }
};
$('fromCur').onclick = () => {
  if (!lastRead) return say('läs av enheten först', 'err');
  setEditorGeq(lastRead.geq_L);
  setEditorPeq(lastRead.peq.map(r => ({...r, on: r.on})));
  say('redigeraren fylld från nuläget (vänster kanal)', 'ok');
};
async function loadSug() {
  say('läser rew_eq_suggestion.json …'); try {
    const d = await jget('/suggestion'); setEditorGeq(d.geq); setEditorPeq(d.peq);
    say('REW-förslaget inläst i redigeraren', 'ok');
  } catch (e) { say(e, 'err'); }
}
$('loadSug').onclick = loadSug; $('loadSug2').onclick = loadSug;
$('flat').onclick = () => { setEditorGeq(BANDS.map(() => 0)); setEditorPeq([null,null,null]); say('redigeringen nollad'); };

async function writeDevice() {
  if (!confirm('Skriva GEQ + PEQ till enheten? Detta skickar en hel minnesdump.')) return;
  say('skriver och läser tillbaka … (~15 s)'); try {
    const d = await jpost('/device/write', {geq: getEditorGeq(), peq: getEditorPeq()});
    if (!d.mismatches.length) say('OK: enheten har exakt det som skrevs. Verifiera akustiskt med en REW-sweep.', 'ok');
    else say(d.mismatches.length + ' avvikelser: ' + d.mismatches.slice(0,3).join(' · '), 'err');
    $('read').click();
  } catch (e) { say(e, 'err'); }
}
$('write').onclick = writeDevice; $('write2').onclick = writeDevice;

// ---- kommandopanel ----
for (const [title, items] of COMMANDS) {
  const h = document.createElement('h3'); h.textContent = title; $('groups').append(h);
  const g = document.createElement('div'); g.className = 'grp'; $('groups').append(g);
  for (const [cmd, label, desc] of items) {
    const b = document.createElement('button'); b.textContent = label; b.title = desc || cmd;
    b.onclick = () => { $('cmdline').value = cmd; runCmd(); }; g.append(b);
  }
}
document.querySelectorAll('button[data-run]').forEach(b =>
  b.onclick = () => { $('cmdline').value = b.getAttribute('data-run'); runCmd(); });

async function postCmd(path, body) {
  const r = await fetch(path, {method:'POST', body: JSON.stringify(body)});
  const j = await r.json(); if (j.error) { $('status').textContent = 'fel: ' + j.error; $('status').className = 'err'; } return j;
}
const runCmd = () => postCmd('/run', {cmdline: $('cmdline').value});
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
            self._device(suggestion)
        else:
            self._json({"error": "404"}, 404)

    def _device(self, fn, *a):
        try:
            self._json(fn(*a))
        except DeviceError as e:
            self._json({"error": str(e)}, 400)
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
            elif self.path == "/device/write":
                self._device(device_write, body.get("geq", []), body.get("peq", []))
            else:
                self._json({"error": "404"}, 404)
        except (ValueError, RuntimeError) as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, *a):   # tyst
        pass


def serve(port=PORT, open_browser=True):
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
