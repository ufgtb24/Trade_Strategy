# 多维稳健区调参工具链 v2（每股反转循环 + 候选长表 + 联合空间）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「必须真扫参数」的多维调参从「每格一次全宇宙 scan」改成「每股一次反转循环」，输出候选长表；在联合空间（真扫维 × where 维）上用「相对每 fold 参照增量 → fold 最小 → r=1 邻域最小 → 按股 bootstrap + 选择后校正」识别稳健区；在 bb_v1 上端到端跑通（6 维 4096 格 × where 档，分钟级）并与逐格 scan 精确对拍。

**Architecture:** 三处引擎侧纯效率修复（`calculate_atr` 向量化；throwback 三版本 ATR 每股算一次；`eval.py` 首穿尺度 M 可外传）+ 两处协议小改（`BurstDetector.filter_params` 声明；`ThrowbackEventV1.day_drop` 字段）+ scan 文件 per-match 字段；skill 侧四个文件：`multivar_core.py`（纯函数：参数分类探针 / 影响集 / 单股反转循环）→ `multivar_scan.py`（进程池 + parquet 分片 + 台账）→ `region_core.py`（纯函数：格张量 / 可评估 / 增量 / 邻域最小 / bootstrap / 校正）→ `region_find.py`（图 + 报告）。不改 `path2/dag/` 引擎，不引入优化框架。

**Tech Stack:** Python 3.12 / numpy / pandas / pyarrow（新增）/ matplotlib / pytest；包管理 `uv`。

**Spec:** `docs/superpowers/specs/2026-08-25-multivar-region-reversed-loop-design.md`（v2；v1 `2026-08-23-multivar-robust-region-design.md` 已标注取代）。研究依据：`docs/research/2026-08-24_region-search-budget/final_report.md`、`docs/research/2026-08-24_multivar-region-review/final_report.md`。

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**（repo root = `git rev-parse --show-toplevel`）。唯一的机器本地绝对路径是主目录数据 `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls`（不在 git 内、worktree 里没有），Task 0 用符号链接把它接到 `datasets/`，之后一律用相对路径 `datasets/pkls`。**只读**：任何步骤不得写主目录。
- 实施基线：分支 `worktree-tune-tools`，工作目录即本 worktree。实施前 `git status --short` 应为空。
- **禁止**改 `path2/dag/` 下任何文件；**禁止**引入 optuna / Ax / scikit-learn 新用法 / LHS / GP；**不**为旧 scan 文件做兼容。
- 与并行的 tb 简化分支唯一重叠 = `path2/atoms/throwback_v1.py` 的 Task 2 改动（ATR 算一次 + `day_drop` 字段）；本 plan 只做这两处、不动 tb 判据。
- 入口脚本**无 argparse**：全部参数是 `main()` 起始处的大写常量。
- 指标契约：FP = `up / (up + down + both)`（`none` 不进分母）；**按 match 计**（每行一份四态）；win_rate 不出现在任何输出。
- **HEAD_BUFFER = 250**（训练窗前缓冲交易日），`multivar_scan` 与 `region_find` 共用；`region_find` 读 ledger 核对不一致即退出。
- 数值红线：`calculate_atr` 新旧逐值 `atol=1e-12`；反转循环与逐格 `engine.analyze` 的键集 `(symbol, 各节点 span, fr, 四态)` + 每股 `match_fp_counts` 必须**零差**。
- 测试：库内测试 `uv run pytest tests/<path> -q`；skill 内测试**显式路径**跑 `uv run pytest .claude/skills/tune-gates/<test>.py -q`（与 `test_plateau.py` 同约定，不进默认收集）。真实数据缺失时相关测试 `pytest.skip`。
- 提交信息中文，前缀 `feat/fix/test/perf/docs/chore`；每个 Task 至少一次提交。
- 调工具纪律（派 subagent 时原样放进 prompt）：中途消息正文至多一句状态行（无代码 token、不预告"我去调用 X"），随后直接发调用；长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字，不要停笔，在同一条消息里立即发出真正的调用。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `datasets` → 符号链接到主目录 `datasets`（gitignored） | 数据 | Task 0 |
| `docs/research/2026-08-25_multivar-bb_v1/ref_params.json` | 参照底座参数快照（OAT 底座，非 default） | Task 0 |
| `docs/research/2026-08-25_multivar-bb_v1/baseline_tests.md` | 改代码前的预存失败测试名单 | Task 0 |
| `path2/calc/atr.py` | `calculate_atr` numpy 标量递推 | Task 1 |
| `tests/path2/calc/test_atr_equivalence.py` | 逐值等价 | Task 1 |
| `docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py` | 修复前/后子集 scan 对比 | Task 1/2 |
| `path2/atoms/throwback_v1.py`、`throwback_v0.py`、`throwback.py` | ATR 每股一次；v1 事件加 `day_drop` | Task 2 |
| `tests/path2/atoms/test_throwback_v1_day_drop.py` | `day_drop` 字段与 `_revert_max_day_drop` 一致 | Task 2 |
| `path2/eval.py` | `match_first_passage` / `random_day_first_passage` 增 `M` | Task 3 |
| `tests/path2/test_eval_M_param.py` | M 外传等价 | Task 3 |
| `path2_web/serialize.py` | match 加 `buy_date` / `first_passage` | Task 4 |
| `tests/path2_web/test_serialize_match_fp.py` | 不变式 | Task 4 |
| `path2/atoms/breakout.py` | `BurstDetector.filter_params` | Task 5 |
| `tests/path2/atoms/test_burst_filter_params.py` | 事后过滤 == 直接构造 | Task 5 |
| `.claude/skills/tune-gates/multivar_core.py` | 探针分类 / 影响集 / 组合展开 / 单股反转 | Task 6、7 |
| `.claude/skills/tune-gates/test_multivar_core.py` | 纯函数单测 | Task 6 |
| `.claude/skills/tune-gates/test_multivar_equiv.py` | 真实数据对拍 | Task 7 |
| `.claude/skills/tune-gates/multivar_scan.py` | 进程池 / 分片 / 断点续跑 / 台账 | Task 8 |
| `.claude/skills/tune-gates/region_core.py` | 格张量 / 打分 / 邻域 / bootstrap / 校正 | Task 9、10 |
| `.claude/skills/tune-gates/test_region_core.py` | 合成数据单测 | Task 9、10 |
| `.claude/skills/tune-gates/region_find.py` | 图 / 报告 / cells.csv | Task 10 |
| `.claude/skills/tune-gates/SKILL.md` | 第 4 步与红线 | Task 11 |
| `docs/research/2026-08-25_multivar-bb_v1/repro/compare_longtable_vs_scan.py` | 端到端对拍脚本 | Task 12 |
| `docs/research/2026-08-25_multivar-bb_v1/final_report.md` 及产出 | 端到端 | Task 12 |
| `.claude/skills/tune-gates/reference.md` | 操作卡（端到端之后） | Task 13 |

---

### Task 0: 环境准备 + 参照底座落盘 + 预存失败名单

**Files:**
- Create: `docs/research/2026-08-25_multivar-bb_v1/ref_params.json`
- Create: `docs/research/2026-08-25_multivar-bb_v1/baseline_tests.md`
- Modify: `pyproject.toml`（`uv add pyarrow`）

**Interfaces:**
- Produces: `datasets/pkls/*.pkl` 在本 worktree 可读；`outputs/path2_web/scans/` 存在；`ref_params.json` 供后续全部脚本作 `REF_PARAMS`。

- [ ] **Step 1: 符号链接数据、建输出目录**

```bash
test -e datasets || ln -s /home/yu/PycharmProjects/Trade_Strategy/datasets datasets
mkdir -p outputs/path2_web/scans docs/research/2026-08-25_multivar-bb_v1/repro
ls datasets/pkls | wc -l     # 期望 8325
git status --short           # 期望空(datasets/outputs 已 gitignore)
```

- [ ] **Step 2: 加 pyarrow**

```bash
uv add pyarrow
uv run python -c "import pyarrow, pandas as pd; pd.DataFrame({'a':[1]}).to_parquet('/tmp/claude-1000/_t.parquet'); print('ok')"
```
Expected: 打印 `ok`。

- [ ] **Step 3: 参照底座参数快照**

创建 `docs/research/2026-08-25_multivar-bb_v1/ref_params.json`（内容 = OAT 底座 `tune-*-buf250` scan 文件的 `params_snapshot`，注意 tb 的 `max_window=20 / judged_measure=low / scb_mode=rising`、bo 的 `total_window=20 / min_side_bars=6`，均**不是** `Params.default()`）：

```json
{
  "bo": {"total_window": 20, "min_side_bars": 6, "min_relative_height": 0.2, "exceed_threshold": 0.003,
         "peak_supersede_threshold": 0.01, "vol_baseline_period": 63, "peak_measure": "high", "breakout_measure": "close"},
  "burst": {"gap_max": 8, "vol_baseline_period": 63, "min_bos": 1, "first_drought_min": 0, "distinct_pk_min": 1,
            "vol_spike_min": 0, "peak_age_min": 0},
  "tb": {"max_start_gap": 7, "max_window": 20, "atr_window": 14, "big_rise_k": 5, "stop_confirm_bars": 2,
         "judged_measure": "low", "reference_measure": "close", "scb_mode": "rising", "anchor_mode": "span_min",
         "max_day_drop_pct": null},
  "edges": {}
}
```

验证能重建：
```bash
uv run python -c "
import json; from path2_apps.bb_v1.params import Params
p = Params.from_dict(json.load(open('docs/research/2026-08-25_multivar-bb_v1/ref_params.json')), strict=True); print(p.tb.scb_mode, p.bo.total_window)"
```
Expected: `rising 20`。

- [ ] **Step 4: 记录改代码前的测试基线**

```bash
uv run pytest tests/path2 tests/path2_web -q 2>&1 | tail -15
```
把输出里的失败测试名逐条抄进 `docs/research/2026-08-25_multivar-bb_v1/baseline_tests.md`（格式：一行一个 `<文件>::<测试名>`，另起一段写 passed/failed 总数）。已知可能预存：`test_throwback_debug_anchor_kinds`（4 项）、`test_params`（1 项）。后续每个 Task 的"全 PASS"都指**除本名单外**全 PASS。

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock docs/research/2026-08-25_multivar-bb_v1/ref_params.json docs/research/2026-08-25_multivar-bb_v1/baseline_tests.md
git commit -m "chore(tune): 多维稳健区 v2 环境准备——pyarrow、参照底座快照、预存失败名单"
```

---

### Task 1: `calculate_atr` 向量化 + 逐值等价测试 + 回归基线采集

**Files:**
- Modify: `path2/calc/atr.py`（`calculate_atr`，文件开头第一个函数）
- Create: `tests/path2/calc/test_atr_equivalence.py`
- Create: `docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py`

**Interfaces:**
- Produces: `calculate_atr(highs, lows, closes, period=14) -> pd.Series` 签名/返回不变（index 同 `closes`，前 `period-1` 为 NaN）。
- Produces: `atr_regress.py`，`MODE="before"|"after"|"compare"`；Task 2 复用。

- [ ] **Step 1: 采集修复前回归基线（改任何代码之前）**

创建 `docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py`：

```python
"""ATR 修复回归脚本:子集 scan 修复前后 match 集 + forward_return 逐项相同。
用法:改 MODE 后 `uv run python docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py`
  before  → 修复前跑,落 outputs/path2_web/scans/atr-regress-before.json
  after   → 修复后跑,落 outputs/path2_web/scans/atr-regress-after.json
  compare → 比对两文件
"""
import json, subprocess, sys, time
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))


def _scan(name: str) -> None:
    from path2_web.scan import run_scan_multi
    from path2_web.serialize import serialize_pattern
    from path2_web.discovery import PatternRegistry
    PID = "bb_v1"
    reg = PatternRegistry()
    mod = reg.get(PID)
    snap = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    p = mod.Params.from_dict(snap, strict=True)          # 宽进底座(where 已在机制下限)
    t0 = time.time()
    run_scan_multi(
        data_dir=str(REPO / "datasets/pkls"),
        pattern_specs_json={PID: serialize_pattern(mod.build_pattern(p))},
        module_paths={PID: reg.module_path(PID)}, pattern_ids=[PID],
        end_nodes={PID: mod.eval_meta(params=p)["end_node"]},
        head_buffer_trading_days=250, label_horizon=40,
        start_date="2024-01-01", end_date="2026-01-01",
        workers=8, ticker_regex=r"^A[A-F]", scan_ts=time.strftime("%Y%m%dT%H%M%S"),
        pattern_params_dicts={PID: p.to_dict()}, params_provenance={PID: "atr-regress"},
        note="ATR 修复回归", name=name,
        price_min=0.5, price_max=30.0, volume_min=10000.0,
        first_passage_enabled=True, first_passage_k=5.0,
        outputs_root=str(REPO / "outputs/path2_web"),
    )
    print(f"{name}: {time.time() - t0:.1f}s")


def _key_set(path: Path) -> dict:
    d = json.loads(path.read_text())
    out = {}
    for r in d["results"]:
        pr = (r.get("per_pattern") or {}).get("bb_v1")
        if not pr:
            continue
        for m in pr["analysis"]["matches"]:
            out[(r["symbol"], m["match_id"])] = m["forward_return"]
    return out


def main() -> None:
    MODE = "before"          # before | after | compare
    scans = REPO / "outputs/path2_web/scans"
    if MODE in ("before", "after"):
        _scan(f"atr-regress-{MODE}")
        return
    a, b = _key_set(scans / "atr-regress-before.json"), _key_set(scans / "atr-regress-after.json")
    assert set(a) == set(b), f"match 集不同: 仅前 {len(set(a) - set(b))} / 仅后 {len(set(b) - set(a))}"
    bad = [k for k in a if not ((a[k] is None and b[k] is None) or
                                (a[k] is not None and b[k] is not None and abs(a[k] - b[k]) < 1e-12))]
    assert not bad, f"forward_return 不等: {bad[:5]}"
    print(f"OK: {len(a)} match 逐项相同")


main()
```

运行（MODE 保持 `before`）：`uv run python docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py`
Expected: 打印 `atr-regress-before: <秒>s`，`outputs/path2_web/scans/atr-regress-before.json` 存在。把秒数记到 `docs/research/2026-08-25_multivar-bb_v1/atr-timing.md`（先建文件，一行 `before 子集 ^A[A-F]: <秒>s`）。

- [ ] **Step 2: 写等价测试（含旧实现作 golden）**

创建 `tests/path2/calc/test_atr_equivalence.py`：

```python
"""calculate_atr 向量化实现与原 pandas 逐行实现逐值等价(atol=1e-12)。"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import calculate_atr

PKL_DIR = Path("datasets/pkls")


def _reference_atr(highs, lows, closes, period=14):
    """原实现(pandas 逐行),作 golden。"""
    prev_close = closes.shift(1)
    tr = pd.concat([highs - lows, (highs - prev_close).abs(), (lows - prev_close).abs()],
                   axis=1).max(axis=1)
    atr = pd.Series(np.nan, index=closes.index, dtype=float)
    if len(tr) < period:
        return atr
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, len(tr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return atr


def _real_frames(n=3):
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    out = []
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:
        df = pd.read_pickle(p)
        if len(df) >= 300:
            out.append(df.iloc[-760:].reset_index(drop=True))
        if len(out) == n:
            break
    return out


@pytest.mark.parametrize("period", [14, 20])
def test_equivalent_on_real_data(period):
    for df in _real_frames():
        a = _reference_atr(df["high"], df["low"], df["close"], period)
        b = calculate_atr(df["high"], df["low"], df["close"], period)
        assert b.index.equals(a.index)
        assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)
        assert np.isnan(b.iloc[: period - 1]).all()


def test_short_input_all_nan():
    s = pd.Series([1.0, 2.0, 3.0])
    out = calculate_atr(s + 1, s - 1, s, period=14)
    assert len(out) == 3 and out.isna().all()


def test_nan_inside_matches_reference():
    rng = np.random.default_rng(0)
    c = pd.Series(100 + rng.standard_normal(120).cumsum())
    h, l = c + 1, c - 1
    h.iloc[30] = np.nan                      # 一根缺高价:TR 按 skipna 取余下两项
    a = _reference_atr(h, l, c, 14)
    b = calculate_atr(h, l, c, 14)
    assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)
```

- [ ] **Step 3: 运行测试确认当前通过（旧实现即 golden）**

Run: `uv run pytest tests/path2/calc/test_atr_equivalence.py -q`
Expected: PASS（4 项）。

- [ ] **Step 4: 向量化实现**

替换 `path2/calc/atr.py` 中 `calculate_atr` 函数体：

```python
def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                  period: int = 14) -> pd.Series:
    """Wilder RMA 平滑的 ATR。

    返回与输入同长 Series(前 period-1 为 NaN,第 period 个为算术均;之后为 Wilder 递推)。
    TR_i = max(H_i - L_i, |H_i - C_{i-1}|, |L_i - C_{i-1}|)
    ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period
    实现:numpy 标量递推(无 pandas 逐行索引),与原 pandas 逐行实现逐值等价(1e-12)。
    NaN 语义同 pandas max(skipna):三项中的 NaN 被忽略;全 NaN 则 TR 为 NaN。
    """
    h = highs.to_numpy(dtype=float)
    l = lows.to_numpy(dtype=float)
    c = closes.to_numpy(dtype=float)
    n = len(c)
    out = np.full(n, np.nan)
    if n < period:
        return pd.Series(out, index=closes.index, dtype=float)
    pc = np.empty(n); pc[0] = np.nan; pc[1:] = c[:-1]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))   # fmax 忽略 NaN
    head = tr[:period]
    out[period - 1] = np.nanmean(head) if np.isnan(head).any() else head.mean()
    a = out[period - 1]
    k = period - 1
    for i in range(period, n):
        a = (a * k + tr[i]) / period
        out[i] = a
    return pd.Series(out, index=closes.index, dtype=float)
```

- [ ] **Step 5: 运行等价测试 + calc/atoms 回归**

Run: `uv run pytest tests/path2/calc tests/path2/atoms -q`
Expected: 全 PASS（除 Task 0 基线名单）。

- [ ] **Step 6: 提交**

```bash
git add path2/calc/atr.py tests/path2/calc/test_atr_equivalence.py docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py docs/research/2026-08-25_multivar-bb_v1/atr-timing.md
git commit -m "perf(calc): calculate_atr 改 numpy 标量递推,逐值等价测试 + ATR 回归基线脚本"
```

---

### Task 2: throwback 三版本 ATR 算一次 + v1 事件 `day_drop` 字段 + 回归对比

**Files:**
- Modify: `path2/atoms/throwback_v1.py`（`_atr_at`；`evaluate_throwback` 签名与 `atr = _atr_at(df, bo_idx - 1, atr_window)` 处；`ThrowbackEventV1` 字段；`detect`）
- Modify: `path2/atoms/throwback_v0.py`（`_atr_at`；`evaluate_throwback`；`detect`）
- Modify: `path2/atoms/throwback.py`（`_atr_at`；`detect`）
- Create: `tests/path2/atoms/test_throwback_v1_day_drop.py`

**Interfaces:**
- Produces: 三文件 `_atr_at(atr: pd.Series, idx: int) -> float`（越界/NaN → 0.0）。
- Produces: `throwback_v1.evaluate_throwback(..., atr: Optional[pd.Series] = None, ...)`、`throwback_v0.evaluate_throwback(..., atr: Optional[pd.Series] = None, ...)`——`None` 时函数内自算（既有直接调用方不变），`detect` 传入预算序列。
- Produces: `ThrowbackEventV1.day_drop: float`（`_revert_max_day_drop(df, last_bo.end_idx, r.start_idx)`，**无论 `max_day_drop_pct` 是否为 None 都计算并落字段**；判据不变）。

- [ ] **Step 1: throwback_v1 —— `_atr_at` 与 `evaluate_throwback`**

用 `grep -n "_atr_at\|calculate_atr" path2/atoms/throwback_v1.py` 定位。`_atr_at` 改为：
```python
def _atr_at(atr: pd.Series, idx: int) -> float:
    """预算 ATR 序列在 idx 处的值;越界/NaN → 0.0。"""
    if idx < 0 or idx >= len(atr):
        return 0.0
    v = float(atr.iat[idx])
    return v if v == v else 0.0
```
`evaluate_throwback` 的关键字参数在 `scb_mode: str = "no_new_low",` 之后增加一行 `atr: Optional[pd.Series] = None,`；函数体里
```python
    atr = _atr_at(df, bo_idx - 1, atr_window)     # ★ bo-1:避开 bo 当根异常 TR
    if atr <= 0.0:
        return None
```
改为
```python
    atr_series = atr if atr is not None else calculate_atr(df['high'], df['low'], df['close'], atr_window)
    atr = _atr_at(atr_series, bo_idx - 1)          # ★ bo-1:避开 bo 当根异常 TR
    if atr <= 0.0:
        return None
```
（之后函数体继续用标量 `atr`，无需改名。）docstring 补一句「atr:预算的 ATR 序列(detect 每股算一次下传);None 时自算」。

- [ ] **Step 2: throwback_v1 —— `day_drop` 字段 + `detect`**

`ThrowbackEventV1` 在 `outcome: str = "rise"` 之后加：
```python
    day_drop: float = 0.0   # 回踩段最大单日跌幅(_revert_max_day_drop 口径),恒计算;毒药闸开关只决定是否据此不产事件
```
docstring 的「输出字段」列表补一行 `- day_drop: 回踩段 [revert_idx, confirm] 内最大单日跌幅(pct),供 where / 事后切`。

`detect`：在 `for burst in burst_stream:` 之前加
```python
        atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])
```
调用改为 `r = evaluate_throwback(last_bo, df, anchor=anchor, atr=atr_series, on_gate=self.on_gate, **tb_kw)`。毒药闸块改为**先算、再按开关判**：
```python
            if r is not None:
                day_drop = _revert_max_day_drop(df, last_bo.end_idx, r.start_idx)
                if self._max_day_drop_pct is not None and day_drop >= self._max_day_drop_pct:
                    _emit_tb_gate(   # ...原有参数原样保留...
```
（原 `if self._max_day_drop_pct is not None:` / `day_drop = ...` / `if day_drop >= ...:` 三层合并为上述两行；`_emit_tb_gate(...)` 及其后的 `continue` 原样。）事件构造加 `day_drop=day_drop`：
```python
                events.append(ThrowbackEventV1(
                    start_idx=start, end_idx=r.end_idx,
                    confirm_idx=start,
                    anchor_bo_id=src_id,
                    outcome=r.outcome,
                    day_drop=day_drop))
```

- [ ] **Step 3: throwback_v0**

同 Step 1 三处改法：`_atr_at(atr, idx)`；`evaluate_throwback` 在 `scb_measure: str = "low",` 后加 `atr: Optional[pd.Series] = None,`，`atr = _atr_at(df, bo_idx - 1, atr_window)` 处改为先取/算序列再取值；`detect` 在循环前 `atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])`，调用改 `evaluate_throwback(last_bo, df, anchor=anchor, atr=atr_series, on_gate=self.on_gate, **self._kw)`。

- [ ] **Step 4: throwback.py**

`_atr_at` 改为同签名；`detect` 在 `events = []` 之后、`for bo in bo_stream:` 之前加 `atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])`；`atr = _atr_at(df, bo_idx - 1, self._kw['atr_window'])` 改为 `atr = _atr_at(atr_series, bo_idx - 1)`。`grep -n "_atr_at(\|calculate_atr(" path2/atoms/throwback.py` 确认没有其他调用点。

- [ ] **Step 5: `day_drop` 测试**

创建 `tests/path2/atoms/test_throwback_v1_day_drop.py`：
```python
"""ThrowbackEventV1.day_drop 恒计算,与 _revert_max_day_drop 逐事件一致;闸关时事件集含闸开时被删的样本。"""
from pathlib import Path
import pandas as pd
import pytest

from path2.dag.engine import run_streams
from path2.atoms.throwback_v1 import _revert_max_day_drop
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params

PKL_DIR = Path("datasets/pkls")


def _wins(n=40):
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    out = []
    for p in sorted(PKL_DIR.glob("A*.pkl"))[:200]:
        df = pd.read_pickle(p)
        if len(df) >= 400:
            out.append(df.iloc[-600:].reset_index())
        if len(out) == n:
            break
    return out


def _wide(dpct):
    d = Params.default().to_dict()
    d["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)
    d["tb"]["max_day_drop_pct"] = dpct
    return Params.from_dict(d)


def test_day_drop_matches_revert_function():
    p = _wide(None)
    spec = build_pattern(p)
    seen = 0
    for win in _wins():
        st = run_streams(spec, win, p)
        by_id = {e.instance_id: e for e in st["bo"]}
        for tb in st["tb"]:
            bo = by_id[tb.anchor_bo_id]
            assert tb.day_drop == _revert_max_day_drop(win, bo.end_idx, tb.start_idx)
            seen += 1
    assert seen > 0


def test_gate_on_is_subset_by_day_drop():
    p_off, p_on = _wide(None), _wide(0.2)
    s_off, s_on = build_pattern(p_off), build_pattern(p_on)
    for win in _wins():
        off = {(e.start_idx, e.end_idx, e.anchor_bo_id) for e in run_streams(s_off, win, p_off)["tb"] if e.day_drop < 0.2}
        on = {(e.start_idx, e.end_idx, e.anchor_bo_id) for e in run_streams(s_on, win, p_on)["tb"]}
        assert off == on
```

Run: `uv run pytest tests/path2/atoms/test_throwback_v1_day_drop.py -q`
Expected: PASS（2 项；若无数据 skip）。

- [ ] **Step 6: 全量 atoms/web 测试**

Run: `uv run pytest tests/path2 tests/path2_web -q`
Expected: 除基线名单外全 PASS（既有测试直接调 `evaluate_throwback` 不传 `atr`，走自算分支；若有测试精确断言 `ThrowbackEventV1` 字段集合，按失败信息把 `day_drop` 加进期望）。

- [ ] **Step 7: 回归对比 + 计时**

`atr_regress.py` 的 `MODE` 改 `"after"` 运行，再改 `"compare"` 运行。
Expected: `compare` 打印 `OK: N match 逐项相同`。把 after 秒数追加到 `atr-timing.md`（`after 子集 ^A[A-F]: <秒>s`）。运行结束把 `MODE` 改回 `"before"`。

- [ ] **Step 8: 提交**

```bash
git add path2/atoms/throwback_v1.py path2/atoms/throwback_v0.py path2/atoms/throwback.py tests/path2/atoms/test_throwback_v1_day_drop.py docs/research/2026-08-25_multivar-bb_v1/atr-timing.md
git commit -m "perf(atoms): throwback v0/v1/v2 每股算一次 ATR 序列;v1 事件恒落 day_drop 字段(闸开关只管产不产);子集回归逐项相同"
```

---

### Task 3: `eval.py` 首穿尺度 M 可外传

**Files:**
- Modify: `path2/eval.py`（`match_first_passage`、`random_day_first_passage`）
- Create: `tests/path2/test_eval_M_param.py`

**Interfaces:**
- Produces: `match_first_passage(match, end_node, df, horizon, k=DEFAULT_FP_K, sample_window=None, M=None)`；`random_day_first_passage(ticker, df, start_ts, end_ts, horizon, k=DEFAULT_FP_K, n_days=RANDOM_DAY_K, seed=FIRST_PASSAGE_SEED, M=None)`。`M`（`np.ndarray`，`rolling_atr_pct_nanmedian(high, low, close, 20).values`）为 None 时内算，行为逐字不变。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/test_eval_M_param.py`：
```python
"""match_first_passage / random_day_first_passage 的 M 外传与内算逐值相等。"""
from pathlib import Path
import pandas as pd
import pytest

from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.dag.engine import analyze
from path2.eval import match_first_passage, random_day_first_passage
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params

PKL_DIR = Path("datasets/pkls")


def _scene():
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    d = Params.default().to_dict()
    d["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)
    d["tb"]["max_day_drop_pct"] = None
    p = Params.from_dict(d)
    spec = build_pattern(p)
    for pk in sorted(PKL_DIR.glob("A*.pkl"))[:300]:
        df = pd.read_pickle(pk)
        if len(df) < 400:
            continue
        win = df.iloc[-600:].reset_index()
        res = analyze(spec, win, p)
        if res.matches:
            return pk.stem, win, res
    pytest.skip("无命中股")


def test_match_first_passage_M_param_equal():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    for m in res.matches:
        a = match_first_passage(m, "tb", win, 40, 5.0, sample_window=(100, 550))
        b = match_first_passage(m, "tb", win, 40, 5.0, sample_window=(100, 550), M=M)
        assert a == b


def test_random_day_M_param_equal():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    s, e = pd.to_datetime(win["date"].iat[100]), pd.to_datetime(win["date"].iat[550])
    assert random_day_first_passage(sym, win, s, e, 40, 5.0) == random_day_first_passage(sym, win, s, e, 40, 5.0, M=M)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/test_eval_M_param.py -q`
Expected: FAIL（`TypeError: ... unexpected keyword argument 'M'`）。

- [ ] **Step 3: 实现**

`match_first_passage` 签名末尾加 `M: Optional["np.ndarray"] = None,`；函数体 `M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values` 改为
```python
    if M is None:
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
```
`random_day_first_passage` 同样加 `M: Optional["np.ndarray"] = None,` 并同样改内算处。两函数 docstring 各补一句「M:外传的波动率尺度(每股算一次复用);None 时内算」。

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/path2/test_eval_M_param.py tests/path2/test_eval.py -q`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add path2/eval.py tests/path2/test_eval_M_param.py
git commit -m "perf(eval): match_first_passage / random_day_first_passage 可外传 M(每股算一次),None 时行为不变"
```

---

### Task 4: scan 文件 per-match 增加 `buy_date` 与 `first_passage`

**Files:**
- Modify: `path2_web/serialize.py`（`serialize_per_pattern_result`：`ret_by_id`/`leaf_by_id` 字典区、首穿块、`_with_labels`）
- Create: `tests/path2_web/test_serialize_match_fp.py`

**Interfaces:**
- Produces: 每个 `analysis["matches"][i]` 新增 `"buy_date": str`（`YYYY-MM-DD`，end_node 事件起始日）与 `"first_passage": {"up","down","both","none"} | None`。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2_web/test_serialize_match_fp.py`：
```python
"""serialize_per_pattern_result:match 级 buy_date + first_passage 四态。
不变式:非 None 的 first_passage 四态逐项求和 == match_fp_counts。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta
from path2_apps.bb_v1.params import Params
from path2.dag.engine import analyze as engine_analyze

PKL_DIR = Path("datasets/pkls")


def _wide():
    d = Params.default().to_dict()
    d["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)
    d["tb"]["max_day_drop_pct"] = None
    return Params.from_dict(d)


@pytest.fixture
def scene():
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    p = _wide(); spec = build_pattern(p)
    for pk in sorted(PKL_DIR.glob("A*.pkl"))[:300]:
        df = pd.read_pickle(pk)
        if len(df) < 400:
            continue
        win = df.iloc[-600:].reset_index()
        res = engine_analyze(spec, win, p)
        if res.matches:
            return res, eval_meta(p), win, pd.to_datetime(win["date"].iat[0]), pd.to_datetime(win["date"].iat[-1])
    pytest.skip("无命中股")


def _run(scene, **kw):
    res, meta, win, s, e = scene
    return serialize_per_pattern_result(res, end_node=meta["end_node"], label_horizon=5,
                                        win=win, start_ts=s, end_ts=e, **kw)


def test_fields_present_and_sum_invariant(scene):
    out = _run(scene)
    ms = out["analysis"]["matches"]
    assert ms
    tot = {"up": 0, "down": 0, "both": 0, "none": 0}
    for m in ms:
        assert isinstance(m["buy_date"], str) and len(m["buy_date"]) == 10
        fp = m["first_passage"]
        assert fp is None or set(fp) == set(tot)
        if fp is not None:
            for k in tot:
                tot[k] += fp[k]
    assert tot == out["match_fp_counts"]
    assert any(m["first_passage"] is not None for m in ms)


def test_buy_date_is_end_node_start(scene):
    res, meta, win, *_ = scene
    out = _run(scene)
    by_id = {m.match_id: m for m in res.matches}
    for md in out["analysis"]["matches"]:
        ev = by_id[md["match_id"]].node_index[meta["end_node"].split(".")[0]]
        assert md["buy_date"] == str(pd.to_datetime(win["date"].iat[ev.start_idx]).date())


def test_disabled_first_passage_gives_none(scene):
    out = _run(scene, first_passage_enabled=False)
    assert all(m["first_passage"] is None for m in out["analysis"]["matches"])
    assert out["match_fp_counts"] == {"up": 0, "down": 0, "both": 0, "none": 0}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_web/test_serialize_match_fp.py -q`
Expected: FAIL（`KeyError: 'buy_date'`）。

- [ ] **Step 3: 实现**

在 `serialize_per_pattern_result`：
1. `leaf_by_id: dict = {}` 旁增加 `fp_by_id: dict = {}` 与 `date_by_id: dict = {}`。
2. `leaf_by_id[m.match_id] = leaf_ev.instance_id` 之后加 `date_by_id[m.match_id] = str(pd.to_datetime(win["date"].iat[leaf_ev.start_idx]).date())`。
3. 首穿块改为：
```python
        fp_by_id[m.match_id] = None
        if first_passage_enabled:
            if leaf_ev.instance_id not in seen_fp_leaves:
                seen_fp_leaves.add(leaf_ev.instance_id)
                m_counts = match_first_passage(
                    m, end_node, win, label_horizon, first_passage_k,
                    sample_window=sample_window)
                for s in ("up", "down", "both", "none"):
                    match_fp_counts[s] += m_counts[s]
                fp_by_id[m.match_id] = {s: int(m_counts[s]) for s in ("up", "down", "both", "none")}
```
4. `_with_labels` 返回 dict 增加 `"buy_date": date_by_id[md["match_id"]], "first_passage": fp_by_id[md["match_id"]]`。
5. 文件顶部若无 `import pandas as pd` 则补上。

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/path2_web -q`
Expected: 除基线名单外全 PASS（若既有测试精确断言 match keys 集合，把两个新键加进期望）。

- [ ] **Step 5: 提交**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize_match_fp.py
git commit -m "feat(web): scan 文件 match 级增加 buy_date 与 first_passage 四态"
```

---

### Task 5: `BurstDetector.filter_params` 协议声明

**Files:**
- Modify: `path2/atoms/breakout.py`（`class BurstDetector` 类体开头）
- Create: `tests/path2/atoms/test_burst_filter_params.py`

**Interfaces:**
- Produces: `BurstDetector.filter_params: ClassVar[dict[str, tuple[str, str]]] = {"min_bos": ("count", ">=")}`——语义：以该参数**最松值**构造后按 `getattr(event, field) op value` 过滤，与直接以 `value` 构造的事件集**逐事件相等**（含 members / 全部字段）。Task 6 的探针按 `dim.field in type(det).filter_params` 判 F 类。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/atoms/test_burst_filter_params.py`：
```python
"""BurstDetector.filter_params 协议:min_bos 事后按 count 过滤 == 直接以 min_bos 构造(逐事件全字段相等)。"""
import dataclasses
import numpy as np
import pandas as pd
import pytest

from path2.atoms.breakout import BODetector, BurstDetector, BOEvent
from path2.runner import run


def _df(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 10 + np.abs(rng.standard_normal(n).cumsum())
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="B"),
                         "open": c, "high": c * 1.02, "low": c * 0.98, "close": c,
                         "volume": rng.integers(1000, 5000, n).astype(float)})


def _bos(df):
    bos = list(run(BODetector(min_relative_height=0.02, exceed_threshold=0.001), df))
    if len(bos) < 8:
        # 合成不出足够 bo 时直接造流:三簇(间距 1)+ 孤立点
        bos = [BOEvent(start_idx=i, end_idx=i, confirm_idx=i, drought=3) for i in
               [50, 51, 52, 53, 90, 91, 92, 140, 141, 200]]
    return bos


def _key(e):
    return dataclasses.astuple(dataclasses.replace(e, instance_id=None, node_id=None)) \
        if hasattr(e, "instance_id") else dataclasses.astuple(e)


@pytest.mark.parametrize("gap_max", [1, 5])
@pytest.mark.parametrize("m", [2, 3, 4])
def test_posthoc_filter_equals_direct(gap_max, m):
    df = _df(); bos = _bos(df)
    field, op = BurstDetector.filter_params["min_bos"]
    assert (field, op) == ("count", ">=")
    loose = list(run(BurstDetector(gap_max=gap_max, min_bos=1, vol_baseline_period=5), bos, df))
    direct = list(run(BurstDetector(gap_max=gap_max, min_bos=m, vol_baseline_period=5), bos, df))
    filtered = [e for e in loose if getattr(e, field) >= m]
    assert [_key(e) for e in filtered] == [_key(e) for e in direct]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_burst_filter_params.py -q`
Expected: FAIL（`AttributeError: type object 'BurstDetector' has no attribute 'filter_params'`）。

- [ ] **Step 3: 实现**

`class BurstDetector` 类体在 `on_gate = None` 之后加：
```python
    # 过滤型构造参数声明(tune-gates multivar 协议):param → (事件字段, op)。
    # 语义:以该参数最松值构造,事后按 `getattr(event, field) op value` 过滤,与直接以 value
    # 构造得到的事件集逐事件相等(含 members 与全部字段)——min_bos 只在 emit 处把关
    # (`k - head + 1 >= self.min_bos`),不参与切串,故成立。声明者对等价性负责
    # (tests/path2/atoms/test_burst_filter_params.py)。
    filter_params: ClassVar[dict] = {"min_bos": ("count", ">=")}
```
（文件已 `from typing import ClassVar`，否则补 import。）docstring 末尾加一句「min_bos 为过滤型参数（见 filter_params）」。

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/path2/atoms/test_burst_filter_params.py tests/path2/atoms/test_burst.py -q`
Expected: 全 PASS。若 `_key` 因事件字段含不可 hash 对象报错，改为比较 `repr(e)` 去掉 `instance_id`/`node_id` 两项后的字符串。

- [ ] **Step 5: 提交**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_burst_filter_params.py
git commit -m "feat(atoms): BurstDetector 声明 filter_params={min_bos:(count,>=)},事后过滤等价测试"
```

---

### Task 6: `multivar_core.py` 第一部分——探针分类 / 影响集 / 组合展开

**Files:**
- Create: `.claude/skills/tune-gates/multivar_core.py`
- Create: `.claude/skills/tune-gates/test_multivar_core.py`

**Interfaces:**
- Produces（Task 7/8 消费，签名精确）：
  - `Dim = tuple[str, str]`（`(section, field)`）；`col_of(dim) -> str`（`"section.field"`）；`node_col(node_id, field) -> str`（`"node.field"`）。
  - `probe_dim(mod, base_dict, dim, alt_value) -> Probe`，`Probe(detector_nodes: tuple[str,...], where_clauses: tuple[tuple[str,str,str],...], edges_changed: bool)`；`where_clauses` 元素 `(node_id, field, op)`。
  - `classify(mod, base_dict, scan_grid: dict[Dim, list], where_levels: dict[Dim, list]) -> Classification`：字段 `kinds: dict[Dim, str]`（`"W"|"F"|"D"|"E"|"unknown"`）、`detector_nodes: dict[Dim, tuple[str,...]]`、`where_fields: dict[Dim, tuple[str,str,str]]`（W 维 → `(node, field, op)`）、`filter_fields: dict[Dim, tuple[str,str,str]]`（F 维 → `(node, field, op)`）。`scan_grid` 含 W 维 → `ValueError`；`where_levels` 含非 W 维 → `ValueError`；`unknown` → `ValueError`。
  - `check_where_axes(spec, where_fields) -> None`：where 所在 node 是任一 `NegationEdge.dst` → `ValueError`。
  - `upstream_closure(spec, node_id) -> tuple[str,...]`（含自身，沿 `consumes_stream` 向上）。
  - `influence_dims(spec, cls: Classification, scan_grid) -> dict[str, tuple[Dim,...]]`（node_id → 影响其流的 D 类维，按 `scan_grid` 键序；F 维不含）。
  - `detection_combos(scan_grid, cls) -> list[dict[Dim, object]]`（去掉 F 维的笛卡尔积，保持 `scan_grid` 键序）。
  - `apply_overrides(base_dict, wide_overrides: dict[str, dict], assignments: dict[Dim, object]) -> dict`（深拷贝后依次覆盖）。

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/tune-gates/test_multivar_core.py`：
```python
# -*- coding: utf-8 -*-
"""multivar_core 纯函数单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_multivar_core.py -q
"""
import json, subprocess, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from multivar_core import (Dim, apply_overrides, check_where_axes, classify, col_of,  # noqa: E402
                           detection_combos, influence_dims, probe_dim, upstream_closure)
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402

BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
             ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"): [4, 8, 12, 20],
             ("burst", "min_bos"): [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"): [0, 1, 2, 3],
             ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                ("burst", "distinct_pk_min"): [1, 3, 4],
                ("burst", "vol_spike_min"): [0, 10, 15],
                ("burst", "peak_age_min"): [0, 125]}


def test_probe_where_dim():
    pr = probe_dim(mod, BASE, ("burst", "first_drought_min"), 20)
    assert pr.detector_nodes == () and not pr.edges_changed
    assert pr.where_clauses == (("burst", "first_drought", ">="),)


def test_probe_detector_dims():
    assert probe_dim(mod, BASE, ("burst", "gap_max"), 12).detector_nodes == ("burst",)
    assert probe_dim(mod, BASE, ("bo", "exceed_threshold"), 0.01).detector_nodes == ("bo",)
    pr = probe_dim(mod, BASE, ("tb", "max_start_gap"), 9)
    assert pr.detector_nodes == ("tb",) and pr.edges_changed      # 同时是 edge max_gap 的 SSoT


def test_classify_bb_v1():
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    assert cls.kinds[("burst", "min_bos")] == "F"
    assert cls.filter_fields[("burst", "min_bos")] == ("burst", "count", ">=")
    for d in [("bo", "min_relative_height"), ("bo", "exceed_threshold"), ("burst", "gap_max"),
              ("tb", "stop_confirm_bars"), ("tb", "big_rise_k")]:
        assert cls.kinds[d] == "D"
    for d in WHERE_LEVELS:
        assert cls.kinds[d] == "W"
    assert cls.where_fields[("burst", "vol_spike_min")] == ("burst", "max_bar_vol_ratio", ">=")


def test_classify_rejects_where_in_scan_grid():
    bad = dict(SCAN_GRID); bad[("burst", "first_drought_min")] = [0, 20]
    with pytest.raises(ValueError):
        classify(mod, BASE, bad, {})


def test_classify_rejects_detector_dim_in_where_levels():
    with pytest.raises(ValueError):
        classify(mod, BASE, SCAN_GRID, {("burst", "gap_max"): [4, 8]})


def test_upstream_closure_and_influence():
    spec = mod.build_pattern(mod.Params.from_dict(BASE))
    assert upstream_closure(spec, "tb") == ("tb", "burst", "bo")
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    inf = influence_dims(spec, cls, SCAN_GRID)
    assert inf["bo"] == (("bo", "min_relative_height"), ("bo", "exceed_threshold"))
    assert inf["burst"] == inf["bo"] + (("burst", "gap_max"),)
    assert inf["tb"] == inf["burst"] + (("tb", "stop_confirm_bars"), ("tb", "big_rise_k"))


def test_detection_combos_excludes_filter_dims():
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    combos = detection_combos(SCAN_GRID, cls)
    assert len(combos) == 4 ** 5
    assert ("burst", "min_bos") not in combos[0]
    assert list(combos[0]) == [d for d in SCAN_GRID if d != ("burst", "min_bos")]


def test_apply_overrides_deep_copies():
    out = apply_overrides(BASE, {"tb": {"max_day_drop_pct": None}}, {("burst", "gap_max"): 12})
    assert out["burst"]["gap_max"] == 12 and out["tb"]["max_day_drop_pct"] is None
    assert BASE["burst"]["gap_max"] == 8


def test_check_where_axes_rejects_negation_target():
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec
    from path2.dag.edges import TemporalEdge, NegationEdge
    from path2.dag import where as W
    from path2.atoms.breakout import BODetector, BurstDetector
    nodes = (NodeSpec("bo", BODetector(), render_grid="price"),
             NodeSpec("burst", BurstDetector(gap_max=5, min_bos=1), consumes_stream="bo",
                      children={"members": "bo"},
                      where=(("fd", W.attr("first_drought", ">=", 0)),)),
             NodeSpec("bo2", BODetector(), render_grid="price"))
    spec = PatternSpec(pattern_id="t", nodes=nodes,
                       edges=(TemporalEdge("bo2", "burst", min_gap=1, max_gap=50),
                              NegationEdge("bo2", "burst", min_gap=1, max_gap=5)))
    with pytest.raises(ValueError):
        check_where_axes(spec, {("burst", "first_drought_min"): ("burst", "first_drought", ">=")})
    check_where_axes(spec, {})    # 空 where 不报错


def test_col_of():
    assert col_of(("burst", "gap_max")) == "burst.gap_max"
```
（`test_check_where_axes_rejects_negation_target` 的合成 spec 若因 `PatternSpec` 校验（如 NegationEdge 端点规则）构造失败，改用 `spec.edges` 的最小 stub：`types.SimpleNamespace(edges=(NegationEdge("bo2", "burst"),), nodes=())`——`check_where_axes` 只读 `spec.edges`。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_core.py -q`
Expected: FAIL（`ModuleNotFoundError: multivar_core`）。

- [ ] **Step 3: 实现**

创建 `.claude/skills/tune-gates/multivar_core.py`：
```python
# -*- coding: utf-8 -*-
"""multivar_scan 的纯函数层(无 I/O):参数分类探针 / 影响集 / 组合展开 / 单股反转循环。

设计(spec v2 §3):pattern 无关——只依赖 PatternRegistry 暴露的 mod(build_pattern / Params /
eval_meta)、NodeSpec.consumes_stream 拓扑与 Params 的 section 约定。

参数四类(spec §1):W where 阈值(联合空间免费轴)/ F 过滤型(detector 声明 filter_params,
按最松档构造、事后按字段谓词切)/ D detector 构造参数(结构型与状态机型统一处理:上游流缓存、
本级及下游重跑)/ E 只改 edge(只影响 solve)。分类靠**探针**:把某维改成另一档,比较两份
PatternSpec 里各 node detector 的实例属性、where 子句阈值与 edges 哪些变了——不猜签名、不看名字。
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.dag._graph import detector_topo_order
from path2.dag._reify import reify
from path2.dag._solve import compile_plan, solve
from path2.dag.edges import NegationEdge
from path2.dag.engine import annotate_stream
from path2.eval import (_resolve_end_events, match_first_passage, match_forward_drawdowns,
                        match_forward_returns)
from path2.runner import run

Dim = tuple  # (section, field)
STATES = ("up", "down", "both", "none")


def col_of(dim: Dim) -> str:
    return f"{dim[0]}.{dim[1]}"


def node_col(node_id: str, field: str) -> str:
    return f"{node_id}.{field}"


# ---------------------------------------------------------------- 探针分类
def _det_state(det) -> str:
    """detector 实例的可比较状态:非可调用实例属性的 repr(排序)。"""
    items = sorted((k, repr(v)) for k, v in vars(det).items() if not callable(v))
    return repr(items)


def _iter_attr_preds(pred):
    """递归展开 where 组合子,产出 meta.kind=='attr' 的叶谓词 meta。"""
    meta = getattr(pred, "meta", None) or {}
    if meta.get("kind") == "attr":
        yield meta
    for c in getattr(pred, "children", ()):
        yield from _iter_attr_preds(c)


def _where_table(spec) -> dict[tuple[str, str, str], list]:
    """{(node, field, op): [threshold, ...]}(同一 (node,field,op) 可能多子句)。"""
    out: dict = {}
    for n in spec.nodes:
        for _cid, fn in n.where:
            for m in _iter_attr_preds(fn):
                out.setdefault((n.node_id, m["field"], m["op"]), []).append(m["threshold"])
    return out


@dataclass(frozen=True)
class Probe:
    detector_nodes: tuple      # 该维改变了哪些 node 的 detector 实例状态
    where_clauses: tuple       # 该维改变了哪些 where 子句 (node, field, op)
    edges_changed: bool


def apply_overrides(base_dict: dict, wide_overrides: dict, assignments: dict) -> dict:
    d = copy.deepcopy(base_dict)
    for sec, kv in (wide_overrides or {}).items():
        d.setdefault(sec, {}).update(kv)
    for (sec, field), v in assignments.items():
        d.setdefault(sec, {})[field] = v
    return d


def probe_dim(mod, base_dict: dict, dim: Dim, alt_value) -> Probe:
    p0 = mod.Params.from_dict(base_dict, strict=True)
    p1 = mod.Params.from_dict(apply_overrides(base_dict, {}, {dim: alt_value}), strict=True)
    s0, s1 = mod.build_pattern(p0), mod.build_pattern(p1)
    by0 = {n.node_id: n for n in s0.nodes}
    det_nodes = tuple(n.node_id for n in s1.nodes
                      if n.detector is not None and by0[n.node_id].detector is not None
                      and _det_state(n.detector) != _det_state(by0[n.node_id].detector))
    w0, w1 = _where_table(s0), _where_table(s1)
    clauses = tuple(sorted(k for k in set(w0) | set(w1) if w0.get(k) != w1.get(k)))
    return Probe(det_nodes, clauses, repr(s0.edges) != repr(s1.edges))


@dataclass
class Classification:
    kinds: dict            # Dim → "W" | "F" | "D" | "E"
    detector_nodes: dict   # Dim → tuple[node_id]
    where_fields: dict     # W 维 → (node, field, op)
    filter_fields: dict    # F 维 → (node, field, op)


def _alt_of(levels, base_v):
    for v in levels:
        if v != base_v:
            return v
    raise ValueError(f"档位 {levels} 与底座值 {base_v} 无差异,无法探针")


def classify(mod, base_dict: dict, scan_grid: dict, where_levels: dict) -> Classification:
    kinds, det_nodes, where_fields, filter_fields = {}, {}, {}, {}
    spec0 = mod.build_pattern(mod.Params.from_dict(base_dict, strict=True))
    dets = {n.node_id: n.detector for n in spec0.nodes if n.detector is not None}
    for dim, levels in list(scan_grid.items()) + list(where_levels.items()):
        base_v = base_dict[dim[0]][dim[1]]
        pr = probe_dim(mod, base_dict, dim, _alt_of(levels, base_v))
        det_nodes[dim] = pr.detector_nodes
        if pr.where_clauses and not pr.detector_nodes and not pr.edges_changed:
            if len(pr.where_clauses) != 1:
                raise ValueError(f"{col_of(dim)} 同时驱动多条 where 子句 {pr.where_clauses},不能作单轴")
            kinds[dim] = "W"; where_fields[dim] = pr.where_clauses[0]
        elif pr.detector_nodes:
            fp = None
            for nid in pr.detector_nodes:
                decl = getattr(type(dets[nid]), "filter_params", {}) or {}
                if dim[1] in decl:
                    fp = (nid,) + tuple(decl[dim[1]])
            if fp is not None and len(pr.detector_nodes) == 1 and not pr.edges_changed:
                kinds[dim] = "F"; filter_fields[dim] = fp
            else:
                kinds[dim] = "D"
        elif pr.edges_changed:
            kinds[dim] = "E"
        else:
            raise ValueError(f"{col_of(dim)} 改档后 detector/where/edges 都没变:参数未被消费或 detector 未把它存为实例属性")
    for dim in scan_grid:
        if kinds[dim] == "W":
            raise ValueError(f"{col_of(dim)} 是 where 阈值(W),不进 SCAN_GRID;放 WHERE_LEVELS")
    for dim in where_levels:
        if kinds[dim] != "W":
            raise ValueError(f"{col_of(dim)} 不是纯 where 阈值(探针:{kinds[dim]}),不能作 WHERE_LEVELS 轴")
    return Classification(kinds, det_nodes, where_fields, filter_fields)


def check_where_axes(spec, where_fields: dict) -> None:
    neg_dst = {e.dst for e in spec.edges if isinstance(e, NegationEdge)}
    for dim, (nid, field, _op) in where_fields.items():
        if nid in neg_dst:
            raise ValueError(f"{col_of(dim)} 所在 node {nid!r} 是 NegationEdge 目标,where 收紧可能增加 match,"
                             "不能作长表谓词轴;改为真扫维")


# ---------------------------------------------------------------- 拓扑 / 影响集 / 组合
def upstream_closure(spec, node_id: str) -> tuple:
    by = {n.node_id: n for n in spec.nodes}
    out, cur = [], node_id
    while cur is not None:
        out.append(cur)
        cur = by[cur].consumes_stream
    return tuple(out)


def influence_dims(spec, cls: Classification, scan_grid: dict) -> dict:
    out = {}
    for n in spec.nodes:
        if n.detector is None:
            continue
        closure = set(upstream_closure(spec, n.node_id))
        out[n.node_id] = tuple(d for d in scan_grid
                               if cls.kinds[d] == "D" and closure & set(cls.detector_nodes[d]))
    return out


def detection_combos(scan_grid: dict, cls: Classification) -> list:
    dims = [d for d in scan_grid if cls.kinds[d] != "F"]
    return [dict(zip(dims, vals)) for vals in itertools.product(*(scan_grid[d] for d in dims))]
```
（Task 7 在此文件末尾续写 `ScanConfig` 与 `scan_one_stock`。）

- [ ] **Step 4: 运行测试**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_core.py -q`
Expected: 全 PASS（10 项）。若 `test_probe_detector_dims` 里 `max_start_gap` 的 `edges_changed` 为 False，检查 `repr(spec.edges)` 是否包含 `max_gap`（`TemporalEdge` 是 dataclass，应包含）；若 `PatternSpec` 归一化把 edges 变成新对象但 repr 仍相同则改用 `[(type(e).__name__, getattr(e, 'min_gap', None), getattr(e, 'max_gap', None), e.src, e.dst) for e in spec.edges]` 比较。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/tune-gates/multivar_core.py .claude/skills/tune-gates/test_multivar_core.py
git commit -m "feat(tune-gates): multivar_core 探针式参数分类(W/F/D/E)、影响集、检测组合展开"
```

---

### Task 7: `multivar_core.py` 第二部分——单股反转循环 + 真实数据对拍

**Files:**
- Modify: `.claude/skills/tune-gates/multivar_core.py`（末尾追加）
- Create: `.claude/skills/tune-gates/test_multivar_equiv.py`

**Interfaces:**
- Consumes: Task 6 全部；Task 3 的 `M=`；Task 2 的 `day_drop`；Task 5 的 `filter_params`。
- Produces:
  - `ScanConfig`（frozen dataclass，picklable）：`module_path: str`、`base_dict: dict`、`wide_overrides: dict`、`scan_grid: dict`、`where_levels: dict`、`end_node: str`、`label_horizon: int`、`fp_k: float`、`price_min: float|None`、`price_max: float|None`。
  - `scan_one_stock(symbol: str, win: pd.DataFrame, start_ts, end_ts, cfg: ScanConfig, mod=None) -> list[dict]`：每行 = 一个 match，列见下；`mod` 缺省按 `module_path` import。
  - 行列名：`symbol`；每个非 F 真扫维 `col_of(dim)`；每个 F 维 `node_col(node, field)`；每个 W 维 `node_col(node, field)`；每个 `match.node_index` 节点 `node_col(nid, "start")` / `node_col(nid, "end")`；`buy_date`（str）、`fr`、`dd`（float 或 None）、`fp_up/fp_down/fp_both/fp_none`（int）。
  - `row_columns(cfg, cls, spec) -> list[str]`（固定列序，parquet 分片共用）。

- [ ] **Step 1: 写对拍测试（真实数据，先失败）**

创建 `.claude/skills/tune-gates/test_multivar_equiv.py`：
```python
# -*- coding: utf-8 -*-
"""反转循环(scan_one_stock)vs 逐格 engine.analyze + serialize 的精确对拍(真实数据;缺失 skip):
uv run pytest .claude/skills/tune-gates/test_multivar_equiv.py -q
键 = (各节点 span, fr(12 位), 四态) 多重集 + 每股 match_fp_counts;覆盖随机 8 格 + 4 角点 + 一套收紧 where。
"""
import json, random, subprocess, sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from multivar_core import ScanConfig, apply_overrides, classify, col_of, node_col, scan_one_stock  # noqa: E402
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402

DATA = REPO / "datasets/pkls"
BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
SCAN_GRID = {("bo", "min_relative_height"): [0.15, 0.2], ("bo", "exceed_threshold"): [0.003, 0.01],
             ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"): [0, 1, 2, 3], ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20], ("burst", "distinct_pk_min"): [1, 3],
                ("burst", "vol_spike_min"): [0, 10], ("burst", "peak_age_min"): [0, 125],
                ("tb", "max_day_drop_pct"): [None, 0.2]}
WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
        "tb": {"max_day_drop_pct": None}}
H, K = 40, 5.0


def _cells():
    rng = random.Random(7)
    dims = list(SCAN_GRID)
    allc = [dict(zip(dims, v)) for v in __import__("itertools").product(*SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (SCAN_GRID[d][0], SCAN_GRID[d][-1]) for d in dims)]
    return rng.sample(allc, 8) + rng.sample(corners, 4)


def _where_sets():
    wide = {d: lv[0] for d, lv in WHERE_LEVELS.items()}
    tight = {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3,
             ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 125, ("tb", "max_day_drop_pct"): 0.2}
    return [wide, tight]


def _ref_keys(spec, p, win, lo, hi, s, e):
    res = analyze(spec, win, p)
    out = serialize_per_pattern_result(res, end_node="tb", label_horizon=H, win=win, start_ts=s, end_ts=e,
                                       price_min=0.5, price_max=30.0, first_passage_k=K, sample_window=(lo, hi))
    keep = {m["match_id"] for m in out["analysis"]["matches"]}
    keys = []
    for m in res.matches:
        if m.match_id not in keep:
            continue
        md = next(x for x in out["analysis"]["matches"] if x["match_id"] == m.match_id)
        fp = md["first_passage"] or {"up": 0, "down": 0, "both": 0, "none": 0}
        spans = tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(m.node_index.items()))
        keys.append((spans, None if md["forward_return"] is None else round(md["forward_return"], 12),
                     fp["up"], fp["down"], fp["both"], fp["none"]))
    return sorted(keys), out["match_fp_counts"]


def _rows_keys(rows, cell, where, cls):
    keys, tot = [], {"up": 0, "down": 0, "both": 0, "none": 0}
    for r in rows:
        ok = all(r[col_of(d)] == v for d, v in cell.items() if cls.kinds[d] != "F")
        for d, v in cell.items():
            if cls.kinds[d] == "F":
                n, f, _ = cls.filter_fields[d]; ok &= r[node_col(n, f)] >= v
        for d, v in where.items():
            if v is None:
                continue
            n, f, op = cls.where_fields[d]
            x = r[node_col(n, f)]
            ok &= (x >= v) if op == ">=" else (x < v) if op == "<" else (x > v) if op == ">" else (x <= v)
        if not ok:
            continue
        nodes = sorted({c.rsplit(".", 1)[0] for c in r if c.endswith(".start")})
        spans = tuple((n, r[node_col(n, "start")], r[node_col(n, "end")]) for n in nodes)
        keys.append((spans, None if r["fr"] is None else round(r["fr"], 12), r["fp_up"], r["fp_down"], r["fp_both"], r["fp_none"]))
        for s_ in tot:
            tot[s_] += r[f"fp_{s_}"]
    return sorted(keys), tot


def test_reversed_loop_equals_per_cell_analyze():
    if not DATA.exists():
        pytest.skip("datasets/pkls 缺失")
    config.set_runtime_checks(True)
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    cfg = ScanConfig(module_path="path2_apps.bb_v1.dag_spec", base_dict=BASE, wide_overrides=WIDE,
                     scan_grid=SCAN_GRID, where_levels=WHERE_LEVELS, end_node="tb", label_horizon=H, fp_k=K,
                     price_min=0.5, price_max=30.0)
    s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
    bs = str((s - pd.Timedelta(days=round(250 * TRADING_TO_CALENDAR_RATIO))).date())
    be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    n_stock = n_cmp = mism = 0
    for pk in _list_pkls(str(DATA), r"^A[A-C]"):
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) < 300:
            continue
        n_stock += 1
        lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
        rows = scan_one_stock(pk.stem, win, s, e, cfg, mod=mod)
        for cell in _cells():
            for where in _where_sets():
                d = apply_overrides(BASE, WIDE, {**cell, **where})
                p = mod.Params.from_dict(d, strict=True)
                ref = _ref_keys(mod.build_pattern(p), p, win, lo, hi, s, e)
                got = _rows_keys(rows, cell, where, cls)
                n_cmp += 1
                if ref != got:
                    mism += 1
                    print("MISMATCH", pk.stem, cell, where, len(ref[0]), len(got[0]))
    assert n_stock > 50 and n_cmp > 1000
    assert mism == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_equiv.py -q`
Expected: FAIL（`ImportError: cannot import name 'ScanConfig'`）。

- [ ] **Step 3: 实现 `ScanConfig` 与 `scan_one_stock`**

追加到 `.claude/skills/tune-gates/multivar_core.py` 末尾：
```python
# ---------------------------------------------------------------- 单股反转循环
@dataclass(frozen=True)
class ScanConfig:
    module_path: str
    base_dict: dict
    wide_overrides: dict
    scan_grid: dict
    where_levels: dict
    end_node: str
    label_horizon: int
    fp_k: float
    price_min: Optional[float] = None
    price_max: Optional[float] = None


def _import(path: str):
    import importlib
    return importlib.import_module(path)


def row_columns(cfg: ScanConfig, cls: Classification, spec) -> list:
    cols = ["symbol"] + [col_of(d) for d in cfg.scan_grid if cls.kinds[d] != "F"]
    cols += [node_col(n, f) for (n, f, _) in cls.filter_fields.values()]
    cols += [node_col(n, f) for (n, f, _) in cls.where_fields.values()]
    for n in spec.nodes:
        if n.detector is not None:
            cols += [node_col(n.node_id, "start"), node_col(n.node_id, "end")]
    return cols + ["buy_date", "fr", "dd", "fp_up", "fp_down", "fp_both", "fp_none"]


def scan_one_stock(symbol: str, win: pd.DataFrame, start_ts, end_ts, cfg: ScanConfig, mod=None) -> list:
    """一只股票上跑完整个设计:上游流按影响集缓存、每个检测组合 solve、label 按 end_node span 记忆化。
    返回 rows(list[dict],列 = row_columns)。where 一律宽进(谓词留给 region 阶段),F 维按最松档构造。"""
    mod = mod or _import(cfg.module_path)
    cls = classify(mod, cfg.base_dict, cfg.scan_grid, cfg.where_levels)
    filter_min = {d: min(cfg.scan_grid[d]) for d in cfg.scan_grid if cls.kinds[d] == "F"}
    base = apply_overrides(cfg.base_dict, cfg.wide_overrides, filter_min)
    spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    check_where_axes(spec0, cls.where_fields)
    infl = influence_dims(spec0, cls, cfg.scan_grid)
    order = [nid for nid in detector_topo_order(spec0.nodes)]
    children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
    leaf = cfg.end_node.split(".")[0]
    H, K = cfg.label_horizon, cfg.fp_k

    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    lo = int(win["date"].searchsorted(start_ts, "left"))
    hi = int(win["date"].searchsorted(end_ts, "right")) - 1
    dates = win["date"]
    closes = win["close"]
    stream_cache: dict = {}
    label_memo: dict = {}
    rows: list = []

    for combo in detection_combos(cfg.scan_grid, cls):
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        by_id = {n.node_id: n for n in spec.nodes}
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None:
                continue
            key = (nid, tuple(combo[d] for d in infl[nid]))
            if key not in stream_cache:
                if node.consumes_stream is None:
                    evs = list(run(node.detector, win))
                else:
                    evs = list(run(node.detector, streams[node.consumes_stream], win))
                annotate_stream(counts, nid, evs, children_of)     # 已标注的上游流会被跳过
                stream_cache[key] = evs
            streams[nid] = stream_cache[key]
        plan = compile_plan(spec)
        combo_cols = {col_of(d): v for d, v in combo.items()}
        for sol in solve(plan, streams):
            m = reify(sol, streams, plan)
            events = _resolve_end_events(m, cfg.end_node)
            if not any(start_ts <= dates.iat[ev.start_idx] <= end_ts for ev in events):
                continue
            cl = [closes.iat[ev.start_idx] for ev in events]
            if not any((cfg.price_min is None or c >= cfg.price_min)
                       and (cfg.price_max is None or c <= cfg.price_max) for c in cl):
                continue
            span_key = tuple((ev.start_idx, ev.end_idx) for ev in events)
            if span_key not in label_memo:
                fr = match_forward_returns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                dd = match_forward_drawdowns(m, cfg.end_node, win, [H], sample_window=(lo, hi))[H]
                fp = match_first_passage(m, cfg.end_node, win, H, K, sample_window=(lo, hi), M=M)
                label_memo[span_key] = (fr, dd, fp)
            fr, dd, fp = label_memo[span_key]
            leaf_ev = m.node_index[leaf]
            row = {"symbol": symbol, **combo_cols}
            for (n, f, _) in cls.filter_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for (n, f, _) in cls.where_fields.values():
                row[node_col(n, f)] = getattr(m.node_index[n], f)
            for nid, ev in m.node_index.items():
                row[node_col(nid, "start")] = ev.start_idx; row[node_col(nid, "end")] = ev.end_idx
            row["buy_date"] = str(pd.to_datetime(dates.iat[leaf_ev.start_idx]).date())
            row["fr"] = fr; row["dd"] = dd
            for s in STATES:
                row[f"fp_{s}"] = int(fp[s])
            rows.append(row)
    return rows
```

- [ ] **Step 4: 运行对拍**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_equiv.py -q -s 2>&1 | tail -5`
Expected: PASS，`mism == 0`（约 104 股 × 12 格 × 2 套 where ≈ 2500 次比较；耗时数分钟）。若出现 MISMATCH：先看是否只在收紧 where 组出现（→ 检查 `day_drop` 是否恒计算、`peak_age_max` 字段名）；只在 F 维 ≥2 出现（→ 检查 `filter_min` 是否真的以最松档构造）；全面出现（→ 检查 `annotate_stream` 是否每个 combo 用了新的 `counts`、`influence_dims` 是否漏了某维）。**不得**通过放宽键来"修"。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/tune-gates/multivar_core.py .claude/skills/tune-gates/test_multivar_equiv.py
git commit -m "feat(tune-gates): 单股反转循环 scan_one_stock(上游流缓存 + 每组合 solve + label 记忆化)+ 真实数据逐格对拍零差"
```

---

### Task 8: `multivar_scan.py`——进程池 / parquet 分片 / 断点续跑 / 台账

**Files:**
- Create: `.claude/skills/tune-gates/multivar_scan.py`

**Interfaces:**
- Consumes: Task 7 `ScanConfig` / `scan_one_stock` / `row_columns` / `classify`；Task 3 `random_day_first_passage(..., M=)`。
- Produces: `OUT_DIR/longtable/part-<k>.parquet`（列 = `row_columns` + `fold_Y` + `fold_6M`）、`OUT_DIR/random_baseline.csv`（`symbol,n_sampled,up,down,both,none`）、`OUT_DIR/ledger.md`。模块级 `_worker(pkl_path, cfg, buf_start, buf_end, start_date, end_date, volume_min) -> (symbol, rows|None, random_fp|None, err|None)`。

- [ ] **Step 1: 实现脚本**

创建 `.claude/skills/tune-gates/multivar_scan.py`：
```python
# -*- coding: utf-8 -*-
"""多维稳健区 v2 · 扫描端:每股一次反转循环 → 候选长表(parquet 分片)+ 随机日基线 + 台账。
用法:复制到研究目录改 main() 常量后 `uv run python <路径>/multivar_scan.py`
断点续跑:按股——已有分片里出现过的 symbol 直接跳过(删分片即重跑)。
产出与 region_find.py 共用 HEAD_BUFFER(写进 ledger.md,region_find 读出核对)。
"""
from __future__ import annotations

import json, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(Path(__file__).parent))

from multivar_core import ScanConfig, classify, col_of, row_columns, scan_one_stock  # noqa: E402


def _fold_cols(buy_date: pd.Series) -> tuple:
    d = pd.to_datetime(buy_date)
    return d.dt.year.astype(str), d.dt.year.astype(str) + "H" + np.where(d.dt.month <= 6, "1", "2")


def _worker(pkl_path, cfg: ScanConfig, buf_start, buf_end, start_date, end_date, volume_min):
    from path2 import config
    from path2.calc.atr import rolling_atr_pct_nanmedian
    from path2.eval import random_day_first_passage
    from path2_web.data import slice_window
    symbol = Path(pkl_path).stem
    try:
        config.set_runtime_checks(True)
        win = slice_window(pd.read_pickle(pkl_path), buf_start, buf_end)
        if len(win) == 0:
            return (symbol, None, None, None)
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        if volume_min is not None:
            sw = win[(win["date"] >= s) & (win["date"] <= e)]
            if len(sw) == 0 or sw["volume"].mean() <= volume_min:
                return (symbol, None, None, None)
        rows = scan_one_stock(symbol, win, s, e, cfg)
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
        rfp = random_day_first_passage(symbol, win, s, e, cfg.label_horizon, cfg.fp_k, M=M)
        return (symbol, rows, rfp, None)
    except Exception as ex:  # noqa: BLE001
        return (symbol, None, None, f"{type(ex).__name__}: {ex}")


def main() -> None:
    PATTERN_ID = "bb_v1"
    DATA_DIR = "datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER = 250                                # ★ 与 region_find 共用
    LABEL_HORIZON, FIRST_PASSAGE_K = 40, 5.0
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 8
    TICKER_REGEX = None
    REF_PARAMS = "docs/research/2026-08-25_multivar-bb_v1/ref_params.json"
    WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                      "tb": {"max_day_drop_pct": None}}
    SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
                 ("bo", "exceed_threshold"):    [0.001, 0.003, 0.01, 0.03],
                 ("burst", "gap_max"):          [4, 8, 12, 20],
                 ("burst", "min_bos"):          [1, 2, 3, 4],
                 ("tb", "stop_confirm_bars"):   [0, 1, 2, 3],
                 ("tb", "big_rise_k"):          [3.0, 5.0, 8.0, 12.0]}
    WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                    ("burst", "distinct_pk_min"):   [1, 3, 4],
                    ("burst", "vol_spike_min"):     [0, 10, 15],
                    ("burst", "peak_age_min"):      [0, 125],
                    ("tb", "max_day_drop_pct"):     [None, 0.2]}
    OUT_DIR = "docs/research/2026-08-25_multivar-bb_v1/"
    SHARD_STOCKS = 200

    from path2_web.discovery import PatternRegistry
    from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls
    reg = PatternRegistry(); mod = reg.get(PATTERN_ID)
    base = json.loads((REPO / REF_PARAMS).read_text())
    p0 = mod.Params.from_dict(base, strict=True)
    end_node = mod.eval_meta(params=p0)["end_node"]
    cls = classify(mod, base, SCAN_GRID, WHERE_LEVELS)
    print("参数分类:"); [print(f"  {col_of(d):32s} {k}") for d, k in cls.kinds.items()]
    print("where 轴:", {col_of(d): v for d, v in cls.where_fields.items()})
    print("过滤型:", {col_of(d): v for d, v in cls.filter_fields.items()})
    cfg = ScanConfig(module_path=reg.module_path(PATTERN_ID), base_dict=base, wide_overrides=WIDE_OVERRIDES,
                     scan_grid=SCAN_GRID, where_levels=WHERE_LEVELS, end_node=end_node,
                     label_horizon=LABEL_HORIZON, fp_k=FIRST_PASSAGE_K, price_min=PRICE_MIN, price_max=PRICE_MAX)
    spec0 = mod.build_pattern(p0)
    columns = row_columns(cfg, cls, spec0) + ["fold_Y", "fold_6M"]

    out = REPO / OUT_DIR; lt = out / "longtable"; lt.mkdir(parents=True, exist_ok=True)
    done = set()
    for part in sorted(lt.glob("part-*.parquet")):
        done |= set(pd.read_parquet(part, columns=["symbol"])["symbol"].unique())
    rb_path = out / "random_baseline.csv"
    rb_rows = pd.read_csv(rb_path).to_dict("records") if rb_path.exists() else []
    done |= {r["symbol"] for r in rb_rows}
    s, e = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((s - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((e + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())
    pkls = [p for p in _list_pkls(str(REPO / DATA_DIR), TICKER_REGEX) if p.stem not in done]
    print(f"股票 {len(pkls)} 待扫(已完成 {len(done)}),窗 {buf_start}..{buf_end},HEAD_BUFFER={HEAD_BUFFER}")

    t0 = time.time(); cpu0 = time.process_time()
    buf, n_shard = [], len(list(lt.glob("part-*.parquet")))
    n_done = n_det = n_hit = n_rows = n_err = 0; per_ms = []
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_worker, str(p), cfg, buf_start, buf_end, START_DATE, END_DATE, VOLUME_MIN): p for p in pkls}
        for fut in as_completed(futs):
            symbol, rows, rfp, err = fut.result(); n_done += 1
            if err:
                n_err += 1; print("ERR", symbol, err); continue
            if rows is None:
                continue
            n_det += 1
            if rows:
                n_hit += 1; n_rows += len(rows); buf.extend(rows)
            rb_rows.append({"symbol": symbol, "n_sampled": rfp["n_sampled"], **rfp["counts"]})
            if n_det % SHARD_STOCKS == 0 or n_done == len(pkls):
                if buf:
                    df = pd.DataFrame(buf, columns=columns[:-2]); df["fold_Y"], df["fold_6M"] = _fold_cols(df["buy_date"])
                    df.to_parquet(lt / f"part-{n_shard:04d}.parquet", index=False); n_shard += 1; buf = []
                pd.DataFrame(rb_rows).to_csv(rb_path, index=False)
            if n_done % 200 == 0:
                print(f"  {n_done}/{len(pkls)} 股 · {n_rows} 行 · {time.time() - t0:.0f}s")
    if buf:
        df = pd.DataFrame(buf, columns=columns[:-2]); df["fold_Y"], df["fold_6M"] = _fold_cols(df["buy_date"])
        df.to_parquet(lt / f"part-{n_shard:04d}.parquet", index=False)
        pd.DataFrame(rb_rows).to_csv(rb_path, index=False)
    wall = time.time() - t0

    # 台账 + fold 计数分布(真扫格粒度、宽进 where)
    full = pd.concat([pd.read_parquet(p) for p in sorted(lt.glob("part-*.parquet"))], ignore_index=True)
    combo_cols = [col_of(d) for d in SCAN_GRID if cls.kinds[d] != "F"]
    cnt = full.groupby(combo_cols + ["fold_Y"]).size()
    lines = [f"# multivar_scan 台账 · {PATTERN_ID}", "",
             f"- 窗:{START_DATE}..{END_DATE};HEAD_BUFFER={HEAD_BUFFER};LABEL_HORIZON={LABEL_HORIZON};FIRST_PASSAGE_K={FIRST_PASSAGE_K}",
             f"- 过滤:price [{PRICE_MIN},{PRICE_MAX}],volume_min {VOLUME_MIN};底座 {REF_PARAMS};宽进 {WIDE_OVERRIDES}",
             f"- SCAN_GRID:{ {col_of(d): v for d, v in SCAN_GRID.items()} }", f"- WHERE_LEVELS:{ {col_of(d): v for d, v in WHERE_LEVELS.items()} }",
             f"- 分类:{ {col_of(d): k for d, k in cls.kinds.items()} }", f"- where 轴:{ {col_of(d): v for d, v in cls.where_fields.items()} }",
             f"- 股数:待扫 {len(pkls)} / 进 detector {n_det} / 有 match {n_hit} / 异常 {n_err};累计行 {len(full)}",
             f"- 耗时:wall {wall:.0f}s @ {WORKERS} workers(本进程 cpu {time.process_time() - cpu0:.0f}s)",
             f"- 宽进 where 下真扫格 × 年折的 match 数分布:min {cnt.min()} / p50 {cnt.median():.0f} / max {cnt.max()}", ""]
    (out / "ledger.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟 + 断点续跑**

把脚本复制到 `docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_smoke.py`，改常量：`TICKER_REGEX = r"^A[A-C]"`、`OUT_DIR = "docs/research/2026-08-25_multivar-bb_v1/smoke/"`、`SCAN_GRID` 只留 `("burst","gap_max"): [8, 12]` 与 `("tb","stop_confirm_bars"): [1, 2]` 两维、`WHERE_LEVELS` 只留 `("burst","first_drought_min"): [0, 20]`、`WORKERS = 4`、`SHARD_STOCKS = 30`。

Run 两次：`uv run python docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_smoke.py`
Expected：第一次打印分类表（`burst.gap_max D`、`tb.stop_confirm_bars D`、`burst.first_drought_min W`）、生成 `smoke/longtable/part-000*.parquet` ≥ 2 个、`random_baseline.csv`、`ledger.md`；第二次打印 `股票 0 待扫`。用 `uv run python -c "import pandas as pd, glob; df = pd.concat(map(pd.read_parquet, glob.glob('docs/research/2026-08-25_multivar-bb_v1/smoke/longtable/*.parquet'))); print(df.shape); print(df.columns.tolist()); print(df.fold_Y.value_counts())"` 核对列名含 `burst.gap_max, tb.stop_confirm_bars, burst.first_drought, bo.start, burst.start, tb.start, buy_date, fr, dd, fp_up..fp_none, fold_Y, fold_6M`。

- [ ] **Step 3: 提交**

```bash
git add .claude/skills/tune-gates/multivar_scan.py docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_smoke.py
git commit -m "feat(tune-gates): multivar_scan 进程池反转扫描 → parquet 分片长表 + 随机日基线 + 台账,按股断点续跑"
```
（`smoke/` 产物不提交：在 `docs/research/2026-08-25_multivar-bb_v1/.gitignore` 写入 `smoke/` 与 `longtable/` 并一并提交。）

---

### Task 9: `region_core.py` 第一部分——格张量 / 可评估 / 增量 / 邻域最小

**Files:**
- Create: `.claude/skills/tune-gates/region_core.py`
- Create: `.claude/skills/tune-gates/test_region_core.py`

**Interfaces:**
- Produces（Task 10 消费）：
  - `pred_level_index(values, op, levels) -> np.ndarray[int16]`：levels **松→紧**、嵌套；返回每行满足的最紧档下标（不满足最松档 → −1）；非嵌套 → `ValueError`。
  - `Prepared`（dataclass）：`flat: np.ndarray[int64]`（每行的格桶扁平索引）、`states: np.ndarray[int64, (n,4)]`、`sym_codes: np.ndarray[int]`、`n_sym: int`、`shape: tuple`（= combo 轴长 + pred 轴长 + `(n_folds, 4)`）、`n_combo_axes: int`、`n_pred_axes: int`、`fold_axis: int`、`combo_levels: dict`、`pred_specs: list`、`folds: list`、`row_keep: np.ndarray[bool]`。
  - `prepare(df, combo_levels: dict[str, list], pred_specs: list[tuple[str, str, list]], fold_col: str, folds: list) -> Prepared`。
  - `tensor(prep, weights: np.ndarray | None = None) -> np.ndarray`（形状 `prep.shape`，四态计数；`weights` 按 symbol 索引，None = 全 1；含 pred 轴后缀累加）。
  - `fp_count(T) -> (fp, count)`（形状 = `shape[:-1]`，`fp` 分母 0 → NaN）。
  - `score(fp, count, ref_index: tuple, min_count: int) -> (s, evaluable, delta)`：`delta[..., f] = fp[..., f] − fp[ref + (f,)]`；`evaluable = (count >= min_count).all(-1)`；`s = min_f delta`（不可评估 → NaN）。
  - `neighbor_min(s, evaluable, axes: list[int]) -> (s_nb, n_eval_nb)`。
  - `rank_cells(s_nb, n_eval_nb) -> np.ndarray[int]`（扁平索引降序；并列按 `n_eval_nb` 大、再按离边界远）。
  - `tolerance(s_nb, center: tuple) -> dict[int, tuple[int, int]]`（轴 → (向下连续 `s_nb>0` 档数, 向上档数)）。
  - `cell_coords(prep, flat_index) -> dict[str, object]`（扁平索引 → {列名: 档位值}，pred 列给档位值）。

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/tune-gates/test_region_core.py`：
```python
# -*- coding: utf-8 -*-
"""region_core 合成数据单测(显式路径跑):uv run pytest .claude/skills/tune-gates/test_region_core.py -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from region_core import (cell_coords, fp_count, neighbor_min, pred_level_index, prepare,  # noqa: E402
                         rank_cells, score, tensor, tolerance)

COMBO = {"g": [4, 8, 12], "K": [0, 1, 2]}
PREDS = [("count", ">=", [1, 2, 3]), ("fd", ">=", [0, 20])]
FOLDS = ["2024", "2025"]


def _synth(seed=0, n_sym=400, plateau=None, base_p=0.5, n_per=6):
    """每股每 (g,K) 组合 n_per 行;count/fd 随机;up 概率 = base_p (+ plateau 增量在指定格子集)。"""
    rng = np.random.default_rng(seed)
    rows = []
    for sym in range(n_sym):
        eff = rng.normal(0, 0.03)                     # 按股随机效应
        for g in COMBO["g"]:
            for K in COMBO["K"]:
                for _ in range(n_per):
                    cnt = rng.integers(1, 4); fd = rng.choice([0, 10, 25, 40]); year = rng.choice(FOLDS)
                    p = base_p + eff
                    if plateau and (g, K) in plateau["cells"] and fd >= plateau.get("fd_min", 0):
                        p += plateau["delta"]
                    up = rng.random() < p
                    rows.append(dict(symbol=f"S{sym}", g=g, K=K, count=cnt, fd=fd, fold=year,
                                     fp_up=int(up), fp_down=int(not up), fp_both=0, fp_none=0))
    return pd.DataFrame(rows)


def test_pred_level_index_nested_and_none():
    v = np.array([0.0, 15.0, 25.0, np.nan])
    assert pred_level_index(v, ">=", [0, 20]).tolist() == [0, 0, 1, -1]
    assert pred_level_index(np.array([0.1, 0.3, np.nan]), "<", [None, 0.2]).tolist() == [1, 0, 0]
    with pytest.raises(ValueError):
        pred_level_index(v, ">=", [20, 0])          # 紧→松:非嵌套


def test_tensor_suffix_cumsum_counts():
    df = _synth(n_sym=20)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    T = tensor(prep)
    assert T.shape == (3, 3, 3, 2, 2, 4)
    # 最松档 (count>=1, fd>=0) 的总数 == 全部行数(去掉 fold 不在 FOLDS 的,这里没有)
    assert T[:, :, 0, 0, :, :].sum() == len(df)
    # count>=2 的行数手算
    sub = df[df["count"] >= 2]
    assert T[:, :, 1, 0, :, :].sum() == len(sub)
    # 某一格手算:g=8,K=1,count>=3,fd>=20,2024,up
    m = (df.g == 8) & (df.K == 1) & (df["count"] >= 3) & (df.fd >= 20) & (df.fold == "2024")
    assert T[1, 1, 2, 1, 0, 0] == df.loc[m, "fp_up"].sum()


def test_score_and_evaluable():
    df = _synth(n_sym=200)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    fp, cnt = fp_count(tensor(prep))
    ref = (1, 1, 0, 0)                                 # g=8,K=1,最松
    s, ev, delta = score(fp, cnt, ref, min_count=100)
    assert s[ref] == pytest.approx(0.0)
    assert ev[ref]
    # 功效线:把 min_count 抬到超过任何格 → 全不可评估
    s2, ev2, _ = score(fp, cnt, ref, min_count=10 ** 6)
    assert not ev2.any() and np.isnan(s2).all()


def test_neighbor_min_spike_and_boundary():
    s = np.full((3, 3), -0.02); s[1, 1] = 0.05
    ev = np.ones((3, 3), bool)
    s_nb, n = neighbor_min(s, ev, axes=[0, 1])
    assert s_nb[1, 1] == pytest.approx(-0.02) and n[1, 1] == 4
    assert n[0, 0] == 2 and n[0, 1] == 3                # 角 2 邻、边 3 邻(无 pad)
    ev[0, 1] = False; s[0, 1] = np.nan
    s_nb, n = neighbor_min(s, ev, axes=[0, 1])
    assert np.isnan(s_nb[0, 1]) and n[0, 0] == 1 and n[1, 1] == 3   # 不可评估格不作邻居、自身缺失


def test_rank_and_tolerance():
    s_nb = np.array([[0.01, 0.03, 0.03], [np.nan, 0.02, -0.01]])
    n = np.array([[2, 3, 2], [0, 4, 3]])
    order = rank_cells(s_nb, n)
    assert order[0] == 1                                  # (0,1):0.03 且 n=3 胜 (0,2)
    tol = tolerance(np.array([[-0.1, 0.1, 0.2, 0.1, -0.1]]), center=(0, 2))
    assert tol[1] == (1, 1) and tol[0] == (0, 0)


def test_plateau_recovered_end_to_end():
    plat = {"cells": {(8, 1), (8, 2), (12, 1), (12, 2)}, "delta": 0.08, "fd_min": 20}
    df = _synth(seed=1, n_sym=600, plateau=plat)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    fp, cnt = fp_count(tensor(prep))
    s, ev, _ = score(fp, cnt, ref_index=(1, 1, 0, 0), min_count=100)
    s_nb, n = neighbor_min(s, ev, axes=list(range(4)))
    best = rank_cells(s_nb, n)[0]
    c = cell_coords(prep, best)
    assert (c["g"], c["K"]) in plat["cells"] and c["fd"] == 20
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest .claude/skills/tune-gates/test_region_core.py -q`
Expected: FAIL（`ModuleNotFoundError: region_core`）。

- [ ] **Step 3: 实现**

创建 `.claude/skills/tune-gates/region_core.py`：
```python
# -*- coding: utf-8 -*-
"""region_find 的纯函数层:长表 → 联合空间格张量 → 可评估 / 相对参照增量 / fold 最小 / r=1 邻域最小
→ 排序 → 按股 bootstrap + 选择后校正(Task 10 追加)。

格张量:轴 = [combo 轴...] + [pred 轴...] + [fold, 4 态]。combo 轴 = 反转循环真扫的检测组合维
(行值精确等于档位);pred 轴 = 过滤型 / where 维(行带原始量,档位松→紧嵌套):行先落在其满足的
**最紧档**桶,再沿 pred 轴做后缀累加——满足紧档的行也属于所有更松的格。一次 bincount 出全部格。
bootstrap 用同一 flat 索引按 symbol 权重重做 bincount,不在原始行上重采样。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

STATES = ["fp_up", "fp_down", "fp_both", "fp_none"]


def pred_level_index(values, op: str, levels: list) -> np.ndarray:
    v = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)
    idx = np.full(len(v), -1, dtype=np.int16)
    prev = None
    for j, lv in enumerate(levels):
        if lv is None:
            ok = np.ones(len(v), bool)
        elif op == ">=":
            ok = v >= lv
        elif op == ">":
            ok = v > lv
        elif op == "<":
            ok = v < lv
        elif op == "<=":
            ok = v <= lv
        else:
            raise ValueError(f"不支持的 op {op!r}")
        if prev is not None and np.any(ok & ~prev):
            raise ValueError(f"档位 {levels} 非松→紧嵌套(op {op})")
        idx[ok] = j
        prev = ok
    return idx


@dataclass
class Prepared:
    flat: np.ndarray
    states: np.ndarray
    sym_codes: np.ndarray
    n_sym: int
    shape: tuple
    n_combo_axes: int
    n_pred_axes: int
    fold_axis: int
    combo_levels: dict
    pred_specs: list
    folds: list
    row_keep: np.ndarray


def prepare(df: pd.DataFrame, combo_levels: dict, pred_specs: list, fold_col: str, folds: list) -> Prepared:
    ci = [pd.Categorical(df[c], categories=lv).codes.astype(np.int64) for c, lv in combo_levels.items()]
    pi = [pred_level_index(df[c].values, op, lv).astype(np.int64) for c, op, lv in pred_specs]
    fi = pd.Categorical(df[fold_col], categories=folds).codes.astype(np.int64)
    keep = fi >= 0
    for x in ci + pi:
        keep &= x >= 0
    axes = [len(lv) for lv in combo_levels.values()] + [len(lv) for _, _, lv in pred_specs] + [len(folds)]
    index = tuple(x[keep] for x in ci + pi) + (fi[keep],)
    flat = np.ravel_multi_index(index, axes)
    sym = pd.Categorical(df["symbol"]).codes.astype(np.int64)[keep]
    return Prepared(flat=flat, states=df[STATES].values[keep].astype(np.int64), sym_codes=sym,
                    n_sym=int(sym.max()) + 1 if len(sym) else 0, shape=tuple(axes) + (4,),
                    n_combo_axes=len(combo_levels), n_pred_axes=len(pred_specs), fold_axis=len(axes) - 1,
                    combo_levels=combo_levels, pred_specs=pred_specs, folds=folds, row_keep=keep)


def tensor(prep: Prepared, weights=None) -> np.ndarray:
    n_cells = int(np.prod(prep.shape[:-1]))
    w = None if weights is None else np.asarray(weights, dtype=float)[prep.sym_codes]
    T = np.empty((n_cells, 4), dtype=np.int64)
    for s in range(4):
        col = prep.states[:, s].astype(float)
        T[:, s] = np.rint(np.bincount(prep.flat, weights=col if w is None else col * w, minlength=n_cells)).astype(np.int64)
    T = T.reshape(prep.shape)
    for ax in range(prep.n_combo_axes, prep.n_combo_axes + prep.n_pred_axes):
        T = np.flip(np.cumsum(np.flip(T, axis=ax), axis=ax), axis=ax)     # 后缀累加:紧档行也属松档
    return T


def fp_count(T: np.ndarray):
    den = T[..., 0] + T[..., 1] + T[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        fp = np.where(den > 0, T[..., 0] / np.maximum(den, 1), np.nan)
    return fp, T.sum(-1)


def score(fp, count, ref_index: tuple, min_count: int):
    ref_fp = fp[ref_index]                                  # 形状 (n_folds,)
    delta = fp - ref_fp
    evaluable = (count >= min_count).all(-1) & np.isfinite(fp).all(-1)
    s = np.where(evaluable, np.nanmin(np.where(np.isfinite(delta), delta, np.inf), axis=-1), np.nan)
    return s, evaluable, delta


def neighbor_min(s, evaluable, axes):
    s_nb = np.where(evaluable, s, np.nan)
    n_eval = np.zeros(s.shape, dtype=np.int64)
    for ax in axes:
        for shift in (1, -1):
            nb = np.roll(s, shift, axis=ax)
            nb_ok = np.roll(evaluable, shift, axis=ax).copy()
            edge = [slice(None)] * s.ndim
            edge[ax] = 0 if shift == 1 else -1
            nb_ok[tuple(edge)] = False                         # 绕回的邻居不存在(无 pad)
            take = evaluable & nb_ok
            s_nb = np.where(take, np.fmin(s_nb, nb), s_nb)
            n_eval += take
    return s_nb, n_eval


def _boundary_dist(shape):
    grids = np.indices(shape)
    d = np.min([np.minimum(g, (n - 1) - g) for g, n in zip(grids, shape)], axis=0)
    return d


def rank_cells(s_nb, n_eval_nb) -> np.ndarray:
    flat_s = s_nb.ravel(); flat_n = n_eval_nb.ravel(); flat_b = _boundary_dist(s_nb.shape).ravel()
    key_s = np.where(np.isfinite(flat_s), flat_s, -np.inf)
    order = np.lexsort((-flat_b, -flat_n, -key_s))
    return order


def tolerance(s_nb, center: tuple) -> dict:
    out = {}
    for ax in range(s_nb.ndim):
        down = up = 0
        idx = list(center)
        for i in range(center[ax] - 1, -1, -1):
            idx[ax] = i
            if np.isfinite(s_nb[tuple(idx)]) and s_nb[tuple(idx)] > 0:
                down += 1
            else:
                break
        for i in range(center[ax] + 1, s_nb.shape[ax]):
            idx[ax] = i
            if np.isfinite(s_nb[tuple(idx)]) and s_nb[tuple(idx)] > 0:
                up += 1
            else:
                break
        out[ax] = (down, up)
    return out


def cell_coords(prep: Prepared, flat_index: int) -> dict:
    idx = np.unravel_index(int(flat_index), prep.shape[:-2])
    out = {}
    for (c, lv), i in zip(prep.combo_levels.items(), idx[: prep.n_combo_axes]):
        out[c] = lv[i]
    for (c, _op, lv), i in zip(prep.pred_specs, idx[prep.n_combo_axes:]):
        out[c] = lv[i]
    return out
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest .claude/skills/tune-gates/test_region_core.py -q`
Expected: 全 PASS（6 项）。`test_neighbor_min_spike_and_boundary` 第二段的 `n[1,1] == 3`：(0,1) 变不可评估后中心少一个邻居。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/tune-gates/region_core.py .claude/skills/tune-gates/test_region_core.py
git commit -m "feat(tune-gates): region_core 格张量(bincount+后缀累加)/可评估/相对参照增量/fold 最小/r=1 邻域最小/排序/容错"
```

---

### Task 10: `region_core.py` 第二部分（bootstrap / 选择后校正）+ `region_find.py`（图 / 报告）

**Files:**
- Modify: `.claude/skills/tune-gates/region_core.py`（末尾追加）
- Modify: `.claude/skills/tune-gates/test_region_core.py`（追加）
- Create: `.claude/skills/tune-gates/region_find.py`

**Interfaces:**
- Consumes: Task 9 全部；Task 8 长表列名（`col_of` 真扫列、`node.field` 谓词列、`fold_Y` / `fold_6M`）。
- Produces:
  - `analyze_tensor(prep, ref_index, min_count, axes, weights=None) -> dict`：键 `fp, count, s, evaluable, delta, s_nb, n_eval_nb, order`。
  - `bootstrap(prep, ref_index, min_count, axes, B, seed, top_n) -> dict`：键 `stability`（`P(ĉ_b ∈ N(ĉ)∪{ĉ})`）、`ci`（`s_nb(ĉ)` 的 2.5/97.5 百分位）、`optimism`（mean_b[`s_nb,b(ĉ_b)` − `s_nb(ĉ_b)`]）、`top_freq`（{flat_idx: 入选前 top_n 的次数}）、`center`（原数据 ĉ 扁平索引）。
  - `split_half(prep, ref_index, min_count, axes, seed) -> float`（两向平均）。
  - `region_find.main()`：产出 `region_report.md`、`cells.csv`、`folds_6M.csv`、`slice_<axis>.png`、`heat_<a>_<b>.png`、`boot_top.png`。

- [ ] **Step 1: 追加测试（先失败）**

在 `.claude/skills/tune-gates/test_region_core.py` 末尾追加：
```python
from region_core import analyze_tensor, bootstrap, split_half  # noqa: E402


def test_bootstrap_null_low_stability_and_optimism_nonneg():
    df = _synth(seed=2, n_sym=500)                       # 无结构
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    axes = list(range(4))
    bs = bootstrap(prep, ref_index=(1, 1, 0, 0), min_count=100, axes=axes, B=40, seed=0, top_n=5)
    assert 0.0 <= bs["stability"] <= 0.6
    assert bs["optimism"] >= -1e-9
    assert bs["ci"][0] <= bs["ci"][1]


def test_bootstrap_plateau_center_stable():
    plat = {"cells": {(8, 1), (8, 2), (12, 1), (12, 2)}, "delta": 0.10, "fd_min": 0}
    df = _synth(seed=3, n_sym=800, plateau=plat)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    bs = bootstrap(prep, ref_index=(1, 1, 0, 0), min_count=100, axes=list(range(4)), B=40, seed=0, top_n=5)
    assert bs["stability"] >= 0.5


def test_split_half_returns_finite():
    df = _synth(seed=4, n_sym=600)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    v = split_half(prep, ref_index=(1, 1, 0, 0), min_count=50, axes=list(range(4)), seed=0)
    assert np.isfinite(v)
```

Run: `uv run pytest .claude/skills/tune-gates/test_region_core.py -q`
Expected: 新 3 项 FAIL（ImportError）。

- [ ] **Step 2: 实现 bootstrap / split-half**

追加到 `.claude/skills/tune-gates/region_core.py`：
```python
# ---------------------------------------------------------------- 打分管线 / bootstrap / 校正
def analyze_tensor(prep: Prepared, ref_index: tuple, min_count: int, axes, weights=None) -> dict:
    fp, count = fp_count(tensor(prep, weights))
    s, ev, delta = score(fp, count, ref_index, min_count)
    s_nb, n_eval = neighbor_min(s, ev, axes)
    return dict(fp=fp, count=count, s=s, evaluable=ev, delta=delta, s_nb=s_nb, n_eval_nb=n_eval,
                order=rank_cells(s_nb, n_eval))


def _neighbors_flat(shape, flat_index: int, axes) -> set:
    idx = list(np.unravel_index(flat_index, shape))
    out = {flat_index}
    for ax in axes:
        for d in (-1, 1):
            j = list(idx); j[ax] += d
            if 0 <= j[ax] < shape[ax]:
                out.add(int(np.ravel_multi_index(j, shape)))
    return out


def bootstrap(prep: Prepared, ref_index: tuple, min_count: int, axes, B: int, seed: int, top_n: int) -> dict:
    base = analyze_tensor(prep, ref_index, min_count, axes)
    shape = base["s_nb"].shape
    c_hat = int(base["order"][0])
    if not np.isfinite(base["s_nb"].ravel()[c_hat]):
        return dict(center=c_hat, stability=float("nan"), ci=(float("nan"), float("nan")), optimism=float("nan"), top_freq={})
    nb_hat = _neighbors_flat(shape, c_hat, axes)
    rng = np.random.default_rng(seed)
    hits, s_at_hat, opt, top_freq = 0, [], [], {}
    s0 = base["s_nb"].ravel()
    for _ in range(B):
        w = rng.multinomial(prep.n_sym, np.full(prep.n_sym, 1.0 / prep.n_sym))
        r = analyze_tensor(prep, ref_index, min_count, axes, weights=w)
        sb = r["s_nb"].ravel(); cb = int(r["order"][0])
        if not np.isfinite(sb[cb]):
            continue
        hits += cb in nb_hat
        s_at_hat.append(sb[c_hat])
        if np.isfinite(s0[cb]):
            opt.append(sb[cb] - s0[cb])
        for i in r["order"][:top_n]:
            if np.isfinite(sb[i]):
                top_freq[int(i)] = top_freq.get(int(i), 0) + 1
    s_at_hat = np.array([x for x in s_at_hat if np.isfinite(x)])
    return dict(center=c_hat, stability=hits / max(B, 1),
                ci=(float(np.percentile(s_at_hat, 2.5)), float(np.percentile(s_at_hat, 97.5))) if len(s_at_hat) else (float("nan"),) * 2,
                optimism=float(np.mean(opt)) if opt else float("nan"), top_freq=top_freq)


def split_half(prep: Prepared, ref_index: tuple, min_count: int, axes, seed: int) -> float:
    rng = np.random.default_rng(seed)
    half = rng.random(prep.n_sym) < 0.5
    vals = []
    for sel_mask in (half, ~half):
        w_sel = sel_mask.astype(float); w_eval = (~sel_mask).astype(float)
        a = analyze_tensor(prep, ref_index, min_count, axes, weights=w_sel)
        b = analyze_tensor(prep, ref_index, min_count, axes, weights=w_eval)
        c = int(a["order"][0])
        v = b["s_nb"].ravel()[c]
        if np.isfinite(a["s_nb"].ravel()[c]) and np.isfinite(v):
            vals.append(v)
    return float(np.mean(vals)) if vals else float("nan")
```

Run: `uv run pytest .claude/skills/tune-gates/test_region_core.py -q`
Expected: 全 PASS（9 项）。`test_bootstrap_null_low_stability_and_optimism_nonneg` 若 stability 偶尔略高于 0.6，把 `n_sym` 提到 800 重跑一次；仍高则检查 `_neighbors_flat` 是否把整片邻域算得过大（应 ≤ 1 + 2×轴数）。

- [ ] **Step 3: 写 `region_find.py`**

创建 `.claude/skills/tune-gates/region_find.py`：
```python
# -*- coding: utf-8 -*-
"""多维稳健区 v2 · 识别端:候选长表 → 联合空间(真扫维 × where 维)打分 → 按股 bootstrap + 三口径校正
→ cells.csv / folds_6M.csv / 切片图 / 热力图 / region_report.md。
用法:复制到研究目录改 main() 常量后 `uv run python <路径>/region_find.py`
"""
from __future__ import annotations

import re, subprocess, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(Path(__file__).parent))
from region_core import (analyze_tensor, bootstrap, cell_coords, fp_count, prepare,  # noqa: E402
                         split_half, tensor, tolerance)


def _load(lt_dir: Path) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in sorted(lt_dir.glob("part-*.parquet"))], ignore_index=True)


def _check_head_buffer(ledger: Path, head_buffer: int) -> None:
    m = re.search(r"HEAD_BUFFER=(\d+)", ledger.read_text())
    if not m or int(m.group(1)) != head_buffer:
        raise SystemExit(f"ledger 的 HEAD_BUFFER={m and m.group(1)} 与本脚本 {head_buffer} 不一致,拒绝比较")


def main() -> None:
    LONGTABLE_DIR = "docs/research/2026-08-25_multivar-bb_v1/longtable/"
    HEAD_BUFFER = 250
    SCAN_DIMS = ["bo.min_relative_height", "bo.exceed_threshold", "burst.gap_max", "burst.min_bos",
                 "tb.stop_confirm_bars", "tb.big_rise_k"]           # 轴序(含 F 维,F 维在下面按 FILTER_PREDS 变谓词)
    COMBO_LEVELS = {"bo.min_relative_height": [0.1, 0.15, 0.2, 0.3], "bo.exceed_threshold": [0.001, 0.003, 0.01, 0.03],
                    "burst.gap_max": [4, 8, 12, 20], "tb.stop_confirm_bars": [0, 1, 2, 3], "tb.big_rise_k": [3.0, 5.0, 8.0, 12.0]}
    FILTER_PREDS = [("burst.count", ">=", [1, 2, 3, 4])]              # F 维:长表列 burst.count,档位 = burst.min_bos 档位
    WHERE_PREDS = [("burst.first_drought", ">=", [0, 20, 40]), ("burst.distinct_pk", ">=", [1, 3, 4]),
                   ("burst.max_bar_vol_ratio", ">=", [0, 10, 15]), ("burst.peak_age_max", ">=", [0, 125]),
                   ("tb.day_drop", "<", [None, 0.2])]
    FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
    MIN_COUNT_PER_FOLD = 100
    REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
                 "tb.stop_confirm_bars": 2, "tb.big_rise_k": 5.0}     # 参照 = 此检测组合 × 全部谓词最松档
    NEIGHBOR_AXES = "all"
    B_BOOT, SEED, TOP_N = 300, 0, 20
    FLAG_RULES = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
    OUT_DIR = "docs/research/2026-08-25_multivar-bb_v1/"

    out = REPO / OUT_DIR
    _check_head_buffer(out / "ledger.md", HEAD_BUFFER)
    df = _load(REPO / LONGTABLE_DIR)
    preds = FILTER_PREDS + WHERE_PREDS
    prep = prepare(df, COMBO_LEVELS, preds, FOLD_COL, FOLDS)
    axes = list(range(prep.n_combo_axes + prep.n_pred_axes)) if NEIGHBOR_AXES == "all" else NEIGHBOR_AXES
    ref_index = tuple(COMBO_LEVELS[c].index(REF_POINT[c]) for c in COMBO_LEVELS) + (0,) * prep.n_pred_axes
    R = analyze_tensor(prep, ref_index, MIN_COUNT_PER_FOLD, axes)
    shape = R["s_nb"].shape
    n_cells = int(np.prod(shape)); n_eval = int(R["evaluable"].sum()); n_neg = int((R["s_nb"] < 0).sum())
    c_hat = int(R["order"][0]); c_idx = np.unravel_index(c_hat, shape)
    tol = tolerance(R["s_nb"], c_idx)
    bs = bootstrap(prep, ref_index, MIN_COUNT_PER_FOLD, axes, B_BOOT, SEED, TOP_N)
    sh = split_half(prep, ref_index, MIN_COUNT_PER_FOLD, axes, SEED)
    naive = float(R["s_nb"].ravel()[c_hat]); corrected = naive - bs["optimism"]

    # cells.csv(每格一行)
    rows = []
    fp, cnt, delta = R["fp"], R["count"], R["delta"]
    for flat in range(n_cells):
        idx = np.unravel_index(flat, shape); c = cell_coords(prep, flat)
        row = dict(flat=flat, **c, evaluable=bool(R["evaluable"][idx]), s=R["s"][idx], s_nb=R["s_nb"][idx],
                   n_eval_nb=int(R["n_eval_nb"][idx]), boot_top=bs["top_freq"].get(flat, 0))
        for f, fold in enumerate(FOLDS):
            row[f"count_{fold}"] = int(cnt[idx + (f,)]); row[f"fp_{fold}"] = fp[idx + (f,)]; row[f"delta_{fold}"] = delta[idx + (f,)]
        row["flags"] = ";".join(x for x in (r(c) for r in FLAG_RULES) if x)
        rows.append(row)
    cells = pd.DataFrame(rows).sort_values("s_nb", ascending=False, na_position="last")
    cells.to_csv(out / "cells.csv", index=False)

    # 半年诊断视图
    prep6 = prepare(df, COMBO_LEVELS, preds, "fold_6M", sorted(df["fold_6M"].unique()))
    fp6, cnt6 = fp_count(tensor(prep6))
    r6 = []
    for flat in cells["flat"].head(TOP_N):
        idx = np.unravel_index(int(flat), shape)
        r6.append(dict(flat=int(flat), **{f"count_{f}": int(cnt6[idx + (i,)]) for i, f in enumerate(prep6.folds)},
                       **{f"fp_{f}": fp6[idx + (i,)] for i, f in enumerate(prep6.folds)}))
    pd.DataFrame(r6).to_csv(out / "folds_6M.csv", index=False)

    # 图:一维切片 / 二维热力 / bootstrap 频率
    axis_names = list(COMBO_LEVELS) + [c for c, _, _ in preds]
    axis_levels = list(COMBO_LEVELS.values()) + [lv for _, _, lv in preds]
    for ax, name in enumerate(axis_names):
        sl = [slice(None) if i == ax else c_idx[i] for i in range(len(shape))]
        xs = [str(v) for v in axis_levels[ax]]
        plt.figure(figsize=(5, 3.2))
        plt.plot(xs, R["s_nb"][tuple(sl)], "o-", label="s_nb")
        plt.plot(xs, R["s"][tuple(sl)], "s--", label="s")
        for f, fold in enumerate(FOLDS):
            plt.plot(xs, delta[tuple(sl) + (f,)], ":", label=f"Δ{fold}")
        plt.axhline(0, color="k", lw=0.5); plt.title(f"过 ĉ 的切片:{name}"); plt.legend(fontsize=7); plt.tight_layout()
        plt.savefig(out / f"slice_{name}.png", dpi=110); plt.close()
    for a in range(prep.n_combo_axes):
        for b in range(a + 1, prep.n_combo_axes):
            sl = [c_idx[i] for i in range(len(shape))]; sl[a] = slice(None); sl[b] = slice(None)
            Z = R["s_nb"][tuple(sl)]
            plt.figure(figsize=(4.2, 3.6)); plt.imshow(np.where(np.isfinite(Z), Z, np.nan).T, origin="lower", cmap="RdBu", vmin=-0.05, vmax=0.05)
            plt.colorbar(label="s_nb"); plt.xticks(range(len(axis_levels[a])), axis_levels[a], fontsize=7); plt.yticks(range(len(axis_levels[b])), axis_levels[b], fontsize=7)
            plt.xlabel(axis_names[a]); plt.ylabel(axis_names[b]); plt.scatter([c_idx[a]], [c_idx[b]], marker="*", c="k")
            plt.tight_layout(); plt.savefig(out / f"heat_{axis_names[a]}_{axis_names[b]}.png", dpi=110); plt.close()
    top = sorted(bs["top_freq"].items(), key=lambda kv: -kv[1])[:TOP_N]
    if top:
        plt.figure(figsize=(6, 3)); plt.bar([str(k) for k, _ in top], [v for _, v in top]); plt.xticks(rotation=90, fontsize=6)
        plt.title(f"bootstrap 入选前 {TOP_N} 频次"); plt.tight_layout(); plt.savefig(out / "boot_top.png", dpi=110); plt.close()

    # 报告
    ref_c = cell_coords(prep, int(np.ravel_multi_index(ref_index, shape)))
    ev_axes = []
    for ax, name in enumerate(axis_names):
        ok = R["evaluable"].any(axis=tuple(i for i in range(len(shape)) if i != ax))
        ev_axes.append(f"{name}: 可评估档 {[str(v) for v, o in zip(axis_levels[ax], ok) if o]}")
    lines = [f"# region_find 报告", "", f"- 长表 {LONGTABLE_DIR};HEAD_BUFFER={HEAD_BUFFER};fold={FOLDS};功效线 {MIN_COUNT_PER_FOLD}/fold;邻域轴 {NEIGHBOR_AXES}",
             f"- 联合空间 {shape} = {n_cells} 格;可评估 {n_eval};不可评估 {n_cells - n_eval};邻域分为负 {n_neg}",
             f"- 参照格 {ref_c}:" + ";".join(f"{fold} count {int(cnt[ref_index + (f,)])} FP {fp[ref_index + (f,)]:.4f}" for f, fold in enumerate(FOLDS)),
             "", "## 推荐格(邻域最小分最高)", f"- ĉ = {cell_coords(prep, c_hat)}", f"- naive s_nb = {naive:.4f};optimism 校正 = {corrected:.4f}(上界);split-half = {sh:.4f}(下界)",
             f"- bootstrap:选中格稳定性 P(ĉ_b ∈ N(ĉ)) = {bs['stability']:.2f};s_nb(ĉ) 95% CI = [{bs['ci'][0]:.4f}, {bs['ci'][1]:.4f}](B={B_BOOT})",
             f"- 容错宽度(向下档数, 向上档数):" + "; ".join(f"{axis_names[a]} {tol[a]}" for a in tol),
             "", "## 可评估面", *[f"- {x}" for x in ev_axes], "", f"## 前 {TOP_N} 格", "",
             cells.head(TOP_N).to_markdown(index=False, floatfmt=".4f"), "",
             "## 读数纪律", "- 三口径并报,不折中;唯一无偏数字是同 HEAD_BUFFER 的 2026 外推窗(本工具不做)。",
             "- 不可评估 ≠ 坏:计数不足的格只报计数;不降功效线硬凑。", "- 半年诊断视图见 folds_6M.csv;标记列 flags 见 cells.csv。",
             "", "## 下一步", "- 同 HEAD_BUFFER 的 2026 窗独立验证推荐格与其邻域(tune-gates 现流程)。"]
    (out / "region_report.md").write_text("\n".join(lines))
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 在冒烟长表上跑通**

复制到 `docs/research/2026-08-25_multivar-bb_v1/repro/region_find_smoke.py`，常量改成与 Task 8 冒烟一致：`LONGTABLE_DIR = ".../smoke/longtable/"`、`OUT_DIR = ".../smoke/"`、`COMBO_LEVELS = {"burst.gap_max": [8, 12], "tb.stop_confirm_bars": [1, 2]}`、`FILTER_PREDS = []`、`WHERE_PREDS = [("burst.first_drought", ">=", [0, 20])]`、`REF_POINT = {"burst.gap_max": 8, "tb.stop_confirm_bars": 2}`、`MIN_COUNT_PER_FOLD = 5`、`B_BOOT = 30`、`FLAG_RULES = []`。
Run: `uv run python docs/research/2026-08-25_multivar-bb_v1/repro/region_find_smoke.py`
Expected: 生成 `smoke/region_report.md`、`cells.csv`（8 行）、`folds_6M.csv`、3 张 `slice_*.png`、1 张 `heat_*.png`；报告首段数字合理（可评估格数 ≤ 8）。若 `to_markdown` 缺 `tabulate` → `uv add tabulate`。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/tune-gates/region_core.py .claude/skills/tune-gates/test_region_core.py .claude/skills/tune-gates/region_find.py docs/research/2026-08-25_multivar-bb_v1/repro/region_find_smoke.py pyproject.toml uv.lock
git commit -m "feat(tune-gates): region_core bootstrap/optimism/split-half + region_find 报告与图(联合空间、不可评估≠坏、三口径并报)"
```

---

### Task 11: SKILL.md 第 4 步与红线改写

**Files:**
- Modify: `.claude/skills/tune-gates/SKILL.md`

- [ ] **Step 1: 改写第 4 步「必须真扫参数的调参」**

用 `grep -n "必须真扫参数的调参" .claude/skills/tune-gates/SKILL.md` 定位，把从 `**必须真扫参数的调参**：` 起到该 bullet 末尾（`且放减法之后。`）整段替换为：

```markdown
**必须真扫参数的调参（多维稳健区 v2）**：不再逐档全宇宙 scan。① `multivar_core.classify` 探针分类（W where 阈值 / F 过滤型 / D 构造参数 / E 边参数）；② 选 D/F 维 4 档左右 + 声明 where 维档位，`multivar_scan.py` 一次**每股反转循环**（上游流缓存、每检测组合 solve、label 按 span 记忆化）出候选长表——6 维 4096 格 × where 档全宇宙分钟级；③ `region_find.py` 在**联合空间**（真扫维 × where 维）上：功效线按格按 fold 标「不可评估」→ 相对每 fold 参照（宽进底座格）的增量 → fold 最小 → r=1 邻域最小 → 排序 → 按股 cluster bootstrap（稳定性 + CI）→ 选择后校正三口径（naive / optimism / split-half）并报；④ 人复核切片图 / 热力图 / 可评估面 / 机制合理性；⑤ 同 HEAD_BUFFER 的外推窗独立验证。OAT 降级为选维线索与复核视图（`plateau.py` 可吃 `cells.csv` 的一维切片）。**先对拍后读数**：长表与逐格 `engine.analyze` 的抽样对拍（`test_multivar_equiv.py` 思路扩到 ≥500 股）零差之后才读 region。**不是所有真扫参数都值得扫**：机制合理值（atr_window / vol_baseline_period / 口径选项）不动；`k` 与 `atr_window` 共线二选一；`first_drought_min ≤ gap_max` 的格闸恒真（报告 flags）。反转路径不产出 gate_failures，诊断走单格 scan。
```

- [ ] **Step 2: 红线段追加**

在「## 红线（硬约束）」列表末尾追加：
```markdown
- **多维稳健区不取 argmax、不用绝对 τ**：推荐 = r=1 邻域最小分最高的格，容错按「邻域分仍为正的跨度」报告；增量相对每 fold 参照。
- **联合空间，禁两段式**：区域在真扫维 × where 维上一起算；「宽进态找区、事后单独收紧 where」是组间切片漂移，禁。
- **功效线按格按 fold，不可评估 ≠ 坏**：任一 fold count 低于功效线标「不可评估」（报计数不报比例、不作邻居、不作墙）；主口径年折，半年为诊断视图；**不降功效线硬凑**。
- **检验 = 按股 bootstrap + 三口径并报**：optimism 校正当上界、split-half 当下界、naive 只作参考；唯一无偏数字是同 HEAD_BUFFER 的外推窗。不做 permutation、不做中心重跑。
- **fold 计数 / 功效线 / 参照增量必须与长表同 HEAD_BUFFER**：`region_find` 读 ledger 核对；不同缓冲的 scan 文件不得跨行比较（2026-08 教训：eval_meta≈70 窗与 buf250 混比，把窗口截断读成 where 效应）。
- **预算便宜之后仍要选择后校正**：4096 格选 1 的抬高 +1～2.5 pt 与效应同量级；报告不得只报 naive。
- **不引入优化 / 采样框架**（optuna / LHS / GP / racing）；只有 detector 全是状态机、上游对下游不独立时才走 2 档全因子 → 坍缩维 → 补档的退路。
```

- [ ] **Step 3: 「plateau.py 用法」段后加工具入口**

```markdown
## multivar_scan.py / region_find.py 用法

```
uv run python .claude/skills/tune-gates/multivar_scan.py     # 常量在 main() 起始处;复制到研究目录改常量后运行
uv run python .claude/skills/tune-gates/region_find.py       # 读 multivar_scan 的 longtable/ 与 ledger.md
uv run pytest .claude/skills/tune-gates/test_multivar_core.py .claude/skills/tune-gates/test_region_core.py -q
uv run pytest .claude/skills/tune-gates/test_multivar_equiv.py -q     # 真实数据对拍(数分钟)
```
```

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/tune-gates/SKILL.md
git commit -m "docs(tune-gates): 第 4 步改走多维稳健区 v2(反转循环 + 联合空间),红线增删"
```

---

### Task 12: 端到端——bb_v1 对拍基准 + fold 计数对拍 + 全网格 + region_find + final_report

**Files:**
- Create: `docs/research/2026-08-25_multivar-bb_v1/repro/compare_longtable_vs_scan.py`
- Create: `docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_full.py`、`region_find_full.py`（复制 skill 脚本改常量）
- Create: `docs/research/2026-08-25_multivar-bb_v1/final_report.md`

- [ ] **Step 1: 全宇宙长表**

复制 `.claude/skills/tune-gates/multivar_scan.py` 为 `docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_full.py`（常量保持 skill 默认：6 维 4 档、5 个 where 维、`TICKER_REGEX=None`、`WORKERS=8`）。
Run: `time uv run python docs/research/2026-08-25_multivar-bb_v1/repro/multivar_scan_full.py 2>&1 | tail -20`
Expected: 完成，`ledger.md` 有耗时；预期 wall ≈ 15～30 min @8w（研究 T1+ 实测 16 min）。> 1 h 则在 final_report 解释（检查 `influence_dims` 是否让 bo 被多余重跑：ledger 行数 ≈ 6720 股 × 2668 行/股 ≈ 17.9M）。

- [ ] **Step 2: 对拍脚本（§6.4 第 1、5 条）**

创建 `docs/research/2026-08-25_multivar-bb_v1/repro/compare_longtable_vs_scan.py`：
```python
"""端到端对拍:全宇宙长表按格谓词聚合 vs 逐格 engine.analyze + serialize(抽样 ≥500 股)。
(a) 3 维 80 格(scb×min_bos×gap_max,bo 参照档);(b) 6 维随机 64 格 + 全部 64 角点;(c) 两套收紧 where(FINAL/B)。
键 = (各节点 span, fr 12 位, 四态) 多重集 + 每股 match_fp_counts。用法:uv run python <本文件>
"""
import itertools, json, random, subprocess, sys, time
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from multivar_core import apply_overrides, classify, col_of, node_col  # noqa: E402
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402


def main():
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    TICKER_REGEX = r"^[A-Z][A-C]"          # 跨字母抽样(≥500 股)
    SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3], ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
                 ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
                 ("tb", "stop_confirm_bars"): [0, 1, 2, 3], ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
    WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40], ("burst", "distinct_pk_min"): [1, 3, 4],
                    ("burst", "vol_spike_min"): [0, 10, 15], ("burst", "peak_age_min"): [0, 125], ("tb", "max_day_drop_pct"): [None, 0.2]}
    WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0}, "tb": {"max_day_drop_pct": None}}
    WHERES = {"wide": {d: lv[0] for d, lv in WHERE_LEVELS.items()},
              "FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15, ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2},
              "B": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2}}
    H, K, SEED = 40, 5.0, 11
    config.set_runtime_checks(True)
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    dims = list(SCAN_GRID); rng = random.Random(SEED)
    ref_bo = {("bo", "min_relative_height"): 0.2, ("bo", "exceed_threshold"): 0.003}
    cells_a = [dict(ref_bo, **dict(zip(dims[2:], v))) for v in itertools.product(*(SCAN_GRID[d] for d in dims[2:]))]      # 80 格(K 只有 4 档→64;spec 说 80 含 K=4,本网格 K∈0..3 → 64)
    allc = [dict(zip(dims, v)) for v in itertools.product(*SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (SCAN_GRID[d][0], SCAN_GRID[d][-1]) for d in dims)]
    cells_b = rng.sample(allc, 64) + corners
    plan = [("a", c, "wide") for c in cells_a] + [("b", c, "wide") for c in cells_b] + [("c", c, w) for c in rng.sample(cells_a, 12) for w in ("FINAL", "B")]

    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
    bs = str((s - pd.Timedelta(days=round(250 * TRADING_TO_CALENDAR_RATIO))).date()); be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    syms = [p for p in _list_pkls(str(REPO / "datasets/pkls"), TICKER_REGEX)]
    print(f"股票 {len(syms)};对拍项 {len(plan)}"); t0 = time.time(); mism = n_cmp = 0
    sub = df[df["symbol"].isin({p.stem for p in syms})]
    for tag, cell, wname in plan:
        where = WHERES[wname]
        p = mod.Params.from_dict(apply_overrides(BASE, WIDE, {**cell, **where}), strict=True); spec = mod.build_pattern(p)
        m = pd.Series(True, index=sub.index)
        for d, v in cell.items():
            if cls.kinds[d] == "F":
                n, f, _ = cls.filter_fields[d]; m &= sub[node_col(n, f)] >= v
            else:
                m &= sub[col_of(d)] == v
        for d, v in where.items():
            if v is None:
                continue
            n, f, op = cls.where_fields[d]; x = sub[node_col(n, f)]
            m &= (x >= v) if op == ">=" else (x < v)
        got_rows = sub[m]
        for pk in syms:
            win = slice_window(pd.read_pickle(pk), bs, be)
            if len(win) < 300:
                continue
            lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
            res = analyze(spec, win, p)
            out = serialize_per_pattern_result(res, end_node="tb", label_horizon=H, win=win, start_ts=s, end_ts=e,
                                               price_min=0.5, price_max=30.0, first_passage_k=K, sample_window=(lo, hi))
            keep = {x["match_id"]: x for x in out["analysis"]["matches"]}
            ref = sorted((tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(mm.node_index.items())),
                          None if keep[mm.match_id]["forward_return"] is None else round(keep[mm.match_id]["forward_return"], 12),
                          *(keep[mm.match_id]["first_passage"] or {"up": 0, "down": 0, "both": 0, "none": 0}).values())
                         for mm in res.matches if mm.match_id in keep)
            g = got_rows[got_rows["symbol"] == pk.stem]
            got = sorted((tuple((n, int(r[node_col(n, "start")]), int(r[node_col(n, "end")])) for n in ("bo", "burst", "tb")),
                          None if pd.isna(r["fr"]) else round(float(r["fr"]), 12), int(r["fp_up"]), int(r["fp_down"]), int(r["fp_both"]), int(r["fp_none"]))
                         for _, r in g.iterrows())
            n_cmp += 1
            if ref != got or out["match_fp_counts"] != {k: int(g[f"fp_{k}"].sum()) for k in ("up", "down", "both", "none")}:
                mism += 1; print("MISMATCH", tag, pk.stem, cell, wname, len(ref), len(got))
    print(f"对拍 {n_cmp} 股×格,mismatch={mism},{time.time() - t0:.0f}s")


main()
```
Run: `uv run python docs/research/2026-08-25_multivar-bb_v1/repro/compare_longtable_vs_scan.py 2>&1 | tail -5`
Expected: `mismatch=0`（耗时长：≈ 600 股 × 200 项逐格 analyze，可能 1～2 h；可先把 `TICKER_REGEX` 改 `^[A-Z]A` 缩到 ~300 股跑通再放大）。**任何 mismatch 都不得通过改键消化**，回 Task 7 排查。输出末行抄进 final_report。

- [ ] **Step 3: fold 计数对拍（同代码新扫）**

写一次性脚本 `docs/research/2026-08-25_multivar-bb_v1/repro/fold_counts_check.py`：
```python
"""参照格 × FINAL / B where 的年折 count:长表谓词聚合 vs 当前代码 run_scan_multi 新扫(同 HEAD_BUFFER=250)。"""
import json, subprocess, sys, time
from pathlib import Path
import pandas as pd
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_web.discovery import PatternRegistry


def main():
    BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    WHERES = {"FINAL": dict(first_drought_min=20, distinct_pk_min=4, vol_spike_min=15, peak_age_min=0),
              "B": dict(first_drought_min=20, distinct_pk_min=3, vol_spike_min=10, peak_age_min=0)}
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    ref = (df["bo.min_relative_height"] == 0.2) & (df["bo.exceed_threshold"] == 0.003) & (df["burst.gap_max"] == 8) \
        & (df["tb.stop_confirm_bars"] == 2) & (df["tb.big_rise_k"] == 5.0) & (df["burst.count"] >= 1) & (df["tb.day_drop"] < 0.2)
    reg = PatternRegistry(); mod = reg.get("bb_v1")
    for name, w in WHERES.items():
        m = ref & (df["burst.first_drought"] >= w["first_drought_min"]) & (df["burst.distinct_pk"] >= w["distinct_pk_min"]) \
            & (df["burst.max_bar_vol_ratio"] >= w["vol_spike_min"]) & (df["burst.peak_age_max"] >= w["peak_age_min"])
        lt_counts = df[m].groupby("fold_Y").size().to_dict()
        snap = json.loads(json.dumps(BASE)); snap["burst"].update(w); snap["tb"]["max_day_drop_pct"] = 0.2
        p = mod.Params.from_dict(snap, strict=True)
        out = run_scan_multi(data_dir=str(REPO / "datasets/pkls"), pattern_specs_json={"bb_v1": serialize_pattern(mod.build_pattern(p))},
                             module_paths={"bb_v1": reg.module_path("bb_v1")}, pattern_ids=["bb_v1"], end_nodes={"bb_v1": "tb"},
                             head_buffer_trading_days=250, label_horizon=40, start_date="2024-01-01", end_date="2026-01-01",
                             workers=8, ticker_regex=None, scan_ts=time.strftime("%Y%m%dT%H%M%S"), pattern_params_dicts={"bb_v1": p.to_dict()},
                             name=f"foldcheck-{name}", price_min=0.5, price_max=30.0, volume_min=10000.0,
                             first_passage_enabled=True, first_passage_k=5.0, outputs_root=str(REPO / "outputs/path2_web"))
        sc = {}
        for r in out["results"]:
            pr = (r.get("per_pattern") or {}).get("bb_v1")
            for mm in (pr["analysis"]["matches"] if pr else []):
                sc[mm["buy_date"][:4]] = sc.get(mm["buy_date"][:4], 0) + 1
        print(name, "长表", lt_counts, "新扫", sc, "研究§5.3 参考", {"FINAL": "73/92", "B": "164/172"}[name])
        assert lt_counts == sc, f"{name} fold 计数不一致"


main()
```
Run: `uv run python docs/research/2026-08-25_multivar-bb_v1/repro/fold_counts_check.py`
Expected: 两行 `长表 == 新扫`（断言通过），并打印研究参考值；结果抄进 final_report（含与 73/92、164/172 的偏差与解释：代码版本 / peak_age / 毒药闸口径）。若 `run_scan_multi` 返回值不含 `results`，改读它落盘的 `outputs/path2_web/scans/foldcheck-<name>.json`。

- [ ] **Step 4: region_find 全量**

复制 `.claude/skills/tune-gates/region_find.py` 为 `docs/research/2026-08-25_multivar-bb_v1/repro/region_find_full.py`（常量保持默认）。
Run: `time uv run python docs/research/2026-08-25_multivar-bb_v1/repro/region_find_full.py 2>&1 | tail -15`
Expected: `region_report.md`、`cells.csv`（1024 × 4 × 108 = 442,368 行）、`folds_6M.csv`、10 张 slice、10 张 heat、`boot_top.png`；耗时以 bootstrap 为主（300 × 4 次 bincount 于 17.9M 行 ≈ 5～10 min）。

- [ ] **Step 5: final_report.md**

写 `docs/research/2026-08-25_multivar-bb_v1/final_report.md`，节：① 目的与口径（HEAD_BUFFER 250、窗、底座 = OAT 快照、网格与 where 档）；② 预算实测（ledger 的 wall / 行数 / 每股 ms；与研究预期 16～24 min 对照）；③ 对拍（Step 2 输出末行、Step 3 两行）；④ region 读数（报告首段 + 推荐格 + 三口径 + 稳定性 + 可评估面；**按格陈述**，不可评估的格只报计数）；⑤ 与研究 §5.3/§5.4 预期的对照（FINAL where 切片是否在参照格附近不可评估、gap_max≥12 / K≤1 一侧是否可评估；B where 是否大部分可评估）；⑥ 诚实边界（bb_v1 已判无 edge；tb 简化分支落地后需重跑；唯一无偏数字是 2026 外推窗，本轮未做）；⑦ 文件清单。

- [ ] **Step 6: 提交**

```bash
git add docs/research/2026-08-25_multivar-bb_v1/repro docs/research/2026-08-25_multivar-bb_v1/final_report.md docs/research/2026-08-25_multivar-bb_v1/ledger.md docs/research/2026-08-25_multivar-bb_v1/region_report.md docs/research/2026-08-25_multivar-bb_v1/cells.csv docs/research/2026-08-25_multivar-bb_v1/folds_6M.csv docs/research/2026-08-25_multivar-bb_v1/*.png
git commit -m "docs(research): bb_v1 多维稳健区 v2 端到端——全宇宙反转扫描 + 逐格对拍零差 + fold 计数对拍 + region 报告"
```
（`longtable/` 与 `smoke/` 不提交，`.gitignore` 已在 Task 8 写入。若 `cells.csv` > 50 MB 则改为只提交 `cells_top200.csv`：`head -201 cells.csv > cells_top200.csv`。）

---

### Task 13: `reference.md` 操作卡（端到端之后）

**Files:**
- Create: `.claude/skills/tune-gates/reference.md`

- [ ] **Step 1: 写操作卡（只写 Task 12 真跑过的内容）**

结构：
```markdown
# 多维稳健区操作卡(pattern 无关)

## 0. 何时用
必须真扫参数 ≥ 2 维、或想把 where 闸与真扫维联合评估时。单闸微调仍走 plateau.py。

## 1. 准备
- 参照底座:生产参数快照 json(不是 Params.default());where 维放机制下限(WIDE_OVERRIDES)
- HEAD_BUFFER 定一个值写死(bb_v1:250),两脚本同值
- 数据/输出目录;pyarrow

## 2. 分类与选维
`classify` 探针输出 W/F/D/E;SCAN_GRID 只放 D/F,WHERE_LEVELS 只放 W;共线维二选一;机制值不动

## 3. 扫描
复制 multivar_scan.py 改常量 → 跑 → ledger.md(记录 wall、行数、fold 计数分布);断点续跑按股

## 4. 对拍(必做,读 region 之前)
compare_longtable_vs_scan.py 思路:≥500 股 × 随机格 + 角点 + 收紧 where,mismatch=0;fold 计数与同代码新扫相等

## 5. 识别
复制 region_find.py 改常量(COMBO_LEVELS / FILTER_PREDS / WHERE_PREDS / REF_POINT / 功效线)→ region_report.md + cells.csv + 图

## 6. 复核(人)
切片图形状、热力图可评估面、flags、三口径、稳定性;推荐 ≠ 采用

## 7. 外推
同 HEAD_BUFFER 的下一窗独立验证推荐格与邻域

## 8. 坑(本轮实证)
[从 Task 12 的 final_report 抄:实际耗时、mismatch 排查经历、fold 计数偏差原因、tabulate 依赖、cells.csv 体积……]

## 附录 A · bb_v1 实例
底座快照要点 / 网格 / where 档 / 参照格 / 结果一行摘要 / 下一步
```
每一节填 Task 12 的真实数字与命令，不写未跑过的选项。

- [ ] **Step 2: 提交**

```bash
git add .claude/skills/tune-gates/reference.md
git commit -m "docs(tune-gates): 多维稳健区操作卡(据 bb_v1 端到端实跑沉淀)"
```

---

## Self-Review

**Spec 覆盖**：§0 前置三项 → Task 1/2/3；§2 文件表 → Task 0-13 逐项对应（`multivar_core`/`region_core` 拆纯函数层）；§3.1-3.2 → Task 7/8；§3.3 negation 检查 → Task 6 `check_where_axes` + Task 7 调用；`day_drop` 恒计算 → Task 2；§3.4 `filter_params` → Task 5/6；§4 → Task 9/10（联合空间 / 不可评估 / 相对参照 / 邻域最小无 pad / bootstrap / 三口径 / flags / 图 / 报告 / 6M 视图）；§5-§8 → Task 11；§6 端到端三项 → Task 12；§7 测试表 → 各 Task；reference.md 后置 → Task 13。§9 退路不实施（spec 明示）。

**类型一致性**：`ScanConfig` 字段名在 Task 7/8/12 一致；`classify` 返回的 `kinds/where_fields/filter_fields` 在 Task 6/7/8/12 一致；`node_col(n, f)` 列名 `"node.field"` 与 Task 10 `region_find` 的 `burst.count / burst.first_drought / tb.day_drop` 一致；`col_of(dim)` `"section.field"` 与 `COMBO_LEVELS` 键一致；`prepare` 的 `pred_specs` 元素 `(col, op, levels)` 与 `FILTER_PREDS/WHERE_PREDS` 一致；`analyze_tensor` 键在 Task 10 报告代码中逐一使用。

**已知偏差**：spec §6 写「3 维 80 格」（K 5 档），本 plan 网格 K∈{0,1,2,3} 4 档 → 64 格；对拍覆盖不变（Task 12 注释已标）。
