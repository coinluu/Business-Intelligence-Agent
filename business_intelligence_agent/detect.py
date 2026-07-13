from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
from pathlib import Path
from typing import Any


def _obsidian_config_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/obsidian/obsidian.json"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "obsidian/obsidian.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obsidian/obsidian.json"


def discover_obsidian_vaults() -> list[str]:
    paths: set[Path] = set()
    config = _obsidian_config_path()
    if config.exists():
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
            for item in payload.get("vaults", {}).values():
                raw = item.get("path") if isinstance(item, dict) else None
                if raw:
                    paths.add(Path(raw).expanduser())
        except (OSError, json.JSONDecodeError):
            pass

    common_roots = [Path.home() / "Documents", Path.home() / "Obsidian"]
    for root in common_roots:
        if not root.is_dir():
            continue
        try:
            for marker in root.glob("*/.obsidian"):
                paths.add(marker.parent)
        except OSError:
            continue
    return sorted(str(path.resolve()) for path in paths if (path / ".obsidian").is_dir())


def network_reachable(host: str = "github.com", port: int = 443) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def detect_environment() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": sys.version.split()[0],
        "tools": {name: shutil.which(name) for name in ("git", "uv", "python", "python3")},
        "network": {"github_https": network_reachable()},
        "proxy": {
            key: bool(os.environ.get(key))
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy")
        },
        "timezone": str(__import__("datetime").datetime.now().astimezone().tzinfo),
        "obsidian_vaults": discover_obsidian_vaults(),
    }
