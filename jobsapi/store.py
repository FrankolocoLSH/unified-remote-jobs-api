"""SQLite store: schema, upserts, dedupe resolution, and query layer.

Dedupe strategy: jobs are keyed (source, source_key). A second layer collapses
the *same posting* syndicated across boards: norm_key = normalized
(company + title). The earliest-posted row stays canonical; later copies get
duplicate_of set. Queries filter duplicates out by default (dedupe=true).
"""
import re
import sqlite3
import time
from typing import Dict, List, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_key TEXT NOT NULL,
    norm_key TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    remote INTEGER DEFAULT 1,
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT DEFAULT 'USD',
    salary_text TEXT DEFAULT '',
    url TEXT NOT NULL,
    posted_at TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    description TEXT DEFAULT '',
    fetched_at TEXT NOT NULL,
    duplicate_of INTEGER,
    UNIQUE(source, source_key)
);
CREATE INDEX IF NOT EXISTS idx_jobs_norm ON jobs(norm_key);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_at);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE TABLE IF NOT EXISTS refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    fetched INTEGER DEFAULT 0,
    upserted INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error TEXT DEFAULT ''
);
"""


def norm_key(company: str, title: str) -> str:
    def n(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())
    return f"{n(company)}|{n(title)}"


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, job: Dict) -> int:
    """Insert or update one normalized job dict. Returns row id."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    nk = norm_key(job.get("company", ""), job.get("title", ""))
    cur = conn.execute(
        """INSERT INTO jobs (source, source_key, norm_key, title, company, location, remote,
                             salary_min, salary_max, salary_currency, salary_text, url,
                             posted_at, tags, description, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source, source_key) DO UPDATE SET
             title=excluded.title, company=excluded.company, location=excluded.location,
             remote=excluded.remote, salary_min=excluded.salary_min, salary_max=excluded.salary_max,
             salary_currency=excluded.salary_currency, salary_text=excluded.salary_text,
             url=excluded.url, posted_at=excluded.posted_at, tags=excluded.tags,
             description=excluded.description, fetched_at=excluded.fetched_at,
             norm_key=excluded.norm_key""",
        (
            job["source"], job["source_key"], nk,
            job.get("title", ""), job.get("company", ""), job.get("location", ""),
            1 if job.get("remote", True) else 0,
            job.get("salary_min"), job.get("salary_max"),
            job.get("salary_currency", "USD"), job.get("salary_text", ""),
            job.get("url", ""), job.get("posted_at", ""),
            ",".join(job.get("tags", [])), (job.get("description", "") or "")[:2000],
            now,
        ),
    )
    row_id = cur.lastrowid
    if row_id == 0 or row_id is None:  # conflict path — look up existing id
        row = conn.execute(
            "SELECT id FROM jobs WHERE source=? AND source_key=?",
            (job["source"], job["source_key"]),
        ).fetchone()
        row_id = row["id"]
    _resolve_duplicate(conn, row_id, nk, job.get("posted_at", ""))
    conn.commit()
    return row_id


def _resolve_duplicate(conn: sqlite3.Connection, row_id: int, nk: str, posted_at: str) -> None:
    """Mark this row (or the older rival) as a cross-board duplicate."""
    rivals = conn.execute(
        "SELECT id, posted_at FROM jobs WHERE norm_key=? AND id!=? AND duplicate_of IS NULL",
        (nk, row_id),
    ).fetchall()
    for r in rivals:
        # earliest posted_at wins canonical status; empty dates sort last
        mine = posted_at or "9999"
        theirs = r["posted_at"] or "9999"
        if mine < theirs:
            conn.execute("UPDATE jobs SET duplicate_of=? WHERE id=?", (row_id, r["id"]))
        elif mine > theirs:
            conn.execute("UPDATE jobs SET duplicate_of=? WHERE id=?", (r["id"], row_id))
        # exact tie: keep the lower id as canonical
        elif row_id > r["id"]:
            conn.execute("UPDATE jobs SET duplicate_of=? WHERE id=?", (r["id"], row_id))
        else:
            conn.execute("UPDATE jobs SET duplicate_of=? WHERE id=?", (row_id, r["id"]))


def query_jobs(
    conn: sqlite3.Connection,
    q: str = "", company: str = "", location: str = "", remote_only: bool = False,
    min_salary: Optional[float] = None, posted_since: str = "", source: str = "",
    dedupe: bool = True, sort: str = "newest", limit: int = 20, offset: int = 0,
) -> Dict:
    where = ["1=1"]
    params: List = []
    if dedupe:
        where.append("duplicate_of IS NULL")
    if q:
        where.append("(title LIKE ? OR company LIKE ? OR description LIKE ? OR tags LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like, like]
    if company:
        where.append("company LIKE ?")
        params.append(f"%{company}%")
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location}%")
    if remote_only:
        where.append("remote = 1")
    if min_salary is not None:
        where.append("COALESCE(salary_max, salary_min, 0) >= ?")
        params.append(min_salary)
    if posted_since:
        where.append("posted_at >= ?")
        params.append(posted_since)
    if source:
        where.append("source = ?")
        params.append(source)

    clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) c FROM jobs WHERE {clause}", params).fetchone()["c"]

    order = {
        "newest": "posted_at DESC",
        "oldest": "posted_at ASC",
        "salary": "COALESCE(salary_max, salary_min, 0) DESC",
    }.get(sort, "posted_at DESC")

    rows = conn.execute(
        f"SELECT * FROM jobs WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return {"total": total, "jobs": [dict(r) for r in rows]}


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[Dict]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def stats(conn: sqlite3.Connection) -> Dict:
    sources = []
    for src in ("remoteok", "remotive", "arbeitnow"):
        n = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE source=? AND duplicate_of IS NULL", (src,)
        ).fetchone()["c"]
        log = conn.execute(
            "SELECT finished_at, status FROM refresh_log WHERE source=? ORDER BY id DESC LIMIT 1",
            (src,),
        ).fetchone()
        sources.append({
            "source": src,
            "jobs": n,
            "last_refresh": (log["finished_at"] if log else "") or "",
            "last_status": (log["status"] if log else "") or "",
        })
    total = conn.execute("SELECT COUNT(*) c FROM jobs WHERE duplicate_of IS NULL").fetchone()["c"]
    newest = conn.execute(
        "SELECT MAX(posted_at) m FROM jobs WHERE duplicate_of IS NULL").fetchone()["m"] or ""
    oldest = conn.execute(
        "SELECT MIN(posted_at) m FROM jobs WHERE duplicate_of IS NULL AND posted_at != ''"
    ).fetchone()["m"] or ""
    return {"total_jobs": total, "sources": sources,
            "newest_posted_at": newest, "oldest_posted_at": oldest}


def log_refresh_start(conn: sqlite3.Connection, source: str) -> int:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cur = conn.execute(
        "INSERT INTO refresh_log (source, started_at, status) VALUES (?,?, 'running')",
        (source, now),
    )
    conn.commit()
    return cur.lastrowid


def log_refresh_end(conn: sqlite3.Connection, log_id: int, fetched: int,
                    upserted: int, status: str = "ok", error: str = "") -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "UPDATE refresh_log SET finished_at=?, fetched=?, upserted=?, status=?, error=? WHERE id=?",
        (now, fetched, upserted, status, error[:500], log_id),
    )
    conn.commit()
