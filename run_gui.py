"""
Webb-GUI för run.sh: en knapp per kommando, utskriften strömmas till sidan och
frågorna skripten ställer (input()) besvaras i ett textfält. Ren stdlib.

    python run_gui.py        # startar http://127.0.0.1:8765 och öppnar webbläsaren
    ./run.sh gui

Kör exakt det terminalen kör: ./run.sh <kommando> <flaggor>, med
PYTHONUNBUFFERED=1 så att prompter syns direkt. Ett kommando i taget.
Lyssnar bara på localhost.
"""
import json
import os
import shlex
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PORT = 8765

# Knapparna. Fritextfältet tar vad som helst run.sh tar (grab/push/house-curve, flaggor).
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
        ("readback", "Readback", "GEQ + PEQ ur enhetens dump, ändrar inget"),
        ("monitor", "Monitor", "lyssna 30 s på returvägen"),
        ("sysex", "SysEx-förfrågan", "hämta dumpen, spara som .syx"),
        ("probe", "Probe", "dumpa, CC på ett band, dumpa, diffa"),
        ("probe --manual", "Probe manuell", "pausa medan du ändrar EN sak på enheten"),
        ("push dumps/dsp8000_sysex_p16db.syx", "Push +16 dB-dump", "test av RCV MEMORY DUMP (docs/midi.md 4)"),
        ("calibrate", "Kalibrera", "CC→dB mot displayen"),
    ]),
    ("Övrigt", [
        ("test", "Självtester", "kräver varken REW eller enheten"),
        ("help", "Hjälp", "./run.sh help"),
    ]),
]
# run.sh: känt underkommando, annars flaggor rakt till rew_script.py
SUBCOMMANDS = {"help", "ports", "monitor", "sysex", "readback", "grab", "push",
               "probe", "calibrate", "send", "show", "test", "refine", "target",
               "house-curve", "gui"}

state = {"proc": None, "out": "", "cmd": "", "exit": None, "gen": 0}
lock = threading.Lock()


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


HTML = """<!doctype html><meta charset="utf-8"><title>DSP8000 körpanel</title>
<style>
 :root{color-scheme:light dark} body{font:14px system-ui,sans-serif;margin:1rem;max-width:64rem}
 h1{font-size:1.1rem} h2{font-size:.9rem;margin:1rem 0 .3rem;opacity:.7}
 .grp{display:flex;flex-wrap:wrap;gap:.4rem} button{font:inherit;padding:.3rem .6rem;cursor:pointer}
 form{display:flex;gap:.4rem;margin:.6rem 0} input{font:inherit;flex:1;padding:.3rem}
 pre{background:#8882;padding:.6rem;min-height:12rem;max-height:50vh;overflow:auto;white-space:pre-wrap}
 #status{opacity:.7;margin:-.3rem 0 .3rem} .run{color:#c80} .err{color:#d44;opacity:1}
</style>
<h1>DSP8000 – körpanel (<code>./run.sh</code>)</h1>
<div id="groups"></div>
<form id="runf"><input id="cmdline" placeholder="kommando + flaggor, t.ex. send --verify  eller  grab dumps/x.syx">
 <button>Kör</button><button type="button" id="stop">Stoppa</button></form>
<div id="status">&nbsp;</div>
<pre id="out"></pre>
<form id="inf"><input id="line" placeholder="svar på fråga (Enter = tom rad, t.ex. välj default)">
 <button>Skicka</button></form>
<script>
const COMMANDS = __COMMANDS__;
const $ = id => document.getElementById(id);
for (const [title, items] of COMMANDS) {
  const h = document.createElement('h2'); h.textContent = title; $('groups').append(h);
  const g = document.createElement('div'); g.className = 'grp'; $('groups').append(g);
  for (const [cmd, label, desc] of items) {
    const b = document.createElement('button'); b.textContent = label; b.title = desc || cmd;
    b.onclick = () => { $('cmdline').value = cmd; run(); }; g.append(b);
  }
}
async function post(path, body) {
  const r = await fetch(path, {method: 'POST', body: JSON.stringify(body)});
  const j = await r.json(); if (j.error) { $('status').textContent = 'fel: ' + j.error; $('status').className = 'err'; } return j;
}
const run = () => post('/run', {cmdline: $('cmdline').value});
$('runf').onsubmit = e => { e.preventDefault(); run(); };
$('stop').onclick = () => post('/stop', {});
$('inf').onsubmit = e => { e.preventDefault(); post('/stdin', {line: $('line').value}); $('line').value = ''; };
let seen = 0, gen = 0, errGen = 0;
setInterval(async () => {
  const j = await (await fetch('/out?since=' + seen + '&gen=' + gen)).json();
  if (j.gen !== gen) { gen = j.gen; seen = 0; $('out').textContent = ''; }
  if (j.text) { $('out').textContent += j.text; seen = j.len; $('out').scrollTop = 1e9; }
  if ($('status').className === 'err' && j.gen === errGen) return;   // låt felet stå tills nästa körning
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
            body = HTML.replace("__COMMANDS__", json.dumps(COMMANDS, ensure_ascii=False)).encode()
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
        else:
            self._json({"error": "404"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path == "/run":
                start(body.get("cmdline", ""))
            elif self.path == "/stdin":
                send_line(body.get("line", ""))
            elif self.path == "/stop":
                stop()
            else:
                return self._json({"error": "404"}, 404)
            self._json({"ok": True})
        except (ValueError, RuntimeError) as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, *a):   # tyst
        pass


def serve(port=PORT, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"DSP8000 körpanel: http://127.0.0.1:{srv.server_port}/  (Ctrl-C avslutar)")
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{srv.server_port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop()
    return srv


if __name__ == "__main__":
    serve()
