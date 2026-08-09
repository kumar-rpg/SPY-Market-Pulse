"""Alpaca paper-trading account equity / positions snapshot.

Same auth pattern as lib/alpaca_client.py, but hits the trading account API
(paper-api.alpaca.markets) rather than the market-data API - separate base
URL, so kept in its own module.
"""

import os
import sys

import requests

BASE = "https://paper-api.alpaca.markets/v2"


def _headers():
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        sys.exit("Set ALPACA_API_KEY and ALPACA_API_SECRET in your environment first.")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def snapshot():
    """Current account equity/day-change plus open positions with unrealized P&L.

    Raises on request failure - callers that shouldn't let a portfolio API
    hiccup kill an otherwise-successful market snapshot should catch and
    soft-fail (see scripts/run_snapshot.py).
    """
    headers = _headers()
    acct = requests.get(f"{BASE}/account", headers=headers, timeout=15)
    acct.raise_for_status()
    acct = acct.json()

    pos = requests.get(f"{BASE}/positions", headers=headers, timeout=15)
    pos.raise_for_status()
    pos = pos.json()

    equity = float(acct.get("equity", 0))
    last_equity = float(acct.get("last_equity", equity))
    day_change = equity - last_equity
    day_change_pct = (day_change / last_equity * 100) if last_equity else 0.0

    positions = [{
        "symbol": p.get("symbol"),
        "qty": float(p.get("qty", 0)),
        "avg_entry_price": round(float(p.get("avg_entry_price", 0)), 2),
        "current_price": round(float(p.get("current_price", 0)), 2),
        "market_value": round(float(p.get("market_value", 0)), 2),
        "unrealized_pl": round(float(p.get("unrealized_pl", 0)), 2),
        "unrealized_plpc": round(float(p.get("unrealized_plpc", 0)) * 100, 3),
    } for p in pos]

    return {
        "equity": round(equity, 2),
        "cash": round(float(acct.get("cash", 0)), 2),
        "portfolio_value": round(float(acct.get("portfolio_value", 0)), 2),
        "day_change": round(day_change, 2),
        "day_change_pct": round(day_change_pct, 3),
        "positions": positions,
    }
