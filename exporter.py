from __future__ import annotations

import json
from pathlib import Path

from breach_models import BreachLookupResult
from models import EmailRecord


def serialize_email_records(
    *,
    repository: str,
    records: list[EmailRecord],
    breach_reports: dict[str, BreachLookupResult] | None = None,
    include_breach_details: bool = True,
) -> dict[str, object]:
    breach_reports = breach_reports or {}
    return {
        "repository": repository,
        "count": len(records),
        "breached_count": sum(
            1
            for record in records
            if (breach_reports.get(record.email) and breach_reports[record.email].is_breached)
        )
        if include_breach_details
        else 0,
        "results": [
            _serialize_record(
                record,
                breach_reports=breach_reports,
                include_breach_details=include_breach_details,
            )
            for record in records
        ],
    }


def export_email_records(
    output_path: Path,
    *,
    repository: str,
    records: list[EmailRecord],
    breach_reports: dict[str, BreachLookupResult] | None = None,
    include_breach_details: bool = True,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_email_records(
        repository=repository,
        records=records,
        breach_reports=breach_reports,
        include_breach_details=include_breach_details,
    )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_selected_records(
    output_path: Path,
    *,
    repository: str,
    records: list[EmailRecord],
    breach_reports: dict[str, BreachLookupResult] | None = None,
    include_breach_details: bool = True,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_email_records(
        repository=repository,
        records=records,
        breach_reports=breach_reports,
        include_breach_details=include_breach_details,
    )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _serialize_record(
    record: EmailRecord,
    *,
    breach_reports: dict[str, BreachLookupResult],
    include_breach_details: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": record.name,
        "email": record.email,
        "domain": record.domain,
        "commit_count": record.commit_count,
        "first_seen": record.first_seen.isoformat(),
        "last_seen": record.last_seen.isoformat(),
    }
    if not include_breach_details:
        return payload

    breach_result = breach_reports.get(record.email)
    payload["is_breached"] = breach_result.is_breached if breach_result else None
    payload["breach_count"] = len(breach_result.breaches) if breach_result else 0
    payload["breach_error"] = breach_result.error if breach_result else None
    payload["breaches"] = (
        [
            {
                "title": breach.title,
                "domain": breach.domain,
                "breach_date": breach.breach_date,
                "pwn_count": breach.pwn_count,
                "data_classes": list(breach.data_classes),
            }
            for breach in breach_result.breaches
        ]
        if breach_result
        else []
    )
    return payload
