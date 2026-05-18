from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BreachEntryResponse(BaseModel):
    title: str
    domain: str
    breach_date: str
    pwn_count: int
    data_classes: list[str]


class EmailRecordResponse(BaseModel):
    name: str
    email: str
    domain: str
    commit_count: int
    first_seen: str
    last_seen: str
    is_breached: bool | None = None
    breach_count: int | None = None
    breach_error: str | None = None
    breaches: list[BreachEntryResponse] | None = None


class ScanRequest(BaseModel):
    repo: str = Field(..., description="Git repository URL or local filesystem path.")
    exclude_github_noreply: bool = Field(
        default=False,
        description="Exclude *@users.noreply.github.com addresses from the response.",
    )
    sort_mode: Literal["commits", "recent", "name", "email", "domain"] = Field(
        default="commits",
        description="Sort order for the returned records.",
    )
    skip_breach_checks: bool = Field(
        default=False,
        description="Skip breach lookups and return email records without breach status.",
    )
    include_breach_details: bool = Field(
        default=True,
        description="Include breach flags and per-breach metadata in the response.",
    )


class ScanResponse(BaseModel):
    repository: str
    repo_source: str
    count: int
    breached_count: int
    results: list[EmailRecordResponse]


class HealthResponse(BaseModel):
    status: str
    service: str
