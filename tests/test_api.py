"""API integration tests — temp SQLite DB seeded ONLY from real recorded
fixtures (tests/fixtures/*.json). The hand-inserted duplicate pair used for
the dedupe test lives in the temp test DB and never touches production data.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from jobsapi import config, scrapers, store

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name)) as f:
        return json.load(f)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "RAPIDAPI_PROXY_SECRET", "")
    conn = store.connect(db)
    for job in scrapers.parse_remoteok(load("remoteok_sample.json")):
        store.upsert_job(conn, job)
    for job in scrapers.parse_remotive(load("remotive_sample.json")):
        store.upsert_job(conn, job)
    for job in scrapers.parse_arbeitnow(load("arbeitnow_sample.json")):
        store.upsert_job(conn, job)
    conn.close()
    from jobsapi.main import app
    return TestClient(app)


def test_root_and_health(client):
    assert client.get("/").status_code == 200
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["stored_jobs"] > 0


def test_search_returns_schema(client):
    r = client.get("/jobs", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0 and len(body["jobs"]) <= 5
    job = body["jobs"][0]
    for key in ("id", "source", "title", "company", "url", "posted_at",
                "salary_min", "salary_max", "salary_currency", "tags"):
        assert key in job


def test_search_keyword_filter(client):
    body = client.get("/jobs", params={"q": "python"}).json()
    assert body["total"] >= 1


def test_search_source_filter(client):
    body = client.get("/jobs", params={"source": "remotive", "limit": 100}).json()
    assert body["total"] > 0
    assert all(j["source"] == "remotive" for j in body["jobs"])


def test_search_min_salary_filter(client):
    body = client.get("/jobs", params={"min_salary": 100000, "limit": 100}).json()
    for j in body["jobs"]:
        best = j["salary_max"] if j["salary_max"] is not None else j["salary_min"]
        assert best is not None and best >= 100000


def test_search_posted_since_filter(client):
    body = client.get("/jobs", params={"posted_since": "2026-09-01", "limit": 100}).json()
    assert body["total"] > 0
    assert all(j["posted_at"] >= "2026-09-01" for j in body["jobs"])


def test_search_bad_params_rejected(client):
    assert client.get("/jobs", params={"source": "nope"}).status_code == 400
    assert client.get("/jobs", params={"sort": "nope"}).status_code == 400


def test_get_one_and_404(client):
    first_id = client.get("/jobs", params={"limit": 1}).json()["jobs"][0]["id"]
    assert client.get(f"/jobs/{first_id}").status_code == 200
    assert client.get("/jobs/999999999").status_code == 404


def test_dedupe_collapses_cross_board_copies(client, tmp_path, monkeypatch):
    # hand-insert the same posting under two sources (test DB only)
    base = dict(source="remoteok", source_key="dup-1", title="QA Engineer",
                company="Acme Corp", location="Remote", remote=True,
                salary_min=None, salary_max=None, salary_currency="USD",
                salary_text="", url="https://example.com/1",
                posted_at="2026-09-17", tags=[], description="")
    conn = store.connect(config.DB_PATH)
    store.upsert_job(conn, base)
    store.upsert_job(conn, {**base, "source": "remotive", "source_key": "dup-2",
                            "url": "https://example.com/2", "posted_at": "2026-09-18"})
    conn.close()

    deduped = client.get("/jobs", params={"q": "QA Engineer", "company": "Acme Corp"}).json()
    raw = client.get("/jobs", params={"q": "QA Engineer", "company": "Acme Corp",
                                      "dedupe": "false"}).json()
    assert raw["total"] == 2
    assert deduped["total"] == 1
    # earliest posted wins canonical status
    assert deduped["jobs"][0]["posted_at"] == "2026-09-17"


def test_stats(client):
    body = client.get("/stats").json()
    assert body["total_jobs"] > 0
    assert {s["source"] for s in body["sources"]} == {"remoteok", "remotive", "arbeitnow"}
    assert body["newest_posted_at"] >= body["oldest_posted_at"]


def test_proxy_secret_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "RAPIDAPI_PROXY_SECRET", "s3cr3t")
    assert client.get("/jobs").status_code == 403
    r = client.get("/jobs", headers={"X-RapidAPI-Proxy-Secret": "s3cr3t"})
    assert r.status_code == 200
    # health stays public
    assert client.get("/health").status_code == 200
