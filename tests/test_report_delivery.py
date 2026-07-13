import importlib.util
import sys
from pathlib import Path


def load_score_module():
    path = Path(__file__).resolve().parents[1] / "scripts/score_commercial_intelligence.py"
    spec = importlib.util.spec_from_file_location("score_commercial_intelligence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_uses_profile_folder_title_and_filename(tmp_path: Path):
    module = load_score_module()
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    profile = {
        "delivery": {"folder": "Research/Robotics"},
        "report": {
            "title": "Robotics Watch",
            "sections": ["executive_summary"],
            "filename": "{date}-robotics.md",
        },
    }
    output = module.write_outputs(
        tmp_path, vault, "2026-07-13", [], [], 70, 30,
        {"executive_summary": "Verified summary."}, profile,
    )
    assert output.name == "2026-07-13-robotics.md"
    assert output.parent == vault / "Research/Robotics/2026-07-13"
    content = output.read_text(encoding="utf-8")
    assert "Robotics Watch" in content
    assert "Verified summary." in content
    assert "高价值情报" not in content
