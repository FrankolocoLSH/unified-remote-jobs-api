# RapidAPI Listing Draft — Unified Remote Jobs API

## Listing title
**Unified Remote Jobs API — RemoteOK + Remotive + Arbeitnow, Normalized & Deduped**

## Short description
One clean REST API for remote jobs across three major boards. Normalized schema, cross-board dedupe, salary parsing, and powerful filters — without wiring three different APIs yourself.

## Long description (for the listing page)

Stop juggling three job-board APIs with three different schemas. The Unified Remote Jobs API aggregates **RemoteOK**, **Remotive**, and **Arbeitnow** into a single, normalized, deduped feed of remote job listings — refreshed on a schedule and served from cache for millisecond responses.

**What you get:**
- 🔍 **One search endpoint** — keyword search across title, company, description, and tags
- 🧹 **Cross-board dedupe** — the same posting syndicated on two boards appears once (toggleable)
- 💰 **Normalized salaries** — `salary_min`/`salary_max` as annual equivalents (hourly rates annualized at 2080 hrs/yr, disclosed), raw text preserved in `salary_text`
- 🎯 **Filters that matter** — company, location text, remote-only, minimum salary, posted-since date, per-board source filter, newest/oldest/salary sort
- ⚡ **Fast by design** — every response served from cache; upstream boards are never hit on your request path
- 📊 **Source health** — `/stats` shows corpus size, per-board counts, and last refresh status

**Real use cases:**
1. **Job-board builders** — power a niche remote-jobs site (e.g. "remote Python jobs in LATAM") with one integration instead of three.
2. **Discord / Telegram job bots** — poll `/jobs?posted_since=<today>&q=react` on a timer and push fresh postings to a channel.
3. **Career dashboards & browser extensions** — salary-filtered search (`min_salary=100000&sort=salary`) for high-paying remote roles.
4. **Recruiting & market research** — track hiring demand by keyword/company over time; `/stats` gives corpus health at a glance.
5. **Email alert services** — combine `posted_since` + `q` filters to build "new matching jobs" digests.

**Endpoints:** `GET /jobs` · `GET /jobs/{id}` · `GET /stats` · `GET /health`
Interactive docs at `/docs`; full OpenAPI spec at `/openapi.json`.

## Pricing tiers (RapidAPI recommended structure)

| Plan | Price | Quota | For |
|---|---|---|---|
| **BASIC** | Free | 100 requests/day | Trying it out, hobby bots |
| **PRO** | $25/mo | 10,000 requests/month | Indie job boards, active bots |
| **ULTRA** | $75/mo | 50,000 requests/month | Production apps, alert services |
| **MEGA** | $150/mo | 250,000 requests/month | High-volume platforms, resellers |

(RapidAPI takes a 20% platform fee; payouts are monthly via Stripe.)

## Suggested tags/keywords
`jobs`, `remote jobs`, `employment`, `careers`, `job search`, `hiring`, `recruiting`, `salary data`
