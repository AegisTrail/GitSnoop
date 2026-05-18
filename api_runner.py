from __future__ import annotations

import uvicorn

from api_app import GitSnoopAPI

DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 6969


class APIServerRunner:
    def __init__(
        self,
        *,
        host: str = DEFAULT_API_HOST,
        port: int = DEFAULT_API_PORT,
    ) -> None:
        self.host = host
        self.port = port

    def run(self) -> None:
        app = GitSnoopAPI().create_app()
        uvicorn.run(app, host=self.host, port=self.port)
