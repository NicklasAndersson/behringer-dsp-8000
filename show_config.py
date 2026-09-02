"""
Visar vad som ska ställas in på DSP8000 utifrån rew_eq_suggestion.json
(som rew_script.py skapar).

Genererar dsp8000_config.html och öppnar den i webbläsaren. Ingen
GUI-toolkit - Homebrews python 3.14 saknar tkinter, och en HTML-sida
räcker för att bara visa värden.

Beroenden: inga (stdlib).
"""
import html
import json
import sys
import webbrowser
from pathlib import Path

import dsp8000

JSON_FILE = Path("rew_eq_suggestion.json")
HTML_FILE = Path("dsp8000_config.html")


def bar(db, scale=dsp8000.GRAPHIC_MAX_BOOST_DB):
    """Enkel CSS-stapel: mitten = 0 dB, höger = boost, vänster = cut."""
    frac = max(-1.0, min(1.0, db / scale))
    if frac >= 0:
        return f'<span class="bar"><span class="pos" style="width:{frac*50:.0f}%"></span></span>'
    return f'<span class="bar"><span class="neg" style="width:{-frac*50:.0f}%;margin-left:{50+frac*50:.0f}%"></span></span>'


def render(data):
    m = data.get("measurement", {})
    bands = data.get("graphic_band_gains_db", {})
    peqs = sorted(data.get("peq_filters", []),
                  key=lambda f: abs(f.get("gaindB", 0)), reverse=True)

    rows = []
    for f in dsp8000.ISO_BANDS:
        g = bands.get(str(f), bands.get(f, 0.0))
        cc_l = dsp8000.CC_GRAPHIC_LEFT[f]
        cc_r = dsp8000.CC_GRAPHIC_RIGHT[f]
        rows.append(
            f"<tr><td class='f'>{f} Hz</td>"
            f"<td class='g'>{g:+.1f} dB</td>"
            f"<td>{bar(g)}</td>"
            f"<td class='cc'>L {cc_l} / R {cc_r}</td>"
            f"<td class='cc'>{dsp8000.db_to_cc(g)}</td></tr>"
        )

    peq_rows = []
    for i, f in enumerate(peqs[:dsp8000.PEQ_COUNT], 1):
        peq_rows.append(
            f"<tr><td>{i}</td><td>{f.get('frequency', 0):.0f} Hz</td>"
            f"<td>{f.get('gaindB', 0):+.1f} dB</td>"
            f"<td>{f.get('q', 0):.2f}</td></tr>"
        )
    extra = len(peqs) - dsp8000.PEQ_COUNT
    peq_note = (f"<p class='warn'>REW föreslog {len(peqs)} filter, "
                f"DSP8000 har {dsp8000.PEQ_COUNT}. De {extra} minsta visas inte "
                f"- mät om efteråt och lägg ev. till manuellt.</p>") if extra > 0 else ""

    return f"""<!doctype html><meta charset="utf-8">
<title>DSP8000-konfig</title>
<style>
 body{{font:14px system-ui,sans-serif;margin:2rem;max-width:760px;color:#222}}
 h1{{font-size:1.2rem}} h2{{font-size:1rem;margin-top:2rem}}
 .meta{{color:#666}}
 table{{border-collapse:collapse;width:100%;margin-top:.5rem}}
 td,th{{padding:.25rem .5rem;border-bottom:1px solid #eee;text-align:left}}
 .f{{white-space:nowrap}} .g{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
 .cc{{color:#888;font-size:.85em;white-space:nowrap}}
 .bar{{display:inline-block;width:160px;height:12px;background:#f0f0f0;position:relative;vertical-align:middle}}
 .bar::before{{content:"";position:absolute;left:50%;top:0;bottom:0;border-left:1px solid #bbb}}
 .pos{{position:absolute;left:50%;top:0;bottom:0;background:#3a7}}
 .neg{{position:absolute;top:0;bottom:0;background:#c55}}
 .warn{{color:#a50;background:#fff8e8;padding:.5rem;border-radius:4px}}
 @media(prefers-color-scheme:dark){{
   body{{background:#1a1a1a;color:#ddd}} td,th{{border-color:#333}}
   .bar{{background:#2a2a2a}} .warn{{background:#332b18}}
 }}
</style>
<h1>DSP8000 – vad som ska ställas in</h1>
<p class="meta">Från mätning <b>{html.escape(str(m.get('title', '?')))}</b>
 ({html.escape(str(m.get('date', '')))}) · genererad {html.escape(str(data.get('generated_at', '')))}</p>

<h2>Grafisk EQ (31 band, per kanal)</h2>
<p class="meta">Kolumnerna: målförstärkning · CC-nummer (vänster/höger kanal) ·
 CC-värde att skicka (<b>okalibrerad</b> gissning, se readme).</p>
<table>
 <tr><th>Band</th><th class="g">Gain</th><th>–12 ····· 0 ····· +12</th><th>CC #</th><th>CC-värde</th></tr>
 {''.join(rows)}
</table>

<h2>Parametriska filter (max {dsp8000.PEQ_COUNT}, för rumsmoder)</h2>
{peq_note}
<table>
 <tr><th>#</th><th>Frekvens</th><th>Gain</th><th>Q</th></tr>
 {''.join(peq_rows) or '<tr><td colspan=4 class=meta>inga</td></tr>'}
</table>
<p class="meta">Parametriska filter kan inte fjärrstyras via MIDI på
 grundmodellen – ställ in dem för hand och spara som program.</p>
"""


def main():
    if not JSON_FILE.exists():
        raise SystemExit(f"{JSON_FILE} saknas - kör rew_script.py först.")
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    HTML_FILE.write_text(render(data), encoding="utf-8")
    print(f"Skrev {HTML_FILE}")
    if "--no-open" not in sys.argv:
        webbrowser.open(HTML_FILE.resolve().as_uri())


if __name__ == "__main__":
    main()
