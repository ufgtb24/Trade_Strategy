# Scan File Dialog Design

**日期**: 2026-06-16
**作者**: brainstorming session (user + Claude)
**Branch**: dag

## 背景与动机

`path2_web_ui` 当前在 `SidebarScanPanel.vue` 底部以 inline 列表展示扫描历史（每条只是一行时间戳，点击即加载结果文件）。需求：

1. 把「加载扫描结果文件」从 inline 列表升级为**专门的模态对话框**，参考 `BreakoutStrategy/dev/dialogs/file_dialog.py` 的 dev UI 设计（Treeview + 路径栏 + Open/Cancel 底栏）。
2. 对话框中按 **Delete 键**可删除（多选）选中的扫描结果文件，含确认弹窗（同 dev UI）。
3. 顺带：「扫描进行中」与「打开历史对话框」的交互冲突——把现有「开始扫描」按钮在扫描进行时切换为「停止扫描」，给后端补一条扫描取消机制；扫描进行时「打开历史」按钮 disabled。

dev UI 是 Tkinter 桌面工具，本 spec 在 Vue 3 + FastAPI 上做对应实现，**不引入** dev UI 的文件系统浏览能力（路径栏 / 跨目录），范围严格限定为「当前选中 pattern 的扫描历史」。

## 改动范围（总览）

四块文件 + 一处后端新增逻辑：

| 层 | 文件 | 改动 |
|---|---|---|
| 后端 | `path2_web/scan.py` | `list_scans` 返回值升级；新增 `delete_scan`；`run_scan` 接受 `cancel_event`；新增 `ScanCancelled` 异常 |
| 后端 | `path2_web/api.py` | `GET /scans/{pid}` 返回类型同步；新增 `DELETE /scans/{pid}/{ts}`；新增 `POST /scan/{scan_id}/cancel`；`ScanManager` 加 `cancel_event` 维护 + `cancel()` 方法 |
| 前端 | `path2_web_ui/src/api.ts` + `src/stores/scan.ts` + `src/stores/view.ts` + `src/types.ts` | `listScans` 签名更新；新增 `deleteScan` / `cancelScan` API；scan store 新增 `remove(ts)` / `cancel()`；view store 新增 `clearScanFile()` |
| 前端 | `path2_web_ui/src/components/SidebarScanPanel.vue` | 移除 inline `.history`；按钮 = 「开始/停止」切换；新增「打开历史…」按钮 |
| 前端 | `path2_web_ui/src/components/ScanResultDialog.vue` | **新增组件**：模态文件列表对话框 + 内嵌确认 layer |

**不做**：路径穿越加固（本地工具威胁模型≈0）、`_meta.json` 索引（dev UI 也没用、N<1000 时逐文件读 json 的 50ms 量级开销可接受）、对话框抽通用 `ConfirmDialog.vue`（YAGNI，本任务两处 confirm 各自内嵌 layer）。

## 后端契约

### `path2_web/scan.py`

#### `list_scans` 返回值升级

```python
def list_scans(pattern_id, outputs_root="outputs/path2_web") -> list[dict]:
    """返回 [{scan_ts, hits, total, size}, ...],按 scan_ts 倒序。
    单文件读 json 取 scan.hits / scan.scanned;读不出 (损坏/格式不对) → hits=total=None。"""
    d = Path(outputs_root) / pattern_id
    if not d.exists():
        return []
    rows = []
    for p in d.glob("*.json"):
        try:
            scan_section = json.loads(p.read_text())["scan"]
            hits = scan_section.get("hits")
            total = scan_section.get("scanned")
        except (json.JSONDecodeError, KeyError, OSError):
            hits = total = None
        rows.append({"scan_ts": p.stem, "hits": hits, "total": total, "size": p.stat().st_size})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows
```

**契约关键点**：
- 损坏 json 不抛异常，降级为 `hits=total=None`，UI 渲染时显示 `—`
- size 用 `p.stat().st_size`（字节）
- 排序仍按 `scan_ts` 倒序（最新在上）

#### 新增 `delete_scan`

```python
def delete_scan(pattern_id, scan_ts, outputs_root="outputs/path2_web") -> None:
    """删除单个结果文件;不存在 → FileNotFoundError(原生)。"""
    path = Path(outputs_root) / pattern_id / f"{scan_ts}.json"
    path.unlink()
```

不加路径穿越加固——前端是唯一调用方，威胁模型≈0。

#### 新增 `ScanCancelled` 异常 + `run_scan` 取消支持

```python
class ScanCancelled(Exception):
    """run_scan 检测到 cancel_event 已 set,主动退出 (用激进 terminate 杀 worker 进程)。"""

def run_scan(*, ..., cancel_event: threading.Event | None = None) -> dict:
    ...
    def _iter():
        ex = executor_factory(max(1, workers))
        try:
            futs = [ex.submit(_scan_ticker, ...) for p in pkls]
            for fut in as_completed(futs):
                if cancel_event is not None and cancel_event.is_set():
                    # 激进终止:杀所有 worker 进程立刻停 (internal API trade-off:
                    # ex._processes 多年稳定但非公开契约;ThreadPool 测试路径走 hasattr guard)
                    if hasattr(ex, "_processes"):
                        for p in list(ex._processes.values()):
                            try: p.terminate()
                            except Exception: pass    # 进程已死忽略
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise ScanCancelled()
                yield fut.result()
        finally:
            ex.shutdown(wait=False)
    ...
```

**契约关键点**：
- `cancel_event=None` 行为不变（向后兼容老调用方）
- `ScanCancelled` 由 `ScanManager.runner` 捕获 → 取消 done event
- 取消时**不写结果文件**（`write_result_file` 在 `run_scan` 末尾，异常路径不到达）
- ThreadPool 测试夹具走 `hasattr(ex, "_processes")` guard，只走 shutdown 不 terminate

### `path2_web/api.py`

#### `ScanManager` 扩展

```python
class ScanManager:
    def __init__(self):
        self._scans: dict = {}

    def start(self, loop, scan_id, job, done_meta_fn):
        cancel_event = threading.Event()
        q: asyncio.Queue = asyncio.Queue()
        self._scans[scan_id] = {"queue": q, "done": False, "last": None, "cancel": cancel_event}

        def runner():
            try:
                result = job(on_progress, cancel_event)   # job 闭包内透传给 run_scan
                done = {"type": "done", **done_meta_fn(result)}
            except scan_mod.ScanCancelled:
                done = {"type": "done", "cancelled": True, "error": None,
                        "hits": 0, "errors": 0, "total": 0}
            except Exception as e:           # noqa: BLE001
                done = {"type": "done", "error": f"{type(e).__name__}: {e}",
                        "hits": 0, "errors": 0, "total": 0}
            ...

    def cancel(self, scan_id) -> bool:
        entry = self._scans.get(scan_id)
        if entry is None or entry["done"]:
            return False
        entry["cancel"].set()
        return True
```

`post_scan` 端点内的 `job` 闭包改签名 `(on_progress, cancel_event)`，把 `cancel_event` 透传给 `run_scan`。

#### 端点签名

```python
@router.get("/scans/{pattern_id}")
def scans_list(pattern_id: str) -> list[dict]:   # 类型由 list[str] 升级
    return scan_mod.list_scans(pattern_id, outputs_root)

@router.delete("/scans/{pattern_id}/{scan_ts}")
def scan_delete(pattern_id: str, scan_ts: str):
    try:
        scan_mod.delete_scan(pattern_id, scan_ts, outputs_root)
    except FileNotFoundError:
        raise HTTPException(404, "scan not found")
    return {"ok": True}

@router.post("/scan/{scan_id}/cancel")
def scan_cancel(scan_id: str):
    if not manager.cancel(scan_id):
        raise HTTPException(404, "scan not running or unknown")
    return {"ok": True}
```

**契约破坏性变更**：`GET /scans/{pid}` 返回 `list[str]` → `list[dict]`。当前无第三方消费者，直接改。

## 前端契约

### `src/types.ts`

```ts
export interface ScanHistoryEntry {
  scan_ts: string
  hits: number | null
  total: number | null
  size: number      // bytes
}

export interface ScanDone {
  type: 'done'
  hits: number
  errors: number
  total: number
  cancelled?: boolean        // 新增:取消路径为 true
  error?: string | null
}
```

### `src/api.ts`

```ts
export function listScans(patternId: string): Promise<ScanHistoryEntry[]> {
  return getJson(`/scans/${patternId}`)
}
export function deleteScan(patternId: string, scanTs: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scans/${patternId}/${scanTs}`, {method: 'DELETE'})
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function cancelScan(scanId: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scan/${scanId}/cancel`, {method: 'POST'})
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
```

### `src/stores/scan.ts`

```ts
const history = ref<ScanHistoryEntry[]>([])      // 类型升级 string[] → ScanHistoryEntry[]
const currentScanId = ref<string | null>(null)   // 新增:用于 cancel()

async function run(req: ScanReq) {
  ...
  const id = await startScan(req)
  currentScanId.value = id
  ...
}

async function remove(patternId: string, scanTs: string) {
  // 由 ScanResultDialog 触发,对单条调用;dialog 负责循环多条 + 失败收集
  // 签名与 open/refreshHistory 一致,显式传 patternId
  await deleteScan(patternId, scanTs)
}

async function cancel(): Promise<void> {
  if (!currentScanId.value || !running.value) return
  await cancelScan(currentScanId.value)
  // 不主动改 running——等 SSE 'done' (含 cancelled=true) 进来,
  // 现有 streamScan 闭包遇到 done 会清 running.value=false
  await new Promise<void>((resolve) => {
    const stop = watch(running, (v) => { if (!v) { stop(); resolve() } })
  })
}
```

### `src/stores/view.ts`

```ts
function clearScanFile() {
  scanFile.value = null
  symbol.value = null
  roleVisible.value = {}
  selected.value = null
  selectedEventId.value = null
  hoveredEventId.value = null
  // diag 由现有 watch([symbol, scanFile, pattern]) 自动清:symbol → null 时
}
```

## 前端组件

### `SidebarScanPanel.vue`

**移除**：`.history` 块（第 15-17 行）。

**改造**：原「开始扫描」按钮在扫描中切「停止扫描」（红色）。

```vue
<template>
  <!-- 开始/停止 共享按钮位 -->
  <button :disabled="!selectedId" :class="{'btn-stop': running}" @click="onPrimary">
    {{ running ? '停止扫描' : '开始扫描' }}
  </button>

  <!-- 打开历史 (扫描中 disabled) -->
  <button :disabled="!selectedId || running" @click="dialogOpen = true">
    打开历史…
  </button>

  <!-- 现有 progress / lastDone 展示 -->
  <div v-if="progress" class="prog">...</div>
  <div v-if="lastDone" class="done">
    <template v-if="lastDone.cancelled">扫描已取消</template>
    <template v-else-if="lastDone.error">扫描失败: {{ lastDone.error }}</template>
    <template v-else>完成: 命中 {{ lastDone.hits }} / 错误 {{ lastDone.errors }}</template>
  </div>

  <ScanResultDialog
    v-if="dialogOpen && selectedId"
    :pattern-id="selectedId"
    @close="dialogOpen = false"
  />
</template>

<script setup>
const dialogOpen = ref(false)
async function onPrimary() {
  if (!selectedId.value) return
  if (running.value) await scan.cancel()
  else await onScan()    // 现有逻辑
}
</script>

<style scoped>
button.btn-stop { background: #ef4444; color: #fff; }
</style>
```

### `ScanResultDialog.vue` (新增)

**Props / Emits**

```ts
defineProps<{ patternId: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()
```

**模板结构**

```vue
<Teleport to="body">
  <div class="backdrop" @click.self="onCancel">
    <div class="card"
         @keydown.esc.stop="onCancel"
         @keydown.enter.stop="onOpen"
         @keydown.delete.stop="onDeleteKey">
      <header>
        <h3>Scan Results — {{ patternId }}</h3>
      </header>

      <div v-if="loading" class="state">Loading…</div>
      <div v-else-if="error" class="state error">
        {{ error }} <button @click="reload">Retry</button>
      </div>
      <div v-else-if="!rows.length" class="state">No scan history.</div>
      <table v-else class="file-list" tabindex="0" ref="listEl">
        <thead><tr><th>Time</th><th>Hits</th><th>Size</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="r.scan_ts"
              :class="{ active: selected.has(r.scan_ts), current: r.scan_ts === currentScanTs }"
              @click.exact="selectSingle(i)"
              @click.ctrl="toggle(i)" @click.meta="toggle(i)"
              @click.shift="extendTo(i)"
              @dblclick="openOne(r.scan_ts)">
            <td>{{ formatTs(r.scan_ts) }}</td>
            <td>{{ r.hits === null ? '—' : `${r.hits} / ${r.total}` }}</td>
            <td>{{ formatSize(r.size) }}</td>
          </tr>
        </tbody>
      </table>

      <footer>
        <span class="hint">{{ selected.size }} selected · ↑↓ / Enter / Delete / Esc</span>
        <button @click="onCancel">Cancel</button>
        <button :disabled="selected.size !== 1" @click="onOpen">Open</button>
      </footer>

      <!-- 内嵌确认 layer (删除确认) -->
      <div v-if="confirming" class="confirm-backdrop" @click.self>
        <div class="confirm-card">
          <p>{{ confirmMessage }}</p>
          <p v-if="confirmIncludesCurrent" class="warn">
            Note: includes the currently loaded scan; main view will be cleared.
          </p>
          <button @click="confirming = false">Cancel</button>
          <button class="btn-stop" @click="performDelete">Delete</button>
        </div>
      </div>
    </div>
  </div>
</Teleport>
```

**键盘交互表**

| 键 / 事件 | 行为 |
|---|---|
| `↑` / `↓` | 移动 anchor，单选 |
| `Shift+↑` / `Shift+↓` | 扩展选区 |
| `Ctrl/⌘+点击` | 切换单行选中 |
| `Shift+点击` | 范围选 |
| `Enter` | 仅在单选时 = Open |
| `Delete` | 触发确认 layer |
| `Esc` / 点 backdrop | Cancel |
| 双击行 | 直接打开该行 |

**关键 setup 逻辑**

```ts
const rows = ref<ScanHistoryEntry[]>([])
const selected = ref(new Set<string>())
const anchor = ref<number>(-1)
const loading = ref(false), error = ref<string | null>(null)
const confirming = ref(false), confirmMessage = ref(''), confirmIncludesCurrent = ref(false)

const view = useViewStore()
const scan = useScanStore()
const currentScanTs = computed(() => view.scanFile?.scan?.scan_ts ?? null)

async function reload() {
  loading.value = true; error.value = null
  try { rows.value = await listScans(props.patternId) }
  catch (e: any) { error.value = `Failed to load history: ${e.message ?? e}` }
  finally { loading.value = false }
}

onMounted(() => {
  reload()
  nextTick(() => listEl.value?.focus())
})

function onDeleteKey() {
  if (!selected.value.size) return
  const sel = Array.from(selected.value)
  confirmMessage.value = sel.length === 1
    ? `Delete ${formatTs(sel[0])}?`
    : buildMultiMessage(sel)       // 列前 3 个 + ...and K more
  confirmIncludesCurrent.value = currentScanTs.value !== null && selected.value.has(currentScanTs.value)
  confirming.value = true
}

async function performDelete() {
  const targets = Array.from(selected.value)
  const failures: string[] = []
  for (const ts of targets) {
    try { await scan.remove(props.patternId, ts) } catch { failures.push(ts) }
  }
  await scan.refreshHistory(props.patternId)
  rows.value = scan.history     // 同步
  if (currentScanTs.value !== null && targets.includes(currentScanTs.value)) {
    view.clearScanFile()
  }
  selected.value.clear()
  confirming.value = false
  if (failures.length) error.value = `Failed to delete: ${failures.join(', ')}`
}

async function onOpen() {
  if (selected.value.size !== 1) return
  const ts = Array.from(selected.value)[0]
  await scan.open(props.patternId, ts)   // 现有路径
  emit('close')
}

function openOne(ts: string) {
  scan.open(props.patternId, ts)
  emit('close')
}

function onCancel() { emit('close') }
```

**格式化辅助**

```ts
function formatTs(ts: string): string {
  // 20260615T143012 → 2026-06-15 14:30:12
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/)
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : ts
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024**2) return `${(bytes/1024).toFixed(1)} KB`
  if (bytes < 1024**3) return `${(bytes/1024/1024).toFixed(1)} MB`
  return `${(bytes/1024**3).toFixed(2)} GB`
}
```

**样式（自适应尺寸，遵 `.claude/rules/UI.md`）**

```css
.backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  min-width: 480px;
  max-width: 80vw;
  max-height: 70vh;
  display: flex; flex-direction: column;
  position: relative;
}
.file-list { overflow-y: auto; max-height: 50vh; }
.file-list tr.active { background: #eff6ff; }
.file-list tr.current { font-weight: 600; }
.confirm-backdrop {
  position: absolute; inset: 0;
  background: rgba(255,255,255,0.85);
  display: flex; align-items: center; justify-content: center;
}
.confirm-card { background: #fff; border: 1px solid #cbd5e1; padding: 16px; border-radius: 6px; }
.warn { color: #b91c1c; font-size: 12px; }
button.btn-stop { background: #ef4444; color: #fff; }
```

`max-width/max-height` 是上限，行少时 card 自然贴合内容（min-width 是下限避免太窄），多到爆才滚条。

## 数据流（端到端）

### 打开 → Open

```
User clicks 「打开历史…」 (only enabled when !running)
  → SidebarScanPanel: dialogOpen = true
  → <ScanResultDialog mounted>
  → onMounted: reload() = await listScans(patternId)
  → render rows
  → user 双击 row OR 选中 row + 点 Open
  → scan.open(pid, ts) = await loadScan() + viewStore.loadScanFile()
  → emit('close')
  → SidebarScanPanel: dialogOpen = false
  → 主视图 (KlineChart / SidebarResultList) 自动绑定新 scanFile
```

### 打开 → Delete (含当前已加载文件)

```
User selects rows (含 currentScanTs) → presses Delete
  → onDeleteKey: 计算 confirmIncludesCurrent = true
  → 内嵌 confirm layer 弹出,显示文件列表 + 红字「includes the currently loaded scan; main view will be cleared」
  → user 点 Delete
  → performDelete:
      for ts of targets: await scan.remove(ts)
      await scan.refreshHistory(pid)
      view.clearScanFile()   // scanFile=null + symbol=null + 派生状态清
  → confirm layer 关闭
  → 列表自动刷新 (rows = scan.history)
  → 用户继续操作 / 关闭对话框 / SidebarResultList 显「未加载扫描结果」
```

### 扫描中 → 用户想看历史

```
running = true → 「打开历史…」disabled,「开始扫描」按钮变红色「停止扫描」
User clicks 「停止扫描」
  → scan.cancel():
      POST /scan/{currentScanId}/cancel
      backend: cancel_event.set() → run_scan as_completed 检测点 → terminate workers + ScanCancelled
      runner catches → SSE 投 done {cancelled: true}
      frontend streamScan 收 done → running = false
      scan.cancel 内 watch(running) 解 promise → 返回
User clicks 「打开历史…」 (now enabled)
  → 正常打开对话框
```

## 错误处理与边界

| 场景 | 处理 |
|---|---|
| `selectedId` 为空 | 两个按钮 disabled |
| `GET /scans/{pid}` 失败 | 对话框内 inline `Failed to load history: <msg>` + Retry 按钮 |
| `listScans` 某条 `hits=null/total=null` | Hits 列显 `—` |
| 删除部分失败 | `performDelete` 收集 `failures`，refreshHistory 后 inline error 列失败 ts |
| 删除条目包含当前 `scanFile` | 确认 layer 追加红字提示；确认后 `view.clearScanFile()` |
| 用户狂点 Open/Delete | `loading` / `confirming` 局部 flag 期间 button disabled |
| `scan.cancel` 时扫描已自然结束 | `running` 已 false，`cancel` 早 return；POST 返 404 时前端 catch 后忽略（已无事可做）|
| 取消的扫描是否留文件 | 不留——`write_result_file` 在 `run_scan` 末尾，`ScanCancelled` 异常路径不到 |
| ThreadPool 测试夹具走 cancel 分支 | `hasattr(ex, '_processes')` guard：线程池只 shutdown 不 terminate（线程没法激进 kill）|

## 测试策略

### 后端（pytest，沿用 `tests/path2_web/`）

```
test_list_scans_returns_entries_with_hits_total_size
test_list_scans_sorted_desc_by_ts
test_list_scans_corrupt_json_returns_null_hits
test_list_scans_empty_or_missing_dir_returns_empty_list
test_delete_scan_removes_file
test_delete_scan_missing_raises_filenotfound
test_api_delete_scan_200
test_api_delete_scan_404_when_missing
test_run_scan_cancelled_raises_ScanCancelled       # 用 ThreadPool 夹具,cancel_event 在 N=10 ticker 跑到一半 set
test_scanmanager_cancel_running_scan_returns_true
test_scanmanager_cancel_unknown_or_done_returns_false
test_api_post_scan_cancel_404_when_unknown
test_cancelled_scan_writes_no_result_file
```

### 前端单测（Vitest，沿用 `path2_web_ui/tests/`）

```
scan.store: remove(pid, ts) calls deleteScan
scan.store: cancel() awaits running → false
ScanResultDialog: emits close on Esc / backdrop click / Cancel
ScanResultDialog: dblclick row triggers scan.open + close
ScanResultDialog: Delete on multi-select opens confirm layer with N count
ScanResultDialog: confirm with current ts in selection → clearScanFile called
ScanResultDialog: Open button disabled when selected.size !== 1
```

### e2e（Playwright，沿用 `path2_web_ui/e2e/`）

```
e2e/scan-dialog.spec.ts:
  1. open dialog → rows visible (列 Time/Hits/Size 都渲染)
  2. click row + Open → ChartArea 绑定该 scanFile
  3. multi-select 2 rows + Delete → confirm → 2 行消失,主视图保留
  4. select currentScanTs + Delete → confirm 出现红字提示 → 删后主视图清空
  5. Start scan → 按钮变红「停止扫描」→ click → SSE done.cancelled → 「扫描已取消」 + 「打开历史」按钮 enabled
```

## 范围外（Out of Scope）

- **`lastDone` 提示视觉权重**：当前 11px 灰色一行，本次只新增 `cancelled` 分支，不动 styling；用户感知弱的问题作为独立 followup。
- **跨目录文件浏览器**：dev UI 那种「Path: 栏 + 上下导航」语义对 web 端不适用，不引入。
- **`_meta.json` 索引**：N<1000 时逐文件读 json 开销可接受，dev UI 也未用，未来真撞瓶颈再加。
- **路径穿越加固**：本地工具威胁模型≈0，前端是唯一调用方。
- **`ConfirmDialog.vue` 通用组件抽象**：YAGNI，本任务两处 confirm 内嵌 layer 足够。

## 实现顺序建议

1. 后端 `list_scans` 升级 + 单测
2. 后端 `delete_scan` + DELETE 端点 + 单测
3. 后端 `ScanCancelled` + `run_scan(cancel_event=)` + `ScanManager.cancel` + cancel 端点 + 单测
4. 前端 `types.ts` + `api.ts` + `scan.ts` store + `view.ts` `clearScanFile`
5. 前端 `ScanResultDialog.vue` (含确认 layer) + 单测
6. 前端 `SidebarScanPanel.vue` 移除 history + 按钮切换 + 接入 dialog
7. e2e 跑通五个场景

Stage 1-3 与 4-7 之间无强耦合（前端开发可用 mock listScans），可适度并行。
