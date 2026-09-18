# Unified Remote Jobs API

One normalized REST API over three public remote-job boards — **RemoteOK**, **Remotive**, and **Arbeitnow**. Keyword search, location / remote-only / salary / recency filters, cross-board dedupe, and normalized salary fields. Data is refreshed on a cron into SQLite; the API serves only from the local DB, so it's fast even when upstream boards are slow.

Picked over a TikTok-trends API after a head-to-head reliability spike (see [DECISION.md](DECISION.md)): TikTok's logged-out endpoints now require signed URLs (0/20 requests returned data), while all three job sources served reliably.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/jobs` | Search: `q`, `company`, `location`, `remote_only`, `min_salary`, `posted_since` (YYYY-MM-DD), `source`, `dedupe` (default true), `sort` (newest/oldest/salary), `limit` (≤100), `offset` |
| GET | `/jobs/{id}` | One job |
| GET | `/stats` | Corpus size, per-source counts, last refresh status |
| GET | `/health` | Health check (always public) |

Interactive docs: `/docs` (Swagger UI), `/openapi.json`.

### Salary normalization (disclosed)

- `salary_min` / `salary_max`: annual equivalents. Hourly rates (e.g. `$90 - $150 /hour`) are annualized at 2080 hrs/yr.
- `salary_text`: the raw string as published, always preserved.
- European decimal commas (`$31,2k`) are parsed as 31.2k.
- Missing/ambiguous salaries stay `null` — never guessed.

## Local dev

```bash
cd ~/workspace/rapidapi
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# populate the DB (takes a few minutes; polite 2s+ per-host pacing)
.venv/bin/python -m jobsapi.refresh

# serve
.venv/bin/uvicorn jobsapi.main:app --reload --port 8000
# -> http://localhost:8000/docs
```

Run tests: `.venv/bin/python -m pytest tests/ -q`
Tests use only real recorded API responses (`tests/fixtures/`, captured live); no invented data.

## Scheduled refresh (cron)

The API never scrapes on request — keep the DB fresh with a cron job:

```cron
# every 6 hours
0 */6 * * * cd /path/to/rapidapi && /path/to/rapidapi/.venv/bin/python -m jobsapi.refresh >> /var/log/jobsapi-refresh.log 2>&1
```

`refresh.py` logs per-source results to the `refresh_log` table (visible via `/stats`); exit code is 1 if any source failed.

## Deploy

### Render (recommended — free tier works)
1. Push this folder to a GitHub repo.
2. Render dashboard → **New +** → **Web Service** → connect the repo.
3. Render auto-detects the `Dockerfile`. Set env var `JOBS_DB=/app/data/jobs.db`.
4. Add a **Disk** (1 GB) mounted at `/app/data` so SQLite survives restarts.
5. Add a **Cron Job** (same repo, Docker): command `python -m jobsapi.refresh`, schedule `0 */6 * * *`. Set the same `JOBS_DB` and disk mount.
6. Note the service URL, e.g. `https://remote-jobs-api.onrender.com`.

### Railway
1. `railway init` → deploy from the repo (Dockerfile is picked up automatically).
2. Add a **Volume** mounted at `/app/data`; set `JOBS_DB=/app/data/jobs.db`.
3. Add a second **Cron** service in the same project running `python -m jobsapi.refresh` on `0 */6 * * *` with the volume attached.

### Optional hardening
Set env var `RAPIDAPI_PROXY_SECRET` to a random string, and configure the same value in RapidAPI (API Settings → proxy secret header). Then only requests carrying `X-RapidAPI-Proxy-Secret` are served (except `/`, `/health`, docs).

No secrets are committed to this repo — everything sensitive comes from env vars.

## Register on RapidAPI

1. [rapidapi.com](https://rapidapi.com) → **My APIs** → **Add New API** → REST.
2. Name it per [LISTING.md](LISTING.md); set the base URL to your deployed service URL.
3. **Endpoints**: add `GET /jobs`, `GET /jobs/{id}`, `GET /stats` — paste the query params from `/docs`; RapidAPI imports the OpenAPI spec from `https://YOUR-URL/openapi.json` to speed this up.
4. **Monetize** tab → create the 4 plans from [LISTING.md](LISTING.md) (BASIC free / PRO $25 / ULTRA $75 / MEGA $150).
5. Add the description + use cases from [LISTING.md](LISTING.md); publish.
6. Stripe payout: RapidAPI pays providers monthly (20% platform fee). Connect payout details under **My APIs → Monetization**.

## Politeness & legality notes

- Only public, unauthenticated endpoints are used (RemoteOK/Remotive/Arbeitnow all offer free public APIs).
- Remotive's public API exposes the newest jobs per category (~16/category) — that slice is a freshness feature, and it's combined with the full RemoteOK/Arbeitnow pulls.
- Per-host minimum 2s between requests, rotating user-agents, retries with backoff.
- No invented listings: every row traces to a real upstream posting with its source URL.
