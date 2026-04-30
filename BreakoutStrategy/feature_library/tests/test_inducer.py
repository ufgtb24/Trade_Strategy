"""Tests for inducer.batch_induce."""
from unittest.mock import MagicMock

import pytest
import yaml

from BreakoutStrategy.feature_library.inducer import batch_induce


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return paths


@pytest.fixture
def fake_samples(tmp_path, isolated_paths):
    """构造 3 个假 samples（chart.png + meta.yaml + nl_description.md）。"""
    sample_ids = []
    for i, ticker in enumerate(["AAPL", "MSFT", "GOOG"]):
        sid = f"BO_{ticker}_2024010{i+1}"
        sample_dir = isolated_paths.SAMPLES_DIR / sid
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "chart.png").write_bytes(b"fake-png-bytes")
        meta = {
            "sample_id": sid,
            "ticker": ticker,
            "bo_date": f"2024-01-0{i+1}",
            "breakout_day": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
            "consolidation": {
                "consolidation_length_bars": 30,
                "consolidation_height_pct": 5.0,
                "consolidation_position_vs_52w_high": -2.0,
                "consolidation_volume_ratio": 0.6,
                "consolidation_tightness_atr": 1.8,
            },
        }
        (sample_dir / "meta.yaml").write_text(yaml.safe_dump(meta), encoding="utf-8")
        (sample_dir / "nl_description.md").write_text("desc", encoding="utf-8")
        sample_ids.append(sid)
    return sample_ids


def test_batch_induce_parses_valid_yaml(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 盘整缩量后突破\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
        "  - text: 突破日大量\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102, BO_GOOG_20240103]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 2
    assert candidates[0].text == "盘整缩量后突破"
    assert candidates[0].K == 2
    assert candidates[0].N == 3
    assert candidates[1].K == 3

    # raw_response_excerpt 字段：非空 + 长度 ≤ 500
    assert len(candidates[0].raw_response_excerpt) > 0
    assert len(candidates[0].raw_response_excerpt) <= 500


def test_batch_induce_filters_K_lt_2(fake_samples):
    """SYSTEM_PROMPT 要求 K ≥ 2，单独支持的 candidate 应被过滤。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 单图独有\n"
        "    supporting_sample_ids: [BO_AAPL_20240101]\n"
        "  - text: 双图共性\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert candidates[0].text == "双图共性"


def test_batch_induce_filters_unknown_sample_ids(fake_samples):
    """LLM 幻觉出的 sample_id（不在 batch 内）应被过滤。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 含幻觉 ID\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_FAKE_99999999]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    # K=1 (filtered to AAPL only) → < 2 → 整条被过滤
    assert len(candidates) == 0


def test_batch_induce_empty_candidates_yaml(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "candidates: []"
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_invalid_yaml_returns_empty(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "this is: not valid: : yaml: text"
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_empty_backend_response(fake_samples):
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = ""
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert candidates == []


def test_batch_induce_raises_on_too_many_samples():
    fake_backend = MagicMock()
    with pytest.raises(ValueError, match="exceeds max_batch_size"):
        batch_induce(
            sample_ids=[f"BO_S{i}_20240101" for i in range(6)],
            backend=fake_backend,
            max_batch_size=5,
        )


def test_batch_induce_raises_on_missing_sample_artifacts(isolated_paths):
    """sample 目录不存在时抛 FileNotFoundError。"""
    fake_backend = MagicMock()
    with pytest.raises(FileNotFoundError, match="BO_MISSING_20240101"):
        batch_induce(
            sample_ids=["BO_MISSING_20240101"],
            backend=fake_backend,
        )


def test_batch_induce_passes_charts_and_message_to_backend(fake_samples):
    """验证 backend.batch_describe 收到正确的 chart_paths + user_message。
    归一化方案 B：user_message 含 [1]/[2]/[3] 匿名图序，不含真实 ticker/ID。
    """
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = "candidates: []"
    batch_induce(sample_ids=fake_samples, backend=fake_backend)

    call_kwargs = fake_backend.batch_describe.call_args.kwargs
    assert len(call_kwargs["chart_paths"]) == 3
    # 脱敏后 user_message 含 [1]/[2]/[3] 匿名编号，不含真实 sample_id
    assert "[1]" in call_kwargs["user_message"]
    assert "[2]" in call_kwargs["user_message"]
    assert "[3]" in call_kwargs["user_message"]
    assert "BO_AAPL_20240101" not in call_kwargs["user_message"]
    assert call_kwargs["system_prompt"]  # 显式传 INDUCER_SYSTEM_PROMPT


def test_batch_induce_logs_warning_on_full_hallucination(fake_samples, caplog):
    """全部 supporting_ids 都是幻觉时应 log warning。"""
    import logging
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 全幻觉\n"
        "    supporting_sample_ids: [BO_FAKE_1, BO_FAKE_2]\n"
    )
    with caplog.at_level(logging.WARNING):
        candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 0
    assert any("全部 supporting_ids 不在 batch 内" in record.message
               for record in caplog.records)


def test_batch_induce_strips_yaml_code_fence(fake_samples):
    """GLM-4V-Flash 实际会用 ```yaml ... ``` 包裹输出（违反 SYSTEM_PROMPT），
    inducer 应剥离围栏后再解析。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "```yaml\n"
        "candidates:\n"
        "  - text: 盘整缩量后突破\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
        "```\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert candidates[0].text == "盘整缩量后突破"


def test_batch_induce_strips_plain_code_fence(fake_samples):
    """无 yaml 标签的 ``` ... ``` 围栏也应被剥离。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "```\n"
        "candidates:\n"
        "  - text: 双图共性\n"
        "    supporting_sample_ids: [BO_AAPL_20240101, BO_MSFT_20240102]\n"
        "```"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert candidates[0].text == "双图共性"


def test_batch_induce_translates_anonymous_indices_to_real_ids(fake_samples):
    """生产路径：GLM 返回 [1]/[2] 匿名图序，inducer 应翻译回真实 sample_id 后再过滤。

    fake_samples fixture 的 id_map：[1]→BO_AAPL_20240101, [2]→BO_MSFT_20240102, [3]→BO_GOOG_20240103
    """
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 匿名图序应被翻译\n"
        "    supporting_sample_ids: ['[1]', '[2]']\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert set(candidates[0].supporting_sample_ids) == {"BO_AAPL_20240101", "BO_MSFT_20240102"}
    assert candidates[0].K == 2


def test_batch_induce_accepts_bare_int_supporting_ids(fake_samples):
    """实际生产路径:GLM-4V 输出 YAML `supporting_sample_ids: [1, 2, 3]` 时被解析成裸整数 list,
    inducer 应将其归一化为 [1]/[2]/[3] 再查 id_map。

    Regression for: '全部 supporting_ids 不在 batch 内, hallucinated=[1, 2, 3, 4, 5]'
    Phase 1 entry script 首跑时所有 candidate 被误判为幻觉的根因。
    """
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 三图共性(裸整数)\n"
        "    supporting_sample_ids: [1, 2, 3]\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1, \
        f"裸整数 supporting_sample_ids 应被翻译,而非全部判幻觉,实际: {candidates}"
    assert set(candidates[0].supporting_sample_ids) == {
        "BO_AAPL_20240101", "BO_MSFT_20240102", "BO_GOOG_20240103",
    }
    assert candidates[0].K == 3


def test_batch_induce_accepts_digit_string_supporting_ids(fake_samples):
    """另一种 GLM 变体:`supporting_sample_ids: ["1", "2"]`(数字字符串)。"""
    fake_backend = MagicMock()
    fake_backend.batch_describe.return_value = (
        "candidates:\n"
        "  - text: 数字字符串支持\n"
        "    supporting_sample_ids: ['1', '2']\n"
    )
    candidates = batch_induce(sample_ids=fake_samples, backend=fake_backend)
    assert len(candidates) == 1
    assert set(candidates[0].supporting_sample_ids) == {"BO_AAPL_20240101", "BO_MSFT_20240102"}
