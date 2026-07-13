from __future__ import annotations

import argparse
import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .compiler import compile_runtime
from .detect import detect_environment, discover_obsidian_vaults
from .doctor import run_doctor
from .env import load_env, render_env
from .files import atomic_write, backup
from .profile import ProfileError, load_profile, validate_profile
from .runtime import project_root, run_pipeline, scheduled_tick
from . import scheduler


def _print(payload: object, as_json: bool = False) -> None:
    if as_json or isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


def _save_profile(project: Path, source: Path) -> Path | None:
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProfileError("Profile must be a YAML object")
    validate_profile(data)
    target = project / "user-profile.yaml"
    previous = backup(target)
    atomic_write(target, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    try:
        compile_runtime(project, load_profile(target))
    except Exception:
        if previous:
            shutil.copy2(previous, target)
        else:
            target.unlink(missing_ok=True)
        raise
    return previous


def command_init(args: argparse.Namespace) -> int:
    project = project_root()
    target = project / "user-profile.yaml"
    if not target.exists():
        shutil.copy2(project / "user-profile.example.yaml", target)
    vaults = discover_obsidian_vaults()
    env_values = load_env(project / ".env.local")
    if len(vaults) == 1 and not env_values.get("OBSIDIAN_VAULT"):
        env_values["OBSIDIAN_VAULT"] = vaults[0]
    if args.api_key_stdin:
        if sys.stdin.isatty():
            env_values["AI_API_KEY"] = getpass.getpass("API key: ")
        else:
            env_values["AI_API_KEY"] = sys.stdin.read().strip()
    profile = load_profile(target)
    env_values["AI_MODEL"] = profile["model"]["model"]
    env_values["AI_API_BASE"] = profile["model"].get("api_base", "")
    atomic_write(project / ".env.local", render_env(env_values), mode=0o600)
    compile_runtime(project, profile)
    needs = []
    if not env_values.get("AI_API_KEY"):
        needs.append("model_api_key")
    if not env_values.get("OBSIDIAN_VAULT"):
        needs.append("obsidian_vault_selection" if len(vaults) > 1 else "obsidian_vault_path")
    _print({"ok": not needs, "profile": str(target), "discovered_vaults": vaults, "needs_input": needs})
    return 0 if not needs else 2


def command_configure(args: argparse.Namespace) -> int:
    project = project_root()
    previous = _save_profile(project, Path(args.profile_file))
    if args.api_key_stdin:
        values = load_env(project / ".env.local")
        values["AI_API_KEY"] = getpass.getpass("API key: ") if sys.stdin.isatty() else sys.stdin.read().strip()
        profile = load_profile(project / "user-profile.yaml")
        values["AI_MODEL"] = profile["model"]["model"]
        values["AI_API_BASE"] = profile["model"].get("api_base", "")
        atomic_write(project / ".env.local", render_env(values), mode=0o600)
    _print({"ok": True, "backup": str(previous) if previous else None})
    return 0


def command_set_vault(args: argparse.Namespace) -> int:
    project = project_root()
    vault = Path(args.path).expanduser().resolve()
    if not (vault / ".obsidian").is_dir():
        raise ProfileError(f"Not an initialized Obsidian vault: {vault}")
    values = load_env(project / ".env.local")
    values["OBSIDIAN_VAULT"] = str(vault)
    profile = load_profile(project / "user-profile.yaml")
    values["AI_MODEL"] = profile["model"]["model"]
    values["AI_API_BASE"] = profile["model"].get("api_base", "")
    atomic_write(project / ".env.local", render_env(values), mode=0o600)
    _print({"ok": True, "vault": str(vault)})
    return 0


def command_status(_: argparse.Namespace) -> int:
    project = project_root()
    success = project / ".state/last-success.json"
    failure = project / ".state/last-failure.json"
    last = json.loads(success.read_text(encoding="utf-8")) if success.exists() else None
    last_failure = json.loads(failure.read_text(encoding="utf-8")) if failure.exists() else None
    _print({"scheduler": scheduler.status(), "last_success": last, "last_failure": last_failure})
    return 0


def command_update(_: argparse.Namespace) -> int:
    project = project_root()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=project, text=True, stdout=subprocess.PIPE, check=True,
    ).stdout.strip()
    if dirty:
        raise RuntimeError("Tracked files have local changes; update refused to prevent data loss")
    subprocess.run(["git", "pull", "--ff-only"], cwd=project, check=True)
    subprocess.run(["uv", "sync", "--frozen"], cwd=project, check=True)
    compile_runtime(project, load_profile(project / "user-profile.yaml"))
    _print({"ok": True, "updated": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bia", description="Business Intelligence Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    detect = sub.add_parser("detect", help="detect environment and Obsidian vaults")
    detect.set_defaults(func=lambda args: (_print(detect_environment(), True), 0)[1])

    init = sub.add_parser("init", help="initialize local profile and secrets")
    init.add_argument("--api-key-stdin", action="store_true")
    init.set_defaults(func=command_init)

    configure = sub.add_parser("configure", help="validate and atomically apply a profile")
    configure.add_argument("--profile-file", required=True)
    configure.add_argument("--api-key-stdin", action="store_true")
    configure.set_defaults(func=command_configure)

    vault = sub.add_parser("set-vault", help="set a verified Obsidian vault")
    vault.add_argument("path")
    vault.set_defaults(func=command_set_vault)

    validate = sub.add_parser("validate", help="validate and compile current profile")
    validate.set_defaults(func=lambda args: (_print({"ok": True, "runtime": {key: str(value) for key, value in compile_runtime(project_root(), load_profile(project_root() / 'user-profile.yaml')).items()}}), 0)[1])

    doctor = sub.add_parser("doctor", help="check installation readiness")
    doctor.add_argument("--live-api", action="store_true")
    doctor.set_defaults(func=lambda args: (_print(result := run_doctor(project_root(), args.live_api), True), 0 if result["ok"] else 1)[1])

    run = sub.add_parser("run", help="run collection and report generation now")
    run.add_argument("--collect-only", action="store_true")
    run.add_argument("--report-only", action="store_true")
    run.set_defaults(func=lambda args: (_print(run_pipeline(project_root(), collect=not args.report_only, report=not args.collect_only), True), 0)[1])

    test = sub.add_parser("test", help="run a real end-to-end collection and report verification")
    test.set_defaults(func=lambda args: (_print(run_pipeline(project_root(), collect=True, report=True), True), 0)[1])

    tick = sub.add_parser("scheduled-tick", help="internal scheduler entry point")
    tick.set_defaults(func=lambda args: (_print(scheduled_tick(project_root()), True), 0)[1])

    schedule = sub.add_parser("schedule", help="manage the operating-system scheduler")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    for name, function in (
        ("install", lambda: {"ok": True, "installed": scheduler.install(project_root())}),
        ("uninstall", lambda: (scheduler.uninstall(), {"ok": True})[1]),
        ("pause", lambda: (scheduler.set_enabled(False), {"ok": True})[1]),
        ("resume", lambda: (scheduler.set_enabled(True), {"ok": True})[1]),
        ("status", scheduler.status),
    ):
        item = schedule_sub.add_parser(name)
        item.set_defaults(func=lambda args, fn=function: (_print(fn(), True), 0)[1])

    status = sub.add_parser("status", help="show scheduler and last successful run")
    status.set_defaults(func=command_status)
    update = sub.add_parser("update", help="fast-forward a clean installation and revalidate configuration")
    update.set_defaults(func=command_update)
    return parser


def main() -> None:
    parser = build_parser()
    try:
        args = parser.parse_args()
        code = args.func(args)
    except (ProfileError, ValueError, RuntimeError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        code = 1
    raise SystemExit(code)
