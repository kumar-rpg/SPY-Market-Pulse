#!/usr/bin/env python3
"""Entrypoint for the market-close cloud routine firing.

Reads back today's full snapshot file, renders reports/<today>.html, commits
it into the repo, and deploys it to Vercel as the production deployment.
No-ops cleanly if today isn't a trading day or no snapshots exist yet.

Supports an optional --date YYYY-MM-DD override for manual backfills/reruns
(e.g. re-deploying a day's report after a prior deploy failure, or testing
the deploy path outside market hours). An explicit --date skips the
trading-day gate, since a manual override implies deliberate intent.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, ".")

from lib import market_calendar as cal
from lib import snapshot_store, report_builder, vercel_deploy


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, shell=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD override; skips the trading-day gate.")
    args = ap.parse_args()

    if args.date:
        session_day = args.date
    else:
        now = cal.now_et()
        if not cal.is_trading_day(now.date()):
            print(f"NO-OP: {now.date()} is not a US market trading day.")
            return
        session_day = now.date().isoformat()
    data = snapshot_store.load_today(session_day)
    if not data["entries"]:
        print(f"NO-OP: no snapshots recorded for {session_day} yet, nothing to report.")
        return

    print(f"Building report for {session_day} from {len(data['entries'])} snapshot(s)...")
    html = report_builder.build(data)

    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", f"{session_day}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    _run(["git", "pull", "--rebase", "origin", "main"])
    _run(["git", "add", report_path])
    commit = _run(["git", "commit", "-m", f"report: {session_day} end-of-day HTML"])
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        print(f"WARN: git commit issue: {commit.stderr}")
    push = _run(["git", "push", "origin", "main"])
    if push.returncode != 0:
        print(f"WARN: git push issue: {push.stderr}")

    print("Deploying to Vercel...")
    url = vercel_deploy.deploy_html(html)
    print(f"DONE: deployed {session_day} report -> {url}")


if __name__ == "__main__":
    main()
