"""Pydantic schemas — the public contract of the API."""
from typing import List, Optional
from pydantic import BaseModel, Field


class Job(BaseModel):
    id: int
    source: str = Field(examples=["remotive"])
    title: str
    company: str
    location: str = ""
    remote: bool = True
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    salary_text: str = ""
    url: str
    posted_at: str = ""
    tags: List[str] = []
    description: str = ""


class JobList(BaseModel):
    total: int
    limit: int
    offset: int
    deduped: bool
    jobs: List[Job]


class SourceStat(BaseModel):
    source: str
    jobs: int
    last_refresh: str = ""
    last_status: str = ""


class Stats(BaseModel):
    total_jobs: int
    sources: List[SourceStat]
    newest_posted_at: str = ""
    oldest_posted_at: str = ""
