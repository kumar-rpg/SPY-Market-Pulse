#!/usr/bin/env python3
"""Entrypoint for every ~15-min GitHub Actions snapshot run.

Owns: trading-day/window gating (no-ops cleanly outside the intended window
- expected, not an error), fetching data, scoring, appending to
snapshots/<today>.json, commit+push. Run from the repo root.

Auto-detects phase from the real US/Eastern clock rather than taking a
--mode flag: the workflow's cron fires broadly across both DST regimes, and
this script decides what (if anything) to actually do.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from lib import market_calendar as cal
from lib import premarket_model, intraday_trend, breadth, portfolio, snapshot_store


def main():
    now = cal.now_et()
    phase = cal.session_phase(now)

    if not cal.is_trading_day(now.date()):
        print(f"NO-OP: {now.date()} is not a US market trading day.")
        return
    if phase == "closed":
        print(f"NO-OP: current ET session phase is 'closed' (now={now.isoformat()}). "
              f"Outside the 9:15am-4:00pm ET window; skipping.")
        return

    session_day = now.date().isoformat()
    now_utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checkpoint_label = f"{now.strftime('%H:%M')} ET " + ("pre-open" if phase == "preopen" else "checkpoint")

    entry = {
        "fired_at_et": now.isoformat(),
        "phase": phase,
        "checkpoint_label": checkpoint_label,
    }

    print(f"Fetching market basket ({phase})...")
    b = breadth.snapshot(phase, session_day, now_utc_iso if phase == "session" else None)
    entry.update(b)

    print("Fetching Alpaca portfolio snapshot...")
    try:
        entry["portfolio"] = portfolio.snapshot()
        p = entry["portfolio"]
        print(f"  -> equity ${p['equity']:.2f}  day change {p['day_change']:+.2f} "
              f"({p['day_change_pct']:+.2f}%)  {len(p['positions'])} open position(s)")
    except Exception as e:
        print(f"  -> WARN: portfolio fetch failed, skipping for this checkpoint: {e}")

    if phase == "preopen":
        print("Training pre-market direction model...")
        pm = premarket_model.train_and_predict(now.date())
        if pm:
            entry["premarket_model"] = pm
            print(f"  -> {pm['predicted_direction']} (p_up={pm['p_up']})")
        else:
            print("  -> insufficient history, skipping premarket model for today.")
    else:
        print("Scoring partial-session intraday trend...")
        it = intraday_trend.score_partial_session(session_day, now_utc_iso)
        entry["intraday_trend"] = it
        if it.get("insufficient_bars"):
            print(f"  -> only {it['bars_observed']} bars observed, skipping trend scoring.")
        else:
            print(f"  -> {it['direction']} conviction={it['conviction']} ({it['support']}/4)")

    print("Appending snapshot and pushing to origin/main...")
    snapshot_store.append_and_push(session_day, entry)
    print(f"DONE: recorded {checkpoint_label} for {session_day}.")


if __name__ == "__main__":
    main()
