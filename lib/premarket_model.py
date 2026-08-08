"""Pre-market directional bias model.

Adapted from the workspace's premarket_direction_model.py: same six features,
same chronological-split logistic regression, refit fresh on every call
(~800 days of daily bars, a few seconds) rather than persisting a model
artifact. Returns a dict instead of printing a report.

Predictors (all observable strictly before 09:30 ET on the target day):
  prev_ret     prior session's open->close return
  prev_clv     prior session's close location in its range (0=low, 1=high)
  prev_range   prior session's high-low range, a volatility proxy
  vixy_ret     prior session's VIXY open->close, i.e. the change in fear
  btc_on       BTC/USD return from 21:00Z prior day to 13:00Z target day
  dow          day of week
"""

from datetime import date, timedelta

import numpy as np
from scipy.optimize import minimize

from lib.alpaca_client import paged, BARS_URL, CRYPTO_BARS_URL

NAMES = ["prev_ret", "prev_clv", "prev_range", "vixy_ret", "btc_on", "dow"]


def _btc_overnight(btc_by_hour, prev_day, day):
    a = btc_by_hour.get(f"{prev_day}T21")
    b = btc_by_hour.get(f"{day}T13")
    if not a or not b or not a["c"]:
        return None
    return (b["c"] - a["c"]) / a["c"] * 100


def train_and_predict(as_of_date):
    """Train on history strictly before `as_of_date`, predict today's direction.

    `as_of_date`: date object for "today" (the pre-open session being scored).
    Returns None if there isn't enough usable history (should not happen in
    practice with a live feed, but fail soft rather than crash a cron firing).
    """
    end = (as_of_date - timedelta(days=1)).isoformat()
    start = (as_of_date - timedelta(days=800)).isoformat()

    spy = paged(BARS_URL, {"symbols": "SPY", "timeframe": "1Day", "feed": "iex",
                            "adjustment": "all", "start": start, "end": end,
                            "limit": 10000}, "SPY")
    vixy = paged(BARS_URL, {"symbols": "VIXY", "timeframe": "1Day", "feed": "iex",
                             "adjustment": "all", "start": start, "end": end,
                             "limit": 10000}, "VIXY")
    btc = paged(CRYPTO_BARS_URL, {"symbols": "BTC/USD", "timeframe": "1Hour",
                                   "start": start, "end": end + "T23:59:59Z",
                                   "limit": 10000}, "BTC/USD")

    vixy_by_day = {b["t"][:10]: b for b in vixy}
    btc_by_hour = {b["t"][:13]: b for b in btc}

    rows = []
    for i in range(1, len(spy)):
        cur, prv = spy[i], spy[i - 1]
        day, pday = cur["t"][:10], prv["t"][:10]

        prev_ret = (prv["c"] - prv["o"]) / prv["o"] * 100
        rng = prv["h"] - prv["l"]
        prev_clv = (prv["c"] - prv["l"]) / rng if rng > 0 else 0.5
        prev_range = rng / prv["o"] * 100

        vb = vixy_by_day.get(pday)
        vixy_ret = (vb["c"] - vb["o"]) / vb["o"] * 100 if vb else None
        bo = _btc_overnight(btc_by_hour, pday, day)
        if vixy_ret is None or bo is None:
            continue

        target = (cur["c"] - cur["o"]) / cur["o"] * 100
        rows.append({
            "x": [prev_ret, prev_clv, prev_range, vixy_ret, bo,
                  date.fromisoformat(day).weekday()],
            "y": 1.0 if target > 0 else 0.0,
        })

    if len(rows) < 100:
        return None

    X = np.array([r["x"] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    n = len(rows)
    split = int(n * 0.70)
    mu, sd = X[:split].mean(0), X[:split].std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    Ztr, ytr = Z[:split], y[:split]
    Zte, yte = Z[split:], y[split:]

    def negll(w, Zm, ym, lam=1.0):
        z = np.clip(Zm @ w[1:] + w[0], -30, 30)
        p = 1 / (1 + np.exp(-z))
        eps = 1e-9
        return -(ym * np.log(p + eps) + (1 - ym) * np.log(1 - p + eps)).mean() \
            + lam * np.sum(w[1:] ** 2) / len(ym)

    res = minimize(negll, np.zeros(X.shape[1] + 1), args=(Ztr, ytr), method="L-BFGS-B")
    w = res.x

    def acc_of(Zm, ym):
        p = 1 / (1 + np.exp(-(Zm @ w[1:] + w[0])))
        return ((p > 0.5).astype(float) == ym).mean()

    oos_acc = acc_of(Zte, yte)
    oos_base = max(yte.mean(), 1 - yte.mean())

    # Build today's feature row from the most recent completed session + latest overnight data.
    last, prev_last = spy[-1], spy[-2]
    today_str = as_of_date.isoformat()
    prev_ret_t = (last["c"] - last["o"]) / last["o"] * 100
    rng_t = last["h"] - last["l"]
    prev_clv_t = (last["c"] - last["l"]) / rng_t if rng_t > 0 else 0.5
    prev_range_t = rng_t / last["o"] * 100
    vb_t = vixy_by_day.get(last["t"][:10])
    vixy_ret_t = (vb_t["c"] - vb_t["o"]) / vb_t["o"] * 100 if vb_t else 0.0
    bo_t = _btc_overnight(btc_by_hour, last["t"][:10], today_str) or 0.0
    x_today = np.array([prev_ret_t, prev_clv_t, prev_range_t, vixy_ret_t, bo_t,
                         as_of_date.weekday()], dtype=float)
    z_today = (x_today - mu) / sd
    p_up = 1 / (1 + np.exp(-(z_today @ w[1:] + w[0])))

    return {
        "p_up": round(float(p_up), 4),
        "predicted_direction": "UP" if p_up > 0.5 else "DOWN",
        "features": dict(zip(NAMES, [round(v, 3) for v in x_today.tolist()])),
        "oos_accuracy_context": f"{oos_acc*100:.1f}% OOS vs {oos_base*100:.1f}% naive base rate "
                                 f"(refit on {n} sessions, {start} to {end})",
    }
