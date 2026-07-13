from pathlib import Path

import pytest
import yaml

from business_intelligence_agent.compiler import compile_runtime
from business_intelligence_agent.profile import DEFAULT_PROFILE, ProfileError, deep_merge, validate_profile


def ready_profile():
    return deep_merge(DEFAULT_PROFILE, {
        "onboarding": {
            "information_target_confirmed": True,
            "report_format_confirmed": True,
            "schedule_confirmed": True,
        },
        "profile": {"objective": "Track AI company changes", "topics": ["AI agents"]},
        "delivery": {"folder": "Research/AI"},
    })


def test_profile_requires_user_intent():
    with pytest.raises(ProfileError, match="objective"):
        validate_profile(DEFAULT_PROFILE)


def test_profile_rejects_unsafe_delivery_path():
    profile = ready_profile()
    profile["delivery"]["folder"] = "../outside"
    with pytest.raises(ProfileError, match="relative path"):
        validate_profile(profile)


def test_profile_rejects_unknown_filename_placeholder():
    profile = ready_profile()
    profile["report"]["filename"] = "{customer}-report.md"
    with pytest.raises(ProfileError, match="supports only"):
        validate_profile(profile)


def test_compiler_generates_targeted_runtime(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    (tmp_path / "config/config.yaml").write_text(
        (source_root / "config/config.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "config/timeline.yaml").write_text(
        (source_root / "config/timeline.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    profile = ready_profile()
    profile["profile"]["exclude_keywords"] = ["rumor"]
    profile["sources"]["rss_feeds"] = [
        {"id": "example", "name": "Example", "url": "https://example.com/feed"}
    ]
    generated = compile_runtime(tmp_path, profile)
    assert all(path.exists() for path in generated.values())
    keywords = generated["keywords"].read_text(encoding="utf-8")
    assert "AI\\ agents" in keywords
    assert "rumor" in keywords
    runtime_config = yaml.safe_load(generated["config"].read_text(encoding="utf-8"))
    assert runtime_config["rss"]["feeds"][0]["id"] == "example"
