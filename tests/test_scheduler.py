from pathlib import Path
from xml.etree import ElementTree

import pytest

from business_intelligence_agent import scheduler


class Result:
    returncode = 0
    stdout = "ok"


def test_macos_scheduler_escapes_paths(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "A & B"
    project.mkdir()
    original_run = scheduler._run
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return original_run(command, **kwargs) if command[0] == "plutil" else Result()

    monkeypatch.setattr(scheduler.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scheduler.Path, "home", lambda: home)
    monkeypatch.setattr(scheduler.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(scheduler.shutil, "which", lambda name: "/usr/local/bin/uv")
    monkeypatch.setattr(scheduler, "_run", run)
    target = Path(scheduler.install(project))
    content = target.read_text(encoding="utf-8")
    ElementTree.fromstring(content)
    assert "A &amp; B" in content
    assert "StartInterval" in content
    assert any(command[0] == "plutil" for command in commands)
    assert any(command[:2] == ["launchctl", "bootstrap"] for command in commands)


def test_non_macos_scheduler_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Unsupported")
    with pytest.raises(RuntimeError, match="macOS only"):
        scheduler.install(tmp_path)
