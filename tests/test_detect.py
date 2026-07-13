import json
from pathlib import Path

from business_intelligence_agent import detect


def test_discovers_only_initialized_vaults(tmp_path: Path, monkeypatch):
    first = tmp_path / "Vault One"
    second = tmp_path / "Missing Marker"
    (first / ".obsidian").mkdir(parents=True)
    second.mkdir()
    config = tmp_path / "obsidian.json"
    config.write_text(json.dumps({"vaults": {
        "one": {"path": str(first)},
        "two": {"path": str(second)},
    }}), encoding="utf-8")
    monkeypatch.setattr(detect, "_obsidian_config_path", lambda: config)
    monkeypatch.setattr(detect.Path, "home", lambda: tmp_path / "empty-home")
    assert detect.discover_obsidian_vaults() == [str(first.resolve())]
