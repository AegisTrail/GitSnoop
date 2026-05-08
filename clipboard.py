from __future__ import annotations

import shutil
import subprocess


class ClipboardError(RuntimeError):
    """Raised when no clipboard backend is available."""


def copy_text(text: str) -> None:
    commands = (
        ("pbcopy",),
        ("wl-copy",),
        ("xclip", "-selection", "clipboard"),
        ("xsel", "--clipboard", "--input"),
    )

    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text, text=True, check=True)
            return
        except subprocess.CalledProcessError as error:
            raise ClipboardError(f"Clipboard command failed: {command[0]}") from error

    raise ClipboardError(
        "No clipboard utility found. Install pbcopy, wl-copy, xclip, or xsel."
    )
