from pathlib import Path
from xml.etree import ElementTree

from business_intelligence_agent import scheduler


class Result:
    returncode = 0
    stdout = "ok"


def test_macos_scheduler_escapes_paths(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "A & B"
    project.mkdir()
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scheduler.Path, "home", lambda: home)
    monkeypatch.setattr(scheduler.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(scheduler.shutil, "which", lambda name: "/usr/local/bin/uv")
    monkeypatch.setattr(scheduler, "_run", lambda *args, **kwargs: Result())
    target = Path(scheduler.install(project))
    content = target.read_text(encoding="utf-8")
    ElementTree.fromstring(content)
    assert "A &amp; B" in content
    assert "StartInterval" in content


def test_windows_scheduler_uses_task_scheduler(tmp_path: Path, monkeypatch):
    commands = []
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Windows")
    monkeypatch.setattr(scheduler.shutil, "which", lambda name: "C:\\uv.exe")
    monkeypatch.setattr(scheduler, "_run", lambda command, **kwargs: (commands.append(command), Result())[1])
    scheduler.install(tmp_path)
    assert commands[0][0] == "schtasks"
    assert "/Create" in commands[0]


def test_linux_scheduler_uses_user_timer(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scheduler.Path, "home", lambda: home)
    monkeypatch.setattr(scheduler.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(scheduler, "_run", lambda *args, **kwargs: Result())
    target = Path(scheduler.install(project))
    assert target.exists()
    assert "OnUnitActiveSec=5min" in target.read_text(encoding="utf-8")
