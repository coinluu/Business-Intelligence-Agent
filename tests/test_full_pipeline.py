import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


class OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        prompt = request["messages"][-1]["content"]
        payload = json.loads(prompt.rsplit("[INPUT_JSON]", 1)[1].strip())
        if "commercial-intelligence-value-scoring" in prompt:
            content = [{
                "id": item["id"], "impact": 30, "actionability": 20,
                "timeliness": 10, "credibility": 10, "scarcity": 10,
                "score": 80, "category": "Technology", "reason": "Material update",
                "affected": "Industry", "next_check": "Primary announcement",
            } for item in payload]
        elif "commercial-intelligence-factual-brief" in prompt:
            content = [{
                "id": item["id"], "one_line": "Verified test conclusion",
                "brief": "Test source disclosed a product update.",
                "key_details": ["Primary detail"],
                "information_value": "Useful for product monitoring.",
                "verification": ["Check the primary announcement"],
                "source_scope": "title/limited summary",
            } for item in payload]
        else:
            content = {
                "executive_summary": "Verified integration summary.",
                "key_themes": ["Product update"],
                "major_changes": ["A product changed"],
                "information_gaps": ["Full announcement unavailable"],
                "watchlist": ["Primary announcement"],
                "custom_sections": {},
            }
        response = json.dumps({
            "id": "test", "object": "chat.completion", "created": 1,
            "model": "test", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(content, ensure_ascii=False)
            }}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        return


def test_scoring_to_obsidian_with_openai_compatible_api(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    date = datetime.now().astimezone().strftime("%Y-%m-%d")
    news_dir = project / "output/news"
    news_dir.mkdir(parents=True)
    with sqlite3.connect(news_dir / f"{date}.db") as connection:
        connection.execute("CREATE TABLE platforms (id TEXT PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE news_items (id INTEGER PRIMARY KEY, title TEXT, platform_id TEXT, url TEXT, first_crawl_time TEXT, rank INTEGER)")
        connection.execute("INSERT INTO platforms VALUES ('test', 'Primary Test Source')")
        connection.execute("INSERT INTO news_items VALUES (1, 'Test company launches product', 'test', 'https://example.com/source', '09-30', 1)")

    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    profile = {
        "profile": {"objective": "Track product changes", "topics": ["products"]},
        "report": {
            "title": "Product Watch", "language": "en",
            "sections": ["executive_summary", "high_value_intelligence"],
            "custom_requirements": "Keep sources", "threshold": 70, "limit": 10,
            "filename": "{date}-product-watch.md",
        },
        "delivery": {"folder": "Research/Product Watch"},
    }
    profile_path = project / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", 0), OpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = os.environ.copy()
        environment.update({
            "AI_API_KEY": "test-only-key",
            "AI_MODEL": "openai/test",
            "AI_API_BASE": f"http://127.0.0.1:{server.server_port}/v1",
        })
        result = subprocess.run([
            sys.executable, str(repo / "scripts/score_commercial_intelligence.py"),
            "--project", str(project), "--vault", str(vault),
            "--profile", str(profile_path), "--date", date,
        ], cwd=repo, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stdout
    report = vault / f"Research/Product Watch/{date}/{date}-product-watch.md"
    assert report.is_file()
    content = report.read_text(encoding="utf-8")
    assert "Product Watch" in content
    assert "Verified integration summary" in content
    assert "https://example.com/source" in content
    assert "[BIA_REPORT]" in result.stdout
