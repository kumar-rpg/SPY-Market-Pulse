"""Partial-session intraday trend scoring for SPY.

Adapted from the workspace's spy_intraday_trend.py: same four dimensions
(net move, persistence, close-location, VWAP posture), but scored against
"bars observed so far today" at each checkpoint rather than a completed
session. The neutral band still comes from the trailing 60-day distribution
of FULL-DAY open->close moves — it is NOT scaled down for elapsed time, so
early-session reads should be treated as soft/loose (documented limitation,
not silently hidden).
"""

from datetime import date, timedelta

from lib.alpaca_client import fetch_intraday_bars, fetch_daily_bars

SYMBOL = "SPY"
NEUTRAL_SIGMA = 0.5

MIN_BARS = 3  # guard against degenerate linreg reads right after 9:30


def linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, 0.0
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, r2


def _neutral_band(session_day):
    hist = [b for b in fetch_daily_bars(SYMBOL,
                                         (date.fromisoformat(session_day) - timedelta(days=120)).isoformat(),
                                         session_day)
            if b["t"][:10] < session_day][-60:]
    moves = [(b["c"] - b["o"]) / b["o"] * 100 for b in hist]
    if len(moves) < 10:
        return None, None
    m = sum(moves) / len(moves)
    sd = (sum((x - m) ** 2 for x in moves) / (len(moves) - 1)) ** 0.5
    return NEUTRAL_SIGMA * sd, sd


def score_partial_session(session_day, now_utc_iso):
    """`session_day`: 'YYYY-MM-DD'. `now_utc_iso`: RFC3339 UTC end-cursor for bars."""
    bars = fetch_intraday_bars(SYMBOL, f"{session_day}T13:30:00Z", now_utc_iso)
    if len(bars) < MIN_BARS:
        return {"insufficient_bars": True, "bars_observed": len(bars)}

    o = bars[0]["o"]
    c = bars[-1]["c"]
    hi = max(b["h"] for b in bars)
    lo = min(b["l"] for b in bars)
    net = (c - o) / o * 100

    pv = sum(b["vw"] * b["v"] for b in bars)
    vol = sum(b["v"] for b in bars)
    vwap = pv / vol if vol else float("nan")
    above = sum(1 for b in bars if b["c"] > vwap) / len(bars) * 100

    xs = [i * 5 / 60 for i in range(len(bars))]
    ys = [b["c"] for b in bars]
    slope, r2 = linreg(xs, ys)
    slope_pct = slope / o * 100

    clv = (c - lo) / (hi - lo) if hi > lo else 0.5

    band, hist_sd = _neutral_band(session_day)
    if band is None:
        direction = "UNKNOWN"
        support = 0
    else:
        if net > band:
            direction = "UP"
        elif net < -band:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"

        support = 0
        if direction == "UP":
            support = sum([slope_pct > 0, clv >= 0.6, above >= 60, r2 >= 0.4])
        elif direction == "DOWN":
            support = sum([slope_pct < 0, clv <= 0.4, above <= 40, r2 >= 0.4])

    conviction = "n/a"
    if direction not in ("NEUTRAL", "UNKNOWN"):
        conviction = "high" if support >= 3 else "moderate" if support == 2 else "low - signals disagree"

    return {
        "insufficient_bars": False,
        "bars_observed": len(bars),
        "session_open": round(o, 2),
        "last_price": round(c, 2),
        "session_high": round(hi, 2),
        "session_low": round(lo, 2),
        "net_move_pct": round(net, 3),
        "neutral_band_pct": round(band, 3) if band is not None else None,
        "band_note": "vs trailing-60d full-day sigma band; not scaled for elapsed time, partial-day reads are soft",
        "slope_pct_per_hour": round(slope_pct, 3),
        "r2": round(r2, 3),
        "clv": round(clv, 3),
        "vwap": round(vwap, 2),
        "vwap_above_pct": round(above, 1),
        "direction": direction,
        "conviction": conviction,
        "support": support,
    }
