from __future__ import annotations

from fastapi import FastAPI, HTTPException

from api_models import HealthResponse, ScanRequest, ScanResponse
from exporter import serialize_email_records
from git_client import GitCommandError
from scan_service import RepositoryScanService, ScanOptions


class GitSnoopAPI:
    def __init__(self, scan_service: RepositoryScanService | None = None) -> None:
        self.scan_service = scan_service or RepositoryScanService()

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="GitSnoop API",
            version="2.0.0",
            summary="HTTP API for GitSnoop.",
            description=(
                "GitSnoop exposes the same repository email collection workflow used by the CLI "
                "through a FastAPI application."
            ),
        )

        @app.get("/health", response_model=HealthResponse, tags=["system"])
        def health() -> HealthResponse:
            return HealthResponse(status="ok", service="gitsnoop")

        @app.post("/scan", response_model=ScanResponse, tags=["scan"])
        def scan_repository(request: ScanRequest) -> ScanResponse:
            try:
                result = self.scan_service.scan(
                    request.repo,
                    options=ScanOptions(
                        exclude_github_noreply=request.exclude_github_noreply,
                        sort_mode=request.sort_mode,
                        skip_breach_checks=request.skip_breach_checks,
                    ),
                )
            except GitCommandError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

            payload = serialize_email_records(
                repository=result.repo_name,
                records=result.records,
                breach_reports=result.breach_reports,
                include_breach_details=request.include_breach_details,
            )
            return ScanResponse(
                repository=payload["repository"],
                repo_source=result.repo_source,
                count=payload["count"],
                breached_count=payload["breached_count"],
                results=payload["results"],
            )

        return app
