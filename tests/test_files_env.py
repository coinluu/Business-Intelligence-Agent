import os
import stat
from pathlib import Path

from business_intelligence_agent.env import load_env, render_env
from business_intelligence_agent.files import atomic_write, backup


def test_secret_round_trip_and_permissions(tmp_path: Path):
    path = tmp_path / ".env.local"
    atomic_write(path, render_env({"AI_API_KEY": "key with spaces and ' quote", "OBSIDIAN_VAULT": "/tmp/Vault"}), 0o600)
    assert load_env(path)["AI_API_KEY"] == "key with spaces and ' quote"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_backup_preserves_previous_content(tmp_path: Path):
    path = tmp_path / "user-profile.yaml"
    path.write_text("old", encoding="utf-8")
    destination = backup(path)
    assert destination and destination.read_text(encoding="utf-8") == "old"
