#!/usr/bin/env python3
"""为当日全部情报评分，并把高价值结果写入 Obsidian。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from json_repair import repair_json
from trendradar.ai.client import AIClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROMPT_DIR = Path(__file__).resolve().parents[1] / "config" / "custom" / "ai"
PROFILE_CONTEXT = ""
REPORT_REQUIREMENTS = ""


def render_prompt(filename: str, payload: object) -> str:
    template = (PROMPT_DIR / filename).read_text(encoding="utf-8")
    rendered = template.replace("{{INPUT_JSON}}", json.dumps(payload, ensure_ascii=False))
    return (
        f"[USER_INTELLIGENCE_OBJECTIVE]\n{PROFILE_CONTEXT}\n\n"
        f"[USER_REPORT_REQUIREMENTS]\n{REPORT_REQUIREMENTS}\n\n{rendered}"
    )


@dataclass
class IntelligenceItem:
    item_id: str
    title: str
    source: str
    source_type: str
    url: str
    published_at: str
    summary: str
    rank: int | None = None


def normalize_title(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", title.casefold())


def atomic_write_text(path: Path, content: str) -> None:
    """完整落盘后再替换目标文件，避免 Obsidian 读取到半成品。"""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

    if path.read_text(encoding="utf-8") != content:
        raise RuntimeError(f"写入后回读校验失败：{path}")


def load_items(project: Path, date: str) -> list[IntelligenceItem]:
    items: list[IntelligenceItem] = []
    news_db = project / "output" / "news" / f"{date}.db"
    rss_db = project / "output" / "rss" / f"{date}.db"

    if news_db.exists():
        query = """
            SELECT n.id, n.title, p.name, n.url, n.first_crawl_time, n.rank
            FROM news_items AS n
            JOIN platforms AS p ON p.id = n.platform_id
        """
        with sqlite3.connect(news_db) as connection:
            for row in connection.execute(query):
                crawl_time = row[4] or ""
                if re.fullmatch(r"\d{2}-\d{2}", crawl_time):
                    crawl_time = f"{date} {crawl_time.replace('-', ':')}"
                items.append(IntelligenceItem(
                    item_id=f"news-{row[0]}", title=row[1], source=row[2],
                    source_type="热榜", url=row[3] or "", published_at=crawl_time,
                    summary="", rank=int(row[5]),
                ))

    if rss_db.exists():
        query = """
            SELECT i.id, i.title, f.name, i.url, i.published_at, i.summary
            FROM rss_items AS i
            JOIN rss_feeds AS f ON f.id = i.feed_id
        """
        with sqlite3.connect(rss_db) as connection:
            for row in connection.execute(query):
                clean_summary = re.sub(r"<[^>]+>", " ", row[5] or "")
                clean_summary = re.sub(r"\s+", " ", clean_summary).strip()[:500]
                items.append(IntelligenceItem(
                    item_id=f"rss-{row[0]}", title=row[1], source=row[2],
                    source_type="RSS", url=row[3] or "", published_at=row[4] or "",
                    summary=clean_summary,
                ))

    deduplicated: dict[str, IntelligenceItem] = {}
    for item in items:
        key = normalize_title(item.title)
        existing = deduplicated.get(key)
        if not existing or (item.source_type == "RSS" and existing.source_type != "RSS"):
            deduplicated[key] = item
    return list(deduplicated.values())


def score_batch(client: AIClient, batch: list[IntelligenceItem]) -> list[dict]:
    payload = [
        {
            "id": item.item_id,
            "title": item.title,
            "source": item.source,
            "type": item.source_type,
            "published_at": item.published_at,
            "summary": item.summary,
            "rank": item.rank,
        }
        for item in batch
    ]
    prompt = render_prompt("01-value-scoring.txt", payload)
    response = client.chat(
        [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=7000
    )
    parsed = json.loads(repair_json(response))
    return parsed if isinstance(parsed, list) else []


def score_all(client: AIClient, items: list[IntelligenceItem], batch_size: int) -> list[dict]:
    scores: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        print(f"[评分] {start + 1}-{start + len(batch)} / {len(items)}", flush=True)
        scores.extend(score_batch(client, batch))
    return scores


def load_cached_scores(
    project: Path, date: str, items: list[IntelligenceItem]
) -> dict[str, dict]:
    """复用同一天内容未变化的评分，避免每轮重复调用模型。"""
    cache_file = project / "output" / "scored" / f"{date}-scores.json"
    if not cache_file.exists():
        return {}

    try:
        previous = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    previous_items = previous.get("items", {})
    previous_scores = previous.get("scores", [])
    current_items = {item.item_id: asdict(item) for item in items}
    comparable_fields = ("title", "source", "source_type", "published_at", "summary")
    dimensions = ("impact", "actionability", "timeliness", "credibility", "scarcity")
    cached: dict[str, dict] = {}

    for score in previous_scores:
        item_id = str(score.get("id", ""))
        old_item = previous_items.get(item_id)
        current_item = current_items.get(item_id)
        if not isinstance(old_item, dict) or not current_item:
            continue
        if any(old_item.get(field) != current_item.get(field) for field in comparable_fields):
            continue
        if not all(isinstance(score.get(field), int) for field in dimensions):
            continue
        cached[item_id] = score

    return cached


def eligible_for_daily(item: IntelligenceItem, report_date: str, max_age_days: int = 3) -> bool:
    """旧 RSS 仍保留评分，但不进入当日决策榜。"""
    if item.source_type == "热榜" or not item.published_at:
        return True
    try:
        published = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(report_date) - timedelta(days=max_age_days)
        return published.replace(tzinfo=None) >= cutoff
    except ValueError:
        return True


def select_entries(
    items: list[IntelligenceItem], scores: list[dict], date: str, threshold: int, limit: int
) -> list[tuple[int, IntelligenceItem, dict]]:
    item_map = {item.item_id: item for item in items}
    valid_scores = []
    for score in scores:
        item = item_map.get(str(score.get("id", "")))
        if not item:
            continue
        dimensions = ["impact", "actionability", "timeliness", "credibility", "scarcity"]
        calculated = sum(int(score.get(name, 0)) for name in dimensions)
        score["score"] = calculated
        if calculated >= threshold and eligible_for_daily(item, date):
            valid_scores.append((calculated, item, score))
    valid_scores.sort(key=lambda entry: entry[0], reverse=True)
    return valid_scores[:limit]


def enrich_selected(
    client: AIClient, selected: list[tuple[int, IntelligenceItem, dict]], batch_size: int = 5
) -> None:
    """只深度加工入选情报，避免对低价值信息浪费 token。"""
    required = ("one_line", "brief", "key_details", "information_value", "verification", "source_scope")
    pending = [entry for entry in selected if not all(entry[2].get(key) for key in required)]
    if not pending:
        print(f"[精编缓存] 复用 {len(selected)} 条既有精编", flush=True)
        return

    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        payload = [
            {
                "id": item.item_id,
                "title": item.title,
                "source": item.source,
                "published_at": item.published_at,
                "summary": item.summary,
                "score": total,
                "reason": score.get("reason", ""),
                "affected": score.get("affected", ""),
            }
            for total, item, score in batch
        ]
        prompt = render_prompt("02-factual-brief.txt", payload)
        response = client.chat(
            [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=5000
        )
        parsed = json.loads(repair_json(response))
        enrichment = {str(row.get("id")): row for row in parsed if isinstance(row, dict)}
        for _, item, score in batch:
            score.update(enrichment.get(item.item_id, {}))

    unresolved = [
        entry for entry in pending if not all(entry[2].get(key) for key in required)
    ]
    if unresolved and batch_size > 1:
        print(f"[精编] {len(unresolved)} 条返回不完整，逐条补齐", flush=True)
        enrich_selected(client, unresolved, batch_size=1)


def summarize_day(client: AIClient, selected: list[tuple[int, IntelligenceItem, dict]]) -> dict:
    payload = [
        {
            "title": item.title,
            "score": total,
            "category": score.get("category", "其他"),
            "brief": score.get("brief", ""),
            "one_line": score.get("one_line", ""),
            "key_details": score.get("key_details", []),
        }
        for total, item, score in selected
    ]
    prompt = render_prompt("03-daily-overview.txt", payload)
    response = client.chat(
        [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=3000
    )
    parsed = json.loads(repair_json(response))
    return parsed if isinstance(parsed, dict) else {}


def write_outputs(
    project: Path,
    vault: Path,
    date: str,
    items: list[IntelligenceItem],
    scores: list[dict],
    threshold: int,
    limit: int,
    overview: dict | None = None,
    profile: dict | None = None,
) -> Path:
    selected = select_entries(items, scores, date, threshold, limit)
    overview = overview or {}
    generated_at = datetime.now().astimezone()

    profile = profile or {}
    report_config = profile.get("report", {})
    delivery_config = profile.get("delivery", {})
    root = vault / delivery_config.get("folder", "Business Intelligence")
    daily_dir = root / date
    data_dir = project / "output" / "scored"
    daily_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    def list_lines(values: object) -> list[str]:
        return [f"- {value}" for value in values] if isinstance(values, list) else ["- 暂无"]

    lines = []
    frontmatter = report_config.get("frontmatter", {})
    if frontmatter.get("enabled", True):
        tags = frontmatter.get("tags", [])
        lines.extend([
            "---",
            f"date: {date}",
            f"generated_at: {generated_at.isoformat()}",
            "type: business-intelligence",
            f"tags: {json.dumps(tags, ensure_ascii=False)}",
            "---",
            "",
        ])
    lines.extend([
        f"# {date} {report_config.get('title', 'Business Intelligence Briefing')}",
        "",
        f"> 采集并去重：{len(items)} 条｜入选门槛：{threshold} 分｜精选：{len(selected)} 条  ",
        f"> 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}  ",
        "> 排序方式：商业情报价值总分从高到低",
        "",
    ])
    section_map = {
        "executive_summary": ("当日总览", "executive_summary", False),
        "key_themes": ("核心主题", "key_themes", True),
        "major_changes": ("当日关键变化", "major_changes", True),
        "information_gaps": ("当前信息缺口", "information_gaps", True),
        "watchlist": ("未来 24—72 小时核验清单", "watchlist", True),
    }
    requested_sections = report_config.get("sections", list(section_map) + ["high_value_intelligence"])
    for section in requested_sections:
        if section == "high_value_intelligence":
            continue
        if section in section_map:
            heading, key, is_list = section_map[section]
            content = list_lines(overview.get(key)) if is_list else [overview.get(key, "暂无")]
        else:
            heading = str(section).replace("_", " ").strip().title()
            custom = overview.get("custom_sections", {})
            value = custom.get(section) if isinstance(custom, dict) else None
            content = list_lines(value) if isinstance(value, list) else [value or "现有信息未披露。"]
        lines.extend([f"## {heading}", "", *content, ""])

    if "high_value_intelligence" in requested_sections:
        lines.extend(["## 高价值情报", ""])
    rendered_entries = selected if "high_value_intelligence" in requested_sections else []
    for index, (total, item, score) in enumerate(rendered_entries, 1):
        source_link = f"[{item.source}]({item.url})" if item.url else item.source
        lines.extend([
            f"### {index}. {item.title}",
            "",
            f"> **价值总分：{total}/100**｜{score.get('category', '其他')}｜{item.source_type}",
            "",
            f"**一句话结论**：{score.get('one_line', item.title)}",
            "",
            "**事件全貌**",
            "",
            score.get("brief", item.summary or "当前来源仅提供标题，具体事实需进入原始链接核验。"),
            "",
            "**关键细节**",
            "",
            *list_lines(score.get("key_details")),
            "",
            "**情报价值**",
            "",
            score.get("information_value", score.get("reason", "")),
            "",
            "**后续核验节点**",
            "",
            *list_lines(score.get("verification")),
            "",
            f"**信息边界**：{score.get('source_scope', '标题/有限摘要')}。评分是线索优先级，不替代原始文件核验。",
            "",
            f"**评分拆解**：影响 {score.get('impact', 0)}/30；行动价值 {score.get('actionability', 0)}/25；时效 {score.get('timeliness', 0)}/15；信源 {score.get('credibility', 0)}/15；稀缺 {score.get('scarcity', 0)}/15",
            "",
            f"**原始来源**：{source_link}",
            "",
            "---",
            "",
        ])

    timestamp = generated_at.strftime("%Y-%m-%d-%H-%M-%S")
    filename_pattern = report_config.get("filename", "{datetime}-business-intelligence.md")
    filename = filename_pattern.format(date=date, datetime=timestamp)
    daily_file = daily_dir / filename
    collision = 2
    while daily_file.exists():
        stem = Path(filename).stem
        daily_file = daily_dir / f"{stem}-{collision:02d}.md"
        collision += 1
    atomic_write_text(daily_file, "\n".join(lines))

    raw_output = {
        "date": date,
        "total_items": len(items),
        "threshold": threshold,
        "scores": scores,
        "items": {item.item_id: asdict(item) for item in items},
    }
    atomic_write_text(
        data_dir / f"{date}-scores.json",
        json.dumps(raw_output, ensure_ascii=False, indent=2),
    )
    return daily_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--date", default=datetime.now().astimezone().strftime("%Y-%m-%d"))
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--threshold", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=35)
    args = parser.parse_args()

    profile = {}
    if args.profile:
        profile = yaml.safe_load(args.profile.read_text(encoding="utf-8")) or {}
    report_config = profile.get("report", {})
    target_config = profile.get("profile", {})
    global PROFILE_CONTEXT, REPORT_REQUIREMENTS
    PROFILE_CONTEXT = json.dumps({
        "objective": target_config.get("objective", ""),
        "topics": target_config.get("topics", []),
        "regions": target_config.get("regions", []),
        "languages": target_config.get("languages", []),
    }, ensure_ascii=False)
    REPORT_REQUIREMENTS = json.dumps({
        "language": report_config.get("language", "zh-CN"),
        "sections": report_config.get("sections", []),
        "custom_requirements": report_config.get("custom_requirements", ""),
    }, ensure_ascii=False)
    threshold = args.threshold if args.threshold is not None else int(report_config.get("threshold", 70))
    limit = args.limit if args.limit is not None else int(report_config.get("limit", 30))

    api_key = os.environ.get("AI_API_KEY", "")
    if not api_key:
        raise SystemExit("缺少 AI_API_KEY")
    client = AIClient({
        "MODEL": os.environ.get("AI_MODEL", "deepseek/deepseek-chat"),
        "API_KEY": api_key,
        "API_BASE": os.environ.get("AI_API_BASE", "https://api.deepseek.com"),
        "TEMPERATURE": 0.1,
        "MAX_TOKENS": 7000,
        "TIMEOUT": 180,
        "NUM_RETRIES": 2,
    })
    project = args.project.resolve()
    vault = args.vault.expanduser().resolve()
    if not (vault / ".obsidian").is_dir():
        raise SystemExit(f"目标不是当前已初始化的 Obsidian Vault：{vault}")
    items = load_items(project, args.date)
    print(f"[评分] 去重后共 {len(items)} 条情报", flush=True)
    cached_scores = load_cached_scores(project, args.date, items)
    pending_items = [item for item in items if item.item_id not in cached_scores]
    print(
        f"[评分缓存] 复用 {len(cached_scores)} 条，新增或变化 {len(pending_items)} 条",
        flush=True,
    )
    new_scores = score_all(client, pending_items, args.batch_size)
    new_score_map = {str(score.get("id", "")): score for score in new_scores}
    scores = [
        cached_scores.get(item.item_id) or new_score_map.get(item.item_id)
        for item in items
    ]
    missing = [item.item_id for item, score in zip(items, scores) if score is None]
    if missing:
        raise RuntimeError(f"仍有 {len(missing)} 条情报未获得评分，停止生成日报")
    scores = [score for score in scores if score is not None]
    selected = select_entries(items, scores, args.date, threshold, limit)
    print(f"[精编] 深度加工 {len(selected)} 条高价值情报", flush=True)
    enrich_selected(client, selected)
    print("[总览] 生成当日事实型情报摘要", flush=True)
    overview = summarize_day(client, selected)
    output = write_outputs(
        project, vault, args.date, items, scores, threshold, limit,
        overview, profile,
    )
    print(f"[Obsidian交付] 已原子写入并回读验证：{output}", flush=True)
    print(f"[BIA_REPORT] {output}", flush=True)
    print(f"[完成] {output}", flush=True)


if __name__ == "__main__":
    main()
