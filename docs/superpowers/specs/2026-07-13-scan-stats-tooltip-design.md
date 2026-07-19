# 扫描 stats · Pattern 名 hover tooltip 设计

**日期**: 2026-07-13
**范围**: `path2_web` 扫描落盘 + `path2_web_ui` 命中股列表面板

## 1. 背景与目标

### 1.1 现状

`path2_web/scan.py::run_scan_multi` 是 web UI 「扫描」按钮触发的多股 · 多 pattern 并发扫描,产物落盘到 `outputs/path2_web/scans/<scan_ts>.json`。当前 schema (`MultiScanResultFile`):

```json
{
  "pattern_ids": [...],
  "per_pattern": {"<pid>": {"pattern_spec": ..., "end_role": ...}},
  "scan": {"scanned": ..., "hits": ..., "label_horizon": ..., ...},
  "results": [
    {"symbol": ..., "per_pattern": {"<pid>": {"summary", "analysis", "max_forward_return"}}}
  ]
}
```

其中每 match 都注入了 `forward_return`(见 `path2_web/serialize.py::serialize_per_pattern_result`),但**全宇宙聚合分布**从未算过。UI 现有面板 (`path2_web_ui/src/components/SidebarResultList.vue`):
- 表头两级: hdr-pattern (per-pattern 名字跨列头) → hdr-field (per-pattern 内 num/fr 两列)
- 每股 · 每 pattern 展示 num (match 数) + fr (per-symbol max_forward_return)

用户扫描完想看「这批股 · 这个 pattern 命中的收益分布」(count / mean / min / q25 / median / q75 / max / win_rate)时缺入口——只能手跑 `scripts/path2_eval_scan.py` 重扫(口径与 UI 不同:多 horizon · 按买点去重)。

### 1.2 目标

- **后端**: `run_scan_multi` 落盘时自动算每 pattern 的全宇宙 `forward_return` 分布 stats,塞进 `MultiScanResultFile`
- **前端**: 用户 hover `SidebarResultList` hdr-pattern 那一行的 pattern 名 `<th>` 时,自制 tooltip 显示 8 字段分布(表格式 8 行右对齐)

### 1.3 排除方案(不做)

- **不做前端现算 fallback**——后端单一数据源避免前后端 stats 逻辑漂移
- **不加 API endpoint**——JSON 自带随扫描历史落盘持久化,无需运行时算
- **不做 boxplot 图 / 多行分组 tooltip**——已选定表格式 8 行
- **不做 active pattern 联动**——每个 pattern 名字上 hover 天然对应,无需 UI 状态耦合
- **不做多 horizon**——UI 扫描本就单 `label_horizon`;多 horizon 归 `scripts/path2_eval_scan.py`

## 2. 设计

### 2.1 数据契约

**Schema 新增字段**(`MultiScanResultFile.per_pattern[pid]`,可选、旧 JSON 无此字段):

```json
"stats": {
  "count": 203,
  "mean": 0.032,
  "min": -0.081,
  "q25": 0.008,
  "median": 0.025,
  "q75": 0.057,
  "max": 0.184,
  "win_rate": 0.68
}
```

- 数值为**原始 float**(未乘 100)——前端复用 `SidebarResultList.vue::fmt(v)` 展示时再乘
- 全空样本(0 matches): `count=0`,其余字段 `null`
- horizon 沿用 `scan.label_horizon`(扫描全局单值,stats 无需自带 horizon)

**口径(关键决策)**: **按 match 计入**——同一 tb 买点被多条组合路径命中会重复计入,与 UI `SidebarResultList` cell 展示的 `num`(match 数)一致。**不做按买点去重**(去重口径属 eval_runner 那条路,与 UI 面板 count 语义分离)。

### 2.2 后端

#### 2.2.1 共享统计函数

`path2_web/eval_runner.py` 新增:

```python
def _summarize_flat(vals: list) -> dict:
    """给定一组 float, 返回 count/mean/min/q25/median/q75/max/win_rate。
    None 值调用者已过滤;空 vals -> count=0, 其余 None。"""
    if not vals:
        return {"count": 0, **{k: None for k in
            ("mean", "min", "q25", "median", "q75", "max", "win_rate")}}
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
```

现有 `_summarize(rows, horizons)`(同文件 line 103)内部循环改成调 `_summarize_flat`——两处保持单一实现,无漂移。

#### 2.2.2 扫描落盘时算

`path2_web/scan.py::run_scan_multi` 在 `write_result_file_flat` 之前(即 `result = {...}` 构造后、`write_result_file_flat(result, ...)` 之前),对每 pid 遍历所有 result matches 抽 `forward_return`:

```python
from path2_web.eval_runner import _summarize_flat

for pid in pattern_ids:
    vals = [
        m["forward_return"]
        for r in agg["results"]
        for m in r["per_pattern"].get(pid, {}).get("analysis", {}).get("matches", [])
        if m.get("forward_return") is not None
    ]
    per_pattern_meta[pid]["stats"] = _summarize_flat(vals)
```

`partial=True`(用户按停止保存)扫描仍照算——已聚部分有语义。

### 2.3 前端

#### 2.3.1 新组件 `PatternStatsTooltip.vue`

Props: `stats: PatternStats`(对应 §2.1 schema 类型)。

布局: CSS grid 2 列(label 左对齐、数字右对齐)· 8 行。字段展示顺序与 §2.1 schema 一致: `count / mean / min / q25 / median / q75 / max / win_rate`。

数字格式:
- `count`: 整数原样
- `mean/min/q25/median/q75/max`: 复用 `SidebarResultList.vue::fmt(v)` → `+3.2%` / `-8.1%`
- `win_rate`: `(v * 100).toFixed(0) + '%'` → `68%`
- 空样本时 `count: 0`,其余显示 `—`

#### 2.3.2 `SidebarResultList.vue` 挂载

hdr-pattern `<th>` 加 `@mouseenter="showTooltip(pid, $event)"` / `@mouseleave="hideTooltip()"`。Tooltip 挂在 `SidebarResultList` 根 `<div class="list">` 内、`position: absolute`、`z-index` 高于表头 sticky;定位用 `th.getBoundingClientRect()` 算 th 下沿(相对根节点偏移)。

**Fallback 判定**: `v-if="perPatternMeta[pid]?.stats"` — 旧 JSON 无字段 → 不挂 hover,pattern 名照常展示(无警告)。

Tooltip 全局单实例(同一时刻只 hover 一个 pattern)。

#### 2.3.3 类型

`path2_web_ui/src/types.ts`(或对应 store types 文件)加:

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
```

挂到 `MultiScanResultFile.per_pattern[pid].stats?: PatternStats`(可选字段)。

### 2.4 Fallback / 边界

| 场景 | 行为 |
|---|---|
| 旧 JSON 无 `stats` 字段 | 前端不挂 tooltip,pattern 名照常展示,无警告 |
| `partial=True` 扫描 | 后端算已聚部分 stats,正常落盘,无特殊标记 |
| 某 match `forward_return=None`(超窗) | 后端过滤后再算,与 `_summarize` 现有行为一致 |
| 全空样本(0 matches) | `count=0`,其余 `null`;tooltip 显示 `count: 0` + 其余 `—` |
| 单元素样本(count=1) | `min==q25==median==q75==max==mean=vals[0]`,`win_rate ∈ {0, 1}`;`pd.quantile` 直算无需特判 |

### 2.5 测试

**后端** — `tests/path2_web/test_eval_runner.py`:
- `_summarize_flat` 单测:
  - 空 vals → `{count=0, 其余 None}`
  - 全负 → `win_rate=0`, `mean<0`
  - 全正 → `win_rate=1`, `mean>0`
  - 混合 → 分位数按 `pd.quantile` 语义
  - 单元素 → `min==max==mean`, `win_rate ∈ {0,1}`
- 现有 `_summarize` 测试保持通过(内部已改调 `_summarize_flat`)

**后端** — `tests/path2_web/test_scan.py`:
- `run_scan_multi` 落盘 JSON `per_pattern[pid].stats` 字段存在
- stats 值 == 手工按 match 聚 `forward_return` 后 `_summarize_flat` 结果
- partial 场景 `per_pattern[pid].stats` 仍存在

**前端** — `path2_web_ui/tests/components.pattern-stats-tooltip.spec.ts`(新;命名遵循现有 `components.<kebab-name>.spec.ts` 约定):
- 8 行渲染 · 格式与 `fmt` 一致
- 空样本 fallback `—`

**前端** — `path2_web_ui/tests/components.sidebar-result-list.spec.ts`(新;`SidebarResultList` 当前无测试文件):
- 有 stats 时 hover 弹出 tooltip
- 无 stats 时 hdr-pattern th 无 hover 挂载
- 多 pattern 时每个 pattern 各自触发独立 tooltip

### 2.6 涉及文件

**新建**:
- `path2_web_ui/src/components/PatternStatsTooltip.vue`
- `path2_web_ui/tests/components.pattern-stats-tooltip.spec.ts`
- `path2_web_ui/tests/components.sidebar-result-list.spec.ts`

**修改**:
- `path2_web/eval_runner.py` — 抽 `_summarize_flat`,`_summarize` 改调
- `path2_web/scan.py` — `run_scan_multi` 落盘前算 per-pattern stats
- `path2_web_ui/src/components/SidebarResultList.vue` — hdr-pattern th 加 hover 挂载
- `path2_web_ui/src/types.ts` — `PatternStats` interface + `MultiScanResultFile.per_pattern[pid].stats?`
- `tests/path2_web/test_eval_runner.py` — `_summarize_flat` 单测
- `tests/path2_web/test_scan.py` — stats 字段验证

### 2.7 已排除方案与理由

| 方案 | 排除理由 |
|---|---|
| 前端现算 fallback | 前后端两套 stats 逻辑易漂移 |
| 后端 `/stats/<pid>` API | JSON 自带 + 随扫描历史落盘持久化,无需运行时算 |
| tooltip 用原生 `title=""` | 无法做右对齐 8 行表格式(浏览器默认样式) |
| stats 按买点去重(`event_id`) | 与 UI 面板 `num` 计数口径不一致 |
| stats 放 `results[i].per_pattern[pid].stats`(per-symbol) | 需求是全宇宙聚合,per-symbol 无意义 |
| 独立浮出 stats 侧栏 / SidebarScanPanel 完成提示卡片 / ChartArea inline tag | 与 UI 表格 pattern 分列语义脱耦或冲突;hdr-pattern hover tooltip 奥卡姆最优 |
| stats 多 horizon | UI 扫描单 `label_horizon`,多 horizon 归 `scripts/path2_eval_scan.py` |
| stats 在 `scan.stats` 顶层聚合 | 各 pattern 分布不同 · 全局聚合无意义 |

## 3. 实施 checklist

按 authoring 顺序(每步可独立测通):

1. `path2_web/eval_runner.py`: 抽 `_summarize_flat`,`_summarize` 改调;补 `_summarize_flat` 单测
2. `path2_web/scan.py::run_scan_multi`: 落盘前算 stats、塞 `per_pattern[pid]`;补 `test_scan.py` 验证
3. `path2_web_ui/src/types.ts`: 加 `PatternStats` interface
4. `path2_web_ui/src/components/PatternStatsTooltip.vue`: 新建组件 + 单测(8 行渲染 + 空样本 + 格式)
5. `path2_web_ui/src/components/SidebarResultList.vue`: hdr-pattern th 加 hover 挂载 + tooltip 单实例定位;测试覆盖 hover / 无 stats 分支
6. e2e: 手扫一批股 → 打开 UI → hover pattern 名 → 确认 tooltip 显示 · 数字对 · 多 pattern 各自触发

各步四 gate 全绿: `pytest tests/path2_web/`、`vitest`、`vue-tsc`、`vite build`。
