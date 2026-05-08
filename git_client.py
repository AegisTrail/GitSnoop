from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

from models import EmailRecord

EMAIL_REGEX = re.compile(r"(.+?)\s*<(.+?)>")
class GitCommandError(RuntimeError):
    """Raised when a git command fails."""


class GitRepositoryClient:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def run(self, *cmd: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            cmd,
            cwd=cwd or self.repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or "Unknown git error"
            raise GitCommandError(stderr)
        return result.stdout

    def run_optional(self, *cmd: str, cwd: Path | None = None) -> str | None:
        try:
            return self.run(*cmd, cwd=cwd).strip()
        except GitCommandError:
            return None

    def collect_emails(self) -> list[EmailRecord]:
        output = self.run("git", "log", "--format=%an%x1f%ae%x1f%ad", "--date=short")
        aggregated: dict[tuple[str, str], dict[str, object]] = defaultdict(dict)

        for line in output.splitlines():
            parts = [part.strip() for part in line.split("\x1f")]
            if len(parts) != 3:
                continue

            name, email, commit_day = parts
            if not EMAIL_REGEX.match(f"{name} <{email}>"):
                continue

            key = (name, email)
            seen_day = date.fromisoformat(commit_day)
            current = aggregated.get(key)
            if not current:
                aggregated[key] = {
                    "name": name,
                    "email": email,
                    "commit_count": 1,
                    "first_seen": seen_day,
                    "last_seen": seen_day,
                }
                continue

            current["commit_count"] = int(current["commit_count"]) + 1
            current["first_seen"] = min(current["first_seen"], seen_day)
            current["last_seen"] = max(current["last_seen"], seen_day)

        records = [
            EmailRecord(
                name=data["name"],
                email=data["email"],
                commit_count=int(data["commit_count"]),
                first_seen=data["first_seen"],
                last_seen=data["last_seen"],
            )
            for data in aggregated.values()
        ]
        records.sort(key=lambda record: (-record.commit_count, record.name.lower(), record.email.lower()))
        return records

    def commits_by_author(self, email: str) -> list[str]:
        output = self.run(
            "git",
            "log",
            "--pretty=format:%h | %ad | %s",
            "--date=short",
            f"--author={email}",
        )
        return output.splitlines()
