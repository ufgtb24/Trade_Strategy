# Scan Stats · Pattern Hover Tooltip 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 web UI 扫描落盘时自动算 per-pattern forward_return 分布 stats,前端命中股列表 hdr-pattern th 上 hover 显示 8 行表格式 tooltip。

**Architecture:** 后端 `run_scan_multi` 落盘前算 stats(复用抽自 `_summarize` 的 `_summarize_flat`)塞进 `MultiScanResultFile.per_pattern[pid].stats`;前端新 `PatternStatsTooltip.vue` 组件 + `SidebarResultList.vue` hover 挂载;旧 JSON 无 stats 字段 → 不挂 tooltip(fallback)。

**Tech Stack:** Python 3.12 · pandas · Vue 3 (`<script setup lang="ts">`) · Pinia · vitest · @vue/test-utils · pytest。

**Spec:** `docs/superpowers/specs/2026-07-13-scan-stats-tooltip-design.md`(必读——每 task 引用其中的 §)。

## Global Constraints

- **口径**: 按 match 计入 forward_return(同一买点多路径命中重复计入),与 UI 面板 `num` 一致;**不做**按买点去重
- **数值 schema**: 原始 float(未乘 100),前端展示时乘;空样本 `count=0`、其余 `null`
- **Fallback**: 旧 JSON 无 `stats` 字段 → 前端不挂 hover,pattern 名照常展示(无警告)
- **前端测试命名**: 遵现有约定 `components.<kebab-name>.spec.ts`
- **subagent 模型**: implementer=`sonnet`,reviewer=`opus`(CLAUDE.md 铁律)
- **四 gate**: `pytest tests/path2_web/`、`vitest`、`vue-tsc`、`vite build` — Task 6 全跑绿
- **入口脚本**: 无 argparse,参数在 `main()` 起始位置(CLAUDE.md)
- **注释语言**: 中文;不加多行 docstring / 装饰性说明;非必要不加注释(CLAUDE.md 编码规范)
- **Commit 格式**: HEREDOC 传 message,末尾 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

---

## Task 1 — 抽 `_summarize_flat`,`_summarize` 内部改调

**Files:**
- Modify: `path2_web/eval_runner.py:103-125`(现有 `_summarize` 区域)
- Modify: `tests/path2_web/test_eval_runner.py`(追加 `_summarize_flat` 单测)

**Interfaces:**
- Consumes: 无(基础任务)
- Produces:
  ```python
  def _summarize_flat(vals: list) -> dict:
      """返回 {count, mean, min, q25, median, q75, max, win_rate}。
      None 值调用者已过滤;空 vals → count=0, 其余 None。"""
  ```
  返回 dict key 顺序: `count` / `mean` / `min` / `q25` / `median` / `q75` / `max` / `win_rate`。

**Spec Ref:** §2.2.1

---

- [ ] **Step 1: 写 `_summarize_flat` 的失败测试**

打开 `tests/path2_web/test_eval_runner.py`,文件顶部 `from path2_web import eval_runner` 已存在。在文件**末尾**追加:

```python
import pytest

from path2_web.eval_runner import _summarize_flat


def test_summarize_flat_empty():
    r = _summarize_flat([])
    assert r["count"] == 0
    for k in ("mean", "min", "q25", "median", "q75", "max", "win_rate"):
        assert r[k] is None, k


def test_summarize_flat_all_negative():
    r = _summarize_flat([-0.1, -0.05, -0.2])
    assert r["count"] == 3
    assert r["mean"] == pytest.approx((-0.1 - 0.05 - 0.2) / 3)
    assert r["min"] == pytest.approx(-0.2)
    assert r["max"] == pytest.approx(-0.05)
    assert r["win_rate"] == 0.0


def test_summarize_flat_all_positive():
    r = _summarize_flat([0.05, 0.1, 0.15])
    assert r["count"] == 3
    assert r["mean"] == pytest.approx(0.1)
    assert r["win_rate"] == 1.0


def test_summarize_flat_mixed():
    r = _summarize_flat([-0.1, 0.05, 0.1, 0.2, -0.05])
    assert r["count"] == 5
    assert r["min"] == pytest.approx(-0.1)
    assert r["max"] == pytest.approx(0.2)
    assert r["win_rate"] == pytest.approx(3 / 5)
    assert r["median"] == pytest.approx(0.05)


def test_summarize_flat_single_element_positive():
    r = _summarize_flat([0.05])
    assert r["count"] == 1
    for k in ("mean", "min", "q25", "median", "q75", "max"):
        assert r[k] == pytest.approx(0.05), k
    assert r["win_rate"] == 1.0


def test_summarize_flat_single_element_zero():
    r = _summarize_flat([0.0])
    assert r["count"] == 1
    assert r["win_rate"] == 0.0  # v > 0 才算 win
```

- [ ] **Step 2: 跑测试验证失败**

Run: `uv run pytest tests/path2_web/test_eval_runner.py::test_summarize_flat_empty -v`

Expected: `ImportError` — `_summarize_flat` 尚未定义。

- [ ] **Step 3: 实现 `_summarize_flat` 并让 `_summarize` 内部改调**

编辑 `path2_web/eval_runner.py` line 103-115 附近。**当前** `_summarize` 是:

```python
def _summarize(rows: list, horizons: Sequence[int]) -> dict:
    """每 horizon 的 count/mean/min/q25/median/q75/max/win_rate(None 值剔除;空 → 各项 None)。"""
    per = {}
    for n in horizons:
        vals = [r["returns"][str(n)] for r in rows
                if r["returns"][str(n)] is not None]
        if vals:
            s = pd.Series(vals)
            q25, q75 = s.quantile([0.25, 0.75])
            per[str(n)] = {
                "count": len(vals),
                "mean": sum(vals) / len(vals),
                "min": float(s.min()),
                "q25": float(q25),
                "median": float(s.median()),
                "q75": float(q75),
                "max": float(s.max()),
                "win_rate": sum(v > 0 for v in vals) / len(vals),
            }
        else:
            per[str(n)] = {k: None for k in
                           ("count", "mean", "min", "q25", "median", "q75",
                            "max", "win_rate")}
            per[str(n)]["count"] = 0
    return per
```

**替换为**(先加 `_summarize_flat`,再让 `_summarize` 内部循环调它):

```python
def _summarize_flat(vals: list) -> dict:
    """给定一组 float, 返回 count/mean/min/q25/median/q75/max/win_rate。
    None 值调用者已过滤;空 vals -> count=0, 其余 None。"""
    if not vals:
        return {"count": 0, "mean": None, "min": None, "q25": None,
                "median": None, "q75": None, "max": None, "win_rate": None}
    s = pd.Series(vals)
    q25, q75 = s.quantile([0.25, 0.75])
    return {
        "count": len(vals),
        "mean": sum(vals) / len(vals),
        "min": float(s.min()),
        "q25": float(q25),
        "median": float(s.median()),
        "q75": float(q75),
        "max": float(s.max()),
        "win_rate": sum(v > 0 for v in vals) / len(vals),
    }


def _summarize(rows: list, horizons: Sequence[int]) -> dict:
    """每 horizon 的 count/mean/min/q25/median/q75/max/win_rate(None 值剔除;空 → 各项 None)。"""
    per = {}
    for n in horizons:
        vals = [r["returns"][str(n)] for r in rows
                if r["returns"][str(n)] is not None]
        per[str(n)] = _summarize_flat(vals)
    return per
```

- [ ] **Step 4: 跑测试验证全绿**

Run: `uv run pytest tests/path2_web/test_eval_runner.py -v`

Expected: 所有 test_summarize_flat_* 及现有 10 项测试全部 PASS(共 16+ 项)。

如现有 `_summarize` 测试(如 `test_eval_core_aggregates_and_summarizes`)因新 dict 结构失败 → 不动它;若失败请检查 `_summarize_flat` 实现与旧结构 key 顺序是否一致。

- [ ] **Step 5: Commit**

```bash
git add path2_web/eval_runner.py tests/path2_web/test_eval_runner.py
git commit -m "$(cat <<'EOF'
refactor(eval_runner): 抽 _summarize_flat · 供 scan.py 复用

- _summarize 内部循环改调 _summarize_flat,单一实现无漂移
- 覆盖空/全负/全正/混合/单元素/零元素 6 场景
- 后续 Task 2 的 scan.py stats 落盘将复用此签名

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — `run_scan_multi` 落盘时算 per-pattern stats

**Files:**
- Modify: `path2_web/scan.py:170-190`(`agg = _aggregate_multi(...)` 后、`write_result_file_flat(...)` 前)
- Modify: `tests/path2_web/test_scan_multi_pattern.py`(追加测试)

**Interfaces:**
- Consumes: Task 1 `_summarize_flat`
- Produces: `MultiScanResultFile.per_pattern[pid].stats: dict` 字段(§2.1 schema)

**Spec Ref:** §2.1 · §2.2.2

---

- [ ] **Step 1: 写失败测试**

打开 `tests/path2_web/test_scan_multi_pattern.py`。文件已 `import` 了 `run_scan_multi` 与 `tiny_pkls` fixture。追加以下三个测试到文件末尾:

```python
from path2_web.eval_runner import _summarize_flat


def test_multi_scan_per_pattern_has_stats(tmp_path, tiny_pkls):
    """扫描落盘产物 per_pattern[pid] 含 stats 字段,值 = _summarize_flat 手工聚合。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_breakout_burst"},
        pattern_ids=["bbb"],
        end_roles={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120000",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    assert "stats" in saved["per_pattern"]["bbb"], "per_pattern[pid].stats 缺失"
    vals = [
        m["forward_return"]
        for r in saved["results"]
        for m in r["per_pattern"].get("bbb", {}).get("analysis", {}).get("matches", [])
        if m.get("forward_return") is not None
    ]
    expected = _summarize_flat(vals)
    assert saved["per_pattern"]["bbb"]["stats"] == expected


def test_multi_scan_stats_survives_json_roundtrip(tmp_path, tiny_pkls):
    """stats 字段能通过 json.dumps/loads round-trip(所有值 JSON-safe)。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_breakout_burst"},
        pattern_ids=["bbb"],
        end_roles={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120100",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    out_file = Path(tmp_path / "out" / "scans" / "20260713T120100.json")
    reload = json.loads(out_file.read_text())
    assert reload["per_pattern"]["bbb"]["stats"] == saved["per_pattern"]["bbb"]["stats"]


def test_multi_scan_stats_all_pids_present(tmp_path, tiny_pkls):
    """多 pattern 扫描:每个 pid 各自都有 stats。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={
            "bbb": serialize_pattern(build_bbb(PBbb.default())),
            "bo": serialize_pattern(build_bo(PBo.default())),
        },
        module_paths={
            "bbb": "path2_apps.bottom_breakout_burst",
            "bo": "path2_apps.bo_only",
        },
        pattern_ids=["bbb", "bo"],
        end_roles={"bbb": "tb", "bo": "bo"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120200",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    for pid in ("bbb", "bo"):
        assert "stats" in saved["per_pattern"][pid], f"{pid} stats 缺失"
        assert "count" in saved["per_pattern"][pid]["stats"]
```

- [ ] **Step 2: 跑测试验证失败**

Run: `uv run pytest tests/path2_web/test_scan_multi_pattern.py::test_multi_scan_per_pattern_has_stats -v`

Expected: FAIL with `AssertionError: per_pattern[pid].stats 缺失`(因为 scan.py 未算)。

- [ ] **Step 3: 修改 `scan.py::run_scan_multi` 落盘前算 stats**

打开 `path2_web/scan.py`。文件顶部 imports 区域(line 20-30 附近)追加:

```python
from path2_web.eval_runner import _summarize_flat
```

然后在 `run_scan_multi` 函数内、`per_pattern_meta = {...}` 构造完之后(line 172-174 后)、`result = {...}` 构造之前(line 175 前)插入:

```python
    # 每 pattern 全宇宙聚合 stats(按 match 计,过滤 None forward_return)
    for pid in pattern_ids:
        vals = [
            m["forward_return"]
            for r in agg["results"]
            for m in r["per_pattern"].get(pid, {}).get("analysis", {}).get("matches", [])
            if m.get("forward_return") is not None
        ]
        per_pattern_meta[pid]["stats"] = _summarize_flat(vals)
```

- [ ] **Step 4: 跑测试验证全绿**

Run: `uv run pytest tests/path2_web/test_scan_multi_pattern.py -v`

Expected: 新增 3 项全 PASS + 原有测试全 PASS。

再跑一遍完整后端: `uv run pytest tests/path2_web/ -v` — 应无回归。

- [ ] **Step 5: Commit**

```bash
git add path2_web/scan.py tests/path2_web/test_scan_multi_pattern.py
git commit -m "$(cat <<'EOF'
feat(scan): run_scan_multi 落盘时算 per-pattern forward_return 分布 stats

- MultiScanResultFile.per_pattern[pid] 新增 stats 字段(可选)
- 按 match 计入 · 过滤 None forward_return · 复用 _summarize_flat
- partial 扫描仍算已聚部分
- 供前端 hover tooltip 展示分布(count/mean/min/q25/median/q75/max/win_rate)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — TS `PatternStats` interface

**Files:**
- Modify: `path2_web_ui/src/types.ts:50-53`(`PerPatternMeta` 加 `stats?`)

**Interfaces:**
- Consumes: 无
- Produces: 类型 `PatternStats` + `PerPatternMeta.stats?: PatternStats`

**Spec Ref:** §2.3.3

---

- [ ] **Step 1: 修改 types.ts**

打开 `path2_web_ui/src/types.ts`。**当前** line 50-53:

```typescript
export interface PerPatternMeta {
  pattern_spec: SerializedPattern
  end_role: string
}
```

**替换为**:

```typescript
export interface PatternStats {
  count: number
  mean: number | null
  min: number | null
  q25: number | null
  median: number | null
  q75: number | null
  max: number | null
  win_rate: number | null
}
export interface PerPatternMeta {
  pattern_spec: SerializedPattern
  end_role: string
  stats?: PatternStats
}
```

- [ ] **Step 2: 跑 vue-tsc 验证类型无错**

Run(在 `path2_web_ui/` 目录):

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 无 error 输出(可能 warning 忽略)。若出现引用 `PerPatternMeta` 的地方类型不兼容,直接放行(新增可选字段不破坏原有消费者)。

- [ ] **Step 3: Commit**

```bash
git add path2_web_ui/src/types.ts
git commit -m "$(cat <<'EOF'
types(webui): PerPatternMeta 加 stats?: PatternStats(可选)

- 后端 scan.py 落盘时会填,旧 JSON 无字段(可选故兼容)
- 供 SidebarResultList hover tooltip 消费

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `PatternStatsTooltip.vue` 组件 + vitest

**Files:**
- Create: `path2_web_ui/src/components/PatternStatsTooltip.vue`
- Create: `path2_web_ui/tests/components.pattern-stats-tooltip.spec.ts`

**Interfaces:**
- Consumes: Task 3 `PatternStats`
- Produces: 组件 `PatternStatsTooltip`,`defineProps<{ stats: PatternStats }>()`;渲染 8 行 CSS grid;数字复用现有 `SidebarResultList.vue::fmt` 风格(内联实现)。

**Spec Ref:** §2.3.1

---

- [ ] **Step 1: 写失败测试**

新建 `path2_web_ui/tests/components.pattern-stats-tooltip.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PatternStatsTooltip from '../src/components/PatternStatsTooltip.vue'

describe('PatternStatsTooltip', () => {
  it('renders 8 rows with correct formatted values', () => {
    const stats = {
      count: 203,
      mean: 0.032,
      min: -0.081,
      q25: 0.008,
      median: 0.025,
      q75: 0.057,
      max: 0.184,
      win_rate: 0.68,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    const rows = w.findAll('.row')
    expect(rows).toHaveLength(8)
    const txt = w.text()
    expect(txt).toContain('203')
    expect(txt).toContain('+3.2%')
    expect(txt).toContain('-8.1%')
    expect(txt).toContain('+0.8%')
    expect(txt).toContain('+2.5%')
    expect(txt).toContain('+5.7%')
    expect(txt).toContain('+18.4%')
    expect(txt).toContain('68%')
  })

  it('falls back to em-dash for null fields (empty samples)', () => {
    const stats = {
      count: 0,
      mean: null, min: null, q25: null, median: null,
      q75: null, max: null, win_rate: null,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    const txt = w.text()
    expect(txt).toContain('0')
    const dashes = w.findAll('.val').filter(v => v.text() === '—')
    expect(dashes.length).toBe(7)
  })

  it('formats win_rate as integer percent', () => {
    const stats = {
      count: 100, mean: 0.01, min: 0.01, q25: 0.01,
      median: 0.01, q75: 0.01, max: 0.01, win_rate: 0.755,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    expect(w.text()).toContain('76%')
  })

  it('handles zero-mean as +0.0%', () => {
    const stats = {
      count: 1, mean: 0, min: 0, q25: 0, median: 0,
      q75: 0, max: 0, win_rate: 0,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    expect(w.text()).toContain('+0.0%')
    expect(w.text()).toContain('0%')
  })
})
```

- [ ] **Step 2: 跑测试验证失败**

Run(在 `path2_web_ui/`):

```bash
cd path2_web_ui && npx vitest run tests/components.pattern-stats-tooltip.spec.ts
```

Expected: FAIL — 组件文件不存在。

- [ ] **Step 3: 实现组件**

新建 `path2_web_ui/src/components/PatternStatsTooltip.vue`:

```vue
<template>
  <div class="pattern-stats-tooltip">
    <div class="row"><span class="label">count</span><span class="val">{{ stats.count }}</span></div>
    <div class="row"><span class="label">mean</span><span class="val">{{ fmtVal(stats.mean) }}</span></div>
    <div class="row"><span class="label">min</span><span class="val">{{ fmtVal(stats.min) }}</span></div>
    <div class="row"><span class="label">q25</span><span class="val">{{ fmtVal(stats.q25) }}</span></div>
    <div class="row"><span class="label">median</span><span class="val">{{ fmtVal(stats.median) }}</span></div>
    <div class="row"><span class="label">q75</span><span class="val">{{ fmtVal(stats.q75) }}</span></div>
    <div class="row"><span class="label">max</span><span class="val">{{ fmtVal(stats.max) }}</span></div>
    <div class="row"><span class="label">win_rate</span><span class="val">{{ fmtWinRate(stats.win_rate) }}</span></div>
  </div>
</template>

<script setup lang="ts">
import type { PatternStats } from '../types'

defineProps<{ stats: PatternStats }>()

function fmtVal(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}

function fmtWinRate(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
}
</script>

<style scoped>
.pattern-stats-tooltip {
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 12px;
  padding: 8px 10px;
  background: #1e293b;
  color: #f1f5f9;
  border-radius: 4px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  min-width: 140px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
}
.row { display: contents; }
.label { text-align: left; opacity: 0.75; }
.val { text-align: right; font-weight: 600; }
</style>
```

- [ ] **Step 4: 跑测试验证全绿**

Run:

```bash
cd path2_web_ui && npx vitest run tests/components.pattern-stats-tooltip.spec.ts
```

Expected: 4 tests PASS。

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/PatternStatsTooltip.vue path2_web_ui/tests/components.pattern-stats-tooltip.spec.ts
git commit -m "$(cat <<'EOF'
feat(webui): PatternStatsTooltip 组件 · 8 行 CSS grid 右对齐

- 展示 count/mean/min/q25/median/q75/max/win_rate
- 收益 +3.2% / -8.1% 百分比 1 位小数带符号
- win_rate 整数百分比 · null 值回退 —
- 空样本时 count=0 其余 —

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — `SidebarResultList.vue` hover 挂载 + vitest

**Files:**
- Modify: `path2_web_ui/src/components/SidebarResultList.vue`
- Create: `path2_web_ui/tests/components.sidebar-result-list.spec.ts`

**Interfaces:**
- Consumes: Task 3 `PatternStats`,Task 4 `PatternStatsTooltip`
- Produces: `SidebarResultList` hdr-pattern th 支持 hover · tooltip 单实例定位相对 `.list` 根节点

**Spec Ref:** §2.3.2

---

- [ ] **Step 1: 写失败测试**

新建 `path2_web_ui/tests/components.sidebar-result-list.spec.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SidebarResultList from '../src/components/SidebarResultList.vue'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, PatternStats } from '../src/types'

const SAMPLE_STATS: PatternStats = {
  count: 10, mean: 0.05, min: -0.02, q25: 0.01,
  median: 0.05, q75: 0.08, max: 0.15, win_rate: 0.7,
}

function makeScanFile(pids: string[], withStats: boolean): MultiScanResultFile {
  const per_pattern: Record<string, any> = {}
  for (const pid of pids) {
    per_pattern[pid] = {
      pattern_spec: { pattern_id: pid, roles: [], edges: [], event_styles: {} } as any,
      end_role: 'tb',
      ...(withStats ? { stats: SAMPLE_STATS } : {}),
    }
  }
  return {
    pattern_ids: pids,
    per_pattern,
    scan: {
      scan_ts: '20260713T120000',
      start_date: '2025-01-01', end_date: '2026-12-31', workers: 2,
      scanned: 0, hits: 0, errors: 0, dataset_dir: '', params: 'default',
      win_start: '2025-01-01', win_end: '2026-12-31', label_horizon: 5,
    },
    results: [],
  }
}

describe('SidebarResultList · hover tooltip', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('shows PatternStatsTooltip on hdr-pattern hover when stats present', async () => {
    const view = useViewStore()
    ;(view as any).scanFile = makeScanFile(['bo_only'], true)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    expect(th.exists()).toBe(true)
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    w.unmount()
  })

  it('does not mount tooltip when stats absent (old JSON)', async () => {
    const view = useViewStore()
    ;(view as any).scanFile = makeScanFile(['bo_only'], false)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(false)
    w.unmount()
  })

  it('hides tooltip on mouseleave', async () => {
    const view = useViewStore()
    ;(view as any).scanFile = makeScanFile(['bo_only'], true)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    await th.trigger('mouseleave')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(false)
    w.unmount()
  })

  it('multi-pattern hovers show tooltip for each pid independently', async () => {
    const view = useViewStore()
    ;(view as any).scanFile = makeScanFile(['bo_only', 'bottom_burst'], true)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th1 = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    const th2 = w.find('.col-pattern[data-pattern-pid="bottom_burst"]')
    expect(th1.exists() && th2.exists()).toBe(true)

    await th1.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    await th1.trigger('mouseleave')

    await th2.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    w.unmount()
  })
})
```

**注**: 若 `useViewStore` 的 `scanFile` 是 `shallowRef` 且外部无 setter,测试内 `(view as any).scanFile = ...` 直接改 store 内部的 ref 是否生效需现场核查——如果测试 mount 后组件读不到,改用 `view.$patch({ scanFile: ... })` 或调 store 现有的 `loadScanFile / open` 方法(先读 `path2_web_ui/src/stores/view.ts` 找现有 setter)。核心断言不变。

- [ ] **Step 2: 跑测试验证失败**

Run:

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts
```

Expected: FAIL — 组件未加 hover 逻辑,tooltip 从不 mount。

- [ ] **Step 3: 修改 `SidebarResultList.vue` 加 hover 挂载**

打开 `path2_web_ui/src/components/SidebarResultList.vue`。

**改动 A** — template 里 hdr-pattern th(当前 line 32-39):

**当前**:
```vue
<template v-for="pid in visiblePatterns" :key="pid">
  <th v-if="fieldCountFor(pid) > 0"
      class="col-pattern"
      :colspan="fieldCountFor(pid)"
      :data-pattern-pid="pid">
    {{ pid }}
  </th>
</template>
```

**替换为**:
```vue
<template v-for="pid in visiblePatterns" :key="pid">
  <th v-if="fieldCountFor(pid) > 0"
      class="col-pattern"
      :colspan="fieldCountFor(pid)"
      :data-pattern-pid="pid"
      @mouseenter="onPatternHover(pid, $event)"
      @mouseleave="onPatternLeave">
    {{ pid }}
  </th>
</template>
```

**改动 B** — template 根 `<div class="list">` 内 · 靠近末尾追加 tooltip 节点(在 `.field-menu` 之后、`</div>` 之前):

```vue
<PatternStatsTooltip v-if="hoveredStats"
                     :stats="hoveredStats"
                     class="hover-tooltip"
                     :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }" />
```

**改动 C** — `<script setup>` imports 追加(在现有 `import { useViewStore, ... }` 附近):

```typescript
import PatternStatsTooltip from './PatternStatsTooltip.vue'
```

**改动 D** — `<script setup>` 里加 hover state 与 handler(建议放 `openFieldsMenu` 之前):

```typescript
const hoveredPid = ref<string | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

const hoveredStats = computed(() => {
  if (!hoveredPid.value || !scanFile.value) return null
  return scanFile.value.per_pattern[hoveredPid.value]?.stats ?? null
})

function onPatternHover(pid: string, evt: MouseEvent) {
  const th = evt.currentTarget as HTMLElement | null
  const listEl = th?.closest('.list') as HTMLElement | null
  if (!th || !listEl) return
  if (!scanFile.value?.per_pattern[pid]?.stats) return  // 无 stats 不挂
  const thRect = th.getBoundingClientRect()
  const listRect = listEl.getBoundingClientRect()
  tooltipX.value = thRect.left - listRect.left
  tooltipY.value = thRect.bottom - listRect.top + 2
  hoveredPid.value = pid
}

function onPatternLeave() {
  hoveredPid.value = null
}
```

**改动 E** — `<style scoped>` 里追加(现有 style 块末尾):

```css
.list { position: relative; }
.hover-tooltip {
  position: absolute;
  z-index: 100;
  pointer-events: none;
}
```

**注**: `.list` 若已在现有 style 中定义则合并 `position: relative` 到原有规则,不要重复声明。

- [ ] **Step 4: 跑前端测试验证全绿**

Run:

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts tests/components.pattern-stats-tooltip.spec.ts
```

Expected: 两个测试文件全 PASS。

再跑一次前端全套: `cd path2_web_ui && npx vitest run` — 应无回归。若因为 `scanFile` 测试注入方式(见 Step 1 注)失败 → 改用 `path2_web_ui/src/stores/view.ts` 中现有的 setter 方法(如 `open` / `loadScanFile` 之类)。

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/SidebarResultList.vue path2_web_ui/tests/components.sidebar-result-list.spec.ts
git commit -m "$(cat <<'EOF'
feat(webui): SidebarResultList hdr-pattern hover 显示 stats tooltip

- 挂 PatternStatsTooltip 单实例、absolute 定位相对 .list 根节点
- 旧 JSON 无 stats 字段 → 不挂 hover(pattern 名照常展示)
- 多 pattern 各自独立触发

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — 四 gate 全跑 + Playwright e2e 视觉验证

**Files:**
- 无代码改动;仅验证。若 e2e 发现回归 → 回到对应 task 修复。

**Interfaces:**
- Consumes: Task 1-5 全部
- Produces: 手动/自动化 sign-off

**Spec Ref:** §3

---

- [ ] **Step 1: 四 gate 全跑**

在仓库根跑:

```bash
# 后端
uv run pytest tests/path2_web/ -v
# 前端
cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build && cd ..
```

Expected: 全部 PASS / 0 error / build 成功。

- [ ] **Step 2: 起后端 · 起前端 · 用 playwright 拉起 UI**

**后端**(后台跑):

```bash
uv run python scripts/run_path2_web.py
```

**前端 dev server**(后台跑):

```bash
cd path2_web_ui && npm run dev
```

若 `package.json` 无 `dev` script,改用 `npx vite`。

**Playwright MCP 打开**(通过 `mcp__plugin_playwright_playwright__browser_navigate`):`http://localhost:5173`(或前端 dev server 端口)。

- [ ] **Step 3: 手动扫描 + hover 验证**

在 UI 里点「扫描」按钮打开 ScanConfigDialog → 选择 `bottom_breakout_burst` pattern → 窗口设一个已知有命中的年份(如 2024-01-01 ~ 2025-01-01)→ 提交扫描。

等扫描完成(SidebarScanPanel 出现「完成: 命中 N / 错误 M」)→ 命中股列表 SidebarResultList 出现。

**Playwright 操作**:
1. `browser_resize(2560, 1440)`
2. Hover `.col-pattern[data-pattern-pid="bottom_breakout_burst"]`(用 `browser_hover` + selector)
3. `browser_take_screenshot(fullPage=false, target='.list', scale='device')` — 拍元素级截图确认 tooltip 显示 · 数字对齐 · 8 行

**视觉断言**:
- Tooltip 在 pattern 名下方弹出
- 8 行显示 count / mean / min / q25 / median / q75 / max / win_rate
- 右对齐 · 数字带百分号 · win_rate 显示整数百分比
- 深色背景 · 白色文字 · 圆角

- [ ] **Step 4: 多 pattern hover 验证(若可扫多 pattern)**

若扫描配置支持多 pattern,再扫一次带 2 个 pattern(如 `bo_only + bottom_breakout_burst`)→ 分别 hover 两个 pattern 名 → 确认 tooltip 独立触发 · 数字不同。

Playwright 截图对照两个 pattern 各自的 tooltip 内容。

- [ ] **Step 5: 旧 JSON fallback 验证**

打开一个 **旧**扫描历史(通过 SidebarScanPanel「打开历史」按钮 → 选一个 Task 1-5 前的 scan_ts)→ hover pattern 名 → 确认**无** tooltip 弹出(pattern 名照常展示、无警告)。

- [ ] **Step 6: Playwright 目录清理**

若本 task 用了 playwright MCP:

```bash
rm -rf .playwright-mcp/*
```

(CLAUDE.md「Playwright 卫生」)

- [ ] **Step 7: 无代码改动 → 无需 commit(若前面 5 个 task 已 commit 干净)**

若 Step 3-5 发现问题 → 回到对应 Task 修 + commit;修完再跑 Step 1 四 gate。

---

## 完成判据

- [ ] Task 1-5 各 commit 独立干净
- [ ] `uv run pytest tests/path2_web/` 全绿
- [ ] `cd path2_web_ui && npx vitest run` 全绿
- [ ] `cd path2_web_ui && npx vue-tsc --noEmit` 无 error
- [ ] `cd path2_web_ui && npx vite build` 成功
- [ ] Playwright e2e 截图证实 tooltip 视觉 OK · 多 pattern 独立 · 旧 JSON fallback OK
- [ ] `.playwright-mcp/` 清空

## 排除方案(Plan 不做)

见 spec §2.7:
- 前端 fallback 现算(旧 JSON 兼容)—— 用户选定「只后端算 · 旧 JSON 不显示 tooltip」
- 后端 `/stats/<pid>` API endpoint
- tooltip 用原生 `title=""` (无法右对齐 8 行)
- stats 按买点去重
- stats 放在 `results[i].per_pattern[pid].stats`(per-symbol)
- 独立浮出 stats 侧栏
- stats 多 horizon
- stats 在 `scan.stats` 顶层聚合
