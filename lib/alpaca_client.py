"""Shared Alpaca REST client helpers.

Auth pattern lifted from the workspace's existing alpaca_test.py /
premarket_direction_model.py / spy_intraday_trend.py scripts: credentials
come from the environment only, never written to disk.
"""

import os
import sys

import requests

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
CRYPTO_BARS_URL = "https://data.alpaca.markets/v1beta3/crypto/us/bars"


def _headers():
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        sys.exit("Set ALPACA_API_KEY and ALPACA_API_SECRET in your environment first.")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def paged(url, params, key):
    """Follow Alpaca's cursor pagination and return the flattened bar list for `key`."""
    out, token = [], None
    headers = _headers()
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        r = requests.get(url, headers=headers, params=p, timeout=60)
        if r.status_code != 200:
            sys.exit(f"[{r.status_code}] {url}: {r.text[:250]}")
        j = r.json()
        out.extend(j.get("bars", {}).get(key, []))
        token = j.get("next_page_token")
        if not token:
            return out


def fetch_daily_bars(symbol, start, end, limit=10000):
    return paged(BARS_URL, {"symbols": symbol, "timeframe": "1Day", "feed": "iex",
                             "adjustment": "all", "start": start, "end": end,
                             "limit": limit}, symbol)


def fetch_intraday_bars(symbol, start_iso, end_iso, timeframe="5Min", limit=10000):
    """5-min (or other) bars for a session, `start_iso`/`end_iso` as RFC3339 UTC strings."""
    return paged(BARS_URL, {"symbols": symbol, "timeframe": timeframe, "feed": "iex",
                             "limit": limit, "start": start_iso, "end": end_iso}, symbol)


def fetch_latest_daily_bar(symbol):
    """Most recent completed daily bar plus prior day's, for computing a change %."""
    from datetime import date, timedelta
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=10)).isoformat()
    bars = fetch_daily_bars(symbol, start, end)
    return bars[-2:] if len(bars) >= 2 else bars
