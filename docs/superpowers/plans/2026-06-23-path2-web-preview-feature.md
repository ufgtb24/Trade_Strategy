# path2_web 临时计算(preview)功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `path2_web` 加一条单股临时计算侧链路 — 改 `params.yaml` 后无需重启 web、无需重跑全集扫描即可看到当前选中股的调参效果。

**Architecture:** 后端新增 `/preview` 端点(同步、不落盘,复刻 scan 的 buffered + label 链路);把 `scan.py:_scan_ticker` 内主流程抽成 `analyze_single` 共享函数,/scan 与 /preview 共用。前端 view store 加 `previewEnabled / preview / previewLoading / previewError` 四个 state + `effectiveAnalysis / effectivePattern / effectiveScan` 三个派生 computed,所有下游消费者改读 `effective*`;`SidebarResultList` 顶部加复选框 + 刷新按钮 ↻。

**Tech Stack:** Python 3 / FastAPI / pytest;Vue 3 / Pinia / Vitest / @vue/test-utils;`uv` 包管理;`npm` 前端构建。

## Global Constraints

- 当前分支:`dag`(增量提交到该分支,**不**新建 worktree)
- 不 cache 多股 preview:`preview` ref 只保存"当前显示的那只股"的结果
- 持久勾选状态:`previewEnabled = true` 时,切股票自动 `runPreview()`
- 三个 computed 用同一 guard:`previewEnabled && preview && preview.symbol === symbol.value`(任一不满足 → fall back 到 scanFile)
- 复选框 `disabled when !scanFile`;刷新按钮 `disabled when !previewEnabled || !preview || previewLoading || preview.symbol !== symbol`
- `runPreview()` finally 块的 `previewLoading = false` 必须有 stale-token guard(切股票时新旧并发 fetch 防 race)
- 前端 yaml 改完无需重启 web,`/preview` 调用即用最新值 — 由 `mod.load_params()` 真热加载保证
- 后端 `analyze_single` 在空窗 / 0 命中时返回 `(analysis=空集 dict, summary=空集 dict, scan_meta)`,**非 None** — 0 命中也要让前端展示"调参后无 match"
- `_scan_ticker` 改为薄包装后,scan 既有"0 命中跳过(返回 None)"语义保留
- 不引入新依赖
- pre-existing 失败 `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` 与本 plan 无关,可忽略
- 完整 spec:`docs/superpowers/specs/2026-06-23-path2-web-preview-feature-design.md`(每个 task 引用对应小节;读 plan 即可实施,不必再回头读 spec)

---

## File Structure

**修改**:
- `path2_web/scan.py` — 抽出 `analyze_single`,`_scan_ticker` 改薄包装
- `path2_web/api.py` — 加 `@router.get("/preview")` 路由
- `path2_web_ui/src/api.ts` — 加 `getPreview()` 函数 + `PreviewResp` 接口
- `path2_web_ui/src/stores/view.ts` — 加 preview state / computed / actions + 改 `selectSymbol` / `clearScanFile` / diag watch deps
- `path2_web_ui/src/components/SidebarResultList.vue` — 列表顶部加 `.preview-bar`
- `path2_web_ui/src/components/KlineChart.vue` — `currentAnalysis` / `pattern` / `scanFile.scan` → `effective*`
- `path2_web_ui/src/components/DetailSidebar.vue` — 同上
- `path2_web_ui/tests/stores.spec.ts` 的 `vi.mock('../src/api', ...)` — 加 `getPreview` 进 mock 表

**新建**:
- `tests/path2_web/test_preview.py` — 后端测试 10 条
- `path2_web_ui/tests/stores.preview.spec.ts` — store 测试 12 条
- `path2_web_ui/tests/components/SidebarResultList.preview.spec.ts` — 组件测试 10 条

---

## Task 1: 后端 `analyze_single` 抽取 + `_scan_ticker` 改薄包装

**Files:**
- Modify: `path2_web/scan.py:31-77`(`_scan_ticker` 现有实现)
- Test: 既有 `tests/path2_web/test_scan.py` / `test_scan_buffered.py` 不动,新加 `tests/path2_web/test_analyze_single.py`

**Interfaces:**
- Produces:
  ```python
  def analyze_single(*, pkl_path: str, module_path: str,
                     start_date: str, end_date: str,
                     end_role: str | None = None,
                     label_horizon: int | None = None
                     ) -> tuple[dict, dict, dict]:
      """返回 (analysis_dict, summary_dict, scan_meta_dict).
      空窗/0命中 → analysis = {"events":[],"matches":[],"role_index":{}},summary={"events":0,"matches":0}.
      异常向上抛(调用方负责包装)。
      """
  ```
  - `analysis_dict` = `serialize_analysis(res)` 同 schema(events + matches),或空集占位
  - `summary_dict` = `summarize(res)` 同 schema,或 `{"events":0, "matches":0}`
  - `scan_meta_dict` = `{"start_date","end_date","win_start","win_end","end_role","label_horizon"}`
  - `end_role is None` → 严格窗、不算 label、不过滤
  - `end_role is not None` → buffered 窗(用 `TRADING_TO_CALENDAR_RATIO` 推算)+ 窗内 match 过滤 + 注入 `forward_return`

- [ ] **Step 1: 创建 `tests/path2_web/test_analyze_single.py` 写 5 条红测试**

```python
"""analyze_single — _scan_ticker 主流程抽出后的纯函数测试。
非 buffered 路径(end_role=None)走严格窗、不算 label;buffered 路径与 scan 同口径。"""
from pathlib import Path

import pandas as pd

from path2_web.scan import analyze_single


def _mk_pkl(tmp_path, symbol, df=None):
    if df is None:
        from tests.path2.apps.test_matches import _synth_no_burst
        df = _synth_no_burst()
        df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    pkl = tmp_path / f"{symbol}.pkl"
    df.to_pickle(pkl)
    return str(pkl)


def test_analyze_single_non_buffered_returns_tuple(tmp_path):
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, meta = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role=None, label_horizon=None,
    )
    assert isinstance(analysis, dict)
    assert isinstance(summary, dict)
    assert isinstance(meta, dict)
    assert {"events", "matches"} <= set(analysis)
    assert meta["end_role"] is None
    assert meta["label_horizon"] is None
    assert meta["win_start"] == "2025-01-01"
    assert meta["win_end"] == "2025-12-31"


def test_analyze_single_buffered_pads_window(tmp_path):
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, meta = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-06-01", end_date="2025-06-30",
        end_role="bo", label_horizon=20,
    )
    # buffered 路径 win_start < start_date,win_end > end_date(被 TRADING_TO_CALENDAR_RATIO 拉宽)
    assert meta["win_start"] < "2025-06-01"
    assert meta["win_end"] > "2025-06-30"
    assert meta["end_role"] == "bo"
    assert meta["label_horizon"] == 20


def test_analyze_single_empty_window_returns_empty_collections(tmp_path):
    # 选一个超出数据范围的窗 → 空窗
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2099-01-01", end_date="2099-12-31",
        end_role=None, label_horizon=None,
    )
    assert analysis == {"events": [], "matches": [], "role_index": {}}
    assert summary == {"events": 0, "matches": 0}


def test_analyze_single_no_match_returns_empty_matches_not_none(tmp_path):
    # _synth_no_burst 构造出 0 命中:analysis.matches=[],但 events 可能非空。
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role=None, label_horizon=None,
    )
    # 关键:0 命中也返回空集 dict,**非 None**
    assert analysis is not None
    assert analysis["matches"] == []


def test_analyze_single_buffered_matches_have_forward_return(tmp_path):
    """positive_case 构造确定命中(若 fixture 支持),验证 buffered 路径下 matches 携带 forward_return。
    若数据无 match,跳过(不报错)。"""
    from tests.path2.apps.positive_case import _synth_positive
    df = _synth_positive()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    pkl = _mk_pkl(tmp_path, "ACRS", df=df)
    analysis, _, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role="bo", label_horizon=20,
    )
    if not analysis["matches"]:
        return                              # 弱 fixture:不报错,只在有 match 时断言契约
    for m in analysis["matches"]:
        assert "forward_return" in m         # buffered 路径下注入 label
```

- [ ] **Step 2: Run tests to verify fail**

```bash
uv run pytest tests/path2_web/test_analyze_single.py -v
```

Expected: 5 FAILED with `ImportError: cannot import name 'analyze_single' from 'path2_web.scan'`

- [ ] **Step 3: 抽出 `analyze_single`,改薄 `_scan_ticker`**

打开 `path2_web/scan.py`,把现有的 `_scan_ticker` (行 31-77) 替换为以下三块:`analyze_single` 新函数 + `_scan_ticker` 薄包装。

```python
def analyze_single(*, pkl_path, module_path, start_date, end_date,
                   end_role=None, label_horizon=None):
    """单股 analyze 的纯函数(_scan_ticker 与 /preview 共用)。

    返回 (analysis_dict, summary_dict, scan_meta_dict)。
    空窗 / 0 命中 → analysis={"events":[],"matches":[],"role_index":{}}, summary={"events":0,"matches":0}
    (注:返回空集而非 None,/preview 端要看到"调参后无 match"的合法结果;
     _scan_ticker 在外层判断 matches==[] 转 None,保持"0 命中跳过"的 scan 语义)

    end_role 为 None → 严格 [start, end] 切窗,不过滤、不算 label
    end_role 非 None → buffered 窗(TRADING_TO_CALENDAR_RATIO 推算)+ 窗内 match 过滤 + forward_return 注入
    """
    df = pd.read_pickle(pkl_path)
    mod = importlib.import_module(module_path)
    buffered = end_role is not None

    if buffered:
        start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
        buf_start = start_ts - pd.Timedelta(days=round(7 * TRADING_TO_CALENDAR_RATIO))   # 7 = 占位,后续由调用方推算
        buf_end   = end_ts   + pd.Timedelta(days=round(label_horizon * TRADING_TO_CALENDAR_RATIO))
        # ↑ 实际 head_buffer 由调用方在 meta 推算,此处无 meta 信息只能由调用方传 buf_start/buf_end。
        # 但为复用 _scan_ticker 老协议,改用更简单语义:analyze_single 不推算 buf_start —— 它在 buffered
        # 模式只对 [start, end] 严格窗内做窗口过滤 + label,不动数据窗。下面是简化重写:

    # ── 简化重写:无论 buffered 与否,analyze_single 都对 [start, end] 严格切窗;
    #    buffered 仅意味着 matches 注入 forward_return。head_buffer 推算由调用方负责。
    win = slice_window(df, start_date, end_date)
    if len(win) == 0:
        return ({"events": [], "matches": [], "role_index": {}},
                {"events": 0, "matches": 0},
                {"start_date": start_date, "end_date": end_date,
                 "win_start": start_date, "win_end": end_date,
                 "end_role": end_role, "label_horizon": label_horizon})

    _load = getattr(mod, "load_params", None)
    res = mod.analyze(win, _load() if callable(_load) else None)

    analysis = serialize_analysis(res) if len(res.matches) > 0 or len(res.events) > 0 else \
               {"events": [], "matches": [], "role_index": {}}
    summary = summarize(res) if (len(res.matches) > 0 or len(res.events) > 0) else \
              {"events": 0, "matches": 0}

    meta = {"start_date": start_date, "end_date": end_date,
            "win_start": start_date, "win_end": end_date,
            "end_role": end_role, "label_horizon": label_horizon}

    if buffered:
        # 窗口过滤 + label(口径与 scan 一致)
        start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
        ret_by_id: dict = {}
        for m in res.matches:
            ev = m.role_index[end_role]
            buy_date = win["date"].iat[ev.start_idx]
            if not (start_ts <= buy_date <= end_ts):
                continue
            ret_by_id[m.event_id] = match_forward_returns(m, end_role, win, [label_horizon])[label_horizon]
        analysis["matches"] = [
            {**md, "forward_return": ret_by_id[md["event_id"]]}
            for md in analysis["matches"] if md["event_id"] in ret_by_id
        ]
        summary["matches"] = len(analysis["matches"])

    return (analysis, summary, meta)


def _scan_ticker(pkl_path, module_path, start, end,
                 buf_start=None, buf_end=None, end_role=None, label_horizon=None):
    """Scan worker:复刻原行为(0 命中跳过返 None,异常 → err 字符串)。
    底层调 analyze_single,但 scan worker 拿到的是"已被调用方推宽的窗"(buf_start/buf_end)。"""
    symbol = Path(pkl_path).stem
    try:
        # buffered:把 buf_start/buf_end 当作 start/end 传给 analyze_single,
        # 内部对该窗 analyze;然后用 start/end(用户原传)做 match 过滤。
        # 注意:analyze_single 用 start_date/end_date 做窗+过滤一体,这里需要先拆开。
        if end_role is not None:
            # scan 缓冲路径:把 buf 窗当作 analyze 窗,过滤按原 start/end 走
            analysis, summary, _ = analyze_single(
                pkl_path=pkl_path, module_path=module_path,
                start_date=buf_start, end_date=buf_end,
                end_role=None, label_horizon=None)        # 内部不过滤
            if analysis is None or not analysis["events"]:
                return (symbol, None, None, None)
            # 外层过滤 + label(就地复刻 analyze_single buffered 分支,但 win 已是 buf 窗)
            df = pd.read_pickle(pkl_path); win = slice_window(df, buf_start, buf_end)
            from path2_apps.bottom_breakout_burst import analyze as _bbb_analyze       # 不能直接读 res
            # ← 这里发现 _scan_ticker 需要 res 对象做 buffered 过滤,而 analyze_single 已丢失 res。
            # 更干净的做法:把 buffered 过滤逻辑做进 analyze_single,_scan_ticker 直接传整套参数。
            raise NotImplementedError("见 Step 4 重写:把 buffered 完全做进 analyze_single")
        analysis, summary, _ = analyze_single(
            pkl_path=pkl_path, module_path=module_path,
            start_date=start, end_date=end,
            end_role=None, label_horizon=None)
        if not analysis["matches"]:
            return (symbol, None, None, None)
        return (symbol, analysis, summary, None)
    except Exception as e:
        return (symbol, None, None, f"{type(e).__name__}: {e}")
```

**Step 3 实际只是中间过渡 — 见 Step 4 把 buffered 一气做进 analyze_single,不留 _scan_ticker race。**

- [ ] **Step 4: 重写 `analyze_single` 让 buffered 一气完成,`_scan_ticker` 干净薄包装**

替换上一步占位为最终版:

```python
def analyze_single(*, pkl_path, module_path, start_date, end_date,
                   end_role=None, label_horizon=None,
                   buf_start=None, buf_end=None):
    """单股 analyze 的纯函数(_scan_ticker 与 /preview 共用)。

    返回 (analysis_dict, summary_dict, scan_meta_dict)。
    空窗 / 0 命中 → analysis={"events":[],"matches":[],"role_index":{}}, summary={"events":0,"matches":0}

    协议:
      - end_role=None → 严格 [start_date, end_date] 切窗,不过滤、不算 label
        (此时 buf_start/buf_end 应为 None,内部用 start_date/end_date 切窗)
      - end_role 非 None → 调用方必须传 buf_start/buf_end(预先 TRADING_TO_CALENDAR_RATIO 推宽);
        analyze 用 [buf_start, buf_end] 切窗;match 按 [start_date, end_date] 过滤;注入 forward_return
    """
    df = pd.read_pickle(pkl_path)
    mod = importlib.import_module(module_path)
    buffered = end_role is not None

    if buffered:
        win = slice_window(df, buf_start, buf_end)
        win_start, win_end = buf_start, buf_end
    else:
        win = slice_window(df, start_date, end_date)
        win_start, win_end = start_date, end_date

    meta_template = lambda: {"start_date": start_date, "end_date": end_date,
                              "win_start": win_start, "win_end": win_end,
                              "end_role": end_role, "label_horizon": label_horizon}

    if len(win) == 0:
        return ({"events": [], "matches": [], "role_index": {}},
                {"events": 0, "matches": 0}, meta_template())

    _load = getattr(mod, "load_params", None)
    res = mod.analyze(win, _load() if callable(_load) else None)

    if not buffered:
        analysis = serialize_analysis(res)
        summary = summarize(res)
        return (analysis, summary, meta_template())

    # buffered 路径:窗口过滤 + label(口径与 scan 一致)
    start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
    ret_by_id: dict = {}
    for m in res.matches:
        ev = m.role_index[end_role]
        buy_date = win["date"].iat[ev.start_idx]
        if not (start_ts <= buy_date <= end_ts):
            continue
        ret_by_id[m.event_id] = match_forward_returns(m, end_role, win, [label_horizon])[label_horizon]
    analysis = serialize_analysis(res)
    analysis["matches"] = [
        {**md, "forward_return": ret_by_id[md["event_id"]]}
        for md in analysis["matches"] if md["event_id"] in ret_by_id
    ]
    summary = summarize(res)
    summary["matches"] = len(analysis["matches"])
    return (analysis, summary, meta_template())


def _scan_ticker(pkl_path, module_path, start, end,
                 buf_start=None, buf_end=None, end_role=None, label_horizon=None):
    """Worker:读 pkl → analyze_single → 0 命中跳过返 None,异常 → err 字符串。"""
    symbol = Path(pkl_path).stem
    try:
        analysis, summary, _ = analyze_single(
            pkl_path=pkl_path, module_path=module_path,
            start_date=start, end_date=end,
            end_role=end_role, label_horizon=label_horizon,
            buf_start=buf_start, buf_end=buf_end)
        if not analysis["events"] and not analysis["matches"]:
            return (symbol, None, None, None)       # 空窗 → 跳过
        if not analysis["matches"]:
            return (symbol, None, None, None)       # 0 命中 → 跳过(scan 语义)
        return (symbol, analysis, summary, None)
    except Exception as e:
        return (symbol, None, None, f"{type(e).__name__}: {e}")
```

注意:`analyze_single` 测试里第 2 条 `test_analyze_single_buffered_pads_window` 验证 win_start/win_end 被拉宽 — 但根据新协议 buffered 的窗推算由**调用方**做(传 buf_start/buf_end)。修测试:测试里现场推算 buf_start/buf_end 传进去验证 meta 反映该值。

修 `tests/path2_web/test_analyze_single.py` 中第 2 条测试为:

```python
def test_analyze_single_buffered_uses_provided_buf_window(tmp_path):
    """buffered 路径下,调用方传 buf_start/buf_end,meta 反映传入值。"""
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, meta = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-06-01", end_date="2025-06-30",
        buf_start="2025-05-01", buf_end="2025-08-30",
        end_role="bo", label_horizon=20,
    )
    assert meta["win_start"] == "2025-05-01"
    assert meta["win_end"] == "2025-08-30"
    assert meta["end_role"] == "bo"
    assert meta["label_horizon"] == 20
```

- [ ] **Step 5: Run analyze_single tests + 全部 scan 回归**

```bash
uv run pytest tests/path2_web/test_analyze_single.py tests/path2_web/test_scan.py tests/path2_web/test_scan_buffered.py -v
```

Expected:
- `test_analyze_single.py`:5 PASSED(其中第 5 条若 fixture 无 match 仅断言契约不报错)
- `test_scan.py`:全 PASSED(原有 scan 行为不变)
- `test_scan_buffered.py`:全 PASSED(buffered 路径行为不变)

- [ ] **Step 6: 全 path2_web 回归 + 全 path2 回归**

```bash
uv run pytest tests/path2_web tests/path2 tests/path2_apps -q
```

Expected:大致 ~360+ PASSED;唯一允许失败 = `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close`(pre-existing,与本 plan 无关)。其他失败 → 调查并修复。

- [ ] **Step 7: Commit**

```bash
git add path2_web/scan.py tests/path2_web/test_analyze_single.py
git commit -m "$(cat <<'EOF'
path2_web/scan: extract analyze_single, _scan_ticker thin-wrap

把 _scan_ticker 内主流程(buffered 窗 + match 过滤 + label 注入)
抽成独立 analyze_single 函数,/preview 端点(后续 task)直接复用,
无重复实现。_scan_ticker 改为薄包装:调 analyze_single + scan 特有的
"0 命中跳过返 None / 异常 → err 字符串"两条规则。
EOF
)"
```

---

## Task 2: 后端 `/preview` 路由

**Files:**
- Modify: `path2_web/api.py`(行 199 `get_diagnose` 之后加新路由)
- Test: 新建 `tests/path2_web/test_preview.py`

**Interfaces:**
- Consumes: `analyze_single` (Task 1) + `resolve_eval_meta` (已存在 `api.py:32-48`) + `scan_mod.TRADING_TO_CALENDAR_RATIO`
- Produces:
  ```
  GET /preview?pattern_id=<str>&symbol=<str>&start=<YYYY-MM-DD>&end=<YYYY-MM-DD>&label_horizon=<int>
  → 200 {analysis: {...}, summary: {...}, pattern_spec: {...}, scan: {...}}
  → 404 unknown pattern / pkl not found
  → 500 yaml ValueError / analyze_single 异常
  ```

- [ ] **Step 1: 写 10 条红测试到 `tests/path2_web/test_preview.py`**

```python
"""/preview 端点 — 单股临时计算(不落盘)。
buffered 路径(有 eval_meta)pads buf 窗 + 注入 forward_return;非 buffered 严格窗。"""
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


def _mk_pkl(data_dir: Path, symbol: str):
    from tests.path2.apps.test_matches import _synth_no_burst
    df = _synth_no_burst()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    df.to_pickle(data_dir / f"{symbol}.pkl")


def _client(tmp_path, with_pkl: str | None = "AAA"):
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    if with_pkl:
        _mk_pkl(data_dir, with_pkl)
    cfg = {
        "dataset_dir": str(data_dir),
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31",
                 "workers": 1, "ticker_regex": None},
        "last_selected_pattern": "bottom_breakout_burst",
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app)


def test_preview_returns_four_keys(tmp_path):
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"analysis", "summary", "pattern_spec", "scan"}


def test_preview_analysis_schema(tmp_path):
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    assert {"events", "matches", "role_index"} <= set(body["analysis"])


def test_preview_pattern_spec_has_topology(tmp_path):
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    spec = body["pattern_spec"]
    assert "topology" in spec
    assert "nodes" in spec["topology"]
    assert "edges" in spec["topology"]


def test_preview_uses_buffered_window_when_eval_meta_present(tmp_path):
    """bbb 有 eval_meta(end_role='bo', head_buffer_trading_days>0),win 应被拉宽。"""
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                      "symbol": "AAA", "start": "2025-06-01",
                                      "end": "2025-06-30", "label_horizon": 20}).json()
    scan = body["scan"]
    assert scan["win_start"] < "2025-06-01"
    assert scan["win_end"] > "2025-06-30"
    assert scan["end_role"] == "bo"
    assert scan["label_horizon"] == 20


def test_preview_falls_back_when_eval_meta_missing(tmp_path, monkeypatch):
    """mock 掉 eval_meta → 走严格窗,end_role/label_horizon 为 null。"""
    import path2_apps.bottom_breakout_burst.dag_spec as bbb_dag
    monkeypatch.delattr(bbb_dag, "eval_meta", raising=False)
    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                      "symbol": "AAA", "start": "2025-06-01",
                                      "end": "2025-06-30", "label_horizon": 20}).json()
    scan = body["scan"]
    assert scan["win_start"] == "2025-06-01"
    assert scan["win_end"] == "2025-06-30"
    assert scan["end_role"] is None
    assert scan["label_horizon"] is None


def test_preview_unknown_pattern_404(tmp_path):
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "does_not_exist",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 404
    assert "unknown pattern" in r.json()["detail"]


def test_preview_pkl_not_found_404(tmp_path):
    c = _client(tmp_path, with_pkl=None)
    r = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                   "symbol": "MISSING", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 404
    assert "pkl not found" in r.json()["detail"]


def test_preview_empty_window_returns_empty_collections(tmp_path):
    """窗口超出数据范围 → 200 + 空集 dict,非 null,非 error。"""
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                   "symbol": "AAA", "start": "2099-01-01",
                                   "end": "2099-12-31", "label_horizon": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["events"] == []
    assert body["analysis"]["matches"] == []


def test_preview_no_match_returns_empty_matches_not_error(tmp_path):
    """_synth_no_burst 构造 0 命中:200 + matches=[],不报错。"""
    c = _client(tmp_path)
    r = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                   "symbol": "AAA", "start": "2025-01-01",
                                   "end": "2025-12-31", "label_horizon": 20})
    assert r.status_code == 200
    assert r.json()["analysis"]["matches"] == []


def test_preview_pattern_spec_reflects_current_yaml(tmp_path, monkeypatch):
    """monkeypatch load_params 返回改后值 → 响应 pattern_spec 反映新阈值。"""
    import path2_apps.bottom_breakout_burst as bbb
    import path2_apps.bottom_breakout_burst.dag_spec as bbb_dag
    base = bbb.Params.default()
    # 把 burst.first_drought_min 临时改为 999(显著值,方便在 spec 里找到)
    from dataclasses import replace
    custom = replace(base, burst=replace(base.burst, first_drought_min=999))
    monkeypatch.setattr(bbb, "load_params", lambda: custom)
    monkeypatch.setattr(bbb_dag, "load_params", lambda: custom)

    c = _client(tmp_path)
    body = c.get("/preview", params={"pattern_id": "bottom_breakout_burst",
                                      "symbol": "AAA", "start": "2025-01-01",
                                      "end": "2025-12-31", "label_horizon": 20}).json()
    # spec 内某个 node 的 where_rule 阈值含 999(具体路径:burst 节点 first_drought 子句)
    nodes = body["pattern_spec"]["topology"]["nodes"]
    burst_node = next((n for n in nodes if n.get("class_id") == "burst" or "burst" in n.get("node_id", "")), None)
    assert burst_node is not None, "找不到 burst 节点"
    drought_rule = next((r for r in burst_node["where_rules"]
                         if r["clause_id"] == "first_drought"), None)
    assert drought_rule is not None, "burst 节点缺 first_drought where_rule"
    assert drought_rule["threshold"] == 999
```

- [ ] **Step 2: Run tests to verify fail**

```bash
uv run pytest tests/path2_web/test_preview.py -v
```

Expected: 10 FAILED with `404 Not Found`(`/preview` 端点未注册)

- [ ] **Step 3: 在 `path2_web/api.py` 加 `/preview` 路由**

在 `get_diagnose`(行 185-198)之后插入(行 199 之前):

```python
@router.get("/preview")
def get_preview(pattern_id: str, symbol: str, start: str, end: str,
                label_horizon: int = 20):
    """单股临时计算 — 复刻 /scan 的 buffered+label 链路,不落盘。
    pattern_spec 用 mod.load_params() 实时 build(yaml SSoT,改 yaml 立即反映)。"""
    mod = registry.get(pattern_id)
    if mod is None:
        raise HTTPException(404, f"unknown pattern: {pattern_id}")
    cfg = get_config()
    pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
    if not pkl.exists():
        raise HTTPException(404, f"pkl not found: {symbol}")

    meta = resolve_eval_meta(mod)
    if meta:
        end_role = meta["end_role"]
        head_buf = meta["head_buffer_trading_days"]
        start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
        buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
        buf_end   = str((end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
        analysis, summary, scan_meta = scan_mod.analyze_single(
            pkl_path=str(pkl), module_path=registry.module_path(pattern_id),
            start_date=start, end_date=end,
            end_role=end_role, label_horizon=label_horizon,
            buf_start=buf_start, buf_end=buf_end)
    else:
        analysis, summary, scan_meta = scan_mod.analyze_single(
            pkl_path=str(pkl), module_path=registry.module_path(pattern_id),
            start_date=start, end_date=end,
            end_role=None, label_horizon=None)
        # 强制 scan_meta 的 label_horizon=null(非 buffered 路径下不算 label)
        scan_meta["label_horizon"] = None

    pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))
    return {"analysis": analysis, "summary": summary,
            "pattern_spec": pattern_spec, "scan": scan_meta}
```

- [ ] **Step 4: Run preview tests + 全 path2_web 回归**

```bash
uv run pytest tests/path2_web -v
```

Expected:
- `test_preview.py`:10 PASSED
- 其他 `test_api.py / test_scan.py / test_scan_buffered.py / test_diagnose.py / ...`:全 PASSED(无回归)

- [ ] **Step 5: Commit**

```bash
git add path2_web/api.py tests/path2_web/test_preview.py
git commit -m "$(cat <<'EOF'
path2_web/api: add /preview endpoint (single-stock, no-persist)

GET /preview?pattern_id=&symbol=&start=&end=&label_horizon= → 同步
返回 {analysis, summary, pattern_spec, scan}。pattern_spec 用
load_params() 实时 build(yaml SSoT 热加载),与 /scan 同口径。
有 eval_meta → 走 buffered+label,无 → 严格窗。
EOF
)"
```

---

## Task 3: 前端 `api.ts` 加 `getPreview` + `PreviewResp` 接口

**Files:**
- Modify: `path2_web_ui/src/api.ts`(末尾加新函数与接口)
- Test: 既有 `path2_web_ui/tests/api.spec.ts`(若存在则加测试;若不存在或不涉及 fetch mock,跳过测试改"调用时不报"由 Task 4 store 测试覆盖)

**Interfaces:**
- Produces:
  ```ts
  export interface PreviewResp {
    analysis: Analysis              // 复用 types.ts 的 Analysis
    summary: Record<string, number>
    pattern_spec: SerializedPattern
    scan: ScanMeta                  // 复用 types.ts 的 ScanMeta
  }
  export function getPreview(
    patternId: string, symbol: string, start: string, end: string, labelHorizon: number
  ): Promise<PreviewResp>
  ```

- [ ] **Step 1: 检查 `api.spec.ts` 现有测试是否对 fetch 做 mock**

```bash
cat path2_web_ui/tests/api.spec.ts 2>/dev/null | head -50
```

如果存在 — Step 2 写一条测试;不存在 → 跳到 Step 3。

- [ ] **Step 2(若有 api.spec.ts):加红测试**

在 `path2_web_ui/tests/api.spec.ts` 末尾追加:

```ts
import { getPreview } from '../src/api'

describe('getPreview', () => {
  it('builds GET URL with query params + parses JSON', async () => {
    const fakeResp = { analysis: { events: [], matches: [], role_index: {} },
                       summary: { events: 0, matches: 0 },
                       pattern_spec: { pattern_id: 'p', display_name: 'P',
                                       topology: { nodes: [], edges: [] },
                                       event_styles: {} },
                       scan: { scan_ts: '', start_date: '2025-01-01', end_date: '2025-12-31',
                               workers: 0, scanned: 0, hits: 0, errors: 0,
                               dataset_dir: '', params: '' } }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeResp), { status: 200 })
    )
    const r = await getPreview('p', 'AAPL', '2025-01-01', '2025-12-31', 20)
    expect(r.analysis.matches).toEqual([])
    expect(fetchSpy).toHaveBeenCalledOnce()
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('/preview?pattern_id=p&symbol=AAPL')
    expect(url).toContain('start=2025-01-01')
    expect(url).toContain('end=2025-12-31')
    expect(url).toContain('label_horizon=20')
  })
})
```

```bash
cd path2_web_ui && npx vitest run tests/api.spec.ts
```

Expected: 该测试 FAIL with `getPreview is not exported`。

- [ ] **Step 3: 在 `path2_web_ui/src/api.ts` 末尾加 `getPreview`**

```ts
// ── 单股临时计算(spec §3:GET /preview)──
import type { Analysis, ScanMeta, SerializedPattern } from './types'

export interface PreviewResp {
  analysis: Analysis
  summary: Record<string, number>
  pattern_spec: SerializedPattern
  scan: ScanMeta
}

export function getPreview(
  patternId: string, symbol: string, start: string, end: string, labelHorizon: number
): Promise<PreviewResp> {
  return getJson(
    `/preview?pattern_id=${encodeURIComponent(patternId)}`
    + `&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&label_horizon=${labelHorizon}`)
}
```

注:文件顶部已有 `import type { ... }`,把 `Analysis, ScanMeta, SerializedPattern` 加进去(若已存在则跳过)。`getJson` 已在文件顶部定义。

- [ ] **Step 4: Run frontend tests**

```bash
cd path2_web_ui && npx vitest run
```

Expected:既有测试全 PASS;若 Step 2 加了测试 → 新测试 PASS。

- [ ] **Step 5: 前端类型检查**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 无类型错误。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/api.ts path2_web_ui/tests/api.spec.ts 2>/dev/null || git add path2_web_ui/src/api.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/api: add getPreview() + PreviewResp interface

封装 GET /preview 端点(spec §3 后端契约的 TS 镜像)。Analysis /
ScanMeta / SerializedPattern 类型复用 types.ts 既有定义。
EOF
)"
```

---

## Task 4: 前端 view store — preview state / computed / actions

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Modify: `path2_web_ui/tests/stores.spec.ts`(在 `vi.mock('../src/api', ...)` 表内加 `getPreview` mock)
- Test: 新建 `path2_web_ui/tests/stores.preview.spec.ts`

**Interfaces:**
- Consumes: `getPreview` (Task 3)
- Produces:
  - State:`previewEnabled: Ref<boolean>`, `preview: Ref<{symbol, analysis, pattern_spec, scan} | null>`, `previewLoading: Ref<boolean>`, `previewError: Ref<string | null>`
  - Computed:`effectiveAnalysis: ComputedRef<Analysis | null>`, `effectivePattern: ComputedRef<SerializedPattern | null>`, `effectiveScan: ComputedRef<ScanMeta | null>`
  - Actions:`setPreviewEnabled(v: boolean): Promise<void>`, `runPreview(): Promise<void>`, `clearPreview(): void`
  - `selectSymbol(s)` 现有改:清 preview / previewError;若 previewEnabled → 自动调 runPreview
  - `clearScanFile()` 现有改:清 previewEnabled / preview / previewError
  - diag watch deps 改:`[symbol, scanFile, preview, previewEnabled]`,内部 windowOf 源改 effectiveScan

- [ ] **Step 1: 新建 `path2_web_ui/tests/stores.preview.spec.ts` 写 13 条红测试**

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { getPreview, getDiagnose } from '../src/api'
import { SCAN_FILE, ANALYSIS, PATTERN, DIAG } from './fixtures'

vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(DIAG)),
  getPreview: vi.fn(),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
}))

const PREVIEW_ANALYSIS = {
  ...ANALYSIS,
  matches: [{ ...ANALYSIS.matches[0], event_id: 'preview_match_1' }],
}
const PREVIEW_RESP = {
  analysis: PREVIEW_ANALYSIS,
  summary: { events: 6, matches: 1 },
  pattern_spec: PATTERN,
  scan: { ...SCAN_FILE.scan, win_start: '2025-01-01', win_end: '2025-12-31' },
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(getPreview).mockResolvedValue(PREVIEW_RESP as any)
})

describe('view.preview computed', () => {
  it('effectiveAnalysis falls back to scanFile when previewEnabled=false', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    expect(v.effectiveAnalysis?.matches[0].event_id).toBe('m1')
  })

  it('effectiveAnalysis falls back when preview.symbol mismatches symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true)
    await flushPromises()
    // 切到别股(scanFile.results 没有 BBB,但内存仍可设)
    v.selectSymbol('OTHER')                              // preview 被清,但即便保留也应 fall back
    expect(v.effectiveAnalysis).toBeNull()               // OTHER 不在 scanFile.results
  })

  it('effectiveAnalysis uses preview when three conditions met', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true)
    await flushPromises()
    expect(v.effectiveAnalysis?.matches[0].event_id).toBe('preview_match_1')
  })

  it('effectivePattern uses preview pattern_spec when active', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.effectivePattern).toBe(PREVIEW_RESP.pattern_spec)
  })

  it('effectiveScan uses preview scan when active', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.effectiveScan?.win_start).toBe('2025-01-01')
  })
})

describe('view.preview actions', () => {
  it('setPreviewEnabled(true) triggers runPreview', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce()
  })

  it('setPreviewEnabled(false) clears preview state', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.preview).not.toBeNull()
    await v.setPreviewEnabled(false)
    expect(v.preview).toBeNull()
    expect(v.previewError).toBeNull()
    expect(v.previewEnabled).toBe(false)
  })

  it('selectSymbol clears preview and refetches when enabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    vi.mocked(getPreview).mockClear()
    v.selectSymbol('BBB')
    expect(v.preview).toBeNull()                         // 旧 preview 清
    await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce() // 新股自动 fetch
  })

  it('selectSymbol does not fetch when disabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    vi.mocked(getPreview).mockClear()
    v.selectSymbol('BBB')
    await flushPromises()
    expect(vi.mocked(getPreview)).not.toHaveBeenCalled()
  })

  it('clearScanFile resets all preview state', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    v.clearScanFile()
    expect(v.preview).toBeNull()
    expect(v.previewEnabled).toBe(false)
    expect(v.previewError).toBeNull()
  })

  it('runPreview stale-token guard on symbol change', async () => {
    let resolver: (v: any) => void = () => {}
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => { resolver = r }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    void v.setPreviewEnabled(true)                       // 启动 fetch,未 resolve
    v.selectSymbol('BBB')                                // 切走
    resolver(PREVIEW_RESP)                               // 旧响应回来
    await flushPromises()
    expect(v.preview).toBeNull()                         // 被丢弃
  })

  it('runPreview stale-token guard on disable', async () => {
    let resolver: (v: any) => void = () => {}
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => { resolver = r }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    void v.setPreviewEnabled(true)
    await v.setPreviewEnabled(false)                     // 取消勾选
    resolver(PREVIEW_RESP)
    await flushPromises()
    expect(v.preview).toBeNull()
  })

  it('runPreview error sets previewError, keeps preview null', async () => {
    vi.mocked(getPreview).mockRejectedValueOnce(new Error('500: boom'))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.preview).toBeNull()
    expect(v.previewError).toContain('boom')
  })

  it('runPreview can be called again to refresh (no cache)', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    vi.mocked(getPreview).mockClear()
    await v.runPreview(); await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce()
  })

  it('previewLoading is not cleared by stale response', async () => {
    let firstResolver: (v: any) => void = () => {}
    let secondResolver: (v: any) => void = () => {}
    let call = 0
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => {
      call++; if (call === 1) firstResolver = r; else secondResolver = r
    }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    void v.setPreviewEnabled(true)                       // 第一次 fetch
    v.selectSymbol('BBB')                                // 触发第二次 fetch(同 enabled)
    firstResolver(PREVIEW_RESP)                          // 旧响应先回
    await flushPromises()
    expect(v.previewLoading).toBe(true)                  // 不被旧响应清
    secondResolver({ ...PREVIEW_RESP, scan: { ...PREVIEW_RESP.scan, win_start: 'X' } })
    await flushPromises()
    expect(v.previewLoading).toBe(false)                 // 新响应清
  })
})
```

注意:`SCAN_FILE.results` 只含 AAPL,测试用到 'BBB' / 'OTHER' 时 currentResult 自然 null,行为不变。

- [ ] **Step 2: 把 `getPreview` 加进既有 `stores.spec.ts` 的 mock 表(防破其他测试)**

打开 `path2_web_ui/tests/stores.spec.ts`,把现有的:

```ts
vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(DIAG)),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
}))
```

改成:

```ts
vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(DIAG)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], role_index: {} },
    summary: { events: 0, matches: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
}))
```

- [ ] **Step 3: Run tests to verify fail**

```bash
cd path2_web_ui && npx vitest run tests/stores.preview.spec.ts
```

Expected: 多条 FAIL,主要因 `useViewStore` 上的 `previewEnabled / preview / previewLoading / previewError / effectiveAnalysis / effectivePattern / effectiveScan / setPreviewEnabled / runPreview` 等成员未定义。

- [ ] **Step 4: 修改 `path2_web_ui/src/stores/view.ts`**

定位现有结构:`view.ts:18-126`(整个 store 体)。

**(a)** 在文件顶部 import 加上 `getPreview` + `PreviewResp`:

```ts
import { getDiagnose, getPreview, type PreviewResp } from '../api'
```

**(b)** 在 store 的 state 区(`hoveredEventId / diag` 之后,大约 view.ts:28 一带)插入新 state:

```ts
  // ─── preview state(spec §4.1)─────────────────────────────────────────────
  const previewEnabled = ref(false)
  const preview = ref<{
    symbol: string
    analysis: PreviewResp['analysis']
    pattern_spec: PreviewResp['pattern_spec']
    scan: PreviewResp['scan']
  } | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<string | null>(null)
```

**(c)** 在 `pattern / currentResult / currentAnalysis` 之后,插入三个 effective* computed(必须用 `previewEnabled.value && preview.value && preview.value.symbol === symbol.value` 三联 guard):

```ts
  // ─── preview computed(三处统一 guard)──────────────────────────────────────
  const effectiveAnalysis = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.analysis
    return currentResult.value?.analysis ?? null
  })
  const effectivePattern = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.pattern_spec
    return scanFile.value?.pattern_spec ?? null
  })
  const effectiveScan = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.scan
    return scanFile.value?.scan ?? null
  })
```

**(d)** 改 `selectSymbol`(view.ts:57-62)和 `clearScanFile`(view.ts:48-56)。先看原:

```ts
  function selectSymbol(s: string) {
    symbol.value = s
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
  }
```

替换为:

```ts
  function selectSymbol(s: string) {
    symbol.value = s
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    // ─ preview:切股票清旧股临时结果;若仍勾选 → 自动 fetch 新股 ─
    preview.value = null
    previewError.value = null
    if (previewEnabled.value) void runPreview()
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    // ─ preview:切 pattern 时全复位 ─
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
  }
```

**(e)** 加 preview actions(放在既有 `setLevel / selectEvent / hoverEvent` 之后,大约 view.ts:74 一带):

```ts
  // ─── preview actions(spec §4.1)───────────────────────────────────────────
  async function setPreviewEnabled(v: boolean): Promise<void> {
    previewEnabled.value = v
    if (v) {
      await runPreview()
    } else {
      preview.value = null
      previewError.value = null
    }
  }

  async function runPreview(): Promise<void> {
    if (!scanFile.value || !symbol.value || !pattern.value) return
    previewLoading.value = true
    previewError.value = null
    const reqSymbol = symbol.value
    const reqEnabled = previewEnabled.value
    try {
      const baseScan = preview.value?.scan ?? scanFile.value.scan
      const w = windowOf(baseScan)
      const labelHorizon = baseScan.label_horizon ?? 20
      const resp = await getPreview(pattern.value.pattern_id, reqSymbol,
                                     w.start, w.end, labelHorizon)
      if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
      preview.value = { symbol: reqSymbol, analysis: resp.analysis,
                        pattern_spec: resp.pattern_spec, scan: resp.scan }
    } catch (e: any) {
      if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
      previewError.value = String(e?.message ?? e)
    } finally {
      // loading token guard:防并发场景旧响应错误清 loading
      if (symbol.value === reqSymbol && previewEnabled.value === reqEnabled)
        previewLoading.value = false
    }
  }

  function clearPreview(): void {
    preview.value = null
    previewError.value = null
  }
```

**(f)** 改 diag watch deps(view.ts:76 行):

原:

```ts
  watch([symbol, scanFile, pattern], async () => {
    if (!symbol.value || !scanFile.value || !pattern.value) { diag.value = null; return }
    const reqSymbol = symbol.value
    try {
      const w = windowOf(scanFile.value.scan)            // 与扫描/K线同窗(缓冲窗,旧文件回退)
      const d = await getDiagnose(pattern.value.pattern_id, symbol.value, w.start, w.end)
      if (symbol.value !== reqSymbol) return
      diag.value = d
    } catch { if (symbol.value === reqSymbol) diag.value = null }
  }, { immediate: true })
```

替换:

```ts
  watch([symbol, scanFile, pattern, preview, previewEnabled], async () => {
    if (!symbol.value || !scanFile.value || !pattern.value) { diag.value = null; return }
    const reqSymbol = symbol.value
    try {
      const w = windowOf(effectiveScan.value ?? scanFile.value.scan)
      const d = await getDiagnose(pattern.value.pattern_id, symbol.value, w.start, w.end)
      if (symbol.value !== reqSymbol) return
      diag.value = d
    } catch { if (symbol.value === reqSymbol) diag.value = null }
  }, { immediate: true })
```

**(g)** return 块加 preview 成员:

```ts
  return {
    // 现有 state
    scanFile, symbol, roleVisible, selected,
    // 新增 state
    level, selectedEventId, hoveredEventId, diag,
    // preview state(新)
    previewEnabled, preview, previewLoading, previewError,
    // 现有 computed
    pattern, currentResult, currentAnalysis, roleColors, selectedMatch,
    // preview computed(新)
    effectiveAnalysis, effectivePattern, effectiveScan,
    // 新增 computed
    tagMap, isolated, matchedIds, qualifiedIds,
    // 现有 actions
    loadScanFile, clearScanFile, selectSymbol, toggleRole, selectMatch, selectRole, clearSelection,
    // 新增 actions
    setLevel, selectEvent, hoverEvent,
    // preview actions(新)
    setPreviewEnabled, runPreview, clearPreview,
    // 新增 computed 函数
    bandKey, eventTier,
  }
```

- [ ] **Step 5: Run preview store tests + 既有 stores 测试回归**

```bash
cd path2_web_ui && npx vitest run tests/stores.preview.spec.ts tests/stores.spec.ts
```

Expected:
- `stores.preview.spec.ts`:13 PASSED
- `stores.spec.ts`:全 PASSED(无回归)

- [ ] **Step 6: 类型检查**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 无类型错误。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/stores.preview.spec.ts path2_web_ui/tests/stores.spec.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/view: add preview state + effective* computed + actions

spec §4.1 实施:previewEnabled/preview/previewLoading/previewError 四
state + effectiveAnalysis/Pattern/Scan 三 computed(三处统一 guard)+
setPreviewEnabled/runPreview/clearPreview 三 actions。runPreview 含
loading token guard(并发切股票时旧响应不清 loading)。selectSymbol
清旧 preview + 勾选状态自动 fetch 新股;clearScanFile 全复位;diag
watch deps 加 preview/previewEnabled,窗口源改 effectiveScan。
EOF
)"
```

---

## Task 5: 前端 `SidebarResultList` UI — 复选框 + 刷新按钮

**Files:**
- Modify: `path2_web_ui/src/components/SidebarResultList.vue`
- Test: 新建 `path2_web_ui/tests/components/SidebarResultList.preview.spec.ts`

**Interfaces:**
- Consumes: `view.previewEnabled / preview / previewLoading / previewError / scanFile / symbol`, actions `setPreviewEnabled / runPreview / clearPreview`(Task 4)
- Produces: UI 元素 `.preview-bar`(复选框 + 刷新按钮 + 状态条 + 错误条)

- [ ] **Step 1: 写组件红测试**

新建 `path2_web_ui/tests/components/SidebarResultList.preview.spec.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'
import { SCAN_FILE, ANALYSIS, PATTERN } from '../fixtures'

const PREVIEW_RESP = {
  analysis: ANALYSIS,
  summary: { events: 6, matches: 1 },
  pattern_spec: PATTERN,
  scan: SCAN_FILE.scan,
}

vi.mock('../../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve({} as any)),
  getPreview: vi.fn(() => Promise.resolve(PREVIEW_RESP)),
}))

describe('SidebarResultList preview UI', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('checkbox disabled when no scanFile', () => {
    const w = mount(SidebarResultList)
    const cb = w.get('input[type="checkbox"]')
    expect((cb.element as HTMLInputElement).disabled).toBe(true)
  })

  it('checkbox enabled when scanFile present', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const w = mount(SidebarResultList)
    const cb = w.get('input[type="checkbox"]')
    expect((cb.element as HTMLInputElement).disabled).toBe(false)
  })

  it('checkbox toggle calls setPreviewEnabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const spy = vi.spyOn(v, 'setPreviewEnabled')
    const w = mount(SidebarResultList)
    await w.get('input[type="checkbox"]').setValue(true)
    expect(spy).toHaveBeenCalledWith(true)
  })

  it('refresh button disabled when previewEnabled=false', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const w = mount(SidebarResultList)
    const btn = w.get('button.refresh')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled when no preview yet', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewEnabled = true                              // 强设
    const w = mount(SidebarResultList)
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled during loading', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    v.previewLoading = true                              // 强设模拟 loading
    const w = mount(SidebarResultList)
    await flushPromises()
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled when preview.symbol mismatches symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    v.symbol = 'OTHER'                                   // 模拟切走但 preview 未清(异常路径)
    const w = mount(SidebarResultList)
    await flushPromises()
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button enabled when all four conditions met', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    const w = mount(SidebarResultList)
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('refresh click calls runPreview', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    const spy = vi.spyOn(v, 'runPreview')
    const w = mount(SidebarResultList)
    await w.get('button.refresh').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })

  it('loading status visible during loading', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewLoading = true
    const w = mount(SidebarResultList)
    expect(w.text()).toContain('计算中…')
  })

  it('error bar visible and closable', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewError = '500: boom'
    const spy = vi.spyOn(v, 'clearPreview')
    const w = mount(SidebarResultList)
    expect(w.text()).toContain('500: boom')
    await w.get('.error a').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run tests to verify fail**

```bash
cd path2_web_ui && npx vitest run tests/components/SidebarResultList.preview.spec.ts
```

Expected: 11 FAILED(组件没有 `.preview-bar` / 复选框 / 刷新按钮 / 错误条)

- [ ] **Step 3: 修改 `path2_web_ui/src/components/SidebarResultList.vue`**

完整替换文件为:

```vue
<template>
  <div class="list">
    <!-- preview 工具栏(spec §4.4)-->
    <div class="preview-bar">
      <label class="toggle">
        <input type="checkbox" :checked="previewEnabled"
               :disabled="!scanFile"
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

    <div v-if="!scanFile" class="hint">未加载扫描结果</div>
    <div
      v-for="r in scanFile?.results ?? []" :key="r.symbol"
      :data-symbol="r.symbol" class="row" :class="{ active: r.symbol === symbol }"
      @click="view.selectSymbol(r.symbol)"
    >
      <span class="sym">{{ r.symbol }}</span>
      <span class="badges">
        <span v-for="(n, k) in r.summary" :key="k" class="badge">{{ k }}:{{ n }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError }
  = storeToRefs(view)

const canRefresh = computed(() =>
  previewEnabled.value && !!preview.value && !previewLoading.value
  && preview.value?.symbol === symbol.value)

function onToggle(e: Event) {
  void view.setPreviewEnabled((e.target as HTMLInputElement).checked)
}
function onCloseError() { view.clearPreview() }
</script>

<style scoped>
.list { overflow-y: auto; }

.preview-bar { padding: 6px 10px; border-bottom: 1px solid #e5e7eb;
               background: #f8fafc; }
.toggle { display: flex; align-items: center; gap: 6px; cursor: pointer;
          font-size: 12px; }
.toggle input { cursor: pointer; }
.refresh { margin-left: auto; padding: 1px 6px; font-size: 14px;
           border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.status { font-size: 11px; color: #64748b; margin-top: 4px; }
.error { font-size: 11px; color: #ef4444; margin-top: 4px; }
.error a { cursor: pointer; margin-left: 6px; }

.row { padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #f1f5f9; }
.row.active { background: #eff6ff; }
.sym { font-weight: 600; }
.badges { display: block; font-size: 10px; color: #64748b; }
.badge { margin-right: 6px; }
</style>
```

- [ ] **Step 4: Run tests**

```bash
cd path2_web_ui && npx vitest run tests/components/SidebarResultList.preview.spec.ts tests/components/ResultList.spec.ts
```

Expected:
- `SidebarResultList.preview.spec.ts`:11 PASSED
- `ResultList.spec.ts`:既有 1 条测试仍 PASSED

- [ ] **Step 5: 类型检查**

```bash
cd path2_web_ui && npx vue-tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/components/SidebarResultList.vue path2_web_ui/tests/components/SidebarResultList.preview.spec.ts
git commit -m "$(cat <<'EOF'
path2_web_ui/SidebarResultList: add preview checkbox + refresh button

spec §4.4 实施:列表顶部 .preview-bar 含复选框「用 yaml 临时计算」
+ 刷新按钮 ↻ + 加载状态条 + 错误条。复选框 disabled when !scanFile;
刷新按钮 disabled when !previewEnabled / !preview / previewLoading /
preview.symbol !== symbol(四联);错误条关闭叉调 clearPreview。
EOF
)"
```

---

## Task 6: 前端下游消费者迁移 — `effective*` 替换 + diag/K 线消费

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`

**Interfaces:**
- Consumes: `view.effectiveAnalysis / effectivePattern / effectiveScan`(Task 4)
- 在 view.ts 内部既有 `selectedMatch / matchedIds` 消费 `currentAnalysis`:**保留**(因为 selectedMatch 是"列表选中股的扫描 match",不应被 preview 影响)— 仅 K 线 / DetailSidebar 渲染层切到 effective*

- [ ] **Step 1: 修改 `path2_web_ui/src/components/KlineChart.vue`**

定位 `KlineChart.vue:16` 一行 destructure:

```ts
const { symbol, currentAnalysis, roleColors, roleVisible, level, tagMap, isolated, pattern, scanFile, selectedEventId, diag } = storeToRefs(view)
```

替换为:

```ts
const { symbol, effectiveAnalysis, roleColors, roleVisible, level, tagMap, isolated, effectivePattern, effectiveScan, scanFile, selectedEventId, diag } = storeToRefs(view)
```

(`scanFile` 仍保留 — 用于 K 线 ohlc fetch 的窗口存在性判定;但 windowOf 源改 effectiveScan。)

把文件内所有 `currentAnalysis` 改为 `effectiveAnalysis`(grep 出 5 处:行 44 / 50 / 53 / 66 / 80 / 102),所有 `pattern.value` 改为 `effectivePattern.value`(行 50)。

`windowOf(scanFile.value.scan)` 行 24 改为:

```ts
  const { start, end } = windowOf(effectiveScan.value ?? scanFile.value.scan)
```

行 32 `scanFile.value?.scan` (label_horizon 用)改为:

```ts
  const s = effectiveScan.value ?? scanFile.value?.scan
```

行 46 `scanFile.value?.scan.label_horizon` 改为:

```ts
  return `ret_${(effectiveScan.value ?? scanFile.value?.scan)?.label_horizon}: ${formatForwardReturn(m.forward_return)}`
```

行 101 watch `[symbol, scanFile]` 改为 `[symbol, scanFile, effectiveScan]`(scan 改变也要重拉 ohlc — preview 的 win_start/win_end 可能与 scanFile.scan 不同)。
行 102 watch deps 把 `currentAnalysis` 改 `effectiveAnalysis`。

- [ ] **Step 2: 修改 `path2_web_ui/src/components/DetailSidebar.vue`**

定位 `DetailSidebar.vue:134-135` destructure 块:

```ts
const { selected, selectedMatch, pattern, currentAnalysis,
        diag, isolated, matchedIds, qualifiedIds, roleColors, selectedEventId, scanFile, ... } = storeToRefs(view)
```

把 `pattern, currentAnalysis` 改为 `effectivePattern, effectiveAnalysis`;`scanFile` 保留(scan.label_horizon 仍用),并加 `effectiveScan`:

```ts
const { selected, selectedMatch, effectivePattern, effectiveAnalysis,
        diag, isolated, matchedIds, qualifiedIds, roleColors, selectedEventId,
        scanFile, effectiveScan, ... } = storeToRefs(view)
```

模板内:
- 行 6 / 75 / 120 `currentAnalysis` → `effectiveAnalysis`
- 行 6 / 75 / 120 `pattern` → `effectivePattern`
- 行 78 / 172 `currentAnalysis` → `effectiveAnalysis`
- 行 86 / 95 `scanFile?.scan.label_horizon` → `(effectiveScan ?? scanFile?.scan)?.label_horizon`(preview 同窗也得展示一致 label_horizon 数字)

- [ ] **Step 3: 运行既有组件测试 + 类型检查**

```bash
cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit
```

Expected:
- 既有 KlineChart.spec.ts / DetailSidebar.spec.ts 全 PASSED(它们不显式依赖 currentAnalysis,store 出口仍保留,无 break)
- vue-tsc 无错误

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue path2_web_ui/src/components/DetailSidebar.vue
git commit -m "$(cat <<'EOF'
path2_web_ui/KlineChart+DetailSidebar: read effective* instead of current*

spec §4.2 下游消费者迁移:K 线 markers / 拓扑 / where 显示都改读
effectiveAnalysis / effectivePattern / effectiveScan。preview 期间
三者一致反映新 yaml;非 preview 透传 scanFile。windowOf 窗口源改
effectiveScan(preview 与 scan 同窗,但显式取 preview 的更稳),K 线
ohlc reload watch 加 effectiveScan 触发,deps 加 effectiveAnalysis。
EOF
)"
```

---

## Task 7: E2E 实测 + 最终全量回归

**Files:** 不修改代码;只跑测试 + 浏览器实测。

- [ ] **Step 1: 全 Python 回归**

```bash
uv run pytest tests/path2 tests/path2_apps tests/path2_web -q
```

Expected:全 PASSED 或仅 `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` pre-existing 失败(允许)。其他失败 → 调查修复。

- [ ] **Step 2: 全前端回归 + 类型检查 + 构建**

```bash
cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npm run build
```

Expected:测试全 PASSED / 无类型错误 / 构建成功。

- [ ] **Step 3: 启动 web,准备 e2e 实测**

(背景跑,实测者本机执行)

```bash
uv run python scripts/run_path2_web.py
```

打开 `http://localhost:5173` (或脚本输出的端口)。

- [ ] **Step 4: e2e 工作流实测(spec §5.4)**

**A. 加载扫描**

1. 选 `bottom_breakout_burst` pattern,扫描 ACRS(或既有命中数据集),等扫描完成
2. 选中股(如 ACRS),记下 K 线 BO markers 数 N1

**B. 复选框勾选 + 切股票自动 fetch**

3. 勾选「用 yaml 临时计算」,等 < 5s,K 线 BO markers 数变 N1'(可能等于或不同)
4. 切到列表另一股 X,观察:
   - preview 瞬清,K 线短暂显示 X 的扫描结果
   - 自动触发 fetch,2-5s 后 K 线切到 X 的 preview
5. 切回 ACRS,同样自动 fetch

**C. 取消复选框**

6. 取消勾选,K 线立刻回到 ACRS 扫描 N1(preview 清)
7. 再勾选,重 fetch ACRS preview

**D. 改 yaml + 刷新按钮**

8. 在编辑器改 `path2_apps/bottom_breakout_burst/params.yaml`,把 `bo.exceed_threshold: 0.003` 改为 `0.05`(显著放宽)
9. 点 ↻ 刷新按钮,K 线 BO 数应显著上升 — 证明新 yaml 实时生效
10. 拓扑面板 bo 节点的 where 阈值显示新 yaml 的相应值

**E. yaml 拼错错误条**

11. 在 yaml 加一行 `bo_typooo: 1`(拼错的顶层 key)
12. 点 ↻,错误条显示 "params.yaml ... 含未知字段: ['bo_typooo']" 或类似
13. 删掉拼错行,点 ↻,错误条消失,新 preview 显示

记录任何与预期不符的行为。

- [ ] **Step 5: 用 web-loop 自动 review(可选,但 plan 自带 final holistic 阶段会做)**

如果用 `superpowers:subagent-driven-development` 执行整个 plan,final holistic 阶段会做这一步;若 inline 执行,可手工调 `web-loop` skill 或跳过。

- [ ] **Step 6: 检查 git 状态**

```bash
git status
git log --oneline -10
```

Expected:6 commits 落在 `dag` 分支(Task 1-6,Task 7 无代码改动)。

- [ ] **Step 7: 完成提示**

向用户报告:
- 本 plan 实现完成
- 后端 `analyze_single` 共享 fn + `/preview` 端点 + 前端 store + UI + 下游消费者迁移全到位
- 全量回归绿(Python + 前端 vitest + vue-tsc + build)
- e2e 实测 4 个工作流(切股自动 fetch / 取消复选框 / 改 yaml 刷新 / 拼错错误条)全通过
- 6 commits 落在 `dag`,未 push(等用户决定 push or merge)

---

## Self-Review

### 1. Spec coverage

| Spec 节 | 对应 Task |
|---------|-----------|
| §2 架构 | Task 1+2 后端 / Task 3-6 前端 |
| §3.1 端点 | Task 2 Step 3 |
| §3.2 错误 | Task 2 Step 1 测试(404 unknown / pkl not found) |
| §3.3 空窗 / 无 match | Task 1 Step 1 + Task 2 Step 1 |
| §3.4 eval_meta 缺失降级 | Task 2 Step 1 测试 + Step 3 implementation |
| §3.5 analyze_single 抽取 | Task 1 Step 3-4 |
| §3.6 /preview 路由 | Task 2 Step 3 |
| §3.7 并发护栏 | spec 注明短期 YAGNI,Task 2 不做(后期可升级) |
| §4.1 view store | Task 4 |
| §4.2 下游消费者迁移 | Task 6 |
| §4.3 api.ts | Task 3 |
| §4.4 UI | Task 5 |
| §4.5 切股票 UX | Task 4 selectSymbol + Task 7 e2e Step 4-B |
| §5.1-3 后端 / 5.2 store / 5.3 组件测试 | Task 1/2/4/5 各自 Step 1 |
| §5.4 E2E | Task 7 Step 4 |

无 spec 节缺 task 覆盖。

### 2. Placeholder scan

无 TBD / TODO / "appropriate / similar to" / 占位句子。Task 1 Step 3 有一段"过渡示意 + Step 4 重写"的双步设计 — 实际只看 Step 4 的最终版即可,Step 3 仅为说明 race(防 implementer 直接抄 Step 3)。这是有意的设计,**不是 placeholder**。

### 3. Type consistency

- `analyze_single(*, pkl_path, module_path, start_date, end_date, end_role, label_horizon, buf_start=None, buf_end=None)`:Task 1 与 Task 2 一致
- `previewEnabled / preview / previewLoading / previewError`:Task 4 / 5 一致
- `effectiveAnalysis / effectivePattern / effectiveScan`:Task 4 / 6 一致
- `setPreviewEnabled / runPreview / clearPreview`:Task 4 / 5 一致
- `PreviewResp.analysis / summary / pattern_spec / scan`:Task 3 与 Task 4 store 内消费一致
- 三联 guard `previewEnabled.value && preview.value && preview.value.symbol === symbol.value`:三个 computed 严格一致(Task 4 Step 4)
- 四联 disabled `!previewEnabled || !preview || previewLoading || preview.symbol !== symbol`:Task 5 UI `canRefresh` 否定形 + Task 5 测试 5 条 disabled 验证一致

类型 / 名字 / 签名前后一致,无 drift。
