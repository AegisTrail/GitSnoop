from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from breach_models import BreachLookupResult
from breach_service import BreachLookupService
from filters import apply_email_filters
from git_client import GitRepositoryClient
from models import EmailRecord
from tui import sort_records

ProgressCallback = Callable[[str, dict[str, object] | None], None]


@dataclass(frozen=True, slots=True)
class ScanOptions:
    exclude_github_noreply: bool = False
    sort_mode: str = "commits"
    skip_breach_checks: bool = False


@dataclass(frozen=True, slots=True)
class ScanResult:
    repo_name: str
    repo_source: str
    records: list[EmailRecord]
    all_records: list[EmailRecord]
    breach_reports: dict[str, BreachLookupResult]


@dataclass(slots=True)
class ScanSession:
    result: ScanResult
    repo_path: Path
    _tempdir: tempfile.TemporaryDirectory[str] = field(repr=False)

    def __enter__(self) -> "ScanSession":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._tempdir.cleanup()


def extract_repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    return name.removesuffix(".git")


class RepositoryScanService:
    def __init__(self, breach_service: BreachLookupService | None = None) -> None:
        self.breach_service = breach_service or BreachLookupService()

    def scan(
        self,
        repo_source: str,
        *,
        options: ScanOptions,
    ) -> ScanResult:
        with self.scan_with_clone(repo_source, options=options) as session:
            return session.result

    def scan_with_clone(
        self,
        repo_source: str,
        *,
        options: ScanOptions,
        on_progress: ProgressCallback | None = None,
    ) -> ScanSession:
        repo_name = extract_repo_name(repo_source)
        tempdir = tempfile.TemporaryDirectory()
        repo_path = Path(tempdir.name) / repo_name
        try:
            client = GitRepositoryClient(repo_path)
            if on_progress is not None:
                on_progress("clone", {"message": f"Cloning {repo_name}..."})
            client.run("git", "clone", repo_source, str(repo_path), cwd=Path(tempdir.name))
            if on_progress is not None:
                on_progress("collect", {"message": "Reading commit history..."})
            all_records = client.collect_emails()

            breach_reports: dict[str, BreachLookupResult] = {}
            if not options.skip_breach_checks:
                if on_progress is not None:
                    on_progress(
                        "breach_start",
                        {
                            "message": "Checking for breaches...",
                            "current": 0,
                            "total": len(all_records),
                        },
                    )
                breach_reports = self.breach_service.fetch_many(
                    (record.email for record in all_records),
                    on_progress=(
                        None
                        if on_progress is None
                        else lambda current, total: on_progress(
                            "breach_progress",
                            {
                                "message": "Checking for breaches...",
                                "current": current,
                                "total": total,
                            },
                        )
                    ),
                )
            elif on_progress is not None:
                on_progress("breach_skip", {"message": "Breach checks skipped."})

            records = apply_email_filters(
                all_records,
                exclude_github_noreply=options.exclude_github_noreply,
            )
            records = sort_records(records, options.sort_mode)
            if on_progress is not None:
                on_progress(
                    "done",
                    {
                        "message": f"Loaded {len(all_records)} authors.",
                        "current": len(all_records),
                        "total": len(all_records),
                    },
                )
            return ScanSession(
                result=ScanResult(
                    repo_name=repo_name,
                    repo_source=repo_source,
                    records=records,
                    all_records=all_records,
                    breach_reports=breach_reports,
                ),
                repo_path=repo_path,
                _tempdir=tempdir,
            )
        except Exception:
            tempdir.cleanup()
            raise
