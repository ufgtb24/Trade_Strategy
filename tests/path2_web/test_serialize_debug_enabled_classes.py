"""v4 契约 C · serialize_pattern 派生 debug_enabled_classes 契约测试。

契约:
- serialize_pattern(spec) 返回 dict 里必有 `debug_enabled_classes: list[str]` 顶层字段
- 值 = spec.nodes 里 detector 类 has_debug_hooks=True 的 event_cls.class_id 去重、按拓扑序
- 今天 bottom_burst pattern 里:
  - `bo` (BODetector, has_debug_hooks=False) → 不含
  - `burst` (BurstDetector, has_debug_hooks=False) → 不含
  - `tb` (ThrowbackDetector, has_debug_hooks=True) → 含
  → 期望 `debug_enabled_classes = ["tb"]`
"""
import pytest


def test_bottom_burst_pattern_debug_enabled_classes_is_tb_only():
    from path2_apps.bottom_breakout_burst import build_pattern, load_params

    from path2_web.serialize import serialize_pattern

    spec = build_pattern(load_params())
    payload = serialize_pattern(spec)

    assert "debug_enabled_classes" in payload, (
        "契约 C 要求 serialize_pattern 输出顶层含 debug_enabled_classes 字段"
    )
    assert payload["debug_enabled_classes"] == ["tb"], (
        f"bottom_burst 今天只 tb 一家标 has_debug_hooks=True · 期望 ['tb'] · "
        f"实际 {payload['debug_enabled_classes']}"
    )


def test_debug_enabled_classes_list_type_and_uniqueness():
    """字段类型 = list[str] · 元素去重(即使同一 class_id 挂多 node 也只出现一次)。"""
    from path2_apps.bottom_breakout_burst import build_pattern, load_params

    from path2_web.serialize import serialize_pattern

    spec = build_pattern(load_params())
    payload = serialize_pattern(spec)
    dec = payload["debug_enabled_classes"]

    assert isinstance(dec, list)
    assert all(isinstance(x, str) for x in dec)
    assert len(dec) == len(set(dec)), f"debug_enabled_classes 应去重 · got {dec}"
