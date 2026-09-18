"""Parser unit tests — all inputs are REAL recorded API responses
(tests/fixtures/*.json, captured live 2026-09-18). No invented payload data.
"""
import json
import os

import pytest

from jobsapi import scrapers

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name)) as f:
        return json.load(f)


# ------------------------------------------------------------- RemoteOK ---
def test_parse_remoteok_skips_legal_notice_and_normalizes():
    jobs = scrapers.parse_remoteok(load("remoteok_sample.json"))
    assert len(jobs) >= 5
    for j in jobs:
        assert j["source"] == "remoteok"
        assert j["title"] and j["company"] and j["url"] and j["source_key"]
        assert j["posted_at"]  # YYYY-MM-DD
        assert j["remote"] is True
    # spot-check the real first job in the fixture
    first = jobs[0]
    assert first["title"] == "Sr Solutions Architect"
    assert first["company"] == "ExtraHop"
    assert first["url"].startswith("https://")


def test_parse_remoteok_zero_salary_becomes_none():
    jobs = scrapers.parse_remoteok(load("remoteok_sample.json"))
    # fixture: five jobs carry salary_min/max = 0 (unknown) -> None ...
    unknowns = [j for j in jobs if j["salary_min"] is None]
    assert len(unknowns) == 5
    # ... while the one real salary in the fixture is preserved exactly
    known = [j for j in jobs if j["salary_min"] is not None][0]
    assert (known["salary_min"], known["salary_max"]) == (190000, 220000)


# ------------------------------------------------------------- Remotive ---
def test_parse_remotive_normalizes():
    jobs = scrapers.parse_remotive(load("remotive_sample.json"))
    assert len(jobs) >= 5
    for j in jobs:
        assert j["source"] == "remotive"
        assert j["title"] and j["company"] and j["url"]
        assert j["posted_at"]
    first = jobs[0]
    assert first["title"] == "Senior Data Scientist"
    assert first["company"] == "Lemon.io"


def test_remotive_real_salary_strings_parse():
    payload = load("remotive_sample.json")
    salary_texts = [j.get("salary") for j in payload["jobs"] if j.get("salary")]
    assert salary_texts, "fixture should contain at least one real salary string"
    for text in salary_texts:
        lo, hi, cur = scrapers.parse_salary(text)
        assert lo is not None and hi is not None and lo <= hi
        assert 1_000 <= lo <= 5_000_000


def test_parse_salary_patterns():
    assert scrapers.parse_salary("$80k - $120k") == (80000.0, 120000.0, "USD")
    assert scrapers.parse_salary("€50,000 - €70,000") == (50000.0, 70000.0, "EUR")
    assert scrapers.parse_salary("$95k") == (95000.0, 95000.0, "USD")
    # hourly rates are annualized at 2080 hrs/yr (disclosed normalization)
    assert scrapers.parse_salary("$90 - $150 /hour") == (187200.0, 312000.0, "USD")
    # European decimal comma
    assert scrapers.parse_salary("$31,2k- $52k") == (31200.0, 52000.0, "USD")
    assert scrapers.parse_salary("") == (None, None, "")
    assert scrapers.parse_salary("competitive") == (None, None, "")


# ------------------------------------------------------------ Arbeitnow ---
def test_parse_arbeitnow_normalizes():
    jobs = scrapers.parse_arbeitnow(load("arbeitnow_sample.json"))
    assert len(jobs) == 5
    for j in jobs:
        assert j["source"] == "arbeitnow"
        assert j["title"] and j["company"] and j["url"]
        assert j["posted_at"]  # epoch -> YYYY-MM-DD
        assert isinstance(j["remote"], bool)
    assert jobs[0]["company"] == "Webmatch GmbH"


# ----------------------------------------------------------------- utils ---
def test_iso_date_handles_formats():
    assert scrapers._iso_date("2026-09-15T00:00:26+00:00") == "2026-09-15"
    assert scrapers._iso_date("2026-09-16T12:35:28") == "2026-09-16"
    assert scrapers._iso_date(1789754466) == "2026-09-18"
    assert scrapers._iso_date("") == ""
    assert scrapers._iso_date(None) == ""


def test_strip_html():
    assert scrapers.strip_html("<p>Hello <b>world</b></p>") == "Hello world"
