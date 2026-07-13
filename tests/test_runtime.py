from pathlib import Path

from business_intelligence_agent.runtime import _redact, _run_metrics


def test_runtime_log_redacts_model_key():
    assert _redact("request failed for test-secret-value", {"AI_API_KEY": "test-secret-value"}) == "request failed for [REDACTED]"


def test_metrics_distinguish_zero_failures_from_real_failures(tmp_path: Path):
    log = "\n".join([
        "成功: ['one', 'two'], 失败: []",
        "[RSS] 抓取完成: 1 个源成功, 0 个失败, 共 20 条",
    ])
    metrics = _run_metrics(tmp_path, log)
    assert metrics["successful_source_count"] == 3
    assert metrics["source_failures"] == []
