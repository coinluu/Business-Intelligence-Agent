from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .compiler import compile_runtime
from .env import load_env
from .files import atomic_write
from .profile import load_profile


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _runtime_env(project: Path, profile: dict[str, Any]) -> dict[str, str]:
    compiled = compile_runtime(project, profile)
    values = load_env(project / ".env.local")
    environment = os.environ.copy()
    environment.update({key: value for key, value in values.items() if value})
    environment["CONFIG_PATH"] = str(compiled["config"])
    environment["FREQUENCY_WORDS_PATH"] = str(compiled["keywords"])
    environment["BIA_PROFILE_PATH"] = str(compiled["profile"])
    environment["TRENDRADAR_OPEN_BROWSER"] = "0"
    return environment


def _redact(text: str, environment: dict[str, str]) -> str:
    redacted = text
    for key in ("AI_API_KEY",):
        secret = environment.get(key, "")
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _acquire_lock(project: Path) -> Path:
    lock = project / ".state/run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        try:
            payload = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
            pid = int(payload["pid"])
            os.kill(pid, 0)
            raise RuntimeError(f"Another run is active (pid {pid})")
        except ProcessLookupError:
            shutil.rmtree(lock)
            lock.mkdir()
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            if time.time() - lock.stat().st_mtime < 6 * 3600:
                raise RuntimeError("Another run may be active; run lock is younger than six hours")
            shutil.rmtree(lock)
            lock.mkdir()
    atomic_write(lock / "owner.json", json.dumps({"pid": os.getpid(), "started": time.time()}))
    return lock


def _database_count(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    with sqlite3.connect(path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _run_metrics(project: Path, log: str) -> dict[str, Any]:
    date = datetime.now().astimezone().strftime("%Y-%m-%d")
    news = _database_count(project / f"output/news/{date}.db", "news_items")
    rss = _database_count(project / f"output/rss/{date}.db", "rss_items")
    source_failures: list[str] = []
    pipeline_errors: list[str] = []
    successful_sources: set[str] = set()
    for raw in log.splitlines():
        line = raw.strip()
        if not line:
            continue
        reports_zero = bool(
            re.search(r"0\s*个失败", line)
            or re.search(r"失败\s*[:=：]\s*\[\]", line)
            or re.search(r"(?:failed)\s*[:=]\s*0\b", line, re.IGNORECASE)
        )
        if re.search(r"(?:抓取|获取|请求|数据源).*(?:失败|failed)", line, re.IGNORECASE) and not reports_zero:
            source_failures.append(line)
        if re.search(r"(?:执行出错|分析流程执行出错|未处理异常|traceback)", line, re.IGNORECASE):
            pipeline_errors.append(line)
        platform_summary = re.search(r"^成功:\s*(\[.*?\]),\s*失败:\s*(\[.*?\])", line)
        if platform_summary:
            try:
                successful_sources.update(str(value) for value in ast.literal_eval(platform_summary.group(1)))
                failed = ast.literal_eval(platform_summary.group(2))
                if failed and line not in source_failures:
                    source_failures.append(line)
            except (SyntaxError, ValueError):
                pass
        rss_summary = re.search(r"\[RSS\]\s*抓取完成:\s*(\d+)\s*个源成功,\s*(\d+)\s*个失败", line)
        if rss_summary:
            successful_sources.update(f"rss-{index}" for index in range(int(rss_summary.group(1))))
            if int(rss_summary.group(2)) and line not in source_failures:
                source_failures.append(line)
    return {
        "news_items": news,
        "rss_items": rss,
        "successful_source_count": len(successful_sources),
        "source_failures": source_failures[-50:],
        "pipeline_errors": pipeline_errors[-50:],
    }


def run_pipeline(project: Path, collect: bool = True, report: bool = True) -> dict[str, Any]:
    profile = load_profile(project / "user-profile.yaml")
    environment = _runtime_env(project, profile)
    started = datetime.now().astimezone()
    state_dir = project / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = _acquire_lock(project)
    log_path = state_dir / "latest-run.log"
    output: list[str] = []

    def execute(command: list[str]) -> None:
        process = subprocess.run(
            command,
            cwd=project,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output.append(_redact(process.stdout, environment))
        atomic_write(log_path, "\n".join(output))
        if process.returncode:
            raise RuntimeError(f"Command failed ({process.returncode}). See {log_path}")

    try:
        if collect:
            execute([sys.executable, "-m", "trendradar"])
        report_file = ""
        if report:
            vault = environment.get("OBSIDIAN_VAULT", "")
            api_key = environment.get("AI_API_KEY", "")
            if not api_key:
                raise RuntimeError("AI_API_KEY is missing")
            if not vault:
                raise RuntimeError("OBSIDIAN_VAULT is missing")
            execute([
                sys.executable,
                "scripts/score_commercial_intelligence.py",
                "--project", str(project),
                "--vault", vault,
                "--profile", str(project / "user-profile.yaml"),
            ])
            for line in reversed("\n".join(output).splitlines()):
                if line.startswith("[BIA_REPORT]"):
                    report_file = line.removeprefix("[BIA_REPORT]").strip()
                    break
            report_path = Path(report_file)
            vault_path = Path(vault).expanduser().resolve()
            if not report_file or not report_path.is_file() or report_path.stat().st_size == 0:
                raise RuntimeError("Report command completed but no non-empty report was verified")
            if not report_path.resolve().is_relative_to(vault_path):
                raise RuntimeError("Generated report is outside the configured Obsidian vault")

        combined_log = "\n".join(output)
        metrics = _run_metrics(project, combined_log)
        if collect and metrics["successful_source_count"] == 0:
            raise RuntimeError("No configured data source completed successfully")
        state = "DEGRADED" if metrics["source_failures"] or metrics["pipeline_errors"] else "COMPLETE"
        result = {
            "ok": True,
            "state": state,
            "started_at": started.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
            "collected": collect,
            "reported": report,
            "report_file": report_file,
            "metrics": metrics,
            "log": str(log_path),
        }
        atomic_write(state_dir / "last-success.json", json.dumps(result, ensure_ascii=False, indent=2))
        return result
    except Exception as error:
        failure = {
            "ok": False,
            "state": "FAILED",
            "started_at": started.isoformat(),
            "failed_at": datetime.now().astimezone().isoformat(),
            "error": str(error),
            "log": str(log_path),
        }
        atomic_write(state_dir / "last-failure.json", json.dumps(failure, ensure_ascii=False, indent=2))
        raise
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def scheduled_tick(project: Path) -> dict[str, Any]:
    profile = load_profile(project / "user-profile.yaml")
    schedule = profile["schedule"]
    timezone = schedule.get("timezone", "system")
    now = datetime.now().astimezone() if timezone == "system" else datetime.now(ZoneInfo(timezone))
    state_dir = project / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    tick_state_path = state_dir / "schedule-state.json"
    try:
        tick_state = json.loads(tick_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        tick_state = {}

    last_collection_raw = tick_state.get("last_collection")
    last_collection = datetime.fromisoformat(last_collection_raw) if last_collection_raw else None
    collection_due = last_collection is None or (
        now - last_collection
    ).total_seconds() >= schedule["collection_every_minutes"] * 60

    today = now.strftime("%Y-%m-%d")
    current = now.strftime("%H:%M")
    completed_reports = set(tick_state.get("completed_reports", []))
    due_slots = []
    for value in schedule["report_times"]:
        marker = f"{today}T{value}"
        if marker in completed_reports:
            continue
        if schedule.get("catch_up", True):
            due = current >= value
        else:
            hour, minute = (int(part) for part in value.split(":"))
            slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            due = timedelta(0) <= now - slot < timedelta(minutes=6)
        if due:
            due_slots.append(value)
    report_due = bool(due_slots)

    if not collection_due and not report_due:
        return {"ok": True, "action": "none", "reason": "not_due"}

    result = run_pipeline(project, collect=collection_due or report_due, report=report_due)
    if collection_due or report_due:
        tick_state["last_collection"] = now.isoformat()
    for slot in due_slots:
        completed_reports.add(f"{today}T{slot}")
    tick_state["completed_reports"] = sorted(
        value for value in completed_reports if value.startswith(today)
    )
    atomic_write(tick_state_path, json.dumps(tick_state, ensure_ascii=False, indent=2))
    return {**result, "action": "run", "report_slots": due_slots}
