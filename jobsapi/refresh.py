"""Cron refresh script: pull all sources, normalize, upsert into SQLite.

Designed to run unattended on a schedule. Example crontab (every 6 hours):

    0 */6 * * * cd /opt/jobsapi && /opt/jobsapi/.venv/bin/python -m jobsapi.refresh >> /var/log/jobsapi-refresh.log 2>&1

A full refresh takes a few minutes (polite per-host rate limiting). The API
itself only ever reads SQLite, so it stays fast even when sources are slow.
Exit code 0 = all sources ok, 1 = one or more sources failed (details logged).
"""
import sys
import traceback

from . import config, scrapers, store

FETCHERS = [
    ("remoteok", scrapers.fetch_remoteok),
    ("remotive", scrapers.fetch_remotive),
    ("arbeitnow", scrapers.fetch_arbeitnow),
]


def main(db_path: str = None) -> int:
    conn = store.connect(db_path or config.DB_PATH)
    failures = 0
    totals = {}
    for source, fetch in FETCHERS:
        log_id = store.log_refresh_start(conn, source)
        try:
            jobs = fetch()
            upserted = 0
            for job in jobs:
                store.upsert_job(conn, job)
                upserted += 1
            store.log_refresh_end(conn, log_id, fetched=len(jobs), upserted=upserted)
            totals[source] = upserted
            print(f"[{source}] fetched={len(jobs)} upserted={upserted}")
        except Exception as e:
            failures += 1
            store.log_refresh_end(conn, log_id, fetched=0, upserted=0,
                                  status="error", error=str(e))
            print(f"[{source}] FAILED: {e}")
            traceback.print_exc()
    conn.close()
    print(f"done: {totals} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(db))
