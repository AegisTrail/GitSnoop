from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# add more domains/emails from additional git providers to ignore
GITHUB_NOREPLY_DOMAIN = "users.noreply.github.com"


@dataclass(frozen=True, slots=True)
class EmailRecord:
    name: str
    email: str
    commit_count: int
    first_seen: date
    last_seen: date

    @property
    def is_github_noreply(self) -> bool:
        return self.email.lower().endswith(f"@{GITHUB_NOREPLY_DOMAIN}")

    @property
    def domain(self) -> str:
        parts = self.email.lower().rsplit("@", 1)
        return parts[1] if len(parts) == 2 else ""
