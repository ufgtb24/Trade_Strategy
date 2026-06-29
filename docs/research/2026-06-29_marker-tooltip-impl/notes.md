# Marker Tooltip 整治 — 端到端实证记录

**日期**: 2026-06-29  
**Task**: Task 2（真实数据端到端实证 + 视觉回归）  
**Task 1 commit**: e2645b2（marker tooltip 三段重排已落地）  
**Spec**: docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md

---

## 测试环境

- Dev server: backend http://localhost:8001, frontend http://localhost:5171
- 数据集: /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls（约 6048 pkl）
- Scan 文件: outputs/path2_web/scans/20260629T160222.json（1667/2101 hits, 8.4 MB）

---

## 测试股票 / 事件

### 主测（burst event 三段结构）
- **股票**: ALTO
- **Pattern**: bottom_burst
- **Event**: `burst_284_288`（burst 事件，bars 284-288，2025-11-06 → 2025-11-12）
- **Match**: `bottom_burst@284-289`（ret_20: +28.9%）
- 截图: screenshot-burst-tooltip.png

### 辅测（失败 clause 加粗）
- **Stock**: ALTO
- **Pattern**: bottom_burst（Detected 视角）
- **Event**: `burst_196_200`（burst 事件，bars 196-200，2025-07-03 → 2025-07-10）
- **特点**: 所有 3 个 clause 均失败（detected tier）
- 截图: screenshot-failing-clauses.png

### 辅测（match 端点 marker）
- **Stock**: ALTO
- **Match bracket**: `brackets` series，`match_id: "bottom_burst@284-289"`
- 截图: screenshot-match-endpoint-tooltip.png

### K-bar tooltip 对照
- **Stock**: A（bo_only）
- **Marker tooltip** 未触发时的 K-bar tooltip 展示
- 截图: screenshot-hover1.png, screenshot-hover2.png

---

## spec §7 验收结果（逐项）

### §7-1: 截图 7 行 → 整治后变为 9 行（身份 3 + 诊断 3 + 属性 2，含 2 段头）

**结果: PASS**

`burst_284_288` 的 marker tooltip（screenshot-burst-tooltip.png）实际 HTML：

```
Identity                       ← 段头 1（粗体）
role: burst
time: 2025-11-06 → 2025-11-12
id: burst_284_288
[hr 分隔线]
Clauses                        ← 段头 2（粗体）
first_drought: 35 >= 20 ✓
distinct_pk: 5 >= 4 ✓
vol_spike: 58.3193 >= 8 ✓
[hr 分隔线]
Attributes                     ← 段头 3（粗体）
count: 2
max_bar_vol_ratio: 58.3193
```

3 段结构正确（Identity / Clauses / Attributes），段头加粗，段间 `<hr/>` 分隔。
注：此例为 3+3+2=8 行内容 + 3 段头，取决于事件具体 clause 和 attribute 数量。

### §7-2: 失败 clause 加粗显示

**结果: PASS**

`burst_196_200` DOM 中实际 HTML（通过 JS 读取验证）：
```html
<b>first_drought: 16 >= 20 ✗</b>
<b>distinct_pk: 1 >= 4 ✗</b>
<b>vol_spike: 0.7724 >= 8 ✗</b>
```

失败 clause 确实在 `<b>` 标签内（加粗）。通过 clause.satisfied 排序后，全部失败的在 Clauses 段最前面（本例全失败）。

截图: screenshot-failing-clauses.png — 可见三行 ✗ 标记在粗体 "Clauses" 段头下。

### §7-3: 数字截到 4 位小数

**结果: PASS**

实测数值：
- `vol_spike: 58.3193` — 4 位小数 ✓
- `vol_spike: 0.7724` — 4 位小数 ✓
- `max_bar_vol_ratio: 58.3193` — 4 位小数 ✓
- `first_drought: 35`, `distinct_pk: 5`, `count: 2` — 整数原样显示 ✓

`fmtNum()` 函数（chart.ts:834-837）实测正确：
`if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(4)`

### §7-4: hover match 端点 marker → 既看到 match 标签又看到 event 三段

**结果: FAIL（数据层缺 event_id）**

**现象**: 悬停 `brackets` series（match bracket marker）只显示：
```
Match: ret_20: +28.9%
```
没有 Identity/Clauses/Attributes 三段。

**根因分析**:

`buildMarkerTooltipFormatter`（Task 1 已改为非互斥）对 params.data 同时检查 `match_id` 和 `event_id`：
- 有 `match_id` → 渲染 Match 顶行
- 有 `event_id` → 渲染三段

但当前 `bracketData` 构造（chart.ts:172-173）：
```typescript
const bracketData = brackets.map((m) => ({
  value: [m.start_idx, m.end_idx, m.lane, m.ordinal],
  match_id: m.event_id,
  // ← 缺少 event_id！
}))
```

`brackets` 数据项只有 `match_id`，没有 `event_id`。反之，`points`/`intervals` 只有 `event_id` 没有 `match_id`。
两类均无法同时显示 match 顶行 + event 三段。

**格式器逻辑**（Task 1 已正确实现非互斥）:
```typescript
// 顶行：match 归属
if (matchId && matchLabel) { ... }
// event 三段
if (eventId && tooltipResolver) { ... }
// 两个 if 不互斥 ✓
```

**修复建议**: 需在 chart.ts 中给 `bracketData` 加上对应事件的 `event_id`，
或给 `pointData`/`intervalData` 加上所属 match 的 `match_id`。
（后者需要在 chart 数据准备阶段建立 event_id → match_id 映射）

### §7-5: K bar tooltip 完全不变

**结果: PASS**

K-bar tooltip（screenshot-hover1.png, screenshot-hover2.png）展示标准格式：
```
Date: 2025-03-24
Open: 120.63
High: 123.18
Low: 119.64
Close: 120.72
Chg: +1.02%
Volume: 1,557,342
RV: 0.86
```
未受任何改动影响。

---

## 汇总

| # | 标准 | 结果 |
|---|------|------|
| 1 | 三段结构（Identity/Clauses/Attributes + 段头） | PASS |
| 2 | 失败 clause 加粗（`<b>` + ✗ 置顶） | PASS |
| 3 | 数字 4 位小数（fmtNum） | PASS |
| 4 | match 端点 hover 显示 match 标签 + event 三段 | **FAIL** |
| 5 | K-bar tooltip 不变 | PASS |

**总体**: 4/5 PASS，1/5 FAIL  
**核心 FAIL**: bracketData 缺 event_id，导致 brackets marker hover 无法同时展示 match label + event 三段  
**格式器逻辑（非互斥）已正确，数据层补丁待 Task 1 fix**

---

## 复现路径

```
1. 启动: uv run python scripts/run_path2_web.py
2. 打开 http://localhost:5171
3. 选 bo_only + bottom_burst checkbox
4. 打开历史 → 选 20260629T160222.json → Open
5. 切 bottom_burst 下拉，点 ALTO 行
6. 切 Matched 视角: hover 下方 grid1 的蓝色方块（burst_284_288 interval marker）
   → 看到完整三段 tooltip（§7-1/2/3 验证）
7. 切 Detected 视角: hover 下方 grid1 的蓝色方块（burst_196_200 interval marker）
   → 看到全失败 clause 加粗（§7-2 验证）
8. 切 Matched: hover chart 上方的蓝色 bracket 横条
   → 只看到 "Match: ret_20: +28.9%"（§7-4 FAIL）
```

---

## 补充：§7-4 再验证（Task 1.5 后）

**验证时间**: 2026-06-29  
**基准 commits**: Task 1 e2645b2（formatter 三段重排） + Task 1.5 433680d（bracketData 注入 event_id）

### 验证过程

- Dev server: frontend http://localhost:5171, backend http://localhost:8001
- 股票: ALTO，Pattern: bottom_burst，match: `bottom_burst@284-289`
- Bracket marker: `brackets` series，dataIndex=0，`match_id: "bottom_burst@284-289"`，`event_id: "tb_289"`
- ECharts `dispatchAction({ type: 'showTip', seriesIndex: 4, dataIndex: 0 })` 触发 tooltip

### Tooltip DOM HTML（实测）

```html
Match: ret_20: +28.9%<br><hr><br>
<b>Identity</b><br>
role: tb<br>
time: 2025-11-13<br>
id:   tb_289<br>
<hr><br>
<b>Attributes</b><br>
anchor_bo_id: bo_288
```

### 验收逐项

| 要素 | 预期 | 实测 | 结果 |
|------|------|------|------|
| 顶行 Match 标签 | `Match: ret_N: +x.x%` | `Match: ret_20: +28.9%` | ✓ |
| `<hr>` 分隔线 | 有 | 有（顶行后、Identity 后各一条） | ✓ |
| Identity 段头 | `Identity`（加粗） | `<b>Identity</b>` | ✓ |
| Identity role | `role: tb` | `role: tb` | ✓ |
| Identity time | 日期 | `time: 2025-11-13` | ✓ |
| Identity id | `id: tb_289` | `id:   tb_289` | ✓ |
| Clauses 段 | 如有（tb 无 where_rules，故无此段） | 无（正确省略） | ✓ |
| Attributes 段头 | `Attributes`（加粗） | `<b>Attributes</b>` | ✓ |
| Attributes 字段 | raw 字段 | `anchor_bo_id: bo_288` | ✓ |

### 结果: **PASS**

Task 1（formatter 三段重排）+ Task 1.5（bracketData 注入 event_id `tb_289`）联合修复了 §7-4。

Bracket marker hover 现在同时显示：
- Match 顶行（`Match: ret_20: +28.9%`）
- Identity 三行（role / time / id）
- Attributes 字段（anchor_bo_id）

截图: `.playwright-mcp/alto-bracket-tooltip-74.png`

### 更新汇总

| # | 标准 | 最终结果 |
|---|------|----------|
| 1 | 三段结构（Identity/Clauses/Attributes + 段头） | PASS |
| 2 | 失败 clause 加粗（`<b>` + ✗ 置顶） | PASS |
| 3 | 数字 4 位小数（fmtNum） | PASS |
| 4 | match 端点 hover 显示 match 标签 + event 三段 | **PASS**（Task 1.5 修复后） |
| 5 | K-bar tooltip 不变 | PASS |

**总体**: 5/5 PASS — 全部通过
