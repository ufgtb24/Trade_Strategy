# Path2 v4 · Class 门机制预留 + Backend Cache 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v3 role-gated debug(已 landed 且 anchor_kind refactor 收编)之上叠加两条独立能力:(A) class 门机制预留 —— `debug_break` 加第二个 required kwarg `class_id`,handler 加 `DEBUG_EVENT_CLASS` env,契约 C(`has_debug_hooks` flag + serialize 派生 `debug_enabled_classes`)让前端未来加 pill 时零猜谜;(B) backend cache —— handler 加 dict cache 消除 sidebar dropdown 切换重跑 root smell,cache-hit 严格 skip detector + skip 写 env,直接消除用户报告的"切换 event_class 反复命中 gate 断点"噪音。

**Architecture:** 双能力并行 · 相互独立可 revert · 都在后端 · 前端零改动(pill UI 休眠 = 不做 pill · sidebar dropdown 语义不变 · cache 自然命中不重跑)。debug_break 判据升级为四门合取:`_DEBUG_MODE ∧ bar in range ∧ (required_anchor_kind is None or match) ∧ (required_class_id is None or match)`。`DEBUG_EVENT_CLASS` env 与既有 `DEBUG_ANCHOR_KIND` 完全独立,未设或空串 = v3 兼容 fallback(任意 class fire)。

**Tech Stack:** Python 3.12(pytest · FastAPI · uv)· Vue 3 + TypeScript(vitest · vue-tsc · vite · 本轮 tiny 改动:types.ts 加一字段)· PyCharm pydevd

**Spec / Design 来源:**
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/final_report.md`(R1-R12 决策 + 载入前提约束 + 一级发现)
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/backend_debug.md` rev3(§8 cache spec · §13 契约 C · §15 minimum viable v4)
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/frontend_ux.md` rev3(§0 契约 C 必需 · §2.5 cache spec)
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/skeptic.md` rev4(cache 独立立项论证 · IDE 断点文档化)

## Global Constraints

**Class_id 词汇(tb baseline · 每 task 都必须使用完全一致的字面量):**
- `'tb'`(小写 · 单引号字符串字面量) —— 今天 tb 是**唯一**挂了 debug_break 的 detector
- 5 处 tb 埋点的 (anchor_kind, class_id) 二维分布 Counter 必等于 `Counter({('gate','tb'):1, ('trough','tb'):1, ('end','tb'):2, ('entry','tb'):1})`
- 若未来加入 bo/burst 埋点,词汇集扩展为 `{'tb','bo','burst'}`,Counter 相应扩展(本轮不实施)

**debug_break 签名(全局强制,v4 演进):**
- `def debug_break(i: int, *, anchor_kind: str, class_id: str) -> None:` — `anchor_kind` 和 `class_id` 都是 required keyword-only,**无 default**
- 缺任一 kwarg 调用 → Python 抛 `TypeError`
- 位置传参 → `TypeError`(keyword-only)

**Debug 判据(debug_break 内部)四门合取:**
```
_DEBUG_MODE=True
  ∧ bar in range
  ∧ (required_anchor_kind is None or required_anchor_kind == anchor_kind)
  ∧ (required_class_id is None or required_class_id == class_id)
```

**Env 契约(v4 = v3 + 第四 env):**
- 既有:`DEBUG_MODE` / `DEBUG_BAR_RANGE` / `DEBUG_ANCHOR_KIND`(v3 已 landed · 不动)
- 新增:`DEBUG_EVENT_CLASS`(handler 按 `event_class` query 设 · 与既有三 env 完全独立)
- `_read_class_id()`:env 未设或空串 → `None`(v3 兼容 fallback · mirror `_read_anchor_kind()`)
- handler 写 env 判据 `if event_class:`(空串也不写 · mirror `if anchor_kind:`)
- handler `finally` **无条件** pop 四 env(既有三 + `DEBUG_EVENT_CLASS`)· 即使本次未写也 pop 兜底 · 防跨 request 污染

**触发 API(fire 分支不变):**
```python
try:
    import pydevd
    pydevd.settrace(suspend=True)
except ImportError:
    breakpoint()
```

**生产零成本(不变):** `_DEBUG_MODE=False` 时 debug_break 第一行 return · pydevd 不 import · env 不读 · anchor_kind/class_id check 不执行。

**契约 C(has_debug_hooks flag · 本轮新增):**
- Detector 类加 `has_debug_hooks: ClassVar[bool] = False`(默认 False · 需在类体上声明为 `ClassVar` · 通过 `from typing import ClassVar` 引入)
- `ThrowbackDetector.has_debug_hooks = True`(唯一挂 debug_break 的 detector 显式标 True)
- `serialize_pattern` 遍历 `spec.nodes[].detector` · 收集 `type(det).has_debug_hooks == True` 的 `event_cls.class_id`,去重后按拓扑序输出为 `debug_enabled_classes: list[str]`,注入 pattern JSON 顶层
- 前端 `SerializedPattern` TS 类型加 `debug_enabled_classes: string[]`(今天单元素 `["tb"]` · 前端本轮不消费 · forward-compat)
- **AST lint 兜底**:`tests/path2/test_debug_break_class_contract.py` 静态扫 `path2/atoms/` 所有 detector 文件 · 若某文件含 `debug_break` call 但对应 detector 类未标 `has_debug_hooks = True` → test fail

**Backend cache 契约(本轮新增 · 与 class 门独立):**
- Handler 加 module-level `_DIAGNOSE_CACHE: dict = {}`(空 dict · 无淘汰 · 本机单用户 dev tool · 见 final_report §载入前提约束)
- Cache 只作用于 `scope is not None` 分支(scope=None 是 legacy 路径,不缓存以保 backward compat)
- Cache key = `(pattern_id, symbol, start, end, scope, src_role, dst_role, event_class, event_id, src_event_id, dst_event_id, edge_id, start_bar, end_bar, anchor_kind, _params_hash(mod.load_params()))`
- Cache value = `(spec, diag, result)` triple(存整个 AnalysisResult · 因 spec 是 rebuild 出来的引用,存也 OK,不存也 OK,存了下次省 rebuild)
- **Cache-hit 严格 spec**:走 `derive_response(query, diag=diag, spec=spec, result=result)` · **不** `attach_and_collect` · **不** `_dag_analyze_engine` · **不** `detach` · **不** 写任何 env · **不** pause · finally 依然 pop 四 env(兜底)
- **Cache-miss**:走既有 v3 路径 · 写 env · 跑 detector · pause · 存入 cache · finally pop env
- `_params_hash(params) -> str`:`hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:8]`(短 hash 用于 key · md5 快而稳)

**测试路径规范(项目约定):**
- pytest 单元测试:`tests/<mirror-source-path>/test_<topic>.py`
- vitest:`path2_web_ui/tests/<prefix>.<topic>.spec.ts`(**不是** src/**/__tests__/**)

**Uv 命令(项目 tooling):** `uv run pytest ...` · `uv run python -m path2_web.main`

**Backend debug port:** 8010(读自 `configs/path2_web.yaml` 的 `backend_port_dbg`)

**Baseline 允许的 pre-existing 失败(不当作回归):**
- pytest baseline 需**每 task 差分测量**(不用 hard 数字 · 用 git stash A/B 证明"改前失败集 == 改后失败集"):`configs/path2_web.yaml` 未提交编辑贡献若干 `tests/path2_web/test_eval_runner.py` 失败;`tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` pre-existing 独立 bug;总 baseline 约 22-44 变动。**不动 `configs/path2_web.yaml`**。
- vitest:2 pre-existing failed(`ScanConfigDialog` · 与本轮无关)

**Web UI 本机单用户前提(载入约束):**
- 本 plan 建立于 "web UI 永远只是本机应用"前提(用户 2026-07-17 明确) · 不做 env → contextvars 迁移 · handler `finally` pop 是充分护栏
- Cache 无淘汰(单进程 · 单用户 dev tool · 不担心内存爆)
- 未来若切换多用户 / SaaS 场景,需重新评估 R11(env → contextvars)+ cache eviction

**Base commit:** `22b90a5`(v3 role gate 5 tasks + M1+M5 fix + anchor_kind refactor 全部 landed 的当前 HEAD;branch `gateA_notwork`;未 push · 未合 master)

**Branch strategy:** v4 继续在 `gateA_notwork` · 每 task 独立 commit(plan 内含 commit 消息)· 不合并 task · 不 push · 不合 master(与 v3 收尾一致)

---

## Task 1: debug_ctx.py 加 class_id kwarg + `_read_class_id()` + 单元测试

**Files:**
- Modify: `path2/debug_ctx.py`
- Modify: `tests/path2/test_debug_ctx.py`(v3 已存在的 19 tests + 新增 class 门 tests)
- Modify: `tests/path2/atoms/test_throwback_debug_hook.py`(lambda stubs 同步补 `class_id=` kwarg · 参 v3 Task 2 follow-up `b92be9e` 类比)

**Interfaces:**
- Produces:
  - `debug_break(i: int, *, anchor_kind: str, class_id: str) -> None` — 双 required kwarg
  - `_read_class_id() -> Optional[str]` — env 未设或空串返 None
- Consumes: 无(纯基础模块)

### Steps

- [ ] **Step 1.1: Read current debug_ctx.py to confirm baseline**

Run: `sed -n '1,60p' path2/debug_ctx.py`

Expected: v3 anchor_kind refactor 后的 60 行结构 · `debug_break(i: int, *, anchor_kind: str)` · `_read_anchor_kind()` · `DEBUG_ANCHOR_KIND` env · 4 处 env 判据。

- [ ] **Step 1.2: Read current test_debug_ctx.py to confirm baseline**

Run: `wc -l tests/path2/test_debug_ctx.py; grep -c "^def test_" tests/path2/test_debug_ctx.py`

Expected: 19 tests(v3 Task 1 的 9 + M1+M5 fix 的 10)· `hits: list[tuple[str, Optional[dict]]] = []` PEP 585 lowercase generics · `fresh_debug_ctx` + `fire_counter` fixtures。

- [ ] **Step 1.3: 追加新测试到 test_debug_ctx.py 末尾**

先读 `tests/path2/test_debug_ctx.py` 末尾 20 行,确认最后一个 test 的位置。然后在文件末尾追加以下测试块(不要覆盖现有测试,只 append):

```python


# ── v4 class 门测试(mirror v3 anchor_kind 测试)──


def test_v1_compat_no_class_env_fires_any_class(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_EVENT_CLASS 未设 → v3 兼容 · 任意 class_id fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="tb")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="bo")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="burst")
    assert len(fire_counter) == 3


def test_v1_compat_empty_class_env_fires_any_class(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_EVENT_CLASS='' 空串 → v3 兼容 fallback · 任意 class_id fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="tb")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="bo")
    assert len(fire_counter) == 2


def test_class_env_tb_only_tb_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_EVENT_CLASS='tb' → 只 class_id='tb' fire · 其他 skip。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "tb")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="tb")    # fire
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="bo")    # skip
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="burst") # skip
    assert len(fire_counter) == 1


def test_class_env_bo_only_bo_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_EVENT_CLASS='bo' → 只 class_id='bo' fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "bo")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="bo")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="tb")
    assert len(fire_counter) == 1


def test_class_id_kwarg_required_typeerror(fresh_debug_ctx):
    """debug_break(i, anchor_kind='gate') 缺 class_id kwarg → TypeError。"""
    with pytest.raises(TypeError, match="class_id"):
        fresh_debug_ctx.debug_break(150, anchor_kind="gate")   # type: ignore[call-arg]


def test_class_id_positional_forbidden_typeerror(fresh_debug_ctx):
    """debug_break(i, 'gate', 'tb') 位置传 class_id → TypeError(keyword-only)。"""
    with pytest.raises(TypeError):
        fresh_debug_ctx.debug_break(150, "gate", "tb")   # type: ignore[misc]


def test_anchor_kind_and_class_id_both_gate(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ANCHOR_KIND='gate' && DEBUG_EVENT_CLASS='tb' → 合取:只 (gate, tb) fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "gate")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "tb")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate",   class_id="tb")    # fire (both match)
    fresh_debug_ctx.debug_break(150, anchor_kind="gate",   class_id="bo")    # skip (class mismatch)
    fresh_debug_ctx.debug_break(150, anchor_kind="trough", class_id="tb")    # skip (anchor mismatch)
    fresh_debug_ctx.debug_break(150, anchor_kind="trough", class_id="bo")    # skip (both mismatch)
    assert len(fire_counter) == 1


def test_class_env_out_of_range_no_fire(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_EVENT_CLASS 匹配但 bar out of range → 不 fire(range 优先短路)。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "tb")
    fresh_debug_ctx.debug_break(50, anchor_kind="gate", class_id="tb")
    assert fire_counter == []
```

- [ ] **Step 1.4: Run new tests to verify they fail**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v -k "class" 2>&1 | tail -30`

Expected: 8 新 class tests **collection error 或 FAIL**(现 `debug_break` 签名不接 `class_id` kwarg · 抛 `TypeError: unexpected keyword argument 'class_id'`;或 `_read_class_id` 不存在)。

- [ ] **Step 1.5: Modify path2/debug_ctx.py 补 class_id kwarg + `_read_class_id()`**

用 Edit 精准替换。先 Edit 文件顶部注释追加 `DEBUG_EVENT_CLASS` 说明:

替换 old:
```python
"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时零成本短路(一次 bool 比较即返)。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8010):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_ANCHOR_KIND="anchor_kind"(v3 新增 · handler 按 anchor_kind query 设):限定命中锚点;未设或空串 = v1 兼容(全 anchor_kind fire)
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
```

new:
```python
"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时零成本短路(一次 bool 比较即返)。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8010):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_ANCHOR_KIND="anchor_kind"(v3 · handler 按 anchor_kind query 设):限定命中锚点;未设或空串 = 全 anchor_kind fire
- DEBUG_EVENT_CLASS="class_id"(v4 新增 · handler 按 event_class query 设):限定命中 detector class;未设或空串 = 全 class fire
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
```

再在 `_read_anchor_kind()` 定义**后**新增 `_read_class_id()`:

替换 old:
```python
def _read_anchor_kind() -> Optional[str]:
    """读 DEBUG_ANCHOR_KIND env · 未设或空串返 None(v1 兼容 fallback:不做 anchor_kind 匹配)。"""
    r = os.environ.get("DEBUG_ANCHOR_KIND")
    return r if r else None


def debug_break(i: int, *, anchor_kind: str) -> None:
```

new:
```python
def _read_anchor_kind() -> Optional[str]:
    """读 DEBUG_ANCHOR_KIND env · 未设或空串返 None(v1 兼容 fallback:不做 anchor_kind 匹配)。"""
    r = os.environ.get("DEBUG_ANCHOR_KIND")
    return r if r else None


def _read_class_id() -> Optional[str]:
    """读 DEBUG_EVENT_CLASS env · 未设或空串返 None(v3 兼容 fallback:不做 class_id 匹配)。"""
    r = os.environ.get("DEBUG_EVENT_CLASS")
    return r if r else None


def debug_break(i: int, *, anchor_kind: str, class_id: str) -> None:
```

再更新 `debug_break` docstring + 内部逻辑。替换 old:
```python
    """在 detector 埋点处调用:DEBUG_MODE=1 且 i 落在 DEBUG_BAR_RANGE 内且 anchor_kind 匹配 → 触发 pause。

    v3(2026-07-16)required keyword-only anchor_kind 参数:
    - DEBUG_ANCHOR_KIND 未设或空串 → 只按 range 匹配(v1 兼容 · 全 anchor_kind fire)
    - DEBUG_ANCHOR_KIND 设了 → range 匹配 && anchor_kind 字面量匹配 · 才 fire
    - 缺 anchor_kind kwarg → Python 抛 TypeError(required · 无 default)

    优先 pydevd.settrace(suspend=True)——PyCharm 显式 pause API · 每次都 fire;
    breakpoint() 在 pydevd 下同一源码位置只报告一次 · 二次触发会静默 fall through
    (实测 2026-07-16 sync+async 皆然)· 故仅在无 pydevd(非 PyCharm 启动)时兜底。
    _DEBUG_MODE=False 时函数第一行 return · pydevd 不 import · 生产零成本。
    """
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if not (r[0] <= i <= r[1]):
        return
    required = _read_anchor_kind()
    if required is not None and required != anchor_kind:
        return
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

new:
```python
    """在 detector 埋点处调用:四门合取通过时触发 pause。

    v4(2026-07-17)双 required keyword-only 参数:
    - anchor_kind:5 元 enum(gate/trough/end/entry)· detector 内部锚点位置
    - class_id  :detector event 的 class_id · 如 'tb'/'bo'/'burst'
    - 缺任一 kwarg → Python 抛 TypeError(required · 无 default)

    判据(短路顺序):
      _DEBUG_MODE ∧ bar in range
        ∧ (DEBUG_ANCHOR_KIND 未设 or 匹配 anchor_kind)
        ∧ (DEBUG_EVENT_CLASS 未设 or 匹配 class_id)

    优先 pydevd.settrace(suspend=True)——PyCharm 显式 pause API · 每次都 fire;
    breakpoint() 在 pydevd 下同一源码位置只报告一次 · 二次触发会静默 fall through
    (实测 2026-07-16 sync+async 皆然)· 故仅在无 pydevd(非 PyCharm 启动)时兜底。
    _DEBUG_MODE=False 时函数第一行 return · pydevd 不 import · 生产零成本。
    """
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if not (r[0] <= i <= r[1]):
        return
    required_ak = _read_anchor_kind()
    if required_ak is not None and required_ak != anchor_kind:
        return
    required_cid = _read_class_id()
    if required_cid is not None and required_cid != class_id:
        return
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

- [ ] **Step 1.6: Run new tests to verify they pass**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v -k "class" 2>&1 | tail -30`

Expected: 8 新 class tests 全部 PASS。

- [ ] **Step 1.7: Run full test_debug_ctx.py 确认 v3 老测试无回归**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v 2>&1 | tail -40`

Expected: 27 tests(19 老 + 8 新) 全部 PASS。若任一 v3 老测试 fail,回退检查 Step 1.5 修改是否影响了 `_read_range` / `_read_anchor_kind` 行为(不该动 · 只 append 新函数)。

- [ ] **Step 1.8: Fix test_throwback_debug_hook.py lambda stubs**

v3 Task 2 follow-up 修过一次(`b92be9e`),lambda 只接受 `anchor_kind` kwarg。本轮加 `class_id`,lambda 也要同步。

Run: `grep -n "lambda i" tests/path2/atoms/test_throwback_debug_hook.py`

Expected: 2 处 lambda stub · 形如 `lambda i, *, anchor_kind: calls.append(i)`。

用 Edit 替换 all(2 处):

替换 old:
```python
lambda i, *, anchor_kind: calls.append(i)
```

new:
```python
lambda i, *, anchor_kind, class_id: calls.append(i)
```

用 Edit 的 `replace_all: true` 一次替 2 处。

- [ ] **Step 1.9: Regression — verify no other test breaks from debug_ctx change**

Run: `uv run pytest tests/path2/ tests/path2_web/ 2>&1 | tail -20`

Expected: 之前的 pre-existing failures 仍以同样理由失败(baseline 与改前一致)· **无新失败** · 特别注意:因为 debug_break 现在 required 双 kwarg · 若旧代码调用 `debug_break(x, anchor_kind='...')` 无 `class_id` · Python 会抛 TypeError · 但这只会在 detector 实际调用时触发。若有 test 因此挂 · 那是**预期**(Task 2 会修 throwback 5 处补 `class_id='tb'`)· 记录挂的 test 名 · 留 Task 2 后验证复绿。

推荐做 A/B 差分:
```bash
# baseline (回退到 22b90a5)
git stash push -m "task1-wip"
uv run pytest tests/path2/ tests/path2_web/ 2>&1 | grep -c "^FAILED" > /tmp/baseline_fails
git stash pop
# 改后
uv run pytest tests/path2/ tests/path2_web/ 2>&1 | grep -c "^FAILED" > /tmp/task1_fails
diff /tmp/baseline_fails /tmp/task1_fails
```

Expected diff: Task 1 后失败数 = baseline + N(N ≈ throwback 相关测试的 tb 埋点调用数)· 全部为 `TypeError: missing class_id` · Task 2 后归零。

- [ ] **Step 1.10: Commit**

```bash
git add path2/debug_ctx.py tests/path2/test_debug_ctx.py tests/path2/atoms/test_throwback_debug_hook.py
git commit -m "$(cat <<'EOF'
feat(debug): v4 · class 门 · debug_break 加 required kwarg class_id + DEBUG_EVENT_CLASS env

- _read_class_id() 读 DEBUG_EVENT_CLASS env · 未设或空串返 None(v3 兼容 fallback)
- debug_break 签名扩为 (i: int, *, anchor_kind: str, class_id: str) · 双 required kwarg · 无 default
- 判据升级为四门合取:_DEBUG_MODE ∧ range ∧ anchor_kind 门 ∧ class_id 门
- fire API 不变:pydevd.settrace(suspend=True) · ImportError fallback breakpoint()
- 生产零成本仍成立:_DEBUG_MODE=False 时第一行 return · pydevd 不 import

test_throwback_debug_hook.py 2 处 lambda stub 同步补 class_id kwarg(mirror v3 b92be9e)。

单元测试新增 8 case(v3 兼容/class 门/双 kwarg required/合取匹配/range 短路优先)· 共 27 tests(19 v3 老 + 8 v4 新)全绿。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: throwback.py 5 处补 `class_id='tb'` + AST 契约测试

**Files:**
- Modify: `path2/atoms/throwback.py`(5 处 debug_break call · L104 / L163 / L219 / L224 / L250)
- Modify: `tests/path2/atoms/test_throwback_debug_roles.py`(v3 已存在的 AST Counter test · 扩为二维 (anchor_kind, class_id) Counter)

**Interfaces:**
- Consumes: Task 1 的 `debug_break(i: int, *, anchor_kind: str, class_id: str) -> None`
- Produces: 无(埋点契约的锚点)

### Steps

- [ ] **Step 2.1: Read current throwback.py debug_break sites**

Run: `grep -n "debug_break" path2/atoms/throwback.py`

Expected: 5 处调用 · 分别在约 L104 / L163 / L219 / L224 / L250(anchor_kind refactor 后可能有 ±5 行漂移)· 每处形如 `debug_break(<expr>, anchor_kind='<literal>')` 无 `class_id` kwarg。

- [ ] **Step 2.2: Read current test_throwback_debug_roles.py to confirm baseline**

Run: `wc -l tests/path2/atoms/test_throwback_debug_roles.py; grep -n "EXPECTED_" tests/path2/atoms/test_throwback_debug_roles.py`

Expected: v3 landed 的 AST 契约 test · 有 `EXPECTED_ANCHOR_KIND_COUNTER = Counter({'gate':1, 'trough':1, 'end':2, 'entry':1})`(变量名可能是 `EXPECTED_ROLE_COUNTER` 若 anchor_kind refactor 未同步改测试变量名 · 见 Step 2.5 需处理)。

- [ ] **Step 2.3: Modify path2/atoms/throwback.py 5 处 debug_break call**

对每处逐个 Edit(用现有 Edit tool · 保留原注释)。**行号是 anchor_kind refactor 后的 approx · Grep 定位实际行号后修改。**

L104 附近(gate):
```python
# 旧:
debug_break(gate_idx, anchor_kind='gate')
# 改:
debug_break(gate_idx, anchor_kind='gate', class_id='tb')
```

L163 附近(trough):
```python
# 旧:
debug_break(trough_idx, anchor_kind='trough')  # v2 · phase1 success(与 event.start_idx 对齐)
# 改:
debug_break(trough_idx, anchor_kind='trough', class_id='tb')  # v2 · phase1 success(与 event.start_idx 对齐)
```

L219 附近(end · phase2 rise):
```python
# 旧:
debug_break(i - 1, anchor_kind='end')  # v2 · phase2 rise end(⚠ i-1 与 event.end_idx 对齐, 非 i)
# 改:
debug_break(i - 1, anchor_kind='end', class_id='tb')  # v2 · phase2 rise end(⚠ i-1 与 event.end_idx 对齐, 非 i)
```

L224 附近(end · phase2 timeout):
```python
# 旧:
debug_break(end_scan, anchor_kind='end')  # v2 · phase2 timeout end(与 event.end_idx 对齐)
# 改:
debug_break(end_scan, anchor_kind='end', class_id='tb')  # v2 · phase2 timeout end(与 event.end_idx 对齐)
```

L250 附近(entry):
```python
# 旧:
debug_break(bo_idx, anchor_kind='entry')  # v2 · attempt entry(dead code when _DEBUG_MODE=False)
# 改:
debug_break(bo_idx, anchor_kind='entry', class_id='tb')  # v2 · attempt entry(dead code when _DEBUG_MODE=False)
```

- [ ] **Step 2.4: 扩展 AST 契约 test 为二维 Counter**

先 Read 现测试文件全文:`cat tests/path2/atoms/test_throwback_debug_roles.py`

保留现有 3 tests(count/kwarg-is-literal/anchor_kind Counter),追加 2 个新 test 覆盖 class_id 维度 + 二维联合。

用 Edit 精准追加(在文件末尾追加,或将 `EXPECTED_*_COUNTER` 一起改)。参考 v3 Task 2 的 AST 结构。

若现文件用变量名 `EXPECTED_ROLE_COUNTER`(anchor_kind refactor 未同步改测试变量名),先用 Edit 改为 `EXPECTED_ANCHOR_KIND_COUNTER`,并在 test 里同步使用新名(此步 optional · 是清理项 · 不做也不阻塞)。

**追加以下测试块**(在文件末尾):
```python


EXPECTED_CLASS_ID_COUNTER = Counter({"tb": 5})   # 5 处 tb 埋点 · 全部 class_id='tb'
EXPECTED_JOINT_COUNTER = Counter({
    ("gate",   "tb"): 1,
    ("trough", "tb"): 1,
    ("end",    "tb"): 2,
    ("entry",  "tb"): 1,
})


def test_every_debug_break_has_class_id_kwarg_as_str_literal():
    """契约 · 每处 debug_break 必带 class_id kwarg 且是 str literal(grep-ability)。"""
    calls = _collect_debug_break_calls()
    for c in calls:
        class_kw = next((k for k in c.keywords if k.arg == "class_id"), None)
        assert class_kw is not None, (
            f"L{c.lineno} debug_break missing required class_id kwarg"
        )
        assert isinstance(class_kw.value, ast.Constant) and isinstance(class_kw.value.value, str), (
            f"L{c.lineno} class_id must be str literal (for grep-ability) · got "
            f"{ast.dump(class_kw.value)}"
        )


def test_throwback_class_id_distribution_matches_baseline():
    """class_id 分布 Counter 严格等于 baseline · throwback 全 tb。"""
    calls = _collect_debug_break_calls()
    class_ids = [
        next(k.value.value for k in c.keywords if k.arg == "class_id")
        for c in calls
    ]
    actual = Counter(class_ids)
    assert actual == EXPECTED_CLASS_ID_COUNTER, (
        f"class_id distribution mismatch:\n"
        f"  expected {dict(EXPECTED_CLASS_ID_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"class_ids: {class_ids}"
    )


def test_throwback_joint_distribution_matches_baseline():
    """(anchor_kind, class_id) 二维联合 Counter 严格等于 baseline。"""
    calls = _collect_debug_break_calls()
    joint = [
        (
            next(k.value.value for k in c.keywords if k.arg == "anchor_kind"),
            next(k.value.value for k in c.keywords if k.arg == "class_id"),
        )
        for c in calls
    ]
    actual = Counter(joint)
    assert actual == EXPECTED_JOINT_COUNTER, (
        f"(anchor_kind, class_id) joint distribution mismatch:\n"
        f"  expected {dict(EXPECTED_JOINT_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"pairs: {joint}"
    )
```

- [ ] **Step 2.5: Run 契约锚 test to verify it passes**

Run: `uv run pytest tests/path2/atoms/test_throwback_debug_roles.py -v`

Expected: 6 tests(3 v3 老 + 3 v4 新) 全部 PASS。若 Step 2.4 里保留了 `EXPECTED_ROLE_COUNTER` 命名而 v3 tests 用了 `EXPECTED_ANCHOR_KIND_COUNTER`(或反),Grep 定位实际命名并保持一致。

- [ ] **Step 2.6: Regression — 全 throwback suite 复绿**

Run: `uv run pytest tests/path2/atoms/ -v 2>&1 | tail -20`

Expected: throwback 相关全部 pass(pre-existing v2 baseline)· 之前 Task 1 Step 1.9 记录的 TypeError 挂点应全部复绿(因为现在 throwback 的 5 处 debug_break 都带 `class_id='tb'`,与 Task 1 double-required kwarg 签名匹配)。

`tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` 仍是 pre-existing 失败(anchor_kind refactor 之前就存在的独立 assertion bug · 不在本轮 scope)。

- [ ] **Step 2.7: Commit**

```bash
git add path2/atoms/throwback.py tests/path2/atoms/test_throwback_debug_roles.py
git commit -m "$(cat <<'EOF'
feat(debug): v4 · throwback 5 处 debug_break 补 class_id='tb' + AST 二维契约锚测试

- 5 处 tb 埋点全部追加 class_id='tb'(mirror v3 anchor_kind 模板)
- (anchor_kind, class_id) 二维 Counter = {('gate','tb'):1, ('trough','tb'):1, ('end','tb'):2, ('entry','tb'):1}
- 契约锚 test 新增 3 case:class_id 必是 str literal · class_id Counter · 二维联合 Counter
- 补 class_id 后与 Task 1 双 required kwarg 签名匹配 · 消除 Task 1 遗留 TypeError

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: /diagnose handler 消费 event_class 写 DEBUG_EVENT_CLASS env + finally pop 三 env

**Files:**
- Modify: `path2_web/api.py`(get_diagnose handler · L198-256 附近)
- Create: `tests/path2_web/test_diagnose_class_env.py`

**Interfaces:**
- Consumes: Task 1 `debug_break` · Task 2 throwback class_id kwarg
- Produces: `/diagnose` HTTP endpoint 消费既有 `event_class` query 参数 → 写 `DEBUG_EVENT_CLASS` env(既有的 serialize filter 语义**并行保留**,不冲突)

### Steps

- [ ] **Step 3.1: Read current handler**

Run: `sed -n '198,256p' path2_web/api.py`

Expected: v3 handler 结构 · sync def · 已有 `event_class: Optional[str] = None` 参数(用于 serialize filter · 见 api.ts:51 注释"按 class_id 二次过滤")· `if anchor_kind:` 写 env · finally pop 两 env。

**关键判断:** `event_class` 参数已存在(v3 前就有),但目前**只用于 serialize 层的 Query filter**,不写 env。本轮改动 = **不改语义** · 只在 `if anchor_kind:` 之后追加 `if event_class:` 写 `DEBUG_EVENT_CLASS` env · finally 增加一行 pop。既有 serialize filter 语义原封不动。

- [ ] **Step 3.2: Create failing handler test**

Create `tests/path2_web/test_diagnose_class_env.py`:

```python
"""v4 handler class 门 env + finally 三 env pop 测试(mirror v3 test_diagnose_role_env.py)。

覆盖:
- event_class query 写 env DEBUG_EVENT_CLASS(非空)
- 无 event_class query · 不写 DEBUG_EVENT_CLASS env
- 空串 event_class · 不写 DEBUG_EVENT_CLASS env(handler 判据 `if event_class:`)
- finally 无条件 pop 三 env(DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND + DEBUG_EVENT_CLASS)
- 跨 request 隔离:上次 preset DEBUG_EVENT_CLASS · 本次不传 event_class · finally 依然 pop 兜底
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带真实数据的 test client(复用 v3 test_diagnose_role_env.py 同构 fixture)。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)
    monkeypatch.delenv("DEBUG_EVENT_CLASS", raising=False)

    data = tmp_path / "data"
    data.mkdir()
    n = 300
    # 构造一段真实突破:前 200 bar 平盘,201-220 上冲,后续回踩
    dates = pd.date_range("2024-01-01", periods=n)
    close = np.concatenate([
        np.full(200, 10.0),
        np.linspace(10.0, 15.0, 20),
        np.full(80, 13.0),
    ])
    df = pd.DataFrame({
        "date": dates, "open": close, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": [100.0] * n,
    }).set_index("date")
    df.to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-10-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


def _diagnose_url(event_class: str | None = None, start_bar: int = 0, end_bar: int = 280):
    q = ("pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-10-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if event_class is not None:
        q += f"&event_class={event_class}"
    return f"/diagnose?{q}"


def test_event_class_query_writes_debug_event_class_env(client, monkeypatch):
    """GET ?event_class=tb · handler try 期间 env DEBUG_EVENT_CLASS 写入。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class="tb"))
    assert r.status_code == 200
    assert "tb" in captured, f"expected 'tb' in captured env values, got {captured}"


def test_no_event_class_query_does_not_write_debug_event_class_env(client, monkeypatch):
    """GET 不传 event_class · handler 不写 DEBUG_EVENT_CLASS env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class=None))
    assert r.status_code == 200
    assert len(captured) > 0, "spy never observed debug_break call · fixture broken"
    assert all(v is None for v in captured), (
        f"expected DEBUG_EVENT_CLASS unset for all captured, got {captured}"
    )


def test_empty_event_class_query_does_not_write_debug_event_class_env(client, monkeypatch):
    """GET ?event_class= 空串 · handler 判据 `if event_class:` · 不写 env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class=""))
    assert r.status_code == 200
    assert len(captured) > 0, "spy never observed debug_break call · fixture broken"
    assert all(v is None for v in captured), (
        f"expected DEBUG_EVENT_CLASS unset (empty event_class treated as unset), got {captured}"
    )


def test_finally_pops_all_three_envs_on_success(client):
    """handler 正常返回后 · 三 env 都 pop 清 · 无残留。"""
    r = client.get(_diagnose_url(event_class="tb"))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_BAR_RANGE") is None
    assert os.environ.get("DEBUG_ANCHOR_KIND") is None
    assert os.environ.get("DEBUG_EVENT_CLASS") is None


def test_finally_pops_debug_event_class_env_bootstrap_pollution(client, monkeypatch):
    """跨 request 隔离:preset DEBUG_EVENT_CLASS='stale' · 本次不传 event_class · finally 依然 pop 兜底
    (无条件 pop DEBUG_EVENT_CLASS · 不管本次是否写过)。"""
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "stale")
    r = client.get(_diagnose_url(event_class=None))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_EVENT_CLASS") is None, (
        "handler finally should pop DEBUG_EVENT_CLASS unconditionally to prevent "
        "cross-request pollution"
    )
```

- [ ] **Step 3.3: Run test to verify it fails**

Run: `uv run pytest tests/path2_web/test_diagnose_class_env.py -v 2>&1 | tail -30`

Expected: 5/5 FAIL(现 handler 不写 `DEBUG_EVENT_CLASS` · finally 也不 pop 它)。

- [ ] **Step 3.4: Modify path2_web/api.py handler**

用 Edit 精准替换,在 `if anchor_kind:` 分支**后**追加 event_class 分支,在 finally 增加一行 pop。

替换 old:
```python
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if anchor_kind:                             # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ANCHOR_KIND"] = anchor_kind
```

new:
```python
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if anchor_kind:                             # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ANCHOR_KIND"] = anchor_kind
        if event_class:                             # ★ v4 · 空串也视同未传
            os.environ["DEBUG_EVENT_CLASS"] = event_class
```

替换 old:
```python
        # ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env,
        # undefined under concurrency, single-user debug tool.
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)  # ★ v3 · 无条件 pop 兜底(跨 request 隔离)
```

new:
```python
        # ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env,
        # undefined under concurrency, single-user debug tool.
        # v4(2026-07-17 class-gate)契约扩展:第四 env DEBUG_EVENT_CLASS 同 finally 无条件 pop。
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)   # ★ v3 · 无条件 pop 兜底
            os.environ.pop("DEBUG_EVENT_CLASS", None)   # ★ v4 · 无条件 pop 兜底(跨 request 隔离)
```

**注意:** `event_class` 参数**在 v3 已存在**(用于 serialize 层 `Query.event_class` filter · 见 L244 的 `Query(..., event_class=event_class, ...)`)· 本轮**不改**该语义,只**并行添加**写 env 逻辑。既有的 serialize filter 行为原封不动。

- [ ] **Step 3.5: Run test to verify it passes**

Run: `uv run pytest tests/path2_web/test_diagnose_class_env.py -v 2>&1 | tail -20`

Expected: 5/5 PASS。

- [ ] **Step 3.6: Regression — verify existing v3 handler tests still pass**

Run: `uv run pytest tests/path2_web/test_diagnose_role_env.py tests/path2_web/test_diagnose_role_integration.py tests/path2_web/test_diagnose_finally_pop.py tests/path2_web/test_debug_env_injection.py -v 2>&1 | tail -20`

Expected: v3 全部 pass · 无新回归。之前 pre-existing failures 仍以同理由失败。

- [ ] **Step 3.7: Commit**

```bash
git add path2_web/api.py tests/path2_web/test_diagnose_class_env.py
git commit -m "$(cat <<'EOF'
feat(diagnose): v4 · handler 消费 event_class 写 DEBUG_EVENT_CLASS env + finally 三 env pop

- get_diagnose 既有 event_class 参数 v3 前就有(serialize 层 filter)· 本轮**并行**写 env · 语义不冲突
- 写 env 判据 `if event_class:` · 空串视同未传(不写 DEBUG_EVENT_CLASS env · mirror anchor_kind)
- finally 无条件 pop 三 env(DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND + DEBUG_EVENT_CLASS)· 兜底跨 request 污染
- v4 契约扩展:三 env 独立 pop · 与 v3 契约兼容(无 event_class 时 debug 行为等价 v3)
- v3 兼容:不传 event_class → DEBUG_EVENT_CLASS 不设 → debug_ctx 全 class fire

单元测试覆盖:event_class 写 env · 无/空串不写 · 正常路径 finally pop · 跨 request preset 污染兜底 pop。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 契约 C(`has_debug_hooks` flag + `serialize_pattern` 派生 `debug_enabled_classes` + AST lint + types.ts)

**Files:**
- Modify: `path2/atoms/throwback.py`(`ThrowbackDetector` 类加 `has_debug_hooks: ClassVar[bool] = True`)
- Modify: `path2/atoms/breakout.py`(`BurstDetector` / `BODetector` 类各加 `has_debug_hooks: ClassVar[bool] = False`)
- Modify: `path2/atoms/trend.py`(`TrendSegmentDetector` 加 flag = False)
- Modify: `path2/atoms/platform.py`(`PlatformDetector` 加 flag = False)
- Modify: `path2/atoms/distribution.py`(`DistributionDetector` 加 flag = False)
- Modify: `path2_web/serialize.py`(`serialize_pattern` 派生 `debug_enabled_classes`)
- Modify: `path2_web_ui/src/types.ts`(`SerializedPattern` 加 `debug_enabled_classes: string[]` 字段)
- Create: `tests/path2/test_debug_break_class_contract.py`(AST lint · 跨 detector 通用契约)
- Create: `tests/path2_web/test_serialize_debug_enabled_classes.py`(serialize 契约 test)

**Interfaces:**
- Consumes: Task 1 `debug_break` · Task 2 throwback class_id kwarg
- Produces: 
  - `Detector.has_debug_hooks: ClassVar[bool]` 类属性契约(默认 False · 埋 debug_break 时同 diff 改 True)
  - `SerializedPattern.debug_enabled_classes: list[str]`(pattern JSON 顶层字段 · 今天单元素 `["tb"]`)
  - AST lint 测试:任何 detector 文件含 `debug_break` call 但类未标 `has_debug_hooks=True` → test fail

### Steps

- [ ] **Step 4.1: Read all detector classes to confirm structure**

Run:
```bash
grep -n "^class .*Detector\|^class .*(BarwiseDetector)" path2/atoms/*.py
```

Expected: 5 个 detector 类:
- `path2/atoms/breakout.py:109:class BurstDetector`
- `path2/atoms/breakout.py:204:class BODetector(BarwiseDetector)`
- `path2/atoms/distribution.py:28:class DistributionDetector(BarwiseDetector)`
- `path2/atoms/platform.py:28:class PlatformDetector`
- `path2/atoms/throwback.py:283:class ThrowbackDetector`
- `path2/atoms/trend.py:28:class TrendSegmentDetector`

- [ ] **Step 4.2: Create failing AST lint test**

Create `tests/path2/test_debug_break_class_contract.py`:

```python
"""v4 契约 C AST lint · 跨 detector 通用契约测试。

契约:
- path2/atoms/ 下任何 .py 文件,若含 `debug_break(...)` call → 该文件里的 Detector 类必须
  显式标注 `has_debug_hooks: ClassVar[bool] = True`
- 无 debug_break call 的 detector 类应保持默认 has_debug_hooks = False(不强测,只测有 hook 侧)
- 允许多个 Detector 类共存于一文件(如 breakout.py 有 BurstDetector + BODetector)· lint 只要求
  "有 debug_break call 的文件里至少一个类标 True"(粗粒度 · 避免 false-positive)

严格版可选:
- 若未来加多 Detector 分层的判断(比如 breakout.py 里只有 BODetector 有 hook,BurstDetector 无),
  可以升级为"标 True 的类等于埋 debug_break 的类"· 本轮不做(YAGNI · 今天 tb 一家)。
"""
import ast
import pathlib


ATOMS_DIR = pathlib.Path(__file__).resolve().parents[1] / "path2" / "atoms"


def _module_has_debug_break_call(module_path: pathlib.Path) -> bool:
    src = module_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "debug_break":
            return True
    return False


def _module_has_hooks_flag_true(module_path: pathlib.Path) -> bool:
    """检查文件里是否至少一个类体上有 `has_debug_hooks: ClassVar[bool] = True`
    或 `has_debug_hooks = True`(不强制 ClassVar 注解,只强制值 True)。"""
    src = module_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(module_path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            # AnnAssign: has_debug_hooks: ClassVar[bool] = True
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) \
                    and stmt.target.id == "has_debug_hooks" \
                    and stmt.value is not None \
                    and isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                return True
            # Assign: has_debug_hooks = True
            if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "has_debug_hooks" for t in stmt.targets) \
                    and isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                return True
    return False


def test_every_debug_break_module_has_hooks_flag_true():
    """任何 detector 文件含 debug_break call → 至少一个类标 has_debug_hooks=True。"""
    offenders = []
    for py in sorted(ATOMS_DIR.glob("*.py")):
        if py.name == "__init__.py":
            continue
        if _module_has_debug_break_call(py) and not _module_has_hooks_flag_true(py):
            offenders.append(py.name)
    assert not offenders, (
        f"以下 detector 文件含 debug_break 调用但没有类标 has_debug_hooks=True:\n"
        f"  {offenders}\n"
        f"契约 C 要求:埋 debug_break 时同 diff 在类体上加 `has_debug_hooks: ClassVar[bool] = True`"
    )


def test_throwback_module_marks_flag_true():
    """具体校验 throwback.py 已标(guard against false-positive from粗粒度 lint)。"""
    assert _module_has_hooks_flag_true(ATOMS_DIR / "throwback.py")
```

- [ ] **Step 4.3: Create failing serialize contract test**

Create `tests/path2_web/test_serialize_debug_enabled_classes.py`:

```python
"""v4 契约 C · serialize_pattern 派生 debug_enabled_classes 契约测试。

契约:
- serialize_pattern(spec) 返回 dict 里必有 `debug_enabled_classes: list[str]` 顶层字段
- 值 = spec.nodes 里 detector 类 has_debug_hooks=True 的 event_cls.class_id 去重、按拓扑序
- 今天 bottom_burst pattern 里:
  - `bo` (BODetector, has_debug_hooks=False) → 不含
  - `burst` (BurstDetector, has_debug_hooks=False) → 不含
  - `tb` (ThrowbackDetector, has_debug_hooks=True) → 含
  → 期望 `debug_enabled_classes = ["tb"]`
"""
import pytest


def test_bottom_burst_pattern_debug_enabled_classes_is_tb_only():
    from path2_apps.bottom_breakout_burst import build_pattern, load_params

    from path2_web.serialize import serialize_pattern

    spec = build_pattern(load_params())
    payload = serialize_pattern(spec)

    assert "debug_enabled_classes" in payload, (
        "契约 C 要求 serialize_pattern 输出顶层含 debug_enabled_classes 字段"
    )
    assert payload["debug_enabled_classes"] == ["tb"], (
        f"bottom_burst 今天只 tb 一家标 has_debug_hooks=True · 期望 ['tb'] · "
        f"实际 {payload['debug_enabled_classes']}"
    )


def test_debug_enabled_classes_list_type_and_uniqueness():
    """字段类型 = list[str] · 元素去重(即使同一 class_id 挂多 node 也只出现一次)。"""
    from path2_apps.bottom_breakout_burst import build_pattern, load_params

    from path2_web.serialize import serialize_pattern

    spec = build_pattern(load_params())
    payload = serialize_pattern(spec)
    dec = payload["debug_enabled_classes"]

    assert isinstance(dec, list)
    assert all(isinstance(x, str) for x in dec)
    assert len(dec) == len(set(dec)), f"debug_enabled_classes 应去重 · got {dec}"
```

- [ ] **Step 4.4: Run new tests to verify they fail**

Run: `uv run pytest tests/path2/test_debug_break_class_contract.py tests/path2_web/test_serialize_debug_enabled_classes.py -v 2>&1 | tail -20`

Expected: 
- `test_every_debug_break_module_has_hooks_flag_true` FAIL(throwback.py 有 debug_break 但类未标 True)
- `test_throwback_module_marks_flag_true` FAIL
- `test_bottom_burst_pattern_debug_enabled_classes_is_tb_only` FAIL(serialize_pattern 尚未加字段)
- `test_debug_enabled_classes_list_type_and_uniqueness` FAIL(同上)

- [ ] **Step 4.5: Add `has_debug_hooks` ClassVar 到 5 个 detector 类**

先给 **ThrowbackDetector** 加 `True`(唯一有 debug_break 的),其余 4 个加 `False`(default · forward-compat 显式声明避免 test 误认 default 是"未声明")。

**注意 ClassVar 需要 import:** 5 个 detector 文件都需要 `from typing import ClassVar`(如已 import 则跳过)。

对每个 detector 文件:

**path2/atoms/throwback.py**(约 L283):

Read 现类头:
```python
class ThrowbackDetector:
    """throwback detector: ..."""
    # existing body
```

在类体第一行(docstring 后)加:
```python
class ThrowbackDetector:
    """throwback detector: ..."""
    has_debug_hooks: ClassVar[bool] = True
    # existing body
```

顶部 import 补(若已有 ClassVar 则跳过):
```python
from typing import ClassVar
```

**path2/atoms/breakout.py**(2 个类 · 约 L109 BurstDetector + L204 BODetector):

两处都加 `has_debug_hooks: ClassVar[bool] = False`(默认 · 显式声明便于未来埋 debug_break 时改 True)。

**path2/atoms/distribution.py / platform.py / trend.py**:各加 `has_debug_hooks: ClassVar[bool] = False`。

- [ ] **Step 4.6: Modify `path2_web/serialize.py::serialize_pattern` 派生 `debug_enabled_classes`**

在 `serialize_pattern` 函数体末尾 return dict **前**加 `debug_enabled_classes` 派生,并在 return dict 里加字段。

替换 old:
```python
    return {
        "pattern_id": spec.pattern_id,
        "topology": {"nodes": nodes, "edges": edges},
        "event_styles": _event_styles(spec, topo),
    }
```

new:
```python
    # v4 契约 C:派生 debug_enabled_classes(has_debug_hooks=True 的 detector 的 class_id 去重,拓扑序)
    debug_enabled_classes: list[str] = []
    seen: set[str] = set()
    for n in spec.nodes:
        det_cls = type(n.detector)
        if getattr(det_cls, "has_debug_hooks", False) and hasattr(n.detector, "event_cls"):
            cid = n.detector.event_cls.class_id
            if cid not in seen:
                seen.add(cid)
                debug_enabled_classes.append(cid)

    return {
        "pattern_id": spec.pattern_id,
        "topology": {"nodes": nodes, "edges": edges},
        "event_styles": _event_styles(spec, topo),
        "debug_enabled_classes": debug_enabled_classes,
    }
```

- [ ] **Step 4.7: Modify `path2_web_ui/src/types.ts` 加 debug_enabled_classes 字段**

Read `types.ts` 找 `SerializedPattern` 定义(约 L12-15)。

替换 old:
```typescript
export interface SerializedPattern {
  pattern_id: string
  topology: Topology; event_styles: Record<string, string>
}
```

new:
```typescript
export interface SerializedPattern {
  pattern_id: string
  topology: Topology; event_styles: Record<string, string>
  debug_enabled_classes: string[]        // ★ v4 契约 C · 挂了 debug_break 的 class_id 列表(拓扑序 · 去重)
}
```

- [ ] **Step 4.8: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_debug_break_class_contract.py tests/path2_web/test_serialize_debug_enabled_classes.py -v 2>&1 | tail -20`

Expected: 4 tests 全部 PASS。

- [ ] **Step 4.9: Regression — 全 path2 + path2_web pytest suite**

Run: `uv run pytest tests/path2/ tests/path2_web/ 2>&1 | tail -20`

Expected: 无新回归 · baseline pre-existing failures 数字不变。

- [ ] **Step 4.10: Regression — frontend gates**

Run: `cd path2_web_ui && npx vue-tsc --noEmit 2>&1 | tail -10`

Expected: TS 编译 clean(SerializedPattern 加字段 · 前端消费者今天不消费也不 break · 因为都是可选读)。

若 vue-tsc 报错(某处 consumer 强解构 SerializedPattern),补类型或改为可选访问。极小概率 · 若发生记录到 Task 4 fix step。

Run: `cd path2_web_ui && npm run build 2>&1 | tail -10`

Expected: build 成功。

Run: `cd path2_web_ui && npx vitest run 2>&1 | tail -20`

Expected: 全 vitest 绿(除 baseline 2 个 ScanConfigDialog pre-existing)· 无新回归。

- [ ] **Step 4.11: Commit**

```bash
git add path2/atoms/throwback.py path2/atoms/breakout.py path2/atoms/distribution.py \
        path2/atoms/platform.py path2/atoms/trend.py \
        path2_web/serialize.py path2_web_ui/src/types.ts \
        tests/path2/test_debug_break_class_contract.py \
        tests/path2_web/test_serialize_debug_enabled_classes.py
git commit -m "$(cat <<'EOF'
feat(contract-C): v4 · has_debug_hooks ClassVar + serialize 派生 debug_enabled_classes + AST lint

- 5 个 detector 类加 has_debug_hooks: ClassVar[bool] · ThrowbackDetector=True · 其余=False
- serialize_pattern 遍历 spec.nodes 派生 debug_enabled_classes: list[str] · 去重按拓扑序 · 今天 = ['tb']
- SerializedPattern TS 类型加 debug_enabled_classes: string[] · 前端本轮不消费(pill UI 休眠) · forward-compat
- AST lint 兜底 tests/path2/test_debug_break_class_contract.py · 任何 detector 文件含 debug_break call
  但类未标 has_debug_hooks=True → test fail · 埋点作者纪律早晚
- serialize 契约 test tests/path2_web/test_serialize_debug_enabled_classes.py · bottom_burst pattern
  debug_enabled_classes == ['tb'] · 类型 list[str] · 去重

契约 C 让未来加 pill 时前端读 pattern.debug_enabled_classes 而非硬编码 vocabulary · 消除
"作者埋点但前端不知道该 class 有 debug 能力" 的可预测失败模式。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Backend cache · handler dict cache + cache-hit skip detector + skip 写 env + 集成测试

**Files:**
- Modify: `path2_web/api.py`(handler 加 module-level dict cache · restructure `get_diagnose` 加 cache-hit 路径)
- Create: `tests/path2_web/test_diagnose_cache.py`(单元 · cache hit/miss 逻辑)
- Create: `tests/path2_web/test_diagnose_cache_integration.py`(集成 · 与 class 门联合 · 真实 pkl · 端到端)

**Interfaces:**
- Consumes: Task 1-3 全部(handler 的 env pop 逻辑 · debug_break gate)
- Produces:
  - `_DIAGNOSE_CACHE: dict` module-level state(测试可通过 monkeypatch 清空)
  - `_params_hash(params: dict) -> str` helper
  - Handler cache-hit 分支:走 `derive_response(query, diag, spec, result)` · **不** 跑 detector · **不** 写 env · **不** pause

### Steps

- [ ] **Step 5.1: Read current handler structure to plan restructure**

Run: `sed -n '198,256p' path2_web/api.py`

Expected: 见 Task 3 后的现状:handler 有 env 写入分支 · try 内 build spec / attach_and_collect / analyze / derive_response · finally pop 三 env。

**Restructure 策略:**
1. 加 module-level `_DIAGNOSE_CACHE: dict = {}` + `_params_hash` helper 到 api.py 顶部(imports 后)
2. handler 内先算 `cache_key`(不含 params_hash 时 lazy 算 params;或先算 mod 和 params 再 key)
3. 若 `scope is not None and cache_key in _DIAGNOSE_CACHE`:直接走 cache-hit 分支(不 attach_and_collect · 不 analyze · 不写 env · finally 依然 pop 兜底)
4. 否则走既有 v3 路径 · 结束时 `if scope is not None: _DIAGNOSE_CACHE[cache_key] = (spec, diag, result)`
5. legacy 路径(scope=None)不 cache(backward compat)

- [ ] **Step 5.2: Create failing cache unit test**

Create `tests/path2_web/test_diagnose_cache.py`:

```python
"""v4 backend cache 单元测试(spy detector 观测 cache hit/miss)。

覆盖:
- 同参数第二次请求 cache hit · detector 只跑 1 次(spy 观测)
- 不同 event_class 参数 → cache miss · detector 再跑
- 不同 anchor_kind 参数 → cache miss · detector 再跑
- 不同 start_bar/end_bar → cache miss · detector 再跑
- scope=None(legacy)不 cache · 每次跑
- Cache hit 时不写 env(spy debug_break 观测 os.environ)
- Cache hit 返回值与 cache miss 首次结果**内容一致**
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)
    monkeypatch.delenv("DEBUG_EVENT_CLASS", raising=False)

    # 清空全局 cache · 避免测试互扰
    import path2_web.api as api_mod
    api_mod._DIAGNOSE_CACHE.clear()

    data = tmp_path / "data"
    data.mkdir()
    n = 300
    dates = pd.date_range("2024-01-01", periods=n)
    close = np.concatenate([
        np.full(200, 10.0),
        np.linspace(10.0, 15.0, 20),
        np.full(80, 13.0),
    ])
    df = pd.DataFrame({
        "date": dates, "open": close, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": [100.0] * n,
    }).set_index("date")
    df.to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-10-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


def _url(**q):
    base = "pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-10-01&scope=time"
    extras = "&".join(f"{k}={v}" for k, v in q.items())
    return f"/diagnose?{base}&{extras}" if extras else f"/diagnose?{base}"


def test_same_params_second_call_is_cache_hit(client, monkeypatch):
    """同参数第二次请求 cache hit · detector _dag_analyze_engine 只被调 1 次。"""
    from path2_web import api as api_mod
    call_count = {"analyze": 0}

    real_analyze = api_mod._dag_analyze_engine
    def spy_analyze(*args, **kwargs):
        call_count["analyze"] += 1
        return real_analyze(*args, **kwargs)
    monkeypatch.setattr(api_mod, "_dag_analyze_engine", spy_analyze)

    r1 = client.get(_url(start_bar=0, end_bar=280))
    assert r1.status_code == 200
    r2 = client.get(_url(start_bar=0, end_bar=280))
    assert r2.status_code == 200
    assert call_count["analyze"] == 1, (
        f"expected analyze called once (miss then hit) · got {call_count['analyze']}"
    )


def test_different_event_class_is_cache_miss(client, monkeypatch):
    """不同 event_class → 不同 cache key → cache miss · detector 再跑。"""
    from path2_web import api as api_mod
    call_count = {"analyze": 0}

    real_analyze = api_mod._dag_analyze_engine
    def spy_analyze(*args, **kwargs):
        call_count["analyze"] += 1
        return real_analyze(*args, **kwargs)
    monkeypatch.setattr(api_mod, "_dag_analyze_engine", spy_analyze)

    client.get(_url(start_bar=0, end_bar=280))                   # miss (event_class=None)
    client.get(_url(start_bar=0, end_bar=280, event_class="tb")) # miss (event_class=tb)
    client.get(_url(start_bar=0, end_bar=280, event_class="bo")) # miss (event_class=bo)
    assert call_count["analyze"] == 3, (
        f"expected analyze called 3 times (all misses on different event_class) · got {call_count['analyze']}"
    )


def test_different_anchor_kind_is_cache_miss(client, monkeypatch):
    from path2_web import api as api_mod
    call_count = {"analyze": 0}

    real_analyze = api_mod._dag_analyze_engine
    def spy_analyze(*args, **kwargs):
        call_count["analyze"] += 1
        return real_analyze(*args, **kwargs)
    monkeypatch.setattr(api_mod, "_dag_analyze_engine", spy_analyze)

    client.get(_url(start_bar=0, end_bar=280, anchor_kind="gate"))
    client.get(_url(start_bar=0, end_bar=280, anchor_kind="trough"))
    assert call_count["analyze"] == 2


def test_different_bar_range_is_cache_miss(client, monkeypatch):
    from path2_web import api as api_mod
    call_count = {"analyze": 0}

    real_analyze = api_mod._dag_analyze_engine
    def spy_analyze(*args, **kwargs):
        call_count["analyze"] += 1
        return real_analyze(*args, **kwargs)
    monkeypatch.setattr(api_mod, "_dag_analyze_engine", spy_analyze)

    client.get(_url(start_bar=0, end_bar=280))
    client.get(_url(start_bar=50, end_bar=280))
    client.get(_url(start_bar=0, end_bar=250))
    assert call_count["analyze"] == 3


def test_cache_hit_does_not_write_env(client, monkeypatch):
    """Cache hit 分支不写 env · 因此 debug_break 不 fire。"""
    from path2_web import api as api_mod
    import path2.debug_ctx as dc

    fire_hits: list = []
    def spy_break(i, *, anchor_kind, class_id):
        fire_hits.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy_break)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy_break)

    # 第一次 miss → 触发 debug_break · env 被写(event_class=tb)
    r1 = client.get(_url(start_bar=0, end_bar=280, event_class="tb"))
    assert r1.status_code == 200
    first_call_count = len(fire_hits)
    assert first_call_count > 0, "fixture broken · first call should have fired debug_break"

    # 第二次 hit → 不应再有 debug_break 被调(spy 不再新增)
    fire_hits_before = len(fire_hits)
    r2 = client.get(_url(start_bar=0, end_bar=280, event_class="tb"))
    assert r2.status_code == 200
    assert len(fire_hits) == fire_hits_before, (
        f"cache hit should skip detector · debug_break should not fire again · "
        f"before hit call: {fire_hits_before}, after: {len(fire_hits)}"
    )


def test_cache_hit_returns_same_payload_as_miss(client):
    """Cache hit 返回值与首次 miss 一致(byte-equivalent)。"""
    r1 = client.get(_url(start_bar=0, end_bar=280, event_class="tb"))
    r2 = client.get(_url(start_bar=0, end_bar=280, event_class="tb"))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json(), "cache hit payload should equal cache miss first result"


def test_scope_none_legacy_path_is_not_cached(client, monkeypatch):
    """scope=None legacy 路径不 cache · 每次都跑。"""
    from path2_web import api as api_mod
    call_count = {"diagnose": 0}

    # legacy 路径调 diagnose_symbol · spy 它
    from path2_web import diagnose as diag_mod
    real_ds = diag_mod.diagnose_symbol
    def spy_ds(*args, **kwargs):
        call_count["diagnose"] += 1
        return real_ds(*args, **kwargs)
    monkeypatch.setattr(diag_mod, "diagnose_symbol", spy_ds)
    monkeypatch.setattr(api_mod, "diagnose_symbol", spy_ds)   # api.py imports 后局部符号也 patch

    # legacy = 不带 scope 参数
    r1 = client.get("/diagnose?pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-10-01")
    r2 = client.get("/diagnose?pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-10-01")
    assert r1.status_code == 200 and r2.status_code == 200
    assert call_count["diagnose"] == 2, (
        f"legacy path should not cache · expected 2 calls · got {call_count['diagnose']}"
    )
```

- [ ] **Step 5.3: Run tests to verify they fail**

Run: `uv run pytest tests/path2_web/test_diagnose_cache.py -v 2>&1 | tail -30`

Expected: 大部分 FAIL(现 handler 无 cache · analyze 每次都跑 · env 每次都写)。少数可能过(如 `test_cache_hit_returns_same_payload_as_miss` 因为无 cache 时两次结果本来就一致 · 这个 test 是 cache 语义正确性的兜底 · 允许通过)。

- [ ] **Step 5.4: Modify path2_web/api.py 加 cache**

顶部 imports 后加 module-level state 和 helper。找到 imports 结束位置(约 L26 附近),加:

```python
# ── v4 backend cache(spec: docs/research/2026-07-16.../final_report.md R12)──
# key = (pattern_id, symbol, start, end, scope, src_role, dst_role, event_class, event_id,
#        src_event_id, dst_event_id, edge_id, start_bar, end_bar, anchor_kind,
#        _params_hash(mod.load_params()))
# value = (spec, diag, result) triple
# 无淘汰(本机单用户 dev tool · 见 final_report §载入前提约束)
# scope=None legacy 路径不 cache(backward compat)
import hashlib as _hashlib_v4cache
import json as _json_v4cache

_DIAGNOSE_CACHE: dict = {}


def _params_hash(params) -> str:
    """params dict → 短 hash 用于 cache key(md5 快而稳)。
    params 可能含非-JSON 类型(如 numpy 标量)· 用 default=str 兜底。"""
    return _hashlib_v4cache.md5(
        _json_v4cache.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:8]
```

Restructure `get_diagnose` handler:找到 handler body,替换。

替换 old:
```python
    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_role: Optional[str] = None, dst_role: Optional[str] = None,
                     event_class: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                     anchor_kind: Optional[str] = None):
        # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
        # 供 path2.debug_ctx.debug_break 消费。v2(2026-07-15 event-debug-dual-emit) 契约 #7:
        # handler 结束必 pop env(request 级作用域, 防跨 request 污染 + scan pool 继承挂死)。
        # v3(2026-07-16 role-gated-debug,后更名 anchor_kind) 契约 #7 扩展:双 env 独立
        # (DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND)· finally 无条件 pop 两 env(即使本次未写
        # DEBUG_ANCHOR_KIND 也 pop 兜底)。
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if anchor_kind:                             # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ANCHOR_KIND"] = anchor_kind
        if event_class:                             # ★ v4 · 空串也视同未传
            os.environ["DEBUG_EVENT_CLASS"] = event_class
        try:
            mod = registry.get(pattern_id)
            if mod is None:
                raise HTTPException(404, f"unknown pattern: {pattern_id}")
            cfg = get_config()
            pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
            if not pkl.exists():
                raise HTTPException(404, f"pkl not found: {symbol}")
            win = slice_window(pd.read_pickle(pkl), start, end)
            # 诊断每次都重新 build_pattern(load_params())——与 /scan 同口径(yaml SSoT 热加载)。
            # 不能复用 mod.PATTERN_DAG(它是 import 时一次性 build,Params.default() 闭合,与 yaml 漂移)。
            spec = mod.build_pattern(mod.load_params())
            if scope is None:
                # legacy 路径:无 scope 参数 → 字节等价,前端旧 api.ts::getDiagnose 不用改。
                return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)
            diag = _dag_diagnose(spec, win, None)
            # ★ Task 24:承 Task 15/17 系统 gap —— scope=time/pair 需要一个挂了 gate_failures 的
            # AnalysisResult,legacy 分派此前从未注入,derive_response 只能落 stub/caveat。复刻
            # scan.py 的 attach_and_collect + analyze + detach + dataclasses.replace(gate_failures=...)
            # 套路(单股即时诊断,非批量 worker,可接受重算成本)。
            collector = attach_and_collect(spec)
            try:
                result = _dag_analyze_engine(spec, win, None)
                result = dataclasses.replace(result, gate_failures=collector.snapshot())
            finally:
                detach(spec)
            query = Query(symbol=symbol, scope=scope, src_role=src_role, dst_role=dst_role,
                         event_class=event_class, event_id=event_id,
                         src_event_id=src_event_id, dst_event_id=dst_event_id,
                         edge_id=edge_id, start_bar=start_bar, end_bar=end_bar)
            try:
                return derive_response(query, diag=diag, spec=spec, result=result)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        # ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env,
        # undefined under concurrency, single-user debug tool.
        # v4(2026-07-17 class-gate)契约扩展:第四 env DEBUG_EVENT_CLASS 同 finally 无条件 pop。
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)   # ★ v3 · 无条件 pop 兜底
            os.environ.pop("DEBUG_EVENT_CLASS", None)   # ★ v4 · 无条件 pop 兜底(跨 request 隔离)
```

new:
```python
    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_role: Optional[str] = None, dst_role: Optional[str] = None,
                     event_class: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                     anchor_kind: Optional[str] = None):
        # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
        # 供 path2.debug_ctx.debug_break 消费。v2(2026-07-15 event-debug-dual-emit) 契约 #7:
        # handler 结束必 pop env(request 级作用域, 防跨 request 污染 + scan pool 继承挂死)。
        # v3(2026-07-16 role-gated-debug,后更名 anchor_kind) 契约 #7 扩展:双 env 独立
        # (DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND)· finally 无条件 pop 两 env。
        # v4(2026-07-17 class-gate + backend cache):第四 env DEBUG_EVENT_CLASS 同 finally
        # 无条件 pop;并新增 backend cache 拔"filter 变即重跑"root smell —— cache-hit 严格
        # skip detector + skip 写 env(见 final_report R1/R12)。

        # ── v4 cache-hit fast path(scope=None legacy 路径不 cache · backward compat)──
        if scope is not None:
            mod = registry.get(pattern_id)
            if mod is None:
                raise HTTPException(404, f"unknown pattern: {pattern_id}")
            params = mod.load_params()
            cache_key = (pattern_id, symbol, start, end, scope,
                         src_role, dst_role, event_class, event_id,
                         src_event_id, dst_event_id, edge_id,
                         start_bar, end_bar, anchor_kind,
                         _params_hash(params))
            cached = _DIAGNOSE_CACHE.get(cache_key)
            if cached is not None:
                # cache HIT:不写 env · 不 attach_and_collect · 不 analyze · 不 pause
                spec_c, diag_c, result_c = cached
                query = Query(symbol=symbol, scope=scope, src_role=src_role, dst_role=dst_role,
                             event_class=event_class, event_id=event_id,
                             src_event_id=src_event_id, dst_event_id=dst_event_id,
                             edge_id=edge_id, start_bar=start_bar, end_bar=end_bar)
                try:
                    return derive_response(query, diag=diag_c, spec=spec_c, result=result_c)
                except ValueError as e:
                    raise HTTPException(400, str(e)) from e

        # ── cache miss (or scope=None):走既有 v3 路径 · 写 env · 跑 detector · pause · 存 cache ──
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if anchor_kind:                             # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ANCHOR_KIND"] = anchor_kind
        if event_class:                             # ★ v4 · 空串也视同未传
            os.environ["DEBUG_EVENT_CLASS"] = event_class
        try:
            mod = registry.get(pattern_id)
            if mod is None:
                raise HTTPException(404, f"unknown pattern: {pattern_id}")
            cfg = get_config()
            pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
            if not pkl.exists():
                raise HTTPException(404, f"pkl not found: {symbol}")
            win = slice_window(pd.read_pickle(pkl), start, end)
            # 诊断每次都重新 build_pattern(load_params())——与 /scan 同口径(yaml SSoT 热加载)。
            # 不能复用 mod.PATTERN_DAG(它是 import 时一次性 build,Params.default() 闭合,与 yaml 漂移)。
            spec = mod.build_pattern(mod.load_params())
            if scope is None:
                # legacy 路径:无 scope 参数 → 字节等价,前端旧 api.ts::getDiagnose 不用改。
                return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)
            diag = _dag_diagnose(spec, win, None)
            # ★ Task 24:承 Task 15/17 系统 gap —— scope=time/pair 需要一个挂了 gate_failures 的
            # AnalysisResult,legacy 分派此前从未注入,derive_response 只能落 stub/caveat。复刻
            # scan.py 的 attach_and_collect + analyze + detach + dataclasses.replace(gate_failures=...)
            # 套路(单股即时诊断,非批量 worker,可接受重算成本)。
            collector = attach_and_collect(spec)
            try:
                result = _dag_analyze_engine(spec, win, None)
                result = dataclasses.replace(result, gate_failures=collector.snapshot())
            finally:
                detach(spec)
            query = Query(symbol=symbol, scope=scope, src_role=src_role, dst_role=dst_role,
                         event_class=event_class, event_id=event_id,
                         src_event_id=src_event_id, dst_event_id=dst_event_id,
                         edge_id=edge_id, start_bar=start_bar, end_bar=end_bar)
            # ★ v4 · miss 完成 · 存 cache 供下次同参数 hit
            _DIAGNOSE_CACHE[cache_key] = (spec, diag, result)
            try:
                return derive_response(query, diag=diag, spec=spec, result=result)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        # ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env,
        # undefined under concurrency, single-user debug tool.
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)   # ★ v3 · 无条件 pop 兜底
            os.environ.pop("DEBUG_EVENT_CLASS", None)   # ★ v4 · 无条件 pop 兜底(跨 request 隔离)
```

**注意实现细节:**
- cache_key 计算在 `if scope is not None:` 分支内 · 因为 scope=None 不进 cache 分支,不需要算 key
- cache_key 需要 `mod` 和 `params`,所以要 duplicate `registry.get(pattern_id)` 调用一次在 cache-hit 快路径(两次调 registry.get 是幂等的)· 或者提取到 handler 顶部
- 更简洁:两处 registry.get 都保留(第一处仅用于 cache-hit 分支 · 第二处是 miss 分支;两次调都是 O(1) dict lookup · 无副作用)
- `cache_key` 在 miss 分支也需要引用 · 所以变量需要提出到函数顶部作用域;当前 new 版本里 miss 分支引用了 `cache_key` · 但 `cache_key` 只在 `if scope is not None:` 分支里定义 —— **潜在 UnboundLocalError 陷阱**!
- 修正:cache_key 计算和 `_DIAGNOSE_CACHE[cache_key] = ...` 存 cache 都要 gate 在 `if scope is not None:` 分支下

修正 miss 分支存 cache 部分,替换 old:
```python
            # ★ v4 · miss 完成 · 存 cache 供下次同参数 hit
            _DIAGNOSE_CACHE[cache_key] = (spec, diag, result)
            try:
                return derive_response(query, diag=diag, spec=spec, result=result)
```

new:
```python
            # ★ v4 · miss 完成 · 存 cache 供下次同参数 hit(scope=None 不 cache · cache_key 未定义)
            if scope is not None:
                _DIAGNOSE_CACHE[cache_key] = (spec, diag, result)
            try:
                return derive_response(query, diag=diag, spec=spec, result=result)
```

- [ ] **Step 5.5: Run cache unit tests to verify pass**

Run: `uv run pytest tests/path2_web/test_diagnose_cache.py -v 2>&1 | tail -30`

Expected: 7/7 PASS。

若 `test_scope_none_legacy_path_is_not_cached` 失败(spy 只观测到 1 次而非 2 次),检查 monkeypatch 是否需要 patch 两处引用(`api_mod.diagnose_symbol` 是 import 的局部符号 · `diag_mod.diagnose_symbol` 是原始定义;handler 里 `return diagnose_symbol(...)` 用的是 api_mod 里 import 后的局部符号 · 必须 patch `api_mod.diagnose_symbol`)。

- [ ] **Step 5.6: Create integration test**

Create `tests/path2_web/test_diagnose_cache_integration.py`:

```python
"""v4 集成测试:cache + class 门联合 · 用真实 TSLA.pkl 数据端到端验证。

若 TSLA.pkl 不可访问 → skip。

覆盖:
- 首次 brush(cache miss) · 命中 gate 断点(monkeypatch pydevd.settrace 为 counter)
- 同参数第二次 brush(cache hit) · **不**命中 gate 断点(spy 观测 fire_recorder 不变)
- 换 event_class(cache miss)· 再命中 gate 断点
- 换回原 event_class(可能 cache hit 或 miss 取决于顺序)· 验证 hit 时不 fire

对应 skeptic 原文"filter 变即重跑即写 env 即命中断点" root smell 的直接消除 · e2e 证明。
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client_with_real_pkl(tmp_path, monkeypatch):
    real_dataset = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    if not (real_dataset / "TSLA.pkl").exists():
        pytest.skip("real dataset unavailable · skip integration test")

    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)
    monkeypatch.delenv("DEBUG_EVENT_CLASS", raising=False)

    sys.modules.pop("path2.debug_ctx", None)

    # 清空全局 cache
    import path2_web.api as api_mod
    api_mod._DIAGNOSE_CACHE.clear()

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(real_dataset),
        "scan": {"start_date": "2025-01-01", "end_date": "2026-01-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


@pytest.fixture
def fire_recorder(monkeypatch):
    """spy debug_break · 记录每次 fire 时的 (bar, anchor_kind, class_id) triple。"""
    hits: list = []
    import path2.debug_ctx as dc

    def wrapped(i, *, anchor_kind, class_id):
        # 复刻 debug_break 判据(不真 pause)
        import os
        if not dc._DEBUG_MODE:
            return
        r = dc._read_range()
        if r is None:
            return
        if not (r[0] <= i <= r[1]):
            return
        required_ak = dc._read_anchor_kind()
        if required_ak is not None and required_ak != anchor_kind:
            return
        required_cid = dc._read_class_id()
        if required_cid is not None and required_cid != class_id:
            return
        hits.append((i, anchor_kind, class_id))

    monkeypatch.setattr(dc, "debug_break", wrapped)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", wrapped)
    return hits


def _url(event_class: str | None = None, start_bar: int = 0, end_bar: int = 250):
    q = ("pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if event_class:
        q += f"&event_class={event_class}"
    return f"/diagnose?{q}"


def test_first_brush_miss_fires_second_brush_hit_does_not_fire(client_with_real_pkl, fire_recorder):
    """首次 brush miss · 命中 gate 断点(fire_recorder 非空);第二次同参数 hit · fire_recorder 不变。"""
    r1 = client_with_real_pkl.get(_url(event_class="tb"))
    assert r1.status_code == 200
    first_fires = len(fire_recorder)
    assert first_fires > 0, "first brush should fire debug_break (real TSLA has tb events)"

    # 第二次同参数 → cache hit → 不再 fire
    r2 = client_with_real_pkl.get(_url(event_class="tb"))
    assert r2.status_code == 200
    assert len(fire_recorder) == first_fires, (
        f"cache hit should not re-fire debug_break · before: {first_fires}, after: {len(fire_recorder)}"
    )


def test_switch_event_class_causes_new_fires(client_with_real_pkl, fire_recorder):
    """切 event_class → cache miss → 新 fire(class 门下只匹配 class 的埋点 fire)。"""
    client_with_real_pkl.get(_url(event_class="tb"))  # miss · tb 埋点 fire
    fires_after_tb = list(fire_recorder)
    client_with_real_pkl.get(_url(event_class="bo"))  # miss · 但 class='bo' 匹配 · tb class_id='tb' 不匹配 → 期望 0 新 fire
    fires_after_bo = list(fire_recorder)

    # bo 分支应无新 fire(tb 埋点的 class_id='tb' 与 required_cid='bo' 不匹配)
    new_fires_on_bo = fires_after_bo[len(fires_after_tb):]
    assert all(cid != "tb" or ak != "gate" for _, ak, cid in new_fires_on_bo) or len(new_fires_on_bo) == 0, (
        f"switching event_class to 'bo' should not re-fire tb.gate anchor · "
        f"got new fires: {new_fires_on_bo}"
    )


def test_cache_hit_leaves_env_unset(client_with_real_pkl, fire_recorder):
    """Cache hit 完成后 · env 三兄弟(anchor_kind 与 event_class)不残留(finally 兜底 pop)。"""
    import os
    client_with_real_pkl.get(_url(event_class="tb", start_bar=0, end_bar=250))
    client_with_real_pkl.get(_url(event_class="tb", start_bar=0, end_bar=250))  # hit
    assert os.environ.get("DEBUG_BAR_RANGE") is None
    assert os.environ.get("DEBUG_ANCHOR_KIND") is None
    assert os.environ.get("DEBUG_EVENT_CLASS") is None
```

- [ ] **Step 5.7: Run integration tests**

Run: `uv run pytest tests/path2_web/test_diagnose_cache_integration.py -v 2>&1 | tail -20`

Expected: 3/3 PASS(或 skip 若 TSLA.pkl 不可访问)。

- [ ] **Step 5.8: Regression — 全 pytest suite + frontend gate**

Run: `uv run pytest tests/path2/ tests/path2_web/ 2>&1 | tail -20`

A/B 差分:
```bash
git stash push -m "task5-wip"
uv run pytest tests/path2/ tests/path2_web/ 2>&1 | grep -c "^FAILED" > /tmp/task4_fails
git stash pop
uv run pytest tests/path2/ tests/path2_web/ 2>&1 | grep -c "^FAILED" > /tmp/task5_fails
diff /tmp/task4_fails /tmp/task5_fails
```

Expected: Task 5 后失败数 = Task 4 后基线(cache 是 additive 后端改动 · 不该引入回归)。

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npm run build 2>&1 | tail -10`

Expected: 前端全绿(cache 不影响前端 · types.ts 已在 Task 4 加过字段)。

- [ ] **Step 5.9: Commit**

```bash
git add path2_web/api.py \
        tests/path2_web/test_diagnose_cache.py \
        tests/path2_web/test_diagnose_cache_integration.py
git commit -m "$(cat <<'EOF'
feat(diagnose): v4 · backend cache P1 · handler dict cache + cache-hit skip detector + skip 写 env

- 加 module-level _DIAGNOSE_CACHE: dict = {} 无淘汰(本机单用户 dev tool)
- 加 _params_hash(params) md5 短 hash 用于 cache key
- Cache key = (pattern_id, symbol, start, end, scope, src_role, dst_role, event_class, event_id,
              src_event_id, dst_event_id, edge_id, start_bar, end_bar, anchor_kind, params_hash)
- Cache value = (spec, diag, result) triple
- Cache-hit 严格 skip:走 derive_response · 不 attach_and_collect · 不 analyze · 不 detach · 不写 env · 不 pause
- Cache-miss:走既有 v3 路径 · 写 env · 跑 detector · pause · 存 cache · finally pop env
- Scope=None legacy 路径不 cache(backward compat · 前端 getDiagnose 不改)
- Finally 仍无条件 pop 三 env(cache-hit 也 pop 兜底 · 幂等)

拔 skeptic §P2 identified root smell "filter 变即重跑即写 env 即命中断点":
- 直接消除用户 2026-07-16 报告的 sidebar dropdown 切换 event_class 反复命中 gate 断点噪音
- 同参数第二次 brush → cache hit → 不 fire · Resume 一次即可(未来 filter 切换也 hit 即静默)

单元 test 7 case:same-params hit / diff event_class/anchor_kind/bar_range miss / hit skip env / hit payload
一致 / legacy scope=None 不 cache。
集成 3 case(真实 TSLA)· 端到端证 miss→hit→env unset。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Final Validation(手动 · lead/user 在 PyCharm 里跑)

**Non-subagent 环节** · 由 lead/user 手动执行:

- [ ] **FV1**:PyCharm 以 Debug 方式跑 `path2_web.main` · 前端 `npm run dev`。curl 无 event_class 验证 v3 兼容:
  ```bash
  curl -s 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250' > /dev/null
  ```
  PyCharm Debug 面板:期望命中 throwback.py 5 处埋点(gate/trough/end/end/entry)· 逐个 F9 Resume · 与 v3 e2e 场景 A 等价。

- [ ] **FV2**:curl event_class=tb + anchor_kind=gate 验证 v4 class 门 + anchor kind 双合取:
  ```bash
  curl -s 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250&event_class=tb&anchor_kind=gate' > /dev/null
  ```
  期望只命中 L104 gate 埋点(且 class_id='tb' 匹配)· 不命中其他 4 处。

- [ ] **FV3**:同参数第二次 curl(FV2 之后立刻)验证 cache hit skip pause:
  ```bash
  curl -s 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250&event_class=tb&anchor_kind=gate' > /dev/null
  ```
  期望**完全不 pause**(cache hit · detector 未跑 · env 未写)· 直接返回。

- [ ] **FV4**:换 event_class 触发 cache miss + class 门筛选:
  ```bash
  curl -s 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250&event_class=bo' > /dev/null
  ```
  期望 cache miss(不同 event_class 参数)· detector 跑 · 但 tb 埋点的 class_id='tb' 与 required='bo' 不匹配 · **不 pause**(class 门筛过)· 除非 bo 未来加了 debug_break(今天没有)。

- [ ] **FV5**:后端 log 检查 · handler 结束时 `DEBUG_BAR_RANGE`/`DEBUG_ANCHOR_KIND`/`DEBUG_EVENT_CLASS` 无残留:
  ```bash
  echo "DEBUG_BAR_RANGE=$DEBUG_BAR_RANGE"
  echo "DEBUG_ANCHOR_KIND=$DEBUG_ANCHOR_KIND"
  echo "DEBUG_EVENT_CLASS=$DEBUG_EVENT_CLASS"
  ```
  期望三个都空(finally pop 兜底 · cache hit 也 pop)。

- [ ] **FV6** (可选):update-ai-context 同步 `.claude/docs/modules/path2.md` + `path2_web.md`,追加:
  - `debug_break(i, *, anchor_kind, class_id)` 双 required kwarg
  - 第四 env `DEBUG_EVENT_CLASS`
  - `has_debug_hooks` ClassVar 契约
  - Backend cache handler dict + cache key + hit skip 语义

- [ ] **FV7** (可选):在前端 K 线主图上手动 brush 一段 · 观察 sidebar「只看」下拉切换 event_class 时:
  - 切换后 sidebar 展示内容改变(既有 serialize filter 语义不变)
  - 切换后**不再命中 gate 断点噪音**(cache miss 触发 detector run · 但 class 门筛过 tb 之外的 class · Resume 一次即可)
  - 反复切回同一 event_class · cache hit · **完全不 pause**

若所有 FV 通过 · v4 完成 · 分支保留 uncommitted / 不 push / 不合 master · 与 v3 收尾一致(用户历次都保留原样)。

---

## Self-Review 记录(writing-plans skill § Self-Review)

**1. Spec coverage** — R1-R12 每条覆盖情况:

- **R1** cache-hit spec(skip detector + skip 写 env) → Task 5 Step 5.4 · Step 5.5 test_cache_hit_does_not_write_env
- **R2** cache 与 class 门正交 → 分为 Task 1-4(class 门)+ Task 5(cache)独立 commit
- **R3** debug filter 默认 first-enabled-class → 前端本轮 UI 休眠 · 不做 pill · 不涉及默认值
- **R4** 入口 D 独立 · sidebar dropdown 保留镜像 → 前端零改动 · 保持 v3 现状
- **R5** 命名 `DEBUG_EVENT_CLASS` → Task 1 Global Constraints + Task 3 handler + Task 4 契约 C
- **R6** 契约 C(has_debug_hooks ClassVar) → Task 4 全部
- **R7** IDE 条件断点不重议 → 无 task · 由用户在 FV 时按需自查
- **R8** 一控件 union → 前端本轮 UI 休眠 · pill 不做 · union 决策留待未来激活
- **R9** class 门 = 机制预留 + UI 休眠 → Task 1-4 只做机制 · 不激活 pill
- **R10** localStorage per (pattern×symbol) → 前端本轮 UI 休眠 · 不做 pill · 不涉及 localStorage
- **R11** env → contextvars = N/A(本机单用户前提)→ 无 task · Global Constraints §载入前提约束标明
- **R12** backend cache P1 → Task 5 全部
- **一级发现**(v3 DEBUG_ROLE 承载 anchor kind)→ anchor_kind refactor(22b90a5)已 landed · 本 plan Base commit 之前

**2. Placeholder scan**:
- Task 2 Step 2.4 里 "若现文件用变量名 `EXPECTED_ROLE_COUNTER` ... 改为 `EXPECTED_ANCHOR_KIND_COUNTER`"是明确条件指令 · 非 placeholder
- Task 4 Step 4.10 里 "若 vue-tsc 报错 ... 补类型或改为可选访问"是防守性 fallback · 非 placeholder
- 无 TBD / TODO / 待补充 · 每 step 都有可执行代码或命令

**3. Type consistency**:
- `debug_break(i: int, *, anchor_kind: str, class_id: str) -> None` 签名在 Task 1/2 一致
- `_read_class_id() -> Optional[str]` 在 Task 1 定义 · Task 3/5 test 通过 env spy 观测 · 一致
- `DEBUG_EVENT_CLASS` env 名在 Task 1/2/3/5 全部使用 · 一致
- HTTP query `event_class: Optional[str] = None` 在 Task 3 复用 v3 已有参数 · Task 5 cache_key 使用 · 一致
- `has_debug_hooks: ClassVar[bool]` 在 Task 4 全部 detector 类 + AST lint 使用 · 一致
- `debug_enabled_classes: list[str]` 字段名 Python side(serialize)与 TS side(SerializedPattern)一致
- Cache key 元组 15 元 · Task 5 Step 5.2 test 和 Step 5.4 handler code 使用相同元素顺序 · 一致
- Class_id 词汇 `'tb'` 在 Task 2 埋点 · Task 3 test · Task 5 集成 · e2e FV2 全部使用 · 一致

**4. 无 gap 需补充 task**。

---

## Baseline 允许失败(参考 v3 plan · 本轮沿用)

- pytest baseline:每 task 用 `git stash` 差分证明"改前失败集 == 改后失败集"(不依赖 hard 数字 · 因 configs/path2_web.yaml 未提交编辑会随环境漂移)
- `tests/path2/atoms/test_throwback.py::test_evaluate_anchor_measure_close` pre-existing assertion bug(anchor_kind refactor 前就存在 · 独立 · 不在本轮 scope)
- vitest baseline:2 pre-existing `ScanConfigDialog` failed(与本轮无关)
- 不动 `configs/path2_web.yaml`(pre-existing 未提交编辑 · 全程 hands-off)
