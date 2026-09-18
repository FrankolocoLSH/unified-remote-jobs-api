# Niche Decision — RapidAPI Data API #1

Date: 2026-09-18
Method: ~20 logged-out requests per source from this Linux VM (datacenter IP), polite sleeps, measured success rate + field completeness.

## Niche A: Viral short-form video trends API (TikTok) — KILLED ❌

- **Success rate: 0/20 (0%)**
- All 5 logged-out endpoint variants (explore item list, For You recommend, mobile post list, hashtag detail, discovery trending) returned HTTP 200 with **zero video items**.
- Verified cause: TikTok now rejects unsigned API calls — response body is `{"status_code": 0, "status_msg": "url doesn't match"}`. Endpoints require signed URLs (msToken / browser session signing). No login-free path exists server-side.
- This matches known hostility: TikTok bot-detects datacenter IPs aggressively (confirmed independently on this network before).
- Options like logged-in sessions or third-party TikTok scraper APIs would add account-ban risk and ongoing cost — not a foundation to build on.

## Niche B: Remote jobs aggregator API — WINNER ✅

| Source | Success | Listings pulled | Field completeness (title/company/location/salary/url/posted) |
|---|---|---|---|
| RemoteOK API | 17/20 (85%) | 1,534 | 1.00 / 1.00 / 0.92 / 0.03 / 1.00 / 1.00 |
| RemoteOK API | 17/20 (85%) | 1,534 | 1.00 / 1.00 / 0.92 / 0.03 / 1.00 / 1.00 |
| Remotive API | 20/20 (100%) | 320 | 1.00 / 1.00 / 1.00 / 0.57 / 1.00 / 1.00 |
| Arbeitnow API | 20/20 (100%) | 2,300 | 1.00 / 1.00 / 0.97 / 0.00 / 1.00 / 1.00 |
| We Work Remotely RSS | 9/20 (45%) | 165 | flaky (301s, malformed XML) — **dropped as a source** |

**Scoring:**
- **Reliability:** B wins decisively. 3 of 4 sources are rock-solid free JSON APIs serving from SQLite cache; only origin refresh touches the network. A = 0%.
- **Buyer demand:** Proven paid demand for jobs data on RapidAPI (e.g., JSearch and similar paid listings). Job-board builders, Discord/Telegram job bots, career dashboards, and recruiting tools all buy this. TikTok data has demand too, but we cannot reliably serve it — unservable demand is worth $0.
- **Differentiation vs free:** The three source APIs are free *individually* but have three different schemas, three different filter models, no cross-board search, and no dedupe. Our paid value-add: **one normalized schema, unified keyword/location/salary/recency filters, cross-board dedupe, salary normalization, and a single fast endpoint** — exactly what bot builders and dashboard makers pay to avoid wiring themselves.

## Build plan (Phase 2)
FastAPI service over SQLite, cron-driven refresh (polite: per-source rate limits, retries, UA rotation), sources = RemoteOK + Remotive + Arbeitnow, normalized schema, OpenAPI docs, pytest suite, RapidAPI listing draft, Render/Railway deploy README.
