#!/usr/bin/env python3
"""Entrypoint for every pre-open/hourly cloud routine firing.

Owns: trading-day/window gating (no-ops cleanly outside the intended window
- expected, not an error), fetching data, scoring, appending to
snapshots/<today>.json, commit+push. Run from the repo root.
"""

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from lib import market_calendar as cal
from lib import premarket_model, intraday_trend, breadth, snapshot_store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preopen", "hourly"], required=True)
    args = ap.parse_args()

    now = cal.now_et()
    phase = cal.session_phase(now)

    if not cal.is_trading_day(now.date()):
        print(f"NO-OP: {now.date()} is not a US market trading day.")
        return
    if args.mode == "preopen" and phase != "preopen":
        print(f"NO-OP: fired for --mode=preopen but current ET session phase is '{phase}' "
              f"(now={now.isoformat()}). Likely DST-drifted cron slot; skipping.")
        return
    if args.mode == "hourly" and phase != "session":
        print(f"NO-OP: fired for --mode=hourly but current ET session phase is '{phase}' "
              f"(now={now.isoformat()}). Likely DST-drifted cron slot or outside session; skipping.")
        return

    session_day = now.date().isoformat()
    now_utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checkpoint_label = f"{now.strftime('%H:%M')} ET " + ("pre-open" if args.mode == "preopen" else "checkpoint")

    entry = {
        "fired_at_et": now.isoformat(),
        "phase": args.mode,
        "checkpoint_label": checkpoint_label,
    }

    print(f"Fetching market basket ({args.mode})...")
    b = breadth.snapshot(args.mode, session_day, now_utc_iso if args.mode == "hourly" else None)
    entry.update(b)

    if args.mode == "preopen":
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
