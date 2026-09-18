"""Central configuration — everything overridable via environment variables.

No secrets are hard-coded. The only optional secret is RAPIDAPI_PROXY_SECRET,
set at deploy time (Render/Railway env vars), never committed.
"""
import os

DB_PATH = os.environ.get("JOBS_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobs.db"))

# Optional hardening: when set, every API route (except /, /health, /docs, /openapi.json)
# requires header X-RapidAPI-Proxy-Secret to match. Configure the same value in the
# RapidAPI dashboard ("API Settings" -> proxy secret) so only RapidAPI traffic is served.
RAPIDAPI_PROXY_SECRET = os.environ.get("RAPIDAPI_PROXY_SECRET", "")

# Polite-scraping knobs
MIN_REQUEST_INTERVAL_S = float(os.environ.get("MIN_REQUEST_INTERVAL_S", "2.0"))
REQUEST_TIMEOUT_S = int(os.environ.get("REQUEST_TIMEOUT_S", "25"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

REMOTEOK_TAGS = [
    "python", "javascript", "typescript", "react", "node", "golang", "rust",
    "devops", "data", "ai", "design", "product", "marketing", "sales",
    "support", "security", "mobile", "backend", "frontend", "full-stack",
]

REMOTIVE_CATEGORIES = [
    "software-dev", "data", "devops", "design", "marketing",
    "sales", "customer-support", "product", "qa", "all-others",
]
REMOTIVE_PAGE_LIMIT = 50

ARBEITNOW_MAX_PAGES = 15
