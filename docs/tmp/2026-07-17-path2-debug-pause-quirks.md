# v3 role-gated debug · 手动验证暴露的两个 pause quirk

**日期**: 2026-07-17
**背景**: v3 SDD 已 landing(commits 79c1c8c..c84bcbd on gateA_notwork)· 用户在 PyCharm 里执行 Final Validation(FV2 · e2e checklist 场景 J1/J2/J3 · `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md`)时发现两个 pause 行为异常。**均非 v3 引入的 bug,是既有架构 + pydevd 语义,v3 role gate 恰好让它们暴露出来**。

## 问题 1 · 单次请求内 pause 触发两次

### 现象

用户 workflow(FV2 场景 J1/J2/J3):
- **选 entry**(marker 右键 → Debug tb entry):pause **两次** 到 `throwback.py:248`,而不是一次
- **选 trough**(marker 右键 → Debug tb trough):pause **两次**(位置见问题 2)
- **选 end**(marker 右键 → Debug tb end):pause **两次** 到 `throwback.py:217`,而不是一次

三个入口 D role 均"两次"—— 同一 root cause。

### Root cause

`path2_web/api.py::get_diagnose` L231 + L238:

```python
diag = _dag_diagnose(spec, win, None)              # ← 第 1 次跑 detector(per-role 诊断)
# ...
collector = attach_and_collect(spec)
try:
    result = _dag_analyze_engine(spec, win, None)  # ← 第 2 次跑 detector(analyze + gate_failures)
    result = dataclasses.replace(result, gate_failures=collector.snapshot())
finally:
    detach(spec)
```

`scope=time` 分支同一次请求内跑两次 detector · 每次都完整遍历 bo_stream 并触发 debug_break · 结果 = 单个匹配的 debug_break 被 fire 两次 · 用户 pause 两次。

**代码注释 L232-235 自陈**: "legacy 分派此前从未注入 gate_failures, `derive_response` 只能落 stub/caveat。复刻 `scan.py` 的 `attach_and_collect + analyze + detach + dataclasses.replace(gate_failures=...)` 套路(单股即时诊断,非批量 worker,**可接受重算成本**)。" —— Task 24 引入的有意架构选择。

### 影响范围

- 只影响 `/diagnose?scope=time`(入口 D 走这条 · 入口 A 走 legacy `scope=None`)
- 入口 A(brush)不受影响,因为 `scope=None` 走 legacy `diagnose_symbol(spec, win, ...)`,只跑一次 `_dag_diagnose` 无 `_dag_analyze_engine` 二 pass
- v2 时代就存在,只是没做入口 D marker 右键功能所以没暴露

### 修复方案候选

| 方案 | 做法 | 代价 | 收益 |
|---|---|---|---|
| **A · 架构** | Handler 合并两条 pass:让 `derive_response` 从 `attach_and_collect + analyze` 一条链路的产物派生 per-role diag,删除单独的 `_dag_diagnose(...)` 调用 | 大改 `derive_response` 消费面 · test 全 revalidate · scope 类似一个独立 refactor | 单次请求内只跑一次 detector · 所有 debug pause 数 = 1 |
| **B · 症状** | `debug_break` 内维护 `(bar, role, class_id) → seen` 全局 set · seen 过 skip · handler `finally` clear set | 简单几行 · 但引入 debug-only 全局状态污染 · 与 debug_ctx 的"stateless gate"哲学冲突 | pause 数 = 1 · 但架构变脏 |
| **C · 接受 + 文档化** | v3 e2e checklist 场景 J1/J2/J3 判据从"pause 一次"改为"pause N 次 · N = handler detector run 数(当前 = 2)" | 零改动 | pause 数不变 · 只是不再当 bug 报 |

### 与 v4 的解耦

**功能层完全解耦**:v4 A 线(class 门机制预留)+ v4 B 线(request-level backend cache)都不针对"单次请求内双跑"这个 pain。

**特别澄清 v4 B 线的 cache 不解决问题 1**:cache 是 **request-level**(同 URL 反复请求 → cache hit → 整个 response 直接返回)。**同一次请求内**的两次 detector run 不共享 cache,handler 内先跑 diag 后跑 analyze 都是 request 内,cache miss 时依然双跑。v4 B 消除的是"切换 filter 又重命中断点"那个 pain,不是"单次 brush 内部 pause 两次"。

**物理层部分重叠 handler**:v4 A(env 写入 + finally pop)+ v4 B(cache 分支)+ 问题 1 方案 A(改 diag/analyze 调用结构)都触 `api.py::get_diagnose`,但都是"补内容 · 不删原有" · 顺序执行无冲突。

**借势观察**:v4 B 做完后 handler 已经有 cache 结构。问题 1 方案 A 放 v4 之后做,可以顺势升级为"**一次 detector run · cache 里同时存 diag + analyze 双产物**",实施更简洁 · 借用 v4 B 的 cache 键结构。

---

## 问题 2 · trough pause 位置漂到下游函数 L200

### 现象

选 trough(FV2 场景 J2):
- pause 到 `_find_end_idx, throwback.py:200`
- **不是** trough 埋点 `throwback.py:163` 或其下一行 `throwback.py:164 return trough_idx`
- 截图 stack 顶显示:`_find_end_idx, throwback.py:200` → `evaluate_throwback, throwback.py:259` → `detect, throwback.py:323` → `run, runner.py:21` → `run_streams, engine.py:68` → `diagnose, diagnose.py:44` → `get_diagnose, api.py:231`

对比:选 end pause 在 `throwback.py:217`(L216 埋点的 return 行,正常);选 entry pause 在 `throwback.py:248`(L247 埋点的下一行,正常)。**只有 trough 漂**。

### Root cause(假设,未 100% 证实)

`pydevd.settrace(suspend=True)` 的 pause 语义是"下一次 Python `line` event 时 pause"。`return` statement 有 `RETURN_VALUE` bytecode 会触发 line event,但 pydevd 或 PyCharm 可能对纯 control-flow return 行做了跳过,直接停在下一 "meaningful" executable line。

trough(L163)fire → `_find_start_idx` L164 return trough_idx(**跳过**)→ `evaluate_throwback` L254 表达式完成 → L257 if 检查 → L259 调用 `_find_end_idx(...)` → **进入 `_find_end_idx` L200 `end_scan = min(...)`**(第一个 executable line · pause 在这)。

### 为什么 L216/L247 不漂 · L163 漂?

结构对比:

```python
# L163(漂)
if depth >= pullback_min_atr * atr:
    debug_break(trough_idx, role='trough')
    return trough_idx                       # ← 漂过

# L216(不漂)
if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
    debug_break(i - 1, role='end')
    return i - 1                            # ← 停在这

# L247(不漂)
debug_break(bo_idx, role='entry')
if bo_idx < 1 or bo_idx >= len(df):        # ← 停在这(if 不是 return)
    return None
```

L163 和 L216 结构几乎相同(都是 `debug_break` 紧跟 `return X`),但行为不同。这个不对称 pydevd 行为需要**实测 + 上网研究**才有确定解释。

### 已尝试的方案(失败)

用户明确要求实测"L163 后加形式 executable line 是否能让 pause 停在 caller"。**三种形式尝试均失败**(用户 2026-07-17 反馈):

1. `_ = trough_idx`(assignment)—— 未生效
2. 其他形式尝试(用户口头描述 · 具体未追问)—— 未生效
3. 第三种(用户口头描述)—— 未生效

结论:pydevd 在这个 context 下**更激进地跳过中间 statement**,连 assignment 也 skip · 需要更根本的方案(改触发机制,或改 debug_break 内部实现)。

### 影响范围

- pause 位置不对齐,导致 IDE 变量面板显示的是 `_find_end_idx` 的入参,**看不到 `trough_idx` / `depth` / `peak` 等局部变量**
- 想查这些变量需要手动点 stack 下一层 `_find_start_idx` frame · 每次 pause 多一步操作
- 与"快速定位"的 debug 初衷冲突 —— 用户明确表示"文档化便失去快速定位的意义"

### 修复方向候选

| 方案 | 做法 | 状态 |
|---|---|---|
| **α · 加形式 line** | L163 后加 assignment / 表达式 | ❌ **已 fail**(三种尝试均漂) |
| **β · 换触发机制** | 换用 `pydevd.set_next_statement(...)` / `pydevd_pycharm.settrace(...)` 或其他 API 强制 pause 位置 | 需上网研究 · 未启动 |
| **γ · 改 debug_break 内部** | `pydevd.settrace(suspend=True)` 调用点里加 stack frame 操作 · 强制 pause 位置对齐 caller | 需上网研究 · 未启动 |
| **δ · Python 3.12 `sys.monitoring`** | 用 Python 3.12+ 的新 monitoring API 替代 `settrace` · 更精细的 line event 控制 | 需上网研究 · 未启动 |
| **接受 + 文档化** | 无解决方案时的兜底 | 用户已明确表示**不接受**(失去快速定位意义) |

### 与 v4 的解耦

**功能层完全解耦**:v4 A(class 门)+ v4 B(cache)都不改 `debug_break` 内部触发方式 · 与 pydevd pause 位置无关。

**物理层**:
- 修复方案 γ / δ 只动 `debug_ctx.py` · **零触 throwback.py** · 完全解耦
- 修复方案 α(如果未来找到有效形式)会与 v4 A 线同触 throwback.py 5 处埋点 · 但都是"补内容 · 不删原有" · 顺序执行无冲突

---

## 综合决策(2026-07-17 待用户拍板)

### 决策 1:两个问题的处理时序

**推荐**:两问题合并为独立立项(暂称 **v4.5 debug UX 批次**),v4 结束后再开。

理由:
- v4 spec 已定稿(`docs/research/2026-07-16_path2-web-event-class-filter-redesign/final_report.md` R1-R12),可立即展开 impl · 无阻塞
- 问题 1 修复(方案 A)需要设计 spec(`derive_response` 如何从 analyze 派生),有工作量
- 问题 2 修复(方案 β/γ/δ)没有解决方案,需先研究 pydevd 语义
- 让"没解决方案"的 quirk 阻塞 "已 spec 好"的 v4 是无意义等待
- 问题 1 修复放 v4 后可**借势** v4 B 的 cache 键结构 · 实施更简洁

### 决策 2:是否现在并行启动 research agent

**候选**:派一个 general-purpose / tom research agent 并行调研 pydevd `settrace(suspend=True)` 的 pause 位置行为 · 产出方案对比文档到 `docs/research/2026-07-17_pydevd-suspend-pause-position/final_report.md` · **不改代码**。

调研方向:
- pydevd `settrace(...)` 的完整参数列表(是否有 `strict_pause` / `explicit_line` 类选项)
- `pydevd_pycharm` 专用 API 是否能强制 pause 在 caller line
- Python 3.12 `sys.monitoring` 新 API 是否可替代 · 位置控制是否更精细
- Community workaround:GitHub issues / StackOverflow 是否有"pydevd suspend 跨函数漂移"的已知 workaround
- 为什么 L216(return-follow)不漂 · L163(return-follow)漂 —— 这个不对称的具体机制

调研**只读 · 不改代码 · 产出方案对比 · 不阻塞 v4 impl**。

### 决策 3:v3 Final Validation 是否继续

- FV1(J1 · 入口 A brush):不受影响 · 可继续
- FV2(J2 · 入口 D entry/trough/end):受问题 1(pause 两次)+ 问题 2(trough 位置)影响 · **判据需暂时改为**"pause 两次,trough stack 顶为 `_find_end_idx` · 均为已知 quirk"
- FV3(J3 · scope=time 边界):不受影响 · 可继续
- FV4-FV6:不受影响 · 可继续

---

## 关联文件

- v3 SDD progress: `.superpowers/sdd/progress.md`
- v3 e2e checklist: `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md`
- v4 spec: `docs/research/2026-07-16_path2-web-event-class-filter-redesign/final_report.md`
- 涉及代码:
  - `path2_web/api.py:198-254`(`get_diagnose` handler · 问题 1 root cause)
  - `path2/debug_ctx.py`(问题 2 修复可能触及)
  - `path2/atoms/throwback.py:104,163,216,221,247`(5 处 debug_break 埋点)
