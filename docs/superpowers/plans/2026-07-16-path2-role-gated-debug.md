# Path2 v3 Role-Gated Debug 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `debug_break` 埋点加 role 门限,消除入口 A(brush 框选)被 v2 event-anchor 埋点污染的噪音,同时保 v1 兼容与生产零成本。

**Architecture:** 双 env 分离(`DEBUG_BAR_RANGE=lo,hi` + `DEBUG_ROLE=role`);`debug_break(i, *, role: str)` required kwarg;前端入口 A 硬编码 `role='gate'`、入口 D 透传 `anchor.key`;`DEBUG_ROLE` 未设 = v1 全 role fire fallback。

**Tech Stack:** Python 3.12(pytest · FastAPI · uv)· Vue 3 + TypeScript(vitest · vue-tsc · vite)· PyCharm pydevd

**Spec:** `docs/superpowers/specs/2026-07-16-path2-role-gated-debug-design.md`(commit 404f48d)

## Global Constraints

**Role 词汇(tb baseline · 每 task 都必须使用完全一致的字面量):**
- `'gate'` · `'trough'` · `'end'` · `'entry'`(小写 · 单引号字符串字面量)
- 5 处埋点的 role 分布 Counter 必等于 `{'gate': 1, 'trough': 1, 'end': 2, 'entry': 1}`

**debug_break 签名(全局强制):**
- `def debug_break(i: int, *, role: str) -> None:` — role 是 required keyword-only 参数,**无 default**
- 缺 role kwarg 调用 → Python 抛 `TypeError`

**Env 契约:**
- 新增 `DEBUG_ROLE`(与现有 `DEBUG_BAR_RANGE` 完全独立)
- `_read_role()`:env 未设或空串 → `None`(v1 兼容 fallback)
- handler `finally` **无条件** pop 两 env(即使本次未写 DEBUG_ROLE 也 pop 兜底,防跨 request 污染)
- handler 写 env 判据 `if role:`(空串也不写)

**Debug 判据(debug_break 内部):**
```
_DEBUG_MODE=True && bar in range && (required_role is None or required_role == role)
```

**触发 API(fire 分支不变):**
```python
try:
    import pydevd
    pydevd.settrace(suspend=True)
except ImportError:
    breakpoint()
```

**前端 role 供给:**
- 入口 A(brush · view.ts 内 `timeScopeResponse.value = await getTimeDiagnose(...)`):硬编码 `role='gate'`
- 入口 D(marker 右键 · view.ts 内 `triggerEventDebug` 里 `await getTimeDiagnose(...)`):`role=anchor.key`

**契约 #4 加强:** debug_break 参数值 == event.<field> **且** role == 前端 anchor.key(字符串一致)

**契约 #7 扩展:** handler finally pop DEBUG_BAR_RANGE + DEBUG_ROLE 两 env

**生产零成本:** `_DEBUG_MODE=False` 时 debug_break 第一行 return · pydevd 不 import · env 不读 · role check 不执行

**Baseline 允许的 pre-existing 失败**(不当作回归):
- pytest:22 pre-existing failed(v2 base · 与 role 门限无关)
- vitest:2 pre-existing failed(ScanConfigDialog · 与 role 门限无关)

**测试路径规范**(项目约定):
- pytest 单元测试:`tests/<mirror-source-path>/test_<topic>.py`
- vitest:`path2_web_ui/tests/<prefix>.<topic>.spec.ts`(**不是** src/**/__tests__/**)

**Uv 命令(项目 tooling):** `uv run pytest ...` · `uv run python -m path2_web.main`

**Backend debug port:** 8010(读自 `configs/path2_web.yaml` 的 `backend_port_dbg`)

**Base commit:** 404f48d(spec commit · 已 landed;dbg_code 分支 head 8cd2e7c 已含 v2 event-debug 全部工作 · v3 从 404f48d 起)

---

## Task 1: debug_ctx.py role gate + 单元测试

**Files:**
- Modify: `path2/debug_ctx.py`
- Create: `tests/path2/test_debug_ctx.py`

**Interfaces:**
- Produces:
  - `debug_break(i: int, *, role: str) -> None` — required kwarg,role 门限
  - `_read_role() -> Optional[str]` — env 未设或空串返 None
- Consumes: 无(纯基础模块)

### Steps

- [ ] **Step 1.1: Read current debug_ctx.py to confirm baseline**

Run: `sed -n '1,40p' path2/debug_ctx.py`

Expected: 看到 v2 已实现的 `_read_range` + `debug_break(i)` 结构(无 role kwarg)· 命中分支已用 `pydevd.settrace(suspend=True)` + ImportError fallback。

- [ ] **Step 1.2: Create failing test file**

Create `tests/path2/test_debug_ctx.py`:

```python
"""v3 role-gated debug 单元测试。

覆盖:
- 生产零成本(DEBUG_MODE 未设 → 立即 return · 不读 env · 不 import pydevd)
- v1 兼容 fallback(DEBUG_ROLE 未设或空串 → 全 role fire)
- v3 role 门限(DEBUG_ROLE 设 → 只匹配 role fire · 其他 skip)
- required kwarg(缺 role → TypeError)

用 monkeypatch stub pydevd.settrace 为计数器 · 避免真 pause。
"""
import importlib
import os
import sys
from typing import List, Tuple

import pytest


@pytest.fixture
def fresh_debug_ctx(monkeypatch):
    """强制 reimport debug_ctx · 让 _DEBUG_MODE 读当前 env。返回 module。"""
    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ROLE", raising=False)
    sys.modules.pop("path2.debug_ctx", None)
    import path2.debug_ctx as m
    return m


@pytest.fixture
def fire_counter(monkeypatch, fresh_debug_ctx):
    """stub pydevd.settrace 为计数器 · 记录每次 fire 时的 role 上下文(靠 caller 传入)。
    ImportError fallback 用 stub breakpoint 也计数。"""
    hits: List[Tuple[int, str]] = []
    # 注 sys.modules['pydevd'] · 让 debug_break 里 `import pydevd` 拿到 stub
    class StubPydevd:
        @staticmethod
        def settrace(**kwargs):
            hits.append(("settrace", kwargs))
    monkeypatch.setitem(sys.modules, "pydevd", StubPydevd)
    # 也 stub breakpoint · 万一 ImportError fallback 走到
    monkeypatch.setattr("builtins.breakpoint", lambda: hits.append(("breakpoint", None)))
    return hits


def test_debug_mode_unset_early_return(monkeypatch):
    """DEBUG_MODE 未设 → 立即 return · 即使 range/role env 齐全也不 fire。"""
    monkeypatch.delenv("DEBUG_MODE", raising=False)
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ROLE", "gate")
    sys.modules.pop("path2.debug_ctx", None)
    import path2.debug_ctx as m
    # 无 pydevd stub · 若真 fire 会挂 stdin;此测试确认 _DEBUG_MODE=False 时不走 fire 路径
    m.debug_break(150, role="gate")   # 不该 fire · 无异常即 pass


def test_no_range_no_fire(fresh_debug_ctx, fire_counter):
    """DEBUG_MODE=1 · 但 DEBUG_BAR_RANGE 未设 → 不 fire。"""
    fresh_debug_ctx.debug_break(150, role="gate")
    assert fire_counter == []


def test_bar_out_of_range_no_fire(fresh_debug_ctx, fire_counter, monkeypatch):
    """bar 落 range 外 → 不 fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    fresh_debug_ctx.debug_break(50, role="gate")
    assert fire_counter == []


def test_v1_compat_no_role_env_fires_any_role(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ROLE 未设 → v1 兼容 · 任意 role fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    # DEBUG_ROLE 未设(fresh_debug_ctx fixture 已 delenv)
    fresh_debug_ctx.debug_break(150, role="gate")
    fresh_debug_ctx.debug_break(150, role="entry")
    fresh_debug_ctx.debug_break(150, role="trough")
    fresh_debug_ctx.debug_break(150, role="end")
    assert len(fire_counter) == 4


def test_v1_compat_empty_role_env_fires_any_role(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ROLE='' 空串 → v1 兼容 fallback · 任意 role fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ROLE", "")
    fresh_debug_ctx.debug_break(150, role="gate")
    fresh_debug_ctx.debug_break(150, role="entry")
    assert len(fire_counter) == 2


def test_role_env_gate_only_gate_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ROLE='gate' → 只 role='gate' fire · 其他 skip。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ROLE", "gate")
    fresh_debug_ctx.debug_break(150, role="gate")   # fire
    fresh_debug_ctx.debug_break(150, role="entry")  # skip
    fresh_debug_ctx.debug_break(150, role="trough") # skip
    fresh_debug_ctx.debug_break(150, role="end")    # skip
    assert len(fire_counter) == 1


def test_role_env_end_matches_end_role(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ROLE='end' → 只 role='end' fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ROLE", "end")
    fresh_debug_ctx.debug_break(150, role="end")
    fresh_debug_ctx.debug_break(150, role="gate")
    assert len(fire_counter) == 1


def test_role_kwarg_required_typeerror(fresh_debug_ctx):
    """debug_break(i) 缺 role kwarg → TypeError(required kwarg)。"""
    with pytest.raises(TypeError, match="role"):
        fresh_debug_ctx.debug_break(150)   # type: ignore[call-arg]


def test_role_positional_forbidden_typeerror(fresh_debug_ctx):
    """debug_break(i, role) 位置传 role → TypeError(keyword-only)。"""
    with pytest.raises(TypeError):
        fresh_debug_ctx.debug_break(150, "gate")   # type: ignore[misc]
```

- [ ] **Step 1.3: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v`

Expected: 所有 role-related tests FAIL(现 debug_break 签名不接 role kwarg · 抛 TypeError · 恰好某些 test 期待的 TypeError 反而不 fail · 但语义都不对)· 具体大部分 test collection 或 assert 层挂。

- [ ] **Step 1.4: Modify path2/debug_ctx.py**

Replace 全文为:

```python
"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时零成本短路(一次 bool 比较即返)。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8010):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_ROLE="role"(v3 新增 · handler 按 role query 设):限定命中角色;未设或空串 = v1 兼容(全 role fire)
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
import os
from typing import Optional

_DEBUG_MODE = os.environ.get("DEBUG_MODE") == "1"


def _read_range() -> Optional[tuple[int, int]]:
    """每次现读 env(handler 会动态覆盖);解析失败静默返 None,不干扰 detector。"""
    raw = os.environ.get("DEBUG_BAR_RANGE")
    if not raw:
        return None
    try:
        lo, hi = (int(x) for x in raw.split(","))
        return lo, hi
    except (ValueError, TypeError):
        return None


def _read_role() -> Optional[str]:
    """读 DEBUG_ROLE env · 未设或空串返 None(v1 兼容 fallback:不做 role 匹配)。"""
    r = os.environ.get("DEBUG_ROLE")
    return r if r else None


def debug_break(i: int, *, role: str) -> None:
    """在 detector 埋点处调用:DEBUG_MODE=1 且 i 落在 DEBUG_BAR_RANGE 内且 role 匹配 → 触发 pause。

    v3(2026-07-16)required keyword-only role 参数:
    - DEBUG_ROLE 未设或空串 → 只按 range 匹配(v1 兼容 · 全 role fire)
    - DEBUG_ROLE 设了 → range 匹配 && role 字面量匹配 · 才 fire
    - 缺 role kwarg → Python 抛 TypeError(required · 无 default)

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
    required = _read_role()
    if required is not None and required != role:
        return
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v`

Expected: 9/9 PASS。

- [ ] **Step 1.6: Regression — verify no other test breaks from debug_ctx change**

Run: `uv run pytest tests/path2/ tests/path2_web/ -x --timeout=60`

Expected: 之前的 pre-existing failures 仍以同样理由失败(不比 v2 baseline 差)· 无新失败 · 特别注意:因为 debug_break 现在 required kwarg · 若旧代码调用 `debug_break(x)` 无 role · Python 会抛 TypeError · 但这只会在 detector 实际调用时触发(测试如果 mock/skip detector 就不会碰到)。若有 test 因此挂 · 那是**预期**(Task 2 会修 detector 5 处补 role kwarg)· 记录挂的 test 名 · 留 Task 2 后验证复绿。

- [ ] **Step 1.7: Commit**

```bash
git add path2/debug_ctx.py tests/path2/test_debug_ctx.py
git commit -m "$(cat <<'EOF'
feat(debug): v3 role gate · debug_break required kwarg role + DEBUG_ROLE env

- _read_role() 读 DEBUG_ROLE env · 未设或空串返 None(v1 兼容 fallback)
- debug_break 签名改为 (i: int, *, role: str) · required kwarg · 无 default
- 判据:_DEBUG_MODE && bar in range && (required is None || required == role)
- fire API 不变:pydevd.settrace(suspend=True) · ImportError fallback breakpoint()
- 生产零成本:_DEBUG_MODE=False 时第一行 return · pydevd 不 import

单元测试覆盖:早退/无 range/out of range/v1 兼容(未设+空串)/role 门限/required kwarg TypeError/keyword-only forbidden positional。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: throwback.py 5 处 role kwarg + 契约锚测试

**Files:**
- Modify: `path2/atoms/throwback.py`(L104 · L163 · L216 · L221 · L247)
- Create: `tests/path2/atoms/test_throwback_debug_roles.py`

**Interfaces:**
- Consumes: Task 1 的 `debug_break(i: int, *, role: str) -> None`
- Produces: 无(埋点契约的锚点)

### Steps

- [ ] **Step 2.1: Read current throwback.py debug_break sites**

Run: `grep -n "debug_break" path2/atoms/throwback.py`

Expected: 5 处调用 · 分别在 L104 / L163 / L216 / L221 / L247 · 每处形如 `debug_break(<expr>)` 无 role kwarg。

- [ ] **Step 2.2: Create failing 契约锚 test**

Create `tests/path2/atoms/test_throwback_debug_roles.py`:

```python
"""v3 role-gated debug 契约锚测试(throwback.py)。

用 ast 静态解析,不运行 detector,不依赖 fixture。

契约:
- throwback.py 里必有且只有 5 处 debug_break call(总数守恒)
- 每处必须传 role kwarg,且必须是 str literal(不允许变量 / f-string / 表达式)
- 5 处 role 字面量分布 Counter == {'gate':1, 'trough':1, 'end':2, 'entry':1}

不依赖精确 lineno · 抗 throwback.py 上下加行漂移。
"""
import ast
import pathlib
from collections import Counter


THROWBACK_PATH = pathlib.Path(__file__).resolve().parents[3] / "path2" / "atoms" / "throwback.py"
EXPECTED_ROLE_COUNTER = Counter({"gate": 1, "trough": 1, "end": 2, "entry": 1})


def _collect_debug_break_calls():
    src = THROWBACK_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(THROWBACK_PATH))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "debug_break"]


def test_throwback_has_exactly_five_debug_break_calls():
    calls = _collect_debug_break_calls()
    assert len(calls) == 5, (
        f"expected 5 debug_break calls in throwback.py · got {len(calls)}"
        f" at lines {[c.lineno for c in calls]}"
    )


def test_every_debug_break_has_role_kwarg_as_str_literal():
    calls = _collect_debug_break_calls()
    for c in calls:
        role_kw = next((k for k in c.keywords if k.arg == "role"), None)
        assert role_kw is not None, (
            f"L{c.lineno} debug_break missing required role kwarg"
        )
        assert isinstance(role_kw.value, ast.Constant) and isinstance(role_kw.value.value, str), (
            f"L{c.lineno} role must be str literal (for grep-ability) · got "
            f"{ast.dump(role_kw.value)}"
        )


def test_throwback_role_distribution_matches_baseline():
    """role 分布 Counter 严格等于 baseline · 抗 lineno 漂移。"""
    calls = _collect_debug_break_calls()
    roles = [
        next(k.value.value for k in c.keywords if k.arg == "role")
        for c in calls
    ]
    actual = Counter(roles)
    assert actual == EXPECTED_ROLE_COUNTER, (
        f"role distribution mismatch:\n"
        f"  expected {dict(EXPECTED_ROLE_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"roles: {roles}"
    )
```

- [ ] **Step 2.3: Run 契约锚 test to verify it fails**

Run: `uv run pytest tests/path2/atoms/test_throwback_debug_roles.py -v`

Expected: `test_every_debug_break_has_role_kwarg_as_str_literal` 和 `test_throwback_role_distribution_matches_baseline` FAIL(现 5 处 debug_break 无 role kwarg)。

- [ ] **Step 2.4: Modify path2/atoms/throwback.py 5 处 debug_break call**

对每处逐个 Edit(用现有 Edit tool · 保留原注释):

L104 内:
```python
# 旧:
debug_break(gate_idx)
# 改:
debug_break(gate_idx, role='gate')
```

L163 附近:
```python
# 旧:
debug_break(trough_idx)  # v2 · phase1 success(与 event.start_idx 对齐)
# 改:
debug_break(trough_idx, role='trough')  # v2 · phase1 success(与 event.start_idx 对齐)
```

L216 附近:
```python
# 旧:
debug_break(i - 1)  # v2 · phase2 rise end(⚠ i-1 与 event.end_idx 对齐, 非 i)
# 改:
debug_break(i - 1, role='end')  # v2 · phase2 rise end(⚠ i-1 与 event.end_idx 对齐, 非 i)
```

L221 附近:
```python
# 旧:
debug_break(end_scan)  # v2 · phase2 timeout end(与 event.end_idx 对齐)
# 改:
debug_break(end_scan, role='end')  # v2 · phase2 timeout end(与 event.end_idx 对齐)
```

L247 附近:
```python
# 旧:
debug_break(bo_idx)  # v2 · attempt entry(dead code when _DEBUG_MODE=False)
# 改:
debug_break(bo_idx, role='entry')  # v2 · attempt entry(dead code when _DEBUG_MODE=False)
```

- [ ] **Step 2.5: Run 契约锚 test to verify it passes**

Run: `uv run pytest tests/path2/atoms/test_throwback_debug_roles.py -v`

Expected: 3/3 PASS。

- [ ] **Step 2.6: Regression — full throwback suite**

Run: `uv run pytest tests/path2/atoms/ -v`

Expected: 现有 throwback 相关测试全部 pass(pre-existing v2 baseline)· debug_break 现在有 role kwarg · 与 Task 1 debug_ctx 匹配。若 Task 1 Step 1.6 记录过因 required kwarg 挂的 test · 此步应复绿。

- [ ] **Step 2.7: Commit**

```bash
git add path2/atoms/throwback.py tests/path2/atoms/test_throwback_debug_roles.py
git commit -m "$(cat <<'EOF'
feat(debug): v3 · throwback 5 处 debug_break 补 role kwarg + 契约锚测试

- L104 role='gate' · L163 role='trough' · L216 role='end' · L221 role='end' · L247 role='entry'
- role 分布 Counter = {'gate':1, 'trough':1, 'end':2, 'entry':1}(与 spec baseline 一致)
- 契约锚 test 用 ast 静态解析 · 抗 lineno 漂移(用 role Counter 而非精确行号 assert)
- 补 role kwarg 后与 Task 1 required kwarg 签名匹配 · 消除 TypeError

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: /diagnose handler role query + finally 双 env pop

**Files:**
- Modify: `path2_web/api.py`(get_diagnose handler · L198 附近)
- Create: `tests/path2_web/test_diagnose_role_env.py`

**Interfaces:**
- Consumes: Task 1 `debug_break` · Task 2 throwback role kwarg
- Produces: `/diagnose` HTTP endpoint 新增 optional `role: Optional[str] = None` query 参数

### Steps

- [ ] **Step 3.1: Read current handler**

Run: `sed -n '198,250p' path2_web/api.py`

Expected: v2 handler 结构:sync def · start_bar/end_bar → env DEBUG_BAR_RANGE · try/finally pop DEBUG_BAR_RANGE。

- [ ] **Step 3.2: Create failing handler test**

Create `tests/path2_web/test_diagnose_role_env.py`:

```python
"""v3 handler role query + 双 env pop 测试。

覆盖:
- role query 写 env DEBUG_ROLE(非空)
- 无 role query · 不写 DEBUG_ROLE env
- 空串 role · 不写 DEBUG_ROLE env(handler 判据 `if role:`)
- finally 无条件 pop 双 env(异常路径也测)
- 跨 request 隔离:上次 preset DEBUG_ROLE · 本次不传 role · finally 依然 pop 兜底
"""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带真实数据的 test client · dataset_dir=tmp_path。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ROLE", raising=False)

    data = tmp_path / "data"
    data.mkdir()
    n = 200
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
        "close": [10.5] * n, "volume": [100.0] * n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-07-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


def _diagnose_url(role: str | None = None, start_bar: int = 50, end_bar: int = 80):
    q = ("pattern_id=bo_only&symbol=AAA&start=2024-01-01&end=2024-07-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if role is not None:
        q += f"&role={role}"
    return f"/diagnose?{q}"


def test_role_query_writes_debug_role_env_during_request(client, monkeypatch):
    """GET ?role=gate · handler try 期间 env DEBUG_ROLE 写入。用 monkeypatch hijack
    debug_break 观测 · 因 handler finally 会 pop · request 结束后 env 已清。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    real = dc.debug_break
    def spy(i, *, role):
        captured.append(os.environ.get("DEBUG_ROLE"))
        # 不 fire · 避免 breakpoint 挂
    monkeypatch.setattr(dc, "debug_break", spy)
    # detector 通过 `from path2.debug_ctx import debug_break` 引用 · 也需 patch
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(role="gate"))
    assert r.status_code == 200
    # handler try 期间至少一次 debug_break 被调 · 其时 DEBUG_ROLE 应 == 'gate'
    assert "gate" in captured, f"expected 'gate' in captured env values, got {captured}"


def test_no_role_query_does_not_write_debug_role_env(client, monkeypatch):
    """GET 不传 role · handler 不写 DEBUG_ROLE env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, role):
        captured.append(os.environ.get("DEBUG_ROLE"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(role=None))
    assert r.status_code == 200
    # request 期间 DEBUG_ROLE 始终未设(None)
    assert all(v is None for v in captured), (
        f"expected DEBUG_ROLE unset for all captured, got {captured}"
    )


def test_empty_role_query_does_not_write_debug_role_env(client, monkeypatch):
    """GET ?role= 空串 · handler 判据 `if role:` · 不写 env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, role):
        captured.append(os.environ.get("DEBUG_ROLE"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(role=""))
    assert r.status_code == 200
    assert all(v is None for v in captured), (
        f"expected DEBUG_ROLE unset (empty role treated as unset), got {captured}"
    )


def test_finally_pops_both_envs_on_success(client):
    """handler 正常返回后 · 两 env 都 pop 清 · 无残留。"""
    r = client.get(_diagnose_url(role="gate"))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_BAR_RANGE") is None
    assert os.environ.get("DEBUG_ROLE") is None


def test_finally_pops_debug_role_env_bootstrap_pollution(client, monkeypatch):
    """跨 request 隔离:preset DEBUG_ROLE='stale' · 本次不传 role · finally 依然 pop 兜底
    (无条件 pop DEBUG_ROLE · 不管本次是否写过)。"""
    monkeypatch.setenv("DEBUG_ROLE", "stale")
    # 注:monkeypatch.setenv 会在 test 结束自动 restore · 所以我们在 request 前手动 unset
    # · 用 os.environ.pop 来测 handler finally 是否 pop
    r = client.get(_diagnose_url(role=None))
    assert r.status_code == 200
    # handler finally 应 pop DEBUG_ROLE(哪怕本次没写)
    assert os.environ.get("DEBUG_ROLE") is None, (
        "handler finally should pop DEBUG_ROLE unconditionally to prevent "
        "cross-request pollution"
    )
```

- [ ] **Step 3.3: Run test to verify it fails**

Run: `uv run pytest tests/path2_web/test_diagnose_role_env.py -v`

Expected: 5/5 FAIL(现 handler 无 role 参数 · env 从未写 DEBUG_ROLE · finally 也不 pop 它)。

- [ ] **Step 3.4: Modify path2_web/api.py handler**

Locate `def get_diagnose(...)` 签名(约 L198-205)· 用 Edit 精准替换:

先看现签名:
```python
    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_role: Optional[str] = None, dst_role: Optional[str] = None,
                     event_class: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None):
```

改为(签名末尾追加 `role`):
```python
    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_role: Optional[str] = None, dst_role: Optional[str] = None,
                     event_class: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                     role: Optional[str] = None):
```

再定位 env 写入分支(约 L209-210):
```python
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
```

追加 role 写入:
```python
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if role:                                    # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ROLE"] = role
```

再定位 finally 分支(约 L247-248):
```python
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
```

改为双 env pop:
```python
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ROLE", None)      # ★ v3 · 无条件 pop 兜底(跨 request 隔离)
```

同时更新 handler 顶部注释(约 L206-208 附近)· 追加 v3 契约 #7 扩展:
```python
        # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
        # 供 path2.debug_ctx.debug_break 消费。v2(2026-07-15 event-debug-dual-emit) 契约 #7:
        # handler 结束必 pop env(request 级作用域, 防跨 request 污染 + scan pool 继承挂死)。
        # v3(2026-07-16 role-gated-debug) 契约 #7 扩展:双 env 独立(DEBUG_BAR_RANGE +
        # DEBUG_ROLE)· finally 无条件 pop 两 env(即使本次未写 DEBUG_ROLE 也 pop 兜底)。
```

- [ ] **Step 3.5: Run test to verify it passes**

Run: `uv run pytest tests/path2_web/test_diagnose_role_env.py -v`

Expected: 5/5 PASS。

- [ ] **Step 3.6: Regression — verify existing v2 handler tests still pass**

Run: `uv run pytest tests/path2_web/ -v --timeout=60`

Expected: v2 test_diagnose_finally_pop.py · test_debug_env_injection.py 保 pass · 无新回归。之前 pre-existing failures 仍以同理由失败。

- [ ] **Step 3.7: Commit**

```bash
git add path2_web/api.py tests/path2_web/test_diagnose_role_env.py
git commit -m "$(cat <<'EOF'
feat(diagnose): v3 · handler 加 role query + finally 双 env pop

- get_diagnose 签名追加 optional role: Optional[str] = None
- 写 env 判据 `if role:` · 空串视同未传(不写 DEBUG_ROLE env)
- finally 无条件 pop 两 env(DEBUG_BAR_RANGE + DEBUG_ROLE)· 兜底跨 request 污染
- v3 契约 #7 扩展:双 env 独立 pop · 与 v2 契约兼容(无 role 时行为等价 v2)
- v1 API 兼容:不传 role query · DEBUG_ROLE env 不设 · debug_ctx 全 role fire

单元测试覆盖:role 写 env · 无 role/空串不写 · 正常/异常路径 finally pop · 跨 request preset 污染兜底 pop。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 前端 api.ts + view.ts role 透传 + vitest

**Files:**
- Modify: `path2_web_ui/src/api.ts`(getTimeDiagnose 签名 + URL 拼接)
- Modify: `path2_web_ui/src/stores/view.ts`(入口 A brush 和入口 D triggerEventDebug 两处调用)
- Create: `path2_web_ui/tests/api.getTimeDiagnose-role.spec.ts`
- Create: `path2_web_ui/tests/stores.role-mapping.spec.ts`

**Interfaces:**
- Consumes: Task 3 的 `/diagnose?role=<role>` HTTP endpoint
- Produces: `getTimeDiagnose(...role?: string)` 前端 API · 两入口自动供 role

### Steps

- [ ] **Step 4.1: Read current api.ts getTimeDiagnose**

Run: `sed -n '50,65p' path2_web_ui/src/api.ts`

Expected: v2 签名 `(patternId, symbol, start, end, startBar, endBar, eventClass?, signal?)` · URL 无 role query。

- [ ] **Step 4.2: Read current view.ts 两入口调用点**

Run: `grep -n "getTimeDiagnose" path2_web_ui/src/stores/view.ts`

Expected: 两处调用点 · 一处入口 A(brush 触发 · 存 `timeScopeResponse.value`)· 一处入口 D(triggerEventDebug 内 · 传 anchor.bar)。

- [ ] **Step 4.3: Read view.ts 两处上下文各 15 行**

Run: `sed -n '505,525p' path2_web_ui/src/stores/view.ts` (入口 A brush 附近)
Run: `sed -n '545,570p' path2_web_ui/src/stores/view.ts` (入口 D triggerEventDebug 附近)

Expected: 定位调用点的完整参数列表(用于精准 Edit 的 old_string 上下文)。

- [ ] **Step 4.4: Create failing vitest tests**

Create `path2_web_ui/tests/api.getTimeDiagnose-role.spec.ts`:

```typescript
/**
 * v3 · getTimeDiagnose URL 参数 role 拼接测试。
 *
 * 契约:
 * - 传 role='gate' → URL 含 '&role=gate'
 * - 传 undefined → URL 不含 role query
 * - 传空串 '' → URL 不含 role query(与后端 handler 空串判据对齐 · 前端主动 skip)
 * - encodeURIComponent 正确
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getTimeDiagnose } from '../src/api'

describe('getTimeDiagnose role query 拼接', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'time', payload: {}, caveats: [] }),
    } as any)
  })

  it('传 role="gate" · URL 含 &role=gate', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'gate')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&role=gate')
  })

  it('传 role="trough" · URL 含 &role=trough', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'trough')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&role=trough')
  })

  it('不传 role(undefined)· URL 不含 role', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined)
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).not.toContain('role=')
  })

  it('传空串 role="" · URL 不含 role', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, '')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).not.toContain('role=')
  })

  it('特殊字符 role encodeURIComponent 正确(防守 · 目前 role 词汇纯字母)', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'gate&x=y')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&role=gate%26x%3Dy')
  })
})
```

Create `path2_web_ui/tests/stores.role-mapping.spec.ts`:

```typescript
/**
 * v3 · store 两入口的 role 供给测试。
 *
 * 契约:
 * - triggerEventDebug(id, 'entry') → getTimeDiagnose 调用参数 role='entry'
 * - triggerEventDebug(id, 'trough') → role='trough'
 * - triggerEventDebug(id, 'end') → role='end'
 * - 入口 A(brush · timeScopeResponse 路径)→ getTimeDiagnose 调用 role='gate'
 *
 * 前后端 role 字面量一致性靠此测试兜底(与 test_throwback_debug_roles Python 侧联防)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import * as api from '../src/api'

// 最小 fixture · 模拟 store 已加载 scan 结果 + 已选 pattern + 已选 symbol
function seedStoreForDebug(store: ReturnType<typeof useViewStore>) {
  store.symbol = 'AAA'
  store.activePatternId = 'bottom_burst'
  store.scanFile = {
    scan: {
      start_date: '2024-01-01', end_date: '2024-07-01',
      label_horizon: 20, win_start: '2024-01-01', win_end: '2024-07-01',
    } as any,
    per_pattern: {},
  } as any
  // 塞一个 tb event 供 anchorsOf 查
  const tbEvent = {
    event_id: 'ev_tb_1', class_id: 'tb', start_idx: 100, end_idx: 105,
    anchor_bo_id: 'ev_bo_1',
  } as any
  const boEvent = {
    event_id: 'ev_bo_1', class_id: 'bo', start_idx: 50, end_idx: 90,
  } as any
  ;(store as any).preview = {
    symbol: 'AAA',
    analysis: { events: [tbEvent, boEvent] },
    pattern_spec: {}, scan: {} as any,
  }
  ;(store as any).previewEnabled = true
}


describe('triggerEventDebug 供 role', () => {
  let getTimeDiagnoseSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    setActivePinia(createPinia())
    getTimeDiagnoseSpy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({
      scope: 'time', payload: {}, caveats: [],
    } as any)
  })

  it('anchor.key="entry" → getTimeDiagnose role="entry"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'entry')
    // getTimeDiagnose 签名末位是 role(第 9 位 · 0-indexed 是 8)
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('entry')
  })

  it('anchor.key="trough" → getTimeDiagnose role="trough"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'trough')
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('trough')
  })

  it('anchor.key="end" → getTimeDiagnose role="end"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'end')
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('end')
  })
})


describe('入口 A(brush)供 role="gate"', () => {
  let getTimeDiagnoseSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    setActivePinia(createPinia())
    getTimeDiagnoseSpy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({
      scope: 'time', payload: {}, caveats: [],
    } as any)
  })

  it('brush 触发的 diag 调用 · getTimeDiagnose 参数 role="gate"', async () => {
    // view.ts 里 brush 场景对应的 action(读代码定位:直接调 timeScopeResponse 的
    // async 路径 · 通常在 KlineChart brush 结束 handler 里)· 用 store 暴露的
    // action 名调用 · 若 action 未暴露 · 用 store 内部函数触发。
    // 参考:brush 场景的 diag 调用点位于 view.ts:513 附近
    const store = useViewStore()
    seedStoreForDebug(store)
    // 直接调 store 里 brush 触发点的 action(见 view.ts 实际 action 名)
    // NOTE: 若 view.ts 里 brush handler 是内部函数 · 需 export or 通过公共 action 触发
    if (typeof (store as any).fetchTimeScope === 'function') {
      await (store as any).fetchTimeScope(50, 80)
    } else {
      // fallback:直接调 view.ts:513 的调用点(implementer 按实际 action 名调整)
      // 若 store 未暴露 brush action · 用 view.ts 里 brush handler 的 named export
      throw new Error(
        'brush action not exposed via store; ' +
        'implementer: locate view.ts:513 action name and update this test'
      )
    }
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('gate')
  })
})
```

**注**:入口 A 的 store action 名 · implementer 在 Step 4.3 读 view.ts 时确认后填入 test。若 brush 触发是通过 KlineChart 组件直接调 store 某 action · 就直接调该 action。若 view.ts 里是内联的 async 匿名函数 · 需 refactor 抽 named action(此 refactor 属于 Task 4 范围)。

- [ ] **Step 4.5: Run vitest to verify tests fail**

Run: `cd path2_web_ui && npx vitest run tests/api.getTimeDiagnose-role.spec.ts tests/stores.role-mapping.spec.ts`

Expected: 大部分 FAIL(getTimeDiagnose 无 role 参数 · view.ts 两入口未传 role)。

- [ ] **Step 4.6: Modify path2_web_ui/src/api.ts**

Locate `export function getTimeDiagnose(` · 用 Edit 精准替换 · 签名末位加 `role?: string` · URL 拼接末位加 role query:

先看现签名:
```typescript
export function getTimeDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  startBar: number, endBar: number, eventClass?: string,
  signal?: AbortSignal,
): Promise<TimeScopeResponse> {
  const url = `${BASE}/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=time`
    + `&start_bar=${startBar}&end_bar=${endBar}`
    + (eventClass ? `&event_class=${encodeURIComponent(eventClass)}` : '')
  return fetch(url, { signal }).then(async r => {
    if (!r.ok) throw new Error(`GET ${url} → ${r.status}: ${await r.text()}`)
    return r.json() as Promise<TimeScopeResponse>
  })
}
```

改为:
```typescript
export function getTimeDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  startBar: number, endBar: number, eventClass?: string,
  signal?: AbortSignal,
  role?: string,                       // ★ v3 · role 门限透传
): Promise<TimeScopeResponse> {
  const url = `${BASE}/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=time`
    + `&start_bar=${startBar}&end_bar=${endBar}`
    + (eventClass ? `&event_class=${encodeURIComponent(eventClass)}` : '')
    + (role ? `&role=${encodeURIComponent(role)}` : '')   // ★ v3 · 空串也 skip · 与后端 handler `if role:` 判据对齐
  return fetch(url, { signal }).then(async r => {
    if (!r.ok) throw new Error(`GET ${url} → ${r.status}: ${await r.text()}`)
    return r.json() as Promise<TimeScopeResponse>
  })
}
```

- [ ] **Step 4.7: Modify path2_web_ui/src/stores/view.ts 入口 A(brush)**

Locate 入口 A 调用点(约 L513 附近)· 用 Edit 精准替换 · 追加 role='gate' 为末位参数。

先在 Step 4.3 中确认调用点上下文(约):
```typescript
      timeScopeResponse.value = await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end,
        startBar, endBar)
```

改为(追加所有中间 optional 参数为 undefined + 末位 role='gate'):
```typescript
      timeScopeResponse.value = await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end,
        startBar, endBar, undefined, undefined, 'gate')   // ★ v3 · 入口 A 硬编码 role='gate'
```

**注**:若原调用有传 eventClass / signal · 保留原值 · 只在末位追加 'gate'。implementer 按实际调用形态调 · 保 role='gate' 是第 9 位参数。

- [ ] **Step 4.8: Modify path2_web_ui/src/stores/view.ts 入口 D(triggerEventDebug)**

Locate triggerEventDebug 内的 getTimeDiagnose 调用(约 L553 附近):

```typescript
      await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end,
        anchor.bar, anchor.bar, event.class_id, controller.signal,
      )
```

改为(追加 role=anchor.key):
```typescript
      await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end,
        anchor.bar, anchor.bar, event.class_id, controller.signal,
        anchor.key,                                       // ★ v3 · anchor.key 直接透传为 role
      )
```

**注**:`anchor.key` 已是 `'entry' | 'trough' | 'end'` 三选一(anchorsOf.tb 定义)· 与后端 role 词汇 baseline 一一对齐。前后端字符串一致由 vitest role-mapping test + Python 侧 test_throwback_debug_roles Counter 双保险。

- [ ] **Step 4.9: Run vitest to verify tests pass**

Run: `cd path2_web_ui && npx vitest run tests/api.getTimeDiagnose-role.spec.ts tests/stores.role-mapping.spec.ts`

Expected: 全部 PASS(9 个 test:api 5 + stores 4)。

- [ ] **Step 4.10: 若 stores.role-mapping brush 场景 test 失败 · 抽 named action**

若 Step 4.9 里 `入口 A(brush)供 role="gate"` test 报 "brush action not exposed" · 需要在 view.ts 里把 brush 触发的匿名 async 抽为 named action(如 `fetchTimeScope(startBar, endBar)`)· 让 KlineChart brush handler 调 action · store 内部保留同样 fetch 逻辑。

Refactor 步骤:
1. 定位 view.ts 里 brush 触发的 async 函数(内联在 `.then` / `watch` 里)
2. 提取为 `async function fetchTimeScope(startBar: number, endBar: number) { ... }`
3. 在 store return 里 export 该 action
4. KlineChart.vue 里 brush handler 从 store 调新 action
5. 重跑 vitest · 应 pass

- [ ] **Step 4.11: 全局前端 gate**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npm run build`

Expected:
- vitest 全绿(pre-existing 2 个 ScanConfigDialog failed 保留 · 但总数增加 9 个新 test 全绿)
- vue-tsc clean
- build 成功

- [ ] **Step 4.12: Commit**

```bash
git add path2_web_ui/src/api.ts path2_web_ui/src/stores/view.ts \
        path2_web_ui/tests/api.getTimeDiagnose-role.spec.ts \
        path2_web_ui/tests/stores.role-mapping.spec.ts
git commit -m "$(cat <<'EOF'
feat(debug-ui): v3 · getTimeDiagnose 加 role + 两入口透传

- api.ts: getTimeDiagnose 签名末位加 optional role?: string · URL 拼 role query(空串 skip)
- view.ts 入口 A(brush timeScopeResponse):硬编码 role='gate'
- view.ts 入口 D(triggerEventDebug):role=anchor.key(entry/trough/end 三选一)
- vitest 覆盖:URL 拼接 5 case + role 供给 4 case(3 anchor + 1 brush)
- 契约 #4 加强:role 字符串前后端一致(vitest 与 Python 侧 test_throwback_debug_roles Counter 双保险)
- v1 API 兼容:未加 role 参数时 URL 无 role query · handler 收 role=None · env DEBUG_ROLE 不写 · debug_break 走 v1 全 fire 分支

若 brush 场景 action 抽 named(fetchTimeScope)· 一并落地(细节见 plan Task 4 Step 4.10)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 集成测试 + 文档同步(e2e checklist 场景 J)

**Files:**
- Create: `tests/path2_web/test_diagnose_role_integration.py`
- Modify: `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md`(追加场景 J1/J2/J3)

**Interfaces:**
- Consumes: Task 1(debug_break)· Task 2(throwback role kwarg)· Task 3(handler role query + env)· Task 4(前端 role 透传)· 全链验证
- Produces: 集成测试 baseline · e2e 手动 checklist 增补

### Steps

- [ ] **Step 5.1: Create failing 集成测试**

Create `tests/path2_web/test_diagnose_role_integration.py`:

```python
"""v3 集成测试:GET /diagnose?role=X 时 · monkeypatch pydevd.settrace 为 counter ·
assert 只对应 role 埋点 fire · 其他 skip。

覆盖:
- role='gate' → 只 role='gate' 埋点 fire · 其他 skip
- role='entry' → 只 'entry' fire
- role='trough' → 只 'trough' fire
- role='end' → 只 'end' fire
- 无 role → 4 种 role 都 fire(v1 兼容)

同时验证 fire 参数值确实落在 range 内(与 v2 契约 #4 加强联防)。
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client_with_real_pkl(tmp_path, monkeypatch):
    """使用真实 pkl 数据(dataset_dir 复用 /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls)
    · 保 TSLA 类活跃股票有 tb events 命中埋点。若数据集不可访问 · skip test。"""
    real_dataset = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    if not (real_dataset / "TSLA.pkl").exists():
        pytest.skip("real dataset unavailable · skip integration test")

    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ROLE", raising=False)

    # 强制 reimport debug_ctx · 让 _DEBUG_MODE 读当前 env
    sys.modules.pop("path2.debug_ctx", None)

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
    """monkeypatch pydevd.settrace + breakpoint · 记录每次 fire 时的 (bar, role)。

    因为 debug_break 内部 fire 时不知道自己是哪个 (bar, role) 上下文 · 我们在
    debug_break 外层再套一层 wrapper · 捕获参数。"""
    hits: list[tuple[int, str]] = []
    import path2.debug_ctx as dc

    real = dc.debug_break

    def wrapped(i: int, *, role: str) -> None:
        # 复刻 real debug_break 的判据 · 只在 fire 分支 append
        if not dc._DEBUG_MODE:
            return
        r = dc._read_range()
        if r is None:
            return
        if not (r[0] <= i <= r[1]):
            return
        required = dc._read_role()
        if required is not None and required != role:
            return
        hits.append((i, role))
        # 不真 fire · 避免 breakpoint 挂 stdin

    monkeypatch.setattr(dc, "debug_break", wrapped)
    # detector 通过 `from path2.debug_ctx import debug_break` · patch 处也需
    monkeypatch.setattr("path2.atoms.throwback.debug_break", wrapped)
    return hits


def _url(role: str | None = None, start_bar: int = 0, end_bar: int = 250):
    q = ("pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}&event_class=tb")
    if role:
        q += f"&role={role}"
    return f"/diagnose?{q}"


def test_role_gate_only_gate_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(role="gate"))
    assert r.status_code == 200
    roles_fired = {role for _, role in fire_recorder}
    assert roles_fired == {"gate"}, (
        f"expected only 'gate' fires · got {roles_fired} · full hits: {fire_recorder}"
    )


def test_role_entry_only_entry_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(role="entry"))
    assert r.status_code == 200
    roles_fired = {role for _, role in fire_recorder}
    assert roles_fired == {"entry"}, (
        f"expected only 'entry' fires · got {roles_fired}"
    )


def test_role_trough_only_trough_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(role="trough"))
    assert r.status_code == 200
    roles_fired = {role for _, role in fire_recorder}
    # trough 埋点在 phase1 success 分支 · 需 tb 有真实 match 才 fire · 若数据无 tb match
    # 集合可能是空(允许) · 若非空则必须只含 trough
    assert roles_fired <= {"trough"}, (
        f"expected only 'trough' (or empty) fires · got {roles_fired}"
    )


def test_role_end_only_end_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(role="end"))
    assert r.status_code == 200
    roles_fired = {role for _, role in fire_recorder}
    assert roles_fired <= {"end"}, (
        f"expected only 'end' (or empty) fires · got {roles_fired}"
    )


def test_no_role_v1_compat_all_roles_fire(client_with_real_pkl, fire_recorder):
    """v1 兼容 · 无 role query · 全 role 都可能 fire。"""
    r = client_with_real_pkl.get(_url(role=None))
    assert r.status_code == 200
    roles_fired = {role for _, role in fire_recorder}
    # v1 兼容 · 至少 gate 或 entry 会 fire(TSLA 2025 数据几乎必有 bo 触发 evaluate_throwback)
    assert len(roles_fired) >= 1, (
        f"expected at least 1 role fires under v1 compat · got empty"
    )
```

- [ ] **Step 5.2: Run 集成测试**

Run: `uv run pytest tests/path2_web/test_diagnose_role_integration.py -v`

Expected: 5/5 PASS(或若 TSLA.pkl 不可访问 · skip)· 关键 assert 是 `roles_fired == {'gate'}` / `{'entry'}` / `<= {'trough'}` / `<= {'end'}`。

- [ ] **Step 5.3: Read current e2e checklist**

Run: `wc -l docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md`

Expected: 现有 v2 checklist(应包含场景 A-I)。

- [ ] **Step 5.4: Append v3 场景 J 到 checklist**

Modify `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md` · 在文件末尾追加:

```markdown

---

## 场景 J · v3 role-gated 隔离(2026-07-16 补 · spec `2026-07-16-path2-role-gated-debug-design.md`)

### 前置
- 与场景 A-C 相同(PyCharm 以 Debug 方式跑 `path2_web.main` · DEBUG_MODE=1 · 前端 `VITE_API_BASE=http://localhost:8010 npm run dev -- --port 5174 --strictPort`)
- 打开一只有 tb match 的股票(如 TSLA · 2025-01-01 ~ 2026-01-01)

### J1 · 入口 A(brush 框选)role 隔离

**目的**:验证 v3 修复 · 入口 A 只 pause 在 gate 失败点 · 不再被 v2 entry/trough/end 埋点污染。

**步骤**:
1. 主图工具栏点「框选」进入 brush 模式
2. 在 K 线主图上框选一段跨越多个 bo 的区间(≥ 50 bar)
3. 观察 PyCharm Debug 面板 · 记录 pause 位置

**判据**:
- ✅ pause 只出现在 `throwback.py:105`(`_emit_tb_gate` 内 · L104 debug_break 后一行)
- ✅ **不再**出现 pause 在 `throwback.py:248`(L247 entry 后)/ `throwback.py:164`(L163 trough 后)/ `throwback.py:217/222`(L216/L221 end 后)
- ✅ 每次 pause · Frame 显示 `_emit_tb_gate` 或 `evaluate_throwback` · 变量含 `gate_idx` / `gate_name` / `measured` / `threshold`
- ⚠ 若框选区间内有多个 bo 走到 gate 失败 · 依然会多次 pause 在 L105 · 但每次都是 gate 语义 · 无其他 role noise · Resume 逐个看

### J2 · 入口 D(marker 右键)role 精准

**目的**:验证 marker 右键选 anchor 时 · 只 pause 在对应 role 埋点。

**步骤**:
1. 选一个 tb marker · 右键弹菜单
2. 分别选 `Debug tb entry` / `Debug tb trough` / `Debug tb end` 三次(每次做完 Resume 到底再做下一个)

**判据**:
- ✅ 选 entry → pause 只在 `throwback.py:248`(L247 entry 后)· 不 pause 在 164/217/222
- ✅ 选 trough → pause 只在 `throwback.py:164`(L163 trough 后)· 不 pause 在 248/217/222
- ✅ 选 end → pause 只在 `throwback.py:217` 或 `throwback.py:222`(L216/L221 end 后 · 取决于 rise vs timeout)· 不 pause 在 248/164
- ✅ 三次调试独立 · 前次 role 不污染后次(DEBUG_ROLE env 每次 handler finally 都 pop)

### J3 · v1 兼容 · curl 不带 role

**目的**:验证 v3 前端不改的 v1 API 用户 · 依然 fire 全 role(与 v2 e2e 场景 A/B/C 兜底覆盖)。

**步骤**:
1. 前端不操作 · 直接在终端手工 curl:
   ```bash
   curl -o /tmp/r.json 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250&event_class=tb'
   ```
   (**注**:URL 不含 `&role=...` · 模拟 v1 API 用户)
2. 观察 PyCharm Debug 面板

**判据**:
- ✅ pause 依然会命中(证明 v1 兼容 fallback 生效)
- ✅ pause 出现在多个位置(L104/L163/L216/L221/L247 · 全 role fire · 与 v2 pre-role-gate 行为等价)
- ✅ 与 v2 e2e checklist 场景 A/B/C 用同一路径 · 判定 v3 未破坏 v1 行为
```

- [ ] **Step 5.5: Commit**

```bash
git add tests/path2_web/test_diagnose_role_integration.py \
        docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md
git commit -m "$(cat <<'EOF'
test(debug-integration): v3 · role 全链集成 + e2e 场景 J 增补

集成测试(pytest · monkeypatch pydevd wrapper 记 fire (bar, role)):
- role='gate' → 只 gate 埋点 fire
- role='entry' → 只 entry fire
- role='trough' → 只 trough fire(或空 · 若无 tb match)
- role='end' → 只 end fire(或空)
- 无 role → v1 兼容 · 至少 1 role fire

e2e checklist 场景 J1/J2/J3:
- J1 入口 A role 隔离(修复目标验证 · pause 只 L105)
- J2 入口 D role 精准(3 anchor 各自独立)
- J3 v1 兼容(curl 不带 role · 全 role fire · 与 v2 行为等价)

TSLA.pkl 不可访问时集成测试 skip · 保 CI 健壮。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Final Validation(手动 · lead/user 在 PyCharm 里跑)

**Non-subagent 环节** · 由 lead/user 手动执行:

- [ ] **FV1**:按 e2e checklist 场景 J1 步骤 · 手动跑 · 记录 pass/fail
- [ ] **FV2**:按场景 J2 步骤 · 手动跑 · 记录 pass/fail
- [ ] **FV3**:按场景 J3 步骤 · 手动跑 · 记录 pass/fail
- [ ] **FV4** · Regression(手动重跑 v2 e2e 场景 A-C):
  - 场景 A:tb marker 右键选 entry · pause 一次 · Resume 后再选同 anchor · 应能连续 pause(pydevd 长期 fix 保护)
  - 场景 B:tb marker 右键选 trough · pause 一次 · Resume 完毕
  - 场景 C:tb marker 右键选 end · pause 一次(rise 或 timeout · 取决于数据)· Resume 完毕
- [ ] **FV5**:后端 log 检查 · 无 DEBUG_ROLE 残留(handler finally pop 兜底验证)
- [ ] **FV6**:文档同步(可选)· 通过 `update-ai-context` skill 更新 `.claude/docs/modules/path2.md` 和 `path2_web.md` · 追加 v3 role 门限 + 双 env pop 描述

若所有 FV 通过 · v3 完成 · 分支保留 uncommitted / 不 push / 不合 master · 与用户历史习惯一致(每次都保原样)。

---

## Self-Review 记录(writing-plans skill § Self-Review)

**1. Spec coverage**:spec 全部 12 节均有 task 覆盖:
- § 1 目的 → Task 1-5 整体
- § 2 架构 → Task 1(判据)+ Task 3(env 契约)+ Task 4(前端 role 供给)
- § 3 文件级改动 → 每 file 精准 map 到 Task(debug_ctx→T1 · throwback→T2 · api.py→T3 · api.ts/view.ts→T4)
- § 4 数据流 → Task 5 集成测试 monkeypatch counter 端到端验证
- § 5 边界 → Task 1 单元(v1 兼容/required kwarg)+ Task 3 handler(pop 兜底/空串)+ Task 5 集成(monkeypatch)
- § 6 测试策略 → Task 1/2/3/4/5 每 task 都带 TDD 循环 · 契约锚测试在 T2 · 前端测试在 T4 · 集成在 T5
- § 7 生产影响 → Task 1 test_debug_mode_unset_early_return 覆盖 · 手动 FV 不涉及生产
- § 8 兼容矩阵 → Task 1(v1 兼容 unit)+ Task 3(v1 API 不改)+ Task 5(v1 兼容集成 + J3 e2e)
- § 9 Rollout → 5 tasks 依 spec T1-T6 结构(T5 集成 + T6 文档合并进 Task 5)
- § 10 Authoring Guide → Task 2 契约锚测试作为模板 · Plan 无独立 task(未来 detector 加时按模板复用)
- § 11 风险与回滚 → Plan 无独立 task(git revert 是 tool 层 · 无需 plan step)
- § 12 术语与文件锚点 → Global Constraints 已引入

**2. Placeholder scan**:
- Task 4 Step 4.7 里"若原调用有传 eventClass / signal · 保留原值"是明确指令 · 非 placeholder
- Task 4 Step 4.10 里 refactor 步骤是 conditional guide · implementer 按需执行 · 非 placeholder
- Task 4 stores.role-mapping.spec.ts 里 fallback 分支的 `throw new Error(...implementer: locate view.ts:513 action name...)` 是防守性 assert · 指明具体 refactor 路径 · 非 placeholder

**3. Type consistency**:
- `debug_break(i: int, *, role: str)` 签名在 Task 1/2 一致
- `_read_role() -> Optional[str]` 在 Task 1 定义 · Task 3 test 无直接引用(通过 env spy 观测)· 一致
- `role?: string` 在 Task 4 api.ts 定义 · vitest 参数位置(args[8])与签名 9 位对齐
- HTTP query `role: Optional[str] = None` 在 Task 3 定义 · Task 5 集成用 `&role=X` URL 拼接 · 一致
- role 词汇 `{'gate', 'trough', 'end', 'entry'}` 在 spec / Global Constraints / Task 2 契约锚 / Task 4 vitest / Task 5 集成 / e2e J1/J2/J3 全部一致

**4. 无 gap 需补充 task**。
