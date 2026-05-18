from __future__ import annotations

from collections.abc import Callable, Iterable

from breach_client import BreachClient
from breach_models import BreachLookupResult

ProgressCallback = Callable[[int, int], None]


class BreachLookupService:
    def __init__(self, client: BreachClient | None = None, *, batch_size: int = 25) -> None:
        self.client = client or BreachClient()
        self.batch_size = max(1, batch_size)

    def fetch_many(
        self,
        emails: Iterable[str],
        *,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, BreachLookupResult]:
        unique_emails = list(dict.fromkeys(email.strip() for email in emails if email.strip()))
        total = len(unique_emails)
        results: dict[str, BreachLookupResult] = {}

        for start in range(0, total, self.batch_size):
            batch = unique_emails[start : start + self.batch_size]
            for email in batch:
                results[email] = self.client.fetch(email)
            if on_progress is not None:
                on_progress(min(start + len(batch), total), total)

        return results
