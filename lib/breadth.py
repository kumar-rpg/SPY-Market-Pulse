"""'Overall market' stand-in: SPY + QQQ + DIA + IWM + VIXY basket.

Alpaca's free IEX feed has no true advance/decline breadth data, so this ETF
basket (same set premarket_direction_model.py already pulls) is the agreed
proxy. VIXY is a volatility ETF, not a direction ETF: it moving up is treated
as a headwind for the composite score below, not a tailwind.
"""

from datetime import date, timedelta

from lib.alpaca_client import fetch_daily_bars, fetch_intraday_bars

TICKERS = ["SPY", "QQQ", "DIA", "IWM", "VIXY"]


def _chg_pct_from_daily(symbol, as_of_date_str):
    start = (date.fromisoformat(as_of_date_str) - timedelta(days=10)).isoformat()
    bars = fetch_daily_bars(symbol, start, as_of_date_str)
    if len(bars) < 2:
        return None
    prev, last = bars[-2], bars[-1]
    return {"last": round(last["c"], 2), "chg_pct": round((last["c"] - prev["c"]) / prev["c"] * 100, 3)}


def _chg_pct_intraday(symbol, session_day, now_utc_iso):
    prior = _chg_pct_from_daily(symbol, session_day)
    prev_close = None
    if prior:
        start = (date.fromisoformat(session_day) - timedelta(days=10)).isoformat()
        bars = fetch_daily_bars(symbol, start, session_day)
        prev_close = bars[-2]["c"] if len(bars) >= 2 else None

    bars = fetch_intraday_bars(symbol, f"{session_day}T13:30:00Z", now_utc_iso)
    if not bars:
        return prior
    last_price = bars[-1]["c"]
    if prev_close:
        return {"last": round(last_price, 2), "chg_pct": round((last_price - prev_close) / prev_close * 100, 3)}
    return {"last": round(last_price, 2), "chg_pct": None}


def snapshot(phase, session_day, now_utc_iso=None):
    """phase: 'preopen' uses daily-bar change; 'session' uses live intraday bars."""
    basket = {}
    for t in TICKERS:
        if phase == "preopen":
            basket[t] = _chg_pct_from_daily(t, session_day)
        else:
            basket[t] = _chg_pct_intraday(t, session_day, now_utc_iso)

    non_vixy = [basket[t]["chg_pct"] for t in ("SPY", "QQQ", "DIA", "IWM")
                if basket.get(t) and basket[t]["chg_pct"] is not None]
    vixy_chg = basket.get("VIXY", {}).get("chg_pct") if basket.get("VIXY") else None

    if not non_vixy:
        return {"basket": basket, "market_composite": {"direction": "UNKNOWN", "score": None}}

    up_count = sum(1 for v in non_vixy if v > 0)
    score = up_count / len(non_vixy)
    if vixy_chg is not None and vixy_chg > 0:
        score -= 0.15  # rising VIXY is a headwind on the composite read
    score = max(0.0, min(1.0, score))

    direction = "UP" if score >= 0.6 else "DOWN" if score <= 0.4 else "MIXED"

    return {
        "basket": basket,
        "market_composite": {
            "direction": direction,
            "score": round(score, 3),
            "note": f"{up_count}/{len(non_vixy)} of SPY/QQQ/DIA/IWM positive"
                    + (f", VIXY {'up' if vixy_chg > 0 else 'down'}" if vixy_chg is not None else ""),
        },
    }
