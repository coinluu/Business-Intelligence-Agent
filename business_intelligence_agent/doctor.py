from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from trendradar.ai.client import AIClient

from .compiler import compile_runtime
from .detect import detect_environment, discover_obsidian_vaults
from .env import load_env
from .profile import ProfileError, load_profile
from .scheduler import status as scheduler_status


def _check(results: list[dict[str, str]], ok: bool, item: str, detail: str, warning: bool = False) -> None:
    status = "pass" if ok else ("warn" if warning else "fail")
    results.append({"status": status, "item": item, "detail": detail})


def run_doctor(project: Path, live_api: bool = False) -> dict[str, Any]:
    results: list[dict[str, str]] = []
    environment = detect_environment()
    _check(results, platform.system() == "Darwin", "operating_system", platform.system() if platform.system() == "Darwin" else "unsupported; macOS required")
    _check(results, bool(environment["tools"]["uv"]), "uv", environment["tools"]["uv"] or "not found")
    _check(results, bool(environment["network"]["github_https"]), "network", "HTTPS reachable" if environment["network"]["github_https"] else "HTTPS check failed", warning=True)

    profile = None
    try:
        profile = load_profile(project / "user-profile.yaml")
        _check(results, True, "profile", "valid")
        compiled = compile_runtime(project, profile)
        _check(results, all(path.exists() for path in compiled.values()), "runtime_config", "compiled")
    except (ProfileError, ValueError, OSError) as error:
        _check(results, False, "profile", str(error))

    env_path = project / ".env.local"
    secrets = load_env(env_path)
    _check(results, bool(secrets.get("AI_API_KEY")), "model_secret", "configured" if secrets.get("AI_API_KEY") else "AI_API_KEY missing")
    if env_path.exists() and os.name != "nt":
        permissions = stat.S_IMODE(env_path.stat().st_mode)
        _check(results, permissions & 0o077 == 0, "secret_permissions", oct(permissions))
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env.local"], cwd=project, check=False
    ).returncode == 0
    _check(results, ignored, "secret_gitignore", ".env.local is ignored" if ignored else ".env.local is not ignored")

    vault_raw = secrets.get("OBSIDIAN_VAULT", "")
    if vault_raw:
        vault = Path(vault_raw).expanduser()
        valid_vault = (vault / ".obsidian").is_dir()
        _check(results, valid_vault, "obsidian_vault", str(vault))
        if valid_vault:
            created: list[Path] = []
            try:
                folder = profile["delivery"]["folder"] if profile else "Business Intelligence"
                target = vault / folder
                cursor = target
                while not cursor.exists() and cursor != vault:
                    created.append(cursor)
                    cursor = cursor.parent
                target.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", dir=target, prefix=".bia-probe-", delete=True) as probe:
                    probe.write("ok")
                    probe.flush()
                    os.fsync(probe.fileno())
                _check(results, True, "obsidian_write", str(target))
            except OSError as error:
                _check(results, False, "obsidian_write", str(error))
            finally:
                for directory in created:
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
    else:
        found = discover_obsidian_vaults()
        _check(results, False, "obsidian_vault", f"not configured; discovered {len(found)}", warning=bool(found))

    if live_api and profile and secrets.get("AI_API_KEY"):
        try:
            client = AIClient({
                "MODEL": profile["model"]["model"],
                "API_KEY": secrets["AI_API_KEY"],
                "API_BASE": profile["model"].get("api_base", ""),
                "TIMEOUT": 30,
                "NUM_RETRIES": 0,
            })
            response = client.chat([{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=8)
            _check(results, "OK" in response.upper(), "model_live", "request succeeded")
        except Exception as error:
            _check(results, False, "model_live", type(error).__name__)

    schedule = scheduler_status()
    _check(results, bool(schedule["installed"]), "scheduler", "installed" if schedule["installed"] else "not installed", warning=True)
    failures = sum(item["status"] == "fail" for item in results)
    warnings = sum(item["status"] == "warn" for item in results)
    return {"ok": failures == 0, "summary": {"fail": failures, "warn": warnings, "pass": len(results) - failures - warnings}, "checks": results}
