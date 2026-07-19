# Skeptic · workaround 方案质疑稿

**角色**:pause_skeptic teammate(工程 skeptic · 独立判断在先 · 挑战 hunter 方案在后)
**状态**:rev0.5(2026-07-17 · 独立四块 + 现场事实锁定 · 待 hunter 出稿后 rev1)
**归档**:`docs/research/2026-07-17_pydevd-suspend-pause-position/skeptic.md`
**final_report.md**:由 lead 合成 · 我只出 skeptic.md

---

## 独立块 1 · 问题严重度审视(不看 hunter 结论 · 先形成自己判断)

### 现象成本量化

**每次 pause 用户实际动作**:
- 场景 A(正常 · 如 end/entry):IDE 面板已显示对应 caller frame 的 `depth` / `peak` / `trough_idx` 等局部量 → 直接看
- 场景 B(漂 · trough):pause 落在 `_find_end_idx:200` · 变量面板显示 `end_scan` / `base_min` 等下游量 · 想看 trough 相关 → **需手动点 stack 顶下面一层 `_find_start_idx` frame** → IDE 才切显示 phase1 局部量

单次成本:约 **1 次点击 · 亚秒级**。无信息丢失(stack 完整 · 变量面板可切)。

### workflow 频次

FV2 场景 J1/J2/J3 = **entry / trough / end 三条入口 marker 右键 debug**。三条中只有 trough(J2)漂。用户 debug 一支股票的一次 tb event · 大概各 debug 一到两次。tb 事件的调试也不是每支股票 · 是查异常时才用。

**保守估计**:一天 debug 使用 tb marker 5 次 · 其中 trough 占约 1/3 = 1-2 次 · 每次多 1 点击。**日成本 = 1-2 次点击**。

### 严重度定级

**独立判断**:P3(cosmetic annoyance),**不是** P1/P2 blocker。

理由:
1. 无功能丢失(所需变量都能看到 · 只是多 1 步导航)
2. 频次极低(每天 1-2 次点击)
3. 无正确性风险(pause 位置 ≠ 判据错误)
4. 有明确 stack 导航兜底(即使不修 · 用户 workflow 也能推进)

**但用户明确表达"失去快速定位意义"** —— 这是**用户偏好** vs **绝对痛度**的错位。skeptic 立场:**尊重用户偏好** · **但拒绝为满足此偏好接受高侵入面 workaround**。理由:兜底方案(pause on _find_end_idx + 点 stack)已经能让 workflow 跑,任何 workaround 引入的**新 bug 概率**(见独立块 3)必须小于 P3 才值得做。

### 与 hunter 稿的对齐点

hunter(pydevd_expert / cpython_expert)应各自表态:
- 他们估的严重度是什么(P1/P2/P3)?
- 是否有比"点 stack"更廉价的兜底路径 · 使得根本不需要 workaround?
- 如果 workaround 引入新故障模式(如 debug_break perf 降级、L216/L247 从"不漂"变"漂"),他们能否接受?

### 「问题 1 · 双 fire」重要度评审

顺带 lead 附文档提到问题 1(pause 触发两次)· 虽本次任务聚焦问题 2 pause 位置漂:

**独立判断**:问题 1 严重度 = P2(vs 问题 2 = P3)· 因为**用户主观感受 pause 两次是"bug 感"** > **pause 漂位置是"惯出来的错位"**。**问题 1 有既有干净修法(handler 里合并两 pass 或 debug 时短路 diag)· 问题 2 才是真难题**。

但 lead 分给我的任务是聚焦问题 2 · 故问题 1 只标记 · 不深挖。

---

## 独立块 2 · 独立 rank 已有方案候选(α/β/γ/δ)+ 提议新方案 ε/ζ

### 现场事实锁定(rev0.5 新增 · 独立查证)

**pydevd 现场版本**:
- 位置:`/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py`
- `__version__ = '1.4.0'`(L83:`__version_info__ = (1, 4, 0)`)
- Python 现场版本:3.12.12(现场 uv env)
- `uv pip show pydevd` = not found —— 现场 pydevd **不在 uv env** · 是 **PyCharm 启 debug 时 helpers 目录进 sys.path 提供**。**推论**:workaround 必须与 PyCharm 2026.1 helpers 版本 pydevd 1.4.0 兼容 · 不能假设 uv env 提供 pip installable 版本。

**settrace 公开签名**(pydevd.py L1810):
```python
def settrace(
    host=None, stdout_to_server=False, stderr_to_server=False,
    port=5678, suspend=True, trace_only_current_thread=False,
    overwrite_prev_trace=False, patch_multiprocessing=False,
    stop_at_frame=None,      # ← 关键:公开参数
):
```

**docstring 明写**(L1844):`stop_at_frame: if passed it'll stop at the given frame, otherwise it'll stop in the function which called this method.` —— 这是 **hunter 若提"改 debug_break 内部传 stop_at_frame=caller_frame"方案的直接 leverage**。

**set_next_statement API**(pydevd.py L1115):是 `PyDB` class 的**instance method**(不是模块级 function)· 语义 = "跳到指定行"(jump to line)· 用于 IDE 用户点 "set next statement" 时。**skeptic 直觉:能改 f_lineno 但会 mutate 已经在跑的 frame · 不该在 detector loop 里当 workaround 用**。

**sys.monitoring / PEP 669**(Python 3.12+ 新 API):现场 pydevd 已 wire · 有 `_pydevd_bundle/pydevd_pep_669_tracing.py` 和 `pydevd_pep_669_tracing_cython.pyx`。**推论**:pydevd 1.4.0 已迁到 PEP 669 · monitor events 由 pydevd 内部管理 · debug_break 侧直接调 sys.monitoring 会**与 pydevd 冲突**(两个 monitoring consumer 打架)· 除非用 pydevd 提供的 wrapper。

### rank 四个方案

从"用户拒绝"往回排 · 加上 skeptic 挑 gap 后的可行性判定:

| 方案 | 一句话 | Skeptic 独立判定 | 理由 |
|---|---|---|---|
| α · 加形式 executable line | L163 后补 assignment / print | ❌ **已实测证伪** | 现场 L164-166 已有 3 行(`print` / `_ = trough_idx + 0` / `_ = trough_idx`)· 依然漂。任何变体都必须解释为什么已 3 行仍无效 · 高度可疑无解 |
| β · 换 settrace 参数 | `settrace(suspend=True, stop_at_frame=sys._getframe(1))` | ⭐ **首选待验证** | 用公开参数 · docstring 明写 "stop at given frame" · 侵入面小(只改 debug_ctx.py 4 行)· 但需 hunter 实测确认 |
| γ · 改 debug_break 用 set_next_statement | `frame.f_lineno = target_line` | ⚠️ **可行但危险** | mutates running frame · 破坏 python 语义 · 破坏 stack trace · profiler 可能 crash · **不推荐**除非 β 证伪 |
| δ · Python 3.12 sys.monitoring | 用 PEP 669 API 替 settrace | ❌ **与现场 pydevd 冲突** | 现场 pydevd 已经是 monitoring 的 consumer · debug_break 再 register 一个 consumer 会打架 · 除非 pydevd 提供 wrapper(需查现场 pydevd 有无相关 helper) |

### 新方案候选(skeptic 提议)

**ε · 移埋点到 caller**(**极力推荐 · 侵入面 = 移 5 处 debug_break 位置 · 零动 pydevd**):

将 `_find_start_idx` 内 L163 的 `debug_break(trough_idx, anchor_kind='trough')` 移到 `evaluate_throwback` 内 return 后:

```python
# evaluate_throwback L257 后
start = _find_start_idx(...)
if start is None:
    return None
debug_break(start, anchor_kind='trough')   # ← 移这
end = _find_end_idx(...)
```

**优点**:
- pause 停在 evaluate_throwback frame · **直接** 看 `start` / `bo_idx` / `anchor` / `atr`(这些正是用户最需要的调试量)
- 零动 pydevd · 100% 兼容所有 IDE / Python 版本
- 反复 fire 语义不变
- 不引入 pydevd private API 依赖

**缺点**:
- 拿不到 `_find_start_idx` 内的 `depth` / `peak` / `trough_idx` 计算中间值 —— 但注意:**用户日常 debug 关心的是 `trough_idx` 是否合理 · 不是 depth/peak 中间值**;要看中间值仍可点 stack 进一层
- 5 处埋点位置从"贴判据"变成"贴 return" · 与"埋点靠近判据"的初衷有 tension

**skeptic 立场**:ε 是 P3 严重度下的最优 trade-off。当 β 未实测通过前 · ε 就是**当下就能用的最优方案**。

**ζ · 接受 + IDE 侧配置 caller frame 优先显示**:

如果 IDE(PyCharm)有 "debugger.pause.prefer.caller.frame" 类设置 · 让 IDE 侧默认展开 caller frame · 用户 pause 后看到的第一屏就是 caller variables。skeptic 未知 PyCharm 有无此设置 · 需 hunter/lead 查 IDE 文档。**若有 · 零成本兜底 · 应作为方案 C 的加强版**。

### rank 总排(独立结论 · 未看 hunter 稿)

```
1. ε  · 移埋点到 caller · 推荐首选(P3 严重度下最优 trade-off)
2. β  · settrace(stop_at_frame=...) · 推荐次选(需 hunter 实测)
3. ζ  · IDE 侧配置 · 应作为兜底探索(零成本)
4. C  · 接受 + 文档化 stack 导航 · 兜底(用户拒但事实上可用)
5. γ  · f_lineno 硬改 · 不推荐(危险)
6. δ  · sys.monitoring · 不推荐(与 pydevd 冲突)
7. α  · 加形式行 · 已实测证伪(不再考虑)
```

**hunter 若给出的方案落在 α/γ/δ · skeptic 会强烈质疑其可行性;若落在 β/ε · 用 6 维模板挑 gap 后可能通过。**

---

## 独立块 3 · 项目侵入面评估

### 5 处埋点现场

`throwback.py`:
- L104 · `_emit_tb_gate` 内 · anchor_kind='gate'
- L163 · `_find_start_idx` · anchor_kind='trough'(**漂**)
- L216(应为 L219)· `_find_end_idx` · anchor_kind='end' rise 分支
- L221(应为 L224)· `_find_end_idx` · anchor_kind='end' timeout 分支
- L247(应为 L250)· `evaluate_throwback` · anchor_kind='entry'

(tmp doc 里的行号偏移 · 我核对了当前 throwback.py · 上述括号内是当前实际行)

### 侵入面 · 逐方案

| 方案 | debug_ctx.py 改行 | throwback.py 改行 | 引入 new bug 面 |
|---|---|---|---|
| **β** stop_at_frame | +2 行(import sys + settrace 加参数) | 0 | 小 · 只碰 debug_break |
| **γ** f_lineno | +3-5 行 · 需 `frame.f_lineno = target` + PyDB 拿 handle | 0 | **大** · frame mutation 是黑魔法 · profiler 可能 crash · 未来 IDE debugger 升级也可能不兼容 |
| **δ** sys.monitoring | 需 register monitoring event handler + de-register · 20+ 行 | 0 | **极大** · 与现场 pydevd 抢 monitoring · 未验证冲突后果 |
| **ε** 移埋点 | 0 | 移 1 处(trough)· 若一致性要求也移其他 4 处 = 移 5 处 | 小 · 但要保证 event.start_idx / event.end_idx 数值不变(移埋点不改判据) |
| **ζ** IDE 配置 | 0 | 0 | 0(如存在) |
| **C** 接受 | 0 | 0 | 0 · 只加 docstring |

**独立结论**:ε 是**代码侵入最小 + bug 面最小**的方案。β 若实测通过 · 是**结构最优雅**的(埋点位置不用移 · workaround 隔离在 debug_ctx.py 一处)。

### 与 v3 契合度

v3 (commit c84bcbd rename `role`→`anchor_kind`)已经把 debug_break 参数改成 `anchor_kind` · 是**语义**层的东西。方案 β/γ/δ 都是**机制**层修改 · 与 v3 语义正交 · 无冲突。方案 ε 是**埋点位置**层 · 与 v3 语义无冲突 · 但会改动 v3 已 landing 的埋点物理位置 · 需要新 e2e checklist 一遍(FV2 场景 J1/J2/J3 判据要 revalidate)。

---

## 独立块 4 · v4 兼容性评审

v4 spec:`docs/research/2026-07-16_path2-web-event-class-filter-redesign/final_report.md`(R1-R12)

**v4 A 线**:class 门机制预留(class_id kwarg + 5 处埋点加 `class_id='tb'`)
**v4 B 线**:handler cache(request-level cache · 避免切 filter 重命中断点)

### 逐方案对 v4 冲突分析

| 方案 | 与 v4 A(埋点加 class_id) | 与 v4 B(handler cache) |
|---|---|---|
| **β** stop_at_frame | 无冲突(debug_break 签名两边独立 · 都是 kwargs) | 无冲突(handler 层不动) |
| **γ** f_lineno | 无冲突(同上) | 无冲突 |
| **δ** sys.monitoring | 无冲突(debug_ctx 内部机制换) | 无冲突 |
| **ε** 移埋点 | **强冲突** · v4 A 要 5 处补 `class_id='tb'` · 若同期 ε 移 5 处埋点位置 · 会 conflict(需协调:先 v4 A 再 ε · 或反过来) | 无冲突 |
| **ζ** IDE 配置 | 无冲突 | 无冲突 |
| **C** 接受 | 无冲突 | 无冲突 |

**merge 冲突预警**:
- 若 v4 与本任务同时进行 · **ε 必须与 v4 A 协调**(同一 5 处 `debug_break` 埋点行)。协调方式:
  - 顺序化(v4 A 先 landing · ε 后跟)· 简单但阻塞
  - 打包做(v4 A + ε 同 PR)· 高效但增大 review 面
- 其他方案(β/γ/δ/ζ/C)与 v4 完全解耦 · 可并行

### 借势观察

**问题 1**(pause 双 fire)修法与本任务(问题 2)可**共用同一 handler cache 结构**(v4 B 提供)。见 tmp doc §问题 1 与 v4 的解耦。**skeptic 立场**:问题 1 修在 v4 B 之后借势更简洁 · 问题 2(本任务)与 v4 无 leverage 可借 · 独立立项即可。

---

## 独立块 5 · L216 vs L163 不对称的初步机制猜测(skeptic 视角 · 待 cpython_expert 证实/证伪)

**结构对比**(极关键 · lead tmp doc 已列):
```python
# L163 漂
if depth >= pullback_min_atr * atr:
    debug_break(trough_idx, anchor_kind='trough')
    print(f"trough {trough_idx}")             # 已有形式行 · 依然漂
    _ = trough_idx + 0                        # 已有形式行 · 依然漂
    _ = trough_idx                            # 已有形式行 · 依然漂
    return trough_idx

# L219 不漂
if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
    debug_break(i - 1, anchor_kind='end')
    return i - 1                              # 直接 return · 不漂
```

**表面看**:L163 有更多"形式行"应该更容易停 · 反而更漂。**这个反直觉现象是最硬的证伪基准** —— 任何 root-cause 解释必须能覆盖它。

**skeptic 假设**(待 cpython_expert 验证):
1. **控制流深度差异**:L163 在 `_find_start_idx` (深度 3:evaluate → find_start → check) · L219 在 `_find_end_idx` (同深度 3);两者深度相同 · 排除深度差异。
2. **caller 后续动作差异**:L163 return 后 · evaluate_throwback 立即调 `_find_end_idx` → **控制流跨函数** · pydevd suspend 命令传播时可能已跨过 caller · pause 落到新 callee 第一行。L219 return 后 · evaluate_throwback 只做 `if end is None: return None` + wrap ThrowbackResult · **控制流回归 evaluate_throwback 内**,pause 命令有时间在 caller frame line event 触发。
3. **具体验证方法**(cpython_expert 可试):在 L163 埋点后不 return · 直接改成 `while True: pass`(不 return · 强制 pause 有时间发生)· 观察是否漂。若不漂 · 假设 2 成立。

**皮埃罗**:pydevd `settrace(suspend=True)` 内部大概流程 = 设置全局 trace hook → 等待下一次 line event → suspend。若 settrace 返回时"下一次 line event"已经被 caller 的 `_find_end_idx` 调用触发了 · 就会 pause 到那里。**这个 race 需要 pydevd `_locked_settrace` 内部逻辑与 caller frame line event 时序对比才能证实**。

---

## 独立块 6 · v3 契约红线 + 质疑模板(承 rev0 骨架)

### v3 契约红线(hunter 方案必须过)

1. **可反复 fire**(硬要求 · commit 8cd2e7c reason):同一 line 反复触发时 pause 必须每次都停。commit 8cd2e7c 把机制从 `breakpoint()` 换到 `pydevd.settrace(suspend=True)` 的唯一动机就是修 `breakpoint()` 只 fire 一次的 bug。任何 workaround 若引入"同 line 只 fire 一次""同 process 只 fire 一次""同 anchor_kind 全局单次"就是回退。
2. **DEBUG_MODE / DEBUG_BAR_RANGE / DEBUG_ANCHOR_KIND gate 语义**:workaround 不能绕过 `debug_ctx.py::debug_break` 里的三层短路(`_DEBUG_MODE` / `_read_range` / `_read_anchor_kind`)。
3. **handler `finally` env pop 语义**:workaround 不能引入需要 handler 层清理的全局状态(否则 handler 崩溃后残留污染下一次请求)。
4. **零成本 fallback**:`_DEBUG_MODE=False` 时 `debug_break` 第一行 return · pydevd 不 import · 生产路径零开销 —— workaround 不能让 pydevd 在生产也 import。

### 6 维质疑模板

对每个候选方案至少覆盖:

| # | 维度 | 挑 gap 提示 |
|---|---|---|
| 1 | **v3 契约兼容** | 是否只 fire 一次 · 是否需要 handler 层清理全局状态 · 是否破坏 role/range gate |
| 2 | **IDE 兼容** | 是否 PyCharm-only · VSCode/pdb/remote 是否退化 · 是否依赖 undocumented private API |
| 3 | **副作用** | 全局 trace hook / frame mutation / monkey-patch 对 detector loop perf(bo_stream 遍历 hot path)· 是否让 L219/L250 从"不漂"变"漂"(regression)· 与 profiling/logging 冲突 |
| 4 | **API existence** | hunter 声称的 API 是否真在现场 pydevd 1.4.0 存在(grep `/home/yu/.local/share/JetBrains/PyCharm2026.1/python-ce/helpers/pydev/pydevd.py` 现场验)· private API(名字带 `_`)风险过高 |
| 5 | **场景边界** | 是否只对 L163 有效 · L104/L219/L224 若也漂能否复用 · 嵌套 debug_break(evaluate_throwback 内 5 次)是否互相干扰 · 多线程/异步 detector 是否退化 |
| 6 | **理论 vs 实测** | hunter 若只做纸面调研 · 标"待实测";pydevd 行为高度版本依赖(现场 PyCharm 2026.1 helpers · pydevd 1.4.0)· 必须现场 repro |

---

## rev1 · 挑 pydevd_expert 稿 M1(stop_at_frame)+ M2(移埋点 = 我 rev0.5 的 ε)

### 候选 M1 · `pydevd.settrace(suspend=True, stop_at_frame=sys._getframe(1))`

**一句话方案**:传 caller frame 给 settrace · 走 CMD_STEP_OVER 路径 · 只在指定 frame line event 停。

**独立代码验证**(skeptic 自己 grep 现场 pydevd_frame.py · 不复读 pydevd_expert 引用):
- L586-587 `can_skip = (step_cmd in (109, 108) and stop_frame is not frame)`:CMD_STEP_OVER(108)时 · 非目标 frame can_skip=True → NO_FTRACE(L612/658/906/917/936/944)· 目标 frame can_skip=False → 继续 trace
- L839-844 `elif step_cmd in (CMD_STEP_OVER, CMD_STEP_INTO_COROUTINE): stop = stop_frame is frame; if stop and is_line: ...`:代码层面确认 pydevd_expert 描述的语义

**6 维挑 gap**:

1. **v3 契约兼容** · **通过**
   - 反复 fire:CMD_STEP_OVER 是 per-call state · 每次 settrace 覆盖 pydev_step_stop · 承认无残留(pydevd_frame.py L864 continue 后 `info.pydev_step_stop = None` 只在特定 return + 无 back-frame 分支才 reset,一般 continue 命令由 IDE 走另一路径完全清 state — 已经足够)
   - env gate:全在 settrace 之前 · 未动
   - handler finally:pydevd 内部 additional_info 是 pydevd 私有 · handler 无需清理
   - 零成本:`_DEBUG_MODE=False` 短路 · pydevd import 仍 lazy · sys._getframe 是 builtin

2. **IDE 兼容** · **⚠ 待收窄**
   - pydevd_expert 说 VSCode/Cursor "同源 未 diff":skeptic 挑 gap = **同源不代表行为一致**。debugpy 是 microsoft/debugpy fork · 维护独立 · 可能:
     - 用不同 debug adapter protocol · IDE 侧 "continue" 消息投递到 pydev_step_stop 的清理路径可能不同
     - VSCode 侧无 PyCharm-style "step over" 视觉反馈 · 用户可能困惑 pause 是从 CMD_STEP_OVER 触发的
   - **skeptic 立场**:M1 的 v3 契约兼容论证只锁到 PyCharm 现场 · **明确限缩为 "PyCharm 2026.1 v1.4.0 已验证 · VSCode/Cursor 未验证"** · 若 v4 后本项目用户仅 PyCharm · 不 blocker;若未来切 VSCode debug 前必须 revalidate。
   - **修正建议**:pydevd_expert 稿 §"API 兼容" 应把 VSCode/Cursor 行 "未 diff 但同源" 打上明确 unverified 标签,不算在"跨版本安全"。

3. **副作用** · **⚠ 一个 gap**
   - pydevd_expert 说 can_skip flip → NO_FTRACE · 应更省 perf。skeptic 认为 **hot path perf 论点被生产短路(_DEBUG_MODE=0)遮蔽 · 是次要考虑**。
   - **主 gap**:pydevd_expert 只论证了 "L216/L247 不漂能保持"是 **待实测** · 没论证 **加了 stop_at_frame 后 L216/L247 会不会从"不漂"变成"漂到 caller 而非停在原 return 行"**。因为传 `sys._getframe(1)` 后 · L219 从 `_find_end_idx` frame → stop_frame = `_find_end_idx` · 而 L219 原本 pause 在 L220 (`_find_end_idx` 内) · **加了 stop_at_frame 后 pydevd 走 CMD_STEP_OVER · 如果 line event 在 L220 触发 → stop=True → 一致**。但**若 pydevd_expert H2 假设成立(L220 line event 也丢) · L219 会漂到哪?**——**CMD_STEP_OVER 下 · 非目标 frame can_skip=True → NO_FTRACE 全部 down-stream frame · 结果 pause 命令永远不 fire**(和当前"漂"改为"消失")。这是 M1 的**新故障模式**(pause 完全消失 vs 当前 pause 漂位置)· 用户可能更痛。
   - **skeptic 修正建议**:pydevd_expert 稿 §"H1/H2/H3 不对 M1 方案生效性构成影响" 是**错的**。CMD_STEP_OVER 和 CMD_SET_BREAK 都靠 trace_dispatch 触发 · trace_dispatch 触发靠 f_trace + line event · 若 line event 在 caller frame 上不 fire(H2)· CMD_STEP_OVER 只会让 pause **消失** · 不会救回来。**M1 依赖 H2 = False**(caller frame line event 真 fire) · 与 pydevd_expert 断言 "M1 不依赖" 直接冲突。**这是 rev1 最硬的挑战 · 等 cpython_expert 实证 H2 即可 disambiguate**:
     - H2 = True(caller 也丢 line event) → M1 **破**(pause 消失)· 兜底跳到 M2(ε 移埋点)
     - H2 = False(caller line event 真 fire · 只是 pydevd CMD_SET_BREAK 不 latch 到最近 frame) → M1 **通过**

4. **API existence** · **通过**
   - skeptic 独立 grep 现场 pydevd 1.4.0 L1810-1857:`stop_at_frame` 参数存在 · 公开(无 `_` 前缀)· docstring 完整
   - `sys._getframe(1)` 是 CPython builtin · 与 pydevd 无耦合 · frame 引用不会因 pydevd 版本变而 API 变

5. **场景边界** · **一个 gap 已 clear**
   - 嵌套 debug_break(evaluate_throwback 内 5 次):pydevd_expert 说"每次 settrace 覆盖 pydev_step_stop 不干扰"· 独立验证 L1970 `additional_info.pydev_step_stop = stop_at_frame` 是**直接赋值不追加** · 通过
   - **新 gap · gate 埋点**:`_emit_tb_gate` L104 里的 `debug_break(gate_idx, anchor_kind='gate')` · `sys._getframe(1)` = `_emit_tb_gate` frame(不是 `_find_start_idx` 或 `_find_end_idx`)· pause 会停在 `_emit_tb_gate` L105 `on_gate(GateFailure(...))` · 用户想看 "触发这个 gate 的 phase1/phase2 上下文" · **必须再点 stack 上一层到 `_find_start_idx` / `_find_end_idx`** —— 与"漂"的痛度相当 · 只是位置从下游变到旁支
   - **修正建议**:如需 gate 埋点也 caller-perfect · 应用 `sys._getframe(2)` **仅在 `_emit_tb_gate` 内**;或统一改用 M2(ε)风格从 `_emit_tb_gate` 内提出到 `_find_*` 内(与原本 5 处埋点位置想法一致)。**pydevd_expert 稿未论 `sys._getframe(2)` 场景 · 是 gap**。

6. **理论 vs 实测** · **⚠ blocker**
   - pydevd_expert 明说"纸面调研 · 现场 PyCharm attach 未实测 · agent 无法启 PyCharm"
   - **skeptic 立场**:M1 在 rev1 阶段最多标为 **"代码语义正确 + 待用户现场实测"** · **不能作为"已通过"给 lead** · lead 若合成 final_report 采纳 M1 应明写 "**待用户在 PyCharm 2026.1 现场用真 tb 场景 debug 一次 confirm pause 位置**" 才算 landing 条件

**结论**:**M1 待验证**(不推荐 · 不拒 · 视 cpython_expert H2 实证结果 + 用户现场实测结果二次判定)

---

### 候选 M2 · 移埋点(pydevd_expert 采纳我 rev0.5 的 ε)

**一句话方案**:trough 埋点从 `_find_start_idx` L163 上移到 `evaluate_throwback` 内 return 后。

**6 维挑 gap**(skeptic 自审自方案):

1. **v3 契约兼容** · **通过**(零 pydevd 依赖 · 与 debug_ctx 语义完全解耦)
2. **IDE 兼容** · **通过**(不动 pydevd · 任何 IDE 都行 · 甚至 vanilla breakpoint())
3. **副作用** · **通过**(不改判据 · start/end/event_id 数值不变) · 但**丢内部局部变量视图**是真代价(depth/peak/trough_idx 计算中间值不可见 · 用户需点 stack 进一层)
4. **API existence** · N/A(不用 API)
5. **场景边界** · **一个 gap**:pydevd_expert 只论证 trough 移埋点 · 若一致性要求 · **entry/end/gate 是否也移**?若只移 trough · 剩下 4 处埋点若未来结构变化再漂就要再 patch;若统一移 5 处 · 与 v4 A 线(class_id 补 5 处)强 merge 冲突
6. **理论 vs 实测** · **通过**(纯代码移位 · pytest 可验判据不变 · 无 pydevd 时序变量)

**M2 独有隐忧**(pydevd_expert 未列 · skeptic 补):
- 用户明确说"失去快速定位便失去意义"· M2 只是**局部**恢复快速定位(caller frame variables)· **不能给到 phase1 内部 depth/peak 中间值** · 用户偏好可能仍不满
- 但相比 M1 的"待验证 + 5 分之 1 覆盖"(gate 埋点仍需 sys._getframe(2)) · M2 **确定性满足 P3 严重度下的用户核心诉求**(trough_idx 值 · start 值)· 且**零 pydevd 依赖**

**结论**:**M2 推荐兜底 · 若 M1 实测通过则 M2 可弃 · 若 M1 破则直接切 M2 · 判据 = cpython_expert H2 实证**

---

### 候选比较汇总(rev1 后)

| # | 方案 | skeptic 独立 rank | 相对 pydevd_expert 稿 差异 |
|---|---|---|---|
| M1 | `stop_at_frame=sys._getframe(1)` | **待验证 · 依赖 H2=False** | 挑战 pydevd_expert "M1 不依赖 H1/H2/H3" 的断言 · 收窄为 "M1 依赖 H2=False" · gate 埋点 gap · IDE 兼容 unverified 标签 |
| M2 | 移埋点(=我的 ε) | **推荐兜底** | 与 pydevd_expert 一致 · 补一致性 gap(5 处 vs 1 处)+ v4 A 线合并冲突预警 |
| C | 接受 + stack 导航 | **兜底之兜底** | 用户拒 · 但若 M1/M2 都不通过是最后退路 |

---

## 修订历史

- rev0(初版 · 已归档):基线 · 质疑模板 · 兜底方案 A/B/C 骨架
- rev0.5(2026-07-17):独立四块任务落地(严重度 P3 + 独立 rank ε/β 首选 + 项目侵入面 + v4 兼容) + 现场事实锁定
- **rev1(2026-07-17):挑 pydevd_expert M1 稿。核心 gap = "M1 不依赖 H1/H2/H3"论断被 skeptic 独立读 pydevd_frame.py L586/839 后反驳 · 实为 "M1 依赖 H2=False"。等 cpython_expert 实证 H2 是 rev2 关键 blocker**
- **rev2(本稿 · 2026-07-17):承接 rev1 · 补第一轮时序未赶上挑 cpython_expert rev1 三份实验 + 挑 pydevd_expert rev3 新解释 + 提议新方案 η/θ/ι/κ + 复核 lead final_report rev1。核心 gap = drift 归因 "100% 在 IDE 侧"是过判 · M1 反抗机制的新解释是纸面推理无实验支持 · 需列 M1 分层 failure mode + IDE 反抗机制的分层降级路径**
- rev3(待做):收 cpython_v2 rev2 + pydevd_v2 rev4 回应 · 判 blocker 是否 clear · lock 或再挑

---

## rev2 · 补第一轮时序未赶上的挑战 + 独立评估

**背景**:pause_skeptic rev1 挑的是 pydevd_expert **rev1** · 但 pydevd_expert 后来出到 rev3(撤 rev2 cache_skips 论证 · 融合 cpython_expert 三份实验证据) · rev1 时 cpython_expert 也刚刚 idle。skeptic v2 承接 rev1 · 补第一轮 skeptic 没赶上挑的两块 · 走完 rev2/rev3 收敛。

### 挑 A · cpython_expert rev1 三份实验设计

#### A.1 · 实验 1 (raw sys.settrace) 复刻语义 gap

cpython_expert 用自实现 tracer "下一次 line 事件停下"复刻 pydevd `settrace(suspend=True)` 语义 · **两者不严格等价**:

- **pydevd 语义**:`_locked_settrace` 调 `set_trace_for_frame_and_parents`(pydevd.py L1927)· **walk `.f_back` 链把 f_trace = trace_dispatch 挂到所有 caller frames**(L1343-1344)· 然后 flip `additional_info.pydev_state = STATE_SUSPEND` · trace_dispatch 在**下次任意已挂 f_trace 的 frame 的 line event** 里查这 flag → do_wait_suspend
- **自实现 tracer**:sys.settrace(func) 只挂到**当前调用栈上的 frame**(CPython 的 sys.settrace 语义:new frames 才自动 tracer;当前正在跑的 frame 需要手动 `frame.f_trace = func`)· 若不 walk .f_back · caller frame 的 line event 就不 fire tracer

**这是 hunter 侧独有的 pydevd 深度机制** · cpython_expert 实验 1 是否做了这个 walk?若无 · 实验 1 只证 CPython trace 语义自身无不对称 · **不能反证 pydevd 的挂 f_trace 层无 drift**。这是我 rev2 挑给 cpython_v2 的 gap 1a。

**skeptic 立场**:实验 1 结论有效性收窄为 "CPython line event 在三个 anchor 场景下都精确落 return 行 · 排除 CPython bytecode/co_lines 层不对称";**不能**推 "pydevd 挂 f_trace 层无 drift"。cpython_v2 需要:
- 要么补 walk_f_back 挂 tracer 的复刻步骤 · 让实验 1 fidelity 达到 pydevd 层
- 要么明标结论边界

#### A.2 · 实验 2 (真 pydevd + monkey-patch mock IDE) 三个 gap

**gap 2a · warm-up 完整性**:

PHASE 2 "warm-up 让 cache_skips 建起来" · 但 `cache_skips` key = `(co_firstlineno, co_name, co_filename)` 是 **per code object**。需**分别**让 `_find_start_idx` / `_find_end_idx` / `evaluate_throwback` **三个不同 code object 各自** 进入 cache 判 skippable 后 · 再跑正式实验。cpython_expert rev1 未说 warm-up 具体做了什么 · 若只重复调 `evaluate_throwback`(不 fire debug_break)· `_find_start_idx` / `_find_end_idx` 内的 code object 可能没被 trace 到 skippable 判定 · cache_skips 未真填满 · PHASE 2 结论就代表不了真 IDE 已连状态。

**gap 2b · mock 缺 IDE 回发命令 · 掩盖真 drift 机制**:

真 PyCharm IDE 收到 `thread_suspend` 消息后 · 会**回发** step/continue/step_over 命令给 pydevd。这些命令通过 pydevd_process_net_command / pydevd_reader_thread 写入 `additional_info.pydev_step_cmd` · trace_dispatch 下次 fire 走不同分支。

**mock `do_wait_suspend` 只 "记录 frame + 立即释放" · 完全没模拟 IDE 回发命令**。这直接掩盖了一个非常可能的真 drift 机制:
- IDE 因 Skip Files 规则识别 debug_ctx.py 是 helper · 收到 pause 后**回发 CMD_STEP_OVER** 给 pydevd
- pydevd 收到 CMD_STEP_OVER · flip pydev_step_cmd=108 · pydev_step_stop=当前 frame(debug_break)
- 下次 line event · trace_dispatch 走 CMD_STEP_OVER 分支 · debug_break.f_back = _find_start_idx → step_over 语义 = "回到 caller 后停 · 但若 caller 也在 skip 列表继续 step" → walk 到 `_find_end_idx:200`

**这才可能是 drift 真机制**。mock 抹掉它了。cpython_v2 需补此覆盖 · 或明标 "实验 2 只覆盖 IDE 不回发命令场景"。

**gap 2c · "pause 落地 → debug_break():84" 语义边界**:

这是**pydevd 侧 do_wait_suspend 收到的 frame** · 是 CPython/pydevd 层观察。**不是** IDE 侧最终显示给用户的行号。IDE 收到消息后可能自己再走 auto-step / skip / show source 到不同位置。

cpython_expert rev1 结论 "三 anchor 齐整传 debug_break" 只能推 **pydevd 侧无 drift** · **不能** 推 "用户观察的 drift 不存在 → drift 100% 在 IDE 侧"。这个推理链有 gap:
- 前提:pydevd 侧无 drift(实验 2 已证)
- 结论:drift 100% 在 IDE 侧(**过判**)
- 缺环:drift 可能在 IDE 侧 · **也** 可能在 pydevd + IDE 交互路径(如 gap 2b 所述 IDE 回发命令 → pydevd 内部路径走出 drift)

**skeptic 立场**:drift 归因应改为 "**pydevd/CPython core 无 drift · drift 归因 = IDE 侧行为 或 pydevd + IDE 交互路径 · 二选一 · 需 IDE 侧实证收窄**"。lead final_report rev1 的 "100% 在 PyCharm IDE 客户端" 表述过硬 · 应软化。

#### A.3 · 实验 3 (bytecode dis + co_lines) 覆盖率不足

只覆盖 L163 (3 nested if + return) vs L219 (1 if + return) · 未覆盖:
- **L224 timeout**:`_find_end_idx` 循环外 · `debug_break(end_scan, ...)` 后 `return end_scan` · bytecode 结构与 L219 循环内 return 不同(无 END_FOR 前缀)
- **L250 entry**:`evaluate_throwback` 函数头后 · `debug_break(...)` 后 `if bo_idx < 1 or ...` · 后跟 `if` 不是 `return` · line event fire 时机可能不同
- **L104 gate**:`_emit_tb_gate` 内 · `debug_break(gate_idx, ...)` 后 `on_gate(GateFailure(...))` —— 是**普通 CALL_FUNCTION · 不是 return** · 结构上与 L163/L219 都不同。gate 埋点在 M0 下是否漂?未观察 · 无 bytecode 分析支撑

请 cpython_v2 rev2 补:5 处埋点各自 bytecode dump + co_lines 分析 · 覆盖率补齐 5/5。

### 挑 B · pydevd_expert rev3

#### B.4 · 撤 cache_skips 论证不彻底

rev3 撤 rev2 "cache_skips 是 M0 漂移机制" · **但残留污染仍在**:

rev3 §"H1/H2/H3 vs M1 生效" 三张表里 H2 一行仍写:
> H2 mid-execution 挂 f_trace 时序 bug / cache_skips 状态 → **M1 反抗**(is_stepping=True 绕过 cache_skips 短路)

cache_skips 既被证伪 · 这行 M1 反抗解释就失去基础。**M1 反抗机制现在只有"IDE 侧 skip 触发条件"这一条 · 见 B.5**。请 pydevd_v2 rev4:
- H2 行的 M1 反抗解释作废 · 或重写 H2 定义(H2 若在 cache_skips 之外还有其他形式 · rev4 应列)
- rev3 §"M1 反抗 cache_skips 短路 · 新事实(rev2 补入)" 整节从"新事实"降级为"错断言" · 明打删除线保留讨论痕迹 · 而不是像现在只在 TL;DR 提一句 "rev2 撤此论"
- H1/H2/H3 三张表整体审计 · 排除其他残留旧论断

#### B.5 · M1 反抗机制 rev3 新解释是纸面推理 · 未列 M1 分层 failure mode

rev3 新解释:
> `stop_at_frame` 走 CMD_STEP_OVER → pause 时传给 IDE 的 frame 是 caller · IDE 看不到 debug_ctx.py 就无 skip 触发条件 → pause 落 caller

**核心问题**:PyCharm IDE 的 skip files / Just My Code 逻辑对 pause 消息的处理规则**未验证**。以下三条可能性 rev3 未 acknowledge:

- **5a · IDE 可能对所有 pause 消息统一 apply skip filter**(不区分 pydevd 走 CMD_STEP_OVER 还是 CMD_SET_BREAK)· 结果 = **M1 也漂**(与 M0 一样)· 因为 IDE 看到 caller frame `_find_start_idx` 也是"内部 detector"仍 skip
- **5b · IDE 触发 auto-step 后 · CMD_STEP_OVER 语义让 pydevd 直接 continue**:M1 下 pydev_step_stop = caller_frame · IDE 若因 skip files 回发 continue · pydevd walk 到 caller.f_back · `stop_frame is not frame` → can_skip=True → NO_FTRACE 整链 → **pause 完全消失**(比 M0 更痛 · 用户完全看不到 pause · 会以为 debug 挂了)
- **5c · IDE 侧 UX 视觉反馈**:CMD_STEP_OVER 触发的 pause 在 PyCharm 里可能显示为 "stepped over" 状态而非 "paused at breakpoint" · 用户预期是断点停 · 看到 step 状态可能困惑

**M1 分层 failure mode 表**(rev3 未列 · 请 rev4 补):

| 场景 | M1 行为 | 用户观察判据 | 分层回退策略 |
|---|---|---|---|
| M1 pass | pause 落 `throwback.py:164 return trough_idx` · 变量面板显示 trough_idx | 一次实测 confirm | 采纳 M1 |
| M1 fail-mild | pause 落 caller frame 但 IDE 再 auto-step 跳到下游 | 用户观察 = 与 M0 现象等价("漂到 `_find_end_idx:200`") | 退 M2(ε 移埋点) |
| M1 fail-severe | pause 完全消失 · IDE auto-step + CMD_STEP_OVER walk 链一路走到 detector 外 | 用户按 debug 后 detector 跑完不停 · 无 pause | **优先回滚到 M0 再退 M2**(避免用户以为 debug 挂了 · 若断点消失比"漂"更痛) |
| M1 fail-cosmetic | pause 位置对 · 但 IDE 显示 "stepping" 而非 "breakpoint" | pause 停对了位置但状态栏文字不同 | 用户偏好决定(可接受 = 采纳;不可接受 = 退 M2) |

分层回退比"一态 landing / 一态 fail 退 M2"更精准 · **fail-severe 是新故障** · 不是 fail-mild 的加剧。

#### B.6 · Landing 硬前置 5 条覆盖不足

rev3 已列 5 条(trough 落 L164 / 变量面板显示 / 反复 fire / entry/end/end-timeout 不 regression / gate 埋点落 detector 层)· 缺:

- **6a · Continue 后 pydev_step_stop 清理**:rev3 说 CMD_STEP_OVER 是 per-call state · 但**用户按 Continue 后 pydevd 是否真 clear pydev_step_stop**?若不 clear · 下次 debug_break 触发前 pydev_step_stop 残留上次 frame 引用(可能已 GC · dangling)· pydevd 内部可能错乱。请 pydevd_v2 rev4 grep 现场 pydevd 的 `CMD_RUN` / `CMD_CONTINUE` 处理路径 · confirm pydev_step_stop 被 reset · 或说明 additional_info per-thread 生命周期覆盖此风险
- **6b · pause 未 fire 的观察工具**:若 M1 fail-severe(pause 消失)· 用户如何知道是 "pause 没触发" 而不是 "debug 挂了 / debug_break 短路"?rev4 应加 landing 判据的**观察工具**部分:"若 pause 未按预期触发 · 用 env `PYDEVD_DEBUG=1` 启 pydevd log · 观察 do_wait_suspend 是否真调用"
- **6c · IDE 视觉反馈判据**:5c 分层里的 fail-cosmetic 场景 · rev4 应明列判据 · 让用户实测时能区分 "pause 位置对但 IDE 显示 step 状态" 是否 blocker

### 挑 C · 独立评估

#### C.7 · 新方案候选(rev3 未考虑)

除 M1/M2 外 · 我 rev2 提议 4 个新方向:

- **η · IDE Skip Files 配置层规避**:PyCharm Preferences → Build/Execution/Deployment → Debugger → Stepping → **Do not step into files** · 检查 `path2/debug_ctx.py` 是否在自动 skip 列表 · 手动 remove。**零代码改动** · pydevd 层无法验证 · 需用户在 PyCharm 里查设置。**skeptic 独立立场**:这是 drift 根因的 first-check tool · 若 IDE 里有 debug_ctx.py skip 条目 · remove 后直接观察是否 drift 消失 —— 是**最便宜的 drift 归因手段**。lead 决策阶段应在决定 M1 vs M2 前先让用户试这个。

- **θ · 让 debug_ctx.py 伪装成非 helper**:文件挪出 `path2/` 到 project root · 或改名(如 `debug_pause.py`)· 让 PyCharm 的 "user code" 启发式识别为 project code。**代价**:文件位置变、5 处 import path 变。**收益**:零 API 依赖 · 与 M1 正交(可与 M1 组合)。**skeptic 立场**:比 M1 稳定(不依赖 pydevd 内部命令处理路径)· 但侵入面 = touch 6 个文件的 import · 比 M1 大。当 η 证实 IDE 侧 skip 是 drift 根因 · θ 是 workaround;当 η 证否 drift 在 IDE skip · θ 也无效。

- **ι · sys.settrace 手动 attach**:pydevd 之外自建 tracer · debug_break 里 set caller frame f_trace · 直接触发 IDE 侧 breakpoint 逻辑。**风险**:与 pydevd 争 trace hook · sys.settrace 只有一个 tracer slot · 覆盖后 pydevd 自身 trace 停 · debugger 挂。**skeptic 判定**:极大概率不可行 · 除非用 pydevd 提供的 wrapper API(现场未查)。

- **κ · 5 处埋点各自显式传 frame**:每处 debug_break 改成 `debug_break(..., stop_at_frame=sys._getframe())` · **埋点侧决定 caller** · 消除 M1 gate 埋点例外(rev3 gate 办法 A 是这个思路的 gate-only 版 · κ 推广到全 5 处)。
  - **收益**:每处埋点独立控制 · gate 埋点可传 `_getframe(0)` 停在 gate 侧、trough 埋点传 `_getframe(1)` 停在 detector 层、任意变体细粒度可选;消除 M1 的 "统一策略" 限制
  - **代价**:throwback.py 5 处埋点各加 kwarg · 但与 v4 A 线补 `class_id='tb'` 是同批改动 · **rebase 一次 landing 二价值**
  - **skeptic 立场**:κ 是 M1 的"埋点侧知情"泛化版 · 抽象干净、v4 A 线合并优雅;但**仍然依赖 pydevd 侧 CMD_STEP_OVER 语义正确处理** · B.5 提的 IDE 反抗 3 态 κ 也不豁免 —— κ 只是把"传哪个 frame"的决定权从 debug_ctx 移到埋点侧 · **不能救 M1 的 IDE 反抗风险**

**新方案 rank**(独立 rank · 追加到 rev0.5 排序):

```
1. η · IDE Skip Files 配置规避     · first-check drift 归因(零代码 · 最便宜验证)
2. ε (= M2) 移埋点                   · 兜底(pydevd-agnostic)
3. β (= M1) settrace stop_at_frame  · 待验证(依赖 IDE 反抗机制 = 纸面推理)
4. κ · 5 处埋点显式传 frame          · M1 的埋点侧知情泛化 · 仍受 IDE 反抗风险
5. θ · 挪 debug_ctx 出 helper 目录   · η 证实 root cause 后的 workaround · 侵入面较大
6. ζ · IDE 配置层其他设置             · 待探索(rev0.5 已列)
7. C · 接受 + 文档化                  · 兜底之兜底
8. γ · f_lineno 硬改                  · 危险不推荐(rev0.5)
9. ι · sys.settrace 手动 attach       · 与 pydevd 争 hook 大概率不可行
10. δ · sys.monitoring                · cpython_expert 已证不 solve drift
11. α · 加形式行                       · 已实测证伪
```

**首选变更**(相比 rev0.5):**η 上升到首位**(不动代码验证 drift 是否在 IDE Skip Files 那一层)· ε (=M2) 上到次位(pydevd-agnostic 兜底,比 β (=M1) 更稳定)· β (=M1) 降到第 3。理由:B.5 提的 IDE 反抗 3 态在 rev2 阶段未 disambiguate · M1 的 landing 硬前置(用户实测)本质上就是走 η 的路径(用户在 IDE 里试)· 那不如**先** 走 η 直接验证 IDE Skip Files 是不是 root cause · 通过则直接零代码解决 · 不通过再考虑 M1/M2。

#### C.8 · 复核 lead final_report.md rev1

lead rev1 综合了三个中间稿 · 但沿用了几处有问题的表述 · 需 rev2 修正:

- **8a · §Team 共识 §drift 根因定位** 说 "drift **100%** 发生在 PyCharm IDE 客户端"(A.2 gap 2c 已详)—— 100% 是过判 · cpython_expert 实验只证 pydevd/CPython 层无 drift · **不能** 证 drift 100% 在 IDE 侧。**应改为** "drift 归因 = pydevd/CPython core 无 · IDE 侧 或 pydevd + IDE 交互路径 · 二选一 · 需 IDE 侧实证收窄"
- **8b · §Landing 硬前置 第 4 条**:"entry / end / end-timeout 不出现新 regression(原本 "不漂" 保持 "不漂" · pause 不 "消失")" · 括号里的 "pause 不消失" 是隐含 · 未展开。**应改为** 明列 M1 fail-severe 场景("pause 完全消失比漂位置更痛 · 观察到应回滚到 M0 再退 M2")
- **8c · §决策 3 · gate 埋点办法选** 只列办法 A/C · 未列 **κ 全埋点显式传 frame** —— κ 是 A 的推广(A = gate 一处补 kwarg · κ = 5 处都补 kwarg) · 消除 A 的"gate 例外"抽象泄漏。lead 决策阶段应展示 A/κ/C 三选
- **8d · §M1 优先于 M2 理由** 说 "M1 一次改动覆盖 5 埋点" —— 不完全准确 · 实际 "4 处直接受益 + 1 处需办法 A 补 kwarg"(见 rev3 §M1.gate)。这个描述不一致 rev3 自身也存在 · lead rev1 沿用。**应改为** "M1 覆盖 4 处埋点 · gate 埋点需办法 A 补 kwarg(1 处 throwback.py 显式传参)"
- **8e · §决策 1 · v4 vs 本任务时序** 已推荐 "v4 先 · 本任务后" · 与我 rev0.5 独立判定一致 · 但**未 acknowledge** 采纳 η 后可能 "本任务在 v4 之前秒杀"(η 零代码 · 若 IDE Skip Files 是 root cause · 用户手动 remove 即可 · 完全无 rebase 冲突)。lead 决策应加 "η 前置探索 · 若 η 通过则本任务不启动 · 若 η 不通过再按 v4 后启动 M1/M2"
- **8f · §决策 2 · M1 现场实测 5 条 landing 硬前置** 已列 · 但未列 M1 fail-severe 分层回退策略 —— rev4 补完 M1 failure mode 表后 · lead final_report 决策 2 应同步更新 · 让用户实测时按分层判据决策(pass / mild → M2 / severe → M0 兜底再 M2 / cosmetic → 偏好决定)

### rev2 结论汇总

**rev1 → rev2 变更总结**:

1. **drift 归因收窄** · 从 "IDE 侧" 改为 "IDE 侧 或 pydevd + IDE 交互路径" 二选一 · 因 cpython_expert 实验 2 mock 未覆盖 IDE 回发命令场景
2. **M1 反抗机制降级** · 从 "rev3 纸面推理有 3 张表支撑" 改为 "只剩 IDE 反抗机制一条 · 纸面推理无实验支持 · 需列分层 failure mode(mild/severe/cosmetic 三态)"
3. **首选方案变更** · 从 rev0.5 的 "ε(=M2) 首选 / β(=M1) 次选" 改为 "η(IDE Skip Files 前置探索)首选 · ε(=M2) 兜底 · β(=M1) 待验证"
4. **新方案 η/θ/ι/κ 提议** · κ 是 M1 gate 办法 A 的推广 · η 是零代码首验工具

**rev3 blocker**(等 cpython_v2 rev2 + pydevd_v2 rev4 回应):

- cpython_v2:实验 1 复刻 fidelity 是否补 walk_f_back(gap 1a)· 实验 2 是否补 IDE 回发命令场景(gap 2b)· 实验 3 是否补 5 处覆盖率(A.3)
- pydevd_v2:M1 反抗机制是否补 failure mode 分层表(B.5)· cache_skips 论证残留是否清理(B.4)· Landing 硬前置是否补 continue 后 clean-up + 观察工具 + IDE 视觉反馈(B.6)

若 rev2/rev4 clear 所有 blocker · rev3 = lock · 通告 lead;若仍有 blocker · rev3 再挑。

### rev2 独立立场(送 lead 作 final_report rev2 综合参考)

**推荐决策序**:

1. **首步 · η 探索**(用户 3 分钟工作量):打开 PyCharm Preferences → Build/Execution/Deployment → Debugger → Stepping · 检查 `path2/debug_ctx.py` 是否在 "Do not step into files" 列表 · 若在 · 手动 remove · 再跑 FV2 场景 J2 · 观察 trough pause 是否落 L164
   - 通过 → **本任务完成** · 无需 M1/M2 · 直接文档化 IDE 配置步骤
   - 不通过 → drift 不在 Skip Files 层 · 进第 2 步

2. **第 2 步 · M1 现场实测**(用户 5 分钟工作量 · 前提 η 不通过):按 rev3 landing 硬前置 5 条 + rev2 新增 3 条(6a/6b/6c)+ M1 failure mode 分层判据实测
   - M1 pass → 采纳 M1 + gate 办法 A(或 κ 全埋点显式)· 建议 v4 后 landing 避免 rebase 冲突
   - M1 fail-mild / severe → 直切 M2(ε 移埋点 · trough 一处)· 与 v4 A 线注意 rebase
   - M1 fail-cosmetic(仅视觉反馈)→ 用户偏好决定

3. **第 3 步 · v4 时序**:η/M1/M2 无论哪条落地 · 都建议 v4 先 landing(v4 spec 已定稿 · 阻塞人在用户实测)· 本任务放 v4 后。η 是唯一例外(零代码 · 无 rebase 风险 · 可立即前置)

---

## rev3 · lock 判定 · 收 pydevd_v2 rev4 + cpython_v2 rev2 反馈综合

**状态**:rev3(本节 append · 不覆盖 rev1/rev2)· **判定 = lock**(主 blocker 全 clear · 剩残留 minor 送 lead final_report rev2 收尾)· 通告 lead 综合。

### rev3 判定汇总

pydevd_v2 rev4 + cpython_v2 rev2 联合回应我 rev2 挑战:

| 挑战 | pydevd_v2 rev4 回应 | cpython_v2 rev2 回应 | skeptic rev3 判定 |
|---|---|---|---|
| 4 · cache_skips 撤销 | §5.6 双证撤销(实测 + 独立读 _mark_suspend L983-986 · M0 也 flip 到 CMD_STEP_INTO) | (无需回应 · pydevd 侧问题) | ✅ **clear** · 比要求还彻底 |
| 5a · IDE 统一 apply skip filter | §5.3 证据 2 PYDEVD_FILTERS 只在 is_stepping=True 触发 · M0 is_stepping=True 所以 filter 生效解释 M0 漂 · M1 pydevd 层先换 top frame 给 IDE 让 filter 无从 skip | (无需 · pydevd 侧) | ✅ **clear** · 从 PYDEVD_FILTERS 机制层正面反驳 |
| 5b · M1 fail-severe pause 消失 | §5.3 证据 4 stop_reason 分类间接支持(CMD_SET_BREAK vs CMD_STEP_OVER 走不同 UX handler) | (无需 · pydevd 侧) | ⚠ **部分 clear**(源码推理完整 · 无实测) |
| 5c · IDE 视觉反馈判据 | 未回应 | (跨范围 · CPython/PEP 669 视角本不负责) | ⚠ **未 clear** · 送 lead 综合时补 landing checklist 一条 |
| 6a · Continue 后 pydev_step_stop 清理 | 未回应 | (跨范围) | ⚠ **未 clear** · 送 lead 综合时补 |
| 6b · pause 未 fire 观察工具(PYDEVD_DEBUG=1) | 未回应 | (跨范围) | ⚠ **未 clear** · 送 lead 综合时补 |
| 主 blocker · M1 反抗机制纸面推理 | §5.2 完整 pydevd 源码走查(M0 走 L754 SUSPEND early-return / M1 走 L839-890 CMD_STEP_OVER 传 caller) | §"实验 5" pydevd 层实证 M1 反抗(mock 拦截 do_wait_suspend 记录 pydev_step_cmd=108 · pydev_step_stop_func=caller · event=line · 三 anchor 全对齐) | ✅✅ **强 clear** · 从纸面推理升到 pydevd 层实证 · 唯一仍纸面 = IDE 层 · 与 landing 硬前置同一件事 |
| 1a/1b · 实验 1 复刻语义 | (无需 · CPython 侧) | §"Gap 1" 结论边界收窄(实验 1 只做 H1 反证 · 不承担 pydevd 复刻义务;实验 2+5 联合覆盖 pydevd 状态机层) | ✅ **clear** · 边界收窄合理 |
| 2a · warm-up 完整性 | §5.6 已论 cache_skips 短路机制本身被撤销(M0 也 is_stepping=True) | (无需专门回应 · pydevd_v2 已从机制层撤销) | ✅ **clear**(mechanism 已撤销 · warm-up 完整性 moot) |
| 2b · mock 缺 IDE 回发命令 | (无需 · CPython 侧) | §"Gap 2" 承认真 gap 无法 close · 加实验 6 补 in_project_scope 负面证据 · gap 只影响因果链末端 · 不影响 pydevd Python 层无 drift 核心结论 | ⚠ **部分 clear** · agent 环境限制 · 与 landing 硬前置同 blocker |
| 2c · pydevd 侧 vs IDE 侧观察边界 | §5.1 显式承认 "drift 100% 在 IDE Java 侧" | §"Gap 2" 显式确认 gap 只影响因果链末端 | ⚠ **表述过判** · "100%" 仍需软化(见 rev3 minor blocker 1) |
| 3 · 实验 3 覆盖率 | (无需) | §"Gap 3" 实验 4 直接 dis 现场 throwback.py 全 4 return + 3 处 None return + 表达式 return · 全独立 line 归属 · H3 全线证伪 | ✅ **clear 得漂亮** · 真文件 dis · 全变体覆盖 |
| 7a · lead final_report "100%" 过判 | 沿用 rev3 "100%" 表述 | rev2 §"Gap 2" 隐含承认 gap 无法 close · 但正文仍说 drift 100% 在 IDE 侧 | ⚠ **表述过判** · 需 lead final_report rev2 综合时软化 |
| 7b · Landing 第 4 条 pause 消失分层 | 未回应 | (跨范围) | ⚠ **未 clear** · 送 lead 补 M1 failure mode 表 |
| 7c · gate 埋点未列 κ 方案 | 未回应 | (跨范围) | ⚠ **未 clear** · 送 lead 综合补 |
| 7d · "M1 一次改动覆盖 5 埋点" 描述不一致 | 未修正 | (跨范围) | ⚠ **未 clear** · lead 综合修 |
| C.7 · η/θ/ι/κ 4 个新方案 | 未评估 | 未评估(但 rev2 §sys.monitoring 补 PEP 669 M0 pause frame 与 M1 效果相似的新事实 · 隐引出**新方案 λ**) | ⚠ **未 clear** · 送 lead 综合补 |

### 新方案 λ(cpython_v2 rev2 隐引出 · skeptic rev3 独立提名)

cpython_v2 rev2 §"sys.monitoring 修正表述" 揭示 PEP 669 M0 的 pause frame **自然落 caller**(`py_return_callback` 无 STATE_SUSPEND 分支 · CMD_SET_BREAK 只在 `py_line_callback` 触发 · pause 在 caller 层 fire · 不给 IDE 触发 skip 的机会)· 与 M1 效果相似。

**引出新方案 λ · USE_LOW_IMPACT_MONITORING=1 opt-in**:

- 用户环境 env `USE_LOW_IMPACT_MONITORING=1` · 让 pydevd 1.4.0 走 PEP 669 路径 · M0 pause frame 自然是 caller · **不需 M1 改代码**
- **零代码改动**(只加 env var · 与 η IDE Skip Files 配置层同级)
- **风险**:PEP 669 路径的 IDE 侧行为未测(与 M1 landing 硬前置同 blocker)· pydevd 1.4.0 PEP 669 实现完整度未 100% 验证
- **λ vs η vs M1 对比**:

| 方案 | 层次 | 代码改动 | 依赖 | 备注 |
|---|---|---|---|---|
| η | IDE 配置 | 0 行 | PyCharm Preferences | 最直接 · 若 debug_ctx.py 在 Skip Files 列表 · remove 秒解 |
| λ | pydevd 事件源 | 0 行(仅 env) | pydevd 1.4.0+ PEP 669 impl · IDE 兼容 PY_LINE 事件 | 走另一条 code path · 副作用面较大 |
| M1 | 代码层 | debug_ctx.py 1 行 + gate 埋点 1 处 | pydevd stop_at_frame API | 已有 pydevd 层实证支持(cpython_v2 实验 5) |
| M2 | 代码层 | throwback.py 移埋点 1 处 | 零 pydevd | pydevd-agnostic 兜底 |

**skeptic rev3 立场**:λ 加入方案 rank 第 4 位(η 首 · ε=M2 兜底 · β=M1 待验证 · λ 与 β 平级)· lead 综合 final_report rev2 时应展示 4 个非纸面方案 · 让用户自选。

### rev3 最终方案 rank(承 rev2 · 加 λ)

```
1. η · IDE Skip Files 配置规避     · first-check drift 归因(零代码 · 最便宜验证)· 若 debug_ctx.py 在 skip 列表 · 秒解
2. ε (= M2) 移埋点                   · 兜底(pydevd-agnostic · 无 IDE 依赖)· skeptic 推荐次选
3. β (= M1) settrace stop_at_frame  · pydevd 层已实证反抗机制(cpython_v2 实验 5)· 唯一未测 = IDE 侧行为 · landing 硬前置卡在用户实测
4. λ · USE_LOW_IMPACT_MONITORING=1  · pydevd 事件源切换 · M0 pause frame 自然落 caller · 与 β 效果相似 · 零代码但依赖 PEP 669 IDE 兼容
5. κ · 5 处埋点显式传 frame          · β 的埋点侧知情泛化 · 消除 gate 例外 · 与 v4 A 线同批 rebase
6. θ · 挪 debug_ctx 出 helper 目录   · η 证实 root cause 后的 workaround · 侵入面较大(6 处 import)
7. ζ · IDE 配置层其他设置             · 待探索
8. C · 接受 + 文档化                  · 兜底之兜底
9. γ · f_lineno 硬改                  · 危险不推荐
10. ι · sys.settrace 手动 attach       · 与 pydevd 争 hook · 不可行
11. δ · sys.monitoring 单飞           · 已被 λ 收编(λ 是"当前 pydevd 用 PEP 669 而不换 M1"的正确表述)
12. α · 加形式行                       · 已实测证伪
```

### rev3 送 lead 的 minor blocker 清单(lead 综合 final_report rev2 时收尾)

**表述层**(改文字 · 无需追加实验):

1. **7a/2c · "drift 100% 发生在 PyCharm IDE(Java 侧)" 过判**:cpython_v2 实验 6 in_project_scope 只覆盖一个具体机制(pydevd Python 层 filename filter)· 未覆盖 pydevd + IDE 交互路径(PYDEVD_FILTERS env 是 IDE 侧 push 到 pydevd 层触发 filter · 走的是交互路径不是纯 IDE 侧)。**建议改**:"drift 不在 pydevd Python 层可控范围内(in_project_scope / cache_skips / f_trace_lines 三层已证)· drift 归因 = IDE 侧行为(Skip Files / Just My Code / auto-step)· 或 pydevd + IDE 交互路径(PYDEVD_FILTERS IDE push 到 pydevd 触发)· 二选一 · 需用户实测收窄"
2. **7d · "M1 一次改动覆盖 5 埋点" 不一致**:pydevd_v2 rev4 §5.4 caller 关系表已列 "gate 差一层需办法 A" · 但 §"M1 优先于 M2 理由" 仍写 "覆盖 5 埋点"。**建议改**:"M1 一次改动直接覆盖 4 处埋点(trough/end/end-timeout/entry)· gate 埋点需办法 A 补 kwarg(1 处 throwback.py 显式传参)"

**结构层**(补章节 · 无需追加实验):

3. **7b · M1 failure mode 分层表**:pydevd_v2 rev4 landing checklist 6 条未列 pass / fail-mild / fail-severe / fail-cosmetic 四态分层判据 + 回退策略。**建议补**:直接搬 skeptic rev2 §B.5 表格 · fail-severe 强调"pause 完全消失比漂位置更痛 · 观察到应回滚到 M0 再退 M2"
4. **7c/C.7 · gate 埋点方案矩阵补 κ**:pydevd_v2 rev4 §5.4 只列 A/B/C · κ(5 处埋点全显式传 stop_at_frame · 消除 gate 例外)未列。**建议补**:方案矩阵加 κ · 与 A 并列;κ 与 v4 A 线补 class_id 同批改动 · rebase 一次 landing 二价值
5. **η/λ 前置探索方案**:pydevd_v2 rev4 和 cpython_v2 rev2 都未评估 η/θ/ι/κ + λ 4+1 个新方案。**建议补**:方案矩阵前置 η 作 first-check 探索工具 · 加 λ 作 β 替代 · κ 作 β 泛化 · 让用户在采纳 β 前先试 η/λ

**判据层**(补 landing 判据 · 无需追加实验):

6. **6a · Continue 后 pydev_step_stop 清理**:pydevd_v2 rev4 §"风险与场景边界" 第 1 点只提"下次 fire 独立生效" · 未 grep CMD_RUN/CMD_CONTINUE 路径确认 pydev_step_stop 被 reset。**建议补**:landing checklist 加一条 "grep 现场 pydevd `CMD_RUN`/`CMD_CONTINUE` 处理路径 · confirm pydev_step_stop 被 reset · 或说明 additional_info per-thread 生命周期覆盖此风险"
7. **6b · pause 未 fire 观察工具**:landing fail 降级路径缺 "若 pause 未按预期触发 · 用 env `PYDEVD_DEBUG=1` 启 pydevd log · 观察 do_wait_suspend 是否真调用"
8. **5c/6c · IDE 视觉反馈判据**:landing checklist 加 "pause 位置对 · IDE 状态栏显示 'paused at breakpoint' 而非 'stepped over'" · fail 归 fail-cosmetic 分层(见 M1 failure mode 表)

### rev3 lock 通告

**skeptic v2 rev3 = lock**:所有主 blocker(M1 反抗机制纸面推理 · cache_skips 论证残留 · IDE 统一 skip filter 风险)已 clear;剩残留全部是文档表述 / 结构 / 判据完备性级别的 minor blocker · 送 lead final_report rev2 综合时收尾即可。

**不需 pydevd_v2 rev5 或 cpython_v2 rev3** · minor blocker 全部可由 lead 综合稿吸收(pydevd_v2 rev5 出与不出都不影响 skeptic rev3 lock 结论)。

**下一步**:通告 lead · skeptic v2 rev3 lock · 送 minor blocker 清单 · 主 blocker 已全 clear · lead 可综合 final_report rev2 · 送用户按 rev3 rank(η/ε/β/λ)决策。

---

## rev3 · pydevd_expert rev4 应答我 rev2 blocker 的评估

**背景**:pydevd_expert 已出 rev4(承 lead 5 项任务)· 我 rev2 blocker 中 pydevd_v2 三项(B.4/B.5/B.6)由 rev4 §5 直接应答。skeptic 独立评估。

### 逐条评估

| B.# | 我 rev2 blocker | pydevd_expert rev4 应答位置 | clear? |
|---|---|---|---|
| **B.4** | cache_skips 论证残留是否清理 | §5.6 认错清单明确撤 rev2 "cache_skips 短路是 M0 漂机制" · 承 cpython_expert 实验 2 PHASE 2 warm-up 直接证伪 | ✓ **完全 clear** |
| **B.5** | M1 反抗机制补 failure mode 分层表(mild/severe/cosmetic 三态) | §5.5 fail 1-5 降级路径覆盖 mild(fail 3/5 局部)/ severe(fail 2/4 破退 M2)/ cosmetic(fail 5 用户偏好)三态实操 · 未按 mild/severe/cosmetic 命名 · 但降级动作等价 | ✓ **实质 clear**(命名差异不阻塞) |
| **B.6** | landing 硬前置补 continue 后 clean-up + 观察工具 + IDE 视觉反馈 | §5.5 landing 6 条覆盖:反复 fire 检验(条 4 · 隐含 continue clean-up) · 变量面板检验(条 3 · 部分观察工具)· 未明列**观察工具**(用户如何在 PyCharm UI 判断 pause frame 是 debug_break 还是 caller · 除看行号外) · 未明列 **step-over UX vs breakpoint UX 视觉反馈差异** | ⚠️ **2.5/3 clear**(观察工具 + IDE 视觉反馈两项残留 · 非硬 blocker · 用户实测时自然感知) |

### M1 反抗机制 §5.2 源码走查独立复核

skeptic 独立读 rev4 §5.2 M0/M1 各 4/7 步源码路径 · 每步现场 grep pydevd 1.4.0 对齐 · **skeptic 无独立反驳**。M1 反抗从 rev1 挑到的 "纸面推理"升级为 "源码层可完整验证 · 唯一待实测 = IDE Java 侧行为"。**该 gap 在 skeptic 侧关闭**(交 user 现场实测)。

### skeptic rev3 立场

**pydevd_v2 blocker 主体 clear · 剩余等 cpython_v2 rev2**:
- cpython_v2 rev1 三份实验证伪 CPython / pydevd core / bytecode 三层 · 已充分
- cpython_v2 rev2(15 分钟 ETA · warm-up + print/`_=` 形式 anchor 对照)预期为**加强**而非**翻转**(cpython_expert 上一封说 "PHASE 2 warm-up 已跑 · 三处齐整反证 H2" · rev2 只是补 anchor 对照 fidelity)
- 若 cpython_v2 rev2 与 rev1 一致 · skeptic rev3 lock;若翻转(极不可能)· skeptic 可 rev4 补正

**推荐决策序不变**(rev2 已 lock):**η(3 分钟)→ M1 现场实测(5 分钟)→ M2 兜底**。η 强烈建议放决策序首位。

**skeptic 无自身 blocker**:交 lead 综合 final_report。

---

## 修订历史(rev3 补)

- rev0 / rev0.5 / rev1 / rev2:见上章节
- **rev3(2026-07-17):承 pydevd_expert rev4 §5.6 认错清单 + §5.2 M1 反抗源码走查 + §5.5 landing checklist 6 条 · pydevd_v2 3 项 blocker clear 2.5 项 · M1 反抗从 "纸面推理"升级为 "源码层可完整验证"。等 cpython_v2 rev2 · 预期为加强而非翻转 · skeptic rev3 立场 lock · 决策序不变(η→M1→M2)· 交 lead 合成 final_report**
- **rev4(本节 · 2026-07-17):承 pydevd_expert rev5 · rev3 minor blocker 6a/6b/5c 全 clear + η 评估强推 · 但独立坐实 rev5 §6.5 微修正错(下文)**

---

## rev4 · 承 pydevd_expert rev5 + catch §6.5 微修正错

### rev5 clear 情况

| rev3 minor blocker | rev5 应答 | skeptic 独立验证 | clear? |
|---|---|---|---|
| 6a dangling frame ref | §6.1 grep `pydevd_process_net_command.py` L196-214 · CMD_THREAD_RUN 显式 `pydev_step_cmd=-1` + `pydev_step_stop=None` + `pydev_state=STATE_RUN` 三处 reset | 独立 grep 现场同文件 L196-214:代码逐字对齐 rev5 描述(4 行显式 reset · 三处一致) | ✓ **完全 clear** |
| 6b 观察工具 | §6.2 加 landing 判据 9 · 用 PYDEVD_DEBUG log 区分 IDE drift / debug_break 短路 / pydevd bug 三态 | 现场 grep pydevd_utils.py L482-495 · PYDEVD_FILTERS env-var 机制存在 · PYDEVD_DEBUG 同源可用 | ✓ **clear** |
| 5c IDE 视觉反馈 | §6.3 承认 M1 状态栏可能显示 "Stepped over" · 加 landing 判据 10(soft cosmetic)· M2 side benefit 追加 "UX 语义 100% 与用户预期一致" | 逻辑合理 · 无需独立坐实(纯 UX 判断) | ✓ **clear**(soft · 用户自行接受) |
| η 方案评估 | §6.4 强推 η pre-check · 方案矩阵调整为 η → M1 → M2 三级 fallback · η 三种结果表 | 独立复核 η 依赖 PYDEVD_FILTERS 通过 PyCharm Settings push · 现场 grep utils.py 坐实 env-var 机制 · η 决策序可行 | ✓ **完全 clear · 决策序与 skeptic rev2/rev3 建议一致** |

### catch 一处 · §6.5 微修正数值反手错

pydevd_expert rev5 §6.5 声称 "微修正:CMD_SET_BREAK=**107**(rev4 §5.3 证据 4 写 111 错 · 需 lead 收尾统一)"。

**skeptic 独立验证**(现场 grep `pydevd_comm_constants.py`):
```
7:CMD_STEP_INTO = 107
8:CMD_STEP_OVER = 108
9:CMD_STEP_RETURN = 109
11:CMD_SET_BREAK = 111
```

**skeptic 判定**:**pydevd_expert rev4 §5.3 证据 4 的 "CMD_SET_BREAK=111" 才对** · rev5 §6.5 "微修正 = 107" **反手错** · 混淆了 CMD_STEP_INTO(=107)与 CMD_SET_BREAK(=111)。

**根 cause 推测**:pydevd_expert 可能是记住了 "M0 走 `_mark_suspend` 会 flip pydev_step_cmd 到 CMD_STEP_INTO(=107)" · 以为 stop_reason 也随之变化。实际上 · `set_suspend(t, stop_reason)` 的 stop_reason 参数是**调用方传的原值 CMD_SET_BREAK(=111)** · 与 pydev_step_cmd 是两个字段(前者传 IDE 消息 · 后者驱动 trace_dispatch 判断)· 各自独立。

**修正建议**:lead 综合 final_report 时用 111(rev4 §5.3 证据 4 原值)· 不采纳 rev5 §6.5 "107" 微修正。

### rev4 skeptic 最终立场

**pydevd_expert rev5 全体收敛**:6a/6b/5c/η 全 clear · M1 反抗机制源码走查(cpython_v2 rev2 实验 5 已完全实证 · rev5 §6.5 acknowledge)· **仅 §6.5 数值反手错需 lead 收尾修**。

**skeptic 无进一步 blocker · rev4 lock**。若 pydevd_expert 不出 rev6 修数值 · skeptic 已在本节明写正确数值(111)· lead 综合时直接用即可。

**决策序不变**(rev2/rev3/rev4 一致):**η(3 分钟)→ M1 现场实测(5 分钟)→ M2 兜底**。

**skeptic 交 lead 合成 final_report** · 无 outstanding blocker。
