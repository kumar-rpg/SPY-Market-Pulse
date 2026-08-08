"""Render a day's accumulated snapshots into one self-contained HTML report.

No external CDN dependency (keeps the Vercel deploy a single static file):
inline CSS, an inline SVG line chart of SPY price across checkpoints, and a
timeline table. Each entry branches on `phase` rather than assuming shape.
"""

import json


def _verdict_for_entry(e):
    if e.get("phase") == "preopen" and e.get("premarket_model"):
        return e["premarket_model"].get("predicted_direction", "UNKNOWN")
    if e.get("intraday_trend"):
        return e["intraday_trend"].get("direction", "UNKNOWN")
    return e.get("market_composite", {}).get("direction", "UNKNOWN")


def _final_verdict(entries):
    for e in reversed(entries):
        v = _verdict_for_entry(e)
        if v not in ("UNKNOWN", None):
            return v, e.get("checkpoint_label", "")
    return "UNKNOWN", ""


def _price_series(entries):
    pts = []
    for e in entries:
        price = None
        if e.get("intraday_trend") and not e["intraday_trend"].get("insufficient_bars"):
            price = e["intraday_trend"].get("last_price")
        elif e.get("basket", {}).get("SPY"):
            price = e["basket"]["SPY"].get("last")
        if price is not None:
            pts.append({"label": e.get("checkpoint_label", ""), "price": price})
    return pts


def _svg_chart(pts):
    if len(pts) < 2:
        return "<p class='muted'>Not enough data points yet for a chart.</p>"
    w, h, pad = 760, 220, 30
    prices = [p["price"] for p in pts]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    n = len(pts)
    xs = [pad + i * (w - 2 * pad) / (n - 1) for i in range(n)]
    ys = [h - pad - (p - lo) / span * (h - 2 * pad) for p in prices]
    path = " ".join(f"{'M' if i == 0 else 'L'}{xs[i]:.1f},{ys[i]:.1f}" for i in range(n))
    dots = "".join(f"<circle cx='{xs[i]:.1f}' cy='{ys[i]:.1f}' r='3' fill='#3b6fe0'>"
                    f"<title>{pts[i]['label']}: {pts[i]['price']}</title></circle>" for i in range(n))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' role='img' aria-label='SPY price through the session'>"
            f"<path d='{path}' fill='none' stroke='#3b6fe0' stroke-width='2'/>"
            f"{dots}</svg>")


def _entry_html(e):
    verdict = _verdict_for_entry(e)
    rows = []
    if e.get("phase") == "preopen" and e.get("premarket_model"):
        pm = e["premarket_model"]
        rows.append(f"<div>Pre-market model: <b>{pm.get('predicted_direction')}</b> "
                     f"(p_up={pm.get('p_up')}) — {pm.get('oos_accuracy_context', '')}</div>")
    if e.get("intraday_trend") and not e["intraday_trend"].get("insufficient_bars"):
        it = e["intraday_trend"]
        rows.append(f"<div>Intraday trend: <b>{it.get('direction')}</b> "
                     f"conviction={it.get('conviction')} ({it.get('support')}/4) — "
                     f"net {it.get('net_move_pct')}%, slope {it.get('slope_pct_per_hour')}%/hr, "
                     f"R²={it.get('r2')}, CLV={it.get('clv')}, VWAP above {it.get('vwap_above_pct')}%</div>")
    mc = e.get("market_composite", {})
    if mc.get("direction"):
        rows.append(f"<div>Market composite (SPY/QQQ/DIA/IWM/VIXY): <b>{mc.get('direction')}</b> "
                     f"score={mc.get('score')} — {mc.get('note', '')}</div>")
    basket = e.get("basket", {})
    basket_bits = ", ".join(
        f"{t}: {basket[t]['last']} ({basket[t]['chg_pct']:+.2f}%)" if basket.get(t) and basket[t].get('chg_pct') is not None
        else f"{t}: n/a"
        for t in ("SPY", "QQQ", "DIA", "IWM", "VIXY")
    )
    return (f"<tr><td>{e.get('checkpoint_label', '')}</td><td class='dir-{verdict.lower()}'>{verdict}</td>"
            f"<td>{''.join(rows)}<div class='muted'>{basket_bits}</div></td></tr>")


def build(snapshot_data):
    date_str = snapshot_data.get("date", "")
    entries = snapshot_data.get("entries", [])
    verdict, verdict_at = _final_verdict(entries) if entries else ("NO DATA", "")
    chart = _svg_chart(_price_series(entries))
    rows_html = "".join(_entry_html(e) for e in entries) or "<tr><td colspan='3'>No snapshots recorded.</td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>SPY Market Pulse — {date_str}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fff; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.2rem; }}
  .muted {{ color: #666; font-size: 0.85rem; }}
  .banner {{ padding: 1rem; border-radius: 8px; margin: 1rem 0; font-size: 1.1rem; font-weight: 600; }}
  .banner.dir-up {{ background: #e6f4ea; color: #1e7e34; }}
  .banner.dir-down {{ background: #fdecea; color: #c0392b; }}
  .banner.dir-neutral, .banner.dir-mixed, .banner.dir-unknown, .banner.dir-no {{ background: #f1f1f1; color: #555; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: 0.5rem; border-bottom: 1px solid #eee; vertical-align: top; font-size: 0.9rem; }}
  td.dir-up {{ color: #1e7e34; font-weight: 600; }}
  td.dir-down {{ color: #c0392b; font-weight: 600; }}
  td.dir-neutral, td.dir-mixed, td.dir-unknown {{ color: #666; font-weight: 600; }}
  .chart-wrap {{ margin-top: 1rem; border: 1px solid #eee; border-radius: 8px; padding: 0.5rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #14161a; color: #e6e6e6; }}
    .chart-wrap {{ border-color: #2a2d33; }}
    th, td {{ border-color: #2a2d33; }}
  }}
</style></head>
<body>
  <h1>SPY Market Pulse</h1>
  <div class="muted">{date_str} — {len(entries)} checkpoint(s) recorded</div>
  <div class="banner dir-{verdict.lower().replace(' ', '-')}">Final read: {verdict}{f' (as of {verdict_at})' if verdict_at else ''}</div>
  <div class="chart-wrap">{chart}</div>
  <table>
    <thead><tr><th>Checkpoint</th><th>Verdict</th><th>Detail</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p class="muted">Generated automatically. SPY intraday scoring uses Alpaca's free IEX feed (can lag real-time up to ~15 min).
  "Market overall" is approximated via SPY/QQQ/DIA/IWM/VIXY — Alpaca's free tier has no true advance/decline breadth data.</p>
  <script>const SNAPSHOT_DATA = {json.dumps(snapshot_data)};</script>
</body></html>"""
