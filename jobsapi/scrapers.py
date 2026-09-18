"""Polite fetching + normalization for the three job-board sources.

Politeness: per-host minimum interval between requests, rotating user-agents,
retries with exponential backoff, generous timeouts. All parsers are pure
functions so they can be unit-tested against recorded fixtures.
"""
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from . import config

_last_request: Dict[str, float] = {}


def polite_get(url: str, session: Optional[requests.Session] = None) -> requests.Response:
    """GET with per-host rate limiting, UA rotation, retries + backoff."""
    host = urlparse(url).netloc
    sess = session or requests.Session()
    last_exc = None
    for attempt in range(config.MAX_RETRIES):
        # per-host throttle
        wait = config.MIN_REQUEST_INTERVAL_S - (time.time() - _last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            r = sess.get(
                url,
                headers={
                    "User-Agent": random.choice(config.USER_AGENTS),
                    "Accept": "application/json",
                },
                timeout=config.REQUEST_TIMEOUT_S,
            )
            _last_request[host] = time.time()
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                last_exc = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
        except (requests.RequestException, RuntimeError) as e:
            last_exc = e
            _last_request[host] = time.time()
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"GET failed after {config.MAX_RETRIES} tries: {url} ({last_exc})")


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_salary(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """Parse salary strings like '$80k - $120k', '€50,000–€70,000', '£45k'.

    Returns (min, max, currency_code) as ANNUAL equivalents — hourly rates are
    annualized at 2080 hrs/yr (disclosed normalization; raw text is always kept
    in salary_text). Conservative: returns (None, None, '') when the format is
    ambiguous rather than guessing.
    """
    if not text or not text.strip():
        return None, None, ""
    t = text.strip()
    # European decimal comma: "31,2k" -> "31.2k" (comma + 1-2 digits = decimal;
    # comma + 3 digits like "1,200" stays a thousands separator)
    t = re.sub(r"(\d),(\d{1,2})(?=\D|$)", r"\1.\2", t)
    hourly = bool(re.search(r"/\s*(hour|hr)\b", t, re.I))
    currency = "USD"
    if "€" in t:
        currency = "EUR"
    elif "£" in t:
        currency = "GBP"
    elif "₹" in t:
        currency = "INR"
    elif "C$" in t or re.search(r"\bCAD\b", t, re.I):
        currency = "CAD"
    elif "A$" in t or re.search(r"\bAUD\b", t, re.I):
        currency = "AUD"

    # find number tokens, honoring k/m suffixes: "$80k", "120,000", "1.2m"
    tokens = re.findall(r"(\d[\d,]*\.?\d*)\s*([kKmM]?)", t)
    values = []
    for num, suffix in tokens:
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if suffix.lower() == "k":
            v *= 1_000
        elif suffix.lower() == "m":
            v *= 1_000_000
        # bare 2-3 digit numbers next to a 'k' sibling are usually thousands too ("80-120k")
        values.append(v)
    if not values:
        return None, None, currency if currency != "USD" or "$" in t else ""
    # fix "80-120k" style: first token missing suffix while later tokens have it
    suffixes = [s for _, s in tokens]
    if values and len(values) > 1 and not suffixes[0] and any(suffixes[1:]):
        mult = 1_000 if "k" in [s.lower() for s in suffixes[1:]] else 1_000_000
        if values[0] < 1000:
            values[0] *= mult
    # sanity: plausible annual salaries; drop implausible values
    values = [v * 2080 if hourly else v for v in values]  # disclosed: hourly -> annual equiv.
    values = [v for v in values if 1_000 <= v <= 5_000_000]
    if not values:
        return None, None, ""
    lo, hi = min(values), max(values)
    return (lo, hi, currency) if ("$" in t or "€" in t or "£" in t or "₹" in t
                                 or re.search(r"\b(USD|EUR|GBP|CAD|AUD|INR)\b", t, re.I)
                                 or any(s for _, s in tokens)) else (None, None, "")


def _iso_date(value) -> str:
    """Best-effort → 'YYYY-MM-DD' date string."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return ""
    s = str(value).strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    return ""


# ---------------------------------------------------------------- RemoteOK ---
def fetch_remoteok(session: Optional[requests.Session] = None) -> List[Dict]:
    jobs: List[Dict] = []
    for tag in config.REMOTEOK_TAGS:
        try:
            r = polite_get(f"https://remoteok.com/api?tag={tag}", session)
            jobs.extend(parse_remoteok(r.json()))
        except Exception as e:
            print(f"[remoteok:{tag}] error: {e}")
    # tag searches overlap — dedupe by source_key here
    seen, unique = set(), []
    for j in jobs:
        if j["source_key"] not in seen:
            seen.add(j["source_key"])
            unique.append(j)
    return unique


def parse_remoteok(payload) -> List[Dict]:
    items = payload[1:] if isinstance(payload, list) else []  # [0] is a legal notice
    out = []
    for j in items:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        salary_min = j.get("salary_min") or None
        salary_max = j.get("salary_max") or None
        if salary_min == 0:
            salary_min = None
        if salary_max == 0:
            salary_max = None
        out.append({
            "source": "remoteok",
            "source_key": str(j.get("id") or j.get("slug") or j.get("url")),
            "title": (j.get("position") or "").strip(),
            "company": (j.get("company") or "").strip(),
            "location": (j.get("location") or "").strip() or "Remote",
            "remote": True,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_currency": "USD",
            "salary_text": "",
            "url": j.get("url") or "",
            "posted_at": _iso_date(j.get("date")),
            "tags": [t for t in (j.get("tags") or []) if isinstance(t, str)][:12],
            "description": strip_html(j.get("description") or "")[:2000],
        })
    return out


# ---------------------------------------------------------------- Remotive ---
def fetch_remotive(session: Optional[requests.Session] = None) -> List[Dict]:
    jobs: List[Dict] = []
    for cat in config.REMOTIVE_CATEGORIES:
        try:
            r = polite_get(
                f"https://remotive.com/api/remote-jobs?category={cat}&limit={config.REMOTIVE_PAGE_LIMIT}",
                session,
            )
            jobs.extend(parse_remotive(r.json()))
        except Exception as e:
            print(f"[remotive:{cat}] error: {e}")
    seen, unique = set(), []
    for j in jobs:
        if j["source_key"] not in seen:
            seen.add(j["source_key"])
            unique.append(j)
    return unique


def parse_remotive(payload: Dict) -> List[Dict]:
    out = []
    for j in (payload or {}).get("jobs", []):
        if not j.get("title"):
            continue
        s_min, s_max, s_cur = parse_salary(j.get("salary") or "")
        out.append({
            "source": "remotive",
            "source_key": str(j.get("id")),
            "title": (j.get("title") or "").strip(),
            "company": (j.get("company_name") or "").strip(),
            "location": (j.get("candidate_required_location") or "").strip() or "Remote",
            "remote": True,
            "salary_min": s_min,
            "salary_max": s_max,
            "salary_currency": s_cur or "USD",
            "salary_text": (j.get("salary") or "").strip(),
            "url": j.get("url") or "",
            "posted_at": _iso_date(j.get("publication_date")),
            "tags": [t for t in (j.get("tags") or []) if isinstance(t, str)][:12],
            "description": strip_html(j.get("description") or "")[:2000],
        })
    return out


# --------------------------------------------------------------- Arbeitnow ---
def fetch_arbeitnow(session: Optional[requests.Session] = None) -> List[Dict]:
    jobs: List[Dict] = []
    for page in range(1, config.ARBEITNOW_MAX_PAGES + 1):
        try:
            r = polite_get(f"https://www.arbeitnow.com/api/job-board-api?page={page}", session)
            batch = parse_arbeitnow(r.json())
        except Exception as e:
            print(f"[arbeitnow:p{page}] error: {e}")
            break
        if not batch:
            break
        jobs.extend(batch)
    return jobs


def parse_arbeitnow(payload: Dict) -> List[Dict]:
    out = []
    for j in (payload or {}).get("data", []):
        if not j.get("title"):
            continue
        loc = j.get("location")
        if isinstance(loc, list):
            loc = ", ".join(x for x in loc if x)
        out.append({
            "source": "arbeitnow",
            "source_key": str(j.get("slug") or j.get("url")),
            "title": (j.get("title") or "").strip(),
            "company": (j.get("company_name") or "").strip(),
            "location": (loc or "").strip(),
            "remote": bool(j.get("remote")),
            "salary_min": None,
            "salary_max": None,
            "salary_currency": "USD",
            "salary_text": "",
            "url": j.get("url") or "",
            "posted_at": _iso_date(j.get("created_at")),
            "tags": [t for t in (j.get("tags") or []) if isinstance(t, str)][:12],
            "description": strip_html(j.get("description") or "")[:2000],
        })
    return out
