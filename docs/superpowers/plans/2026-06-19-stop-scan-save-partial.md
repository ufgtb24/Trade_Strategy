# Stop Scan: Save / Discard / Continue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** path2_web UI 点「停止扫描」时若有命中则弹 Save / Discard / Continue modal；Save 路径让后端把已聚的部分命中作为正常 scan 结果文件落盘并由前端自动加载，历史列表里这条带「未完成」标。

**Architecture:** 后端在 cancel 检测点新读一个 `save_event` —— set 时优雅 break（用已聚 result 落盘、返回正常 success result），未 set 时维持当前 `raise ScanCancelled()`。`scan` 节落盘加 `partial: bool`。前端三按钮 `StopScanDialog` 组件让用户选保存/丢弃/继续，hits=0 时不弹。保存路径走的是「成功 shape SSE done」，复用本会话已落地的「扫描结束自动加载」链路（`stores/scan.ts` done 成功分支已自动 `open()`）。

**Tech Stack:** Python 3 + FastAPI + threading.Event + ProcessPoolExecutor（后端）/ Vue 3 + Pinia + Vitest + vue-tsc（前端）。

## Global Constraints

- 包管理后端 `uv`、前端 `npm`；任何后端测试用 `uv run pytest`、前端用 `npm run test -- --run`。
- 三绿门槛：每个 task 完成时该层全套测试通过。后端 `uv run pytest tests/path2_web -q`；前端 `npm run test -- --run`、`npx vue-tsc --noEmit`、`npm run build`。
- 文件路径以仓库根 `/home/yu/PycharmProjects/Trade_Strategy` 为基准，命令在该目录下执行。
- 前端语言：界面英文 / 注释中文（与现有代码一致）。
- 保留本会话刚改的 `stores/scan.ts` done 成功分支自动 `open(pattern_id, scan_ts)` 逻辑 —— save 路径走的是 success shape done，正是这条 auto-load 路径，**不要回退或绕开**。
- 三按钮 modal 的关闭语义：Esc / 点 backdrop 外侧 **无效**（不响应），只有点保存/丢弃/继续之一才关。
- 文案：modal 标题或正文「当前已经命中 {{hits}}，是否保存？」；按钮固定写「保存」「丢弃」「继续扫描」（按钮里**不**含数字）。
- 后端 `partial: bool` 字段始终写入新文件 scan 节；读取/历史列表对**旧文件**用 `.get("partial", False)` 兜底（避免旧 JSON 迁移）。
- 不改 SSE 协议除新增可选 `partial?: bool` 字段（success shape done）；cancelled shape done 不带 partial。
- 不动 ScanResultDialog 的删除流程、不改 `view.loadScanFile` 的注入逻辑、不动 `_aggregate` 实现。

---

## File Structure

**Backend (Python)：**
- Modify: `path2_web/scan.py` — `run_scan` 增 `save_event` 参数 + cancel+save 路径 break + 落盘 `partial`；`list_scans` 返回 entry 加 `partial`。
- Modify: `path2_web/api.py` — `ScanManager.start` 创建并存 `save_event` 注入 job；`ScanManager.cancel(scan_id, save:bool)`；POST `/scan/{id}/cancel?save=true|false`；`done_meta` 透传 `partial`。
- Modify: `tests/path2_web/test_scan.py` — 增 save 路径 RED-GREEN 测试（cancel+save → 不抛、文件落盘、scan.partial=True、result.scan.hits=已聚 hits）；调整 list_scans 测试断言 `partial` 字段。
- Modify: `tests/path2_web/test_api.py` — 增 POST cancel?save=true → done shape 含 pattern_id/scan_ts/partial=true 的测试。

**Frontend (Vue/TS)：**
- Modify: `path2_web_ui/src/types.ts` — `ScanDone.partial?: boolean`；`ScanHistoryEntry.partial: boolean`。
- Modify: `path2_web_ui/src/api.ts` — `cancelScan(scanId, save?: boolean)` 加 `?save=...` query。
- Modify: `path2_web_ui/src/stores/scan.ts` — `cancel(save: boolean)` 签名（替换原 `cancel()`）；done 分支不变。
- Create: `path2_web_ui/src/components/StopScanDialog.vue` — Props `{ hits }`；emits `save | discard | continue`；Esc/外面点击不关；三按钮。
- Modify: `path2_web_ui/src/components/SidebarScanPanel.vue` — `onPrimary` 三分支；`running` watcher 关 dialog；嵌入 `StopScanDialog`。
- Modify: `path2_web_ui/src/components/ScanResultDialog.vue` — 行末当 `r.partial` 显示「未完成」小标。
- Modify: `path2_web_ui/tests/stores.spec.ts` — 既有 `cancel no-op` 用例改用 `cancel(false)`；新增 `cancel(true)` / `cancel(false)` 各调通 `cancelScan` 带正确 save 参数。
- Create: `path2_web_ui/tests/components/StopScanDialog.spec.ts` — 三按钮 emit + Esc/backdrop 不响应 + hits 显示。
- Modify: `path2_web_ui/tests/components/SidebarScanPanel.spec.ts` — 增三分支测试（hits=0 直 cancel/false；hits>0 弹 dialog；running 变 false 关 dialog）。
- Modify: `path2_web_ui/tests/components/ScanResultDialog.spec.ts` — 行展示 partial badge 的断言。

---

## Task 1: Backend — `run_scan` save 路径 + `list_scans` partial 字段

**Files:**
- Modify: `path2_web/scan.py` (run_scan 签名 + cancel 检测点；list_scans 返回字段)
- Test: `tests/path2_web/test_scan.py` (新增 + 部分既有用例的断言扩展)

**Interfaces:**
- Consumes: 无（首 task）
- Produces:
  - `scan.run_scan(..., cancel_event=None, save_event=None)`：当 `cancel_event` set 时检查 `save_event`：set → break 优雅退出（用已聚 result 落盘 + 返回正常 result，`result["scan"]["partial"]=True`）；未 set → 保持现有 `raise ScanCancelled()`。
  - `scan.list_scans(pattern_id, outputs_root) -> list[dict]` 每 entry 新增 `partial: bool` 字段（旧文件读不出 partial 时缺省 False）。

### Steps

- [ ] **Step 1.1: 写新 RED 测试 — save 路径**

往 `tests/path2_web/test_scan.py` 文件尾追加：

```python
def test_run_scan_cancel_with_save_returns_partial_and_writes_file(tmp_path):
    """cancel_event 与 save_event 都 set → run_scan 不抛、用已聚 result 落盘、scan.partial=True。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    for i in range(5):
        _write_pkl(data_dir, f"X{i}", _mk_dated(_synth_no_burst()))
    out_dir = tmp_path / "outputs"
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    cancel_event = threading.Event()
    save_event = threading.Event()
    cancel_event.set()
    save_event.set()
    # 不抛
    result = scan.run_scan(
        data_dir=str(data_dir),
        module_path=reg.module_path("bottom_breakout_burst"),
        pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
        pattern_id="bottom_breakout_burst",
        start_date="2025-01-01", end_date="2025-12-31",
        workers=2, ticker_regex=None, scan_ts="20260619T120000",
        outputs_root=str(out_dir),
        on_progress=lambda *a: None,
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        cancel_event=cancel_event,
        save_event=save_event,
    )
    # 落盘
    files = list((out_dir / "bottom_breakout_burst").glob("*.json"))
    assert len(files) == 1
    # scan 节带 partial=True
    assert result["scan"]["partial"] is True
    saved = json.loads(files[0].read_text())
    assert saved["scan"]["partial"] is True


def test_run_scan_cancel_without_save_still_raises_and_no_file(tmp_path):
    """cancel_event set 但 save_event 未 set → 维持现状(抛 ScanCancelled、不落盘)。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _write_pkl(data_dir, "X1", _mk_dated(_synth_no_burst()))
    out_dir = tmp_path / "outputs"
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    cancel_event = threading.Event()
    save_event = threading.Event()                # 故意不 set
    cancel_event.set()
    with pytest.raises(scan.ScanCancelled):
        scan.run_scan(
            data_dir=str(data_dir),
            module_path=reg.module_path("bottom_breakout_burst"),
            pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
            pattern_id="bottom_breakout_burst",
            start_date="2025-01-01", end_date="2025-12-31",
            workers=1, ticker_regex=None, scan_ts="20260619T120001",
            outputs_root=str(out_dir),
            on_progress=lambda *a: None,
            executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
            cancel_event=cancel_event,
            save_event=save_event,
        )
    assert not (out_dir / "bottom_breakout_burst").exists() or \
        not list((out_dir / "bottom_breakout_burst").glob("*.json"))
```

注：文件顶部已 `import json`、`import threading`、`import pytest`、`from concurrent.futures import ThreadPoolExecutor`、`from path2_web import scan`、`_write_pkl`、`_mk_dated` —— 如缺则补。

- [ ] **Step 1.2: 跑 RED**

运行：`uv run pytest tests/path2_web/test_scan.py::test_run_scan_cancel_with_save_returns_partial_and_writes_file tests/path2_web/test_scan.py::test_run_scan_cancel_without_save_still_raises_and_no_file -v`
预期：第一个 FAIL（`save_event` 未被识别 / partial 字段缺失），第二个 PASS（既有行为）。

- [ ] **Step 1.3: 改 `run_scan` —— 加 `save_event` 参数与 break 路径**

在 `path2_web/scan.py` 的 `run_scan` 签名末尾追加 `save_event=None`，cancel 检测点改为先 break / 后 raise，循环结束后用 `save_event.is_set()` 标 partial：

```python
def run_scan(*, data_dir, module_path, pattern_spec_json, pattern_id,
             start_date, end_date, workers, ticker_regex, scan_ts,
             end_role=None, head_buffer_trading_days=None, label_horizon=None,
             outputs_root="outputs/path2_web", on_progress=lambda *a: None,
             executor_factory=None, cancel_event=None, save_event=None) -> dict:
    ...
    def _iter():
        ex = executor_factory(max(1, workers))
        try:
            futs = [ex.submit(_scan_ticker, str(p), module_path, start_date, end_date,
                              win_start if buffered else None, win_end if buffered else None,
                              end_role, label_horizon) for p in pkls]
            for fut in as_completed(futs):
                if cancel_event is not None and cancel_event.is_set():
                    if hasattr(ex, "_processes"):
                        for proc in list(ex._processes.values()):
                            try:
                                proc.terminate()
                            except Exception:        # noqa: BLE001  已死忽略
                                pass
                    ex.shutdown(wait=False, cancel_futures=True)
                    if save_event is not None and save_event.is_set():
                        break                       # 优雅退出,_aggregate 拿现有结果
                    raise ScanCancelled()           # 老行为
                yield fut.result()
        finally:
            ex.shutdown(wait=False)

    agg = _aggregate(_iter(), total, on_progress)
    partial = save_event is not None and save_event.is_set()
    result = {
        "pattern_id": pattern_id,
        "pattern_spec": pattern_spec_json,
        "scan": {
            "scan_ts": scan_ts, "start_date": str(start_date), "end_date": str(end_date),
            "workers": workers, "scanned": agg["scanned"], "hits": agg["hits"],
            "errors": agg["errors"], "dataset_dir": str(data_dir), "params": "default",
            "win_start": win_start, "win_end": win_end,
            "label_horizon": label_horizon if buffered else None, "end_role": end_role,
            "partial": partial,
        },
        "results": agg["results"],
    }
    write_result_file(result, pattern_id, scan_ts, outputs_root)
    return result
```

- [ ] **Step 1.4: 跑两条新测试 + 既有 cancel 测试 GREEN**

运行：`uv run pytest tests/path2_web/test_scan.py -v`
预期：所有用例 PASS（既有 `test_run_scan_cancelled_raises_and_writes_no_file` 与 `test_run_scan_cancel_event_none_keeps_old_behavior` 维持绿色——前者不传 save_event 等价 None；后者既不传 cancel_event 也不传 save_event）。

- [ ] **Step 1.5: 改 `list_scans` —— 返回 partial 字段**

在 `path2_web/scan.py` 的 `list_scans` 改为：

```python
def list_scans(pattern_id: str, outputs_root: str = "outputs/path2_web") -> list[dict]:
    """[{scan_ts, hits, total, size, partial}, ...],按 scan_ts 倒序。
    单文件读 json 取 scan.hits / scan.scanned / scan.partial;读不出 → hits=total=None, partial=False。"""
    d = Path(outputs_root) / pattern_id
    if not d.exists():
        return []
    rows = []
    for p in d.glob("*.json"):
        try:
            scan_section = json.loads(p.read_text())["scan"]
            hits = scan_section.get("hits")
            total = scan_section.get("scanned")
            partial = bool(scan_section.get("partial", False))
        except (json.JSONDecodeError, KeyError, OSError):
            hits = total = None
            partial = False
        rows.append({"scan_ts": p.stem, "hits": hits, "total": total,
                     "size": p.stat().st_size, "partial": partial})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows
```

- [ ] **Step 1.6: 扩展既有 list_scans 测试 + 新增 partial entry 测试**

打开 `tests/path2_web/test_scan.py` 找到 `test_list_scans_returns_entries_with_hits_total_size`（约第 90 行起），在断言里**追加** `assert all("partial" in r and r["partial"] is False for r in rows)`（旧 fixture 文件没 partial 字段，期望 False）；并往文件尾新增：

```python
def test_list_scans_exposes_partial_field_for_partial_files(tmp_path):
    """落盘 scan.partial=True 的文件 → list_scans 返回该 entry partial=True;旧文件无 partial → False。"""
    d = tmp_path / "X"
    d.mkdir(parents=True)
    (d / "20260619T100000.json").write_text(json.dumps({
        "scan": {"hits": 3, "scanned": 5, "partial": True},
    }))
    (d / "20260619T100100.json").write_text(json.dumps({
        "scan": {"hits": 9, "scanned": 9},                      # 老文件无 partial 字段
    }))
    rows = scan.list_scans("X", outputs_root=str(tmp_path))
    by_ts = {r["scan_ts"]: r for r in rows}
    assert by_ts["20260619T100000"]["partial"] is True
    assert by_ts["20260619T100100"]["partial"] is False
```

- [ ] **Step 1.7: 跑 list_scans 测试 GREEN**

运行：`uv run pytest tests/path2_web/test_scan.py -v`
预期：全 PASS。

- [ ] **Step 1.8: 跑后端整套 path2_web 测试三绿**

运行：`uv run pytest tests/path2_web -q`
预期：所有用例 PASS（含 test_api / test_scan_buffered / test_diagnose 等）。如有失败请定位非 test_scan.py 的回归并解决（不应该有：本 task 只动 `scan.py` 内部 cancel 路径 + list_scans 字段，对其他模块无影响）。

- [ ] **Step 1.9: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web/scan.py tests/path2_web/test_scan.py
git commit -m "path2_web/scan: save_event 路径 + partial 字段 (RED→GREEN)"
```

---

## Task 2: Backend — `ScanManager.cancel(save)` + cancel endpoint query param

**Files:**
- Modify: `path2_web/api.py` (ScanManager.start / cancel；POST endpoint；done_meta)
- Test: `tests/path2_web/test_api.py` (新增 cancel?save 路径)

**Interfaces:**
- Consumes: `scan.run_scan(..., save_event=...)`（Task 1 已实现）。
- Produces:
  - `ScanManager.cancel(scan_id, save: bool) -> bool`：set cancel_event（动作不变）；save=True 时同时 set save_event。
  - POST `/scan/{scan_id}/cancel?save=true|false`：缺省 save=false。
  - SSE done 成功 shape 多带 `partial: bool`（透传自 `result["scan"]["partial"]`）。

### Steps

- [ ] **Step 2.1: 写 RED 测试 — cancel?save=true 路径**

先看一下 `tests/path2_web/test_api.py` 现有 fixture 风格（TestClient + thread pool + 小数据集），仿写。在文件尾追加：

```python
def test_post_cancel_with_save_writes_partial_file_and_done_includes_partial(tmp_path, client):
    """POST /scan?... 起扫 → 立刻 POST /scan/{id}/cancel?save=true → SSE done partial=true,
    且 outputs 目录下能拿到对应 scan_ts 的 partial JSON。"""
    # client fixture 必须用 use_thread_pool=True、tmp outputs_root,且数据集足够多让 cancel 能切到
    # 已存在的其他 cancel 测试是参考样板。
    # 启扫
    r = client.post("/scan", json={
        "pattern_id": "bottom_breakout_burst",
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "workers": 1, "ticker_regex": None, "label_horizon": 20,
    })
    assert r.ok
    scan_id = r.json()["scan_id"]
    # 即刻 cancel?save=true(竞态:数据集小到几乎可同步检测,worker 还没全聚也行 —— hits 可能 0,
    # 这里只验 partial 落盘与 done 形状,hits 可 0 可非 0)
    rc = client.post(f"/scan/{scan_id}/cancel?save=true")
    assert rc.ok
    # 消费 SSE 直到 done
    done = _consume_sse_done(client, scan_id)         # 既有 helper(若无则按本测试文件其他用例样式实现一个)
    assert done["type"] == "done"
    assert done.get("partial") is True
    assert done.get("pattern_id") == "bottom_breakout_burst"
    assert "scan_ts" in done
    # 文件落盘且带 partial
    out = Path(tmp_path) / "bottom_breakout_burst" / f"{done['scan_ts']}.json"
    assert out.exists()
    saved = json.loads(out.read_text())
    assert saved["scan"]["partial"] is True


def test_post_cancel_with_save_false_keeps_legacy_cancelled_shape(client):
    """save=false(或缺省)→ 维持 cancelled shape done、不落盘(既有行为)。"""
    r = client.post("/scan", json={
        "pattern_id": "bottom_breakout_burst",
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "workers": 1, "ticker_regex": None, "label_horizon": 20,
    })
    scan_id = r.json()["scan_id"]
    rc = client.post(f"/scan/{scan_id}/cancel?save=false")
    assert rc.ok
    done = _consume_sse_done(client, scan_id)
    assert done["type"] == "done"
    assert done.get("cancelled") is True
    assert done.get("partial") in (None, False)        # 不带 partial / 或显式 false 任一可接受
```

注：`_consume_sse_done` / `client` fixture 应当在该测试文件已存在（用于现有 `test_post_cancel_*` 类似用例）；若文件里命名不同，改成对应 helper 即可。先读 `tests/path2_web/test_api.py` 顶部 fixture 部分确认实际名称再写。

- [ ] **Step 2.2: 跑 RED**

运行：`uv run pytest tests/path2_web/test_api.py::test_post_cancel_with_save_writes_partial_file_and_done_includes_partial tests/path2_web/test_api.py::test_post_cancel_with_save_false_keeps_legacy_cancelled_shape -v`
预期：第一个 FAIL（save query 未被接受 / done 不带 partial）；第二个可能 PASS（既有行为）。

- [ ] **Step 2.3: 改 `ScanManager.start` —— 创建并存 save_event**

```python
def start(self, loop, scan_id, job, done_meta_fn):
    q: asyncio.Queue = asyncio.Queue()
    cancel_event = threading.Event()
    save_event = threading.Event()
    self._scans[scan_id] = {"queue": q, "done": False, "last": None,
                            "cancel": cancel_event, "save": save_event}

    def on_progress(scanned, total, hits, errors):
        evt = {"scanned": scanned, "total": total, "hits": hits, "errors": errors}
        self._scans[scan_id]["last"] = evt
        loop.call_soon_threadsafe(q.put_nowait, evt)

    def runner():
        try:
            result = job(on_progress, cancel_event, save_event)
            done = {"type": "done", **done_meta_fn(result)}
        except scan_mod.ScanCancelled:
            done = {"type": "done", "cancelled": True, "error": None,
                    "hits": 0, "errors": 0, "total": 0}
        except Exception as e:           # noqa: BLE001
            done = {"type": "done", "error": f"{type(e).__name__}: {e}",
                    "hits": 0, "errors": 0, "total": 0}
        self._scans[scan_id]["last"] = done
        self._scans[scan_id]["done"] = True
        loop.call_soon_threadsafe(q.put_nowait, done)

    loop.run_in_executor(None, runner)
```

- [ ] **Step 2.4: 改 `ScanManager.cancel` —— 接收 save 参数**

```python
def cancel(self, scan_id, save: bool = False) -> bool:
    """set cancel_event;save=True 时同时 set save_event,run_scan 检测点会优雅退出并落盘。
    scan_id 已知返 True(幂等);scan_id 未知返 False。"""
    entry = self._scans.get(scan_id)
    if entry is None:
        return False
    if save:
        entry["save"].set()
    entry["cancel"].set()
    return True
```

- [ ] **Step 2.5: 改 cancel endpoint —— 读 query**

```python
@router.post("/scan/{scan_id}/cancel")
def scan_cancel(scan_id: str, save: bool = False):
    if not manager.cancel(scan_id, save=save):
        raise HTTPException(404, "scan not running or unknown")
    return {"ok": True}
```

- [ ] **Step 2.6: 改 `post_scan` 内的 `job` 与 `done_meta` —— 接 save_event + 透传 partial**

```python
def job(on_progress, cancel_event, save_event):
    return scan_mod.run_scan(
        ...
        cancel_event=cancel_event,
        save_event=save_event,
    )

def done_meta(result):
    s = result["scan"]
    return {"pattern_id": req.pattern_id, "scan_ts": scan_ts,
            "hits": s["hits"], "errors": s["errors"], "total": s["scanned"],
            "partial": bool(s.get("partial", False))}
```

- [ ] **Step 2.7: 跑 RED→GREEN + 整套 path2_web 测试**

运行：`uv run pytest tests/path2_web -q`
预期：所有 PASS（含本 task 新增两条、既有 cancel 路径用例、Task 1 用例）。如 fixture 名称对不上，按真实 helper 名调整测试代码再跑。

- [ ] **Step 2.8: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web/api.py tests/path2_web/test_api.py
git commit -m "path2_web/api: cancel(save) endpoint + ScanManager 接 save_event"
```

---

## Task 3: Frontend — `cancelScan(save)` 链路 + 类型 + store cancel(save)

**Files:**
- Modify: `path2_web_ui/src/types.ts` (ScanDone.partial / ScanHistoryEntry.partial)
- Modify: `path2_web_ui/src/api.ts` (cancelScan 加 save 参数)
- Modify: `path2_web_ui/src/stores/scan.ts` (cancel(save:boolean))
- Test: `path2_web_ui/tests/stores.spec.ts` (既有 cancel no-op 调用签名更新 + 新增 save=true / save=false 透传断言)

**Interfaces:**
- Consumes: 后端 cancel?save query（Task 2）+ 后端 list scans 返回 partial 字段（Task 1）。
- Produces:
  - `api.cancelScan(scanId: string, save?: boolean): Promise<{ok:true}>`
  - `scan.cancel(save: boolean): Promise<void>`（替换原 `cancel()`，签名变了）
  - `ScanDone.partial?: boolean`
  - `ScanHistoryEntry.partial: boolean`

### Steps

- [ ] **Step 3.1: 改 types.ts**

打开 `path2_web_ui/src/types.ts`，找 `ScanDone` 与 `ScanHistoryEntry`，分别加：

```ts
export interface ScanDone {
  type: 'done'; hits: number; errors: number; total: number
  pattern_id?: string; scan_ts?: string; error?: string | null
  cancelled?: boolean
  partial?: boolean              // ★ save 路径下后端透传
}

export interface ScanHistoryEntry {
  scan_ts: string
  hits: number | null
  total: number | null
  size: number
  partial: boolean               // ★ Task 1 后端总返回(旧文件 → false)
}
```

- [ ] **Step 3.2: 改 api.ts**

```ts
export function cancelScan(scanId: string, save: boolean = false): Promise<{ok: true}> {
  return fetch(`${BASE}/scan/${scanId}/cancel?save=${save}`, { method: 'POST' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
```

- [ ] **Step 3.3: 改 stores/scan.ts cancel 签名**

把现有：

```ts
async function cancel(): Promise<void> {
  if (!currentScanId.value || !running.value || cancelling.value) return
  cancelling.value = true
  try {
    await cancelScan(currentScanId.value)
    await new Promise<void>((resolve) => {
      const stop = watch(running, (v) => { if (!v) { stop(); resolve() } })
    })
  } finally {
    cancelling.value = false
  }
}
```

改为：

```ts
async function cancel(save: boolean): Promise<void> {
  if (!currentScanId.value || !running.value || cancelling.value) return
  cancelling.value = true
  try {
    await cancelScan(currentScanId.value, save)
    await new Promise<void>((resolve) => {
      const stop = watch(running, (v) => { if (!v) { stop(); resolve() } })
    })
  } finally {
    cancelling.value = false
  }
}
```

- [ ] **Step 3.4: 修复既有 stores.spec.ts cancel no-op 测试调用**

打开 `path2_web_ui/tests/stores.spec.ts`，找到：

```ts
it('cancel no-op when not running', async () => {
  ...
  await s.cancel()
  expect(cancelScan).not.toHaveBeenCalled()
})
```

把 `await s.cancel()` 改为 `await s.cancel(false)`。

- [ ] **Step 3.5: 新增 cancel(save) 透传单测**

在 `stores.spec.ts` 的 `describe('scan store remove + cancel', ...)` 内新增：

```ts
it('cancel(true) calls cancelScan(scan_id, true) when running', async () => {
  const { cancelScan, startScan, streamScan } = await import('../src/api')
  vi.mocked(startScan).mockResolvedValueOnce('scan_id_x')
  vi.mocked(streamScan).mockImplementationOnce(() => ({ close: () => {} } as any))
  vi.mocked(cancelScan).mockResolvedValueOnce({ok: true})
  const s = useScanStore()
  await s.run({ pattern_id: 'pat_x', start_date: '2025-01-01', end_date: '2025-12-31',
                workers: 1, ticker_regex: null, label_horizon: 20 })
  // 模拟扫描 running 立刻被 cancel(true) 触发后 done 让 watcher 退出
  setTimeout(() => { s.$patch({ running: false }) }, 0)
  await s.cancel(true)
  expect(cancelScan).toHaveBeenCalledWith('scan_id_x', true)
})

it('cancel(false) calls cancelScan(scan_id, false) when running', async () => {
  const { cancelScan, startScan, streamScan } = await import('../src/api')
  vi.mocked(startScan).mockResolvedValueOnce('scan_id_y')
  vi.mocked(streamScan).mockImplementationOnce(() => ({ close: () => {} } as any))
  vi.mocked(cancelScan).mockResolvedValueOnce({ok: true})
  const s = useScanStore()
  await s.run({ pattern_id: 'pat_y', start_date: '2025-01-01', end_date: '2025-12-31',
                workers: 1, ticker_regex: null, label_horizon: 20 })
  setTimeout(() => { s.$patch({ running: false }) }, 0)
  await s.cancel(false)
  expect(cancelScan).toHaveBeenCalledWith('scan_id_y', false)
})
```

注：这两个用例放在 `describe('scan store remove + cancel', () => { beforeEach(() => setActivePinia(createPinia())) ... })` 内。若 `$patch({ running: false })` 触发 watch 在 vitest 下有时机问题，改为：

```ts
const s = useScanStore()
;(s as any).running = true            // 直接 setup ref(此 store 用 setup 风格,Pinia ref 暴露在 store 上)
;(s as any).currentScanId = 'scan_id_x'
setTimeout(() => { (s as any).running = false }, 0)
await s.cancel(true)
expect(cancelScan).toHaveBeenCalledWith('scan_id_x', true)
```

（pinia setup-style store 的 ref 直接可写。两种写法都跑 vitest 验证哪种通过即可。）

- [ ] **Step 3.6: 跑前端单测 + 类型 + build 三绿**

运行：
```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm run test -- --run
npx vue-tsc --noEmit
npm run build
```
预期：全绿。注意本 task 改了 `cancel()` 签名为 `cancel(save)` —— 若 `SidebarScanPanel.vue` 里既有 `scan.cancel()` 调用，会**编译报错**。这是预期：把 `SidebarScanPanel.vue` 既有那处 `await scan.cancel()` 临时改为 `await scan.cancel(false)`（语义等价旧行为，作为 Task 5 真正接线前的桥梁）。

- [ ] **Step 3.7: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/types.ts path2_web_ui/src/api.ts path2_web_ui/src/stores/scan.ts path2_web_ui/src/components/SidebarScanPanel.vue path2_web_ui/tests/stores.spec.ts
git commit -m "path2_web_ui: cancelScan(save) 链路 + ScanDone/Entry.partial 类型"
```

---

## Task 4: Frontend — `StopScanDialog.vue` 新组件

**Files:**
- Create: `path2_web_ui/src/components/StopScanDialog.vue`
- Test: `path2_web_ui/tests/components/StopScanDialog.spec.ts`

**Interfaces:**
- Consumes: 无后端依赖。
- Produces:
  - Component `StopScanDialog`
  - Props: `{ hits: number }`（reactive，父组件直接传 `progress.hits`）
  - Emits: `save`、`discard`、`continue`
  - Esc / 点 backdrop 外面：无效，dialog 不消失。
  - 文案：「当前已经命中 {{ hits }}，是否保存？」三按钮「保存」「丢弃」「继续扫描」。

### Steps

- [ ] **Step 4.1: 写 RED 测试**

新建 `path2_web_ui/tests/components/StopScanDialog.spec.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StopScanDialog from '../../src/components/StopScanDialog.vue'

describe('StopScanDialog', () => {
  it('renders hits in prompt', () => {
    const w = mount(StopScanDialog, { props: { hits: 7 } })
    expect(w.text()).toContain('7')
    expect(w.text()).toContain('当前已经命中')
  })

  it('emits save on save button', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 } })
    await w.get('[data-testid="btn-save"]').trigger('click')
    expect(w.emitted('save')).toHaveLength(1)
  })

  it('emits discard on discard button', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 } })
    await w.get('[data-testid="btn-discard"]').trigger('click')
    expect(w.emitted('discard')).toHaveLength(1)
  })

  it('emits continue on continue button', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 } })
    await w.get('[data-testid="btn-continue"]').trigger('click')
    expect(w.emitted('continue')).toHaveLength(1)
  })

  it('Esc keydown does not emit anything (ignored)', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 }, attachTo: document.body })
    await w.find('.card').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('save')).toBeUndefined()
    expect(w.emitted('discard')).toBeUndefined()
    expect(w.emitted('continue')).toBeUndefined()
    w.unmount()
  })

  it('clicking backdrop does not emit anything (ignored)', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 } })
    await w.get('.backdrop').trigger('click')              // self trigger,实现里不应 emit
    expect(w.emitted('save')).toBeUndefined()
    expect(w.emitted('discard')).toBeUndefined()
    expect(w.emitted('continue')).toBeUndefined()
  })

  it('hits prop updates reactively', async () => {
    const w = mount(StopScanDialog, { props: { hits: 3 } })
    expect(w.text()).toContain('3')
    await w.setProps({ hits: 9 })
    expect(w.text()).toContain('9')
  })
})
```

- [ ] **Step 4.2: 跑 RED**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm run test -- --run tests/components/StopScanDialog.spec.ts
```
预期：FAIL（组件未实现）。

- [ ] **Step 4.3: 实现 `StopScanDialog.vue`**

新建 `path2_web_ui/src/components/StopScanDialog.vue`：

```vue
<template>
  <div class="backdrop">
    <div class="card" tabindex="-1">
      <p class="prompt">当前已经命中 {{ hits }},是否保存?</p>
      <footer>
        <button data-testid="btn-save"     @click="$emit('save')">保存</button>
        <button data-testid="btn-discard"  @click="$emit('discard')">丢弃</button>
        <button data-testid="btn-continue" @click="$emit('continue')">继续扫描</button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
// 三按钮中途停止对话框:hits 由父组件绑定 reactive progress.hits,扫描期间会跟着涨。
// Esc / 点 backdrop 外侧不响应——用户必须显式选保存/丢弃/继续才能离开。
defineProps<{ hits: number }>()
defineEmits<{ (e: 'save'): void; (e: 'discard'): void; (e: 'continue'): void }>()
</script>

<style scoped>
.backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;                       /* 高于 ScanResultDialog 的 1000 */
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  min-width: 320px;
  max-width: 480px;
  outline: none;
}
.prompt { margin: 0 0 16px; font-size: 14px; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
button { padding: 6px 14px; font-size: 13px; cursor: pointer; }
button[data-testid="btn-save"]    { background: #2563eb; color: #fff; border: none; border-radius: 4px; }
button[data-testid="btn-discard"] { background: #ef4444; color: #fff; border: none; border-radius: 4px; }
button[data-testid="btn-continue"]{ background: #fff;    color: #1f2937; border: 1px solid #cbd5e1; border-radius: 4px; }
</style>
```

- [ ] **Step 4.4: 跑组件单测 GREEN**

```bash
npm run test -- --run tests/components/StopScanDialog.spec.ts
```
预期：全 PASS。

- [ ] **Step 4.5: 整套测试 + 类型 + build 三绿**

```bash
npm run test -- --run
npx vue-tsc --noEmit
npm run build
```
预期：全绿。

- [ ] **Step 4.6: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/StopScanDialog.vue path2_web_ui/tests/components/StopScanDialog.spec.ts
git commit -m "path2_web_ui: StopScanDialog 三按钮组件 (保存/丢弃/继续)"
```

---

## Task 5: Frontend — `SidebarScanPanel` onPrimary 三分支 + dialog 接线

**Files:**
- Modify: `path2_web_ui/src/components/SidebarScanPanel.vue`
- Test: `path2_web_ui/tests/components/SidebarScanPanel.spec.ts`

**Interfaces:**
- Consumes: `scan.cancel(save)` (Task 3)；`StopScanDialog` 组件 (Task 4)。
- Produces: 「停止扫描」点击三分支：
  1. `running && progress.hits === 0` → 立刻 `scan.cancel(false)`（无 dialog）。
  2. `running && progress.hits > 0` → 打开 `StopScanDialog`，根据用户三选分别 `scan.cancel(true)` / `scan.cancel(false)` / 关 dialog。
  3. `!running` → `onScan()`（既有起扫逻辑）。
- watch `running`：若 dialog 开着且 `running` 变 false（扫描自然完成）→ 自动关 dialog。

### Steps

- [ ] **Step 5.1: 读现有 SidebarScanPanel.spec.ts 测试风格**

```bash
cat path2_web_ui/tests/components/SidebarScanPanel.spec.ts
```
保持沿用现有 mount + stub store 的风格。

- [ ] **Step 5.2: 写 RED 测试**

往 `tests/components/SidebarScanPanel.spec.ts` 文件尾追加：

```ts
import StopScanDialog from '../../src/components/StopScanDialog.vue'

describe('SidebarScanPanel onPrimary 三分支', () => {
  beforeEach(() => setActivePinia(createPinia()))
  // ↑ 若文件顶部已有 setActivePinia 全局 beforeEach 可省

  it('hits=0 时点停止 → 直接 cancel(false),不弹 dialog', async () => {
    const scan = useScanStore()
    // 模拟 running + progress.hits=0(setup-style store: ref 可直接赋值)
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 0, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValueOnce()
    const w = mount(SidebarScanPanel, { /* ...patterns store fixture... */ })
    await w.get('button.btn-stop').trigger('click')      // 或 :class .btn-stop
    expect(cancelSpy).toHaveBeenCalledWith(false)
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('hits>0 时点停止 → 弹 StopScanDialog,不立刻调 cancel', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValueOnce()
    const w = mount(SidebarScanPanel, { /* fixture */ })
    await w.get('button.btn-stop').trigger('click')
    expect(cancelSpy).not.toHaveBeenCalled()
    expect(w.findComponent(StopScanDialog).exists()).toBe(true)
  })

  it('dialog emit save → cancel(true) + 关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValueOnce()
    const w = mount(SidebarScanPanel, { /* fixture */ })
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('save')
    expect(cancelSpy).toHaveBeenCalledWith(true)
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog emit discard → cancel(false) + 关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValueOnce()
    const w = mount(SidebarScanPanel, { /* fixture */ })
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('discard')
    expect(cancelSpy).toHaveBeenCalledWith(false)
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog emit continue → 关 dialog,不调 cancel', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValueOnce()
    const w = mount(SidebarScanPanel, { /* fixture */ })
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('continue')
    expect(cancelSpy).not.toHaveBeenCalled()
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog 开着时 running 变 false → 自动关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const w = mount(SidebarScanPanel, { /* fixture */ })
    await w.get('button.btn-stop').trigger('click')
    expect(w.findComponent(StopScanDialog).exists()).toBe(true)
    ;(scan as any).running = false
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })
})
```

`/* fixture */` 部分按既有 `SidebarScanPanel.spec.ts` 顶部用例的 mount 调用复制（含 selectedId 必备的 patterns store stub、cfg store mock）。

- [ ] **Step 5.3: 跑 RED**

```bash
npm run test -- --run tests/components/SidebarScanPanel.spec.ts
```
预期：FAIL（三分支与 dialog 联动均未实现，cancel 都还是直接调用）。

- [ ] **Step 5.4: 实现 `SidebarScanPanel.vue` 新逻辑**

```vue
<template>
  <div class="panel">
    <label>区间</label>
    <input v-model="start" /> ~ <input v-model="end" />
    <label>workers</label>
    <input v-model.number="workers" type="number" min="1" />
    <label>label horizon (days)</label>
    <input v-model.number="labelHorizon" type="number" min="1" />

    <button
      :disabled="!selectedId"
      :class="{ 'btn-stop': running }"
      @click="onPrimary"
    >
      {{ running ? '停止扫描' : '开始扫描' }}
    </button>

    <button
      :disabled="!selectedId || running"
      @click="dialogOpen = true"
    >
      打开历史…
    </button>

    <div v-if="progress" class="prog">{{ progress.scanned }}/{{ progress.total }} · 命中 {{ progress.hits }}</div>
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

    <StopScanDialog
      v-if="stopDialogOpen"
      :hits="progress?.hits ?? 0"
      @save="onStopSave"
      @discard="onStopDiscard"
      @continue="onStopContinue"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePatternsStore } from '../stores/patterns'
import { useScanStore } from '../stores/scan'
import { useConfigStore } from '../stores/config'
import ScanResultDialog from './ScanResultDialog.vue'
import StopScanDialog from './StopScanDialog.vue'

const patterns = usePatternsStore()
const scan = useScanStore()
const cfg = useConfigStore()
const { selectedId } = storeToRefs(patterns)
const { running, progress, lastDone } = storeToRefs(scan)

const start = ref('2025-01-01')
const end = ref('2025-12-31')
const workers = ref(8)
const tickerRegex = ref<string | null>(null)
const labelHorizon = ref(20)
const dialogOpen = ref(false)
const stopDialogOpen = ref(false)

onMounted(async () => {
  try {
    await cfg.load()
    const s = cfg.config?.scan
    if (s) {
      start.value = s.start_date; end.value = s.end_date
      workers.value = s.workers; tickerRegex.value = s.ticker_regex
      labelHorizon.value = s.label_horizon ?? 20
    }
  } catch { /* 后端不可用:保留默认 */ }
})

async function onPrimary() {
  if (!selectedId.value) return
  if (running.value) {
    // 正在扫:已命中数 > 0 → 弹 StopScanDialog 让用户选;= 0 → 直接 cancel(false)
    if ((progress.value?.hits ?? 0) > 0) {
      stopDialogOpen.value = true
    } else {
      await scan.cancel(false)
    }
  } else {
    await onScan()
  }
}

async function onScan() {
  if (!selectedId.value) return
  const s = {
    start_date: start.value, end_date: end.value,
    workers: workers.value, ticker_regex: tickerRegex.value,
    label_horizon: labelHorizon.value,
  }
  if (cfg.config) await cfg.save({ ...cfg.config, scan: s })
  scan.run({ pattern_id: selectedId.value, ...s })
}

async function onStopSave()    { stopDialogOpen.value = false; await scan.cancel(true) }
async function onStopDiscard() { stopDialogOpen.value = false; await scan.cancel(false) }
function onStopContinue()      { stopDialogOpen.value = false }

// dialog 开着时,扫描若自然跑完 → 自动关 dialog
watch(running, (r) => { if (!r && stopDialogOpen.value) stopDialogOpen.value = false })
</script>

<style scoped>
.panel { padding: 10px; border-top: 1px solid #e5e7eb; }
label { font-size: 11px; color: #64748b; display: block; margin-top: 6px; }
input { padding: 3px; width: 90px; }
button { margin-top: 8px; width: 100%; padding: 6px; }
button.btn-stop { background: #ef4444; color: #fff; }
.prog, .done { font-size: 11px; margin-top: 6px; }
</style>
```

- [ ] **Step 5.5: 跑组件测试 GREEN + 整套**

```bash
npm run test -- --run
npx vue-tsc --noEmit
npm run build
```
预期：全绿。

- [ ] **Step 5.6: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/SidebarScanPanel.vue path2_web_ui/tests/components/SidebarScanPanel.spec.ts
git commit -m "path2_web_ui/SidebarScanPanel: 停止扫描三分支 + StopScanDialog 接线"
```

---

## Task 6: Frontend — `ScanResultDialog` 历史行「未完成」标

**Files:**
- Modify: `path2_web_ui/src/components/ScanResultDialog.vue`
- Test: `path2_web_ui/tests/components/ScanResultDialog.spec.ts`

**Interfaces:**
- Consumes: `ScanHistoryEntry.partial` (Task 3) + 后端 list_scans 返回 partial 字段（Task 1）。
- Produces: 表格每一行：若 `r.partial===true`，在 Time 列后或末尾显示「未完成」小标。

### Steps

- [ ] **Step 6.1: 写 RED 测试**

打开 `path2_web_ui/tests/components/ScanResultDialog.spec.ts`，参考既有 row 渲染断言，新增：

```ts
it('显示「未完成」标当某行 partial=true', async () => {
  const scan = useScanStore()
  // 通过 store 注入 history(既有用例已有类似 mock 模式)
  ;(scan as any).history = [
    { scan_ts: '20260619T100000', hits: 3, total: 5, size: 200, partial: true },
    { scan_ts: '20260619T100100', hits: 9, total: 9, size: 500, partial: false },
  ]
  const w = mount(ScanResultDialog, { props: { patternId: 'pat_x' } })
  await flushPromises()
  const rows = w.findAll('tbody tr')
  expect(rows[0].text()).toContain('未完成')      // history 排序后第一行(partial=true)
  expect(rows[1].text()).not.toContain('未完成')
})
```

注：history 的注入方式按现有测试中怎么写 history（可能是 `scan.refreshHistory` 走 listScans mock，或者直接 `rows.value` 注入），照样模仿。

- [ ] **Step 6.2: 跑 RED**

```bash
npm run test -- --run tests/components/ScanResultDialog.spec.ts
```
预期：FAIL（"未完成" 字样不存在）。

- [ ] **Step 6.3: 改 `ScanResultDialog.vue` 渲染 partial 标**

在 `<table>` 的 `<thead>` 不动，`<tbody>` 的 row 模板里在 `<td>` 时间列后或最末加：

```vue
<tbody>
  <tr v-for="(r, i) in rows" :key="r.scan_ts"
      :class="{ active: selected.has(r.scan_ts), current: r.scan_ts === currentScanTs }"
      @click.exact.prevent="selectSingle(i)"
      @click.ctrl.prevent="toggle(i)"
      @click.meta.prevent="toggle(i)"
      @click.shift.prevent="extendTo(i)"
      @dblclick="openOne(r.scan_ts)">
    <td>
      {{ formatTs(r.scan_ts) }}
      <span v-if="r.partial" class="partial-badge">未完成</span>
    </td>
    <td>{{ r.hits === null ? '—' : `${r.hits} / ${r.total}` }}</td>
    <td>{{ formatSize(r.size) }}</td>
  </tr>
</tbody>
```

样式块加：

```css
.partial-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 10px;
  background: #fef3c7;
  color: #92400e;
  border-radius: 3px;
  vertical-align: middle;
}
```

- [ ] **Step 6.4: 跑组件测试 + 全套三绿**

```bash
npm run test -- --run
npx vue-tsc --noEmit
npm run build
```
预期：全 PASS。

- [ ] **Step 6.5: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/ScanResultDialog.vue path2_web_ui/tests/components/ScanResultDialog.spec.ts
git commit -m "path2_web_ui/ScanResultDialog: 历史行展示「未完成」partial 标"
```

---

## Verification (Plan-level end-to-end)

实现完毕后，端到端验证：

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
# 后端
uv run pytest tests/path2_web -q
# 前端
cd path2_web_ui && npm run test -- --run && npx vue-tsc --noEmit && npm run build
```

手工浏览器验证（按 spec § 验证 5-9）：

1. **保存路径**：起扫 → 等 `hits > 0` → 点停止 → modal 出现 → 点保存 → 主视图自动加载新结果（沿用 done auto-load）。打开「打开历史…」→ 顶部那条带「未完成」标。
2. **丢弃路径**：起扫 → 等 `hits > 0` → 点停止 → 点丢弃 → 主视图不变 → 打开历史 → 没这条。
3. **继续扫描**：起扫 → 等 `hits > 0` → 点停止 → 点继续扫描 → modal 消失、扫描继续 → 直到自然完成 → 主视图加载完整结果（历史那行**无**「未完成」标）。
4. **0 命中停止**：起扫 → 立刻点停止（hits=0）→ modal 不出现，直接走丢弃。
5. **modal 自动关**：起扫 → 等 `hits > 0` → 点停止 → modal 出现 → 等扫描自然跑完 → modal 自动消失、主视图加载完整结果。
6. **历史功能回归**：「打开历史…」批量删除、Open 等功能不变。

## Self-Review 已执行项

- 全部 spec 章节覆盖：用户体验 → Task 4/5；后端契约 § 1-3 → Task 1/2；前端契约 § 1-5 → Task 3/4/5/6；边界（modal 期间扫描在跑、hits=0 不弹、save+cancelled 互斥、modal singleton）→ Task 5 onPrimary 三分支 + watch running。
- 所有 TBD/TODO 已消除；每步含可执行命令或完整代码块。
- 类型签名一致：`scan.cancel(save: boolean)`、`api.cancelScan(scanId, save?: boolean)`、`ScanManager.cancel(scan_id, save: bool)`、`run_scan(..., save_event=None)`、`partial: bool` 全程同名同型。
