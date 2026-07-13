from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from .files import atomic_write


def _safe_pattern(words: list[str]) -> str:
    values = [re.escape(str(word).strip()) for word in words if str(word).strip()]
    return "|".join(values) or "business intelligence"


def compile_runtime(project: Path, profile: dict[str, Any]) -> dict[str, Path]:
    runtime = project / "runtime"
    base = yaml.safe_load((project / "config/config.yaml").read_text(encoding="utf-8"))
    config = copy.deepcopy(base)

    source_cfg = profile["sources"]
    platform_ids = set(source_cfg.get("platform_ids", []))
    if platform_ids:
        known = {item["id"] for item in config["platforms"]["sources"]}
        unknown = sorted(platform_ids - known)
        if unknown:
            raise ValueError(f"Unknown platform ids: {', '.join(unknown)}")
        config["platforms"]["sources"] = [
            item for item in config["platforms"]["sources"] if item["id"] in platform_ids
        ]
    custom_feeds = source_cfg.get("rss_feeds", [])
    if custom_feeds:
        config["rss"]["feeds"] = custom_feeds
    config["ai"]["model"] = profile["model"]["model"]
    config["ai"]["api_base"] = profile["model"].get("api_base", "")

    config_path = runtime / "config.yaml"
    keywords_path = runtime / "frequency_words.txt"
    profile_path = runtime / "profile.yaml"
    timeline_path = runtime / "timeline.yaml"
    atomic_write(config_path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    atomic_write(timeline_path, (project / "config/timeline.yaml").read_text(encoding="utf-8"))

    target = profile["profile"]
    included = list(dict.fromkeys(target.get("topics", []) + target.get("include_keywords", [])))
    excluded = target.get("exclude_keywords", [])
    keywords = ["[GLOBAL_FILTER]", *excluded, "", "[WORD_GROUPS]", "", "[User Intelligence Targets]", f"/{_safe_pattern(included)}/", "@100", ""]
    atomic_write(keywords_path, "\n".join(keywords))
    atomic_write(profile_path, yaml.safe_dump(profile, allow_unicode=True, sort_keys=False))
    return {"config": config_path, "keywords": keywords_path, "profile": profile_path, "timeline": timeline_path}
