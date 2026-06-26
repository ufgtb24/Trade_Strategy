# path2_web 多 pattern 同扫与漏检调试设计

> 日期:2026-06-27
> 范围:path2_web 后端 + path2_web_ui 前端
> 目标:支持多 pattern 同时扫描,股票列表为并集、每 pattern 单开 forward_return 列;右侧主图/拓扑/侧栏单 active pattern 展示。核心场景=用锚 pattern(如 bo)排序找调优目标 pattern(如 bbb)的漏检。

## 1. 动机

调整 dag pattern 的关键是查看漏检——已知某些上涨股理应被 pattern 命中,实际未命中。当前 web UI 一次只能扫一个 pattern,要复刻"基于 bo 锚 label 排序找漏检"的工作流必须每次切 pattern 重扫一遍,无法在同一画面上交叉比对。

引入"多 pattern 同扫"后:
- 把 bo 也当作一个独立 pattern(`path2_apps/bo_only/`),用它对全市场扫出"bo 命中股 + max forward_return"作为涨幅锚
- 同时扫调优目标 pattern(`bottom_breakout_burst`)
- 股票列表展示**并集**:任一 pattern 命中即入选,每 pattern 单开 ret 列
- 用户按 bo.ret 列降序,逐股查看 bbb 的扫描结果(detected/qualified/matched 三档),判断哪个 role 没检测到 / 哪个 where 不通过 / 哪条边关系断裂

## 2. 设计原则与已锁定决策

1. **N=1 是退化情况、不是特例**:统一 schema、统一目录、统一组件路径。无"单 pattern 模式"分叉。
2. **锚 pattern 与 active pattern 解耦**:排序锚由用户点列头决定,右侧 active pattern 由 ChartArea dropdown 显式决定;cell 点击只切股、不切 active pattern。
3. **每股每 pattern 都跑完整 analyze 并写完整 analysis**:events 全集必存(用于 K 线 detected 层),matches 可空数组。
4. **铁律:所有 pattern 必须声明 eval_meta**:discovery 闸过滤;删除所有 fallback 到非缓冲路径的代码。
5. **缓冲段事件可见(灰色层)沿用现状**:多 pattern 取 max(head_buffer) 后超额段的 events 照常检出可见。
6. **preview 永远跟随 activePatternId**:切股、切 active pattern 都自动重算 preview(若开)。

## 3. 后端 schema 与契约

### 3.1 落盘文件结构 `MultiScanResultFile`

```python
{
  "pattern_ids": ["bo_only", "bottom_breakout_burst"],
  "per_pattern": {
    "bo_only": {
      "pattern_spec": <SerializedPattern>,    # 自包含,离线渲染
      "end_role": "bo"
    },
    "bottom_breakout_burst": {
      "pattern_spec": <SerializedPattern>,
      "end_role": "tb"
    }
  },
  "scan": {
    "scan_ts": "20260627T120000",
    "start_date": "2024-01-01",
    "end_date":   "2024-06-30",
    "workers": 8,
    "dataset_dir": "...",
    "params": "yaml-frozen-snapshot",
    "win_start": "2023-08-01",          # buf_start (取 max head_buffer)
    "win_end":   "2024-08-01",          # buf_end   (label_horizon * 1.65 日历日)
    "label_horizon": 20,                # 全局单值
    "scanned": 6048,
    "hits": 423,                         # 并集计数:至少一个 pattern matches 非空
    "errors": 5
  },
  "results": [
    {
      "symbol": "AAPL",
      "per_pattern": {
        "bo_only": {
          "summary": {"bo": 18, "matches": 18},      # {class_id: count} ∪ {matches: n}
          "analysis": {"events": [...], "matches": [...]},   # 完整 analysis
          "max_forward_return": 0.234                 # max over matches; matches 空 → null
        },
        "bottom_breakout_burst": {
          "summary": {"bo": 18, "burst": 3, "tb": 2, "matches": 2},
          "analysis": {"events": [...], "matches": [...]},
          "max_forward_return": 0.182
        }
      }
    },
    # ... 排序按 worker 内 results.sort(key=symbol);前端排序在 store 派生
  ]
}
```

**关键不变量**:
- `results` 每行的 `per_pattern` 字典键集 ≡ `pattern_ids`(每股每 pattern 必有项,即使 matches 空)。
- 行入选并集条件:`any(len(per_pattern[pid].analysis.matches) > 0 for pid in pattern_ids)`。
- `max_forward_return = max(m.forward_return for m in matches if m.forward_return is not None)`;matches 空或全 None → `null`。

### 3.2 落盘路径

- 新:`outputs/path2_web/scans/<scan_ts>.json`(扁平、无 per-pattern 子目录)。
- 旧:`outputs/path2_web/<pattern_id>/<scan_ts>.json` 不迁移、不读、不列。用户可手动 rm。

### 3.3 后端路由

| 方法 | 路径 | 改动 |
|---|---|---|
| POST | `/scan` | body 改 `{pattern_ids: List[str], start_date, end_date, workers, ticker_regex?, label_horizon}`;校验 `len ≥ 1`,空数组返 422;重复 pid 自动去重 |
| GET | `/scans/` | **新:无 pattern_id**,列 `outputs/path2_web/scans/` 历史。每 entry 含 `scan_ts, pattern_ids: string[], hits, total, size, partial` |
| GET | `/scans/{scan_ts}` | **新:无 pattern_id 前缀**,加载单次 MultiScanResultFile |
| DELETE | `/scans/{scan_ts}` | **新:无 pattern_id 前缀**,删 |
| GET | `/diagnose` | 不变(per-pattern + per-symbol) |
| GET | `/preview` | body 仍是单 pattern_id(preview 永远单 pattern 单股) |
| GET | `/patterns` | 不变,但 discovery 过滤后只返回声明了 eval_meta 的 pattern |
| GET | `/ohlc` · `/config` · POST `/scan/{id}/cancel` · GET `/scan/{id}/stream` | 不变 |
| ~~GET `/scans/{pid}`~~ | ~~`/scans/{pid}/{ts}`~~ ~~DELETE `/scans/{pid}/{ts}`~~ | **删除**,前端不再调用 |

### 3.4 worker 与 run_scan

`run_scan` 改签名:
```python
def run_scan(
    *, data_dir,
    pattern_specs_json: Dict[str, dict],      # pid -> serialized pattern_spec (前端透传)
    module_paths: Dict[str, str],             # pid -> "path2_apps.bo_only" 之类
    end_roles: Dict[str, str],                # pid -> end_role (每 pattern 必有)
    head_buffer_trading_days: int,            # 已是 max(per pattern head_buffer)
    label_horizon: int,                       # 全局单值
    start_date, end_date, workers, ticker_regex, scan_ts,
    outputs_root, on_progress, executor_factory,
    cancel_event, save_event,
) -> dict:
```

worker per-stock 逻辑(在 `_scan_ticker_multi`):
```
df = read_pkl(pkl_path)
buf_win = slice_window(df, buf_start, buf_end)   # 一次性切
if len(buf_win) == 0: return (symbol, None, None, None)

per_pattern = {}
for pid in pattern_ids:
  mod = import(module_paths[pid])
  res = mod.analyze(buf_win, mod.load_params())
  # 窗口过滤 + label 注入:口径与现 _analyze_single buffered 路径同
  filtered_matches = []
  for m in res.matches:
    ev = m.role_index[end_roles[pid]]
    buy_date = buf_win["date"].iat[ev.start_idx]
    if start_ts <= buy_date <= end_ts:
      ret = match_forward_returns(m, end_roles[pid], buf_win, [label_horizon])[label_horizon]
      filtered_matches.append({**serialize_match(m), "forward_return": ret})

  analysis = serialize_analysis(res)              # events 全集照旧
  analysis["matches"] = filtered_matches
  summary = summarize(res)
  summary["matches"] = len(filtered_matches)
  max_ret = max((m["forward_return"] for m in filtered_matches if m["forward_return"] is not None),
                default=None)
  per_pattern[pid] = {"summary": summary, "analysis": analysis,
                      "max_forward_return": max_ret}

# 入选并集条件
any_match = any(per_pattern[pid]["summary"]["matches"] > 0 for pid in pattern_ids)
if not any_match: return (symbol, None, None, None)
return (symbol, per_pattern, None)
```

`_aggregate` 改 result 形态:
```python
results.append({"symbol": symbol, "per_pattern": per_pattern})
```

SSE 进度事件 shape 不变(`{scanned, total, hits, errors}`),total = N_stocks。

### 3.5 discovery 改造(铁律落地)

`PatternRegistry.discover` 扫 `path2_apps/*/dag_spec.py`,对每个候选 pattern:
1. 必须 import 成功
2. 必须有 `PATTERN_DAG` 模块级常量
3. 必须有 `analyze` 函数
4. **必须有 `eval_meta` callable**
5. **`eval_meta()` 返回 dict 且包含 `end_role: str` 和 `head_buffer_trading_days: int`**

任一失败:**跳过该 pattern + log warning**。`PatternRegistry.ids()` 不返回,`/patterns` 不返回,前端面板不可见。

### 3.6 fallback 路径清理

铁律下永远不走非缓冲路径,删除以下分支:
- `path2_web/api.py::resolve_eval_meta` 改为 `require_eval_meta`,缺/错抛 ValueError 而非返 None
- `path2_web/scan.py::analyze_single` 删 `end_role is None` 分支(非缓冲路径)
- `path2_web/scan.py::run_scan` 删 `head_buffer_trading_days is None` 分支
- `path2_web/api.py::post_scan` 删 `meta is None` 分支
- `path2_web/api.py::get_preview` 删 `meta is None` else 分支
- `path2_web_ui/src/render/visible.ts::windowOf` 删 `win_*` 缺失回退 `start_date/end_date` 分支(改为 `win_*` 必有,缺则抛)
- `path2_web/scan.py::analyze_single` meta_template 中 `win_start, win_end, end_role, label_horizon` 改为永远非 null

## 4. 前端 store 与组件

### 4.1 types.ts 镜像

```ts
// 替换原 ScanResultFile / StockResult
export interface PerPatternResult {
  summary: Record<string, number>            // {class_id: count} ∪ {matches: n}
  analysis: Analysis                          // events + matches(可空)
  max_forward_return: number | null
}
export interface StockResult {
  symbol: string
  per_pattern: Record<string, PerPatternResult>    // key = pattern_id
}
export interface PerPatternMeta {
  pattern_spec: SerializedPattern
  end_role: string
}
export interface MultiScanResultFile {
  pattern_ids: string[]
  per_pattern: Record<string, PerPatternMeta>
  scan: ScanMeta                              // win_start/win_end/label_horizon/end_role 永远非 null
                                              // (end_role 字段语义改:每 pattern 自有,此字段移除)
  results: StockResult[]
}
export interface ScanHistoryEntry {
  scan_ts: string
  pattern_ids: string[]                       // 新:此次扫描覆盖
  hits: number | null
  total: number | null
  size: number
  partial: boolean
}
```

`ScanMeta.end_role` 字段移除(每 pattern 自有,在 `per_pattern[pid].end_role`)。其余字段(`win_start/win_end/label_horizon`)改为非 optional(必有)。

### 4.2 view store 改造

state:
```ts
const scanFile = ref<MultiScanResultFile | null>(null)
const activePatternId = ref<string | null>(null)
const sortByPid = ref<string | null>(null)
const sortDesc = ref(true)
```

computed:
```ts
const patternIds = computed(() => scanFile.value?.pattern_ids ?? [])
const currentPerStock = computed<StockResult | null>(() =>
  scanFile.value?.results.find(r => r.symbol === symbol.value) ?? null)

// active-pattern-derived 三件套(preview 命中优先)
const pattern = computed<SerializedPattern | null>(() => {
  if (!activePatternId.value || !scanFile.value) return null
  return scanFile.value.per_pattern[activePatternId.value]?.pattern_spec ?? null
})
const currentAnalysis = computed<Analysis | null>(() =>
  currentPerStock.value?.per_pattern[activePatternId.value!]?.analysis ?? null)
const effectivePattern = computed<SerializedPattern | null>(() => {
  if (previewEnabled.value && preview.value
      && preview.value.symbol === symbol.value
      && preview.value.pattern_spec.pattern_id === activePatternId.value)
    return preview.value.pattern_spec
  return pattern.value
})
const effectiveAnalysis = computed<Analysis | null>(() => {
  if (previewEnabled.value && preview.value
      && preview.value.symbol === symbol.value
      && preview.value.pattern_spec.pattern_id === activePatternId.value)
    return preview.value.analysis
  return currentAnalysis.value
})

// 列表:并集行 + per-pattern cell
type UnionRow = { symbol: string; cells: Array<{ pid: string; max_ret: number | null; matched: boolean }> }
const unionRows = computed<UnionRow[]>(() => /* 从 scanFile.results 派生 */)
const sortedRows = computed<UnionRow[]>(() => /* 按 sortByPid + sortDesc;null 永远沉底 */)
```

actions:
```ts
loadScanFile(f: MultiScanResultFile) {
  scanFile.value = f
  // active pattern 初值:优先 last_selected_pattern(若在 pattern_ids 中)、否则 pattern_ids[0]
  const last = useConfigStore().config.last_selected_pattern
  activePatternId.value = f.pattern_ids.includes(last) ? last : f.pattern_ids[0] ?? null
  sortByPid.value = null               // 默认不排序,worker 顺序
  symbol.value = f.results[0]?.symbol ?? null
  // 其他状态复位(roleVisible/selected/selectedEventId/hoveredEventId/preview/previewError)
}
setActivePattern(pid: string) {
  activePatternId.value = pid
  useConfigStore().setLastSelectedPattern(pid)
  // diag watch 与 preview watch 自动响应
}
setSort(pid: string) {
  if (sortByPid.value === pid) sortDesc.value = !sortDesc.value
  else { sortByPid.value = pid; sortDesc.value = true }
}
```

cell 点击:**只 selectSymbol,不动 activePatternId**(铁律之 §2)。

diag watch 依赖列表新增 `activePatternId`:
```ts
watch([symbol, scanFile, activePatternId, preview, previewEnabled], async () => {
  if (!symbol.value || !activePatternId.value || !scanFile.value) { diag.value = null; return }
  // 用 activePatternId 调 /diagnose
})
```

preview watch 行为:`setActivePattern` / `selectSymbol` 都触发 `runPreview()` 若 `previewEnabled`;`runPreview` 用 `activePatternId.value` 作为 pattern_id。

### 4.3 组件改造

**`SidebarPatternPanel`**:
- 单选 radio → 多选 checkbox(state 改为 `Set<string>`,store 中存 `selected_pattern_ids`)
- 顶部加"全选 / 反选 / 清空"操作
- 加载/选 active 时:不直接动 selected_pattern_ids(这只与扫描配置有关),保留独立 store 字段

**`SidebarScanPanel`**:
- "起扫描"按钮 disabled 条件:`selected_pattern_ids.size === 0`
- body: `pattern_ids: Array.from(selected_pattern_ids)`

**`SidebarResultList`**:
- 表头新增 N 列:`th = pattern.display_name`(title=pattern_id),点击切 sortByPid/翻向(三态:升/降/无;但 spec §4.2 简化为二态切换,默认 desc)
- 每行 N 个单元格:`max_ret` 经 `formatForwardReturn` 格式化;null = `—`
- 单元格背景按 `matched`(布尔)染色:命中=浅色背景、未命中=灰白
- cell 点击:`selectSymbol(symbol)` 单一动作
- preview 工具栏不动
- 排序方向:默认无排序(worker 顺序);点列头第一次 desc、第二次 asc、第三次回 null(可选);本 spec 简化为二态(desc / asc),不支持回 null,因第一次点列头即变 desc

**`ChartArea`**:
- 顶部 level 控件旁新增 `<select v-model="activePatternId">`,options 来自 `view.patternIds`
- TopologyControl / KlineChart / DetailSidebar 不改(都从 view 的 active-pattern-derived computed 派生)

**`ScanResultDialog`**:
- 后端路由改 `/scans/`(无 pid),前端 dialog 移除 per-pattern 子目录
- 每行展示 `scan_ts + pattern_ids chips + hits + total + partial 图标`
- 选中即加载对应 MultiScanResultFile

## 5. 数据流时序

### 5.1 起多 pattern 扫描

```
User: 勾 [bo_only, bbb],点起扫描
→ scan.run({pattern_ids:["bo_only","bbb"], start, end, label_horizon=20})

Backend POST /scan:
  load_params + build_pattern × 2
  meta_per_pid = {pid: require_eval_meta(mod) for ...}   # 缺失即抛
  head_buffer = max(meta_per_pid[pid]["head_buffer_trading_days"] for pid in ...)
  end_roles = {pid: meta["end_role"] for ...}
  manager.start(scan_id, job=run_scan(pattern_specs={...}, end_roles, head_buffer, label_horizon, ...))

Worker per stock:
  df = read_pkl, buf_win = slice(df, buf_start, buf_end)   # 一次切
  for pid in pattern_ids:
    res = analyze(spec_pid, buf_win, params_pid)
    filtered_matches = filter+inject_label(res.matches, end_role=end_roles[pid], label_horizon)
    per_pattern[pid] = {summary, analysis(events全集+filtered_matches), max_forward_return}
  if any(per_pattern[pid].summary.matches > 0):
    yield {symbol, per_pattern}

Backend done → SSE done {scan_ts}
Frontend:
  scan.open(scan_ts) → loadScan(scan_ts) → view.loadScanFile(file)
  activePatternId = config.last_selected_pattern if in pattern_ids else pattern_ids[0]
```

### 5.2 找漏检工作流

```
列表初始:sortByPid=null,worker 顺序;activePatternId=bbb(用户在调 bbb)
点 bo_only 列头 → sortByPid=bo_only, sortDesc=true → 列表按 bo_only.max_ret 降序
点列表 stockX 行(bbb.ret=—,bo_only.ret=0.85)
  → selectSymbol(stockX)
  → activePatternId 维持 bbb
  → diag watch 触发,拉 /diagnose?pattern_id=bbb&symbol=stockX
  → ChartArea 显示 stockX 在 bbb 视角下:K 线 + 拓扑 + 漏斗(detected ⊇ qualified ⊇ matched=0)
  → DetailSidebar 看哪个 role qualified→matched 断
  → 必要时切下拉到 bo_only 看 bo 在该股的散布
```

### 5.3 preview 切 active pattern

```
User 改 bbb yaml → stockX 页面勾 preview
→ runPreview(activePatternId=bbb, stockX, baseScan.start_date, baseScan.end_date, label_horizon)
→ Backend GET /preview?pattern_id=bbb&symbol=stockX&...
→ view.preview = {symbol: stockX, analysis, pattern_spec, scan}
→ effective 三件套切到 preview;K 线/拓扑/侧栏按 preview 重渲染

User 切 active pattern → bo_only
→ activePatternId = bo_only
→ effective 三件套:preview.pattern_spec.pattern_id="bbb" ≠ "bo_only" → 不命中
   退回 scanFile.per_pattern[bo_only].analysis
→ 因 previewEnabled=true,触发 runPreview(activePatternId=bo_only, stockX, ...)
→ 完成后 view.preview 更新为 bo_only 的临时结果
→ effective 三件套重新命中 preview
```

### 5.4 取消扫描

cancel 路径不变;run_scan 检测点抛 ScanCancelled,上层捕获写 partial MultiScanResultFile。

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| pattern 缺 eval_meta 或字段不全 | discovery 闸过滤,/patterns 不返回,前端面板不可见 |
| POST /scan body `pattern_ids` 为空 / 含未注册 pid | 422 / 404 |
| worker 内某 pattern analyze 抛异常 | 该股整条 errors++(不进 results),其他股不受影响 |
| 用户取消扫描 | 落 partial MultiScanResultFile,前端加载与正常文件路径一致 |
| `last_selected_pattern` 不在文件 pattern_ids 中 | fallback 到 `pattern_ids[0]`,不修改 config |
| pattern_ids 含重复 | 后端 dict 自然去重 |
| 加载旧 outputs/<pid>/<ts>.json | 不读取(路由删除);手动 rm 由用户负责 |

## 7. 测试

### 7.1 后端 pytest

- `test_discovery_eval_meta_required.py`:fake_app 缺 eval_meta / 缺 end_role / 缺 head_buffer_trading_days → 不进 registry
- `test_scan_multi_pattern.py`:N=2 pattern 同扫,落盘 MultiScanResultFile schema 正确;per_pattern 字典键集 ≡ pattern_ids;并集语义;head_buffer = max
- `test_scan_multi_pattern_partial_failure.py`:worker 内一 pattern 抛异常 → 该股 errors++,其他股不受影响
- `test_scan_buffered_only.py`:scan meta 的 win_*/label_horizon 永远非 null;非缓冲分支不可达
- `test_serialize_multi.py`:per_pattern 投影 round-trip
- `test_api_scan_post.py`:pattern_ids=[] 返 422;重复 pid 去重;未注册 pid 返 404
- `test_scans_route.py`:`GET /scans/` 列、`GET /scans/{ts}` 加载、`DELETE /scans/{ts}` 删

### 7.2 前端 vitest

- `view.spec.ts`:
  - loadScanFile 后 activePatternId 初值规则(优先 last_selected_pattern;否则 pattern_ids[0])
  - setActivePattern 触发 diag 重拉 + preview 重算(若 enabled)
  - effective 三件套 preview 命中条件:symbol 匹配 + pattern_spec.pattern_id 匹配
- `unionRows.spec.ts`:
  - 入选条件 = 至少一个 pattern.matches 非空
  - max_forward_return:None 时单元格 null
  - sortedRows:null 永远沉底;翻向正确
- `SidebarResultList.spec.ts`:
  - N 列 th 渲染 display_name + title=pattern_id
  - 点列头切 sortByPid;再点同列翻向
  - cell 点击只 selectSymbol、不动 activePatternId
- `SidebarPatternPanel.spec.ts`:
  - checkbox 多选状态 ↔ selected_pattern_ids
  - 全选/反选/清空
- `ChartArea.spec.ts`:
  - active pattern dropdown 渲染 patternIds
  - select change → setActivePattern

### 7.3 端到端手动 playwright

- N=1 退化路径:勾单个 bbb,行为/视觉等同重构前
- N=2 主路径:勾 [bo_only, bbb] → 起扫描 → 列表 N 列正确 → 按 bo_only 列降序 → 点高 bo.ret 股 → 右侧维持 bbb 视图 → 切下拉到 bo_only 观察 → 开 preview 切 active pattern 自动重算

## 8. 实施顺序与拆分

按 plan-execution.md "默认不拆分" 原则,本 spec 写成一份完整 plan、单 session 跑完。Plan 涵盖:

1. 后端 discovery 闸 + fallback 清理(铁律落地)
2. 后端 schema + serialize + worker + run_scan 多 pattern 改造
3. 后端 api 路由改造(/scan / /scans 系列 / /preview)
4. types.ts + scanFile.ts 加载层适配
5. view store 改造(activePatternId / unionRows / sortedRows / effective 三件套 / watch 依赖)
6. SidebarPatternPanel + SidebarScanPanel 多选改造
7. SidebarResultList N 列 + 点列头排序 + cell 只切股
8. ChartArea 顶部 dropdown
9. ScanResultDialog 改造
10. `path2_apps/bo_only/` 子包新建(dag_spec + params + yaml + eval_meta)
11. 后端 pytest + 前端 vitest 各 gate 绿
12. 手动 playwright e2e 实证 N=1 退化 + N=2 主路径

每 task 双审(spec + quality)+ 最终 holistic,subagent-driven 跑(`superpowers:subagent-driven-development`)。Plan 自包含,新 session 可粘贴直接实施。

## 9. 不在本 spec 范围(显式排除)

- 旧 `outputs/<pid>/<ts>.json` 迁移:不做。用户手动 rm。
- 单 pattern 路径与多 pattern 路径并存:不做。N=1 是退化情况。
- preview 多 pattern 并算:不做。preview 永远单 pattern。
- 列表 N 列的"matched count + max_ret"双子列:不做。仅 max_ret 一列。
- 列表默认按 active pattern 排序:不做。默认无排序,用户显式点列头。
- diag 为所有命中 pattern 预取:不做。只为 activePatternId 预取。
- 缓冲段 events 不可见的语义重构:不做。沿用现状。
- 右侧主图同时叠加多 pattern 的 markers:不做。永远单 active pattern。
