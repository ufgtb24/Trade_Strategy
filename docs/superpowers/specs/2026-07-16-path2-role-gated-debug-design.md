# Path2 Role-Gated Debug Design (v3)

**Date**: 2026-07-16
**Branch**: gateA_notwork (worktree Trade_Strategy-gateA_notwork,base commit 4a5f687)
**Predecessors**: v1 (`2026-07-14-path2-web-debug-breakpoints`) · v2 (`2026-07-15-path2-web-event-debug-multi-anchor`)
**Status**: 设计已通过用户逐节确认,待写 plan 实施

---

## 1. 目的与上下文

### 1.1 问题声明

v1 spec 让「入口 A」(K 线主图 brush 框选一段区间)触发后端 `/diagnose?scope=time`,在 `_emit_tb_gate`(`path2/atoms/throwback.py:104`)前插 `debug_break(gate_idx)`,让开发者 pause 在 gate 失败样例处、看 `GateFailure` 各字段——目的是漏检诊断。

v2 spec 在此之上给 detected event(已 match 的 tb marker)加了 4 处 event-anchor 埋点:
- L163 `debug_break(trough_idx)` — phase1 success
- L216 `debug_break(i - 1)` — phase2 rise end
- L221 `debug_break(end_scan)` — phase2 timeout end
- L247 `debug_break(bo_idx)` — attempt entry

v1 与 v2 共用同一 env `DEBUG_BAR_RANGE=lo,hi`,`debug_break(x)` 只按 `x ∈ [lo, hi]` 判定 pause,**无角色区分**。

结果:入口 A 框选一段较宽区间(如 [200, 300])时,detector 里的 4 处 v2 event-anchor 埋点也全部激活。例如 L247 attempt entry 对**每一个 bo 的 `bo.end_idx`** fire一次——一个框选区间常见 3-5 个 bo,pause 就出现 3-5 次视觉噪音,才走到开发者关心的 L104 gate 失败点。

实测(2026-07-16):用户框选一段区间调试,pause 顺序:
1. `throwback.py:248`(L247 entry 埋点)× 3 次
2. `throwback.py:105`(L104 gate 埋点)· 用户实际目标

### 1.2 v3 目标

引入 **role 门限**,让 `debug_break` 按角色隔离触发:
- 入口 A 只 pause 在 gate 失败前(role='gate')· 消除 4 处 v2 埋点噪音
- 入口 D(marker 右键)按 anchor.key(entry/trough/end)精准 pause · 不受其他 role 影响
- 未来任意 detector 用同一机制自由声明 role 词汇

### 1.3 Non-Goals

- **不改变 pause 底层 API**:继续用 v2 的 `pydevd.settrace(suspend=True)` + `breakpoint()` ImportError fallback,role 门限与 pause 机制正交
- **不细分 gate role**(如 phase1_gate / phase2_gate):`gate_name` 字段已在 `GateFailure` 里承担 phase 细分,role='gate' 一码通吃
- **不做 role 类型枚举**:role 是自由 string,契约靠测试 assert 保
- **不改前端 UI**:brush 组件和 marker 菜单外观零变化,role 藏在 store 逻辑里
- **不做多进程并发保护**:v2 已声明 env `undefined under concurrency`,v3 继承,单用户 debug 场景不实际
- **不改生产路径**:DEBUG_MODE=0 下 `_DEBUG_MODE=False` 早退,pydevd 不 import,role check 零执行

---

## 2. 架构与分层

三层强度递增:

| 层 | v3 语义 | 强度 |
|---|---|---|
| **HTTP handler** (`path2_web/api.py::get_diagnose`) | 新增 optional `role: Optional[str] = None` query 参数。传了 → env 写 `DEBUG_ROLE`;未传 → env 不写 | 宽松兼容 |
| **Env 契约** (process 内) | 新增 `DEBUG_ROLE` env,与现有 `DEBUG_BAR_RANGE` 完全独立。handler `finally` 两个 env 各自 pop | 双 env 独立 |
| **`debug_break` API** (`path2/debug_ctx.py`) | 签名 `debug_break(i: int, *, role: str) -> None`,**required kwarg**。detector 里 5 处调用必须显式传 | 内部代码强规范 |

### 2.1 触发判据

```python
def debug_break(i: int, *, role: str) -> None:
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if not (r[0] <= i <= r[1]):
        return
    required = _read_role()      # env 读 DEBUG_ROLE · 未设返 None
    if required is not None and required != role:
        return
    # fire
    try:
        import pydevd
        pydevd.settrace(suspend=True)
    except ImportError:
        breakpoint()
```

**关键**:`required is None` → 不做 role 匹配(v1 兼容 fallback)· `required is not None` → 严格匹配。

### 2.2 前端两入口的 role 供给

- **入口 A**(brush 框选 · `path2_web_ui/src/stores/view.ts:513`):调 `getTimeDiagnose(...)` 时硬编码 `role='gate'`
- **入口 D**(marker 右键 · `path2_web_ui/src/stores/view.ts:553`):`triggerEventDebug(eventId, anchorKey)` 内部把 `anchorKey`(entry/trough/end)直接透传为 role

### 2.3 tb detector role 词汇 baseline

| debug_break 位置 | role |
|---|---|
| `throwback.py:104` `_emit_tb_gate` 内 | `'gate'` |
| `throwback.py:163` phase1 success | `'trough'` |
| `throwback.py:216` phase2 rise end | `'end'` |
| `throwback.py:221` phase2 timeout end | `'end'` |
| `throwback.py:247` attempt entry | `'entry'` |

**rise 与 timeout 共享 role='end'**:与 v2 已确立的「前端 UI 3 anchor · 后端 4 埋点合并 end」语义一致。一次 detect 只走 rise 或 timeout 分支之一 · 双 fire 不可能。

---

## 3. 文件级改动清单

### 3.1 后端 Python(4 处 · 0 新文件)

#### 3.1.1 `path2/debug_ctx.py`

```python
# 新增
def _read_role() -> Optional[str]:
    """读 DEBUG_ROLE env · 未设或空串返 None(v1 兼容 fallback:不做 role 匹配)。"""
    r = os.environ.get("DEBUG_ROLE")
    return r if r else None

# 改
def debug_break(i: int, *, role: str) -> None:
    """v3(2026-07-16)required kwarg role。判据加 role 门限:
    - env DEBUG_ROLE 未设 → 只按 range 匹配(v1 兼容)
    - env DEBUG_ROLE 设了 → range 匹配 && role 字面量匹配 · 才 fire
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

#### 3.1.2 `path2/atoms/throwback.py`(5 处埋点 role kwarg)

- L104: `debug_break(gate_idx)` → `debug_break(gate_idx, role='gate')`
- L163: `debug_break(trough_idx)` → `debug_break(trough_idx, role='trough')`
- L216: `debug_break(i - 1)` → `debug_break(i - 1, role='end')`
- L221: `debug_break(end_scan)` → `debug_break(end_scan, role='end')`
- L247: `debug_break(bo_idx)` → `debug_break(bo_idx, role='entry')`

**逐字精确**:role 字面量必须与 tb baseline table 一一对齐,不允许 typo。

#### 3.1.3 `path2_web/api.py`(handler role query + 双 env pop)

`get_diagnose` 函数签名追加参数:

```python
@router.get("/diagnose")
def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                 scope: Optional[str] = None,
                 # ... 现有参数不变 ...
                 start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                 role: Optional[str] = None):   # ★ v3 新增
    if start_bar is not None and end_bar is not None:
        os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
    if role:                                    # ★ v3 新增(空串也视同未传)
        os.environ["DEBUG_ROLE"] = role
    try:
        # ... 现有逻辑不变 ...
    finally:
        os.environ.pop("DEBUG_BAR_RANGE", None)
        os.environ.pop("DEBUG_ROLE", None)      # ★ v3 新增(无条件 pop 兜底)
```

**关键**:finally 无条件 pop `DEBUG_ROLE`,即使本次没写(前一次 request 可能写了未 pop 的残留)。

### 3.2 前端 TypeScript(2 处 · 0 新文件)

#### 3.2.1 `path2_web_ui/src/api.ts`

`getTimeDiagnose` 签名加 optional `role`:

```typescript
export function getTimeDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  startBar: number, endBar: number, eventClass?: string,
  signal?: AbortSignal,
  role?: string,           // ★ v3 新增
): Promise<TimeScopeResponse> {
  const url = `${BASE}/diagnose?pattern_id=${encodeURIComponent(patternId)}...`
    + `&start_bar=${startBar}&end_bar=${endBar}`
    + (eventClass ? `&event_class=${encodeURIComponent(eventClass)}` : '')
    + (role ? `&role=${encodeURIComponent(role)}` : '')   // ★ v3 新增
  return fetch(url, { signal }).then(...)
}
```

#### 3.2.2 `path2_web_ui/src/stores/view.ts`

**入口 A**(brush · L513 附近):

```typescript
// 原:
timeScopeResponse.value = await getTimeDiagnose(
  activePatternId.value, symbol.value, w.start, w.end, ...)
// 改(追加 role='gate' 到末位):
timeScopeResponse.value = await getTimeDiagnose(
  activePatternId.value, symbol.value, w.start, w.end,
  startBar, endBar, /*eventClass*/undefined, /*signal*/undefined,
  'gate')  // ★ v3 硬编码入口 A 语义
```

**入口 D**(marker 右键 · triggerEventDebug L553 附近):

```typescript
// 原:
await getTimeDiagnose(
  activePatternId.value, symbol.value, w.start, w.end,
  anchor.bar, anchor.bar, event.class_id, controller.signal,
)
// 改(追加 anchor.key 作为 role):
await getTimeDiagnose(
  activePatternId.value, symbol.value, w.start, w.end,
  anchor.bar, anchor.bar, event.class_id, controller.signal,
  anchor.key)  // ★ v3 · anchor.key 就是 role 字面量(entry/trough/end)
```

### 3.3 不改的部分

- `path2_web_ui/src/components/KlineChart.vue` — brush handler 只调 store action · role 藏在 store 里
- `path2_web_ui/src/components/DetailSidebar.vue` — debug 卡片三态 UI 与 role 正交
- `path2_web/main.py` / `path2_web/config.py` / pydevd fallback 逻辑 — 全部 0 改动

---

## 4. 数据流

### 4.1 主场景 · 入口 D(marker 右键)

用户右键 tb marker · 选 "Debug tb trough (bar 303)":

```
[UI]  view.ts triggerEventDebug(eventId='ev_xx', anchorKey='trough')
        │  anchor.bar = event.start_idx = 303
        │  anchor.key = 'trough'
        ▼
[UI]  api.ts fetch /diagnose?...&start_bar=303&end_bar=303
                              &event_class=tb&role=trough
        ▼
[BE]  handler get_diagnose:
        os.environ['DEBUG_BAR_RANGE'] = '303,303'
        os.environ['DEBUG_ROLE']      = 'trough'
        try: detect
        ▼
[BE]  detector 遇 5 处 debug_break:
        L104 role='gate'    → required='trough' 不匹配 → skip
        L163 role='trough'  → 303 in [303,303] && 'trough'=='trough' → FIRE
        L216 role='end'     → required='trough' 不匹配 → skip
        L221 role='end'     → required='trough' 不匹配 → skip
        L247 role='entry'   → required='trough' 不匹配 → skip
        ▼
[IDE] pydevd.settrace(suspend=True) → PyCharm pause
        (用户看 Frame 变量,Resume)
        ▼
[BE]  handler finally: pop 两 env → response 200
        ▼
[UI]  DetailSidebar "断点已释放"
```

### 4.2 主场景 · 入口 A(brush 框选 [200, 300])

```
[UI]  view.ts brush handler → getTimeDiagnose(..., 200, 300, role='gate')
        ▼
[BE]  handler: DEBUG_BAR_RANGE='200,300' + DEBUG_ROLE='gate'
        ▼
[BE]  detector:
        L247 entry role='entry'  → required='gate' 不匹配 → skip ★ v3 关键收益
        L163 role='trough'       → 不匹配 → skip
        L216/L221 role='end'     → 不匹配 → skip
        L104 gate_idx in [200,300] && role='gate' → FIRE
        (若 range 内有多个 bo 走到 gate 失败 · 依然会多次 fire · 用户 Resume 逐个看)
```

**v3 修复效果**:入口 A 不再被 v2 的 4 处 event-anchor 埋点污染 · 直接 pause 在 gate 失败点。

### 4.3 v1 兼容分支(curl 不带 role)

```
curl /diagnose?...&start_bar=200&end_bar=300     # 无 role query
[BE]  handler: DEBUG_BAR_RANGE='200,300' · DEBUG_ROLE 不写
[BE]  detector · debug_break 内 _read_role() 返 None
      role gate 判据 `required is None` · 放行 · 全部 fire = v1 行为等价
```

---

## 5. 边界与错误处理

| 情境 | 行为 | 保障 |
|---|---|---|
| **env DEBUG_ROLE 跨 request 污染** | handler finally 无条件 pop 两 env(即使本次没写 DEBUG_ROLE 也 pop) | 双 env 独立 pop · 无残留 |
| **role 拼写错**(前端传 `'enter'`) | 后端所有 debug_break role='entry' 都不匹配 · 全部 skip · **静默无 pause** | **测试 assert 是唯一防线**(§6) |
| **并发 request** | env 是 process-wide · 两 request 写 env 会 race · finally pop 可能清另一方的 env | **继承 v2 caveat**(api.py:245 comment)· 单用户 debug 场景不实际 |
| **PYTHONBREAKPOINT=0**(历史短路机制) | v1 曾用于禁用 breakpoint() · v3 因用 pydevd.settrace 不再受此影响 | **生产短路由 `_DEBUG_MODE=False` 保**(第一行 return · pydevd 不 import · 零成本) |
| **无 pydevd 环境**(非 PyCharm 启动) | 保留 v2 的 `try: pydevd.settrace() except ImportError: breakpoint()` fallback · fallback 到普通 breakpoint 也遵循 role 门限 | role 门限与 pause 机制正交 · fire 后的 API 无变 |
| **role 参数缺失**(源码里写 `debug_break(303)` 忘 role) | Python 抛 `TypeError: missing required keyword argument 'role'` | 编译期抓 · 契约锚测试 A#3 二次静态校验 |
| **契约 #4 加强**(v2 已有 · 现追加 role) | debug_break 参数 == event.<field> · v3 追加 role == anchor.key · 靠单元测试 assert | 端到端字符串一致 |

---

## 6. 测试策略

### 6.1 核心哲学

v3 唯一软肋 = **role 拼写错静默 skip**(前端 role='enter' · 后端埋点 role='entry' · 全部不匹配 · 无 pause 无报错)。测试首要职责 = 把这条软肋堵死。

### 6.2 Python 单元(pytest · 3 个文件)

| 文件 | 覆盖 | 关键 assert |
|---|---|---|
| `tests/path2/test_debug_ctx.py`(**新**) | debug_break role 门限的正负两向 + required kwarg | (1) env 无 DEBUG_ROLE · 任意 role fire = v1 兼容 · (2) env DEBUG_ROLE='gate' · role='gate' fire · role='entry' skip · (3) env DEBUG_ROLE='' (空串) · v1 兼容(_read_role 返 None) · (4) `debug_break(303)` 缺 role kwarg → TypeError |
| `tests/path2_web/test_diagnose_role_env.py`(**新**) | handler role env 写入 + finally 双 env pop | (1) GET `?role=gate` → 两 env 写入 · (2) GET 不传 role → 只写 DEBUG_BAR_RANGE · DEBUG_ROLE 不写 · (3) finally 无条件 pop 两 env(正常路径 + 异常路径) · (4) 跨 request 隔离:前次写 DEBUG_ROLE · 本次不传 · 本次 handler finally 依然 pop 兜底 |
| `tests/path2/atoms/test_throwback_debug_roles.py`(**新 · 契约锚**) | **静态 grep** throwback.py 里 5 处 debug_break 的 role 字面量 | (1) 恰 5 处 debug_break call(总数守恒) · (2) 每处必须传 role kwarg 且为 str 字面量(用 ast 解析 · 无 role 或非字面量即 fail) · (3) role 分布 Counter 严格等于 `{'gate':1, 'trough':1, 'end':2, 'entry':1}`(不依赖精确 lineno · 抗 throwback.py 上下加行漂移) |

契约锚测试的实现细节:

```python
import ast, pathlib
from collections import Counter
def test_throwback_debug_break_roles():
    src = pathlib.Path('path2/atoms/throwback.py').read_text()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, 'id', None) == 'debug_break']
    assert len(calls) == 5, f"expected 5 debug_break calls, got {len(calls)}"
    for c in calls:
        role_kw = next((k for k in c.keywords if k.arg == 'role'), None)
        assert role_kw is not None, f"L{c.lineno} debug_break missing role kwarg"
        assert isinstance(role_kw.value, ast.Constant) and isinstance(role_kw.value.value, str), \
            f"L{c.lineno} role must be str literal (for grep-ability)"
    role_counts = Counter(
        next(k.value.value for k in c.keywords if k.arg == 'role')
        for c in calls
    )
    # 抗 lineno 漂移 · 只 assert role 分布 · 不 assert 具体行号
    assert role_counts == Counter({'gate': 1, 'trough': 1, 'end': 2, 'entry': 1})
```

### 6.3 TypeScript 单元(vitest · 2 个文件)

| 文件 | 覆盖 | 关键 assert |
|---|---|---|
| `path2_web_ui/tests/api.getTimeDiagnose-role.spec.ts`(**新**) | getTimeDiagnose 的 URL 参数拼接 | (1) 传 role='gate' → URL 含 `&role=gate` · (2) 传 undefined → URL 不含 role query · (3) 特殊字符(如带 `&`)encodeURIComponent 正确 |
| `path2_web_ui/tests/stores.role-mapping.spec.ts`(**新**) | store 两入口的 role 供给 | (1) triggerEventDebug(id, 'entry') → getTimeDiagnose 调用参数最后一位是 'entry' · (2) triggerEventDebug(id, 'trough') → 'trough' · (3) triggerEventDebug(id, 'end') → 'end' · (4) brush handler(view.ts:513 附近的 timeScopeResponse 路径) → getTimeDiagnose 调用最后一位是 'gate' |

### 6.4 集成(pytest 一体化 · 1 个文件)

| 文件 | 覆盖 |
|---|---|
| `tests/path2_web/test_diagnose_role_integration.py`(**新**) | monkeypatch `pydevd.settrace` 为 mock counter · curl 4 role 各触发一次 · assert 只对应埋点 fire。具体 · monkeypatch: 每次 debug_break fire 时记录当次的 (bar, role);GET `?role=gate&range=0,300` · assert 只记录到 role='gate' 的 fire · GET `?role=entry` · 只记录到 'entry' · GET `?role=trough` · 只记录到 'trough' · GET `?role=end` · 只记录到 'end' · GET 不传 role · 4 种 role 都记录到(v1 兼容分支) |

### 6.5 手动 e2e(增补 checklist 场景 J)

在 `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md` 追加:

- **J1 入口 A 隔离**:框选一段区间 · 只 pause 在 L105(gate)· 不再 pause 在 L248/L164/L217/L222 其他 role 位置(entry noise 消失)
- **J2 入口 D role 精准**:右键选 trough anchor · 只 pause 在 L164(trough 埋点后)· 不 pause 在 L248/L217/L222
- **J3 v1 兼容**:手工 `curl /diagnose?...&start_bar=200&end_bar=300`(不带 role)· 依然 fire 所有 role(v1 行为等价 · v2 现有 e2e 场景 A/B/C 兜底覆盖)

### 6.6 双保险论证

- **前端拼写错**(如 view.ts 里 role='enter'):`stores.role-mapping.spec.ts` 直接 assert `role === anchor.key` · anchor.key 本身只有 4 个字面量 · IDE 自动补全兜住
- **后端拼写错**(如 throwback.py 里 role='trouhg'):`test_throwback_debug_roles.py` 静态 grep 精确检查每 line 的 role 字面量属于 `{gate, entry, trough, end}` · CI 立刻挂
- **前后端不对齐**(前端 'end' · 后端 'timeout'):集成测试 monkeypatch counter 直接看 fire 匹配

---

## 7. 生产影响

| 维度 | 保障 |
|---|---|
| **DEBUG_MODE=0**(默认生产) | `_DEBUG_MODE=False` · debug_break 第一行 return · pydevd 不 import · env 不读 · role check 不执行 · **零运行时开销** |
| **reload=True 生产模式**(port 8000) | 与 v3 完全无关 · handler 已回滚到 sync def(方向 A 已弃)· 无 loop 阻塞副作用 |
| **签名变化的运行时开销** | debug_break 加 kwarg 参数解析 · 微秒级 · 但因 `_DEBUG_MODE=False` 提前 return · 生产代码永远走不到 role check · **净零** |
| **API 用户** | v3 加 optional `role` query · 不传即 v1 行为 · **不破坏任何现有调用者** |

---

## 8. 向后兼容矩阵

| 场景 | v3 行为 | 是否要改 |
|---|---|---|
| **v1 现有前端 brush**(未加 role='gate') | env DEBUG_ROLE 不写 · debug_break _read_role() 返 None · 全 role fire = v1 行为 | ✓ 前端要改一次(v3 才消除 noise) |
| **v1 API 手工 curl**(不带 role query) | 同上 · v1 语义完全等价 | ✗ 无需改 |
| **v2 前端 marker 右键** | anchor.key 已是 entry/trough/end · v3 一行透传 · 精度提升无感升级 | ✓ 前端要改一次 |
| **v2 test_diagnose_finally_pop.py** | 老 test 只测 DEBUG_BAR_RANGE pop · v3 追加 DEBUG_ROLE pop 测(§6.2)· 老 test 保留 | ✗ 老 test 无需改(新 test 补充) |
| **v2 现有 5 处 debug_break** | v3 required kwarg · 5 处必须补 role kwarg · 否则 TypeError | ✓ 一次性改齐 |

**结论**:v3 是**纯前向增益的 refactor** · 不删任何行为 · 只加 role 门限精度。

---

## 9. Rollout(实施 plan task 分解建议)

| Task | 内容 | 依赖 |
|---|---|---|
| **T1** | `path2/debug_ctx.py`:`_read_role` + `debug_break` required kwarg + docstring · 单元测试 §6.2 第 1 行 | — |
| **T2** | `path2/atoms/throwback.py`:5 处埋点补 role kwarg(编译错消失)· 契约锚测试 §6.2 第 3 行 | T1 |
| **T3** | `path2_web/api.py`:handler role query + finally 双 env pop · handler 测试 §6.2 第 2 行 | T1 |
| **T4** | `path2_web_ui/src/api.ts` + `stores/view.ts`:两入口 role 透传 · 前端测试 §6.3 | T3 |
| **T5** | 集成测试 §6.4(monkeypatch pydevd counter) | T2,T3,T4 |
| **T6** | 手动 e2e 场景 J1/J2/J3(§6.5)+ 文档同步 `.claude/docs/modules/path2.md` / `path2_web.md`(通过 update-ai-context skill)+ `docs/tmp/*-e2e-checklist.md` 追加场景 J | T5 |

---

## 10. Authoring Guide(未来新 detector 接入 role 门限)

1. Detector 内所有埋点 **必须** `debug_break(x, role='<word>')` · role kwarg required
2. Detector 自选 role 词汇(baseline: `entry` / `trough` / `end` / `gate` · 若语义不 fit 可自命名如 `lookback_start` / `stop_signal` 等 · 但同一 detector 内不复用歧义)
3. **单元测试模板**(仿 `test_throwback_debug_roles.py`):
   ```python
   def test_<detector>_debug_role_contract():
       tree = ast.parse(pathlib.Path('path2/atoms/<detector>.py').read_text())
       calls = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, 'id', None) == 'debug_break']
       for c in calls:
           role_kw = next((k for k in c.keywords if k.arg == 'role'), None)
           assert role_kw is not None
           assert isinstance(role_kw.value, ast.Constant)
       roles = {next(k.value.value for k in c.keywords if k.arg == 'role')
                for c in calls}
       assert roles <= EXPECTED_ROLE_SET  # detector 声明的 role set
   ```
4. 前端 `anchorsOf` 声明新 class_id 的 anchor · anchor.key 字面量 **必须 = 后端 role 字面量**(靠 vitest assert 兜)
5. `view.ts` / `api.ts` / `api.py` handler / `debug_ctx.py` — **零改动**(通用逻辑 · 自动支持新 role)

---

## 11. 风险与回滚

- **单 commit refactor**:若 pytest gate 挂 · git revert 即回到 v2
- **无生产 rollback 风险**(生产路径不参与)
- **唯一 dev-time 风险**:role 拼写错静默 skip → 契约锚测试 A#3 + vitest 前端 assert = 双保险
- **v3 之后新加埋点忘 role**:required kwarg → Python 抛 TypeError · 编译期抓 · 单元测试也会 fail

---

## 12. 术语与文件锚点

- **入口 A**:K 线主图 brush 框选一段区间 → scope=time · 目的漏检 gate 定位。前端调用点 `path2_web_ui/src/stores/view.ts:513` 附近 · 后端 handler `path2_web/api.py:198` `get_diagnose`
- **入口 D**:tb marker 右键菜单 → 选 anchor(entry/trough/end)· 目的 detected event 精准 pause。前端调用点 `path2_web_ui/src/stores/view.ts:553` 附近(`triggerEventDebug`)· anchor 定义 `anchorsOf.tb`(view.ts:29-56)
- **anchor.key**:`'entry' | 'trough' | 'end'` · v2 前端 UI 层的 3 anchor 语义。v3 中 anchor.key 直接透传为 role 字面量
- **_DEBUG_MODE**:`path2/debug_ctx.py:9` 模块级常量 · `os.environ['DEBUG_MODE'] == '1'` · 生产短路的唯一开关
- **DEBUG_BAR_RANGE**:v1 引入 · 格式 `'lo,hi'` · handler 写 / debug_break 读
- **DEBUG_ROLE**:v3 新增 · 格式 role 字面量(如 `'gate'`) · handler 写 / debug_break 读 · 未设 = 不做 role 匹配 = v1 兼容
- **contract #4**:v2 定义 `debug_break 参数值 == event.<field>` · v3 加强追加 `role == anchor.key`
- **contract #7**:v2 定义 handler `finally` pop env · v3 扩展到双 env pop
- **契约锚测试**:静态 ast grep 检查源码里所有 debug_break call 的 role 字面量与预期表一致的 pytest 测试
