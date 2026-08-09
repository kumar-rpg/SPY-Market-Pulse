# SPY Market Pulse

Automated intraday SPY / market-direction tracker. A GitHub Actions workflow
fires every ~15 minutes through the US trading session (starting 9:15am ET
pre-open), appends a scored snapshot to `snapshots/YYYY-MM-DD.json`, and a
second workflow at market close renders everything into a single HTML report
deployed to Vercel.

This is a **test run**, not production infra — see the plan doc this repo was
built from for known limitations (no early-close handling, etc). The
scripts self-gate on the real US/Eastern clock (`lib/market_calendar.py`), so
the cron schedules below are intentionally broad (covering both EDT/EST) and
safe to over-fire — off-window runs just no-op.

## Layout

- `lib/alpaca_client.py` — shared Alpaca REST helpers (auth, pagination).
- `lib/market_calendar.py` — US/Eastern trading-day + session-window gating.
- `lib/premarket_model.py` — pre-market logistic direction model (refit each morning).
- `lib/intraday_trend.py` — partial-session trend scoring (net move, slope, CLV, VWAP).
- `lib/breadth.py` — SPY/QQQ/DIA/IWM/VIXY basket as an "overall market" proxy.
- `lib/portfolio.py` — Alpaca paper-account equity/day-change + open positions with unrealized P&L (reuses the same `ALPACA_API_KEY`/`ALPACA_API_SECRET`, no extra secret needed). A fetch failure here soft-fails a checkpoint rather than aborting it.
- `lib/snapshot_store.py` — git-backed read/append/push of the day's snapshot file.
- `lib/report_builder.py` — renders the self-contained HTML report.
- `lib/vercel_deploy.py` — deploys the report via Vercel's REST API.
- `scripts/run_snapshot.py` — every ~15-min firing; auto-detects pre-open vs. session phase.
- `scripts/run_close_report.py` — the market-close firing.
- `.github/workflows/snapshot.yml` / `close-report.yml` — the schedules that drive it all.

## GitHub Actions secrets (Settings -> Secrets and variables -> Actions)

- `ALPACA_API_KEY`, `ALPACA_API_SECRET` — used by every snapshot firing.
- `VERCEL_TOKEN` — used only by the close-report firing to deploy.

The workflows push back to `main` using the auto-provisioned `GITHUB_TOKEN`,
which needs write access: Settings -> Actions -> General -> Workflow
permissions -> "Read and write permissions".

## Local dev

```
pip install -r requirements.txt
```

Create a local `.env` (git-ignored) with `ALPACA_API_KEY`, `ALPACA_API_SECRET`,
and (for the close script) `VERCEL_TOKEN`, then source it into your shell
before running a script directly, e.g.:

```
python scripts/run_snapshot.py
python scripts/run_close_report.py
```

## How the workflows use this repo

Each Actions run is a fresh checkout with no shared disk between runs — the
git repo is the persistence layer. Every entrypoint script `git pull`s
before reading and `git push`es after writing, so the next run sees prior
snapshots from the same trading day.
