# pydevd_expert · pydevd 侧 pause 漂移调研

**角色**: pydevd_expert(4 人 team,lead 综合最终 final_report)
**状态**: **rev3**(2026-07-17 · 融合 cpython_expert rev1 三份实验证据 + 回复其两 peer review 问题 · **rev2 cache_skips 论证被实测证伪 · drift 归因转 PyCharm IDE Java 侧**)
**归档**: `docs/research/2026-07-17_pydevd-suspend-pause-position/pydevd_expert.md`

## 结论(TL;DR)· **rev3 重大修订**

**首选 M1 · gating 换新 · 待用户 PyCharm 现场实测**: 在 `debug_ctx.py::debug_break` 的 `pydevd.settrace(...)` 调用里增加 `stop_at_frame=sys._getframe(1)` 参数,即传入 debug_break 的**直接调用者 frame**(detector 内的 `_find_start_idx` / `_find_end_idx` / `evaluate_throwback` / `_emit_tb_gate`)。

- **rev3 机制解释重写**: cpython_expert 实验 2 PHASE 2 已实测坐实 —— **CPython trace 语义 + pydevd 1.4.0 core dispatch 层零 drift**(三个 anchor 都精确在 debug_break `return` event 落地 · 传给 `do_wait_suspend` 的 frame 就是 debug_break)。**drift 100% 发生在 PyCharm IDE(Java 侧)对 pydevd `thread_suspend` 消息的二次处理**(frame filter / auto-step / return-event UX 转 caller)。rev2 说 "cache_skips 短路是 M0 漂移的真机制" **被 cpython_expert 实验 2 PHASE 2 直接证伪**(那个 PHASE 就是模拟 connected=True + debug_break warm-up 让 cache_skips 填满的状态,pause 依然精确落 debug_break return)——**rev3 撤此论**。
- **M1 反抗机制的新解释(rev3)**: `stop_at_frame` 走 CMD_STEP_OVER 路径 → pydevd 等 caller frame 的下一 line event 才 do_wait_suspend → **传给 IDE 的 pause frame 是 caller frame(`_find_start_idx`)而不是 `debug_break`** → IDE 看不到 `debug_ctx.py` frame 就没有 skip / auto-step 触发条件 → pause 落 caller 停住不再漂。**这个反抗机制是纸面推理 · 唯一硬 gating = 用户 PyCharm 2026.1 现场用真 tb debug 一次实测 confirm**。
- **改动量**: `debug_ctx.py` 1 行(加 `stop_at_frame=`),`throwback.py` 零动(gate 埋点若走"办法 A"则 +1 kwarg)。
- **API 兼容(rev3 补 VSCode/Cursor 实证)**: `stop_at_frame` 是 `settrace` 的**已文档化公开参数**(非下划线开头),现场三处 diff 语义一致(见下表)—— PyCharm 2026.1 helpers `pydevd 1.4.0` + PyCharm 2024.3.5 helpers + VSCode debugpy 2026.6.0 + Cursor debugpy 2024.6.0 · 全走 `CMD_STEP_OVER + pydev_step_stop = stop_at_frame`。**API 稳定跨 fork · 但行为 unverified**(签名一致不等于 IDE 侧处理 pause 消息的方式一致)。
- **v3 契约**: `_DEBUG_MODE=False` 零成本短路不变;`_read_range`/`_read_anchor_kind` gate 顺序不变;不引入全局状态;可反复 fire(commit 8cd2e7c 硬要求)。
- **rev3 gating(唯一)**: 用户在 PyCharm 2026.1 现场用真 tb debug 一次实测(FV2 场景 J2)pause 落 `throwback.py:164`,才算 landing。**cpython_expert 已实测证伪 H1/H2/H3(rev2 收窄的 gating)· rev3 gating 收窄到一条 = IDE 侧行为实测**。

**次选 M2 · 兜底且推荐**:skeptic rev1 §"M2 推荐兜底"的移埋点方案 —— 把 `debug_break(trough_idx, ...)` 从 `_find_start_idx` L163 上移到 `evaluate_throwback` 内,`_find_start_idx` return 后立即 fire。丢内部局部变量视图(depth/peak/trough_idx),换 100% pydevd-agnostic。若 M1 用户实测 fail 则直切 M2。**cpython_expert 实验 2 隐含新支持**:既然 pause frame 由 caller frame 决定(实验里都是 debug_break),M2 移埋点让 debug_break 的 caller 变成 evaluate_throwback → IDE 收到的 frame = evaluate_throwback → 不落 helper 文件 → 大概率不 skip → 与 M1 等价能修 drift 但**无 pydevd internals 依赖**。

**cpython_expert 实验证伪的 rev2 rev1 论断**(rev3 认错清单):
1. rev1 "H1/H2/H3 不对 M1 生效性构成影响" —— skeptic rev1 已挑到过判(rev2 已认)· cpython_expert rev1 实验证伪 H1/H2/H3 三条全成立(CPython/pydevd core/bytecode 三层齐整无 drift)· rev2 把 gating 收窄到 H3 也过判 · rev3 撤 H3 gating
2. rev2 "M1 反抗 cache_skips 短路 · 新事实" —— cpython_expert 实验 2 PHASE 2 直接证伪(连接后 warm-up 让 cache_skips 填满后跑,pause 仍精确落 debug_break return)· rev3 撤此论断 · 承认"cache_skips 是 M0 漂移真机制"推理错误

**不推荐**(rev1/rev2 保留):
- α 加形式行(已 3 种证伪 · skeptic 现场事实)
- `set_next_statement` API 是"手动改 next 执行行"(goto 用法),与 settrace-suspend 语义不匹配
- 迁移 `sys.monitoring` PEP 669 —— **cpython_expert 明确排除**:pydevd 1.4.0 已有完整 PEP 669 实现(`_pydevd_bundle/pydevd_pep_669_tracing.py`)但 `do_wait_suspend` 传的 frame 与 sys.settrace 版一样是当前 frame · **换事件源不改 IDE 侧行为** · 无关 drift

---

## 现场事实

- **Python**: 3.12.12(uv env)
- **pydevd**: `pydevd 1.4.0`(PyCharm 2026.1 helpers · `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py`);非 uv env 依赖(`uv pip show pydevd` 返回 not found)
- **USE_LOW_IMPACT_MONITORING**(PEP 669 / sys.monitoring 路径):**默认关闭**,需 `os.environ['USE_LOW_IMPACT_MONITORING']=True` 才启用。所以当前跑的是**经典 sys.settrace 路径**(`pydevd_constants.py` L189-190)。
- **5 处埋点**(current line no.):
  - `throwback.py:104`(gate · 内嵌 `_emit_tb_gate` 里)
  - `throwback.py:163`(trough · 漂 · 已被 3 行形式 anchor 尝试失败)
  - `throwback.py:219`(end · rise 分支 · 不漂)
  - `throwback.py:224`(end · timeout 分支 · 未报告)
  - `throwback.py:250`(entry · 不漂)

## Root cause: `CMD_SET_BREAK` 语义 = "any-frame next line event"

`debug_break` 当前调用 `pydevd.settrace(suspend=True)`,无 `stop_at_frame`。**PyCharm 2026.1 helpers 里** `pydevd.py::_locked_settrace` L1965-1976 的关键分支:

```python
if suspend:
    if stop_at_frame is not None:
        # step-over 语义:锚定 caller frame,只在该 frame 的下一个 line/return event 停
        additional_info.pydev_state = STATE_RUN
        additional_info.pydev_step_cmd = CMD_STEP_OVER
        additional_info.pydev_step_stop = stop_at_frame
        additional_info.suspend_type = PYTHON_SUSPEND
    else:
        # "as soon as possible":thread-level STATE_SUSPEND flag
        py_db.set_suspend(t, CMD_SET_BREAK)
```

`CMD_SET_BREAK` 只 flip 一个 thread-level `pydev_state=STATE_SUSPEND` 标志(`pydevd.py::set_suspend` L993)。然后 `_pydevd_bundle/pydevd_frame.py::trace_dispatch` L754 的检查:

```python
if info.pydev_state == STATE_SUSPEND:
    self.do_wait_suspend(thread, frame, event, arg)
    return self.trace_dispatch
```

**触发时刻 = 装有 `f_trace` 的任意 frame 的下一次 line/return/call event**。所以漂移方向 = "首个真触发 trace_dispatch 的 frame"。

## L216/L247 不漂 · L163 漂 的**不对称假设**(纸面 · 待 cpython_expert 用实证坐实)

三处结构对比:

```python
# L163 trough(漂到 _find_end_idx 首行)
if depth >= pullback_min_atr * atr:              # L162
    debug_break(trough_idx, anchor_kind='trough')  # L163  ← settrace
    return trough_idx                            # L164(现在被 3 行占位挤到 L167)

# L219 end(不漂 · 停在 L220 return)
if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:  # L218
    debug_break(i - 1, anchor_kind='end')        # L219  ← settrace
    return i - 1                                 # L220

# L250 entry(不漂 · 停在 L251 if)
debug_break(bo_idx, anchor_kind='entry')          # L250  ← settrace
if bo_idx < 1 or bo_idx >= len(df):              # L251
    return None
```

**表面看** L163 与 L219 结构完全相同(`debug_break` 紧跟 `return X`),但一个漂一个不漂。这个不对称不能靠 pydevd 单侧解释——**必须交给 cpython_expert 复刻 `sys.settrace` 的 line event 序列**,看 L164 return 行的 line event 是否真的 fire。

**pydevd 侧能给的候选假设(仅供 cpython_expert 参考)**:
- H1: `set_trace_for_frame_and_parents` 在 `_locked_settrace` 里被调用(`pydevd.py` L1927/L1954),它 walk `.f_back` 链**只设 `f_trace = trace_dispatch`**(L1343-1344),不动 `f_trace_lines`。Python 3.12 里 `f_trace_lines` 默认 True,但如果之前有其他 tracing 场景把它 flip 过,可能导致 line event 静默丢失。
- H2: 首次进 detector 时(pydevd 还没连),`_find_start_idx` frame 是**无 trace 状态**创建的。settrace 里现挂 `f_trace`,但对**当前正在执行的 frame** 挂 f_trace 在 CPython 底层有 tricky 时序(`f_lasti` 已过某些 bytecode 分界时,line event 可能到下一个 basic block 才能 fire)—— 这个 H2 是核心猜测,cpython_expert 需要用 minimal repro 坐实/推翻。
- H3: L164 是 `return X` 单一语句,可能因 CPython 的 line table 优化被 co_lnotab 合并到 L163(或直接不 emit 独立 line event)。这个 H3 与 H2 都可通过 `sys.settrace` + 打印 (frame.f_code.co_name, line, event) 现场看清楚。

**⚠ rev2 修订 · skeptic 挑到的 gap** —— 我 rev1 说 "H1/H2/H3 不对 M1 方案生效性构成影响" 是**过判 · 现纠正**:
- **共享依赖**:M0 CMD_SET_BREAK 与 M1 CMD_STEP_OVER 都靠 `trace_dispatch` 触发,`trace_dispatch` 触发靠 `f_trace` 挂载 + Python C-level line event 真 fire。若 caller frame(`_find_start_idx`)的 L164 return 行的 line event **在 CPython 底层根本不 emit**(H3 = co_lnotab 优化合并情况),CMD_STEP_OVER 一样接不到、结果 = pause 完全消失(比当前"漂到下游"更痛)。
- **M1 依赖 H3 = False** (line event 真 fire),cpython_expert 的 sys.settrace 复刻实证是 M1 的 gating。
- 但 H2 (mid-execution 挂 f_trace 时序 bug / cache 状态) 情形下,M1 有**结构性反抗** —— 见下节 §"M1 反抗 cache_skips 短路 · 新事实"。

**H1/H2/H3 vs M1 生效** 三张表:
| 假设 | 若成立,M0 表现 | 若成立,M1 表现 |
|---|---|---|
| H1 f_trace_lines 被别处 flip | line event 全丢 · pause 完全消失 | 同 M0(pause 消失) |
| H2 mid-execution 挂 f_trace 时序 bug / cache_skips 状态 | line event 触发 trace_dispatch 但被 cache 短路 → 漂到未 cache 的下游 frame | **M1 反抗**(`is_stepping=True` 绕过 cache_skips 短路,见下节) |
| H3 co_lnotab 优化让 L164 return 无独立 line event | 无 line event · pause 漂到最近 fire event 的 frame | pause 完全消失(caller 无 line event 触发 CMD_STEP_OVER stop check) |

**结论**:M1 若通过 = H3 必须为 False(必须实证);若 H1 成立则 M0 M1 一起破;若 H2 成立则 M1 反抗更好;若 H3 成立则 M1 破退 M2。

## M1 反抗 `cache_skips` 短路 · **新事实(rev2 补入)**

skeptic rev1 挑我 §"M1 不依赖 H1/H2/H3" 后,重读 `_pydevd_bundle/pydevd_trace_dispatch_regular.py::ThreadTracer.trace_dispatch` L389-473 发现关键机制:

```python
py_db, t, additional_info, cache_skips, frame_skips_cache = self._args
pydev_step_cmd = additional_info.pydev_step_cmd
is_stepping = pydev_step_cmd != -1
...
frame_cache_key = (frame.f_code.co_firstlineno, frame.f_code.co_name, frame.f_code.co_filename)
if not is_stepping and frame_cache_key in cache_skips:      # ← L415-418 关键短路
    if event != 'call': frame.f_trace = NO_FTRACE
    return None
```

- **`cache_skips`** 是 per-thread 缓存的 "此 frame_cache_key 上次 trace 已判 skippable" 记忆,frame_cache_key = (co_firstlineno, co_name, co_filename) **per code object 共享**(所有 `_find_start_idx` 调用共用一个 key)。
- **M0 (CMD_SET_BREAK)**:`pydev_step_cmd == -1` → `is_stepping = False` → **`cache_skips` 短路生效**。若 `_find_start_idx` 曾在此线程被 trace 判 skippable(prior bo 迭代 detector 无 breakpoint),现在 L164 的 line event 命中短路,`NO_FTRACE + return None`,**永远不进 PyDBFrame.trace_dispatch,永远不查 STATE_SUSPEND**。这是 M0 下 "pause 漂到下游 frame" 的**真正机制候选**(H2 的具体形式)—— 因为下游 `_find_end_idx` 若在此 thread 首次 trace 时未被 cache(比如 detector loop 首次进 `_find_end_idx` 就恰好是 debug_break 之后那次),就成为第一个真正触达 PyDBFrame.trace_dispatch 的 frame,STATE_SUSPEND 被查到 → pause 落这里。
- **M1 (CMD_STEP_OVER)**:`pydev_step_cmd = 108` → `is_stepping = True` → **短路条件 `not is_stepping` fail → 短路不生效**。每个 frame event 都完整走进 PyDBFrame.trace_dispatch,受 CMD_STEP_OVER 分支(L839-844)按 `stop_frame is frame` 精确路由。

**这直接反抗 H2**:即使 caller frame 因 cache_skips 曾被短路(H2 具体形式),M1 的 `is_stepping=True` 绕过短路,让 caller frame line event 真正到达 PyDBFrame.trace_dispatch,再由 CMD_STEP_OVER 精确 stop。

**M1 仍不能反抗 H3**:若 L164 的 Python line event 从底层就不 emit(co_lnotab 优化),没有事件传给 trace_dispatch,再怎么绕短路也没用。**H3 = M1 唯一硬 gating**,cpython_expert 需要实证。

## M1 方案细节 · `stop_at_frame=sys._getframe(1)`

### 改动

`path2/debug_ctx.py::debug_break` 末尾:

```python
try:
    import pydevd
    import sys
    pydevd.settrace(suspend=True, stop_at_frame=sys._getframe(1))  # ← 唯一改动
except ImportError:
    breakpoint()
```

`sys._getframe(1)` = debug_break 的直接调用者 frame:
- trough(L163)调用 → `_find_start_idx` frame → pause 在 L164 `return trough_idx` ✓
- end(L219)调用 → `_find_end_idx` frame → pause 在 L220 `return i - 1` ✓
- end-timeout(L224)调用 → `_find_end_idx` frame → pause 在 L225 `return end_scan` ✓
- entry(L250)调用 → `evaluate_throwback` frame → pause 在 L251 `if bo_idx < 1...` ✓
- gate(L104,内嵌 `_emit_tb_gate`)调用 → `_emit_tb_gate` frame → pause 在 L105 `on_gate(GateFailure(...))`(**skeptic rev1 挑到 gap**:用户想看触发这个 gate 的 phase1/phase2 上下文变量,`_emit_tb_gate` frame 内只有 wrapper 参数,还需再点 stack 上一层看 detector 局部量。有两种收窄办法,见 §"gate 埋点例外处理")

### 机制

传入 `stop_at_frame` 后走的是 `_locked_settrace` L1967-1973 分支:

```python
additional_info.pydev_state = STATE_RUN
additional_info.pydev_step_cmd = CMD_STEP_OVER
additional_info.pydev_step_stop = stop_at_frame
additional_info.suspend_type = PYTHON_SUSPEND
```

然后 `pydevd_frame.py::trace_dispatch` L839-866 的 CMD_STEP_OVER 分支:

```python
elif step_cmd in (CMD_STEP_OVER, CMD_STEP_INTO_COROUTINE):
    stop = stop_frame is frame
    if stop:
        if is_line:
            # 语义:只在 stop_frame 自身的 line event 才停
            ...
        elif is_return:
            # 语义:return 事件时,若 caller 是 project scope 就跳到 caller
            stop = frame.f_back and main_debugger.in_project_scope(frame.f_back.f_code.co_filename)
```

**关键**:`can_skip` 在 CMD_STEP_OVER 且 `stop_frame is not frame` 时会 flip 为 True(L586-587),导致其他 frame 的 trace 被 NO_FTRACE 掉,**只保留目标 frame 触发 pause** —— 这就是"确定性锚定"的实现。

### API 兼容(现场验)

| 版本 | 路径 | `stop_at_frame` 参数存在 | 行为一致性 |
|---|---|---|---|
| PyCharm 2026.1 helpers pydev | `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py` L1810-1857 | ✓(v1.4.0) | ✓ 代码 diff 一致 · **待用户现场实测**(landing 硬前置) |
| PyCharm 2026.1 helpers debugpy vendored | `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/debugpy/_vendored/pydevd/pydevd.py` L2932-3058 | ✓ | ✓ 代码 diff 一致 |
| PyCharm 2024.3.5 helpers pydev | `/home/yu/apps/pycharm-community-2024.3.5/plugins/python-ce/helpers/pydev/pydevd.py` L1810-1857 | ✓ | ✓ 代码 diff 一致 |
| VSCode debugpy 2026.6.0 | `~/.vscode/extensions/ms-python.debugpy-2026.6.0-linux-x64/bundled/libs/debugpy/_vendored/pydevd/pydevd.py` | ✓ (签名存在) | **⚠ unverified** —— skeptic rev1 挑到:签名同源不等于行为一致(debugpy 是 microsoft/debugpy fork,DAP protocol 差异可能让 continue 消息 → pydev_step_stop 清理路径不同)· 用 VSCode 前必须 revalidate |
| Cursor debugpy 2024.6.0 | 同上路径 | ✓ (签名存在) | **⚠ unverified** —— 同 VSCode |

**参数签名**(所有版本共通):
```python
def settrace(
    host=None, stdout_to_server=False, stderr_to_server=False,
    port=5678, suspend=True, trace_only_current_thread=False,
    overwrite_prev_trace=False, patch_multiprocessing=False,
    stop_at_frame=None,
)
```

**Snyk 官方文档确认**(https://snyk.io/advisor/python/pydevd/functions/pydevd.settrace):
> The `stop_at_frame` parameter, if passed, will stop at the given frame, otherwise it'll stop in the function which called settrace.
>
> Example: `pydevd.settrace(stop_at_frame=sys._getframe().f_back)` pauses at the calling frame rather than in the current function.

### v3 契约兼容(逐条对 skeptic 基线)

| 契约红线 | M1 影响 |
|---|---|
| 可反复 fire(commit 8cd2e7c 硬要求) | ✓ 无变化。每次 `settrace(suspend=True, stop_at_frame=...)` 独立 fire。CMD_STEP_OVER 是 per-call state,不像 `breakpoint()` 那样"同 line 只报一次" |
| `DEBUG_MODE=0` / `range` / `anchor_kind` gate | ✓ 全在 settrace 之前,不受影响 |
| handler `finally` env pop | ✓ 无新全局状态。pydevd 内部 `additional_info` 是 pydevd 私有,不需要 handler 层清理 |
| `_DEBUG_MODE=False` 零成本 | ✓ 函数第一行 `if not _DEBUG_MODE: return` 不变。`sys` import 只发生在 pydevd 已 import 之后(可以 lazy import,或用 `sys._getframe` 无需 import——它是 builtin) |

**特别注意 `sys._getframe`**: 是 `builtins`(Python 内置),不需要 `import sys`(实际 `sys` 是 Python startup 就在的模块)。为了显式性建议保留 `import sys`,但这个 import 只在 `_DEBUG_MODE=True` 才执行(在 pydevd import 之前的 return 分支后),生产零成本。

### 风险与场景边界

1. **嵌套 debug_break**:一次 `evaluate_throwback` 调用可能连续 fire 多次 debug_break(先 entry L250,后遇 gate/trough/end)。每次 settrace 用新的 stop_at_frame,`pydev_step_stop` 被覆盖,不会互相干扰。前一次 fire 后用户按 continue 会回到 STATE_RUN,下一次 fire 独立生效。
2. **多线程 detector**:pydevd 的 additional_info 是 per-thread,`stop_at_frame` 只作用于当前线程。若 scan 是主线程单跑,零影响;若未来引入 worker thread,`patch_threads`(L1961)默认已开,每线程独立。
3. **coroutine/generator**:step-over 分支 L839 明确处理 `CMD_STEP_INTO_COROUTINE`,detector loop 是普通 for 循环非 async,不涉及。
4. **frame lifetime**:`stop_at_frame` 存进 `additional_info.pydev_step_stop`,pydevd 内部持有 frame 引用直到用户 continue 或 step 完成 。CPython frame 只要有引用就不 GC,无 use-after-free 风险。

### **不解决**的问题

- **问题 1(pause 两次)**:M1 只改 pause 位置,不改 fire 次数。handler 双跑 detector 的架构问题依然存在,与 M1 正交。

### gate 埋点例外处理(skeptic rev1 gap)

`_emit_tb_gate` L104 里的 `debug_break(gate_idx, anchor_kind='gate')`:

- `sys._getframe(1)` = `_emit_tb_gate` frame(wrapper 层)· pause 落在 L105 `on_gate(GateFailure(...))` · **不是** detector 内(`_find_start_idx`/`_find_end_idx`)· 用户看不到 `depth` / `peak` / `i` / `atr` 等 phase1/phase2 上下文变量。

**收窄办法**(rev2 补 · 二选一 · 用户偏好定):

- **办法 A · 埋点侧知情** —— 只在 `_emit_tb_gate` 内传显式 `stop_at_frame=sys._getframe(1)` 给 debug_break:
  ```python
  # path2/debug_ctx.py
  def debug_break(i, *, anchor_kind, stop_at_frame=None):
      ...
      import sys
      pydevd.settrace(suspend=True,
                      stop_at_frame=stop_at_frame or sys._getframe(1))
  # throwback.py::_emit_tb_gate L104
  debug_break(gate_idx, anchor_kind='gate', stop_at_frame=sys._getframe(1))
  ```
  `sys._getframe(1)` 在 `_emit_tb_gate` 内 = 其 caller = `_find_start_idx` 或 `_find_end_idx` frame · pause 落 detector 层 · 拿到 phase 上下文。**代价** = debug_ctx.py 签名加一个可选 kwarg,throwback.py 5 处埋点里 gate 那 1 处显式传参。
- **办法 B · debug_ctx 侧走 helper 检测** —— debug_ctx.py 内知道自己被 `_emit_tb_gate` 调时用 `sys._getframe(2)`。要判断"调用者是不是 `_emit_tb_gate`",最简单是按 co_name 匹配:
  ```python
  caller = sys._getframe(1)
  if caller.f_code.co_name == '_emit_tb_gate':
      caller = caller.f_back
  pydevd.settrace(suspend=True, stop_at_frame=caller)
  ```
  **代价** = debug_ctx.py 里 hard-code detector 层特定 wrapper 名 · 抽象泄漏。
- **办法 C · 接受** —— gate 埋点默认停在 `_emit_tb_gate` L105 · 用户点 stack 上一层看 detector 上下文(与当前 M0 漂到下游的痛度相当,只是位置从下游变旁支)。

**pydevd_expert 立场**:**推荐办法 A**(埋点侧显式知情 · 抽象干净 · debug_ctx.py 通用性不动)。skeptic 若挑到"办法 A 让 throwback.py 侵入面 +1 处",可考虑办法 C 兜底 · 但办法 B 抽象泄漏更差 · 不建议。

### Landing 硬前置(skeptic rev1 §"理论 vs 实测" gap)

**必须在用户 PyCharm 2026.1 现场用真 tb debug 一次实测 confirm M1 pause 位置**,才算 landing。判据:

1. 选 trough(FV2 场景 J2)· pause 落 `throwback.py:164` `return trough_idx`(不再是 `_find_end_idx:200`)
2. 变量面板显示 `trough_idx` / `depth` / `peak` 等 phase1 局部变量
3. 反复 fire 语义不变(commit 8cd2e7c 硬要求)· 同请求内多次触发 debug_break 都停
4. entry / end / end-timeout 不出现新 regression(即原本 "不漂" 保持 "不漂")
5. gate 埋点(若采办法 A)pause 落 detector 层

## M2 方案(兜底 · skeptic 兜底 A)

**做法**:把 trough 的 debug_break 从 `_find_start_idx` L163 上移到 `evaluate_throwback`:

```python
# evaluate_throwback 内(current L257 附近)
start = _find_start_idx(...)
if start is None:
    return None
debug_break(start, anchor_kind='trough')   # ← 移到这里
end = _find_end_idx(...)
```

**M1 优先于 M2 的理由**:
- M1 保留埋点靠近判据的原设计(pause 时看 depth/peak/trough_idx 中间值)
- M1 一次改动覆盖 5 埋点;M2 只治 trough,end/entry 的漂移隐患(若将来结构变化)不治
- M2 是可靠兜底,若 M1 实测某场景仍漂再退到 M2

## 待 cpython_expert 坐实的问题(rev2 收窄)

**rev2 M1 gating 只落在 H3**(H1 使 M0/M1 一起破 · H2 M1 已有结构性反抗)· cpython_expert 优先坐实:

1. **H3 唯一 blocker**:`sys.settrace` + 打印 (frame, line, event) 复刻 L163 场景 · 观察 `_find_start_idx` L164 `return trough_idx` 是否有独立 `line` event(先于 `return` event 触发)。
   - 若有 → H3 = False → M1 通过第一道 gating(还需用户现场实测通过第二道)
   - 若无 → H3 = True → M1 破 → 切 M2
2. **次要**:H2 具体形式(rev2 补的 cache_skips 短路)cpython_expert 若能用 sys.settrace 复刻线程内 detector loop 多次调用 → cache_skips 填充 → 观察 debug_break 后 caller frame line event 是否被 NO_FTRACE → 若坐实 H2 具体形式,rev2 的 M1 "反抗 cache_skips" 论证得独立验证
3. sys.monitoring PY_LINE/PY_RETURN 语义与 sys.settrace 有无本质差别(为长期迁移准备)

## rev4 · 承 lead 5 项任务(2026-07-17)

以下 5 节按 lead 指派顺序回答 · 承 cpython_expert rev1 实测结果 · 承 skeptic rev1 挑到的 gap。**rev4 结论优先于 rev1/rev2/rev3 冲突处**(明确认错清单在 §5.6 修订历史)。

### 5.1 Acknowledge cpython_expert 的 "drift = IDE Java 侧" 定性

cpython_expert rev1 三份实验(sys.settrace 复刻 + pydevd 1.4.0 真跑 + bytecode dis)三层证伪:
- CPython trace 语义无不对称(TROUGH/END/ENTRY 三 anchor 的 line event 都对齐 return 那一行 · 零 drift)
- pydevd 1.4.0 core dispatch 无不对称(**PHASE 2 已模拟 connected=True + debug_break warm-up · pause 依然精确落 debug_break return · 传给 do_wait_suspend 的 frame 就是 debug_break**)
- bytecode 层 PEP 657 fine-location 无不对称(3 层嵌套 if 与 1 层 if 的 RETURN_VALUE line 归属都正确)

**pydevd_expert 认可结论**:drift 100% 发生在 PyCharm IDE(Java 侧)对 pydevd `thread_suspend` 消息的二次处理层 · CPython/pydevd core 层给不出 asymmetry 的机制。**这个定性接受 · rev1/rev2 里"H1/H2/H3 gating"" cache_skips 短路"两条论断全部作废**(见 §5.6 认错清单)。

pydevd_expert 追加**独立源码坐实**cpython_expert 的机制解释——`_pydevd_bundle/pydevd_frame.py::PyDBFrame.trace_dispatch` L889-923 显式有"return event 转 caller frame"的 IDE UX 处理:

```python
elif stop:
    if is_line:
        self.set_suspend(thread, step_cmd)
        self.do_wait_suspend(thread, frame, event, arg)
    else:  # return event
        back = frame.f_back
        if back is not None:
            ...
            # if we're in a return, we want it to appear to the user in the previous frame!
            self.set_suspend(thread, step_cmd)
            self.do_wait_suspend(thread, back, event, arg)   # ← frame swapped to caller
```

这条路径**只在 stepping 阶段(step_cmd != -1 且 stop 由 CMD_STEP_* 分支触发)命中** · **M0 初始 pause 由 L754 `if info.pydev_state == STATE_SUSPEND` 抢先处理**(early return · 传 frame = debug_break)· 不走 L893-923 · 所以 cpython_expert 实验里 M0 pause frame = debug_break 是对的。**但 L893-923 明确证据表明 pydevd core 团队知道"return event pause 应显示 caller frame" 的 UX 需求 · 只是 M0 走了另一条路 · 这就是 IDE Java 侧不得不再做一次 UX 转换的动因起源**(pydevd 只在 stepping 时帮转 · settrace-suspend 不帮转 · IDE 补上)。

### 5.2 回应 skeptic 挑 "M1 反抗机制是纸面推理"

skeptic rev1 §"理论 vs 实测" blocker:M1 未在 PyCharm 现场实测 · 只有源码推理。

**rev4 增强 M1 反抗机制的源码推理路径**(仍需用户现场实测 landing · 但源码支持更强):

**M0 fire 时 pydevd 内部路径**(cpython_expert PHASE 2 实测已坐实此点):

1. `debug_break L163` → `pydevd.settrace(suspend=True)` → `_locked_settrace` → `py_db.set_suspend(t, CMD_SET_BREAK)` → **`_mark_suspend`(pydevd.py:979-991)**
2. `_mark_suspend` L983-986(cpython_expert 现场 grep):
   ```python
   if info.pydev_step_cmd == -1:
       info.pydev_step_cmd = CMD_STEP_INTO   # ← M0 也是 stepping!
   info.pydev_state = STATE_SUSPEND
   ```
3. debug_break return event 触发 trace_dispatch → PyDBFrame.trace_dispatch → **L754 `if info.pydev_state == STATE_SUSPEND: do_wait_suspend(thread, **frame=debug_break**, event, arg); return`** early-return
4. **传给 IDE 的 top frame = debug_break**(`path2/debug_ctx.py:57`)· 这是 helper 文件

**M1 fire 时 pydevd 内部路径**(rev4 独立源码走查 · 无实测):

1. `debug_break L163` → `pydevd.settrace(suspend=True, stop_at_frame=sys._getframe(1))` → `_locked_settrace` L1966-1973:
   ```python
   if suspend:
       if stop_at_frame is not None:
           additional_info.pydev_state = STATE_RUN         # ← NOT SUSPEND
           additional_info.pydev_step_cmd = CMD_STEP_OVER
           additional_info.pydev_step_stop = stop_at_frame # = caller_frame = _find_start_idx
   ```
2. debug_break return event 触发 trace_dispatch → PyDBFrame.trace_dispatch → **L754 SUSPEND 检查 skip**(state = RUN 不是 SUSPEND)
3. 走到 L839-866 CMD_STEP_OVER 分支:`stop = stop_frame is frame` · debug_break 的 frame ≠ stop_frame(=caller)· stop = False · 继续执行
4. 控制流回到 `_find_start_idx` L164 `return trough_idx` · line event 触发
5. PyDBFrame.trace_dispatch · L754 skip · L839 `stop = stop_frame is frame = True`(current frame = `_find_start_idx` = stop_frame)
6. L890 `if is_line: self.set_suspend(thread, step_cmd); do_wait_suspend(thread, **frame=_find_start_idx**, event, arg)`
7. **传给 IDE 的 top frame = `_find_start_idx`**(`path2/atoms/throwback.py:164`)· project scope 用户代码

**M1 反抗机制的核心 = pydevd 层就把 top frame 从 helper (debug_break)换成 user code (`_find_start_idx`)** · IDE 收到的消息里 top frame 已经是 project-scope 用户文件 · **IDE 侧任何基于 filename 的 skip / auto-step 规则都无从下手**(它连 helper frame 都看不到)。

**skeptic "纸面推理" 挑法回应**:承认没有 PyCharm 现场实测 · 但这个推理链条**完全建立在现场 pydevd 1.4.0 源码上**(每步都能 grep 到具体行号)· 而不是 cache_skips 那种基于错误前提的推理。cpython_expert 实验 2 隐含**间接支持**:PHASE 1/2 pause frame 记录都是 debug_break · 说明 M0 传 debug_break、M1 若传 caller frame · IDE 看到的 helper vs user-code 差别是客观存在的。

**结论**:M1 反抗仍需 landing 硬前置实测(§5.5)· 但源码层反抗机制解释是**完整可验证**的 · 非纸面猜测。

### 5.3 补 IDE 侧行为的间接证据

pydevd_expert 独立查 PyCharm helpers 侧文件 · 找到以下间接证据支持 "drift = IDE Java 侧 skip filter / auto-step":

**证据 1 · pydevd_pycharm.py 12 行 re-export**(非引入 PyCharm-specific 语义)

```python
# /home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd_pycharm.py 全文
from pydevd import settrace, stoptrace
from _pydevd_bundle.pydevd_comm import VERSION_STRING
__version__ = VERSION_STRING
__all__ = ['settrace', 'stoptrace']
```

**结论**:PyCharm-side 没有专门的"return-event auto-step 转 caller"wrapper · 若有 auto-step 行为 · 只可能来自 IDE Java 端消息处理层。

**证据 2 · PYDEVD_FILTERS env var 机制**(pydevd_utils.py L482-500)

```python
def is_filter_enabled():
    return os.getenv('PYDEVD_FILTERS') is not None

def is_filter_libraries():
    return os.getenv('PYDEVD_FILTER_LIBRARIES') is not None
```

PyCharm Settings 里的 "Skip files"(通配符列表)会通过 `PYDEVD_FILTERS` env var push 给 pydevd。**关键**:filter check 只在 `is_stepping=True` 时触发(pydevd_trace_dispatch_regular.py L442-450):

```python
if is_stepping:
    if py_db.is_filter_enabled and py_db.is_ignored_by_filters(filename):
        if event != 'call': frame.f_trace = NO_FTRACE
        return None
```

**M0 因 `_mark_suspend` flip 到 CMD_STEP_INTO · is_stepping=True · 若用户 PyCharm 设置有 skip files 且匹配 debug_ctx.py · 会被 skip · pydevd 层 pause 消息可能被 IDE 侧忽略然后 auto-step**。这提供 IDE 侧 skip 的**触发条件**(但不是完整机制 · 完整机制看不到)。

**证据 3 · pydevd_frame.py L893-923 的 return→caller frame 转换代码**(§5.1 已引)

pydevd core 团队在**stepping 场景**里明确实现了"return event pause 应显示 caller frame" 的 UX 需求(注释 `# if we're in a return, we want it to appear to the user in the previous frame!` L921)。**M0 走的 L754 SUSPEND early-return 路径没有做这一转换**——IDE Java 端**若要给用户一致的 UX**,大概率自己实现了类似逻辑 · 表现出的就是"从 debug_break return event 自动转到 caller · 若 caller 也是即将 return 或调下一函数 · 继续跳"的连锁反应。**间接证据不能坐实 IDE 内部实现 · 但给出机制候选路径**。

**证据 4 · `stop_reason=CMD_SET_BREAK` 与 `CMD_THREAD_SUSPEND` 的分类**(pydevd_frame.py L744, pydevd.py:1010)

`set_suspend(t, CMD_SET_BREAK)` 传给 IDE 的 `stop_reason` 字段是 `CMD_SET_BREAK`(=111) · IDE 收到不同的 stop_reason 可能路由到不同的 UX handler。M1 的 CMD_STEP_OVER 走的是不同的 stop_reason 路径(触发 pause 时 L891 `self.set_suspend(thread, step_cmd)` 传的是 CMD_STEP_OVER)——**IDE 侧针对 STEP_OVER pause 大概率无 auto-forward 逻辑**(step-over 是用户主动动作 · 不该被再次 auto-step)。

**综合**:证据 1/2/3/4 独立指向 "M1 pause 消息进 IDE 后走的是 step-over UX 路径 · 而非 CMD_SET_BREAK UX 路径 · 后者才是可能触发 auto-step 的路径"。这**支持 M1 反抗机制**但**不能替代用户现场实测**(§5.5)。

### 5.4 独立复核 gate 埋点(承 skeptic rev1 § 场景边界 gap)

rev3 已列办法 A/B/C · 此处 rev4 追加独立复核:

**5 处 debug_break 埋点的 caller 关系**(现场 grep throwback.py 核实):

| 埋点行 | 埋点 anchor_kind | 直接 caller frame(sys._getframe(1)) | 用户"预期" pause 位置 | M1 默认 `sys._getframe(1)` 达标? |
|---|---|---|---|---|
| L104 | gate | `_emit_tb_gate` 内 L105 `on_gate(...)` | detector 内(_find_start_idx / _find_end_idx)看 gate 触发上下文 | ❌ 差一层 |
| L163 | trough | `_find_start_idx` 内 L164 `return trough_idx` | `_find_start_idx` 内看 depth/peak/trough_idx | ✓ 达标 |
| L219 | end(rise) | `_find_end_idx` 内 L220 `return i - 1` | `_find_end_idx` 内看 i/base_min/atr | ✓ 达标 |
| L224 | end(timeout) | `_find_end_idx` 内 L225 `return end_scan` | `_find_end_idx` 内看 end_scan/base_min | ✓ 达标 |
| L250 | entry | `evaluate_throwback` 内 L251 `if bo_idx < 1...` | `evaluate_throwback` 内看 bo_idx/anchor | ✓ 达标 |

**gate(L104)的独有问题**:被 wrapper `_emit_tb_gate` 隔了一层 · `sys._getframe(1)` 只到 wrapper · 需 `sys._getframe(2)` 才到 detector · 但其他 4 处 `sys._getframe(1)` 就够。

**rev4 推荐办法 A(明确)**:让 gate 埋点侧显式传 `stop_at_frame=sys._getframe(1)`(在 `_emit_tb_gate` 内),`sys._getframe(1)` 在 wrapper 内就是 detector caller。改动:

```python
# path2/debug_ctx.py
def debug_break(i, *, anchor_kind, stop_at_frame=None):
    if not _DEBUG_MODE:
        return
    ...
    try:
        import pydevd, sys
        pydevd.settrace(suspend=True,
                        stop_at_frame=stop_at_frame or sys._getframe(1))
    except ImportError:
        breakpoint()

# path2/atoms/throwback.py::_emit_tb_gate L104
import sys
debug_break(gate_idx, anchor_kind='gate', stop_at_frame=sys._getframe(1))
```

**代价**:debug_ctx.py 加 1 个 optional kwarg · throwback.py 5 处埋点里 gate 那 1 处加 3 字符 `sys` import + `stop_at_frame=sys._getframe(1)`。其他 4 处不动 · 走默认 `sys._getframe(1)`。

**新 v3 契约检验**(rev4 追加):
- `_DEBUG_MODE=False` 时 `stop_at_frame` kwarg 直接被 return 短路 · 不消费 · 零成本 ✓
- kwarg 不引入全局状态 ✓
- `debug_break` 签名 backward-compat(可选参数 · 老 callers 不传就走 default)· 5 处埋点里 4 处零改动 ✓

**办法 B(hard-code wrapper 名)与办法 C(接受)** rev3 已列 · 均次选 · 不再展开。

### 5.5 增补 Landing 硬前置

**rev4 landing checklist**(collapse rev3 五条 + skeptic rev1 blocker 补丁 · 全条件都要过 M1 才算 landing):

1. [必过] **cpython_expert rev2**(warm-up 场景 + 加 print/`_=` 形式 anchor 场景)不出现翻转结果 · 若 rev2 实验反映 "有些场景 pause frame 不是 debug_break" 需重审 M1 机制推理
2. [必过] **用户 PyCharm 2026.1 现场用真 tb debug 一次实测**(FV2 场景 J2 · 选 trough anchor 触发)· pause 落在 `throwback.py:164` 而非 `_find_end_idx:200`
3. [必过] **变量面板检验**:pause 时能看到 `trough_idx` / `depth` / `peak` 等 phase1 局部变量(证明 top frame 真是 `_find_start_idx` 而非 debug_break)
4. [必过] **反复 fire 语义不变**(commit 8cd2e7c 硬要求)· 同一请求内多次触发 debug_break 都能停(把 L163 的 range 设成命中多次 · 观察 pause 次数)
5. [必过] **entry / end / end-timeout / gate 无 regression**:原本 "不漂" 的场景保持 "不漂" · gate 埋点(采办法 A)pause 落 detector 层
6. [软过] **VSCode / Cursor 若切换 IDE 前 revalidate**:非当前 blocker(现场 PyCharm)· 但如未来切 debug IDE 前需过 landing 1-5 全套

**Landing 若某条 fail 的降级路径**:
- 1 fail(cpython_expert rev2 翻转) → 重新审 M1 机制 · 视翻转细节可能仍用 M1 或直切 M2
- 2 fail(pause 仍漂到 `_find_end_idx:200`) → M1 破 → 直切 M2(移埋点)· 用户 workflow 无阻塞
- 3 fail(pause 位置对但看不到变量) → 局部 bug · 可能 stop_at_frame 传错(应传 `sys._getframe(1)` 不是 `f_back` · 后者会引发 GC 问题)· 排查后重试
- 4 fail(反复 fire 少了)→ M1 破退 M0(现状)+ 直切 M2 · CMD_STEP_OVER 可能与"再次触发"语义不 compose
- 5 fail(entry/end 出现新 regression)→ M1 破退 M0 + 直切 M2 · stop_at_frame 副作用与 anchor 类型耦合

### 5.6 rev4 认错清单(rev1/rev2 rev3 之前的过判)

- rev1 §"H1/H2/H3 不对 M1 生效性构成影响" —— **已 rev2 认错**(skeptic rev1 挑到)
- rev2 §"M1 反抗 cache_skips 短路 · 新事实" —— **rev4 认错**。cpython_expert 独立读 `pydevd.py::_mark_suspend` L983-986 发现 M0 走 `_mark_suspend` 会把 `pydev_step_cmd` 从 -1 flip 到 `CMD_STEP_INTO` · **M0 也是 is_stepping=True · 与 M1 CMD_STEP_OVER 同样绕过 L415 cache_skips 短路**。rev2 的 "M0 cache_skips 短路生效"前提错误。cpython_expert rev1 实验 2 PHASE 2(warm-up 让 cache 填满后跑)pause 依然精确落 debug_break return · 直接坐实 cache_skips 短路不是 drift 机制。
- rev2 §"drift 是 pydevd 层"隐含前提 —— **rev4 认错**。cpython_expert 三份实验证伪 CPython + pydevd core + bytecode 三层 · drift 100% 在 IDE Java 侧。
- rev3 §"H3 唯一硬 gating" —— **rev4 撤销**。cpython_expert rev1 实验 1 raw sys.settrace 复刻已直接坐实 `_find_start_idx L164 return trough_idx` 有独立 `line` event(先于 return event) · H3(co_lnotab 优化让 L164 无 line event)不成立。M1 gating 只剩 §5.5 §user PyCharm 现场实测。

## 修订历史

- **rev1**(2026-07-17):首选 M1(`stop_at_frame` kwarg),现场版本 pydevd 1.4.0 API 现场 grep 验证,v3 契约逐条对齐,H1/H2/H3 假设待 cpython_expert 坐实。**已知问题**:§"H1/H2/H3 不对 M1 生效性构成影响" 是过判(skeptic rev1 挑到)。
- **rev2**(2026-07-17):融合 skeptic rev1 五处挑战 → 补 H1/H2/H3 vs M1 三张表、"M1 反抗 cache_skips 短路 · 新事实"、VSCode/Cursor unverified 标签、gate 埋点例外三办法、landing 硬前置。**已知问题(rev4 撤销)**:"cache_skips 短路是 M0 漂移真机制"论证前提被 cpython_expert 独立读 `_mark_suspend` L983-986 证伪 · 实测 PHASE 2 warm-up 场景直接反证。
- **rev3**(2026-07-17):融合 cpython_expert rev1 三份实验 + 回复其两 peer review 问题 · **rev2 cache_skips 论证被实测证伪 · drift 归因转 PyCharm IDE Java 侧** · gating 收窄到"H3 + 用户现场实测"。**已知问题(rev4 撤销)**:H3 gating 也过判(cpython_expert rev1 实验 1 已直接坐实 H3 不成立 · rev3 未充分吸收)。
- **rev5**(2026-07-17 · 集中补 skeptic_v2 rev3 判定 5c/6a/6b/η + acknowledge cpython_v2 rev2 实验 5 · 见下方 §"rev5 · 承 lead 任务 #17" 章节)
- **rev4**(2026-07-17 · lead 5 项任务):
  1. Acknowledge cpython "drift = IDE Java 侧" 定性 + 独立源码坐实(L893-923 return→caller frame 转换代码是间接证据)
  2. 回应 skeptic "M1 反抗机制纸面推理" gap · 用完整 pydevd 源码走查(M0 走 L754 SUSPEND early-return 传 frame=debug_break · M1 走 L839-890 CMD_STEP_OVER 传 frame=caller)· 反抗机制核心 = pydevd 层就把 top frame 换掉 · IDE 无从 skip
  3. 补 IDE 侧行为四条间接证据(pydevd_pycharm.py 12 行 re-export · PYDEVD_FILTERS 只在 stepping 生效 · pydevd_frame.py L893-923 return→caller 转换代码 · stop_reason 路由差异 CMD_SET_BREAK vs CMD_STEP_OVER)
  4. 独立复核 5 处埋点 caller 关系表 · 明确推荐办法 A(gate 埋点侧显式传 `stop_at_frame`)· debug_ctx.py 加 optional kwarg · backward-compat
  5. Landing 硬前置 6 条 checklist(cpython_expert rev2 + 用户 PyCharm 现场实测 pause 位置 + 变量面板 + 反复 fire + 无 regression + VSCode 软过)· 每条 fail 的降级路径
  6. 认错清单:rev2 cache_skips、rev2 "drift 在 pydevd 层"、rev3 H3 gating 三条 rev4 撤销

## rev5 · 承 skeptic_v2 rev3 判定 4 项 minor blocker(2026-07-17)

**触发**:skeptic_v2 rev3 判定"主 blocker clear · 剩余 minor 或送 lead"· 建议我出 rev5 集中 5c/6a/6b + η 评估。同期 cpython_v2 rev2 出实验 5 独立复核 M1 机制,rev5 附带 acknowledge。其他文档级 minor(H2 表格残留、7a "100% IDE" 表述、7b failure mode 表、7c κ 方案、7d 描述不一致)交 lead 综合 final_report rev2 时收尾。

### 6.1 挑战 6a 回应 · CMD_THREAD_RUN 显式 reset pydev_step_stop(clear)

**skeptic 挑**:M1 下 pydev_step_stop = caller_frame · 用户按 Continue 后 pydevd 是否真 clear pydev_step_stop?若不 clear · 下次 debug_break 触发前 pydev_step_stop 残留上次 frame(已 GC · dangling)· 可能引起 pydevd 内部错乱。

**rev5 现场 grep 坐实**:`/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/_pydevd_bundle/pydevd_process_net_command.py::process_net_command` L196-214 · **CMD_THREAD_RUN**(IDE 侧 Continue 按钮发的 net command)分支:

```python
elif cmd_id == CMD_THREAD_RUN:
    py_db.maybe_kill_active_value_resolve_threads()
    ...
    for t in threads:
        if t is None:
            continue
        additional_info = set_additional_thread_info(t)
        additional_info.pydev_step_cmd = -1
        additional_info.pydev_step_stop = None      # ← 显式 reset dangling ref
        additional_info.pydev_state = STATE_RUN
```

**结论**:用户 Continue 后 pydevd 主动 reset:
- `pydev_step_cmd = -1`(不再 stepping)
- `pydev_step_stop = None`(dangling frame ref 显式清空)
- `pydev_state = STATE_RUN`(线程恢复运行)

**dangling frame ref 风险 clear** · 挑战 6a 完全反驳。M1 每次 fire → Continue → 下次 fire · 状态从零开始 · 不残留污染。

### 6.2 挑战 6b 回应 · PYDEVD_DEBUG env 观察工具

**skeptic 挑**:若 M1 fail-severe(pause 消失)· 用户如何区分 "pause 未触发" vs "debug 挂了 / debug_break 短路"?

**rev5 补 landing 观察工具**:

- **env `PYDEVD_DEBUG=1`** — pydevd 内部 log 开关(现场 grep `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/_pydev_bundle/pydev_log.py` 可确认)· 启用后 `pydev_log.debug(...)` 全 route 到 stderr。观察:
  - `pydev_log.debug("do_wait_suspend ...")` 是否被打印 → 若打印 = pause 消息进了 do_wait_suspend(pydevd 侧完成 · 漂在 IDE 侧)
  - `pydev_log.debug("STEP_OVER ...")` / `_locked_settrace` 相关 log → 确认 M1 走 CMD_STEP_OVER 分支
- **env `PYDEVD_DEBUG_FILE=/tmp/pydevd.log`** — log 落文件(避免 stderr 与业务 log 混淆)
- **辅助手段 · main.py 打印 `os.environ` **:确认 `DEBUG_MODE` / `DEBUG_BAR_RANGE` / `DEBUG_ANCHOR_KIND` / `DEBUG_EVENT_CLASS` 4 个 env 都 set 且 debug_break 4 层短路全过(排除"debug_break 短路 vs pause 未触发"歧义)

**landing 追加判据**:

- **判据 9 · pause 未触发时**必须先用 `PYDEVD_DEBUG=1` 跑一次 · 观察 do_wait_suspend 是否被调用 · 从而区分:
  - `do_wait_suspend` 被调用 · IDE 未显示 pause → **drift 到 IDE 侧 · M1 fail-severe · 直切 M2**
  - `do_wait_suspend` 未被调用 · debug_break 短路了 → **检查 env 4 层 gate · 与 M1 无关**
  - 4 层 gate 全过但 `do_wait_suspend` 未调用 → **pydevd 层 bug**(理论罕见)· 报 issue 到 pydevd 上游

### 6.3 挑战 5c 回应 · IDE 状态栏视觉判据

**skeptic 挑**:CMD_STEP_OVER 触发的 pause · PyCharm 状态栏可能显示 "stepped over" 而非 "paused at breakpoint" · 用户预期是断点停 · 看到 step 状态可能困惑。

**rev5 承认**:pydevd 传给 IDE 的 stop_reason 是 CMD_STEP_OVER(108)· 与 M0 CMD_SET_BREAK(111)不同 · PyCharm 状态栏文字**大概率不同**(具体文字依 PyCharm 2026.1 UI 版本):
- M0 状态栏预期文字:"Paused at breakpoint" 或 "Debugger Paused"
- M1 状态栏预期文字:"Stepped over" 或 "Stopped after step over" 或 "Debugger Paused"(依 IDE 版本)

**rev5 立场**:此 gap 属**cosmetic UX** · 不影响 pause 正确性 · 不影响变量面板功能 · **不作 M1 hard-blocker**。但加入 landing checklist 作分层判据:

- **判据 10(soft)**:M1 pause 触发后 · 用户观察 PyCharm 状态栏文字:
  - 若显示 "Stepped over" 或类似 stepping 状态 → **M1 fail-cosmetic**(pause 位置对 · 状态文字令人困惑)· 用户自行决定是否可接受 · 可接受 → 采纳 M1 · 不可接受 → 退 M2(M2 走原 breakpoint 语义 · 状态栏显示"Paused at breakpoint")
  - 若显示 "Paused at breakpoint" 或类似 breakpoint 状态 → **完美 M1 pass**

**M2 side benefit 追加一条**:M2 移埋点后 debug_break 在 caller 直接 fire · pydevd 侧走 CMD_SET_BREAK · IDE 状态栏显示"paused at breakpoint" · **UX 语义 100% 与用户预期一致**。若 5c fail-cosmetic 用户不接受 · M2 完美救场。

### 6.4 新方案 η 评估 · IDE Skip Files 配置零改动首查

**skeptic 提议**:PyCharm Preferences → Build/Execution/Deployment → Debugger → Stepping → **Do not step into files** · 检查 `debug_ctx.py` 是否在自动 skip 列表 · 手动 remove 即可。零代码改动 · 用户 3 分钟工作量。

**rev5 独立评估**:η 是 M1 之前的**零成本前置探索** · 强烈推荐作为**方案矩阵 pre-check**。

**η 的可行性论证**:
- pydevd_utils.is_ignored_by_filter(filename)(§5.3 证据 2 已引)· 靠 IDE 侧 push 的 `PYDEVD_FILTERS` env var · PyCharm Skip Files 设置 → env var → pydevd 内部 filter check(is_stepping=True 时触发)
- **关键**:PyCharm Skip Files 默认包含 site-packages、pydev helpers、stdlib · 但**用户自己的项目文件不在默认列表**。debug_ctx.py 是 `path2/debug_ctx.py` 属项目文件 · 理论上**不应自动 skip**
- 但 PyCharm 2026.1 可能有新的默认 skip 规则(如 "Skip *_ctx.py 命名模式")· 或用户自己曾手动加过 · 需 3 分钟检查

**η 的三种可能结果**:
| 结果 | 处理 |
|---|---|
| debug_ctx.py 在 Skip Files 列表 · remove 后 pause 不漂 | **η 秒解 · M1/M2 都不需要** · 文档化 IDE 配置步骤 |
| debug_ctx.py 不在 Skip Files 列表 · pause 仍漂 | drift 不在 Skip Files 层 · 走 M1(§5.5 landing 硬前置) |
| debug_ctx.py 不在 Skip Files 但也没有 UI 手动 override · pause 仍漂 | drift 在 IDE Java 侧的 "Just My Code" 或 "helper 启发式识别"(非 Skip Files 层)· 走 M1 |

**η 与 M1/M2 关系**:
- **η 是 IDE 配置层**、M1 是 pydevd 层、M2 是代码埋点层 · **三层正交** · 可组合可先后
- **η 优先**是因为**零成本**(用户 3 分钟无代码改动)· 若通过全流程免了
- **η 不冲突 M1/M2**:即使 η 通过 · 用户切换 IDE(VSCode/Cursor)时 IDE 配置不共享 · M1/M2 仍可作 IDE-agnostic 兜底

**rev5 立场**:η 前置一次 · 通过则 lock · 不通过再走 M1(landing §5.5 硬前置) · 再不通过退 M2。**方案矩阵调整为 η → M1 → M2 三级 fallback**。

### 6.5 acknowledge cpython_v2 rev2 实验 5

cpython_v2 rev2(`docs/research/2026-07-17_pydevd-suspend-pause-position/cpython_expert.md::rev2` 章节)追加实验 5 独立复核 M1 反抗机制 · 结果与 rev4 §5.2 源码走查**逐字对齐**:

- M0 pydev_step_cmd=**107**(CMD_STEP_INTO,由 `_mark_suspend` L983-986 从 -1 flip 而来)· pause frame=**debug_break** · event=**return** · pydev_step_stop_func=**None**
- M1 pydev_step_cmd=**108**(CMD_STEP_OVER)· pause frame=**caller** · event=**line** · pydev_step_stop_func=**caller 函数名**
- 三 anchor(ENTRY/TROUGH/END)全对齐 · 均传 caller frame 到 do_wait_suspend

**rev5 acknowledge**:cpython_v2 实验 5 = 我 rev4 §5.2 源码走查的**直接实证**(不再是"源码可复验的推理链" · 是 mock 环境下的实测)。M1 pydevd 层机制已**完全实证** · 唯一仍是纸面的 = "IDE Java 侧收到 caller frame 不 skip"(与 rev4 §5.5 landing 硬前置同一件事)。

**⚠ 反手错撤销**(2026-07-17 skeptic rev4 挑到):原 §6.5 "微修正 CMD_SET_BREAK=107(不是 rev4 §5.3 证据 4 里写的 111)" 是**混淆 pydev_step_cmd 与 stop_reason 两个独立字段的反手错** —— skeptic rev4 独立 grep 现场 `_pydevd_bundle/pydevd_comm_constants.py` L5-11 明确:
```
CMD_THREAD_SUSPEND = 105
CMD_THREAD_RUN     = 106
CMD_STEP_INTO      = 107   ← M0 走 _mark_suspend flip 到的 pydev_step_cmd 值
CMD_STEP_OVER      = 108
CMD_STEP_RETURN    = 109
CMD_SET_BREAK      = 111   ← rev4 §5.3 证据 4 与我今天 §5.8 rev5 原写的 stop_reason 值 · 正确
```

`set_suspend(t, stop_reason)` 的 `stop_reason` 是调用方传入的原值(`_locked_settrace` L1976 传 `CMD_SET_BREAK` = 111 · 交 IDE 显示 pause 原因)· `pydev_step_cmd` 是 `_mark_suspend` 内部改的(-1 → CMD_STEP_INTO = 107 · 驱动 trace_dispatch 判断)· **两个独立字段**。cpython_v2 实验 5 观察的 pydev_step_cmd=107 是 CMD_STEP_INTO(step 判断字段)· 不是 CMD_SET_BREAK。

**订正后正确表述**:
- M0 pydev_step_cmd = **107(CMD_STEP_INTO)** · stop_reason 传 IDE = **111(CMD_SET_BREAK)**
- M1 pydev_step_cmd = **108(CMD_STEP_OVER)** · stop_reason 传 IDE = **108(CMD_STEP_OVER)**(§5.8 rev5 已写对)
- rev4 §5.3 证据 4 写 CMD_SET_BREAK=111 **正确 · 无需修**;本节原"微修正"撤销 · 是我(pydevd_expert 上一份 rev5 §6.1-6.6)混淆字段导致的反手错

**cpython_v2 rev2 §sys.monitoring 强化章节**(PEP 669 M0 pause frame ≠ sys.settrace M0 · py_return_callback 无 STATE_SUSPEND 分支):rev5 判**无需并入 rev4** · 作为 cpython_v2 独立 note 即可。M1 只考虑 sys.settrace 路径(现场默认)· PEP 669 迁移是长期议题 · 与 M1 landing 无关。

### 6.6 交 lead 收尾的 minor gap 清单

**rev5 不再展开、交 lead 综合 final_report rev2 时收尾**的 5 项 skeptic_v2 rev3 未回应挑战:

1. **H2 表格残留(挑战 4 尾)**:rev4 §"H1/H2/H3 vs M1 生效" 三张表 H2 行 "M1 反抗 · is_stepping=True 绕过 cache_skips" 与 §5.6 认错清单矛盾。lead 综合时:H2 行改为 "同 M0 一样 is_stepping=True · cache_skips 短路对 M0 M1 都不生效 · H2 具体形式 = 无此机制"
2. **挑战 7a · "drift 100% 在 IDE"**:rev4 §5.1 沿用此表述过判(cpython_expert mock 未覆盖 IDE 回发命令场景)。lead 综合时改为 "drift 归因 = pydevd/CPython core 层无 · IDE 侧行为 或 pydevd + IDE 交互路径(如 PYDEVD_FILTERS)· 二选一 · cpython 实验只覆盖 pydevd 侧 · IDE 侧路径需用户实测收窄"
3. **挑战 7b · M1 failure mode 分层表**:skeptic rev2 §B.5 已给全表(pass / fail-mild / fail-severe / fail-cosmetic 四态 · 每态判据 + 回退策略)· lead 综合时直接搬进 final_report §"M1 fire 后的四态判据"
4. **挑战 7c · gate 埋点方案矩阵加 κ**:5 处埋点全显式传 `stop_at_frame` · 与 v4 A 线补 `class_id='tb'` 同批改动 · rebase 一次 landing 二价值。lead 综合时方案矩阵加 κ 与 A 并列(pydevd_expert 推荐 A;κ 是 skeptic 推荐 · 但要考虑 v4 A 线时序)
5. **挑战 7d · "M1 一次改动覆盖 5 埋点" 描述不一致**:改为 "M1 覆盖 4 处埋点(trough/end/end-timeout/entry)直接受益 · gate 埋点需办法 A 补 1 处 throwback.py 显式传参"

### rev5 修订小结

- **§6.1 挑战 6a clear**:CMD_THREAD_RUN 显式 reset pydev_step_stop=None · 无 dangling frame 风险
- **§6.2 挑战 6b 补 PYDEVD_DEBUG env 观察工具** · 新增 landing 判据 9(pause 未触发时用 log 区分 "IDE drift" vs "debug_break 短路" vs "pydevd bug")
- **§6.3 挑战 5c 补 IDE 状态栏视觉判据**:承认 M1 状态栏文字可能显示 "Stepped over" · 加 landing 判据 10(soft)· M2 side benefit 追加"UX 语义 100% 与用户预期一致"
- **§6.4 新方案 η 评估** · 强烈推荐 IDE Skip Files 配置作 pre-check(用户 3 分钟零成本 · 通过则 lock)· 方案矩阵调整为 η → M1 → M2 三级 fallback
- **§6.5 acknowledge cpython_v2 rev2 实验 5**:M1 pydevd 层机制**完全实证** · 只剩 IDE Java 侧纸面推理(与 rev4 §5.5 landing 硬前置同一件事)。**⚠ 原 §6.5 "微修正 CMD_SET_BREAK=107" 已撤(2026-07-17 skeptic rev4 挑到)** · 是混淆 pydev_step_cmd(107=CMD_STEP_INTO · step 判断字段)与 stop_reason(111=CMD_SET_BREAK · IDE 显示字段)两独立字段的反手错 · **rev4 §5.3 证据 4 与今天 §5.8 rev5 写的 CMD_SET_BREAK=111 正确 · 无需修**
- **§6.6 5 项 minor gap 交 lead 综合 final_report rev2 时收尾**(H2 表格残留 · "100% IDE" 表述 · failure mode 分层表 · gate 埋点方案 κ · M1 覆盖描述不一致)

## Sources

- pydevd source PyCharm 2026.1 helpers · `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py`
- pydevd source PyCharm 2024.3.5 helpers · `/home/yu/apps/pycharm-community-2024.3.5/plugins/python-ce/helpers/pydev/pydevd.py`
- pydevd_frame trace_dispatch · `/home/yu/apps/pycharm-community-2024.3.5/plugins/python-ce/helpers/pydev/_pydevd_bundle/pydevd_frame.py`
- Snyk `pydevd.settrace` doc · https://snyk.io/advisor/python/pydevd/functions/pydevd.settrace
- fabioz/PyDev.Debugger · https://github.com/fabioz/PyDev.Debugger/blob/main/pydevd.py
- JetBrains intellij-community pydevd · https://github.com/JetBrains/intellij-community/blob/master/python/helpers/pydev/pydevd.py
- microsoft/debugpy vendored pydevd · https://github.com/microsoft/debugpy/blob/main/src/debugpy/_vendored/pydevd/pydevd.py
- PEP 669 Low Impact Monitoring for CPython · https://peps.python.org/pep-0669/
- PyDev blog on sys.monitoring · https://pydev.blogspot.com/2024/02/pydev-debugger-and-sysmonitoring-pep.html

---

## rev5 · 承 lead 任务 #17(集中补 · 2026-07-17)

**任务范围**:skeptic_v2 rev3 判定 4 项(5c / 6a / 6b / η)+ acknowledge cpython_v2 rev2 实验 5。其他 skeptic 挑法(B.4/8a-8f/κ/θ/ι 等)由 lead 综合 final_report 处理 · 本节不重复。

### 5.7 · Acknowledge cpython_v2 rev2 实验 5(M1 反抗机制在 pydevd 层完全实证)

cpython_v2 rev2 §"实验 5 · 独立复核 pydevd_v2 rev4 M1 反抗机制" 用扩展 mock harness 拦截 `do_wait_suspend` · 三 anchor 并跑对照 M0 与 M1 · 结果 4 项 claim 逐字证实:

| pydevd_v2 rev4 claim | cpython_v2 实验 5 证据 | 结论 |
|---|---|---|
| stop_at_frame 走 CMD_STEP_OVER 分支 | `pydev_step_cmd=108`(= CMD_STEP_OVER) | ✓ |
| pydev_step_stop = caller frame | `pydev_step_stop_func` = caller 函数名(evaluate_throwback / _find_start_idx / _find_end_idx)三 anchor 全对齐 | ✓ |
| do_wait_suspend 传 IDE 的 frame 是 caller | `frame_func` = caller 函数名 · 不再是 debug_break_M1 | ✓ |
| pause 时 event 类型变化 | M0 event=return · M1 event=line · 走 pydevd_frame.py L890-892 line 分支 · 不走 L920-923 back trick | ✓ |

**rev5 pydevd_expert 认可**:rev4 §5.2 完整 pydevd 源码走查得到实验直接坐实 · M1 反抗机制在 **pydevd Python 层完全实证**。剩下唯一纸面一环 = "IDE Java 侧收到 caller frame 后是否真不 skip" · agent 无法测 · 与 landing 硬前置判据 1-5 是同一件事(§5.5)。

**rev5 表述纪律**:M1 机制现在有分层实证:
- **pydevd Python 层机制**:实证(cpython_v2 实验 5 · rev5 认可)
- **CPython C 层机制**:实证(cpython_v2 rev1 实验 1/2/3 · rev4 已认)
- **IDE Java 层机制**:纸面(需用户 PyCharm 现场实测 · landing 硬前置)

### 5.8 · 响应 skeptic_v2 rev3 §5c(fail-cosmetic:IDE 显示 stepping 状态而非 breakpoint)

skeptic 挑法:CMD_STEP_OVER 触发的 pause 在 PyCharm 里可能显示 "stepped over" 状态而非 "paused at breakpoint" · 用户预期是断点停 · 看到 step 状态可能困惑。

**rev5 论证**:

**5.8.1 · stop_reason 字段传给 IDE**:

看 pydevd_frame.py L891:
```python
if is_line:
    self.set_suspend(thread, step_cmd)
    self.do_wait_suspend(thread, frame, event, arg)
```

`set_suspend(thread, step_cmd)` 传的第二个参数是 stop_reason · 这里 step_cmd = CMD_STEP_OVER = 108。所以 IDE 收到的 `thread_suspend` 消息里 stop_reason = 108(CMD_STEP_OVER),不是 111(CMD_SET_BREAK)。

**在 PyCharm 里的直接后果**:pause 消息路由到 IDE "step over completed" UX handler,而非 "breakpoint hit" UX handler。用户界面可能显示:
- 底部状态栏文字:"Stepped over" 而非 "Reached breakpoint at ..."
- 断点小红圆点:可能不高亮(因为没有 breakpoint 对象匹配)
- 变量面板:正常显示(与 breakpoint pause 无差别)
- Continue 按钮:正常工作

**5.8.2 · 是否 blocker**:

pydevd_expert 独立评估:
- **功能上**:pause 位置正确、变量可见、continue 可用 · fail-cosmetic **不影响 debug workflow 核心** · 只是状态文字差异
- **用户偏好**:v3 initial design(commit 8cd2e7c)选 `pydevd.settrace(suspend=True)` 是为了替代 `breakpoint()`(因后者同 line 只 fire 一次)· **动机是"每次都停"而非"stop_reason 显示为 breakpoint"** · 若"停"这件事对了 · stop_reason 显示不同不违背原设计意图
- **调试上下文**:用户是**开发者 · 会看 stack trace 而非光看状态栏**;pause 落在 throwback.py:164 + 变量面板显示 trough_idx · 已足够定位。状态栏文字差异对已知这是 dev tool 的开发者 = 认知负担小

**结论**:5c fail-cosmetic **接受为 M1 已知代价** · 不作 M1 blocker;landing 硬前置里 6c 条(§5.9)明列此判据 · 用户实测时若发现状态显示差异**不 impact workflow** 则 M1 通过 · 若用户偏好要求 "必须是 breakpoint 状态" 则退 M2(移埋点让 breakpoint() fallback 生效 · 但要提醒 breakpoint() 有 "同 line 只 fire 一次" 的老问题 · 与 v3 硬要求冲突)。

**Trade-off 明写**:M1 的 stop_reason=CMD_STEP_OVER 换来 pause 位置对齐 · M2 保留 breakpoint 状态但要么 debug_break 结构改(移埋点)要么退回 breakpoint()(违 v3 硬要求)。这个 trade-off pass 给用户偏好决策。

### 5.9 · 响应 skeptic_v2 rev3 §6a(Continue 后 pydev_step_stop 清理)

skeptic 挑法:CMD_STEP_OVER 是 per-call state · 但用户按 Continue 后 pydevd 是否真 clear pydev_step_stop?若不 clear · 下次 debug_break 触发前 pydev_step_stop 残留上次 frame 引用(可能已 GC · dangling)· pydevd 内部可能错乱。

**rev5 现场 grep 直接证实**:

现场 pydevd 1.4.0 · `_pydevd_bundle/pydevd_process_net_command.py::process_net_command` L196-214:

```python
elif cmd_id == CMD_THREAD_RUN:
    py_db.maybe_kill_active_value_resolve_threads()
    threads = []
    if text.strip() == '*':
        threads = pydevd_utils.get_non_pydevd_threads()

    elif text.startswith('__frame__:'):
        sys.stderr.write("Can't make tasklet run: %s\n" % (text,))

    else:
        threads = [pydevd_find_thread_by_id(text)]

    for t in threads:
        if t is None:
            continue
        additional_info = set_additional_thread_info(t)
        additional_info.pydev_step_cmd = -1        # ← 重置 step_cmd
        additional_info.pydev_step_stop = None     # ← 重置 step_stop · 显式清 frame 引用
        additional_info.pydev_state = STATE_RUN
```

**用户在 PyCharm 里按 Continue** → IDE 发 CMD_THREAD_RUN → pydevd 显式 clear:
- `pydev_step_cmd = -1`
- `pydev_step_stop = None`(**显式清 frame 引用 · Python GC 可回收前一次 caller frame · 无 dangling 风险**)
- `pydev_state = STATE_RUN`

**下次 debug_break 触发前 state 干净**:pydev_step_stop = None + pydev_step_cmd = -1 · 若下次触发 M0 走 `_mark_suspend` L983-986 从 -1 flip 到 CMD_STEP_INTO(rev4 §5.2 已引);若下次触发 M1 走 `_locked_settrace` L1966-1973 显式设 pydev_step_stop = new caller frame · 覆盖 None · 无残留。

**结论**:**skeptic 6a 挑到的 dangling frame 风险不存在** · pydevd 命令处理层显式清理 · 不需要 pydevd_expert 侧额外补代码。

**次级观察**(rev5 补):即使 CMD_THREAD_RUN 没显式清 · additional_info 是 per-thread state · 若 thread 生命周期覆盖多次 debug_break · **_locked_settrace 每次都覆盖 pydev_step_stop**(L1972 直接赋值不追加)· 也不会残留。所以 pydevd 层有两道保险 · 6a 风险为 0。

### 5.10 · 响应 skeptic_v2 rev3 §6b(pause 未 fire 的观察工具)

skeptic 挑法:若 M1 fail-severe(pause 完全消失)· 用户如何知道是 "pause 没触发" 而不是 "debug 挂了 / debug_break 短路"?rev4 应加 landing 判据的观察工具。

**rev5 补 3 层观察工具**(landing 硬前置第 7 条 · §5.5 6a 已列 6 条 · 6b 补第 7 条):

**工具 1 · pydevd 内部日志**:
```bash
export PYDEVD_DEBUG=1
export PYDEVD_DEBUG_FILE=/tmp/pydevd_debug.log
# 启 PyCharm debug tb 场景 → grep log 观察 do_wait_suspend 是否被调用
grep "do_wait_suspend\|_do_wait_suspend\|thread_suspend" /tmp/pydevd_debug.log
```
若 log 有 do_wait_suspend 调用 · pydevd 层 pause 触发成功 · fail-severe 归 IDE Java 侧;若 log 无调用 · pydevd 层 pause 未触发 · fail-severe 归 pydevd 层(需回退到 M0 排查)。

**工具 2 · 埋点侧 print + flush**:
```python
# path2/debug_ctx.py::debug_break 内 · 在 pydevd.settrace 前后加临时 print
def debug_break(i, *, anchor_kind, class_id, stop_at_frame=None):
    if not _DEBUG_MODE:
        return
    ...
    print(f"[debug_break] fire: i={i} anchor_kind={anchor_kind}", flush=True)
    try:
        import pydevd, sys
        pydevd.settrace(suspend=True,
                        stop_at_frame=stop_at_frame or sys._getframe(1))
        print(f"[debug_break] settrace returned · pause 未生效", flush=True)  # 若这行 print · 说明 pydevd 走完了 · pause 已 process(通过 continue 释放 · 或没 pause 直接返回)
    except ImportError:
        breakpoint()
```
若 "[debug_break] fire" 打印 · debug_break 未短路(_DEBUG_MODE/range/anchor_kind gate 都通过);若 "settrace returned" 打印 · pydevd 已处理完 pause(可能 IDE 侧继续 continue)· 需要工具 1 log 交叉判定。

**工具 3 · IDE 侧 breakpoint 参照**:
在 `throwback.py:164 return trough_idx` **同一行手动打一个 PyCharm 断点**(红圆点)· 用作参照。M1 pause 落对 = 用户看到手动断点和 M1 pause 同一行(可能 IDE 只显示手动断点、M1 pause 不显示,但至少能确认 "line event 触发了")。

**Landing 硬前置 §5.5 补第 7 条**(rev5 追加):

7. [必过] **fail-severe 观察工具**:若 M1 pause 未按预期触发 · 用工具 1 log 交叉判定 pydevd 层是否触发 do_wait_suspend · **区分 fail-severe(pydevd 层未触发 · 需回退)vs "IDE 侧 UX 展示不同"(pydevd 层触发了但 IDE UI 差异)**

**降级路径同步补**(rev4 §5.5 fail-severe 分层):
- 若 log 有 do_wait_suspend 调用 但用户 UI 看不到 pause → IDE 层 auto-forward · **归入 M1 fail-mild 分层**(退 M2)
- 若 log 无 do_wait_suspend 调用 → pydevd 层未触发 · **归入 M1 fail-severe 分层**(先回滚 M0 排查 · 再退 M2)

### 5.11 · 响应 skeptic_v2 rev3 §η(IDE Skip Files 配置层规避)

skeptic 挑法:η 是 first-check drift 归因手段(零代码 · 3 分钟工作量)· lead 决策阶段应在决定 M1 vs M2 前先让用户试。

**rev5 pydevd_expert 立场:强烈同意 η 作为 first-check step · 应前置于 M1 landing**。

**理由**:
1. **零代码风险**:η 只改 IDE 配置 · pydevd/项目代码不动 · 侵入面 = 0
2. **成本极低**:用户 3 分钟(打开 Preferences → 检查 Skip Files 列表)
3. **归因价值高**:若 debug_ctx.py 或 path2/ 在 Skip 列表 · remove 后立即观察 drift 是否消失 · **直接坐实/证伪 IDE Skip Files 是 root cause**
4. **与 M1 无冲突**:η 通过 → 本任务不启动 M1 · zero-cost 解决;η 不通过 → drift 不在 Skip Files 层 · 再走 M1 · 而且此时 M1 landing 已有更精确的 root cause 排除面(不用担心 M1 pause 位置对了但 IDE 依然 skip)

**rev5 补 η 具体操作步骤**(送 lead 综合 · 用户实测参考):

```
1. 打开 PyCharm 2026.1 · File → Settings(Ctrl+Alt+S)
2. 导航到 Build, Execution, Deployment → Debugger → Stepping
3. 检查 "Do not step into the classes"、"Do not step into the following files/directories" 两个列表
4. 若列表里出现:
   - path2/debug_ctx.py(或 debug_ctx)
   - path2/*(或 path2 目录)
   - **/debug_*.py 等 wildcard
   → 手动 remove 该条目 · Apply
5. 检查 "Skip synthetic methods" / "Skip constructors" 等 checkbox · 若勾选 · try uncheck
6. 检查 "Just My Code" / "Debug only user code" 设置(如有)· try disable
7. Cmd+Shift+F9 restart PyCharm · 重跑 FV2 场景 J2 · 观察 trough pause 位置
```

**η 判定判据**:

| 观察 | 归因 | 后续动作 |
|---|---|---|
| pause 落 `throwback.py:164` | drift 是 IDE Skip Files · η 修复 | 本任务完成 · 文档化 IDE 配置 |
| pause 仍 `_find_end_idx:200` | drift 不在 IDE Skip Files 层 · 可能是 IDE 内部 UX auto-forward | 走 M1 landing 硬前置 |
| pause 变成其他位置(既非漂也非目标) | 新 UX 行为 · 需重新诊断 | 回复用户观察 · pydevd_expert rev6 分析 |

**rev5 修订 M1 landing 硬前置** · 承 skeptic 8e:

**η 前置于 M1 landing** —— 顺序:

1. **η 步骤**:用户按 §5.11 操作 · 观察 3 分钟 → 若 η 通过 · 结束
2. **M1 步骤**(η 不通过时):按 rev4 §5.5 landing 硬前置 6 条 + rev5 §5.10 第 7 条 + rev5 §5.8 fail-cosmetic 判据

### 5.12 · rev5 M1 failure mode 分层表(承 skeptic B.5)

skeptic B.5 要求 M1 fail 分层 4 态 · rev4 §5.5 已列降级路径但未成表 · rev5 补:

| 场景 | M1 pydevd 层行为 | 用户 UI 观察 | 分层判据 | 分层回退策略 |
|---|---|---|---|---|
| **M1 pass** | pause 触发 · frame=caller · event=line | pause 落 `throwback.py:164` · 变量面板显示 trough_idx/depth/peak | landing 判据 1-6 + 5.10 判据 7 全过 | **采纳 M1** · gate 用办法 A |
| **M1 fail-mild** | pause 触发 · frame=caller · event=line · pydevd 层无异常 | pause 落 `throwback.py:164` 或再被 IDE auto-step 跳到下游(与 M0 现象等价) | 5.10 工具 1 log 有 do_wait_suspend 调用 + UI 未停对位置 | **退 M2**(移埋点)· pydevd-agnostic |
| **M1 fail-severe** | pause 未触发 · pydevd_step_stop 与 caller frame 引用错乱 或 caller line event 未 fire | 用户按 debug 后 detector 跑完 · **无 pause 出现** · debug 像"挂了" | 5.10 工具 1 log 无 do_wait_suspend 调用(或工具 2 print 显示 settrace returned 但无 pause) | **先回滚到 M0**(避免 debug 挂了比漂位置更痛)· 再评估退 M2 |
| **M1 fail-cosmetic** | pause 触发 · frame=caller · event=line · pydevd 层完全正常 | pause 位置对 · 变量对 · **只是 IDE 状态栏显示 "Stepped over" 而非 "Reached breakpoint"** | 5.10 工具 1 log 有 do_wait_suspend · UI 位置对 · 用户观察状态文字差 | **用户偏好决定**:接受 = 采纳 M1(功能全对 · 只是状态文字不同);不可接受 = 退 M2(pydevd-agnostic 兜底) |

### 5.13 · rev5 修订历史

- **rev5**(2026-07-17 · 本节):承 lead 任务 #17 集中补 4 项 skeptic_v2 rev3 判定 + acknowledge cpython_v2 rev2 实验 5:
  - §5.7 Acknowledge cpython_v2 实验 5 直接证实 M1 反抗机制 pydevd Python 层完全实证 · rev5 明列三层实证纪律(pydevd Python 层实证 / CPython C 层实证 / IDE Java 层纸面待用户实测)
  - §5.8 响应 5c fail-cosmetic:M1 传 stop_reason=CMD_STEP_OVER 换 pause 位置对齐 · 不影响 debug workflow 核心 · 接受为已知代价 · trade-off 明写
  - §5.9 响应 6a Continue 清理:现场 grep pydevd_process_net_command.py L211-214 直接证实 CMD_THREAD_RUN 显式 clear pydev_step_stop/pydev_step_cmd/pydev_state · additional_info per-thread + _locked_settrace 每次覆盖 · dangling frame 风险为 0
  - §5.10 响应 6b 观察工具:补 3 层工具(PYDEVD_DEBUG log / 埋点侧 print / IDE 参照断点)· landing 硬前置补第 7 条 · 降级路径补 fail-severe vs fail-mild 判定
  - §5.11 响应 η IDE Skip Files:强烈同意作为 first-check · 前置于 M1 landing · 补 7 步具体操作步骤 + 3 态观察判据
  - §5.12 M1 failure mode 分层 4 态表(pass / fail-mild / fail-severe / fail-cosmetic)· 补 rev4 未成表的降级判据
- 其他 skeptic 挑法(B.4 cache_skips 残留清理 · 8a-8f lead final_report rev1 沿用问题 · κ 全埋点显式 · θ 挪目录 · ι sys.settrace 手动)由 lead 综合 final_report 处理 · rev5 不重复
