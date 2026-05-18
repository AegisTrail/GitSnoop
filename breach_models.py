from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BreachEntry:
    title: str
    domain: str
    breach_date: str
    pwn_count: int
    data_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreachLookupResult:
    email: str
    is_breached: bool | None
    breaches: tuple[BreachEntry, ...]
    error: str | None = None

    @classmethod
    def from_api_payload(cls, email: str, payload: dict[str, object]) -> "BreachLookupResult":
        raw_entries = payload.get("data")
        entries: list[BreachEntry] = []
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                entries.append(
                    BreachEntry(
                        title=str(item.get("Title") or item.get("Name") or "Unknown"),
                        domain=str(item.get("Domain") or ""),
                        breach_date=str(item.get("BreachDate") or "Unknown"),
                        pwn_count=_as_int(item.get("PwnCount")),
                        data_classes=_as_tuple(item.get("DataClasses")),
                    )
                )

        breached = payload.get("breached")
        return cls(
            email=email,
            is_breached=bool(breached) if isinstance(breached, bool) else None,
            breaches=tuple(entries),
        )

    @classmethod
    def unavailable(cls, email: str, error: str) -> "BreachLookupResult":
        return cls(email=email, is_breached=None, breaches=(), error=error)


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _as_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)
