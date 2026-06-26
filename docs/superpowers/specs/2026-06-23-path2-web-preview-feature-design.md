# path2_web 临时计算(preview)功能 — 设计 Spec

**日期**:2026-06-23
**目标**:在已加载扫描结果的场景下,允许用户用当前 `params.yaml` 即时计算选中股票(不落盘),立刻观察调参效果。

## 1. 背景

`params.yaml` 的热加载已通(改 yaml 下一次 `/scan` 即生效,无需重启 web)。但 `/scan` 跑全集 + ProcessPool + 落 json,跑一次 5-30 分钟,不适合"改一行 yaml 看一只股"的调参循环。

本功能加一条**单股临时计算侧链路**:

- 后端新加 `/preview` 端点,复刻 `_scan_ticker` 的 buffered + label 逻辑,单股同步返回 analysis + pattern_spec
- 前端 view store 加 `previewEnabled / preview / previewLoading / previewError` 四个 state + `effectiveAnalysis / effectivePattern / effectiveScan` 三个派生
- `SidebarResultList` 顶部加复选框 "用 yaml 临时计算" + 刷新按钮 ↻

复选框持久勾选:勾选状态下切股票自动 fetch,无需每只股点一次。改 yaml 后点 ↻ 刷新当前股。

## 2. 架构

```
[scan 主链路]                  [preview 侧链路 — 新加]
  POST /scan                    GET /preview?pattern_id=&symbol=&start=&end=&label_horizon=
  ProcessPool 全集               单股同步 in-process
  落盘 json                      不落盘,直接返回
  SSE 进度 + done                 同步 200 响应
  view.scanFile                  view.preview(临时叠加层)
       ↑                                    ↑
       └────── computed.effective{Analysis,Pattern,Scan} ──┘
                       (preview 优先)
```

**核心契约**

- 后端 `/preview` 与 `/scan` 共用底层 `analyze_single` 函数(buffered 窗 + 窗内 match 过滤 + forward_return 注入);`_scan_ticker` 改为薄包装。
- `/preview` 同步返回时一并带 `pattern_spec`(用最新 yaml build),前端 preview 期间拓扑面板 / where 阈值 / K 线 markers 三者一致反映新 yaml。
- 前端 `previewEnabled` 是持久勾选状态;`preview` 只保存当前显示那一只股的结果(不 cache 多股)。
- 切股票 + 勾选状态 → 自动 fetch 新股 preview。改 yaml 后点 ↻ → 强制重 fetch 当前股(无 cache 故自然重 fetch)。

## 3. 后端

### 3.1 端点

```
GET /preview?pattern_id=<str>&symbol=<str>&start=<YYYY-MM-DD>&end=<YYYY-MM-DD>&label_horizon=<int>
```

响应 (HTTP 200):

```json
{
  "analysis": { "events": [...], "matches": [...], "role_index": {...} },
  "summary":  { "events": N, "matches": M },
  "pattern_spec": { ... },           // serialize_pattern(mod.build_pattern(mod.load_params()))
  "scan": {
    "start_date": "...", "end_date": "...",
    "win_start":  "...", "win_end":  "...",
    "end_role":  "...",   "label_horizon": 20
  }
}
```

`analysis` 字段 schema 与 `serialize_analysis(res)` 一致(events + matches + role_index),`pattern_spec` 与 `serialize_pattern(spec)` 一致,`scan` 字段与 `ScanResultFile.scan` 子集一致 — 前端 `windowOf(effectiveScan)` 可复用原口径。

### 3.2 错误

| 触发 | HTTP | 响应 detail |
|------|------|------------|
| `pattern_id` 未注册 | 404 | `unknown pattern: <pattern_id>` |
| `symbol` 对应 pkl 不存在 | 404 | `pkl not found: <symbol>` |
| yaml 拼错(未知字段) | 500 | `ValueError: params.yaml (...) 含未知字段: [...]` |
| `analyze_single` 抛异常 | 500 | `<Type>: <msg>` |

### 3.3 边界 — 空窗 / 无 match

`analyze_single` 在空窗或 0 命中时返回 `analysis = {events: [], matches: [], role_index: {}}` + `summary = {events: 0, matches: 0}`(显式空集,**不是 null**),HTTP 200。前端不弹 error,K 线 markers 空,复选框仍勾选状态。

### 3.4 边界 — `eval_meta` 缺失

`mod.eval_meta` 不存在 / 返回 None / 协议不符 → 走非 buffered 路径:

- `win_start = start_date`,`win_end = end_date`(严格窗)
- 不算 forward_return,matches 不过滤
- 响应 `scan.end_role = null`,`scan.label_horizon = null`

前端无感(`windowOf` 只看 win_start/win_end)。

### 3.5 内部抽取 — `analyze_single`

`path2_web/scan.py` 中抽出新函数:

```python
def analyze_single(*, pkl_path, module_path, start_date, end_date,
                   end_role=None, label_horizon=None) -> tuple:
    """返回 (analysis_dict|None, summary_dict|None, scan_meta_dict)

    复刻 _scan_ticker 的 buffered 逻辑:
      - buffered = end_role is not None
      - buffered=True: slice_window(df, buf_start, buf_end), 窗内过滤 + label
      - buffered=False: slice_window(df, start_date, end_date), 不过滤不算 label
    空窗 → analysis_dict = {"events":[], "matches":[], "role_index":{}}
    异常向上抛(/preview 路由层捕获转 500)
    """
```

`_scan_ticker` 改为薄包装:

```python
def _scan_ticker(pkl_path, module_path, start, end,
                 buf_start=None, buf_end=None, end_role=None, label_horizon=None):
    symbol = Path(pkl_path).stem
    try:
        # buf_start/buf_end 参数保持向后兼容,内部用 end_role 判断 buffered
        analysis, summary, _ = analyze_single(
            pkl_path=pkl_path, module_path=module_path,
            start_date=start, end_date=end,
            end_role=end_role, label_horizon=label_horizon)
        if analysis is None or len(analysis["matches"]) == 0:
            return (symbol, None, None, None)
        return (symbol, analysis, summary, None)
    except Exception as e:
        return (symbol, None, None, f"{type(e).__name__}: {e}")
```

注:_scan_ticker 把"0 命中跳过"语义保留(scan 落盘只关心命中股),analyze_single 不做这层判断 — preview 即便 0 命中也要返回供前端展示。

### 3.6 路由 — `api.py` 加 `@router.get("/preview")`

```python
@router.get("/preview")
def get_preview(pattern_id: str, symbol: str, start: str, end: str,
                label_horizon: int = 20):
    mod = registry.get(pattern_id)
    if mod is None:
        raise HTTPException(404, f"unknown pattern: {pattern_id}")
    cfg = get_config()
    pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
    if not pkl.exists():
        raise HTTPException(404, f"pkl not found: {symbol}")

    meta = resolve_eval_meta(mod)          # 与 /scan 同口径
    end_role = meta["end_role"] if meta else None
    head_buf = meta["head_buffer_trading_days"] if meta else None

    if meta:
        start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
        buf_start = start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))
        buf_end   = end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))
        win_start, win_end = str(buf_start.date()), str(buf_end.date())
    else:
        win_start, win_end = start, end

    analysis, summary, _ = scan_mod.analyze_single(
        pkl_path=str(pkl), module_path=registry.module_path(pattern_id),
        start_date=start, end_date=end,
        end_role=end_role, label_horizon=label_horizon if meta else None)

    pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))

    return {
        "analysis": analysis or {"events": [], "matches": [], "role_index": {}},
        "summary":  summary  or {"events": 0, "matches": 0},
        "pattern_spec": pattern_spec,
        "scan": {
            "start_date": start, "end_date": end,
            "win_start":  win_start, "win_end": win_end,
            "end_role":   end_role,
            "label_horizon": label_horizon if meta else None,
        },
    }
```

### 3.7 并发护栏

`/preview` 同步阻塞跑在 FastAPI worker(asyncio 线程)上,单股 2-5s。短期 YAGNI 接受同步阻塞;后期若多 tab / 多浏览器卡了,把 `analyze_single` 扔 `run_in_executor` 即可(单股 in-process,无 pickle 问题)。

## 4. 前端

### 4.1 view store(`stores/view.ts`)

新增 state:

```ts
const previewEnabled = ref(false)
const preview = ref<{
  symbol: string
  analysis: AnalysisDict
  pattern_spec: SerializedPattern
  scan: ScanMeta
} | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
```

新增 computed:

```ts
const effectiveAnalysis = computed<AnalysisDict | null>(() => {
  if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
    return preview.value.analysis
  return currentResult.value?.analysis ?? null
})

const effectivePattern = computed<SerializedPattern | null>(() => {
  if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
    return preview.value.pattern_spec
  return scanFile.value?.pattern_spec ?? null
})

const effectiveScan = computed<ScanMeta | null>(() => {
  if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
    return preview.value.scan
  return scanFile.value?.scan ?? null
})
```

新增 actions:

```ts
async function setPreviewEnabled(v: boolean) {
  previewEnabled.value = v
  if (v) {
    await runPreview()
  } else {
    preview.value = null
    previewError.value = null
  }
}

async function runPreview() {
  if (!scanFile.value || !symbol.value || !pattern.value) return
  previewLoading.value = true
  previewError.value = null
  const reqSymbol = symbol.value
  const reqEnabled = previewEnabled.value
  try {
    const w = windowOf(effectiveScan.value ?? scanFile.value.scan)
    const labelHorizon = effectiveScan.value?.label_horizon ?? 20
    const resp = await getPreview(pattern.value.pattern_id, reqSymbol, w.start, w.end, labelHorizon)
    if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
    preview.value = { symbol: reqSymbol, ...resp }
  } catch (e: any) {
    if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
    previewError.value = String(e?.message ?? e)
  } finally {
    // loading 也用 token guard:并发场景(切股票时新旧两次 fetch 并发,旧的先回)
    // 不能把 loading 错误置 false — 当前真在跑的是新的那次。
    if (symbol.value === reqSymbol && previewEnabled.value === reqEnabled)
      previewLoading.value = false
  }
}
```

修改既有 actions:

```ts
function selectSymbol(s: string) {
  symbol.value = s
  selected.value = null
  selectedEventId.value = null
  hoveredEventId.value = null
  preview.value = null            // 新增:清旧股的临时结果
  previewError.value = null       // 新增
  if (previewEnabled.value) void runPreview()   // 新增:勾选状态自动 fetch 新股
}

function clearScanFile() {
  scanFile.value = null
  symbol.value = null
  roleVisible.value = {}
  selected.value = null
  selectedEventId.value = null
  hoveredEventId.value = null
  previewEnabled.value = false    // 新增
  preview.value = null            // 新增
  previewError.value = null       // 新增
}
```

### 4.2 下游消费者迁移

| 现有 | 改读 |
|------|------|
| `currentAnalysis` 在 KlineChart / DetailSidebar / render/*.ts | `effectiveAnalysis` |
| `pattern.value` 在 TopologyControl / DetailSidebar / colors / visible | `effectivePattern` |
| `windowOf(scanFile.value.scan)` 在 diag watch / KlineChart | `windowOf(effectiveScan.value)` |
| diag 预取 watch 依赖 `[symbol, scanFile, pattern]` | `[symbol, scanFile, preview, previewEnabled]`(preview 变化时重取 diagnose) |

`currentResult / currentAnalysis` 保留(语义:列表当前选中股的扫描结果),但消费者改读 `effectiveAnalysis`。

### 4.3 API 封装(`api.ts`)

```ts
export interface PreviewResp {
  analysis: AnalysisDict
  summary: SummaryDict
  pattern_spec: SerializedPattern
  scan: ScanMeta
}

export function getPreview(patternId: string, symbol: string,
                            start: string, end: string,
                            labelHorizon: number): Promise<PreviewResp> {
  return getJson(`/preview?pattern_id=${patternId}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&label_horizon=${labelHorizon}`)
}
```

### 4.4 UI(`SidebarResultList.vue`)

列表顶部加 `.preview-bar`:

```vue
<div class="preview-bar">
  <label class="toggle">
    <input type="checkbox" :checked="previewEnabled" :disabled="!scanFile"
           @change="onToggle($event)" />
    <span>用 yaml 临时计算</span>
    <button class="refresh" title="重算当前股(yaml 改过后用)"
            :disabled="!canRefresh" @click="view.runPreview">↻</button>
  </label>
  <div v-if="previewLoading" class="status">计算中…</div>
  <div v-if="previewError" class="error">
    临时计算失败: {{ previewError }}
    <a @click="onCloseError">×</a>
  </div>
</div>
```

disabled 规则:

| 元素 | disabled 当 |
|------|------------|
| 复选框 | `!scanFile` |
| 刷新按钮 ↻ | `!previewEnabled \|\| !preview \|\| previewLoading \|\| preview.symbol !== symbol` |

### 4.5 切股票 UX 实况(勾选状态下)

1. 用户点列表新股票
2. `selectSymbol` 内清 `preview` → `effectiveAnalysis` 瞬间 fall back 到新股的扫描结果(K 线显示扫描 markers)
3. 同 tick 触发 `runPreview()` → `previewLoading = true` → 复选框旁显示"计算中…"
4. 2-5s 后 preview 到 → K 线 markers / 拓扑 / where 切到 preview 数据

短暂闪烁(扫描 → preview)可接受。如果后期需要"loading 期间藏 markers",可在 KlineChart 中加 loading 守门(out-of-scope)。

## 5. 测试矩阵

### 5.1 后端 `tests/path2_web/test_preview.py`(新建)

| 测试 | 验证点 |
|------|--------|
| `test_preview_returns_analysis_pattern_spec_and_scan_meta` | 4 个 key 齐 + schema |
| `test_preview_uses_buffered_window_when_eval_meta_present` | win_start/win_end 拉宽,end_role/label_horizon 非 null |
| `test_preview_falls_back_when_eval_meta_missing` | 严格窗,scan.end_role/label_horizon=null |
| `test_preview_matches_have_forward_return_in_buffered_path` | buffered matches 都有 forward_return |
| `test_preview_pattern_spec_reflects_current_yaml` | monkeypatch load_params → pattern_spec 反映改后值 |
| `test_preview_unknown_pattern_404` | 404 |
| `test_preview_pkl_not_found_404` | 404 |
| `test_preview_empty_window_returns_empty_analysis` | 200 + 显式空集 |
| `test_preview_no_match_returns_empty_analysis` | 200 + matches=[] |
| `test_analyze_single_is_pure_and_reusable` | 单测 analyze_single 直接调,验证 _scan_ticker 已改薄包装 |

### 5.2 前端 `path2_web_ui/tests/stores/view.preview.test.ts`(新建)

| 测试 | 验证点 |
|------|--------|
| `effectiveAnalysis_falls_back_when_previewEnabled_false` | enabled=false → scan |
| `effectiveAnalysis_falls_back_when_preview_symbol_mismatch` | symbol 不匹配 → scan |
| `effectiveAnalysis_uses_preview_when_three_conditions_met` | 三条件齐 → preview |
| `setPreviewEnabled_true_triggers_runPreview` | mock fetch,enabled=true 后 fetch 被调 |
| `setPreviewEnabled_false_clears_preview_state` | 清 preview + previewError |
| `selectSymbol_clears_preview_and_refetches_when_enabled` | 切股票自动 fetch |
| `selectSymbol_does_not_fetch_when_disabled` | enabled=false 切股票不 fetch |
| `clearScanFile_resets_all_preview_state` | 三者全复位(含 enabled) |
| `runPreview_stale_token_guard_on_symbol_change` | 跑期间切 symbol,响应丢弃 |
| `runPreview_stale_token_guard_on_disable` | 跑期间 enabled→false,响应丢弃 |
| `runPreview_stale_response_does_not_clear_loading` | 旧 fetch 先回(symbol 已切),loading 不被错误置 false |
| `runPreview_error_sets_previewError_and_keeps_preview_null` | 5xx → previewError + preview 仍 null |
| `runPreview_can_be_called_again_to_refresh` | 两次调,后一次覆盖 preview |

### 5.3 前端 `path2_web_ui/tests/components/SidebarResultList.preview.test.ts`(新建)

| 测试 | 验证点 |
|------|--------|
| `checkbox_disabled_without_scanfile` | disabled |
| `checkbox_toggle_calls_setPreviewEnabled` | 触发 action |
| `refresh_disabled_when_not_enabled` | ↻ disabled |
| `refresh_disabled_when_no_preview` | ↻ disabled |
| `refresh_disabled_during_loading` | ↻ disabled |
| `refresh_disabled_when_symbol_mismatch` | ↻ disabled |
| `refresh_enabled_when_all_four_conditions_met` | ↻ enabled |
| `refresh_click_calls_runPreview` | 调 action |
| `loading_status_visible_during_loading` | "计算中…"灰字 |
| `error_bar_visible_and_closable` | 错误条 + 关闭叉清 previewError |

### 5.4 E2E(verification 阶段,不入测试套)

1. /scan ACRS 加载;选 ACRS 记 BO 数 N1
2. 勾复选框 → 等 < 5s → BO 数变 N1'(preview)
3. 切其他股 X → preview 瞬清 → 短暂显示 X 的扫描 → 自动 fetch X preview
4. 切回 ACRS → 同样自动 fetch
5. 取消复选框 → 立刻回到 ACRS 扫描 N1
6. 再勾选 → 重 fetch
7. 改 yaml(放宽阈值)→ 点 ↻ → 当前股重 fetch → BO 数变多
8. 改 yaml 拼错 → 点 ↻ → 错误条显示 "params.yaml ... 含未知字段"
9. 改回 yaml → ↻ → 错误条消失,新 preview

## 6. 落地文件清单

新建:
- `path2_web/scan.py`:抽 `analyze_single` 函数(共用 fn,非新文件)
- `path2_web/api.py`:加 `/preview` 路由
- `path2_web_ui/src/api.ts`:加 `getPreview`
- `path2_web_ui/src/stores/view.ts`:加 state / computed / actions
- `path2_web_ui/src/components/SidebarResultList.vue`:加 `.preview-bar`
- `tests/path2_web/test_preview.py`:后端测试
- `path2_web_ui/tests/stores/view.preview.test.ts`:store 测试
- `path2_web_ui/tests/components/SidebarResultList.preview.test.ts`:组件测试

修改:
- `path2_web/scan.py`:`_scan_ticker` 改为 `analyze_single` 薄包装
- 前端各消费者:`currentAnalysis` → `effectiveAnalysis`, `pattern` → `effectivePattern`, `windowOf(scanFile.scan)` → `windowOf(effectiveScan)`

预期回归全绿,无现有测试需要修改(除 stub fixture 跟着 schema 变 — 在 plan task 中处理)。
