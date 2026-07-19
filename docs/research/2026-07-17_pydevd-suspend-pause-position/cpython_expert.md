# cpython_expert · CPython 层与 sys.monitoring 分析

**角色**:cpython_expert(agent team 4 人成员 · lead 是主会话)
**任务**:从 CPython 底层解释 pydevd `settrace(suspend=True)` 的 pause 位置漂移 · 挖掘 sys.monitoring 是否可替代
**归档**:`docs/research/2026-07-17_pydevd-suspend-pause-position/cpython_expert.md`
**final_report.md**:由 leader 合成 · 本文只是中间稿
**状态**:rev2(peer review 融合完毕 · 加实验 4/5 · 已同步 pydevd_expert rev4 结论)

---

## 现场事实(与其他 teammate 共享)

- Python:3.12.12
- pydevd 版本:**1.4.0**(JetBrains fork,`__version_info__ = (1, 4, 0)`)
- pydevd 路径:`/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py`
- 项目里 pydevd 未装进 uv env(`uv pip show pydevd` not found);运行时靠 PyCharm helpers 注入 `sys.path`
- Python 3.12 上,pydevd 1.4.0 的 frame-eval 路径被显式 disable(`elif IS_PY312_OR_GREATER: pass`,see `_pydevd_frame_eval/pydevd_frame_eval_main.py:26`)
- `USE_LOW_IMPACT_MONITORING = IS_PY312_OR_GREATER and os.environ.get('USE_LOW_IMPACT_MONITORING', False)`(default **False**)· 现场用户未 opt-in · **走 sys.settrace 路径,不走 PEP 669**

---

## 结论摘要(1 句话)

**CPython 层与 pydevd 1.4.0 core dispatch 都没有 L163 / L216 / L219 的不对称;三处埋点在这两层都会在 `debug_break` 的 `return` 事件精确落地。用户观测到的漂移(TROUGH 落 `_find_end_idx:200`,END/ENTRY 不漂)本质是 PyCharm IDE 客户端(Java 侧)对 pause 消息的二次处理,pydevd/CPython 层面无解。**

---

## 论证 · 三份实验证据

### 实验 1 · raw sys.settrace 无不对称(H1 反证 CPython 层脏)

**脚本**:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-gateA-notwork/c23b5f45-29bb-4675-bb4e-52aa7e281e32/scratchpad/pause_asymmetry.py`

**做法**:复刻 throwback.py 三函数嵌套结构(_find_start_idx / _find_end_idx / evaluate_throwback)· 用 `sys.settrace` 自定义 tracer 完全按 pydevd 语义模拟 `settrace(suspend=True)` = "下一次 `line` 事件停下"· 打印 event 序列。

**结果**(截录):

```
=== ENTRY (bo_idx=0 → if True return) ===
  pause 落地 → evaluate_throwback():47   ← 「if bo_idx < 1:」这一行
  events 序列:
    call    debug_break():15
    line    debug_break():17
    call    _mark_pause_requested():67
    line    _mark_pause_requested():69
    return  _mark_pause_requested():69 [pause_req=entry]
    return  debug_break():17           [pause_req=entry]
    line    evaluate_throwback():47    [pause_req=entry]   ← ★ 落地正确

=== TROUGH (直接 _find_start_idx) ===
  pause 落地 → _find_start_idx():32   ← 「return trough_idx」这一行
  events 序列:
    ... (同 ENTRY 结构) ...
    return  debug_break():17           [pause_req=trough]
    line    _find_start_idx():32       [pause_req=trough]  ← ★ 落地正确

=== END (直接 _find_end_idx) ===
  pause 落地 → _find_end_idx():41    ← 「return i - 1」这一行
  events 序列:
    ... (同 ENTRY 结构) ...
    return  debug_break():17           [pause_req=end]
    line    _find_end_idx():41         [pause_req=end]    ← ★ 落地正确
```

**读法**:CPython 的 `line` 事件在三个 anchor 上全部对齐 `return` 那一行(TROUGH → `return trough_idx` L32,END → `return i-1` L41)· **三个 anchor 之间没有任何不对称,drift 为零**。

**H1 反证**:若 drift 源自 CPython trace 语义,应该在这里就能看到 TROUGH 漂过 return 行落到 caller / 下游函数。实测三处齐整,H1 被排除。

---

### 实验 2 · pydevd 1.4.0 真跑无不对称(H2 反证 pydevd core dispatch 脏)

**脚本**:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-gateA-notwork/c23b5f45-29bb-4675-bb4e-52aa7e281e32/scratchpad/pause_pydevd_real.py`

**做法**:
1. 把现场 PyCharm helpers 加进 `sys.path`(pydevd 1.4.0)
2. Monkey-patch `PyDB.connect / do_wait_suspend / start_auxiliary_daemon_threads / patch_threads`——绕开 IDE socket,把 `do_wait_suspend` 改成"记录 frame + 立即释放"
3. 每场景直接调 `_find_start_idx` / `_find_end_idx` / `evaluate_throwback`
4. **两个 phase**:PHASE 1 每次 first-connect;PHASE 2 先跑 `settrace(suspend=False)` 让 connected=True,再跑 warm-up 让 `cache_skips` 建起来(**贴近真 PyCharm 已 connected + debug_break 已多次调用的状态**)

**结果**:

```
### PHASE 1: 每场景走 first-connect 分支 ###
=== ENTRY (bo_idx=0) ===
  [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)

=== TROUGH (直接 _find_start_idx) ===
  [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)

=== END (直接 _find_end_idx) ===
  [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)

=== 整链 (bo_idx=5, ENTRY+TROUGH+END 都 fire) ===
  [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)
  [2] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)
  [3] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)

### PHASE 2: connected=True + debug_break 已跑过多次(模拟真 PyCharm) ###
PHASE 2 · TROUGH: [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)
PHASE 2 · END:    [1] pause 落地 → pause_pydevd_real.py:84 in debug_break() (event=return)
```

**读法**:pydevd 1.4.0 的 `do_wait_suspend` **每一场景都在 `debug_break` 的 `return` 事件精确落地一次 · 传的 frame 就是 debug_break 本身**。三个 anchor(TROUGH / END / ENTRY)行为**完全一致 · 零不对称 · 零 drift 到 caller · 更零 drift 到 `_find_end_idx`**。

**H2 反证**:若 drift 源自 pydevd core dispatch,实验 2 应能看到 TROUGH 传的 frame 是 `_find_end_idx` 而非 `debug_break`。实测三处齐整传 `debug_break`,H2 被排除。

---

### 实验 3 · 字节码层无不对称(H3 反证 PEP 657 fine-location 脏)

**脚本**:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-gateA-notwork/c23b5f45-29bb-4675-bb4e-52aa7e281e32/scratchpad/bytecode_asymmetry.py`

**做法**:两个函数 · 一份复刻 L163(`for` + 3 层嵌套 `if` + `return`),一份复刻 L219(`for` + 1 层 `if` + `return`)· 用 `dis` + `co_lines()` 观察 `RETURN_VALUE` 的 line 归属。

**结果**(截录):

```
variant_L163 (3 nested ifs):
  offset=168  RETURN_VALUE  positions=(line=23, col=20..37)   ← 「return trough_idx」
  co_lines: bytecode[162..170] → line 23  ✓
  co_lines: bytecode[170..172] → line 13  (END_FOR 回归 for 头)

variant_L219 (1 if):
  offset= 88  RETURN_VALUE  positions=(line=33, col=12..24)   ← 「return i - 1」
  co_lines: bytecode[ 76.. 90] → line 33  ✓
```

**读法**:两个 `RETURN_VALUE` 的 `positions.lineno` 都正确指向 `return` 那一行。Python 3.11+ PEP 657 fine location 在两个 variant 下**行为完全一致**。嵌套深度(3 层 vs 1 层)不影响 return 的 line attribution。

**H3 反证**:H3 也被排除。

---

## 由三份实验倒推 · 漂移在哪一层

三层证伪叠加 → 漂移不在 CPython trace 语义 / pydevd core dispatch / bytecode 层。**剩下唯一嫌疑 = PyCharm IDE 客户端(Java 侧)对 pydevd 发过来的 `thread_suspend` 消息的二次处理**。

**可能机制**(pydevd/CPython 侧无法直接验证 · 需要 pydevd_expert 侧查 `pydevd_pycharm.py` + IDE 协议或用户实测):

1. **Frame filter / "Skip files" / "Just My Code"**:PyCharm 可能识别 `debug_ctx.py::debug_break` 是"helper / 内部工具"类文件 · 客户端自动 skip 该 frame · 发出 auto-step(相当于用户按了 F8/F7)· pydevd 于是继续 fire `line` 事件到下一个"用户代码"位置。
2. **Return-event pause 的 UX 处理**:pydevd 传过来的是 `debug_break.f_lineno` + `event='return'` · frame 即将从栈上消失 · IDE 可能主动"透传"到 caller frame · 但由于 caller 的下一个可停 line 可能又被 skip,继续漂;累计漂到 `_find_end_idx:200` 是 `_find_start_idx return` + `evaluate_throwback L262 end = _find_end_idx(...)` + 进入 `_find_end_idx` 后第一个可执行行的连锁反应。
3. **`set_next_statement` 或 IDE 自己的 step_cmd**:IDE 收到 pause 消息后可能自动发送 `CMD_STEP_INTO_MY_CODE` · pydevd 就会 `stop = is_line and in_project_scope(frame.co_filename)` · 逐 line 检查 · 遇到第一个 project-scope 且不被 skip 的 frame 停下。

**为什么 TROUGH 漂 · END/ENTRY 不漂**——这个不对称需要 IDE 侧的 skip / 过滤规则解释。CPython 层完全对称,给不出理由。

**关键**:即使我们能在源码里找到 "IDE 侧 skip 规则触发的 pydevd 分支",那也不是 CPython 或 pydevd core 的问题 · 而是 IDE 配置 + client 协议。

---

## sys.monitoring(PEP 669)是否可替代 · 结论:**不能修 drift**

### 与 sys.settrace 的差异

| 维度 | sys.settrace(旧) | sys.monitoring(PEP 669,Python 3.12+) |
|---|---|---|
| 触发时机 | frame 每 line/call/return 都 fire tracer | 只在 opt-in 的 line/code 上 fire callback |
| Line event | 每根一次(即 CPython 的 line-number 变了就 fire) | `LINE` 事件默认关 · 靠 `monitoring.set_local_events(tool_id, code, LINE)` per code object 打开 |
| Return event | 每个 `return` 都 fire(if frame traced) | 拆成 `PY_RETURN`(Python 函数返回) + `PY_YIELD` + `PY_UNWIND`(异常回栈) |
| 位置控制 | frame-level(`frame.f_trace = ...`) | code-object level + per-instruction opt-in(`set_local_events`)· 更精细 |
| 开销 | 全局 tracer 每 event 一次 dispatch(即使不 stop) | 未 opt-in 的 code 零开销;opt-in 后按 event 精准 fire |
| pydevd 已适配? | **是**(默认路径) | **是,但 opt-in**(`USE_LOW_IMPACT_MONITORING=1` env var 才启用 · pydevd 1.4.0 已有完整实现:`_pydevd_bundle/pydevd_pep_669_tracing.py`) |

### pydevd 的 PEP 669 实现要点

从 `pydevd_pep_669_tracing.py` 看:
- 用 `monitoring.use_tool_id(DEBUGGER_ID, PYDEVD_TOOL_NAME)` 注册工具
- 默认注册 `PY_START | RAISE` 两个全局事件 · `LINE/PY_RETURN` 走 code-level opt-in(`_enable_line_tracing(code)` / `_enable_return_tracing(code)`)
- `py_line_callback(code, line_number)` 是核心 pause 触发点 · 检查 `info.pydev_state == STATE_SUSPEND` → `py_db.do_wait_suspend(thread, frame, 'line', None)`
- **suspend 语义完全一致**:pydev_state / step_cmd 状态机与 sys.settrace 路径共用(`_pydevd_bundle.pydevd_additional_thread_info`)
- **do_wait_suspend 传的 frame 也是当前 frame**(与 sys.settrace 版一样)

### 为什么 PEP 669 不能修 drift

- pydevd 的 pause 语义和 do_wait_suspend 消息组装逻辑在两条路径下**完全一致**;差异只在"什么时候 fire 事件"和"每 event 的开销"
- **drift 发生在 IDE 客户端**(Java 侧对 pydevd `thread_suspend` 消息的二次处理),PEP 669 只换了 pydevd 侧的事件源 · 没有改 IDE 协议 · **无法影响 IDE 侧的 frame skip / auto-step 行为**
- 即使把用户环境切成 `USE_LOW_IMPACT_MONITORING=1`,`debug_break` 内 `pydevd.settrace(suspend=True)` 传给 IDE 的还是同一份 `thread_suspend` 消息,IDE 该 skip 还是 skip

**判断**:PEP 669 是性能优化路径 · 不是位置控制路径 · 对 drift 这个问题**无关**。

---

## 有解还是无解 · 判断

**在 pydevd/PyCharm layer 层面 · 三个可能出口**(按可行性排):

### 出口 A · `pydevd.settrace(stop_at_frame=caller_frame)`(★ 最有希望)

pydevd 1.4.0 `settrace()` 有一个 `stop_at_frame` 参数(`pydevd.py:1819`)· `_locked_settrace` 里的处理:

```python
if suspend:
    if stop_at_frame is not None:
        # If the step was set we have to go to run state and
        # set the proper frame for it to stop.
        additional_info.pydev_state = STATE_RUN
        additional_info.pydev_step_cmd = CMD_STEP_OVER
        additional_info.pydev_step_stop = stop_at_frame
        additional_info.suspend_type = PYTHON_SUSPEND
    else:
        # Ask to break as soon as possible.
        py_db.set_suspend(t, CMD_SET_BREAK)
```

**用法**:`debug_break` 里改成

```python
import pydevd
caller_frame = sys._getframe(1)                    # 取 caller 的 frame(如 _find_start_idx)
pydevd.settrace(suspend=True, stop_at_frame=caller_frame)
```

**语义**:走 `CMD_STEP_OVER + pydev_step_stop = caller_frame` · pause 语义变成"当执行流回到 caller_frame 时停下"· 这时 IDE 收到的 pause 消息 frame 是 `_find_start_idx` 而不是 `debug_break` · **理论上可以规避 IDE 的 skip 行为**。

**风险**(留给 pydevd_expert 与 skeptic 挑):
- CMD_STEP_OVER 的判定是 `stop_frame is frame`(见 `pydevd_frame.py:840` 与 pep669 版对齐),要求 caller_frame 是"当前正在执行的 frame"· `debug_break` return 后回到 `_find_start_idx` L164(下一行),pause 应该落这里
- `sys._getframe(1)` 拿到的 frame 引用在 debug_break 返回后是否仍有效 · Python 层面 f_back 引用会持续存活直到 frame 出栈 · 但 pydevd 是否会因 frame 变化而失效 · 需实测
- L104 gate 场景(`_emit_tb_gate` 里的 debug_break)caller 是 `_emit_tb_gate` 而不是外层 detector · 语义可能与 L163/L216/L221 不一致;要么按 anchor_kind 挑 caller 深度 · 要么统一 caller
- pydevd 版本兼容:`stop_at_frame` 参数在 pydevd 1.4.0 有 · 是否所有版本都有 · 需 pydevd_expert 追

### 出口 B · 换 IDE 配置(不改代码)

若 PyCharm 有一个"关闭 return-event auto-step"或"把 `debug_ctx.py` 从 skip 列表移除"的设置 · 直接改配置就能修。**成本极低 · 但需要用户在 PyCharm 里找到这个设置** · pydevd 层面无法查得。留给 pydevd_expert 侧研究 `pydevd_pycharm.py` 与 PyCharm settings。

### 出口 C · 移埋点位置(skeptic 兜底 A 已列)

把 `debug_break(trough_idx, anchor_kind='trough')` 从 `_find_start_idx` L163 移到 `evaluate_throwback` 内 · `_find_start_idx` 返回后紧接着 debug_break。这样 debug_break 的 caller 就是 evaluate_throwback · pause 落在 evaluate_throwback 内(有 `start` / `bo_idx` / `anchor` 可看)· 但拿不到 `_find_start_idx` 内的 `depth` / `peak` 中间值。**Trade-off 明确 · 兜底可行**。

### 出口 D · 用户观察不重现

需 pydevd_expert 侧考虑一个可能:用户看到的 drift 是 PyCharm 2026.1 特定版本 bug · 换 PyCharm 版本可能没了。留 pydevd_expert 挑。

---

## 送 peer review 的两个点

给 **pydevd_expert**:
1. 请查 `pydevd_pycharm.py` 与 PyCharm 客户端 · 有没有"return-event pause 转 caller frame"的规则 · 若有 · 是否可配
2. `stop_at_frame` 参数(出口 A)在 pydevd 1.4.0 是否 pydevd 官方 public API · 会不会在 debugpy fork(`_vendored/pydevd/`)中被移除

给 **pause_skeptic**:
1. 出口 A 若 caller frame 引用在 debug_break 返回后失效 · pause 会怎样降级(fallback 到当前 frame · 还是不 pause)· 6 维审
2. 出口 A 的 L104 `_emit_tb_gate` 场景 · caller frame(evaluate_throwback 内的 `_emit_tb_gate` 调用点)与 anchor_kind='gate' 期望的 pause 位置是否一致

---

## 修订历史

- rev1(2026-07-17):三份实验(sys.settrace / real pydevd / bytecode)全跑 · 三层证伪 CPython/pydevd core/bytecode · 定位 drift 在 IDE 客户端 · 出口 A(stop_at_frame)+ 三兜底 · 待 peer review
- rev2(2026-07-17 · 本稿):补实验 4/5/6 · 独立复核 pydevd_v2 rev4 "M1 反抗机制" 得 pydevd 层间接证据(实验 5 · CMD_STEP_OVER + pause frame 真变 caller · event=line)· 覆盖 skeptic 预挑三 gap · 强化 sys.monitoring 排除结论(补 PEP 669 stop-frame 语义分析 · 修正 rev1 "换事件源不改 IDE 侧行为" 的不精确表述)

---

# rev2 · 覆盖 skeptic_v2 预挑 · 补实验 4/5/6 · 独立复核 pydevd_v2 rev4 M1 反抗机制

**状态**:rev2(本节 append · 不覆盖 rev1)
**任务**:承接 lead 布置 4 项(回应 skeptic_v2 挑三份实验 gap / 补边界实验 / 独立复核 pydevd_v2 rev4 纸面推理 / 强化 sys.monitoring 排除)· 出稿供 skeptic_v2 与 pydevd_v2 review

## rev2 结论摘要(4 句)

1. **实验 4**(直接 dis path2/atoms/throwback.py 现场文件 · 全 4 return 变体):所有 12 处 return 行都有独立 line 归属(rise L220 / timeout L225 / entry L251 / gate 附近 L105 · 三处 None return L151/L177/L185/L217/L252/L255/L261/L266 · 表达式 return L167/L220/L225/L267)· **H3 全 variant 全线证伪 · 不再是 M1 的 gating**。
2. **实验 5**(直接给真 pydevd 传 stop_at_frame=sys._getframe(1) · 用 mock IDE 拦截 do_wait_suspend):**M1 反抗机制在 pydevd 层实证成立** —— M0 走 CMD_SET_BREAK(107)传 debug_break frame + event=return · M1 走 CMD_STEP_OVER(108)传 **caller frame** + event=line · pydev_step_stop_func 精确对应 caller · 三 anchor 全对齐。这是 pydevd 层能提供的最强间接证据 · 与 pydevd_v2 rev4 纸面推理一致 · 唯一仍是纸面的是 "IDE 侧 Java 收到 caller frame 就不 skip" 这一环。
3. **实验 6**(pydevd 的 in_project_scope 对 debug_ctx.py / throwback.py 的判定):两个文件在 agent 默认(无 IDE_PROJECT_ROOTS)与模拟 PyCharm 场景(IDE_PROJECT_ROOTS=项目根)下**都判 in_project=True** · **pydevd Python 层的 in_project_scope 不足以解释 drift 的不对称** · drift 的过滤规则必然在 PyCharm Java 侧("Skip files"/"Just My Code"/step filter · pydevd Python 层无法拿到该配置)。
4. **sys.monitoring 排除结论强化**:rev1 "换事件源不改 IDE 侧行为" **不精确** · PEP 669 M0 的 pause frame 语义与 sys.settrace M0 **不同**(py_return_callback 无 STATE_SUSPEND 分支 · CMD_SET_BREAK 只在 py_line_callback 触发 · pause frame 会自然落 caller 而非 debug_break) · **理论上 PEP 669 单飞可能修 drift**;但 rev2 保留排除结论 · 理由变为 "PEP 669 需 opt-in(USE_LOW_IMPACT_MONITORING=1)· 现场用户未 opt-in · 且 opt-in 后 IDE 侧行为未测 · 与 M1 相比无优势"。

---

## 回应 skeptic_v2 预挑三 gap

### Gap 1(预挑实验 1):raw sys.settrace 是否真复刻了 pydevd 的 suspend 语义?

**skeptic 预挑理由**:自实现 tracer 只模拟 "下一次 line event 停下" · 没有 pydevd 的 `additional_info` 状态机 / cache_skips / frame_skips_cache / project_scope filter 等中间层 · 差异可能被挑到 gap。

**rev2 回应**:**该 gap 无关键性** · 因为:

- rev1 实验 1 的目的**只是问 CPython trace 语义本身有没有不对称**(H1)· 不是完整复刻 pydevd。既然 raw sys.settrace 场景三 anchor 齐整落 return · CPython 层就没有不对称 · H1 排除 · 后续 pydevd 层的复杂性都建立在同一 CPython 语义之上。
- **实验 2**(真 pydevd 1.4.0 mock IDE)已经把 pydevd 的 additional_info / cache_skips 等中间层引入 · rev1 PHASE 2 已 warm-up cache_skips · 结果仍无不对称 · pydevd core dispatch 层无 drift 已经实证。
- **实验 5**(rev2 新增)进一步在真 pydevd 上跑 M1 stop_at_frame · pydev_step_cmd/pydev_step_stop 状态机全部记录 · 与 pydevd_v2 rev4 源码推理逐字对齐 · **相当于给了 additional_info 状态机的实证覆盖**。

**结论**:实验 1 是 H1 反证(CPython trace 语义本身无不对称)· 不承担 "复刻 pydevd 完整语义" 的义务 · gap 无关键性。实验 2 + 5 联合覆盖 pydevd 状态机层。

### Gap 2(预挑实验 2):真 pydevd + monkey-patch mock IDE 与真 PyCharm 行为差异

**skeptic 预挑理由**:mock 的 `do_wait_suspend` 只 "记录 + 立即释放" · 真 PyCharm Java 侧对 pause 消息可能有:
- Java 侧 "Just My Code" filter(不在 pydevd Python 层生效)
- return-event UX 转 caller frame(IDE 客户端自动 step)
- Frame filter / "Skip files" 用户配置
- mock 不发 `thread_suspend` XML 消息到 IDE · 完全没测 IDE 收到消息后的处理

**rev2 承认**:**这条 gap 是真 gap · 无法 close** —— agent 环境无法启 PyCharm · 无法测 IDE Java 侧对 pause 消息的处理。

**rev2 澄清 gap 的范围**:该 gap 只影响 "drift 的具体触发规则是什么" 的**因果链末端** · **不影响 rev1/rev2 的核心结论**(pydevd Python 层无 drift)。

- 实验 2 的结论是 "pydevd 传给 do_wait_suspend 的 frame = debug_break" · 这个结论是可靠的(mock 就是拦截 do_wait_suspend 拿到 frame)
- IDE 收到该 frame 后如何处理 → **需要用户在真 PyCharm 现场用真 tb debug 一次实证** · 这与 M1 landing 硬前置的判据是**同一件事**(final_report §Landing 硬前置)
- **实验 6 补上一个负面证据**:in_project_scope 层不足以解释 drift · 也就是说 "drift 不在 pydevd Python 层可控范围内"

**结论**:gap 承认 · 但对 team 结论无冲击。M1 的 landing 判据本就把 IDE 侧行为留给用户实测 · 该 gap 与 landing 硬前置是同一件事 · 已入 final_report。

### Gap 3(预挑实验 3):bytecode 只测 2 variants 是否覆盖 4 return 变体

**skeptic 预挑理由**:实验 3 rev1 只测 L163(3 层嵌套 if)与 L219(1 层 if)· 未覆盖 rise L219 / timeout L224 / entry L250 / gate L104 四个真实 return 现场 · 且是复刻不是原文件 · co_lnotab 优化在真文件上是否成立未测。

**rev2 补实验 4**(直接 dis path2/atoms/throwback.py 原生 code object):

| 现场埋点 | 后续 RETURN_VALUE line | co_lines 是否含独立归属 | 结论 |
|---|---|---|---|
| L104 gate | L105+(经 on_gate 多行 · 隐式 return) | ✓ 全部有 | 无合并 |
| L163 trough | L167 RETURN_VALUE line=167 | ✓ 独立 | 无合并 |
| L219 end rise | L220 RETURN_VALUE line=220 | ✓ 独立 | 无合并 |
| L224 end timeout | L225 RETURN_VALUE line=225 | ✓ 独立 | 无合并 |
| L250 entry | L251 line=251(下一 line change) | ✓ 独立 | 无合并 |

外加 3 处 None return(L151 phase1_break / L177 phase1_pullback_shortage / L185 phase1_no_trough_timeout / L217 phase2_break / L252/L255/L261/L266 evaluate_throwback 内 None return / L267 ThrowbackResult return)· 全部有独立 line 归属。

**实验 4 关键证据**(dis 每 debug_break 后续指令的 line change · 摘 4 变体):
```
L104 gate    debug_break(...) → +26 PUSH_NULL line=105       ← LINE CHANGE 104→105 ✓
L163 trough  debug_break(...) → +26 LOAD_GLOBAL print line=164 ← LINE CHANGE 163→164 ✓
L219 end     debug_break(...) → +32 LOAD_FAST i line=220     ← LINE CHANGE 219→220 ✓
L224 timeout debug_break(...) → +26 LOAD_FAST end_scan line=225 ← LINE CHANGE 224→225 ✓
L250 entry   debug_break(...) → +26 LOAD_FAST bo_idx line=251 ← LINE CHANGE 250→251 ✓
```

每处 debug_break() 调用后 · 下一条指令的 line 都严格 +1 · CPython 3.12 co_lines 层零合并。

**结论**:**H3 在全 4 return 变体上全线证伪** · 且是**用真文件直 dis · 非复刻**。M1 若 fail 不可能是 H3。

**脚本**:`/tmp/claude-1000/-home-yu-.../scratchpad/exp4_real_bytecode_audit.py`

---

## 实验 5 · 独立复核 pydevd_v2 rev4 "M1 反抗机制"(pydevd 层间接证据)

**pydevd_v2 rev4 claim**:`stop_at_frame=sys._getframe(1)` 让 settrace 走 CMD_STEP_OVER 分支 · `pydev_step_stop = caller frame` · 结果 pause 时 pydevd 传给 `do_wait_suspend` 的 frame 是 caller(非 debug_break)· IDE 看不到 debug_ctx.py 就无 skip 触发条件。

**rev2 独立复核方案**:扩展 rev1 实验 2 的 mock pydevd harness · 加两条 debug_break 版本(M0 无 stop_at_frame / M1 传 sys._getframe(1))· 拦截 do_wait_suspend 记录 (frame_func / frame_line / event / pydev_step_cmd / pydev_step_stop_func) · 三 anchor 并跑对照。

**实验 5 决定性结果**(节录 · 完整见脚本输出):

```
############ M0 · settrace(suspend=True) 无 stop_at_frame ############
=== M0 · ENTRY  bo_idx=0 ===
  [1] frame=exp5.py:81 func=debug_break_M0() event=return
       pydev_step_cmd=107 pydev_step_stop_func=None
=== M0 · TROUGH _find_start_idx(6,5) ===
  [1] frame=exp5.py:81 func=debug_break_M0() event=return
       pydev_step_cmd=107 pydev_step_stop_func=None
=== M0 · END    _find_end_idx(5,6) ===
  [1] frame=exp5.py:81 func=debug_break_M0() event=return
       pydev_step_cmd=107 pydev_step_stop_func=None

############ M1 · settrace(suspend=True, stop_at_frame=sys._getframe(1)) ############
=== M1 · ENTRY  bo_idx=0 ===
  [1] frame=exp5.py:114 func=evaluate_throwback() event=line
       pydev_step_cmd=108 pydev_step_stop_func=evaluate_throwback
=== M1 · TROUGH _find_start_idx(6,5) ===
  [1] frame=exp5.py:102 func=_find_start_idx() event=line
       pydev_step_cmd=108 pydev_step_stop_func=_find_start_idx
=== M1 · END    _find_end_idx(5,6) ===
  [1] frame=exp5.py:109 func=_find_end_idx() event=line
       pydev_step_cmd=108 pydev_step_stop_func=_find_end_idx
```

**证据映射到 rev4 claim**:

| pydevd_v2 rev4 claim | 实验 5 证据 | 结论 |
|---|---|---|
| stop_at_frame 走 CMD_STEP_OVER 分支 | pydev_step_cmd=108(= CMD_STEP_OVER · pydevd_comm_constants.py) | ✓ 直接证实 |
| pydev_step_stop = caller frame | pydev_step_stop_func = caller 函数名(evaluate_throwback / _find_start_idx / _find_end_idx)· 与 sys._getframe(1) 语义一致 | ✓ 直接证实 |
| do_wait_suspend 传给 IDE 的 frame 是 caller(非 debug_break) | frame_func = caller 函数名 · 三 anchor 全对齐 · **不再是 debug_break_M1** | ✓ 直接证实 |
| pause 时 event 类型变化 | M0 event=return · M1 event=line · 走 pydevd_frame.py L890-892 line 分支 · 不走 L920-923 back trick | ✓ 直接证实 |

**M0 与 M1 pause frame 差异的源码级机制**(rev2 独立追):

- **M0 路径**:CMD_SET_BREAK · info.pydev_state=STATE_SUSPEND · 触发 pydevd_frame.py L754 STATE_SUSPEND 分支 → `self.do_wait_suspend(thread, frame, event, arg)` 直接传当前 frame(= debug_break)· 无 back trick。
- **M1 路径**:CMD_STEP_OVER · info.pydev_state=STATE_RUN · debug_break return 事件时 `stop_frame is frame` = (caller is debug_break) = False → 不 stop · 执行流回到 caller · caller line event 时 `stop_frame is frame` = True + is_line = True → L890-892 line 分支 · `self.do_wait_suspend(thread, frame, event, arg)` 传当前 frame(= caller)。

**pydevd 层结论**:pydevd_v2 rev4 的 M1 反抗机制在 pydevd Python 层**完全实证** · 与源码 dispatch 逻辑逐字一致。**唯一仍是纸面的一环** = "IDE 侧 Java 收到 caller frame 后是否真不 skip" · 该环 team 无法证明 · 需用户 PyCharm 现场实测 confirm(与 M1 landing 硬前置判据 1-5 是同一件事)。

**脚本**:`/tmp/claude-1000/-home-yu-.../scratchpad/exp5_stop_at_frame.py`

---

## 实验 6 · in_project_scope 对 debug_ctx.py / throwback.py 的判定(负面证据)

**动机**:CMD_STEP_OVER return-event 分支(pydevd_frame.py L847):
```python
stop = frame.f_back and main_debugger.in_project_scope(frame.f_back.f_code.co_filename)
```
若 debug_ctx.py 被 in_project_scope 判 False · pydevd Python 层就有直接 auto-step 到 caller 的分支 · drift 就有 pydevd 层机制解释。**实验 6 检验这一可能**。

**结果**:
```
### PHASE A · 无 IDE_PROJECT_ROOTS(agent 默认) ###
  in_project=True   debug_ctx.py
  in_project=True   throwback.py
  in_project=True   pydevd.py
  in_project=False  pandas/__init__.py

### PHASE B · 模拟 PyCharm IDE_PROJECT_ROOTS=项目根 ###
  in_project=True   debug_ctx.py
  in_project=True   throwback.py
  in_project=False  pydevd.py
  in_project=False  pandas/__init__.py
```

**结论**:两个文件在 agent 默认与真 PyCharm 场景下 in_project_scope 都判 True · **pydevd Python 层的 in_project_scope 不会因文件类型区分 debug_ctx.py 与 throwback.py** · 也就无法在 pydevd 层解释 "M0 pause 落 debug_break return 后为何漂到 _find_end_idx 而非停在 _find_start_idx L164" 的不对称。

**drift 的过滤规则必然在 PyCharm Java 侧**(pydevd Python 层无法拿到该配置):
- IDEA 平台的 "Skip files" 用户配置(Settings → Build, Execution, Deployment → Debugger → Stepping)
- "Just My Code" filter(Java 侧独立于 pydevd Python 层)
- return-event UX 自动 step 到 caller frame(IDEA 平台侧行为 · 与 debug_ctx.py 内容无关)

**实验 6 补 team 结论的完整性**:final_report 说 "drift 100% 发生在 PyCharm IDE 客户端(Java 侧)" · 实验 6 是这条结论的**负面证据**(pydevd Python 层 in_project_scope 层无该不对称)。

**脚本**:`/tmp/claude-1000/-home-yu-.../scratchpad/exp6_in_project_scope.py`

---

## sys.monitoring / PEP 669 排除结论强化(rev1 表述修正)

**rev1 表述**(cpython_expert.md §"为什么 PEP 669 不能修 drift"):
> pydevd 的 pause 语义和 do_wait_suspend 消息组装逻辑在两条路径下**完全一致**;差异只在"什么时候 fire 事件"和"每 event 的开销"

**rev2 修正**:该表述**不精确** · 通过独立读 pydevd 1.4.0 `_pydevd_bundle/pydevd_pep_669_tracing.py` 发现:

### PEP 669 路径的 STATE_SUSPEND 分支只在 py_line_callback

- **`py_line_callback` L758-760**:检查 `info.pydev_state == STATE_SUSPEND` → `do_wait_suspend(thread, frame, 'line', None)`(当前 frame · line 事件)
- **`py_return_callback` L946-1026**:**没有 STATE_SUSPEND 分支** · 只在 step_cmd 分支(CMD_STEP_INTO / CMD_STEP_OVER / CMD_STEP_RETURN)才可能 stop · 且 stop 时 `do_wait_suspend(thread, back, 'return', retval)` **无条件传 back frame**(L1024-1026)

**对比 sys.settrace 路径**:
- **pydevd_frame.py L754-755**:STATE_SUSPEND 检查在**所有 event**(call/line/return)· 触发时 `do_wait_suspend(thread, frame, event, arg)` 直接传当前 frame
- **pydevd_frame.py L890-923**:step_cmd 分支下 · is_line 传当前 frame(L892)· is_return 传 back frame(L923)

### 差异表(rev2 补)

| 场景 | sys.settrace M0 | PEP 669 M0 |
|---|---|---|
| debug_break return 事件 STATE_SUSPEND | ✓ L754 触发 · pass frame=debug_break · event=return | ✗ py_return_callback 无 STATE_SUSPEND 分支 · 不 fire |
| caller line event STATE_SUSPEND | ✓ L754 触发 · pass frame=caller · event=line | ✓ L758 触发 · pass frame=caller · event=line |
| **首个到达 IDE 的 pause frame** | debug_break(先 fire · 抢先) | **caller**(唯一 fire · 无抢先) |

**推论**:**PEP 669 M0 的 pause frame 会自然落在 caller · 而非 debug_break** · 这与 M1 的效果相似(pause frame = caller · 不给 IDE 触发 skip 的机会)。理论上 PEP 669 单飞就可能修 drift。

### 为什么 rev2 仍保留 sys.monitoring 排除结论

**排除理由从 rev1 的 "语义完全一致" 换成 rev2 的三条**:

1. **默认关**:USE_LOW_IMPACT_MONITORING=False · 现场用户未 opt-in · 换 PEP 669 需要额外配置成本
2. **IDE 侧行为未测**:即使 pause frame = caller(理论上避开 skip)· 真 PyCharm 收到 PY_RETURN 事件的 caller frame 是否会有其他 UX 处理 · 未实测 · 与 M1 landing 硬前置同一 blocker
3. **与 M1 无优势**:M1(stop_at_frame)在 sys.settrace 路径也能让 pause frame = caller · 无需切 PEP 669 · 兼容更广(所有 pydevd 版本 · 不限 Python 3.12+)· 侵入面 1 行

**skeptic_v2 若挑 "未来 pydevd 版本 opt-in 后行为可能变"**:rev2 回应 "会变" · PEP 669 M0 pause frame = caller 是**利好而非阻碍**(用户未来 opt-in 后 · drift 可能自然消失 · M1 就自动退成冗余而非有害)。但 rev2 仍不推荐现在切 PEP 669 · 理由是**M1 + PEP 669 未来 opt-in 是可并存的**:

- M1 只依赖 `stop_at_frame` 参数 · pydevd_pep_669_tracing.py 的 `_locked_settrace` 分支同样处理该参数(pydevd_v2 rev4 已证)
- 用户未来 opt-in USE_LOW_IMPACT_MONITORING=1 后 · M1 依然工作 · 不需回退

**结论**:**排除 sys.monitoring 单飞方案** · 但 rev2 承认 rev1 "语义完全一致" 是过判 · 修正为 "PEP 669 M0 pause frame 与 sys.settrace M0 不同但和 M1 效果相近 · 无需现在切换"。

---

## 送 skeptic_v2 review 的 3 个点

1. **实验 5 是否 close 了 pydevd_v2 rev4 "M1 反抗机制" 的纸面推理**:mock 拦截 do_wait_suspend 拿到的 frame 变化足以证明 pydevd 层机制 · 但 "IDE 收到 caller frame 后不 skip" 仍是纸面 · 是否可接受
2. **实验 6 的 in_project_scope 判定**:是否补足了 final_report "drift 100% 在 IDE Java 侧" 结论的负面证据
3. **sys.monitoring 修正表述**(PEP 669 M0 pause frame ≠ sys.settrace M0):skeptic_v2 是否认可 "PEP 669 与 M1 可并存 · 排除理由从'语义一致'改为'无优势 + 需 opt-in'"

## 送 pydevd_v2 review 的 2 个点

1. **实验 5 结果与你 rev4 M1 机制描述是否逐字对齐**:请核 CMD_STEP_OVER=108 · pydev_step_stop_func = caller · event=line 三项与你源码引用是否有偏差
2. **PEP 669 差异表**(rev2 §sys.monitoring 章节)是否需并入 pydevd_expert.md rev4 · 或作为独立 note

## 未 close 的真空(留给用户实测)

- **IDE 侧 Java 收到 caller frame 是否真不 skip**:唯一硬 gating · agent 无法测 · 与 M1 landing 硬前置判据 1-5 同一件事
- **VSCode/Cursor debugpy 行为**:pydevd_expert rev3 已标 unverified · 用户切 VSCode 前必须 revalidate(rev2 无补充)

---

# rev3 · 逐条回应 skeptic_v2 6 点挑战(1a/1b/2a/2b/2c/3)

**状态**:rev3(本节 append · 不覆盖 rev1/rev2)
**触发**:skeptic_v2 rev2 SendMessage 给我 6 点具体挑战 + 实验 5 边界补声明 + 实验 3 gate CALL_FUNCTION 特别关注

## rev3 结论摘要

- **1a valid**:自实现 tracer 未 walk f_back · 但**对本实验无影响**(rev3 独立追:sys.settrace 全局 tracer 对 settrace **之后创建的 frame** 生效 · 实验 1 detector 链是 settrace 之后创建的 · f_back walk 只影响 settrace 前已在栈上的 caller 框架 · 与 detector 无关)· rev3 补论证 · 保留实验 1 结论
- **1b valid**:rev2 已明标 · rev3 再确认 —— 实验 1 只覆盖 CPython trace 语义本身 · 不覆盖 pydevd 挂 f_trace 层(但实验 2 + 实验 5 联合覆盖该层)
- **2a acknowledged then invalid**:承认 rev1 warm-up 只跑 evaluate_throwback(0) 是 gap · rev3 补实验 7 PHASE A 让 fs/fe/ev 三个 code object 各自 fire debug_break 让 cache 真填满 · **主测结果:pause 位置零变化** · TROUGH/END/整链 都齐整落 debug_break():87 event=return · pydev_step_cmd_before=107(CMD_SET_BREAK)· **warm-up 完整性 gap 不影响 rev1/rev2 主结论**
- **2b acknowledged then invalid**:承认 rev1 mock IDE 只 continue 是 gap · rev3 补实验 7 PHASE B 主动 flip pydev_step_cmd = CMD_STEP_OVER 模拟 IDE 回发 step_over · **主测结果:pause 位置零变化** · B2/B3/B4 三场景都齐整落 debug_break event=return · **即使 pydev_step_cmd 残留 108(CMD_STEP_OVER),下次 settrace 会覆盖 · pydevd 层无 drift**
- **2c valid**:rev3 明写 pydevd 侧观察 vs IDE 侧观察的边界声明(见 §边界声明)· 收窄 rev1 表述 "drift 100% 在 IDE Java 侧" 为 "**drift 排除 pydevd Python 层 + CPython trace 层 + bytecode 层 · 剩余唯一可能层 = PyCharm IDE Java 侧**"(负面证据充分 · 但 100% 定位仍需用户现场实测 confirm)
- **3 valid**:rev2 实验 4 已覆盖全 5 处埋点(含 L104 gate 的 CALL_FUNCTION → on_gate)· 每处 debug_break 后下一条指令都有独立 line change(104→105 / 163→164 / 219→220 / 224→225 / 250→251)· rev3 补 gate 变体特别观察 —— CALL_FUNCTION 与 RETURN_VALUE 在 CPython 3.12 line event 层**无语义差异**(都 fire 独立 line event)· gate 若在 M0 下也漂 · 也是 IDE 侧问题

## 边界声明(挑战 2c · rev1/rev2 表述收窄)

**rev1 §"由三份实验倒推"最后一句原文**:
> 剩下唯一嫌疑 = PyCharm IDE 客户端(Java 侧)对 pydevd 发过来的 `thread_suspend` 消息的二次处理

**rev3 收窄表述**:
> **三层实验(sys.settrace / real pydevd / bytecode)+ 实验 4/5/6/7 联合排除 CPython trace 层 + pydevd Python 层 + bytecode 层 + warm-up cache_skips + IDE 主动回发 CMD_STEP_OVER · drift 的剩余可能层收窄到 PyCharm IDE Java 侧对 pause 消息的二次处理。**"100% 在 IDE Java 侧" 需用户现场实测 confirm(即 M1 landing 硬前置判据 · 通过则 100% · 未通过留剩余排查空间)。

**pydevd 侧观察 vs IDE 侧观察分界**(rev3 明列):

| 观察层 | agent 可测 | 现状 | drift 排除 |
|---|---|---|---|
| CPython trace 语义(H1) | ✓ 实验 1 | 三 anchor 齐整无 drift | ✓ 排除 |
| pydevd core dispatch(H2 cache_skips) | ✓ 实验 2 rev1 + 实验 7 PHASE A rev3 | warm-up 全覆盖后仍无 drift | ✓ 排除 |
| pydevd IDE 命令回发响应(H2 rev2 补) | ✓ 实验 7 PHASE B rev3 | 主动 flip CMD_STEP_OVER 仍无 drift | ✓ 排除 |
| bytecode line attribution(H3) | ✓ 实验 3 + 实验 4 | 全 5 埋点后 return / CALL_FUNCTION 都有独立 line | ✓ 排除 |
| pydevd in_project_scope | ✓ 实验 6 | debug_ctx.py + throwback.py 都 True · pydevd 层不区分 | ✓ 排除 |
| PyCharm IDE Java 侧 skip files / step filter / auto-step | ✗ agent 无法启 PyCharm | 未测 | **剩余可能层** |

**结论**:pydevd 层所有可疑分支已排除 · IDE Java 侧是剩余唯一可能层 · **但 100% 定位仍需用户现场实测 confirm**(landing 硬前置)。

---

## 逐条回应(6 点)

### 挑战 1a · 自实现 tracer 是否 walk f_back?

**回应**:**valid but 无影响**。

- **事实**:pause_asymmetry.py 的 self-tracer:
  ```python
  frame = sys._getframe()
  frame.f_trace = _tracer         # 只挂当前 frame
  sys.settrace(_tracer)           # 全局 tracer(对 settrace 之后创建的 frame 生效)
  ```
  **无 walk f_back 挂父 frame**。
- **pydevd 的 `set_trace_for_frame_and_parents`** 为什么 walk f_back:因为 pydevd 常在 program 已经跑到深处才被 attach · 需要给已在栈上的 caller 也挂 f_trace 才能捕获它们的 line event
- **本实验为何不需要**:实验 1 的 detector 调用链(`evaluate_throwback` → `_find_start_idx` / `_find_end_idx` / `debug_break`)全部是 settrace 之后创建的新 frame · `sys.settrace` 全局 tracer 对这些新 frame 自动生效(每个新 frame 创建时自动继承 f_trace = 全局 tracer)· f_back walk 只影响 settrace 前已在栈的 caller(main / run_scenario_direct)· 那些 frame 无 debug_break 调用 · 与实验主结论无关

**结论**:**gap 承认但无影响**。若挑 "复刻 fidelity 有 gap"· 修正表述见 1b。

### 挑战 1b · 实验 1 边界明标

**回应**:**valid · rev2 已明标**。

rev2 §"Gap 1"已写:"实验 1 是 H1 反证(CPython trace 语义本身无不对称) · **不承担 '复刻 pydevd 完整语义' 的义务** · gap 无关键性。实验 2 + 5 联合覆盖 pydevd 状态机层"。rev3 再确认。

### 挑战 2a · warm-up 完整性

**回应**:**acknowledged 是真 gap · 补实验 7 PHASE A 验证后 invalid(gap 不影响主结论)**。

- **rev1 warm-up 现场**(`pause_pydevd_real.py:162`):`evaluate_throwback(0)` · 因 `bo_idx<1 → return None` · **只 fire ENTRY 一次** · fs/fe 从未被调用 · cache_skips **不包含** `_find_start_idx` / `_find_end_idx` code object · **skeptic 挑战 2a 是真 gap**
- **rev3 补实验 7 PHASE A**:分别调 fs(6, 5) 和 fe(5, 6) 让三个 code object 各自 fire 一次 debug_break · trace_dispatch 各走一遍 · cache_skips 覆盖三个 code object
- **主测结果**:

```
★ PHASE A 主测:cache_skips 覆盖三个 code object 后
  TROUGH   pause 落 debug_break_M0():87 event=return pydev_step_cmd_before=107
  END      pause 落 debug_break_M0():87 event=return pydev_step_cmd_before=107
  整链     pause 三次全部落 debug_break_M0():87 event=return
```

**pause 位置零变化** · 与 rev1 实验 2 PHASE 2 结论一致。**warm-up 完整性 gap 承认 · 但补实验后证明不影响主结论**。

### 挑战 2b · mock IDE 回发命令

**回应**:**acknowledged 是真 gap · 补实验 7 PHASE B 验证后 invalid**。

- **rev1 mock 现场**(`_mock_do_wait_suspend`):`info.pydev_step_cmd = -1` · IDE 只发 continue · 不发 step_over。skeptic 挑 "真 IDE 若因 skip files 规则回发 CMD_STEP_OVER · pydevd 下一 line event 会 walk 到 caller · pause 漂到 _find_end_idx:200" —— **rev3 补 mock 主动 flip pydev_step_cmd = CMD_STEP_OVER + pydev_step_stop = frame 模拟 IDE 回发 step_over**
- **rev3 实验 7 PHASE B 主测结果**:

```
[B1 continue] TROUGH pause=debug_break event=return pydev_step_cmd_before=107(CMD_SET_BREAK)
[B2 step_over TROUGH] pause=debug_break event=return pydev_step_cmd_before=107
[B3 step_over END]    pause=debug_break event=return pydev_step_cmd_before=108(CMD_STEP_OVER)
[B4 step_over 整链]   三次全部 pause=debug_break event=return pydev_step_cmd_before=108
```

**关键观察**:
- 即使 pydev_step_cmd 残留为 CMD_STEP_OVER(B3/B4 pydev_step_cmd_before=108) · **pause 位置依然精确落 debug_break event=return · 没漂到 caller · 没漂到 _find_end_idx**
- **原因**:下次 debug_break 调 `pydevd.settrace(suspend=True)` 时 · `_locked_settrace` 覆盖 `pydev_step_cmd = CMD_SET_BREAK`(无 stop_at_frame 分支)· 上一轮的 CMD_STEP_OVER 状态被重置 · pydevd 层无残留污染
- **skeptic 挑战 2b 假设的 "IDE 回发 CMD_STEP_OVER → pause 漂到 _find_end_idx"** · 在 pydevd 层**不复现**

**结论**:pydevd 层对 IDE 回发命令的响应不导致 drift · **drift 只能在 IDE Java 侧的其他机制(非 pydevd 命令回发)**。

**注意 mock 简化点**:mock 里 stop_frame=frame(debug_break)· 但 frame 已 return · 若真 IDE 回发 step_over 时把 stop_frame 设为 caller 而非 debug_break · 行为可能不同。**rev3 承认此 mock 简化 · 但本次实验的主结论(pydevd 层不因 pydev_step_cmd 残留而漂)仍成立**。要严格测 "IDE 精确设 stop_frame=某个 frame 后 pause 落哪" · 只能用户 PyCharm 现场实测。

### 挑战 2c · pydevd 侧 vs IDE 侧观察边界

**回应**:**valid · rev3 补边界声明**(见 §"边界声明" 章节 · 明表列出各层观察 · 收窄 "100% 在 IDE Java 侧" 表述为 "pydevd 层排除 · IDE Java 侧是剩余唯一可能层 · 100% 定位需用户实测")。

### 挑战 3 · 实验 3 覆盖不全(gate CALL_FUNCTION)

**回应**:**valid · rev2 实验 4 已补齐 5/5 · rev3 补 gate 变体特别关注**。

**rev2 实验 4 已覆盖 5 处埋点**(直 dis 真文件):

| 埋点 | debug_break 后下一条指令 | line event | 结构类型 |
|---|---|---|---|
| L104 gate | `+26 PUSH_NULL line=105` | 104→105 ✓ | CALL_FUNCTION (on_gate) |
| L163 trough | `+26 LOAD_GLOBAL print line=164` | 163→164 ✓ | CALL_FUNCTION (print) + return |
| L219 end rise | `+32 LOAD_FAST i line=220` | 219→220 ✓ | RETURN_VALUE |
| L224 end timeout | `+26 LOAD_FAST end_scan line=225` | 224→225 ✓ | RETURN_VALUE |
| L250 entry | `+26 LOAD_FAST bo_idx line=251` | 250→251 ✓ | IF-COMPARE |

**rev3 特别关注 gate CALL_FUNCTION 变体**:
- L104 debug_break 后紧跟 `on_gate(GateFailure(...))` = CALL_FUNCTION(不是 RETURN_VALUE)
- L105 有独立 line change · 与 RETURN 变体的 line event fire 行为**无差异**
- CPython 3.12 co_lines 层不区分 return 与 CALL_FUNCTION · 都精确 attribute 到源码行
- **结论**:若 gate 埋点在 M0 下也漂(用户未报告 · 但假设存在)· 也是 IDE 侧问题 · 与 return 变体一致

**结论**:gate 变体特别关注 close · 与 skeptic 一致 —— "若 gate 在 M0 下也漂 · 是重要证据"。用户现场若观察到 gate 漂 · 请回报 team 补测。

---

## 送 skeptic_v2 rev3 review 的 3 个点

1. **实验 7 PHASE A/B 结果**(warm-up 全覆盖 + IDE 主动回发 CMD_STEP_OVER 都不复现 drift):是否 close 挑战 2a/2b 或还有 mock 简化的其他 gap 需补
2. **边界声明**(§边界声明章节 · 收窄 "100% 在 IDE Java 侧" 为 "pydevd 层排除 · IDE Java 侧剩余唯一 · 100% 需用户实测"):是否满足挑战 2c 要求
3. **gate CALL_FUNCTION 变体特别关注**(实验 4 结果 · rev3 §挑战 3):是否 close 或需更深 bytecode 分析

## 送 pydevd_v2 review 的 1 个点

- **实验 7 PHASE B 结论**(即使 pydev_step_cmd 残留 CMD_STEP_OVER=108 · 下次 settrace 覆盖为 CMD_SET_BREAK · pydevd 层无残留污染):与你 rev4 §"反复 fire" 契约论证是否一致 · 请核

## 未 close 的真空(rev3 收窄)

- **IDE Java 侧 skip files / step filter / auto-step / Just My Code 具体机制**:唯一未测层 · agent 无法启 PyCharm
- **mock 简化点**:PHASE B 的 stop_frame=frame(debug_break)与真 IDE 精确设 stop_frame 的行为可能不同 · 但主结论(pydevd 层不因 pydev_step_cmd 残留而漂)不变
- **VSCode/Cursor debugpy 行为**:pydevd_expert rev3 已标 unverified

## 修订历史

- rev3(本节 append · 2026-07-17):逐条回应 skeptic_v2 6 点挑战(1a/1b/2a/2b/2c/3)· 补实验 7(warm-up 全覆盖 + IDE 回发 CMD_STEP_OVER)+ 边界声明 + gate 变体特别关注 · rev3 主结论:skeptic 挑战全部 acknowledged · 补实验后 2a/2b 证明 gap 不影响 rev1/rev2 主结论 · 2c 补边界声明收窄表述 · 1a/1b/3 已被 rev2 覆盖 rev3 再确认

---

# rev3 追加 · mini 实验 · 坐实 M0 走 L754 SUSPEND early-return · M1 走 L892 line 分支

**动机**:pydevd_v2 rev4 §5.1/§5.3 请求追加一个坐实实验 · 证 "M0 走 L754 STATE_SUSPEND early-return · 不走 L893-923 return→caller 转换"。

**方法**(pause_m0_early_return.py · 简化避免嵌套 sys.settrace 卡死):
- Mock IDE 拦 do_wait_suspend · 内部用 `sys._getframe(2)` 跳过 PyDBFrame.do_wait_suspend wrapper(L411-412)· 直接拿 pydevd_frame.py 内 do_wait_suspend 真调用点的 line 号
- L754/L755 = STATE_SUSPEND early-return 分支;L892 = CMD_STEP_INTO/CMD_STEP_OVER line 分支;L923 = return→caller 分支

**结果**(截录 · 完整脚本 `/tmp/claude-1000/.../scratchpad/pause_m0_early_return.py`):

```
### M0 · settrace(suspend=True) ###
  [1] user frame: pause_m0_early_return.py:79 in debug_break_M0()  event=return
       state=2  step_cmd=107 (CMD_SET_BREAK)
       ★ do_wait_suspend called from: pydevd_frame.py:755 in trace_dispatch()   ← L754/755 SUSPEND early-return ✓

### M1 · settrace(suspend=True, stop_at_frame=caller) ###
  [1] user frame: pause_m0_early_return.py:109 in _find_start_idx_M1()  event=line
       state=2  step_cmd=108 (CMD_STEP_OVER)
       ★ do_wait_suspend called from: pydevd_frame.py:892 in trace_dispatch()   ← L892 line 分支 ✓
```

**关键论断**(全部直接实证):

| pydevd_v2 rev4 claim | 实证 |
|---|---|
| M0 走 L754 STATE_SUSPEND early-return | ✓ do_wait_suspend called from pydevd_frame.py:**755** |
| M0 pause frame = 当前 frame(debug_break)· event=return · 无 back trick | ✓ user frame=debug_break_M0 · event=return |
| M0 抢先 return · 绕过 L893-923 转换 | ✓ 未见 do_wait_suspend called from L893-923(若走过 · caller_line 应在 L890 之后) |
| M1 走 L892 stepping line 分支 | ✓ do_wait_suspend called from pydevd_frame.py:**892** |
| M1 pause frame = caller frame · event=line | ✓ user frame=_find_start_idx_M1 · event=line |

**这坐实**:pydevd_v2 rev4 §5.1/§5.3 的源码级机制推理**逐字与运行时行为对齐** · 无纸面残留(除仍未测的 IDE Java 侧 skip 行为 · 与 M1 landing 硬前置判据是同一件事)。

**给 pydevd_v2**:这个数据可直接引用作 rev5 § "M0 抢先 return · L893-923 未命中" 的运行时硬证据 · 无需你再跑。

- rev3 追加 · mini 实验(2026-07-17):M0 do_wait_suspend caller_line=755(L754/755 SUSPEND early-return) · M1 caller_line=892(CMD_STEP_OVER line 分支) · 直接实证 pydevd_v2 rev4 §5.1/§5.3 论证 · 无纸面残留

---

## rev3 勘误 · CMD_SET_BREAK vs CMD_STEP_INTO 混淆(2026-07-17 · 承 pydevd_v2 rev4 §5.3 常量对齐)

**背景**:pydevd_v2 rev4 §5.3 证据 4 提 "CMD_SET_BREAK = 111" · 我 rev2 §实验 5 表述里把实测的 `pydev_step_cmd=107` 误标为 "CMD_SET_BREAK" · 导致 pydevd_v2 rev5 §6.5 "修正为 107" 的连锁误改。

**权威常量表** · grep `_pydevd_bundle/pydevd_comm_constants.py`:

```
CMD_STEP_INTO  = 107
CMD_STEP_OVER  = 108
CMD_STEP_RETURN = 109
CMD_SET_BREAK  = 111
```

**语义正解**:
- `pydevd.settrace(suspend=True)` 内部调 `set_suspend(t, CMD_SET_BREAK)`(pydevd.py:1976)· **CMD_SET_BREAK=111** 作 `stop_reason` 传入 · 存到 `thread.stop_reason`
- `_mark_suspend` (pydevd.py L983-986) 若 `pydev_step_cmd == -1` 则 flip 到 **CMD_STEP_INTO=107** · 存到 `additional_info.pydev_step_cmd`
- **M0 场景两个字段共存**:`thread.stop_reason = 111`(CMD_SET_BREAK · 用户看到的 pause 原因)· `additional_info.pydev_step_cmd = 107`(CMD_STEP_INTO · 后续 stepping 路由)
- **M1 场景**:`_locked_settrace` L1968-1971 覆盖 `pydev_step_cmd = CMD_STEP_OVER = 108`(实验 5 实测值)

**rev2 §实验 5 表述勘误**(读者按此理解):
- 原表述:`M0 · step_cmd=107 (CMD_SET_BREAK)` 
- 正确表述:`M0 · pydev_step_cmd=107 (CMD_STEP_INTO · 由 _mark_suspend flip);thread.stop_reason=111 (CMD_SET_BREAK · 用户可见 pause 原因)`

**结论**:pydevd_v2 rev4 §5.3 证据 4 CMD_SET_BREAK=111 **正确 · 无需修** · rev5 §6.5 "修正为 107" **本身是误修 · 需回退**。final_report §过判撤销清单第 4 条也需一并 rev2.2 更正。

无实验数据受影响 · 仅文档表述层。三层实证(实验 5 · rev3 mini 实验 · pydevd_v2 rev4 §5.2)结论不变。

