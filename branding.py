from __future__ import annotations

from functools import lru_cache
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
ASCII_DESIGN_PATH = MODULE_DIR / "asciiDesign.txt"
FALLBACK_ASCII_BANNER = """\
 ██████  ██ ████████ ███████ ███    ██  ██████   ██████  ██████
██       ██    ██    ██      ████   ██ ██    ██ ██    ██ ██   ██
██   ███ ██    ██    ███████ ██ ██  ██ ██    ██ ██    ██ ██████
██    ██ ██    ██         ██ ██  ██ ██ ██    ██ ██    ██ ██
 ██████  ██    ██    ███████ ██   ████  ██████   ██████  ██
"""


@lru_cache(maxsize=1)
def ascii_banner() -> str:
    try:
        banner = ASCII_DESIGN_PATH.read_text(encoding="utf-8").strip("\n")
    except OSError:
        banner = FALLBACK_ASCII_BANNER.strip("\n")
    return banner
