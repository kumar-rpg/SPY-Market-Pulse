# SPY Market Pulse

Automated intraday SPY / market-direction tracker. A cloud routine fires
roughly hourly through the US trading session (starting 9:15am ET pre-open),
appends a scored snapshot to `snapshots/YYYY-MM-DD.json`, and at market close
renders everything into a single HTML report deployed to Vercel.

This is a **test run**, not production infra — see the plan doc this repo was
built from for known limitations (DST-static cron, no early-close handling,
etc).

## Layout

- `lib/alpaca_client.py` — shared Alpaca REST helpers (auth, pagination).
- `lib/market_calendar.py` — US/Eastern trading-day + session-window gating.
- `lib/premarket_model.py` — pre-market logistic direction model (refit each morning).
- `lib/intraday_trend.py` — partial-session trend scoring (net move, slope, CLV, VWAP).
- `lib/breadth.py` — SPY/QQQ/DIA/IWM/VIXY basket as an "overall market" proxy.
- `lib/snapshot_store.py` — git-backed read/append/push of the day's snapshot file.
- `lib/report_builder.py` — renders the self-contained HTML report.
- `lib/vercel_deploy.py` — deploys the report via Vercel's REST API.
- `scripts/run_snapshot.py --mode=preopen|hourly` — every pre-open/hourly firing.
- `scripts/run_close_report.py` — the market-close firing.

## Local dev

```
pip install -r requirements.txt
```

Create a local `.env` (git-ignored) with `ALPACA_API_KEY`, `ALPACA_API_SECRET`,
and (for the close script) `VERCEL_TOKEN`, then source it into your shell
before running a script directly, e.g.:

```
python scripts/run_snapshot.py --mode=preopen
python scripts/run_close_report.py
```

## How the cloud routine uses this repo

Each firing is a fresh, isolated checkout with no shared disk between runs —
the git repo is the persistence layer. Every entrypoint script `git pull`s
before reading and `git push`es after writing, so the next firing sees prior
snapshots from the same trading day.
