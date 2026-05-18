from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from breach_models import BreachLookupResult

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


class BreachClient:
    def __init__(
        self,
        *,
        endpoint: str = "https://www.wescan.live/api/breaches",
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 12.0,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def fetch(self, email: str) -> BreachLookupResult:
        query = urlencode({"email": email})
        request = Request(
            f"{self.endpoint}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return BreachLookupResult.unavailable(email, f"HTTP {error.code}")
        except URLError as error:
            reason = getattr(error, "reason", error)
            return BreachLookupResult.unavailable(email, f"Network error: {reason}")
        except (TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
            return BreachLookupResult.unavailable(email, str(error))

        if not isinstance(payload, dict):
            return BreachLookupResult.unavailable(email, "Invalid response payload")
        return BreachLookupResult.from_api_payload(email, payload)
