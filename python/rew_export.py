"""
REW -> förslagsfil för kontrollpanelen (../dsp8000_gui.html).

Ett litet localhost-GUI: välj mätning i listan, se allt REW vet om den plus
kurvorna (uppmätt, målkurva och den preliminära 31-bandskorrigeringen), välj hur
många parametriska filter enheten ska använda (0-3, banden räknas om mot valet),
och spara ett EQ-förslag - via en filväljare - i exakt det format panelen
importerar.

    python rew_export.py        # http://127.0.0.1:8767, öppnar webbläsaren
    ./run.sh export

Räknandet är rew_script.py:s - det här är bara ett fönster mot det. Att välja
en mätning ändrar ingenting i REW; först "Bygg & spara" kör Match target (och
skriver då filter i REW, precis som ./run.sh gör).

Kräver REW med API:t på (Preferences -> API -> Start server) och `requests`.
Andra varvet: mät om MED EQ:n på, exportera den mätningen rakt av och
importera den i panelen med läget "Merga" - det är samma räkning som
rew_script.py --refine, och andelen i panelen är --refine-damping.
"""
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import dsp8000
import paths
import rew_script

PORT = 8767
PLOT_PPO = 12          # punkter per oktav i grafen (räkningen använder rew_scripts 48)

# ponytail: senaste uträkningen ligger i minnet mellan "Räkna om" och "Spara".
# En användare, en localhost-flik - blir det fler får den flytta in i sidan.
LAST = {}


def slug(text):
    """Mätningstitel -> filnamnsdel, samma stil som kontrollpanelens namn."""
    return re.sub(r"[^a-z0-9]+", "_", (text or "matning").lower()).strip("_")[:40] or "matning"


def default_name(m):
    return f"suggestion-{paths.ts()}-{slug(m.get('title'))}.json"


def measurements():
    """Alla mätningar i REW, nyast sist (samma ordning som listan i REW)."""
    return rew_script.list_measurements()


def _plot(measurement_id, endpoint):
    """En kurva för grafen: [[hz, dB]], grovt samplad (PLOT_PPO)."""
    q = f"?ppo={PLOT_PPO}&smoothing=1/3&unit=SPL"
    c = rew_script._decode_curve(
        rew_script.api_get(f"/measurements/{measurement_id}/{endpoint}{q}"))
    return [[round(f, 2), round(db, 2)] for f, db in c]


def _band_stats(bands):
    """Hur mycket jobb de 31 banden får: snitt av |dB|, värsta bandet, och hur
    många som slår i taket (+SAFE_BOOST_DB) eller golvet (-16 dB)."""
    gains = list(bands.values())
    return {
        "mean_abs": round(sum(abs(g) for g in gains) / len(gains), 2),
        "worst": f"{max(bands, key=lambda f: abs(bands[f])):g}",
        "worst_db": round(max(gains, key=abs), 2),
        "clamped": sum(1 for g in gains
                       if g >= dsp8000.SAFE_BOOST_DB or g <= dsp8000.GRAPHIC_MAX_CUT_DB),
    }


def curve(measurement_id):
    """Allt som går att visa UTAN att röra REW:s tillstånd: mätningens fält,
    uppmätt kurva, målkurvan och den preliminära korrigeringen (target -
    uppmätt vid ISO-banden, samma räkning som förslaget får med 0 filter)."""
    m = rew_script.find_measurement(measurement_id)
    meas = _plot(measurement_id, "frequency-response")
    tgt = rew_script._decode_curve(rew_script.api_get(
        f"/measurements/{measurement_id}/target-response?ppo={PLOT_PPO}&unit=SPL"))
    bands = rew_script.graphic_band_gains(measurement_id, after_peq=False)
    inband = [db for f, db in meas if 20 <= f <= 20000]
    return {
        "info": m,
        "meas": meas,
        "target": [[round(f, 2), round(db, 2)] for f, db in tgt],
        "bands": {f"{f:g}": round(db, 2) for f, db in bands.items()},
        "peq_max": dsp8000.PEQ_COUNT,
        "stats": {
            "points": len(meas),
            "spl_min": round(min(inband), 1) if inband else None,
            "spl_max": round(max(inband), 1) if inband else None,
            "spl_span": round(max(inband) - min(inband), 1) if inband else None,
            "default_name": default_name(m),
            **_band_stats(bands),
        },
    }


def compute(measurement_id, peq_count=dsp8000.PEQ_COUNT):
    """Räkna kedjan för `peq_count` parametriska filter och räkna om de 31
    banden mot resultatet - färre filter betyder mer jobb för grafiska EQ:n.

    n > 0: Match target i REW, behåll de n viktigaste filtren (smala djupa
    först, dsp8000.filter_priority) och räkna banden mot responsen EFTER dem,
    så stegen inte dubbelkorrigerar. n = 0: inga filter, banden gör allt
    (samma sak som rew_script.py --no-peq). Skriver ingen fil - det gör save().
    """
    m = rew_script.find_measurement(measurement_id)
    n = max(0, min(int(peq_count or 0), dsp8000.PEQ_COUNT))
    proposed, filters = [], []
    if n:
        rew_script.run_match_target(m["id"], peq=True)
        proposed = rew_script.get_filters(m["id"])
        filters = rew_script.keep_top_filters(m["id"], proposed, n=n)
    bands = rew_script.graphic_band_gains(m["id"], after_peq=bool(n))
    LAST.update(measurement=m, filters=filters, bands=bands)
    return {
        "peq_count": n,
        "proposed": len(proposed),
        "filters": [dict(f, bw_oct=round(dsp8000.q_to_octaves(f["q"]), 3),
                         priority=round(dsp8000.filter_priority(f.get("gaindB"), f.get("q")), 1))
                    for f in filters if f.get("q")],
        "bands": {f"{f:g}": round(db, 2) for f, db in bands.items()},
        "after": _plot(m["id"], "eq/frequency-response") if n else None,
        "stats": _band_stats(bands),
        "default_name": default_name(m),
    }


def save(name=None):
    """Skriv senaste uträkningen till history/suggestions/ i panelens format och
    lämna tillbaka innehållet. Sidan sparar sedan användarens egen kopia via
    filväljaren; arkivkopian ligger kvar som spår av körningen (paths.py)."""
    if not LAST:
        raise RuntimeError("Inget uträknat än - tryck 'Räkna om' först.")
    path = paths.new(paths.SUGGESTIONS,
                     Path(name or default_name(LAST["measurement"])).name)
    rew_script.save_output(LAST["measurement"], LAST["filters"], LAST["bands"], path=path)
    return {"name": path.name, "path": str(path), "json": path.read_text(encoding="utf-8"),
            "filters": len(LAST["filters"]), "bands": len(LAST["bands"])}


HTML = """<!doctype html>
<meta charset="utf-8">
<title>REW → DSP8000-förslag</title>
<style>
  :root { color-scheme: light dark; --m: #3a7bd5; --t: #e08a3c; --c: #3a7; }
  body { font: 13px system-ui, sans-serif; margin: 1rem; max-width: 1040px; }
  h1 { font-size: 1rem; } h2 { font-size: .95rem; margin: 1.5rem 0 .3rem; }
  #bar, #save { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
  #bar label, #save label { display: flex; gap: .3rem; align-items: center; }
  select, input, button { font: inherit; padding: .15rem .3rem; }
  select { max-width: 32rem; } #name { width: 24rem; }
  #status { margin-left: auto; opacity: .7; }
  .warn { color: #b45; }
  svg { width: 100%; height: 210px; border: 1px solid #8884; border-radius: 3px;
        display: block; margin-top: .3rem; }
  .legend { display: flex; gap: 1rem; opacity: .8; margin: .3rem 0 0; }
  .legend i { display: inline-block; width: 1.4rem; border-top: 2px solid;
              vertical-align: middle; margin-right: .3rem; font-style: normal; }
  table { border-collapse: collapse; margin-top: .3rem; }
  td, th { border: 1px solid #8884; padding: .15rem .5rem; text-align: left;
           font-variant-numeric: tabular-nums; }
  .note { opacity: .75; max-width: 46rem; margin: .5rem 0; }
  #saved, #result { margin-top: .5rem; padding: .5rem; border: 1px solid #8884;
                    border-radius: 3px; background: #8881; }
  #saved[hidden], #result[hidden] { display: none; }
  #result table { margin: .3rem 0 0; }
  code { background: #8881; padding: 0 .2rem; border-radius: 2px; }
</style>

<h1>REW → EQ-förslag för kontrollpanelen</h1>

<div id="bar">
  <label>Mätning <select id="m"><option>hämtar…</option></select></label>
  <button id="reload">Uppdatera listan</button>
  <span id="status"></span>
</div>

<p class="note">Att välja en mätning läser bara – REW rörs inte. Kurvan nedan är
  uppmätt svar (1/3-oktav) mot REW:s målkurva, och staplarna är korrigeringen
  som de 31 banden skulle få. Filtren räknas först när du sparar.</p>

<h2>Uppmätt svar och målkurva</h2>
<svg id="spl" viewBox="0 0 1000 210" preserveAspectRatio="none"></svg>
<div class="legend">
  <span><i style="color:var(--m)"></i>uppmätt</span>
  <span><i style="color:var(--t)"></i>målkurva</span>
  <span><i style="color:var(--c);border-top-style:dashed"></i>efter de valda filtren</span>
</div>

<h2>Preliminär korrigering, 31 band</h2>
<svg id="corr" viewBox="0 0 1000 210" preserveAspectRatio="none"></svg>
<div class="legend">
  <span><i style="color:var(--c)"></i>bandvärden</span>
  <span id="corrnote">preliminärt, utan parametriska filter</span>
</div>

<h2>Mätningen</h2>
<table id="info"><tr><td>Välj en mätning.</td></tr></table>

<h2>Parametriska filter och grafisk EQ</h2>
<div id="save">
  <label>Antal PEQ-filter <select id="peq"></select></label>
  <button id="calc">Räkna om</button>
  <label>Föreslaget filnamn <input id="name" placeholder="suggestion-….json"></label>
  <button id="go" disabled>Spara förslag…</button>
</div>
<p class="note">Enheten har 3 parametriska filter per kanal. Väljer du färre får
  de 31 banden ta över resten – <b>Räkna om</b> kör Match target i REW, behåller
  de valda filtren (<b>smala djupa först</b>: breda korrigeringar klarar grafiska
  EQ:n själv) och räknar om bandvärdena mot responsen <i>efter</i> filtren, så
  stegen inte dubbelkorrigerar. 0 filter = banden gör allt. Raden under visar hur
  mycket jobb banden får med ditt val.</p>
<div id="result" hidden></div>
<div id="saved" hidden></div>
<p class="note"><b>Spara förslag…</b> öppnar en filväljare där du bestämmer var
  filen hamnar (Chrome/Edge; i andra webbläsare blir det en vanlig nedladdning).
  En arkivkopia skrivs alltid till <code>history/suggestions/</code>. Formatet är
  det <code>dsp8000_gui.html</code> importerar: öppna panelen, <b>Importera från
  REW</b>, välj filen. Mätning gjord <b>med</b> EQ:n i kedjan? Välj läget
  <b>Merga</b> i panelen – då läggs förslaget ovanpå det som redan står där,
  med den andel du väljer.</p>

<script>
const $ = id => document.getElementById(id);
const ISO = __BANDS__;
let data = null, calc = null;      // data = read-only-vyn, calc = senaste uträkningen

const say = (t, warn) => { $('status').textContent = t; $('status').className = warn ? 'warn' : ''; };
const X = f => 40 + Math.log10(Math.max(f, 20) / 20) / 3 * 950;
const esc = s => String(s).replace(/[<&]/g, c => ({ '<': '&lt;', '&': '&amp;' }[c]));

// Rutnät + kurvor i ett SVG. ymin/ymax i dB, series = [[punkter, färg], …].
function plot(el, series, ymin, ymax, bars) {
  const Y = v => 200 - (v - ymin) / (ymax - ymin) * 190;
  const out = [];
  for (const f of [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
    out.push(`<line x1="${X(f)}" y1="0" x2="${X(f)}" y2="200" stroke="#8884"/>`
      + `<text x="${X(f) + 3}" y="208" font-size="10" fill="#888">${f >= 1000 ? f / 1000 + 'k' : f}</text>`);
  const stepY = (ymax - ymin) > 40 ? 10 : 6;
  for (let v = Math.ceil(ymin / stepY) * stepY; v <= ymax; v += stepY)
    out.push(`<line x1="40" y1="${Y(v)}" x2="990" y2="${Y(v)}" stroke="#8884"/>`
      + `<text x="2" y="${Y(v) + 3}" font-size="10" fill="#888">${v}</text>`);
  if (bars)
    for (const [f, v] of bars)
      out.push(`<rect x="${X(f) - 6}" y="${Math.min(Y(v), Y(0))}" width="12" `
        + `height="${Math.abs(Y(v) - Y(0))}" fill="var(--c)" opacity=".8"/>`);
  for (const [pts, color, dashed] of series)
    out.push(`<polyline fill="none" stroke="${color}" stroke-width="2"`
      + (dashed ? ' stroke-dasharray="6 4"' : '') + ' points="'
      + pts.map(([f, v]) => `${X(f).toFixed(1)},${Y(v).toFixed(1)}`).join(' ') + '"/>');
  el.innerHTML = out.join('');
}

// Kurvorna + staplarna. `c` = senaste uträkningen (filter valda) eller null.
function draw(d, c) {
  const all = d.meas.concat(d.target).map(p => p[1]);
  const lo = Math.floor(Math.min(...all) / 5) * 5, hi = Math.ceil(Math.max(...all) / 5) * 5;
  const spl = [[d.meas, 'var(--m)'], [d.target, 'var(--t)']];
  if (c && c.after) spl.push([c.after, 'var(--c)', true]);
  plot($('spl'), spl, lo, hi);
  const bands = (c || d).bands;
  plot($('corr'), [], -16, 16, ISO.map(f => [f, bands[f] ?? 0]));
  $('corrnote').textContent = c
    ? `med ${c.peq_count} parametriska filter`
    : 'preliminärt, utan parametriska filter';
}

const bandSummary = s => `snitt ${s.mean_abs} dB per band, störst `
  + `${s.worst_db > 0 ? '+' : ''}${s.worst_db} dB vid ${s.worst} Hz`
  + (s.clamped ? ` · ${s.clamped} band klipps mot enhetens gränser` : '');

function show(d) {
  data = d; calc = null;
  $('result').hidden = true;
  $('go').disabled = true;
  $('peq').innerHTML = [...Array(d.peq_max + 1)].map((_, i) => d.peq_max - i)
    .map(n => `<option value="${n}">${n} filter${n === d.peq_max ? ' (enhetens max)'
      : n === 0 ? ' – bara grafisk EQ' : ''}</option>`).join('');
  draw(d, null);

  const s = d.stats, rows = [
    ['Grafisk EQ utan filter', bandSummary(s)],
    ['Uppmätt 20 Hz–20 kHz', `${s.spl_min}–${s.spl_max} dB (${s.spl_span} dB spann, ${s.points} punkter)`],
  ];
  for (const [k, v] of Object.entries(d.info))
    rows.push([k, typeof v === 'number' ? +v.toFixed(3) : String(v)]);
  $('info').innerHTML = rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('');
  $('name').value = s.default_name;
  say('');
}

async function load(id) {
  say('läser mätning ' + id + '…');
  try {
    const r = await fetch('/curve?id=' + encodeURIComponent(id));
    const d = await r.json();
    if (d.error) return say(d.error, true);
    show(d);
  } catch (e) { say('kunde inte läsa: ' + e.message, true); }
}

async function fillList() {
  say('hämtar mätningar…');
  try {
    const ms = await (await fetch('/measurements')).json();
    if (ms.error) return say(ms.error, true);
    if (!ms.length) return say('REW har inga mätningar – kör en sweep först', true);
    $('m').innerHTML = ms.map(m =>
      `<option value="${esc(m.id)}">${esc(m.id)}: ${esc(m.title || '?')} (${esc(m.date || '')})</option>`).join('');
    $('m').value = ms[ms.length - 1].id;      // nyaste, som i terminalflödet
    load($('m').value);
  } catch (e) { say('ingen kontakt med REW: ' + e.message, true); }
}

$('m').onchange = () => load($('m').value);
$('reload').onclick = fillList;

$('calc').onclick = async () => {
  if (!data) return;
  const n = +$('peq').value;
  $('calc').disabled = true;
  say(n ? `kör Match target och behåller ${n} filter…` : 'räknar banden utan filter…');
  try {
    const r = await fetch('/compute', { method: 'POST', body: JSON.stringify({ id: $('m').value, peq: n }) });
    const c = await r.json();
    if (c.error) { say(c.error, true); return; }
    calc = c;
    draw(data, c);
    const rows = c.filters.map(f => `<tr><td>${(+f.frequency).toFixed(1)} Hz</td>`
      + `<td>${(+f.gaindB).toFixed(1)} dB</td><td>Q ${(+f.q).toFixed(2)}</td>`
      + `<td>${f.bw_oct} okt</td><td>prio ${f.priority}</td></tr>`).join('');
    $('result').hidden = false;
    $('result').innerHTML = `<b>${c.peq_count} filter</b> → grafisk EQ: ${bandSummary(c.stats)}`
      + `<br><span class="note">utan filter: ${bandSummary(data.stats)}`
      + (c.proposed > c.peq_count ? ` · REW föreslog ${c.proposed}, `
         + `${c.proposed - c.peq_count} valdes bort (bredast och grundast först)` : '')
      + '</span>' + (rows ? `<table>${rows}</table>` : '');
    say('uträknat – granska och spara');
    $('go').disabled = false;
  } catch (e) { say('misslyckades: ' + e.message, true); }
  finally { $('calc').disabled = false; }
};

$('go').onclick = async () => {
  if (!calc) return;
  const suggested = $('name').value.trim() || calc.default_name;
  // Filväljaren måste öppnas direkt i klicket (kräver user activation), alltså
  // före hämtningen från servern. Saknas den (Firefox/Safari) blir det i
  // stället webbläsarens vanliga nedladdning.
  let handle = null;
  if (window.showSaveFilePicker) {
    try {
      handle = await window.showSaveFilePicker({
        suggestedName: suggested,
        types: [{ description: 'EQ-förslag för DSP8000 (JSON)',
                  accept: { 'application/json': ['.json'] } }],
      });
    } catch (e) {
      if (e.name === 'AbortError') { say('sparandet avbröts'); return; }
      say('filväljaren gick inte att öppna: ' + e.message, true);
    }
  }
  $('go').disabled = true;
  say('sparar…');
  try {
    const r = await fetch('/save', { method: 'POST', body: JSON.stringify(
      { name: handle ? handle.name : suggested }) });
    const d = await r.json();
    if (d.error) { say(d.error, true); return; }
    let where;
    if (handle) {
      const w = await handle.createWritable();
      await w.write(d.json);
      await w.close();
      where = `Sparade <b>${esc(handle.name)}</b> dit du valde`;
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([d.json], { type: 'application/json' }));
      a.download = d.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      where = `Laddade ner <b>${esc(d.name)}</b>`;
    }
    $('saved').hidden = false;
    $('saved').innerHTML = `${where} – ${d.bands} band, ${d.filters} PEQ-filter. `
      + `Importera den i dsp8000_gui.html under "Importera från REW".`
      + `<br><span class="note">Arkivkopia: <code>${esc(d.path)}</code> · `
      + `<a href="/file?name=${encodeURIComponent(d.name)}" download>hämta igen</a></span>`;
    say('sparat');
  } catch (e) { say('misslyckades: ' + e.message, true); }
  finally { $('go').disabled = false; }
};

fillList();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, code=200, extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, fn, *a):
        """REW-fel (SystemExit ur rew_script, nätverksfel) blir ett fält i
        svaret i stället för en död tråd."""
        try:
            obj, code = fn(*a), 200
        except (Exception, SystemExit) as e:      # noqa: BLE001 - allt visas i sidan
            obj, code = {"error": f"{type(e).__name__}: {e}"}, 400
        self._send(json.dumps(obj).encode(), "application/json", code)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            page = HTML.replace("__BANDS__", json.dumps([f"{f:g}" for f in dsp8000.ISO_BANDS]))
            self._send(page.encode(), "text/html; charset=utf-8")
        elif u.path == "/measurements":
            self._json(measurements)
        elif u.path == "/curve":
            self._json(curve, (q.get("id") or [""])[0])
        elif u.path == "/file":
            # bara filer i history/suggestions/, och bara filnamnet ur frågan
            f = paths.SUGGESTIONS / Path((q.get("name") or [""])[0]).name
            if not f.is_file():
                self._json(lambda: (_ for _ in ()).throw(FileNotFoundError(str(f))))
                return
            self._send(f.read_bytes(), "application/json", extra=[
                ("Content-Disposition", f'attachment; filename="{f.name}"')])
        else:
            self._send(b'{"error":"404"}', "application/json", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if path == "/compute":
            self._json(compute, body.get("id"), body.get("peq", dsp8000.PEQ_COUNT))
        elif path == "/save":
            self._json(save, body.get("name"))
        else:
            self._send(b'{"error":"404"}', "application/json", 404)

    def log_message(self, *a):   # tyst
        pass


def serve(port=PORT, open_browser=True):
    rew_script.check_api_alive()        # tydligt fel här i stället för i sidan
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{srv.server_port}/"
    print(f"REW-export: {url}  (Ctrl-C avslutar)")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return srv


if __name__ == "__main__":
    serve()
