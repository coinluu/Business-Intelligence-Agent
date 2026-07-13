from __future__ import annotations

import copy
import re
import string
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


DEFAULT_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "onboarding": {
        "information_target_confirmed": False,
        "report_format_confirmed": False,
        "schedule_confirmed": False,
    },
    "profile": {
        "name": "My Business Intelligence",
        "objective": "",
        "topics": [],
        "include_keywords": [],
        "exclude_keywords": [],
        "regions": [],
        "languages": ["zh-CN", "en"],
    },
    "sources": {
        "platform_ids": [],
        "rss_feeds": [],
    },
    "report": {
        "language": "zh-CN",
        "title": "Business Intelligence Briefing",
        "sections": [
            "executive_summary",
            "key_themes",
            "major_changes",
            "information_gaps",
            "watchlist",
            "high_value_intelligence",
        ],
        "custom_requirements": "",
        "frontmatter": {"enabled": True, "tags": ["business-intelligence"]},
        "threshold": 70,
        "limit": 30,
        "filename": "{datetime}-business-intelligence.md",
    },
    "delivery": {
        "obsidian_vault": "auto",
        "folder": "Business Intelligence",
    },
    "schedule": {
        "collection_every_minutes": 30,
        "report_times": ["08:00"],
        "timezone": "system",
        "catch_up": True,
    },
    "model": {
        "model": "deepseek/deepseek-chat",
        "api_base": "https://api.deepseek.com",
    },
}


class ProfileError(ValueError):
    pass


def deep_merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ProfileError(f"Profile not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProfileError("Profile must be a YAML object")
    profile = deep_merge(DEFAULT_PROFILE, data)
    validate_profile(profile)
    return profile


def validate_profile(data: dict[str, Any], require_ready: bool = True) -> None:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if require_ready:
        confirmations = data.get("onboarding", {})
        missing = [
            key for key in (
                "information_target_confirmed", "report_format_confirmed", "schedule_confirmed"
            ) if confirmations.get(key) is not True
        ]
        if missing:
            errors.append(f"user confirmation required: {', '.join(missing)}")

    target = data.get("profile", {})
    if require_ready and not str(target.get("objective", "")).strip():
        errors.append("profile.objective is required")
    if require_ready and not (target.get("topics") or target.get("include_keywords")):
        errors.append("at least one profile.topic or include_keyword is required")

    report = data.get("report", {})
    sections = report.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("report.sections must be a non-empty list")
    threshold = report.get("threshold")
    limit = report.get("limit")
    if not isinstance(threshold, int) or not 0 <= threshold <= 100:
        errors.append("report.threshold must be an integer from 0 to 100")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        errors.append("report.limit must be an integer from 1 to 100")
    frontmatter = report.get("frontmatter", {})
    if not isinstance(frontmatter, dict) or not isinstance(frontmatter.get("enabled", True), bool):
        errors.append("report.frontmatter must contain a boolean enabled value")
    elif not isinstance(frontmatter.get("tags", []), list):
        errors.append("report.frontmatter.tags must be a list")
    filename = str(report.get("filename", ""))
    if not filename.endswith(".md") or Path(filename).name != filename:
        errors.append("report.filename must be a safe Markdown filename pattern")
    try:
        fields = {field for _, field, _, _ in string.Formatter().parse(filename) if field}
        if fields - {"date", "datetime"}:
            errors.append("report.filename supports only {date} and {datetime}")
    except ValueError:
        errors.append("report.filename has invalid format placeholders")

    delivery = data.get("delivery", {})
    folder = str(delivery.get("folder", ""))
    if not folder.strip() or Path(folder).is_absolute() or ".." in Path(folder).parts:
        errors.append("delivery.folder must be a non-empty relative path")

    schedule = data.get("schedule", {})
    interval = schedule.get("collection_every_minutes")
    if not isinstance(interval, int) or not 5 <= interval <= 1440:
        errors.append("schedule.collection_every_minutes must be 5..1440")
    times = schedule.get("report_times")
    if not isinstance(times, list) or not times:
        errors.append("schedule.report_times must be a non-empty list")
    elif any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(value)) for value in times):
        errors.append("schedule.report_times must use HH:MM")
    timezone = str(schedule.get("timezone", "system"))
    if timezone != "system":
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            errors.append("schedule.timezone must be system or a valid IANA timezone")

    feeds = data.get("sources", {}).get("rss_feeds", [])
    if not isinstance(feeds, list):
        errors.append("sources.rss_feeds must be a list")
    else:
        ids: set[str] = set()
        for feed in feeds:
            if not isinstance(feed, dict) or not all(feed.get(k) for k in ("id", "name", "url")):
                errors.append("each RSS feed requires id, name, and url")
                continue
            if feed["id"] in ids:
                errors.append(f"duplicate RSS feed id: {feed['id']}")
            ids.add(feed["id"])
            if not str(feed["url"]).startswith(("https://", "http://")):
                errors.append(f"RSS URL must be http(s): {feed['id']}")

    if errors:
        raise ProfileError("; ".join(errors))
