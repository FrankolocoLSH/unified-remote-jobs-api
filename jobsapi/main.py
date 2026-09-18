"""Unified Remote Jobs API — FastAPI service.

Reads exclusively from the local SQLite store (populated by `refresh.py` on a
cron), so responses are fast and never blocked on upstream job boards.
"""
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config, schemas, store

app = FastAPI(
    title="Unified Remote Jobs API",
    description=(
        "One normalized search endpoint across RemoteOK, Remotive, and Arbeitnow: "
        "keyword search, location / remote-only / salary / recency filters, "
        "cross-board dedupe, and normalized salary fields. "
        "Data refreshed on a schedule; all responses served from cache."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    conn = store.connect()
    try:
        yield conn
    finally:
        conn.close()


def check_proxy_secret(x_rapidapi_proxy_secret: Optional[str] = Header(default=None)):
    """Optional hardening: only serve traffic carrying the RapidAPI proxy secret."""
    expected = config.RAPIDAPI_PROXY_SECRET
    if expected and x_rapidapi_proxy_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _to_job(row: dict) -> schemas.Job:
    tags = [t for t in (row.get("tags") or "").split(",") if t]
    return schemas.Job(
        id=row["id"], source=row["source"], title=row["title"], company=row["company"],
        location=row.get("location") or "", remote=bool(row.get("remote")),
        salary_min=row.get("salary_min"), salary_max=row.get("salary_max"),
        salary_currency=row.get("salary_currency") or "USD",
        salary_text=row.get("salary_text") or "", url=row.get("url") or "",
        posted_at=row.get("posted_at") or "", tags=tags,
        description=row.get("description") or "",
    )


@app.get("/", summary="API info")
def root():
    return {
        "name": "Unified Remote Jobs API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/jobs", "/jobs/{id}", "/stats", "/health"],
    }


@app.get("/health", summary="Health check")
def health(conn=Depends(get_conn)):
    n = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    return {"status": "ok", "stored_jobs": n}


@app.get(
    "/jobs",
    response_model=schemas.JobList,
    summary="Search remote jobs",
    dependencies=[Depends(check_proxy_secret)],
)
def search_jobs(
    q: str = Query("", description="Keyword search across title, company, description, tags"),
    company: str = Query("", description="Filter by company name (partial match)"),
    location: str = Query("", description="Filter by location text, e.g. 'Europe', 'LATAM'"),
    remote_only: bool = Query(False, description="Only fully-remote postings"),
    min_salary: Optional[float] = Query(
        None,
        description="Minimum annual salary (hourly rates are annualized at 2080 hrs/yr; raw text kept in salary_text)",
    ),
    posted_since: str = Query("", description="Only jobs posted on/after YYYY-MM-DD"),
    source: str = Query("", description="Restrict to one board: remoteok, remotive, arbeitnow"),
    dedupe: bool = Query(True, description="Collapse the same posting syndicated across boards"),
    sort: str = Query("newest", description="newest | oldest | salary"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    if source and source not in ("remoteok", "remotive", "arbeitnow"):
        raise HTTPException(status_code=400, detail="source must be remoteok, remotive, or arbeitnow")
    if sort not in ("newest", "oldest", "salary"):
        raise HTTPException(status_code=400, detail="sort must be newest, oldest, or salary")
    res = store.query_jobs(
        conn, q=q, company=company, location=location, remote_only=remote_only,
        min_salary=min_salary, posted_since=posted_since, source=source,
        dedupe=dedupe, sort=sort, limit=limit, offset=offset,
    )
    return schemas.JobList(
        total=res["total"], limit=limit, offset=offset, deduped=dedupe,
        jobs=[_to_job(r) for r in res["jobs"]],
    )


@app.get(
    "/jobs/{job_id}",
    response_model=schemas.Job,
    summary="Get one job by id",
    dependencies=[Depends(check_proxy_secret)],
)
def get_job(job_id: int, conn=Depends(get_conn)):
    row = store.get_job(conn, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return _to_job(row)


@app.get(
    "/stats",
    response_model=schemas.Stats,
    summary="Corpus stats and source health",
    dependencies=[Depends(check_proxy_secret)],
)
def get_stats(conn=Depends(get_conn)):
    s = store.stats(conn)
    return schemas.Stats(
        total_jobs=s["total_jobs"],
        sources=[schemas.SourceStat(**x) for x in s["sources"]],
        newest_posted_at=s["newest_posted_at"],
        oldest_posted_at=s["oldest_posted_at"],
    )
