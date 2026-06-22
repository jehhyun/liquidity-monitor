#!/usr/bin/env python3
"""
Fat Cat Capital — Liquidity Pressure Monitor
Fetches FRED data and generates a static HTML dashboard.
Runs via GitHub Actions twice daily.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

FRED_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "WTREGEN": {
        "label": "Treasury General Account",
        "section": "Plumbing",
        "cadence": "Weekly · Wed H.4.1",
        "divisor": 1000,
        "fmt": lambda v: f"${v/1000:.0f}B",
        "note": "Week-avg TGA via H.4.1. Trending toward ~$1T late July per Treasury quarterly guidance — drains reserves as it fills. No RRP buffer to absorb it.",
    },
    "RRPONTSYD": {
        "label": "Overnight Reverse Repo",
        "section": "Plumbing",
        "cadence": "Daily · NY Fed",
        "divisor": 1,
        "fmt": lambda v: f"${v:.2f}B",
        "note": "Depleted from $2T+ pre-2022 to near zero. Old shock absorber is gone — TGA rebuild now hits reserves directly.",
    },
    "WRESBAL": {
        "label": "Reserve Balances",
        "section": "Plumbing",
        "cadence": "Weekly · Wed H.4.1",
        "divisor": 1000000,
        "fmt": lambda v: f"${v/1000000:.2f}T",
        "note": "Last cushion with RRP gone. $2.5T is widely-cited stress threshold. TGA rebuild in July drains this directly.",
    },
    "SOFR": {
        "label": "SOFR",
        "section": "Plumbing",
        "cadence": "Daily · 8am ET",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "vs IORB 3.65% — spread of ~−2bps is normal. Spikes above IORB signal repo stress. Currently clean.",
    },
    "BAMLH0A0HYM2": {
        "label": "HY Corporate OAS",
        "section": "Credit",
        "cadence": "Daily",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "Tightest 5% of readings over 25 years. Widening is the stress signal — watch for convergence with subprime ABS as the escalation trigger.",
    },
    "DGS3MO": {
        "label": "3-month yield",
        "section": "Curve",
        "cadence": "Daily · H.15",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "Front-end policy anchor. No near-term cut priced, no acute funding stress.",
    },
    "DGS6MO": {
        "label": "6-month yield",
        "section": "Curve",
        "cadence": "Daily · H.15",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "Below 2Y = curve still upward sloping at the front end.",
    },
    "DGS2": {
        "label": "2-year yield",
        "section": "Curve",
        "cadence": "Daily · H.15",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "Most policy-sensitive tenor. Highest since Feb 2025 after Warsh's hawkish FOMC debut. ~Half of FOMC projecting a 2026 hike.",
    },
    "DGS10": {
        "label": "10-year yield",
        "section": "Curve",
        "cadence": "Daily · H.15",
        "divisor": 1,
        "fmt": lambda v: f"{v:.2f}%",
        "note": "Rising on hawkish repricing, not growth — wrong kind of higher rates per the framework.",
    },
    "T10Y2Y": {
        "label": "2s10s spread",
        "section": "Curve",
        "cadence": "Daily",
        "divisor": 1,
        "fmt": lambda v: f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%",
        "note": "Positive = upward sloping. Compressing as 2Y reprices faster than 10Y. Watch for inversion as hike bets firm up.",
    },
}

SECTION_ORDER = ["Plumbing", "Credit", "Curve"]
SECTION_KEYS = {
    "Plumbing": ["WTREGEN", "RRPONTSYD", "WRESBAL", "SOFR"],
    "Credit":   ["BAMLH0A0HYM2"],
    "Curve":    ["DGS3MO", "DGS6MO", "DGS2", "DGS10", "T10Y2Y"],
}

# Series where up = bad (for delta coloring)
UP_BAD = {"WTREGEN", "BAMLH0A0HYM2", "DGS2", "DGS10"}
# Series where down = bad
DOWN_BAD = {"WRESBAL", "T10Y2Y"}


def fetch_series(series_id, limit=25):
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    })
    url = f"{FRED_BASE}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data.get("observations", []) if o["value"] != "."]
        if not obs:
            return None
        latest = float(obs[0]["value"])
        latest_date = obs[0]["date"]
        prev = float(obs[min(19, len(obs)-1)]["value"])
        return {"latest": latest, "latestDate": latest_date, "prev20": prev}
    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        return None


def delta_color(series_id, d):
    if d is None or abs(d) < 0.0001:
        return "#555"
    up = d > 0
    if series_id in UP_BAD:
        return "#E24B4A" if up else "#97C459"
    if series_id in DOWN_BAD:
        return "#97C459" if up else "#E24B4A"
    return "#888"


def delta_text(series_id, curr, prev, fmt_fn):
    if curr is None or prev is None:
        return "no prior data"
    d = curr - prev
    if abs(d) < 0.0001:
        return "→ flat ~4wk"
    arrow = "↑" if d > 0 else "↓"
    sign = "+" if d > 0 else "−"
    try:
        amt = fmt_fn(abs(d))
        return f"{arrow} {sign}{amt} vs ~4wk ago"
    except:
        return f"{arrow} {d:+.3f} vs ~4wk ago"


def build_card_html(series_id, cfg, result):
    curr = result["latest"] if result else None
    prev = result["prev20"] if result else None
    latest_date = result["latestDate"] if result else "—"

    fmt = cfg["fmt"]
    display = fmt(curr) if curr is not None else "—"
    d = (curr - prev) if (curr is not None and prev is not None) else None
    d_text = delta_text(series_id, curr, prev, fmt)
    d_color = delta_color(series_id, d)

    return f"""
    <div class="card" onclick="this.classList.toggle('open')">
      <div class="card-top">
        <span class="card-label">{cfg['label']}</span>
        <span class="cadence">{cfg['cadence']}</span>
      </div>
      <div class="card-value">{display}</div>
      <div class="card-delta" style="color:{d_color}">{d_text}</div>
      <div class="card-note">{cfg['note']}<br><span class="last-print">Last print: {latest_date} · FRED ({series_id})</span></div>
      <div class="card-toggle">▼</div>
    </div>"""


def build_html(results, fetched_at):
    now_str = fetched_at.strftime("%b %d, %Y %H:%M UTC")

    sections_html = ""
    for section in SECTION_ORDER:
        keys = SECTION_KEYS[section]
        cards = ""
        for k in keys:
            cfg = SERIES.get(k)
            if cfg:
                cards += build_card_html(k, cfg, results.get(k))

        # ABS manual cards in Credit section
        if section == "Credit":
            cards += """
    <div class="card" onclick="this.classList.toggle('open')">
      <div class="card-top">
        <span class="card-label">ABS — Prime auto AAA</span>
        <span class="cadence">Weekly · manual</span>
      </div>
      <div class="card-value">42 bps</div>
      <div class="card-delta" style="color:#97C459">↓ −5bps vs ~4wk ago</div>
      <div class="card-note">3yr over Treasuries. Flat through early Jun, tighter YoY. Source: JPMorgan via Auto Finance News (not on FRED).<br><span class="last-print">Last print: Jun 4, 2026 (manual)</span></div>
      <div class="card-toggle">▼</div>
    </div>
    <div class="card" onclick="this.classList.toggle('open')">
      <div class="card-top">
        <span class="card-label">ABS — Subprime BBB</span>
        <span class="cadence">Weekly · manual</span>
      </div>
      <div class="card-value">stabilizing</div>
      <div class="card-delta" style="color:#EF9F27">↗ +~50bps after Tricolor/First Brands</div>
      <div class="card-note">Now plateauing. Convergence with HY OAS is the escalation signal — not subprime ABS stress alone.<br><span class="last-print">Last print: Jun 4, 2026 (manual)</span></div>
      <div class="card-toggle">▼</div>
    </div>"""

        sections_html += f"""
  <div class="section">
    <div class="section-label">{section}</div>
    <div class="grid">{cards}</div>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#111111">
  <title>Fat Cat Capital — Liquidity Monitor</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #111;
      color: #f0f0f0;
      font-family: system-ui, -apple-system, sans-serif;
      padding: 20px 16px 60px;
      max-width: 960px;
      margin: 0 auto;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 28px;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .header-left .eyebrow {{
      font-size: 10px;
      color: #444;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .header-left h1 {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.03em;
      line-height: 1;
    }}
    .header-right {{
      text-align: right;
    }}
    .live-dot {{
      font-size: 11px;
      color: #97C459;
      margin-bottom: 3px;
    }}
    .pulled-at {{
      font-size: 10px;
      color: #3a3a3a;
      line-height: 1.6;
    }}
    .section {{
      margin-bottom: 24px;
    }}
    .section-label {{
      font-size: 9px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #3a3a3a;
      font-weight: 600;
      border-bottom: 1px solid #1a1a1a;
      padding-bottom: 6px;
      margin-bottom: 10px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
      gap: 8px;
    }}
    .card {{
      background: #181818;
      border: 1px solid #252525;
      border-radius: 8px;
      padding: 12px 14px;
      cursor: pointer;
      user-select: none;
      position: relative;
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 6px;
      margin-bottom: 8px;
    }}
    .card-label {{
      font-size: 11px;
      color: #666;
      line-height: 1.35;
      flex: 1;
    }}
    .cadence {{
      font-size: 9px;
      color: #3a3a3a;
      background: #111;
      padding: 2px 5px;
      border-radius: 3px;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .card-value {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1;
      color: #f0f0f0;
      font-family: ui-monospace, 'SF Mono', monospace;
      margin-bottom: 6px;
    }}
    .card-delta {{
      font-size: 11px;
      min-height: 16px;
      margin-bottom: 2px;
    }}
    .card-note {{
      display: none;
      font-size: 11px;
      color: #666;
      line-height: 1.6;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid #252525;
    }}
    .last-print {{
      font-size: 10px;
      color: #383838;
      display: block;
      margin-top: 4px;
    }}
    .card-toggle {{
      text-align: right;
      font-size: 9px;
      color: #2a2a2a;
      margin-top: 6px;
    }}
    .card.open .card-note {{ display: block; }}
    .card.open .card-toggle {{ content: "▲"; }}
    .catalyst {{
      background: #181818;
      border: 1px solid #252525;
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 20px;
    }}
    .catalyst-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .catalyst-eyebrow {{
      font-size: 9px;
      color: #444;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .catalyst-cadence {{
      font-size: 9px;
      color: #3a3a3a;
    }}
    .catalyst-date {{
      font-size: 16px;
      font-weight: 600;
      color: #EF9F27;
      margin-bottom: 6px;
    }}
    .catalyst-note {{
      font-size: 11px;
      color: #555;
      line-height: 1.6;
    }}
    .footer {{
      font-size: 9px;
      color: #2e2e2e;
      line-height: 1.8;
      margin-top: 8px;
    }}
    @media (max-width: 480px) {{
      .grid {{ grid-template-columns: 1fr 1fr; }}
      .card-value {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="header-left">
      <div class="eyebrow">Fat Cat Capital</div>
      <h1>Liquidity pressure monitor</h1>
    </div>
    <div class="header-right">
      <div class="live-dot">● live</div>
      <div class="pulled-at">
        pulled {now_str}<br>
        via GitHub Actions · FRED API
      </div>
    </div>
  </div>

  {sections_html}

  <div class="catalyst">
    <div class="catalyst-header">
      <span class="catalyst-eyebrow">Next dated catalyst</span>
      <span class="catalyst-cadence">quarterly refunding cycle</span>
    </div>
    <div class="catalyst-date">Treasury QRA — August 5, 2026</div>
    <div class="catalyst-note">
      TGA rebuild to ~$1T projected late July. RRP at $0.25B = no buffer.
      Reserve drain hits banking system directly in the Jul–Sep window.
      Wednesday H.4.1 (WTREGEN + WRESBAL) is the live tracker between now and then.
    </div>
  </div>

  <div class="footer">
    10 FRED series · fetched twice daily via GitHub Actions (8am + 4pm ET) ·
    deltas vs ~20 prior observations · ABS manual (JPMorgan/Auto Finance News) ·
    tap any card for detail and source
  </div>

  <script>
    // Toggle card arrow text
    document.querySelectorAll('.card').forEach(card => {{
      card.addEventListener('click', () => {{
        const toggle = card.querySelector('.card-toggle');
        toggle.textContent = card.classList.contains('open') ? '▲' : '▼';
      }});
    }});
  </script>
</body>
</html>"""


def main():
    print(f"Fetching {len(SERIES)} FRED series...")
    results = {}
    for sid, cfg in SERIES.items():
        print(f"  {sid}...", end=" ")
        result = fetch_series(sid)
        if result:
            print(f"{cfg['fmt'](result['latest'])} ({result['latestDate']})")
        else:
            print("FAILED")
        results[sid] = result

    fetched_at = datetime.now(timezone.utc)
    html = build_html(results, fetched_at)

    out_path = Path(__file__).parent.parent / "docs" / "index.html"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html)
    print(f"\nWrote {out_path} ({len(html):,} bytes)")
    print(f"Done at {fetched_at.isoformat()}")


if __name__ == "__main__":
    main()
