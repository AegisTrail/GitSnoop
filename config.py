from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "gitsnoop" / "config.json"
DEFAULT_OUTPUT_DIR = Path.home() / ".config" / "gitsnoop" / "output"
DEFAULT_OUTPUT_DIR_TEXT = "~/.config/gitsnoop/output"

@dataclass(frozen=True, slots=True)
class AppConfig:
    exclude_github_noreply: bool = False
    sort_mode: str = "commits"
    compact_help: bool = False
    output_dir: Path = DEFAULT_OUTPUT_DIR


def _default_config_payload() -> dict[str, object]:
    return {
        "exclude_github_noreply": False,
        "sort_mode": "commits",
        "compact_help": False,
        "output_dir": DEFAULT_OUTPUT_DIR_TEXT,
    }


def _ensure_default_config(path: Path) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_default_config_payload(), indent=2), encoding="utf-8")


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    if config_path is None:
        _ensure_default_config(path)

    if not path.exists():
        return AppConfig()

    data = json.loads(path.read_text(encoding="utf-8"))
    output_dir = Path(str(data.get("output_dir", DEFAULT_OUTPUT_DIR_TEXT))).expanduser()

    return AppConfig(
        exclude_github_noreply=bool(data.get("exclude_github_noreply", False)),
        sort_mode=str(data.get("sort_mode", "commits")),
        compact_help=bool(data.get("compact_help", False)),
        output_dir=output_dir,
    )
