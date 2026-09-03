# 多维稳健区调参工具链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 tune-gates skill 增加「必须真扫参数的多维稳健区调参」工具链（ATR 性能修复 → scan 文件 per-match 字段 → 设计/扫描/台账脚本 → 区域识别脚本 → skill 文档），pattern 无关，并在 bb_v1 上端到端跑通。

**Architecture:** 引擎侧两处纯实现修复（`calculate_atr` 向量化；throwback 三版本 ATR 算一次）+ `serialize.py` 给 match 加 `buy_date`/`first_passage`；skill 侧两个独立脚本 `multivar_scan.py`（设计 → 逐点 `run_scan_multi` → `ledger.csv`）与 `region_find.py`（ledger → 网格 → 连通分量 → Chebyshev center → permutation → 图/报告），纯函数与 `main()` 分离以便单测。不引入任何优化框架。

**Tech Stack:** Python 3.12 / numpy / pandas / scipy（`ndimage`、`stats.qmc`）/ scikit-learn（仅 lhs 模式 GP）/ matplotlib / pytest；包管理 `uv`。

**Spec:** `docs/superpowers/specs/2026-08-23-multivar-robust-region-design.md`

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**；绝对路径只用于 `datasets/pkls` 以外的系统路径（本 plan 无）。
- 实施基线：分支 `worktree-oat-optuna-blend`（本 worktree 目录直接执行）。实施前 `git status --short` 确认工作区干净。bb_v1 在本分支**没有** `burst.peak_age_min` / `tb.max_day_drop_pct` 字段（它们在 tune_v1 worktree 未提交）——宽进 override 里这两个键会被 `Params.from_dict` 非严格模式警告忽略，属预期；reference.md 附录提到它们是面向合并后的 bb_v1。
- 入口脚本**不用 argparse**；全部参数为 `main()` 起始处的大写常量。
- 不引入 optuna / Ax / 任何优化框架；不改 `path2/dag/` 引擎；不为旧 scan 文件做兼容。
- 数值红线：`calculate_atr` 新旧实现逐值 `atol=1e-12`；ATR 修复前后同子集 scan 的 `(symbol, match_id)` 集合与 `forward_return` 完全相同。
- 指标契约：FP = `up/(up+down+both)`；`f_robust = min(各 fold FP)`；任一 fold `count < MIN_COUNT_PER_FOLD` → 该点 fail。
- 测试命令统一 `uv run pytest <path> -q`；提交信息中文、前缀 `feat/fix/test/docs/perf`。
- 数据：`datasets/pkls/*.pkl`（8325 只，DataFrame 含 `date/open/high/low/close/volume`，约 1252 行）。数据缺失时涉及真实数据的测试 `pytest.skip`。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `path2/calc/atr.py` | `calculate_atr` 向量化 | 修改 |
| `path2/atoms/throwback_v1.py` | detect 算一次 ATR，`evaluate_throwback` 可接收 `atr` | 修改 |
| `path2/atoms/throwback_v0.py` | 同上 | 修改 |
| `path2/atoms/throwback.py` | detect 算一次 ATR | 修改 |
| `path2_web/serialize.py` | match dict 加 `buy_date`、`first_passage` | 修改 |
| `.claude/skills/tune-gates/multivar_scan.py` | 参数分类打印、设计生成、逐点 scan、fold 聚合、ledger | 新建 |
| `.claude/skills/tune-gates/region_find.py` | 区域识别、permutation、τ 灵敏度、图、报告 | 新建 |
| `.claude/skills/tune-gates/reference.md` | 多维稳健区操作卡 | 新建 |
| `.claude/skills/tune-gates/SKILL.md` | 第 5 步升级 + 红线 | 修改 |
| `tests/path2/calc/test_atr_equivalence.py` | ATR 逐值等价 | 新建 |
| `tests/path2_web/test_serialize_match_fp.py` | per-match 字段不变式 | 新建 |
| `tests/skills/__init__.py`、`tests/skills/test_multivar_scan.py`、`tests/skills/test_region_find.py` | 脚本纯函数单测 | 新建 |
| `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py` | 一次性回归脚本（修复前/后子集 scan 对比） | 新建 |
| `docs/research/2026-08-23_multivar-bb_v1/` | 端到端产出（design/ledger/图/report） | 新建 |

---

### Task 1: `calculate_atr` 向量化 + 逐值等价测试 + 回归基线采集

**Files:**
- Modify: `path2/calc/atr.py`（函数 `calculate_atr`，约第 8-31 行）
- Create: `tests/path2/calc/test_atr_equivalence.py`
- Create: `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py`

**Interfaces:**
- Produces: `calculate_atr(highs, lows, closes, period=14) -> pd.Series` 签名与返回不变（index 同 `closes`，前 `period-1` 为 NaN）。
- Produces: `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py`，`MODE="before"|"after"|"compare"`；`before/after` 各跑一次子集 scan 落 `outputs/path2_web/scans/atr-regress-<mode>.json`，`compare` 比对两文件。Task 2 复用。

- [ ] **Step 1: 采集修复前回归基线（必须在改任何代码之前）**

创建 `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py`：

```python
"""ATR 修复回归脚本:子集 scan 修复前后 match 集 + forward_return 逐项相同。
用法:改 MODE 后 `uv run python docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py`
  before  → 修复前跑,落 outputs/path2_web/scans/atr-regress-before.json
  after   → 修复后跑,落 outputs/path2_web/scans/atr-regress-after.json
  compare → 比对两文件
"""
import json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))


def _scan(name: str) -> None:
    from path2_web.scan import run_scan_multi
    from path2_web.serialize import serialize_pattern
    from path2_web.discovery import PatternRegistry
    PID = "bb_v1"
    reg = PatternRegistry()
    mod = reg.get(PID)
    snap = mod.Params.default().to_dict()
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)   # 宽进:候选多,覆盖 ATR 路径
    snap["tb"]["max_day_drop_pct"] = None
    p = mod.Params.from_dict(snap)
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
        for m in r["per_pattern"]["bb_v1"]["analysis"]["matches"]:
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

运行（MODE 保持 `before`）：`uv run python docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py`
Expected: 打印 `atr-regress-before: <秒>s`，文件 `outputs/path2_web/scans/atr-regress-before.json` 存在。记录秒数到 ledger。

- [ ] **Step 2: 写等价测试（含旧实现作参考）**

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

- [ ] **Step 3: 运行测试确认当前通过（旧实现即 golden，此时应全绿）**

Run: `uv run pytest tests/path2/calc/test_atr_equivalence.py -q`
Expected: PASS（3 项 + 参数化 2）。

- [ ] **Step 4: 向量化实现**

替换 `path2/calc/atr.py` 中 `calculate_atr` 函数体（docstring 保留并补一句「numpy 标量递推,与 pandas 逐行实现逐值等价」）：

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

注意：`pandas` 的 `tr.iloc[:period].mean()` 对 NaN 是 skipna 均值，故 `nanmean` 对齐；`tr` 中 NaN 参与递推时 pandas 也会把 NaN 传播下去，numpy 同样传播——行为一致。

- [ ] **Step 5: 运行等价测试**

Run: `uv run pytest tests/path2/calc/test_atr_equivalence.py tests/path2/atoms -q`
Expected: 全 PASS（atoms 下既有 throwback/platform 测试零回归）。

- [ ] **Step 6: 提交**

```bash
git add path2/calc/atr.py tests/path2/calc/test_atr_equivalence.py docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py
git commit -m "perf(calc): calculate_atr 改 numpy 标量递推(38x),逐值等价测试 + ATR 回归基线脚本"
```

---

### Task 2: throwback 三版本 ATR 算一次 + 回归对比 + 计时

**Files:**
- Modify: `path2/atoms/throwback_v1.py`（`_atr_at` 第 95-100 行；`evaluate_throwback` 签名第 282-292 行与第 318 行调用；`detect` 第 419-441 行）
- Modify: `path2/atoms/throwback_v0.py`（`_atr_at` 第 91-96 行；`evaluate_throwback` 第 259 行起、第 294 行调用；`detect` 第 387-394 行）
- Modify: `path2/atoms/throwback.py`（`_atr_at` 第 251-255 行；`detect` 第 296-318 行）

**Interfaces:**
- Produces: 三文件 `_atr_at(atr: pd.Series, idx: int) -> float`（越界/NaN → 0.0）。
- Produces: `throwback_v1.evaluate_throwback(..., atr: Optional[pd.Series] = None, ...)`、`throwback_v0.evaluate_throwback(..., atr: Optional[pd.Series] = None, ...)`——`None` 时函数内自算（保持既有直接调用方/测试不变），`detect` 传入预算序列。

- [ ] **Step 1: throwback_v1**

`_atr_at` 改为：
```python
def _atr_at(atr: pd.Series, idx: int) -> float:
    """预算 ATR 序列在 idx 处的值;越界/NaN → 0.0。"""
    if idx < 0 or idx >= len(atr):
        return 0.0
    v = float(atr.iat[idx])
    return v if v == v else 0.0
```
`evaluate_throwback` 签名在 `scb_mode` 之后增加 `atr: Optional[pd.Series] = None,`；第 318 行改为：
```python
    if atr is None:
        atr = calculate_atr(df['high'], df['low'], df['close'], atr_window)
    atr_v = _atr_at(atr, bo_idx - 1)     # ★ bo-1:避开 bo 当根异常 TR
    if atr_v <= 0.0:
        return None
```
并把该函数后续所有使用标量 `atr` 的地方改名为 `atr_v`（grep `atr` 在 `evaluate_throwback` 函数体内逐处确认：乘法阈值、`MeasuredKindAware`、`_emit_tb_gate` 的 measured 等）。
`detect` 在 `for burst in burst_stream:` 之前加：
```python
        atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])
```
调用改为 `evaluate_throwback(last_bo, df, anchor=anchor, atr=atr_series, on_gate=self.on_gate, **tb_kw)`（`tb_kw` 来源 `self._kw`，其中含 `atr_window`——保留，`evaluate_throwback` 仍需要它做 lookback 记录）。

- [ ] **Step 2: throwback_v0**

同 Step 1 的三处改法（`_atr_at` 签名、`evaluate_throwback` 加 `atr=None` 并在第 294 行前补自算、`detect` 预算一次后 `evaluate_throwback(last_bo, df, anchor=anchor, atr=atr_series, on_gate=self.on_gate, **self._kw)`）。

- [ ] **Step 3: throwback.py**

`_atr_at` 改为同 Step 1 签名；`detect` 在 `events = []` 之后、`for bo in bo_stream:` 之前加 `atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])`；第 317 行改为 `atr = _atr_at(atr_series, bo_idx - 1)`。检查文件内是否还有其他 `calculate_atr(`/`_atr_at(` 调用（`grep -n "_atr_at(\|calculate_atr(" path2/atoms/throwback.py`），全部改为读 `atr_series`。

- [ ] **Step 4: 全量 atoms 测试**

Run: `uv run pytest tests/path2 -q`
Expected: 全 PASS（既有 throwback v0/v1/v2+ 测试直接调 `evaluate_throwback` 不传 `atr`，走自算分支）。

- [ ] **Step 5: 回归对比**

把 `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py` 的 `MODE` 改 `"after"` 运行，再改 `"compare"` 运行。
Expected: `compare` 打印 `OK: N match 逐项相同`。记录 after 秒数；`before/after` 之比预期 ≥ 5。

- [ ] **Step 6: 全宇宙计时（一次）**

临时把 `atr_regress.py` 的 `ticker_regex` 改 `None`、`workers=24`、MODE=`"after"`、name 改 `"atr-timing-full"` 跑一次，记录秒数（预期 ≤ 60 s；修复前 266 s），跑完把改动还原（保持 MODE="compare" 与子集正则）。结果写进 `docs/research/2026-08-23_multivar-bb_v1/atr-timing.md`（三行：before 子集 / after 子集 / after 全量）。

- [ ] **Step 7: 提交**

```bash
git add path2/atoms/throwback_v1.py path2/atoms/throwback_v0.py path2/atoms/throwback.py docs/research/2026-08-23_multivar-bb_v1/atr-timing.md docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py
git commit -m "perf(atoms): throwback v0/v1/v2 每股算一次 ATR 序列,消除 per-candidate 重算;子集回归逐项相同"
```

---

### Task 3: scan 文件 per-match 增加 `buy_date` 与 `first_passage`

**Files:**
- Modify: `path2_web/serialize.py`（`serialize_per_pattern_result`，第 335-392 行）
- Create: `tests/path2_web/test_serialize_match_fp.py`

**Interfaces:**
- Produces: 每个 `analysis["matches"][i]` 新增 `"buy_date": str`（`YYYY-MM-DD`，end_node 事件起始日）与 `"first_passage": {"up":int,"down":int,"both":int,"none":int} | None`。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2_web/test_serialize_match_fp.py`（fixture 写法照 `tests/path2_web/test_serialize_price_filter.py`）：

```python
"""serialize_per_pattern_result:match 级 buy_date + first_passage 四态。
不变式:非 None 的 first_passage 四态逐项求和 == match_fp_counts。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bottom_burst import build_pattern, Params, eval_meta
from path2.dag.engine import analyze as engine_analyze
from path2.eval import _resolve_end_events

PKL_DIR = Path("datasets/pkls")


def _pick_pkl_with_match():
    if not PKL_DIR.exists():
        return None
    spec = build_pattern(Params.default())
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:
        df = pd.read_pickle(p)
        if len(df) < 200:
            continue
        win = df.iloc[-300:].reset_index()
        if len(engine_analyze(spec, win, Params.default()).matches) > 0:
            return p
    return None


@pytest.fixture
def scene():
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("datasets/pkls 里没有能命中的股;skip")
    df = pd.read_pickle(p)
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(build_pattern(Params.default()), win, Params.default())
    meta = eval_meta()
    return res, meta, win, pd.to_datetime(win["date"].iat[0]), pd.to_datetime(win["date"].iat[-1])


def _run(scene, **kw):
    res, meta, win, s, e = scene
    return serialize_per_pattern_result(res, end_node=meta["end_node"], label_horizon=5,
                                        win=win, start_ts=s, end_ts=e, **kw)


def test_fields_present_and_sum_invariant(scene):
    out = _run(scene)
    ms = out["analysis"]["matches"]
    assert ms, "fixture 应至少一个 match"
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

在 `serialize_per_pattern_result` 中：
1. 第 339 行附近的 dict 区增加 `fp_by_id: dict = {}` 与 `date_by_id: dict = {}`。
2. `leaf_by_id[m.match_id] = leaf_ev.instance_id` 之后加：
   `date_by_id[m.match_id] = str(pd.to_datetime(win["date"].iat[leaf_ev.start_idx]).date())`
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
Expected: 全 PASS（既有 serialize/scan 测试零回归；`test_api_scan_multi` 等若断言 match keys 精确集合需同步加两个键——按失败信息修）。

- [ ] **Step 5: 提交**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize_match_fp.py
git commit -m "feat(web): scan 文件 match 级增加 buy_date 与 first_passage 四态(供 fold 聚合)"
```

---

### Task 4: `multivar_scan.py`（设计 → 逐点 scan → fold 聚合 → ledger）

**Files:**
- Create: `.claude/skills/tune-gates/multivar_scan.py`
- Create: `tests/skills/__init__.py`（空）、`tests/skills/test_multivar_scan.py`

**Interfaces:**
- Produces（纯函数，供测试与 Task 5 复用，均在该文件模块级）：
  - `classify_params(mod) -> dict[str, str]`：key `"<section>.<field>"`，value `"真扫"|"可切"|"未知"`。
  - `make_design(design) -> list[dict]`：`design=("grid", {(sec, field): [levels]})` 或 `("lhs", {"dims": {(sec, field): (low, high, step|None)}, "n": int, "seed": int})`；返回每点 `{"point_id": "p0000", (sec, field): value, ...}`，grid 顺序 = `itertools.product` 按 dims 插入顺序。
  - `fold_of(date_str, mode) -> str`：`mode="6M"` → `"2024H1"`；`"Y"` → `"2024"`。
  - `aggregate_folds(scan_blob, pid, mode, start_date, end_date) -> list[dict]`：每 fold 一行 + `"ALL"` 行，列 `fold,count,fp_up,fp_down,fp_both,fp_none,fp,fr_median`；只统计 `buy_date ∈ [start_date, end_date]` 的 match；`fp` = `up/(up+down+both)`，分母 0 → `None`；`count` = 非 None `first_passage` 数；`fr_median` = 非 None `forward_return` 中位数（无则 `None`）。
  - `LEDGER_COLUMNS = ["point_id", *dims, "fold", "count", "fp_up", "fp_down", "fp_both", "fp_none", "fp", "fr_median", "scan_path"]`，dims 列名 `"<sec>.<field>"`。
  - ledger 每行一个 (point, fold)。

- [ ] **Step 1: 写失败测试**

创建 `tests/skills/__init__.py`（空文件）与 `tests/skills/test_multivar_scan.py`：

```python
"""multivar_scan 纯函数:参数分类 / 设计生成 / fold 聚合。"""
import importlib.util
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location(
    "multivar_scan", Path(".claude/skills/tune-gates/multivar_scan.py"))
mv = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mv)


def test_classify_bb_v1():
    from path2_web.discovery import PatternRegistry
    mod = PatternRegistry().get("bb_v1")
    if mod is None:
        pytest.skip("bb_v1 未注册")
    c = mv.classify_params(mod)
    assert c["tb.stop_confirm_bars"] == "真扫"
    assert c["burst.min_bos"] == "真扫"
    assert c["burst.first_drought_min"] == "可切"
    assert c["burst.distinct_pk_min"] == "可切"


def test_grid_design_order_and_ids():
    d = mv.make_design(("grid", {("tb", "stop_confirm_bars"): [0, 1], ("burst", "min_bos"): [1, 2, 3]}))
    assert len(d) == 6
    assert d[0]["point_id"] == "p0000" and d[5]["point_id"] == "p0005"
    assert [(p[("tb", "stop_confirm_bars")], p[("burst", "min_bos")]) for p in d[:3]] == [(0, 1), (0, 2), (0, 3)]


def test_lhs_design_projection_and_seed():
    dims = {("bo", "min_relative_height"): (0.1, 0.3, None), ("burst", "gap_max"): (4, 20, 4)}
    a = mv.make_design(("lhs", {"dims": dims, "n": 16, "seed": 0}))
    b = mv.make_design(("lhs", {"dims": dims, "n": 16, "seed": 0}))
    assert a == b and len(a) == 16
    for p in a:
        assert 0.1 <= p[("bo", "min_relative_height")] <= 0.3
        assert p[("burst", "gap_max")] in (4, 8, 12, 16, 20)


@pytest.mark.parametrize("d,mode,exp", [("2024-03-01", "6M", "2024H1"), ("2024-07-01", "6M", "2024H2"),
                                        ("2025-12-31", "6M", "2025H2"), ("2025-05-05", "Y", "2025")])
def test_fold_of(d, mode, exp):
    assert mv.fold_of(d, mode) == exp


def _blob(matches):
    return {"results": [{"symbol": "X", "per_pattern": {"pid": {"analysis": {"matches": matches}}}}]}


def test_aggregate_folds_counts_and_fp():
    ms = [
        {"buy_date": "2024-02-01", "first_passage": {"up": 2, "down": 1, "both": 0, "none": 1}, "forward_return": 0.1},
        {"buy_date": "2024-02-02", "first_passage": None, "forward_return": 0.3},          # 去重 leaf:不计 count
        {"buy_date": "2024-09-01", "first_passage": {"up": 0, "down": 0, "both": 0, "none": 3}, "forward_return": None},
        {"buy_date": "2023-12-31", "first_passage": {"up": 9, "down": 0, "both": 0, "none": 0}, "forward_return": 9.0},  # 窗外
    ]
    rows = mv.aggregate_folds(_blob(ms), "pid", "6M", "2024-01-01", "2026-01-01")
    by = {r["fold"]: r for r in rows}
    assert by["2024H1"]["count"] == 1 and by["2024H1"]["fp"] == pytest.approx(2 / 3)
    assert by["2024H1"]["fr_median"] == pytest.approx(0.2)
    assert by["2024H2"]["count"] == 1 and by["2024H2"]["fp"] is None
    assert by["ALL"]["count"] == 2 and by["ALL"]["fp_up"] == 2
    assert "2023H2" not in by
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/skills/test_multivar_scan.py -q`
Expected: FAIL（文件不存在）。

- [ ] **Step 3: 实现脚本**

创建 `.claude/skills/tune-gates/multivar_scan.py`：

```python
"""tune-gates · 多维稳健区 · 第一步:设计 → 逐点全宇宙 scan → fold 聚合 → ledger.csv。

用法:复制到研究目录,改 main() 顶部常量,`uv run python <路径>`。
- 参数分类打印(真扫/可切/未知)帮助选维,不替人选。
- 设计:("grid", {(sec, field): [档位...]}) 全因子;或 ("lhs", {...}) 拉丁超立方(≥5 维)。
- 逐点串行 run_scan_multi(scan 内部已多进程);scan 文件已存在且 params_hash 相同 → 跳过(断点续跑)。
- ledger.csv 每 (point, fold) 一行,每点完成即追加。
"""
from __future__ import annotations

import copy
import csv
import inspect
import itertools
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists() and REPO.parent != REPO:
    REPO = REPO.parent
sys.path.insert(0, str(REPO))

from path2_web.discovery import PatternRegistry            # noqa: E402
from path2_web.scan import run_scan_multi, params_hash      # noqa: E402
from path2_web.serialize import serialize_pattern           # noqa: E402


# ---------- 纯函数 ----------

def classify_params(mod) -> dict:
    """Params 各 section 字段 → 真扫(进 detector 构造签名)/可切(不进任何构造)/未知。"""
    from dataclasses import fields
    p = mod.Params.default()
    spec = mod.build_pattern(p)
    ctor = set()
    for node in spec.nodes:
        det = getattr(node, "detector", None)
        if det is None:
            continue
        ctor |= set(inspect.signature(type(det).__init__).parameters) - {"self"}
    out = {}
    for sec, sect_cls in mod.Params._sections().items():
        for f in fields(sect_cls):
            key = f"{sec}.{f.name}"
            out[key] = "真扫" if f.name in ctor else "可切"
    return out


def make_design(design) -> list:
    kind, cfg = design
    if kind == "grid":
        dims = list(cfg.keys())
        pts = []
        for i, combo in enumerate(itertools.product(*[cfg[d] for d in dims])):
            pts.append({"point_id": f"p{i:04d}", **dict(zip(dims, combo))})
        return pts
    if kind == "lhs":
        from scipy.stats import qmc
        dims = list(cfg["dims"].keys())
        n, seed = int(cfg["n"]), int(cfg.get("seed", 0))
        u = qmc.LatinHypercube(d=len(dims), optimization="random-cd",
                               rng=np.random.default_rng(seed)).random(n)
        pts = []
        for i in range(n):
            row = {"point_id": f"p{i:04d}"}
            for j, d in enumerate(dims):
                lo, hi, step = cfg["dims"][d]
                if step is None:
                    row[d] = float(lo + (hi - lo) * u[i, j])
                else:
                    k = int(round((hi - lo) / step)) + 1
                    row[d] = type(lo)(lo + min(int(u[i, j] * k), k - 1) * step)
            pts.append(row)
        return pts
    raise ValueError(f"未知设计类型 {kind}")


def fold_of(date_str: str, mode: str) -> str:
    y, m = date_str[:4], int(date_str[5:7])
    if mode == "Y":
        return y
    if mode == "6M":
        return f"{y}H{1 if m <= 6 else 2}"
    raise ValueError(f"未知 fold 模式 {mode}")


def aggregate_folds(blob: dict, pid: str, mode: str, start_date: str, end_date: str) -> list:
    acc: dict = {}
    def _row():
        return {"up": 0, "down": 0, "both": 0, "none": 0, "count": 0, "rets": []}
    for r in blob["results"]:
        for m in r["per_pattern"].get(pid, {}).get("analysis", {}).get("matches", []):
            d = m["buy_date"]
            if not (start_date <= d <= end_date):
                continue
            for key in (fold_of(d, mode), "ALL"):
                a = acc.setdefault(key, _row())
                fp = m.get("first_passage")
                if fp is not None:
                    a["count"] += 1
                    for s in ("up", "down", "both", "none"):
                        a[s] += int(fp[s])
                if m.get("forward_return") is not None:
                    a["rets"].append(float(m["forward_return"]))
    rows = []
    for key in sorted(k for k in acc if k != "ALL") + (["ALL"] if "ALL" in acc else []):
        a = acc[key]
        den = a["up"] + a["down"] + a["both"]
        rows.append({"fold": key, "count": a["count"], "fp_up": a["up"], "fp_down": a["down"],
                     "fp_both": a["both"], "fp_none": a["none"],
                     "fp": (a["up"] / den) if den else None,
                     "fr_median": statistics.median(a["rets"]) if a["rets"] else None})
    return rows


def dim_name(d) -> str:
    return f"{d[0]}.{d[1]}"


# ---------- 入口 ----------

def main() -> None:
    # ===== 参数(全部在此声明) =====
    PATTERN_ID = "bb_v1"
    DATA_DIR = "datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER = 250                       # 完整检测值;训练与外推必须同值
    LABEL_HORIZON = 40
    FIRST_PASSAGE_K = 5.0
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 24
    REF_SCAN = None                         # 参照 scan 路径(取 params_snapshot 作底座);None → Params.default()
    WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                      "tb": {"max_day_drop_pct": None}}   # 可切闸全放开;pattern 无该字段时 from_dict 非严格模式警告忽略
    DESIGN = ("grid", {("tb", "stop_confirm_bars"): [0, 1, 2, 3, 4],
                       ("burst", "min_bos"): [1, 2, 3, 4],
                       ("burst", "gap_max"): [4, 8, 12, 20]})
    FOLD = "6M"                             # "6M" | "Y"
    OUT_DIR = "docs/research/2026-08-23_multivar-bb_v1"
    TICKER_REGEX = None                     # 冒烟用子集正则,如 r"^A[A-C]"
    # ==============================

    reg = PatternRegistry()
    mod = reg.get(PATTERN_ID)
    if mod is None:
        raise SystemExit(f"registry 无 {PATTERN_ID}: {reg.errors()}")
    cls = classify_params(mod)
    print("参数分类(真扫=进 detector 构造;可切=只进 where,事后零成本切档,勿进设计;"
          "构造内纯 filter 型参数(如 tb.max_day_drop_pct)虽报真扫,可按可切处理——人判):")
    for k, v in cls.items():
        print(f"  {v}  {k}")
    dims = list(DESIGN[1].keys()) if DESIGN[0] == "grid" else list(DESIGN[1]["dims"].keys())
    for d in dims:
        if cls.get(dim_name(d)) != "真扫":
            print(f"  ⚠ 设计维 {dim_name(d)} 分类为 {cls.get(dim_name(d))},请确认是否该进多维搜索")

    out_dir = REPO / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    design = make_design(DESIGN)
    with (out_dir / "design.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["point_id", *[dim_name(d) for d in dims]])
        for p in design:
            w.writerow([p["point_id"], *[p[d] for d in dims]])

    base = (json.loads(Path(REF_SCAN).read_text())["per_pattern"][PATTERN_ID]["params_snapshot"]
            if REF_SCAN else mod.Params.default().to_dict())
    for sec, kv in WIDE_OVERRIDES.items():
        base[sec].update(kv)

    ledger_path = out_dir / "ledger.csv"
    cols = ["point_id", *[dim_name(d) for d in dims], "fold", "count", "fp_up", "fp_down",
            "fp_both", "fp_none", "fp", "fr_median", "scan_path"]
    done = set()
    if ledger_path.exists():
        with ledger_path.open() as f:
            done = {r["point_id"] for r in csv.DictReader(f)}
    else:
        with ledger_path.open("w", newline="") as f:
            csv.writer(f).writerow(cols)

    scans_dir = REPO / "outputs/path2_web/scans"
    t_all = time.time()
    for i, p in enumerate(design):
        if p["point_id"] in done:
            continue
        snap = copy.deepcopy(base)
        for d in dims:
            snap[d[0]][d[1]] = p[d]
        params = mod.Params.from_dict(snap)
        name = f"mv-{PATTERN_ID}-{p['point_id']}"
        scan_path = scans_dir / f"{name}.json"
        t0 = time.time()
        reuse = False
        if scan_path.exists():
            blob = json.loads(scan_path.read_text())
            reuse = blob["per_pattern"][PATTERN_ID].get("params_hash") == params_hash(params.to_dict())
        if not reuse:
            run_scan_multi(
                data_dir=str(REPO / DATA_DIR),
                pattern_specs_json={PATTERN_ID: serialize_pattern(mod.build_pattern(params))},
                module_paths={PATTERN_ID: reg.module_path(PATTERN_ID)}, pattern_ids=[PATTERN_ID],
                end_nodes={PATTERN_ID: mod.eval_meta(params=params)["end_node"]},
                head_buffer_trading_days=HEAD_BUFFER, label_horizon=LABEL_HORIZON,
                start_date=START_DATE, end_date=END_DATE, workers=WORKERS,
                ticker_regex=TICKER_REGEX, scan_ts=time.strftime("%Y%m%dT%H%M%S"),
                pattern_params_dicts={PATTERN_ID: params.to_dict()},
                params_provenance={PATTERN_ID: f"multivar:{p['point_id']}"},
                note=f"multivar {dict((dim_name(d), p[d]) for d in dims)}", name=name,
                price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
                first_passage_enabled=True, first_passage_k=FIRST_PASSAGE_K,
                outputs_root=str(REPO / "outputs/path2_web"),
            )
            blob = json.loads(scan_path.read_text())
        rows = aggregate_folds(blob, PATTERN_ID, FOLD, START_DATE, END_DATE)
        with ledger_path.open("a", newline="") as f:
            w = csv.writer(f)
            for r in rows:
                w.writerow([p["point_id"], *[p[d] for d in dims], r["fold"], r["count"], r["fp_up"],
                            r["fp_down"], r["fp_both"], r["fp_none"],
                            "" if r["fp"] is None else f"{r['fp']:.6f}",
                            "" if r["fr_median"] is None else f"{r['fr_median']:.6f}",
                            str(scan_path.relative_to(REPO))])
        all_row = next(r for r in rows if r["fold"] == "ALL")
        print(f"[{i + 1}/{len(design)}] {p['point_id']} {'复用' if reuse else f'{time.time() - t0:.0f}s'} "
              f"count={all_row['count']} fp={all_row['fp']}")

    # 收尾:fold count 分布,供功效线校验
    with ledger_path.open() as f:
        rows = [r for r in csv.DictReader(f) if r["fold"] != "ALL"]
    by_fold: dict = {}
    for r in rows:
        by_fold.setdefault(r["fold"], []).append(int(r["count"]))
    print(f"总耗时 {(time.time() - t_all) / 60:.1f} min;各 fold count(min/median):")
    for k in sorted(by_fold):
        v = sorted(by_fold[k]); print(f"  {k}: min={v[0]} median={v[len(v) // 2]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行单测**

Run: `uv run pytest tests/skills/test_multivar_scan.py -q`
Expected: PASS。

- [ ] **Step 5: 冒烟（小子集 + 2×2 网格 + 断点续跑）**

复制脚本到 `docs/research/2026-08-23_multivar-bb_v1/repro/multivar_scan_smoke.py`，改：`DESIGN=("grid", {("tb","stop_confirm_bars"): [1, 2], ("burst","min_bos"): [1, 2]})`、`FOLD="Y"`、`TICKER_REGEX=r"^A[A-C]"`、`OUT_DIR="docs/research/2026-08-23_multivar-bb_v1/smoke"`、`WORKERS=8`。运行两次。
Expected：第一次打印 4 点各耗时与 count；`smoke/design.csv` 4 行、`smoke/ledger.csv` 4×3 行（2024/2025/ALL）；第二次 4 点全部不重扫（ledger 已有 point_id → 跳过，打印「复用」或直接跳过）。跑完删除 `smoke/` 目录与 4 个 `mv-bb_v1-p000*.json`（避免与端到端同名冲突）。

- [ ] **Step 6: 提交**

```bash
git add .claude/skills/tune-gates/multivar_scan.py tests/skills/__init__.py tests/skills/test_multivar_scan.py docs/research/2026-08-23_multivar-bb_v1/repro/multivar_scan_smoke.py
git commit -m "feat(skill): tune-gates multivar_scan——设计生成/逐点 scan/fold 聚合/ledger(断点续跑)"
```

---

### Task 5: `region_find.py` grid 模式（核心纯函数 + 合成测试）

**Files:**
- Create: `.claude/skills/tune-gates/region_find.py`
- Create: `tests/skills/test_region_find.py`

**Interfaces:**
- Produces（模块级纯函数）：
  - `load_ledger(path, dims, folds, min_count) -> tuple[list[list], np.ndarray]`：返回 `(levels, F)`；`levels[j]` = 第 j 维升序档位列表；`F` 形状 `(len(levels[0]), …)`，值 = `f_robust`（各 fold fp 的 min；任一 fold 缺行 / fp 空 / count<min_count → NaN）。
  - `find_regions(F, tau, r_min) -> list[dict]`：按 inradius 降序；每项 `{"label", "inradius", "n_cells", "center_idx": tuple, "min_f", "widths": list[tuple[int,int]]}`（widths 为各维 index 跨度 `(lo, hi)`）；`inradius < r_min` 的分量也返回但 `"robust": False`。盒外 pad False；edt 单位网格。
  - `permutation_test(F, tau, observed_inradius, observed_cells, n_perm, seed) -> dict`：`{"p_inradius", "p_cells"}`；NaN 格子固定不动，仅置换非 NaN 格子的 pass/fail 标签。
  - `tau_sensitivity(F, taus, r_min) -> list[dict]`：每 τ `{"tau", "inradius", "n_cells", "center_idx"}`（无分量时 inradius=0、center_idx=None）。

- [ ] **Step 1: 写失败测试**

创建 `tests/skills/test_region_find.py`：

```python
"""region_find 纯函数:合成 3 维网格(已知椭球达标区 + 噪声)。"""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "region_find", Path(".claude/skills/tune-gates/region_find.py"))
rf = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(rf)


def _ellipsoid_field(shape=(9, 9, 9), center=(4, 4, 4), radii=(3.0, 2.0, 2.5), noise=0.02, seed=0):
    """真值:椭球内 0.6、外 0.4,加高斯噪声;τ=0.5。返回 F 与真 mask。"""
    rng = np.random.default_rng(seed)
    idx = np.indices(shape).astype(float)
    d2 = sum(((idx[k] - center[k]) / radii[k]) ** 2 for k in range(3))
    truth = d2 <= 1.0
    F = np.where(truth, 0.6, 0.4) + rng.normal(0, noise, shape)
    return F, truth


def test_center_inside_truth_and_inradius_close():
    F, truth = _ellipsoid_field()
    regs = rf.find_regions(F, tau=0.5, r_min=1.0)
    assert regs and regs[0]["robust"]
    c = regs[0]["center_idx"]
    assert truth[c], f"center {c} 不在真区"
    # 真 inradius ≈ min(radii)=2.0(格);允许 ±30%
    assert 1.4 <= regs[0]["inradius"] <= 2.6


def test_nan_cells_are_fail_and_box_edge_is_fail():
    F = np.full((5, 5, 5), 0.9)          # 全达标:盒外 pad fail → 中心应在正中,inradius=3(含 pad 后到边界距离)
    F[0, 0, 0] = np.nan
    regs = rf.find_regions(F, tau=0.5, r_min=1.0)
    assert regs[0]["center_idx"] == (2, 2, 2)


def test_all_fail_returns_empty():
    F = np.full((4, 4, 4), 0.1)
    assert rf.find_regions(F, tau=0.5, r_min=1.0) == []


def test_permutation_no_false_positive_on_random_labels():
    rng = np.random.default_rng(1)
    fp_rate = []
    for seed in range(20):
        F = rng.uniform(0.3, 0.7, (6, 6, 6))
        regs = rf.find_regions(F, tau=0.5, r_min=0.0)
        if not regs:
            fp_rate.append(0); continue
        r = rf.permutation_test(F, 0.5, regs[0]["inradius"], regs[0]["n_cells"], n_perm=200, seed=seed)
        fp_rate.append(1 if r["p_inradius"] < 0.05 else 0)
    assert sum(fp_rate) <= 2       # ≥90% 的随机场不报显著


def test_permutation_detects_real_structure():
    F, _ = _ellipsoid_field(noise=0.01)
    regs = rf.find_regions(F, tau=0.5, r_min=1.0)
    r = rf.permutation_test(F, 0.5, regs[0]["inradius"], regs[0]["n_cells"], n_perm=300, seed=0)
    assert r["p_inradius"] < 0.05


def test_tau_sensitivity_monotone_cells():
    F, _ = _ellipsoid_field()
    rows = rf.tau_sensitivity(F, taus=[0.45, 0.5, 0.55], r_min=1.0)
    cells = [r["n_cells"] for r in rows]
    assert cells[0] >= cells[1] >= cells[2]


def test_load_ledger_min_count_and_min_fold(tmp_path):
    p = tmp_path / "ledger.csv"
    p.write_text(
        "point_id,tb.stop_confirm_bars,burst.min_bos,fold,count,fp_up,fp_down,fp_both,fp_none,fp,fr_median,scan_path\n"
        "p0000,0,1,2024H1,150,60,40,0,0,0.600000,0.1,x\n"
        "p0000,0,1,2024H2,150,50,50,0,0,0.500000,0.1,x\n"
        "p0000,0,1,ALL,300,110,90,0,0,0.550000,0.1,x\n"
        "p0001,1,1,2024H1,150,70,30,0,0,0.700000,0.1,x\n"
        "p0001,1,1,2024H2,20,15,5,0,0,0.750000,0.1,x\n"     # count<100 → NaN
        "p0001,1,1,ALL,170,85,35,0,0,0.708333,0.1,x\n")
    levels, F = rf.load_ledger(p, dims=["tb.stop_confirm_bars", "burst.min_bos"],
                               folds=["2024H1", "2024H2"], min_count=100)
    assert levels == [[0, 1], [1]]
    assert F.shape == (2, 1)
    assert F[0, 0] == pytest.approx(0.5)
    assert np.isnan(F[1, 0])
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/skills/test_region_find.py -q`
Expected: FAIL（文件不存在）。

- [ ] **Step 3: 实现（纯函数 + grid 模式 main）**

创建 `.claude/skills/tune-gates/region_find.py`：

```python
"""tune-gates · 多维稳健区 · 第二步:ledger → f_robust 网格 → 达标连通分量 → Chebyshev center
→ permutation 零假设检验 → τ 灵敏度 → 切片图/热力图 → region_report.md。

红线:不取 argmax;达标区成立 = inradius ≥ R_MIN 且 permutation p < 0.05;中心点必须真跑一次全量 scan。
grid 模式直接在网格格子上做(无代理模型);lhs 模式(Task 6)先 GP 回归落网格。
"""
from __future__ import annotations

import csv
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import ndimage

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists() and REPO.parent != REPO:
    REPO = REPO.parent


# ---------- 纯函数 ----------

def _to_num(s: str):
    try:
        return int(s)
    except ValueError:
        return float(s)


def load_ledger(path, dims: list, folds: list, min_count: int):
    rows = list(csv.DictReader(Path(path).open()))
    levels = [sorted({_to_num(r[d]) for r in rows}) for d in dims]
    F = np.full([len(l) for l in levels], np.nan)
    by_point: dict = {}
    for r in rows:
        by_point.setdefault(r["point_id"], {})[r["fold"]] = r
    for pid, fr in by_point.items():
        any_row = next(iter(fr.values()))
        idx = tuple(levels[j].index(_to_num(any_row[d])) for j, d in enumerate(dims))
        vals = []
        ok = True
        for f in folds:
            r = fr.get(f)
            if r is None or r["fp"] == "" or int(r["count"]) < min_count:
                ok = False; break
            vals.append(float(r["fp"]))
        F[idx] = min(vals) if ok else np.nan
    return levels, F


def find_regions(F: np.ndarray, tau: float, r_min: float) -> list:
    mask = np.nan_to_num(F, nan=-np.inf) >= tau
    mp = np.pad(mask, 1, constant_values=False)
    labels, n = ndimage.label(mp)
    out = []
    for lab in range(1, n + 1):
        comp = labels == lab
        edt = ndimage.distance_transform_edt(comp)
        inr = float(edt.max())
        c = np.unravel_index(int(edt.argmax()), edt.shape)
        center = tuple(int(i) - 1 for i in c)
        cells = np.argwhere(comp) - 1
        out.append({"label": lab, "inradius": inr, "n_cells": int(comp.sum()),
                    "center_idx": center, "min_f": float(np.nanmin(F[comp[tuple(slice(1, -1) for _ in F.shape)]])),
                    "widths": [(int(cells[:, j].min()), int(cells[:, j].max())) for j in range(F.ndim)],
                    "robust": inr >= r_min})
    out.sort(key=lambda r: -r["inradius"])
    return out


def permutation_test(F, tau, observed_inradius, observed_cells, n_perm=1000, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    valid = ~np.isnan(F)
    labels = (F[valid] >= tau)
    ge_r = ge_c = 0
    for _ in range(n_perm):
        G = np.full(F.shape, np.nan)
        G[valid] = np.where(rng.permutation(labels), tau, tau - 1.0)
        regs = find_regions(G, tau, r_min=0.0)
        best_r = regs[0]["inradius"] if regs else 0.0
        best_c = regs[0]["n_cells"] if regs else 0
        ge_r += best_r >= observed_inradius
        ge_c += best_c >= observed_cells
    return {"p_inradius": (ge_r + 1) / (n_perm + 1), "p_cells": (ge_c + 1) / (n_perm + 1)}


def tau_sensitivity(F, taus, r_min) -> list:
    rows = []
    for t in taus:
        regs = find_regions(F, t, r_min)
        rows.append({"tau": float(t), "inradius": regs[0]["inradius"] if regs else 0.0,
                     "n_cells": regs[0]["n_cells"] if regs else 0,
                     "center_idx": regs[0]["center_idx"] if regs else None})
    return rows


def fold_fp_at(path, dims: list, levels: list, center_idx: tuple) -> dict:
    """center 点各 fold 的 fp/count(报告用)。"""
    want = {d: levels[j][center_idx[j]] for j, d in enumerate(dims)}
    out = {}
    for r in csv.DictReader(Path(path).open()):
        if all(_to_num(r[d]) == want[d] for d in dims):
            out[r["fold"]] = {"fp": (float(r["fp"]) if r["fp"] else None), "count": int(r["count"])}
    return out


# ---------- 图与报告 ----------

def _plots(F, levels, dims, tau, center, sens, out_dir: Path, fold_curves: dict | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out_dir.mkdir(parents=True, exist_ok=True)
    # 一维切片(过 center)
    for j, d in enumerate(dims):
        sl = [slice(None) if k == j else center[k] for k in range(F.ndim)]
        fig, ax = plt.subplots(figsize=(5, 3.2))
        ax.plot(levels[j], F[tuple(sl)], "o-", label="f_robust")
        if fold_curves:
            for f, ys in fold_curves[j].items():
                ax.plot(levels[j], ys, ".--", alpha=0.6, label=f)
        ax.axhline(tau, color="k", ls=":", label="τ")
        ax.axvline(levels[j][center[j]], color="r", ls="--", label="center")
        ax.set_xlabel(d); ax.set_ylabel("FP"); ax.legend(fontsize=7); fig.tight_layout()
        fig.savefig(out_dir / f"slice1d_{d}.png", dpi=120); plt.close(fig)
    # 二维热力图(过 center)
    for a, b in combinations(range(F.ndim), 2):
        sl = [slice(None) if k in (a, b) else center[k] for k in range(F.ndim)]
        Z = F[tuple(sl)]
        fig, ax = plt.subplots(figsize=(4.5, 3.8))
        im = ax.imshow(Z.T, origin="lower", aspect="auto", cmap="viridis",
                       extent=[-0.5, len(levels[a]) - 0.5, -0.5, len(levels[b]) - 0.5])
        ax.contour(np.nan_to_num(Z, nan=-1).T >= tau, levels=[0.5], colors="w")
        ax.plot(center[a], center[b], "r*", ms=12)
        ax.set_xticks(range(len(levels[a]))); ax.set_xticklabels(levels[a])
        ax.set_yticks(range(len(levels[b]))); ax.set_yticklabels(levels[b])
        ax.set_xlabel(dims[a]); ax.set_ylabel(dims[b]); fig.colorbar(im, ax=ax, label="f_robust")
        fig.tight_layout(); fig.savefig(out_dir / f"heat2d_{dims[a]}__{dims[b]}.png", dpi=120); plt.close(fig)
    # τ 灵敏度
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot([s["tau"] for s in sens], [s["inradius"] for s in sens], "o-", label="inradius")
    ax2 = ax.twinx(); ax2.plot([s["tau"] for s in sens], [s["n_cells"] for s in sens], "s--", color="gray", label="cells")
    ax.axvline(tau, color="r", ls="--"); ax.set_xlabel("τ"); ax.set_ylabel("inradius(格)"); ax2.set_ylabel("格数")
    fig.tight_layout(); fig.savefig(out_dir / "tau_sensitivity.png", dpi=120); plt.close(fig)


def _report(out_dir: Path, cfg: dict, levels, dims, regs, perm, sens, fold_at_center, n_fail, n_total):
    L = [f"# 多维稳健区报告 · {cfg['pattern']}", "",
         f"- ledger: `{cfg['ledger']}`  · 维度: {dims}  · folds: {cfg['folds']}",
         f"- τ={cfg['tau']} · MIN_COUNT_PER_FOLD={cfg['min_count']} · R_MIN={cfg['r_min']} 格 · 模式 {cfg['mode']}",
         f"- 点数 {n_total},fail(功效线/缺 fold) {n_fail}", ""]
    if not regs:
        L += ["## 结论:**无达标格子**(τ 下没有任何点各 fold 都达标)。", ""]
    else:
        r0 = regs[0]
        verdict = "有稳健区" if (r0["robust"] and perm["p_inradius"] < 0.05) else "无稳健区"
        L += [f"## 结论:**{verdict}**", "",
              f"- 主区 inradius={r0['inradius']:.2f} 格(R_MIN={cfg['r_min']}) · 格数 {r0['n_cells']} · min f_robust={r0['min_f']:.3f}",
              f"- permutation: p_inradius={perm['p_inradius']:.3f} · p_cells={perm['p_cells']:.3f}(N={cfg['n_perm']})",
              f"- **center**: " + ", ".join(f"{d}={levels[j][r0['center_idx'][j]]}" for j, d in enumerate(dims)),
              "- 各维跨度(档位): " + ", ".join(
                  f"{d}∈[{levels[j][lo]},{levels[j][hi]}]({hi - lo + 1}格)" for j, (d, (lo, hi)) in enumerate(zip(dims, r0['widths']))),
              "", "| fold@center | count | fp |", "|---|---|---|"]
        L += [f"| {f} | {v['count']} | {v['fp']} |" for f, v in fold_at_center.items()]
        L += ["", "### 全部分量", "", "| # | inradius | 格数 | min_f | center | robust |", "|---|---|---|---|---|---|"]
        L += [f"| {r['label']} | {r['inradius']:.2f} | {r['n_cells']} | {r['min_f']:.3f} | "
              f"{tuple(levels[j][r['center_idx'][j]] for j in range(len(dims)))} | {r['robust']} |" for r in regs]
    L += ["", "### τ 灵敏度", "", "| τ | inradius | 格数 | center |", "|---|---|---|---|"]
    L += [f"| {s['tau']:.2f} | {s['inradius']:.2f} | {s['n_cells']} | "
          f"{None if s['center_idx'] is None else tuple(levels[j][s['center_idx'][j]] for j in range(len(dims)))} |" for s in sens]
    L += ["", "### 下一步(强制)", "",
          "1. 用 center 参数真跑一次全量 scan,确认各 fold FP 与 ledger 一致(防代理/噪声假象)。",
          "2. 同 head_buffer 在外推窗独立验证 center(不得挑子窗口)。",
          "3. 机制复核:center 各参数值在机制上讲得通;各维跨度窄的参数需精调、宽的可放。",
          "", "图:`slice1d_*.png`(每维过 center 切片)、`heat2d_*.png`(每对维度热力图)、`tau_sensitivity.png`。"]
    (out_dir / "region_report.md").write_text("\n".join(L), encoding="utf-8")


# ---------- 入口 ----------

def main() -> None:
    # ===== 参数(全部在此声明) =====
    PATTERN_ID = "bb_v1"
    LEDGER = "docs/research/2026-08-23_multivar-bb_v1/ledger.csv"
    DIMS = ["tb.stop_confirm_bars", "burst.min_bos", "burst.gap_max"]    # 顺序即轴序,与设计一致
    FOLDS = ["2024H1", "2024H2", "2025H1", "2025H2"]
    TAU = 0.50
    MIN_COUNT_PER_FOLD = 100
    R_MIN = 1.0
    N_PERM = 1000
    SEED = 0
    MODE = "grid"                       # "grid" | "lhs"(Task 6)
    OUT_DIR = "docs/research/2026-08-23_multivar-bb_v1"
    # ==============================
    out_dir = REPO / OUT_DIR
    ledger = REPO / LEDGER
    levels, F = load_ledger(ledger, DIMS, FOLDS, MIN_COUNT_PER_FOLD)
    if MODE == "lhs":
        raise SystemExit("lhs 模式见 Task 6")
    n_total, n_fail = F.size, int(np.isnan(F).sum())
    regs = find_regions(F, TAU, R_MIN)
    perm = {"p_inradius": float("nan"), "p_cells": float("nan")}
    center = tuple(s // 2 for s in F.shape)
    fold_at = {}
    if regs:
        perm = permutation_test(F, TAU, regs[0]["inradius"], regs[0]["n_cells"], N_PERM, SEED)
        center = regs[0]["center_idx"]
        fold_at = fold_fp_at(ledger, DIMS, levels, center)
    sens = tau_sensitivity(F, np.round(np.arange(TAU - 0.05, TAU + 0.051, 0.01), 2), R_MIN)
    # 各 fold 在 center 切片上的曲线(报告图用)
    rows = list(csv.DictReader(ledger.open()))
    fold_curves = []
    for j, d in enumerate(DIMS):
        cur = {}
        for f in FOLDS:
            ys = []
            for lv in levels[j]:
                want = {DIMS[k]: levels[k][center[k]] for k in range(len(DIMS))}; want[d] = lv
                hit = [r for r in rows if r["fold"] == f and all(_to_num(r[k]) == want[k] for k in DIMS)]
                ys.append(float(hit[0]["fp"]) if hit and hit[0]["fp"] else np.nan)
            cur[f] = ys
        fold_curves.append(cur)
    _plots(F, levels, DIMS, TAU, center, sens, out_dir, fold_curves)
    _report(out_dir, dict(pattern=PATTERN_ID, ledger=LEDGER, folds=FOLDS, tau=TAU, min_count=MIN_COUNT_PER_FOLD,
                          r_min=R_MIN, mode=MODE, n_perm=N_PERM), levels, DIMS, regs, perm, sens, fold_at, n_fail, n_total)
    print((out_dir / "region_report.md").read_text())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/skills/test_region_find.py -q`
Expected: PASS（7 项）。若 `test_center_inside_truth_and_inradius_close` 的 inradius 超出 [1.4, 2.6]，先打印 `regs[0]` 看是否 pad/argmax 映射错位（常见：忘了 `-1`）。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/tune-gates/region_find.py tests/skills/test_region_find.py
git commit -m "feat(skill): tune-gates region_find——网格达标区/Chebyshev center/permutation/τ 灵敏度/切片图/报告"
```

---

### Task 6: `region_find.py` lhs 模式（GP 回归落网格）

**Files:**
- Modify: `.claude/skills/tune-gates/region_find.py`
- Modify: `tests/skills/test_region_find.py`

**Interfaces:**
- Produces: `lhs_to_grid(points: np.ndarray, f: np.ndarray, bounds: list[tuple[float,float]], res: int) -> tuple[list[np.ndarray], np.ndarray]`：`points` 形状 `(n, d)`，`f` 长 n（NaN = fail）；返回 `(levels, F)`，`levels[j]` 为 `np.linspace(lo, hi, res)`，`F` 为 GP 后验均值网格；fail 点按最近邻把网格格子置 NaN（半径 = 各维量程 / res）。

- [ ] **Step 1: 加测试**

追加到 `tests/skills/test_region_find.py`：

```python
def test_lhs_to_grid_recovers_center():
    rng = np.random.default_rng(0)
    n = 200
    pts = rng.uniform(0, 1, (n, 2))
    truth_c = np.array([0.6, 0.4])
    f = np.where(((pts - truth_c) ** 2).sum(1) <= 0.15 ** 2, 0.6, 0.4) + rng.normal(0, 0.02, n)
    levels, F = rf.lhs_to_grid(pts, f, bounds=[(0, 1), (0, 1)], res=20)
    assert F.shape == (20, 20) and len(levels) == 2
    regs = rf.find_regions(F, tau=0.5, r_min=1.0)
    c = np.array([levels[j][regs[0]["center_idx"][j]] for j in range(2)])
    assert np.linalg.norm(c - truth_c) < 0.1


def test_lhs_to_grid_fail_points_mask_nan():
    pts = np.array([[0.5, 0.5], [0.1, 0.1], [0.9, 0.9]])
    f = np.array([0.6, np.nan, 0.6])
    levels, F = rf.lhs_to_grid(pts, f, bounds=[(0, 1), (0, 1)], res=10)
    assert np.isnan(F[1, 1])            # 最近 fail 点所在格
    assert not np.isnan(F[5, 5])
```

Run: `uv run pytest tests/skills/test_region_find.py -q` → 两项 FAIL（`lhs_to_grid` 不存在）。

- [ ] **Step 2: 实现**

在 `region_find.py` 纯函数区追加：

```python
def lhs_to_grid(points: np.ndarray, f: np.ndarray, bounds: list, res: int = 20):
    """LHS 散点 → GP 回归(Matern 2.5 + WhiteKernel,lengthscale 先验=各维量程/2)→ res^d 网格后验均值。
    fail(NaN)点不参与回归,其最近网格格(半径=量程/res)置 NaN。仅中心点可信,形状不可信(调研 §5.5)。"""
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel
    points = np.asarray(points, float); f = np.asarray(f, float)
    lo = np.array([b[0] for b in bounds], float); hi = np.array([b[1] for b in bounds], float)
    X = (points - lo) / (hi - lo)
    ok = ~np.isnan(f)
    kernel = ConstantKernel(1.0) * Matern(length_scale=np.full(X.shape[1], 0.5), nu=2.5) + WhiteKernel(1e-3)
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=3, random_state=0)
    gp.fit(X[ok], f[ok])
    axes = [np.linspace(0, 1, res) for _ in range(X.shape[1])]
    mesh = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, X.shape[1])
    F = gp.predict(mesh).reshape([res] * X.shape[1])
    if (~ok).any():
        cell = np.round(X[~ok] * (res - 1)).astype(int).clip(0, res - 1)
        for c in cell:
            F[tuple(c)] = np.nan
    levels = [np.linspace(b[0], b[1], res) for b in bounds]
    return levels, F
```

`main()` 的 `if MODE == "lhs": raise SystemExit(...)` 改为：

```python
    if MODE == "lhs":
        rows = list(csv.DictReader(ledger.open()))
        pts_by = {}
        for r in rows:
            pts_by.setdefault(r["point_id"], {})[r["fold"]] = r
        P, fv = [], []
        for pid, fr in pts_by.items():
            any_row = next(iter(fr.values()))
            P.append([float(any_row[d]) for d in DIMS])
            vals = [float(fr[f]["fp"]) for f in FOLDS
                    if f in fr and fr[f]["fp"] and int(fr[f]["count"]) >= MIN_COUNT_PER_FOLD]
            fv.append(min(vals) if len(vals) == len(FOLDS) else np.nan)
        P = np.array(P); bounds = [(P[:, j].min(), P[:, j].max()) for j in range(len(DIMS))]
        levels, F = lhs_to_grid(P, np.array(fv), bounds, res=GRID_RES)
        levels = [list(np.round(l, 4)) for l in levels]
```

并在常量区加 `GRID_RES = 20`。lhs 模式下 `fold_curves` 无法逐档位查 ledger（散点不在网格上），把 `fold_curves` 置 `None`，报告首行加一句「lhs 模式:形状来自 GP 代理,仅 center 可信」。

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/skills -q`
Expected: 全 PASS。

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/tune-gates/region_find.py tests/skills/test_region_find.py
git commit -m "feat(skill): region_find lhs 模式——GP 回归落网格(仅 center 可信)"
```

---

### Task 7: SKILL.md 第 5 步升级 + reference.md 操作卡

**Files:**
- Modify: `.claude/skills/tune-gates/SKILL.md`（语义定位：「## 流程（七步）」第 4 步「事后切闸」段内有一句「**必须真扫参数的调参**：围绕当前值定 3-5 档…」，新小节插在该第 4 步条目之后、第 5 步之前；红线追加到「## 红线（硬约束）」节末尾。用 `grep -n "必须真扫参数的调参\|^## 红线" .claude/skills/tune-gates/SKILL.md` 找行号）
- Create: `.claude/skills/tune-gates/reference.md`

- [ ] **Step 1: SKILL.md**

在第 4 步「事后切闸」条目之后插入小节（Markdown 原文；spec 中称「第 5 步」即此处——现行 SKILL.md 把必须真扫参数调参写在第 4 步内）：

```markdown
#### 多维稳健区(必须真扫参数 ≥2 维时的升级路径)
OAT 找平台是在「其他参数固定」的投影切片上找,其他参数一变切片就漂(毒药闸实证)。≥2 维且怀疑交互时改走**多维稳健区**:
1. `multivar_scan.py`(本目录,复制到研究目录改常量):打印参数分类 → 选 2-4 个真扫参数 + 机制上下界档位 → 全因子网格(≥5 维用 lhs)逐点全宇宙 scan → `ledger.csv`(每 point×fold 一行)。
2. `region_find.py`:`f_robust = min(各 fold FP)`(任一 fold count < 功效线 → fail)→ 达标区连通分量 → **Chebyshev center**(离边界最远,不是 argmax)→ permutation 检验 → τ 灵敏度 → 切片图/热力图 → `region_report.md`。
3. 人复核:center 机制合理性、各维跨度(窄=需精调/宽=可放)、fold 表;**center 真跑一次全量 scan;同 head_buffer 外推验证**。
详见 `reference.md`「多维稳健区操作卡」。
```

在红线区追加：

```markdown
- **多维不取 argmax**:必须真扫参数多维调参取达标区 Chebyshev center;可切参数不进多维设计;设计用全因子网格(≥5 维 lhs),**不引入优化框架**。
- **达标区双闸 + 零假设**:inradius ≥ R_MIN 且各 fold 一致(f_robust 用 min);**permutation p < 0.05** 才能说「有区域」(随机标签下 pass 点 12 个时 91% 概率报单连通——不检验就是给噪声起名字)。
- **center 必须真跑**一次全量 scan;训练与外推同 head_buffer,外推独立验证。
- τ / 功效线 / 维度选择由研究者声明并写台账;工具只报灵敏度。
```

- [ ] **Step 2: reference.md**

创建 `.claude/skills/tune-gates/reference.md`（完整内容）：

```markdown
# tune-gates · reference

## 多维稳健区操作卡(pattern 无关)

### 0. 何时用
必须真扫参数(进 detector 构造)≥2 个、怀疑交互或 OAT 分年分裂时。可切参数(只进 where)永远不进设计——宽进扫一次事后切档零成本。

### 1. 准备
- 底座:参照 scan 的 `params_snapshot`(或 `Params.default()`)+ 宽进 override(可切闸全放开)。
- `HEAD_BUFFER` = 完整检测值(加大重扫对比 match 数不再增长的值);**训练与外推同值**。
- 训练窗 ≥2 年;`FOLD="6M"`(4 折)优先,每 fold count 不足则 `"Y"`。

### 2. 选维与定域
- `multivar_scan.py` 先跑一次(任意设计)看「参数分类」打印:真扫候选里按 OAT 线索(有增量/分年分裂优先)+ 机制判断选 **2-4 维**;「OAT 全平」可能是交互被投影抹掉,机制上怀疑就进。分类是机械判定(进构造=真扫):构造内纯 filter(不改几何,detector 只拿它做闸)按可切处理;机制合理值(如 vol_baseline_period=63 一季度、atr_window=14)不调。
- 每维档位按机制上下界等距取 4-6 档(int 带 step 的按自然档位);档位即「一格」,inradius 以格数计。
- 预算:全因子 = ∏档位数 × 单次 scan 时间(bb_v1 宽进 2 年 buf250 ≈ 35 s)。

### 3. 扫描
`DESIGN=("grid", {...})` → 运行 → `design.csv` + `ledger.csv`。中断后重跑自动续(ledger 已有 point_id 跳过;scan 文件 params_hash 相同复用)。
结束打印各 fold count 分布:min < 功效线 → 改 FOLD 或降 MIN_COUNT_PER_FOLD(写台账)。

### 4. 区域识别
`region_find.py`:`DIMS` 顺序=设计顺序;`TAU`(建议:参照点全池 FP 或随机基线 + 裕量);`MIN_COUNT_PER_FOLD`;`R_MIN`(格,默认 1)。
读 `region_report.md`:
- 「无达标格子」→ τ 下无点各 fold 都达标;看 τ 灵敏度,别降 τ 硬凑。
- 「无稳健区」(inradius<R_MIN 或 p≥0.05)→ 达标点零散,是噪声不是区。
- 「有稳健区」→ center + 各维跨度 + fold@center 表。

### 5. 复核(人)
切片图:每维过 center 的一维曲线(f_robust + 各 fold)——平台还是尖峰一眼可见;热力图:每对维度的二维形状——细长对角=两参数可互换、圆=独立。
机制:center 各值讲得通?跨度窄的维需精调,宽的可放。

### 6. 强制动作
1. center 真跑一次全量 scan,核对各 fold FP 与 ledger 一致。
2. 同 head_buffer 外推窗验证 center(全窗,不挑子窗口)。
3. 台账记:τ、功效线、维度选择理由、center、p 值、外推结果。

### 7. lhs 模式(≥5 维)
`DESIGN=("lhs", {"dims": {(sec,field): (lo, hi, step|None)}, "n": 300, "seed": 0})`;`region_find` 设 `MODE="lhs"`:GP 回归落 20^d 网格。**形状不可信、仅 center 可信**(d=4 n=20 区域 IoU 0.26,n=40 center 8/8 落真区)。

### 8. 坑
| 坑 | 说明 |
|---|---|
| 用 argmax | 点可偶然,区域不可偶然;取 center |
| 不做 permutation | pass 点少时「连通」几乎必然出现 |
| τ 硬凑 | τ 灵敏度图上 inradius 随 τ 陡降 = 假区 |
| fold 太粗 | 2 折的 min 很弱;优先 6M |
| 非等距档位 | 一格≠等参数距离,读 widths 表用实际档位值 |
| 训练/外推 head_buffer 不同 | 63 底座 artifact 教训 |

## 附录 A · bb_v1 实例
- 可切:`burst.first_drought_min / distinct_pk_min / vol_spike_min / peak_age_min`、`tb.max_day_drop_pct`(构造内纯 filter,分类器报真扫,按可切处理)。
- 真扫候选:`tb.stop_confirm_bars / big_rise_k`、`burst.gap_max / min_bos`、`bo.min_relative_height / exceed_threshold`。
- OAT 线索(2026-08-20,250 底座):stop_confirm_bars 2→3 唯一分年一致增量;min_bos 分年分裂(疑交互);其余全平。
- 首次多维:`stop_confirm_bars[0..4] × min_bos[1..4] × gap_max[4,8,12,20]` = 80 点;宽进 2 年 buf250;FOLD 6M。
- 已知:bb_v1 外推区突破信号无 edge(bo_only=随机基线);多维结果「无稳健区」是诚实读数。
```

- [ ] **Step 3: 提交**

```bash
git add .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md
git commit -m "docs(skill): tune-gates 第 5 步多维稳健区升级 + 红线 + reference 操作卡"
```

---

### Task 8: 端到端——bb_v1 三维网格 80 点

**Files:**
- Create: `docs/research/2026-08-23_multivar-bb_v1/multivar_scan.py`、`region_find.py`（从 skill 目录复制并改常量）
- Create（运行产物）: `docs/research/2026-08-23_multivar-bb_v1/{design.csv, ledger.csv, region_report.md, *.png}`
- Create: `docs/research/2026-08-23_multivar-bb_v1/final_report.md`

- [ ] **Step 1: 复制并配置**

`cp .claude/skills/tune-gates/multivar_scan.py .claude/skills/tune-gates/region_find.py docs/research/2026-08-23_multivar-bb_v1/`。`multivar_scan.py` 常量保持 Task 4 默认（80 点、FOLD 6M、WORKERS 24、OUT_DIR 同目录）；`region_find.py` 常量保持 Task 5 默认。

- [ ] **Step 2: 跑扫描**

`uv run python docs/research/2026-08-23_multivar-bb_v1/multivar_scan.py`（约 80 × 35 s ≈ 50 min）。
Expected: `ledger.csv` 80×5 行；结束打印各 fold count 分布。若某 fold `min < 100`：记录并把 `region_find.py` 的 `MIN_COUNT_PER_FOLD` 降到该 fold median 的一半（写进 final_report 台账），不改 FOLD。

- [ ] **Step 3: 跑区域识别**

`uv run python docs/research/2026-08-23_multivar-bb_v1/region_find.py`
Expected: 打印 `region_report.md`；目录下 3 张一维切片、3 张热力图、1 张 τ 灵敏度。

- [ ] **Step 4: center 真跑（若报「有稳健区」）**

把 `docs/research/2026-08-23_multivar-bb_v1/repro/atr_regress.py` 复制为 `repro/center_rescan.py`，改 `ticker_regex=None`、`workers=24`、`name="mv-bb_v1-center"`，并在 `p = mod.Params.from_dict(snap)` 之前加（值取 region_report 的 center）：

```python
    CENTER = {("tb", "stop_confirm_bars"): 3, ("burst", "min_bos"): 2, ("burst", "gap_max"): 8}   # ← 按 region_report 改
    for (sec, field), v in CENTER.items():
        snap[sec][field] = v
```

把 `main()` 改为只跑 `_scan("mv-bb_v1-center")`。跑后在同目录写 `repro/center_compare.py`：

```python
import csv, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]; sys.path.insert(0, str(REPO))
import importlib.util
S = importlib.util.spec_from_file_location("mv", REPO / ".claude/skills/tune-gates/multivar_scan.py"); mv = importlib.util.module_from_spec(S); S.loader.exec_module(mv)
blob = json.loads((REPO / "outputs/path2_web/scans/mv-bb_v1-center.json").read_text())
rows = {r["fold"]: r for r in mv.aggregate_folds(blob, "bb_v1", "6M", "2024-01-01", "2026-01-01")}
CENTER_POINT_ID = "p0000"   # ← region_report 的 center 对应 design.csv 的 point_id
led = {r["fold"]: r for r in csv.DictReader((REPO / "docs/research/2026-08-23_multivar-bb_v1/ledger.csv").open()) if r["point_id"] == CENTER_POINT_ID}
for f in led:
    a, b = rows[f]["fp"], (float(led[f]["fp"]) if led[f]["fp"] else None)
    print(f, rows[f]["count"], led[f]["count"], a, b)
    assert rows[f]["count"] == int(led[f]["count"]) and ((a is None and b is None) or abs(a - b) < 1e-9)
print("center 复跑与 ledger 逐 fold 一致")
```

若报「无稳健区」则跳过本步，在 final_report 写明。

- [ ] **Step 5: final_report.md**

写 `docs/research/2026-08-23_multivar-bb_v1/final_report.md`：背景(一段) → 配置(底座/设计/fold/τ/功效线) → ATR 计时表 → fold count 分布 → `region_report.md` 结论摘录 + 切片图/热力图观察(每维平台/尖峰、交互形状) → center 真跑对比(或「无稳健区」说明) → 诚实边界(bb_v1 无 edge,此处为管线验证) → 下一步(外推验证留给有 edge 的新 pattern)。

- [ ] **Step 6: 提交**

```bash
git add docs/research/2026-08-23_multivar-bb_v1/
git commit -m "docs(research): bb_v1 三维稳健区端到端(80 点)——管线验证 + 报告"
```

---

## Self-Review

- **Spec coverage**：§3 ATR → Task 1-2；§4 serialize → Task 3；§5 multivar_scan（分类/设计/断点/fold/ledger/收尾打印）→ Task 4；§6.2 grid 全 9 步 → Task 5（report 含强制动作）；§6.3 lhs → Task 6；§7 测试 → Task 1/3/4/5/6 各自 + Task 2 回归脚本；§8 SKILL/reference → Task 7；§9 端到端 → Task 8；§10 风险的「fold count 不足」处理 → Task 8 Step 2。
- **Placeholder scan**：无 TBD；Task 2 Step 1 要求 grep 确认 `atr→atr_v` 改名是具体动作；Task 3 Step 4 的「按失败信息修」限定为同步新增两个键。
- **Type consistency**：`classify_params/make_design/fold_of/aggregate_folds`（Task 4）名称与测试一致；`load_ledger/find_regions/permutation_test/tau_sensitivity/lhs_to_grid`（Task 5/6）名称、返回结构（`center_idx` tuple、`widths` list[tuple]、`robust` bool）在 `_report` 与测试中一致；ledger 列名 `"<sec>.<field>"` 在 Task 4 写入与 Task 5 `DIMS` 读取一致；`_atr_at(atr, idx)` 三文件同签名。
