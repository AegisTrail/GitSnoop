from __future__ import annotations

import json
from pathlib import Path

from models import EmailRecord


def export_email_records(
    output_path: Path,
    *,
    repository: str,
    records: list[EmailRecord],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repository": repository,
        "count": len(records),
        "results": [
            {
                "name": record.name,
                "email": record.email,
                "domain": record.domain,
                "commit_count": record.commit_count,
                "first_seen": record.first_seen.isoformat(),
                "last_seen": record.last_seen.isoformat(),
            }
            for record in records
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_selected_records(output_path: Path, records: list[EmailRecord]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "name": record.name,
            "email": record.email,
            "domain": record.domain,
            "commit_count": record.commit_count,
            "first_seen": record.first_seen.isoformat(),
            "last_seen": record.last_seen.isoformat(),
        }
        for record in records
    ]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
