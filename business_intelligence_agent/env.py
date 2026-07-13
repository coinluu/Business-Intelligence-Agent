from __future__ import annotations

import os
import shlex
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parts = shlex.split(value, posix=True)
        values[key.strip()] = parts[0] if parts else ""
    return values


def render_env(values: dict[str, str]) -> str:
    allowed = (
        "AI_API_KEY", "AI_MODEL", "AI_API_BASE", "OBSIDIAN_VAULT",
        "HTTP_PROXY", "HTTPS_PROXY",
    )
    lines = ["# Local secrets. Never commit this file."]
    for key in allowed:
        value = values.get(key, "")
        lines.append(f"{key}={shlex.quote(value)}")
    return "\n".join(lines) + "\n"


def apply_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value:
            os.environ[key] = value
