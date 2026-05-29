"""Generate tuning/preview/index.html with base64-embedded E1, B1, E1_tuned audio."""
from __future__ import annotations
import base64, pathlib

ROOT = pathlib.Path(__file__).parent.parent

CANDIDATES = [
    {
        "id": "c8",
        "label": "crush_8bit",
        "title": "8-BIT",
        "score": 91,
        "accent": "#00c8ff",
        "bg_rgba": "rgba(0,200,255,.12)",
        "params": [
            ("PITCH",  "&minus;2 semitones"),
            ("LENGTH", "1.22 &mdash; extended pauses"),
            ("DRIVE",  "2 dB saturation"),
            ("CRUSH",  "8-bit"),
            ("ROOM",   "0.42 / damp 0.65 / wet 0.24"),
        ],
        "defect": "Slightly less pronounced vocal grain/rasp than official",
        "rubric": [
            ("Timbre Identity", "17/20", "near"),
            ("Cadence",         "18/20", "near"),
            ("Prosodic Contour","14/15", "near"),
            ("Authority",       "14/15", "near"),
            ("Diction",         "10/10", "perfect"),
            ("Synthetic Char.", "9/10",  "near"),
            ("Emotion",         "9/10",  "near"),
        ],
        "wav": ROOT / "tuning/renders/crush_8bit/combined.wav",
    },
    {
        "id": "c7",
        "label": "crush_7bit",
        "title": "7-BIT",
        "score": 97,
        "accent": "#00ff9d",
        "bg_rgba": "rgba(0,255,157,.12)",
        "params": [
            ("PITCH",  "&minus;2 semitones"),
            ("LENGTH", "1.22 &mdash; extended pauses"),
            ("DRIVE",  "2 dB saturation"),
            ("CRUSH",  "7-bit"),
            ("ROOM",   "0.42 / damp 0.65 / wet 0.24"),
        ],
        "defect": "Subtle vocal grain/crackle occasionally slightly more pronounced than ideal",
        "rubric": [
            ("Timbre Identity", "18/20", "near"),
            ("Cadence",         "20/20", "perfect"),
            ("Prosodic Contour","15/15", "perfect"),
            ("Authority",       "15/15", "perfect"),
            ("Diction",         "10/10", "perfect"),
            ("Synthetic Char.", "9/10",  "near"),
            ("Emotion",         "10/10", "perfect"),
        ],
        "wav": ROOT / "tuning/renders/crush_7bit/combined.wav",
    },
    {
        "id": "c6",
        "label": "crush_6bit",
        "title": "6-BIT",
        "score": 76,
        "accent": "#ff6b35",
        "bg_rgba": "rgba(255,107,53,.12)",
        "params": [
            ("PITCH",  "&minus;2 semitones"),
            ("LENGTH", "1.22 &mdash; extended pauses"),
            ("DRIVE",  "2 dB saturation"),
            ("CRUSH",  "6-bit &mdash; too heavy"),
            ("ROOM",   "0.42 / damp 0.65 / wet 0.24"),
        ],
        "defect": "Too crushed &mdash; loses chest resonance, warmth, and Cyclops identity",
        "rubric": [
            ("Timbre Identity", "10/20", "warn"),
            ("Cadence",         "17/20", "near"),
            ("Prosodic Contour","12/15", "near"),
            ("Authority",       "14/15", "near"),
            ("Diction",         "10/10", "perfect"),
            ("Synthetic Char.", "7/10",  "warn"),
            ("Emotion",         "6/10",  "warn"),
        ],
        "wav": ROOT / "tuning/renders/crush_6bit/combined.wav",
    },
]


def card_html(c: dict, b64: str) -> str:
    params_html = "".join(
        f'      {k:<7} <span>{v}</span><br>\n' for k, v in c["params"]
    )
    rubric_html = "".join(
        f'      <span>{row}</span><span class="val {cls}">{val}</span>\n'
        for row, val, cls in c["rubric"]
    )
    cid = c["id"]
    return f"""
  <div class="card" style="--accent:{c['accent']};--bg-hover:{c['bg_rgba']}">
    <div class="card-id">{c['title']}</div>
    <div class="card-name">{c['label']}</div>
    <div class="score-row">
      <span class="score-num">{c['score']}</span>
      <span class="score-denom">/ 100 &nbsp;Gemini</span>
    </div>
    <div class="params">{params_html.strip()}</div>
    <div class="defect">{c['defect']}</div>
    <button class="play-btn" id="btn-{cid}" onclick="togglePlay('{cid}')">
      <span id="icon-{cid}">&#9654;</span>
      <span id="label-{cid}">PLAY {cid.upper()}</span>
    </button>
    <div class="progress-bar"><div class="progress-fill" id="prog-{cid}"></div></div>
    <div class="rubric-grid">{rubric_html.strip()}</div>
    <audio id="audio-{cid}" src="data:audio/wav;base64,{b64}"></audio>
  </div>"""


CSS = """
  :root { --bg:#0a0e14; --panel:#111820; --border:#1e3a4a; --warn:#ff6b35; --text:#c8dde8; --dim:#4a6a7a; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:"Courier New",monospace;
         min-height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; padding:2rem; }
  header { text-align:center; margin-bottom:2.5rem; }
  .logo { font-size:.7rem; letter-spacing:.3em; color:var(--dim); text-transform:uppercase; }
  h1 { font-size:1.4rem; letter-spacing:.15em; color:#00c8ff; margin:.4rem 0; }
  .subtitle { font-size:.75rem; color:var(--dim); letter-spacing:.1em; }
  .cards { display:flex; gap:1.5rem; flex-wrap:wrap; justify-content:center; width:100%; max-width:1200px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:4px;
          padding:1.5rem 1.8rem; flex:1; min-width:280px; max-width:360px; position:relative; overflow:hidden; }
  .card::before { content:""; position:absolute; top:0; left:0; right:0; height:2px; background:var(--accent); }
  .card-id { font-size:.65rem; letter-spacing:.25em; text-transform:uppercase; margin-bottom:.3rem; color:var(--accent); }
  .card-name { font-size:1rem; letter-spacing:.08em; margin-bottom:1rem; color:#e8f4ff; }
  .score-row { display:flex; align-items:baseline; gap:.5rem; margin-bottom:1.2rem; }
  .score-num { font-size:2rem; font-weight:bold; line-height:1; color:var(--accent); }
  .score-denom { font-size:.85rem; color:var(--dim); }
  .params { font-size:.72rem; color:var(--dim); line-height:1.9; margin-bottom:1.2rem;
             border-top:1px solid var(--border); padding-top:.8rem; }
  .params span { color:var(--text); }
  .defect { font-size:.7rem; color:var(--warn); margin-bottom:1.3rem; line-height:1.5; opacity:.85; }
  .defect::before { content:"! "; }
  .play-btn { width:100%; padding:.85rem 1rem; background:transparent; border:1px solid var(--accent);
              border-radius:3px; font-family:"Courier New",monospace; font-size:.8rem;
              letter-spacing:.2em; text-transform:uppercase; cursor:pointer; color:var(--accent);
              transition:background .15s; display:flex; align-items:center; justify-content:center;
              gap:.6rem; margin-bottom:.5rem; }
  .play-btn:hover, .play-btn.playing { background:var(--bg-hover); }
  .play-btn.playing { animation:pulse 1.2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.55} }
  .progress-bar { width:100%; height:2px; background:var(--border); border-radius:1px; overflow:hidden; }
  .progress-fill { height:100%; width:0%; transition:width .1s linear; background:var(--accent); }
  .rubric-grid { display:grid; grid-template-columns:1fr auto; gap:.25rem .8rem; font-size:.68rem;
                 margin-top:1rem; border-top:1px solid var(--border); padding-top:.8rem; color:var(--dim); }
  .val { text-align:right; }
  .perfect { color:#00ff9d; }
  .near    { color:#00c8ff; }
  .warn    { color:#ff6b35; }
  footer { margin-top:2.5rem; font-size:.65rem; color:var(--dim); letter-spacing:.1em; text-align:center; }
"""

JS = """
  const audios = {};
  const active  = {};
  const ivals   = {};
  document.querySelectorAll('audio').forEach(a => {
    const id = a.id.replace('audio-','');
    audios[id] = a; active[id] = false;
  });

  function togglePlay(id) {
    Object.keys(active).forEach(k => { if (k !== id && active[k]) stopTrack(k); });
    active[id] ? stopTrack(id) : startTrack(id);
  }

  function startTrack(id) {
    const a = audios[id];
    a.currentTime = 0; a.play();
    active[id] = true;
    document.getElementById('btn-'  +id).classList.add('playing');
    document.getElementById('icon-' +id).innerHTML = '&#9646;&#9646;';
    document.getElementById('label-'+id).textContent = 'PLAYING…';
    ivals[id] = setInterval(() => {
      if (a.duration) document.getElementById('prog-'+id).style.width = (a.currentTime/a.duration*100)+'%';
    }, 100);
    a.onended = () => stopTrack(id);
  }

  function stopTrack(id) {
    audios[id].pause(); audios[id].currentTime = 0;
    active[id] = false; clearInterval(ivals[id]);
    document.getElementById('btn-'  +id).classList.remove('playing');
    document.getElementById('icon-' +id).innerHTML = '&#9654;';
    document.getElementById('label-'+id).textContent = 'PLAY ' + id.toUpperCase();
    document.getElementById('prog-' +id).style.width = '0%';
  }
"""


def build():
    cards = ""
    for c in CANDIDATES:
        b64 = base64.b64encode(c["wav"].read_bytes()).decode()
        cards += card_html(c, b64)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cyclops Voice &mdash; Phase 2 Candidates</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="logo">Cyclops Voice &mdash; Tuning Console</div>
  <h1>PHASE 2 CANDIDATES</h1>
  <div class="subtitle">Evaluation script &bull; 5 lines &bull; stereo 22.05&nbsp;kHz</div>
</header>
<div class="cards">{cards}</div>
<footer>CYCLOPS ONBOARD AI &bull; TUNING SYSTEM v2 &bull; PHASE 2</footer>
<script>{JS}</script>
</body>
</html>"""

    out = ROOT / "tuning/preview/index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Written {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
