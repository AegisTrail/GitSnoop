from __future__ import annotations

from models import EmailRecord


def apply_email_filters(
    records: list[EmailRecord],
    *,
    exclude_github_noreply: bool,
) -> list[EmailRecord]:
    if not exclude_github_noreply:
        return list(records)

    return [record for record in records if not record.is_github_noreply]
