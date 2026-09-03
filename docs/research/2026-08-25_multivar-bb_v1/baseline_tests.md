# 测试基线（改代码前）

运行命令：`uv run pytest tests/path2 tests/path2_web -q`
运行时间：2026-08-25（Task 0，HEAD = ec6ed28，加 pyarrow 依赖后、未改任何业务代码）

## 预存失败测试名单

```
tests/path2/atoms/test_throwback_v4.py::TestStable::test_new_high_arm_exit
tests/path2/atoms/test_throwback_v4.py::TestStable::test_weak_exit_reentry
tests/path2/atoms/test_throwback_v4.py::TestGlobalBreak::test_ratchet_chain_then_break
tests/path2/atoms/test_throwback_v4.py::TestGates::test_no_gate_on_normal_exits
```

## 总数

4 failed, 911 passed, 2 skipped, 4 warnings in 11.03s

## 与 brief 已知预期的偏差（如实记录，未臆造）

Task 0 brief 中写的"已知可能预存"名单是 `test_throwback_debug_anchor_kinds`（4 项）+ `test_params`（1 项），共 5 项。
实测结果与该名单**不一致**：

- 实际 4 个失败测试均在 `tests/path2/atoms/test_throwback_v4.py`，测试名分别为
  `TestStable::test_new_high_arm_exit`、`TestStable::test_weak_exit_reentry`、
  `TestGlobalBreak::test_ratchet_chain_then_break`、`TestGates::test_no_gate_on_normal_exits`——
  与 brief 提到的 `test_throwback_debug_anchor_kinds` 不是同一测试函数名。
- 未出现任何 `test_params` 相关失败（该项在 brief 预期中，实测里数目为 0）。

以上按实测结果为准；本次任务未修改任何业务代码（仅新增 pyarrow 依赖 + `ref_params.json`），
故这 4 项失败属于本 worktree 当前 HEAD（ec6ed28）下的真实预存状态。**后续每个 Task 的"全 PASS"
以本文件顶部的"预存失败测试名单"（4 项，均在 `test_throwback_v4.py`）为豁免基准，不采用 brief 中
的旧名单。**
