# pydevd `settrace(suspend=True)` pause 位置漂移 · Team Final Report(rev2)

**日期**: 2026-07-17
**Rev**: rev3(**用户 2026-07-17 现场实测采纳 λ · 本任务落地** · rev2.2 三方 lock 综合 + rev3 追加实测结果)
**Team**: pydevd_expert(rev1→rev4 · v2 承接出 rev5)· cpython_expert(rev1 · v2 承接出 rev2 + rev3)· pause_skeptic(rev0.5→rev1 · v2 承接出 rev3→rev4 lock)· lead(主会话综合)
**归档**: `docs/research/2026-07-17_pydevd-suspend-pause-position/`
**触发**: v3 role-gated debug landing 后手动验证(FV2 场景 J2)发现选 trough pause 落 `_find_end_idx:200` 而非 `_find_start_idx:164`
**背景**: 详见 `docs/tmp/2026-07-17-path2-debug-pause-quirks.md` 问题 2

---

## rev3 · 用户 2026-07-17 现场实测结果(**任务落地**)

**采纳方案 · M1 + λ 组合**(M1 代码 `stop_at_frame=sys._getframe(1)` + λ env var `USE_LOW_IMPACT_MONITORING=1`)· **两者缺一不可**。

**实测路径**:
- **η 排除**:PyCharm 2026.1 Settings → Build/Execution/Deployment → Debugger → Stepping · "Do not step into scripts:" checkbox 未勾 + 列表空 · debug_ctx.py 不在 skip 列表 · η 不适用
- **M1 fail-mild**:改 debug_ctx.py 加 `stop_at_frame=sys._getframe(1)` + throwback.py L104 gate 显式传参 · 现场跑 FV2 J2 · **pause 仍漂到 `_find_end_idx:203` 附近** · pydevd 层 stop_at_frame 已生效(cpython_v2 实验 5 已证)· 但 IDE Java 侧对 caller frame 又 auto-step 到 downstream(印证 skeptic rev1 §B.5 5a 风险)· M1 代码已 revert
- **λ 单独 fail**(**2026-07-17 用户后续实测发现 · 推翻早前"λ 秒解"结论**):仅加 env var `USE_LOW_IMPACT_MONITORING=1`、注释掉 M1 代码后 · trough pause **仍漂到 `_find_end_idx:201`** —— pydevd 的 PEP 669 impl 里 `py_return_callback` 可能也走某种 SUSPEND 分支(与 cpython_v2 rev2 mock 分析不同 · 或 IDE 侧对 PY_LINE 事件也 auto-step)· pause frame 仍是 debug_break · IDE 侧同样 auto-step 到 downstream
- **M1 + λ 组合 pass**:M1 代码(debug_ctx.py 的 `stop_at_frame=sys._getframe(1)` + throwback.py L105 gate 显式传参)+ λ env var 一起启用:
  - **入口 D trough** → `throwback.py:164`(`_find_start_idx` 内 · 精确对齐 debug_break L163 之后 · 变量面板显示 `trough_idx` / `depth` / `peak`)✓
  - **入口 A brush gate** → `throwback.py:152`(`_find_start_idx` 循环体 · pause 甚至跳过 `_emit_tb_gate` wrapper · 直接落 detector 层 · 变量面板显示 `i` / `measured_support` / `anchor` / `bo_idx`)✓
  - **反复 fire** · 同请求内多次触发都能停 ✓
  - **entry / end / end-timeout 不 regress** · pause 位置对 · 无消失 ✓
- **α 残留清理**:trough 埋点 L164-166 的 3 行形式尝试(`print` / `_ = trough_idx + 0` / `_ = trough_idx`)已清除

**结论**:**真解 = M1 代码 + λ env var 组合** · **两者缺一不可**:
- **M1 单独**(sys.settrace + stop_at_frame):pydevd 层传 caller frame · 但 IDE Java 侧对 CMD_STEP_OVER 消息也 auto-step · fail-mild
- **λ 单独**(PEP 669 + M0 settrace):事件源换了 · 但 pause frame 仍是 debug_break · IDE 同样 auto-step · fail
- **M1 + λ**:PEP 669 事件源 + caller frame · IDE 侧对这个组合**没有 auto-step 逻辑** · pause 落对

**推测**:PyCharm Java 侧的 return-event auto-step-to-downstream 逻辑挂在 (sys.settrace 事件源 OR CMD_SET_BREAK stop_reason) 上;M1 换 stop_reason 到 CMD_STEP_OVER 但仍触发 auto-step;λ 换事件源但 pause frame 仍是 helper;两者同时才让 IDE 匹配不上任何 auto-step 分支。这个推测**只能推测 · 无源码坐实**(agent 无法读 IDE Java 侧代码)· 但实测数据支持。

**Landing 落库**(建议用户执行 · 二选一或都做):
1. PyCharm Run Configuration → Environment variables → 加 `USE_LOW_IMPACT_MONITORING=1`(仅本地 · 不入 git)
2. 项目 README 或 `.claude/docs/modules/path2.md` / `path2_web.md` 加"debug 需 `USE_LOW_IMPACT_MONITORING=1` env var(PEP 669 pydevd 事件源 · 让 pause 落 detector 层 · 避免 PyCharm 对 return-event 的 auto-step-to-downstream UX)"提示

---

## TL;DR · rev2 关键升级

**推荐决策序**(rev3 已由用户实测收敛为采纳 λ · 保留 4 级 fallback 供未来 IDE 变更时参考):**η(3 分钟)→ λ(3 分钟)→ M1 现场实测(5 分钟)→ M2 兜底**。

- **η · IDE Skip Files pre-check**(零代码 · 用户 3 分钟):PyCharm Settings → Build/Execution/Deployment → Debugger → Stepping → "Do not step into files" 检查 `path2/debug_ctx.py` 是否在自动 skip 列表 · 若在移出后重跑 FV2 J2。**skeptic 强烈建议放决策序首位** —— 若 IDE Skip Files 是 root cause · 秒解 · 无 M1/M2 都不需要
- **λ · `USE_LOW_IMPACT_MONITORING=1` opt-in**(零代码 · env var):切 pydevd PEP 669 事件源 · M0 pause frame 自然落 caller · 与 M1 效果相似 · 但依赖 PEP 669 IDE 兼容(未测)
- **M1 · `stop_at_frame=sys._getframe(1)`**(代码 1 行 · 用户 5 分钟实测):**pydevd 层反抗机制已完全实证**(cpython_v2 实验 5 · CMD_STEP_OVER=108 · pause frame=caller · event=line 三 anchor 全对齐)· 唯一未测环 = IDE Java 侧对 caller frame 收到后是否真不 skip
- **M2 · 移埋点到 caller**(trough 1 处):100% pydevd-agnostic 无 IDE 依赖兜底 · 丢内部局部变量视图换稳定

**rev1 → rev2 关键变化**:

1. **决策序前置** η/λ 零代码探索(rev1 直接跳 M1)· 若 η 或 λ 通过则本任务不启动
2. **drift 归因软化**:rev1 "drift 100% 在 PyCharm IDE Java 侧" → rev2 "drift 归因 = pydevd/CPython 层无 · IDE 侧行为 **或** pydevd + IDE 交互路径 · 二选一 · 需实测收窄"(理由:cpython_v2 mock 未覆盖 IDE 回发命令场景 · 100% 是过判)
3. **M1 反抗机制升级**:rev1 "源码 grep 可证 · 待实测" → rev2 "**pydevd 层完全实证**(cpython_v2 实验 5)· 唯一未测 = IDE Java 侧"
4. **新增 λ / κ 方案**:λ = PEP 669 opt-in 事件源切换;κ = 5 处埋点全显式传 frame(M1 gate 办法 A 的推广 · 与 v4 A 线同批 rebase)
5. **M1 failure mode 分层表**:pass / fail-mild / fail-severe / fail-cosmetic 四态 · 每态判据 + 回退策略
6. **Landing 判据从 5 条扩到 10 条**:补 continue 后 clean-up 确认(CMD_THREAD_RUN 显式 reset · rev5 §6.1)+ 观察工具(PYDEVD_DEBUG=1 log · rev5 §6.2)+ IDE 状态栏视觉判据(soft · rev5 §6.3)

---

## Team v2 共识(rev2 认证 · 三方独立坐实)

### drift 根因(rev2 收窄)

- **pydevd/CPython 层无 drift**(cpython_v2 实验 1-2-3-4-5-6-7 六轮独立坐实)
  - 实验 1 · raw sys.settrace 三 anchor 齐整落 return · **H1 排除**
  - 实验 2 · 真 pydevd 1.4.0 mock IDE + PHASE 2 warm-up cache_skips · 三 anchor 精确落 debug_break return · **pydevd core dispatch 层无不对称**
  - 实验 3 · bytecode dis 复刻 · 3 层嵌套 if 与 1 层 if 都正确 attribute 到 return 行 · **H3 复刻场景排除**
  - 实验 4 · 直 dis 真 throwback.py 全 12 处 return · 全独立 line 归属 · **H3 全场景全线证伪**
  - 实验 5 · 独立复核 M1 反抗机制 · 拦截 do_wait_suspend 拿到 pydev_step_cmd=108 + pause frame=caller + event=line 三 anchor 全对齐 · **M1 pydevd 层机制完全实证**
  - 实验 6 · in_project_scope 对 debug_ctx.py + throwback.py 都判 True(agent 默认 + 模拟 PyCharm 场景)· **pydevd Python 层 filter 不足以解释 drift 不对称**
  - 实验 7 · 覆盖 skeptic 2a/2b 剩余 gap(rev3 补):**PHASE A** 让 `_find_start_idx` / `_find_end_idx` / `evaluate_throwback` 三个 code object 各自 fire debug_break 让 cache_skips 真填满 → **pause 位置零变化**;**PHASE B** mock 主动 flip `pydev_step_cmd=CMD_STEP_OVER` 模拟 IDE 收到 pause 后回发 step 命令 → **pause 位置零变化**(下次 settrace 覆盖 pydev_step_cmd) · skeptic rev4 判定从"部分 clear(agent 环境天花板)"升级为**"实证 clear"**
  - 实验 7 mini(承 pydevd_v2 rev4 §5.1/§5.3 请求 · cpython_expert 追加 · 决定性数据):**M0 do_wait_suspend 从 `pydevd_frame.py:755` 调用**(L754/755 STATE_SUSPEND early-return 分支 · event=return · step_cmd=107)· **M1 do_wait_suspend 从 `pydevd_frame.py:892` 调用**(CMD_STEP_OVER line 分支 · event=line · step_cmd=108)· **M0 抢先 L754 直接把 debug_break frame 传出 · 完全绕过 L893-923 "return→caller" 转换代码** · 与 pydevd_v2 rev4 M0 4 步 + M1 7 步源码走查逐字对齐 · **消除了 M1 反抗机制的所有纸面残留**(除 IDE Java 侧 skip 行为一环 · 需用户实测)

- **drift 归因 = 二选一**(rev2 软化 · 承 skeptic C.8 8a + cpython_v2 Gap 2c):
  - **A 侧 · IDE Java 端行为**:PyCharm 客户端对 pydevd `thread_suspend` 消息的二次处理 · Skip Files 用户配置 / "Just My Code" 启发式 / return-event UX auto-step 到 caller frame
  - **B 侧 · pydevd + IDE 交互路径**:PYDEVD_FILTERS env var 由 IDE 侧 push 到 pydevd 层 · pydevd 内部 filter check 只在 `is_stepping=True` 时触发(pydevd_v2 rev4 §5.3 证据 2)· M0 因 `_mark_suspend` 会把 `pydev_step_cmd` 从 -1 flip 到 `CMD_STEP_INTO` · 所以 M0 也是 is_stepping=True · filter 可能生效
  - **agent 无法启 PyCharm · 二选一需用户实测收窄** —— 与 M1 landing 硬前置是同一件事

- **pydevd_frame.py L889-923 是 IDE UX 需求的显性证据**(pydevd_v2 rev4 §5.1):pydevd core 团队在 CMD_STEP_* 分支里明确实现了 "return event pause 应显示 caller frame" 的转换(注释 `# if we're in a return, we want it to appear to the user in the previous frame!`)· 只是 M0 CMD_SET_BREAK 走的是 L754 SUSPEND early-return 路径不走 L889-923 · **IDE Java 端若要给用户一致 UX 大概率自己实现了类似 auto-forward 逻辑**(间接证据 · 无法坐实 IDE 内部实现)

### 三方独立会师同一核心方案

- **pydevd_v2 M1** = **cpython_v2 出口 A** = **skeptic_v2 β**:三方从不同路径(pydevd 源码 grep / CPython trace 实验 / 独立方案 rank)独立指向同一 API:`pydevd.settrace(stop_at_frame=sys._getframe(1))`
- cpython_v2 实验 5 是 pydevd_v2 rev4 §5.2 源码走查的**直接实证**(不再是"源码可复验的推理链" · 是 mock 环境下的实测数据)

### 过判撤销清单(rev2 承接)

- rev1 "H1/H2/H3 不对 M1 生效性构成影响" —— pydevd_v2 rev2 认错
- rev2 "cache_skips 短路是 M0 漂移真机制" —— pydevd_v2 rev4 认错(cpython_v2 独立读 `_mark_suspend` L983-986 证伪 · M0 也 flip 到 CMD_STEP_INTO · is_stepping=True · 与 M1 一样不进 cache_skips 短路;PHASE 2 warm-up 实测直接反证)
- rev3 "H3 是 M1 唯一硬 gating" —— pydevd_v2 rev4 撤(cpython_v2 实验 1/4 已直接坐实 H3 不成立)
- rev4 §5.3 证据 4 **"CMD_SET_BREAK = 111" 是正确值**(pydevd_comm_constants.py L11 现场坐实);rev5 §6.5 曾误改为 107 是**反手错** —— 把 cpython_v2 实验 5 实测的 `pydev_step_cmd=107=CMD_STEP_INTO`(`_mark_suspend` L983-986 flip 后值)当成 `stop_reason` · 两字段独立不可混。已被 skeptic_v2 rev4 catch + pydevd_v2 rev5 §6.5 撤销块承认 + cpython_expert 独立 grep `_pydevd_bundle/pydevd_comm_constants.py` L5-11 坐实(**三方独立收敛**)。**正确对照**:pydev_step_cmd(M0=107=CMD_STEP_INTO · M1=108=CMD_STEP_OVER)· stop_reason(M0=111=CMD_SET_BREAK · M1=108=CMD_STEP_OVER)
- rev4 "M1 一次改动覆盖 5 埋点" —— rev5 §6.6 修正:M1 直接覆盖 **4 处**(trough/end/end-timeout/entry)· gate 埋点需办法 A 补 kwarg(1 处 throwback.py 显式传参)
- rev4 §"drift 100% 在 IDE Java 侧" —— rev2 本文软化(cpython_v2 mock 未覆盖 IDE 回发命令场景)

---

## 推荐决策序 · 4 级 fallback

用户按下列顺序操作 · 前一级通过则后续不启动:

### 第 1 级 · η · IDE Skip Files pre-check(**首推** · 3 分钟 · 零代码 · 无 rebase 风险)

**操作**:
1. PyCharm Settings → Build/Execution/Deployment → Debugger → Stepping → **Do not step into files**
2. 检查列表是否包含 `path2/debug_ctx.py` 或匹配通配符(如 `**/debug_ctx.py` 或 `**/*_ctx.py`)
3. 若在 · 手动 remove
4. 重跑 FV2 场景 J2(选 trough anchor 触发)· 观察 pause 位置

**判据**:
- **通过**:pause 落 `throwback.py:164 return trough_idx` · **本任务完成** · 无需 M1/M2 · 文档化 IDE 配置步骤(推荐加入项目 README 或 .idea/ 提示)
- **不通过**:drift 不在 Skip Files 层 · 进第 2 级

**η 的三种可能结果**(pydevd_v2 rev5 §6.4):
| 结果 | 处理 |
|---|---|
| debug_ctx.py 在 Skip Files · remove 后 pause 不漂 | **η 秒解** · 收工 |
| debug_ctx.py 不在 Skip Files · pause 仍漂 | drift 不在 Skip Files 层 · 走 M1/λ |
| debug_ctx.py 不在 Skip Files 但 IDE 仍 skip | drift 在 IDE Java 侧的 "Just My Code" 或 helper 启发式(非 Skip Files 层)· 走 M1/λ |

### 第 2 级 · λ · `USE_LOW_IMPACT_MONITORING=1` opt-in(**次推** · 3 分钟 · 零代码 · env var)

**操作**:
1. 在启动 uvicorn 时加环境变量 `USE_LOW_IMPACT_MONITORING=1`(或 shell export)
2. 重跑 FV2 场景 J2 · 观察 pause 位置

**原理**:切 pydevd 从 sys.settrace 路径到 PEP 669 路径。PEP 669 M0 的 `py_return_callback` **无 STATE_SUSPEND 分支**(cpython_v2 rev2 §sys.monitoring 独立坐实)· CMD_SET_BREAK 只在 `py_line_callback` 触发 · pause frame **自然落 caller** · 与 M1 效果相似 · 但**不改代码**。

**判据**:
- **通过**:pause 落 `throwback.py:164` · **本任务完成** · 记环境要求
- **不通过 · pause 仍漂**:PEP 669 IDE 侧行为可能同样触发 skip · 进第 3 级
- **不通过 · debug 挂 / 其他 pydevd 错乱**:PEP 669 impl 未完全 mature · λ 破 · 直进第 3 级(M1)

**λ 的风险**:PEP 669 IDE 侧行为未测(与 M1 landing 硬前置同一 blocker)· pydevd 1.4.0 PEP 669 实现完整度未 100% 验证 · 是**软兜底而非零风险**。

### 第 3 级 · M1 · `stop_at_frame=sys._getframe(1)`(代码 1 行 · 5 分钟实测)

**代码改动**:

`path2/debug_ctx.py::debug_break` 内 `pydevd.settrace(...)` 调用:

```python
try:
    import pydevd
    import sys
    pydevd.settrace(suspend=True,
                    stop_at_frame=stop_at_frame or sys._getframe(1))  # ← M1 改动
except ImportError:
    breakpoint()
```

同时 debug_break 签名加可选 kwarg `stop_at_frame=None` · gate 埋点侧显式传参(见 §"gate 埋点方案矩阵")。

**判据**:见 §"M1 landing 硬前置 10 条 + failure mode 分层表"

### 第 4 级 · M2 · 移 trough 埋点到 caller(兜底 · 100% pydevd-agnostic)

**代码改动**:

`path2/atoms/throwback.py::evaluate_throwback` 内(当前 L257 附近):

```python
start = _find_start_idx(...)
if start is None:
    return None
debug_break(start, anchor_kind='trough', class_id='tb')   # ← trough 埋点上移
end = _find_end_idx(...)
```

同时删除 `_find_start_idx` L163 的原 debug_break。

**代价**:丢 `_find_start_idx` 内的 `depth` / `peak` / `trough_idx` 中间值(需点 stack 进一层)· 换 100% pydevd-agnostic 无 IDE 依赖。

**M2 side benefit**(rev5 §6.3):M2 走原 breakpoint 语义 · IDE 状态栏显示 "paused at breakpoint" · **UX 语义 100% 与用户预期一致**(与 M1 状态栏可能显示 "Stepped over" 相比)。

---

## M1 landing 硬前置 10 条 + failure mode 分层表

### Landing checklist(rev5 覆盖 rev4 6 条 + skeptic rev3 补 4 条)

**必过条件**(全过才算 M1 landing):

1. [**必过**] cpython_v2 rev2 实验 5 已实证 · **不再是 gating**(pydev_step_cmd=108 · pause frame=caller · event=line 三 anchor 全对齐)
2. [**必过**] 用户 PyCharm 2026.1 现场用真 tb debug 一次实测(FV2 场景 J2 · 选 trough anchor 触发)· pause 落在 `throwback.py:164 return trough_idx` 而非 `_find_end_idx:200`
3. [**必过**] 变量面板显示 `trough_idx` / `depth` / `peak` 等 phase1 局部变量(证明 top frame 真是 `_find_start_idx` 而非 debug_break)
4. [**必过**] 反复 fire 语义不变(commit 8cd2e7c 硬要求)· 同一请求内多次触发 debug_break 都能停(把 L163 的 range 设成命中多次 · 观察 pause 次数)
5. [**必过**] entry / end / end-timeout / gate 无 regression:原本 "不漂" 的场景保持 "不漂" · gate 埋点(采办法 A/κ)pause 落 detector 层
6. [**已 confirm**] Continue 后 `pydev_step_stop` clean-up(rev5 §6.1):CMD_THREAD_RUN 显式 reset `pydev_step_cmd=-1 / pydev_step_stop=None / pydev_state=STATE_RUN` · **无 dangling frame ref 风险** · 无需用户额外验证
7. [**观察工具**] 若 M1 pause 未按预期触发 · 用 env `PYDEVD_DEBUG=1` 启 pydevd log(rev5 §6.2)· 观察 `do_wait_suspend(...)` 是否真调用:
   - `do_wait_suspend` 被调用 · IDE 未显示 pause → **drift 到 IDE 侧 · M1 fail-severe · 直切 M2**
   - `do_wait_suspend` 未被调用 · debug_break 短路了 → 检查 env 4 层 gate(DEBUG_MODE / DEBUG_BAR_RANGE / DEBUG_ANCHOR_KIND / DEBUG_EVENT_CLASS)· 与 M1 无关
   - 4 层 gate 全过但 `do_wait_suspend` 未调用 → pydevd 层 bug · 报 issue 到 pydevd 上游
8. [**soft · 视觉反馈**] pause 触发后 · 用户观察 PyCharm 状态栏文字(rev5 §6.3):
   - 显示 "Paused at breakpoint" 或类似 breakpoint 状态 → **完美 M1 pass**
   - 显示 "Stepped over" 或类似 stepping 状态 → **M1 fail-cosmetic**(pause 位置对 · 状态文字令人困惑)· 用户自行决定是否接受 · 不接受 → 退 M2
9. [**软过**] VSCode / Cursor 未 revalidate · 非当前 blocker(现场用 PyCharm)· 但如未来切 IDE 前需过 landing 1-5 全套
10. [**协作**] gate 埋点采办法 A 或 κ · debug_ctx.py 签名 backward-compat(可选 kwarg · 老 callers 不传就走 default)

### M1 failure mode 分层表(承 skeptic rev2 §B.5)

| 场景 | M1 行为 | 用户观察判据 | 分层回退策略 |
|---|---|---|---|
| **M1 pass** | pause 落 `throwback.py:164 return trough_idx` · 变量面板显示 trough_idx | 一次实测 confirm | **采纳 M1** + gate 办法 A/κ |
| **M1 fail-mild** | pause 落 caller frame 但 IDE 再 auto-step 跳到下游 | 用户观察 = 与 M0 现象等价("漂到 `_find_end_idx:200`") | 直切 **M2**(ε 移埋点 · trough 一处) |
| **M1 fail-severe** | pause 完全消失 · IDE auto-step + CMD_STEP_OVER walk 链一路走到 detector 外 | 用户按 debug 后 detector 跑完不停 · 无 pause | **优先回滚到 M0** 再退 M2(避免用户以为 debug 挂了 · 断点消失比漂更痛) |
| **M1 fail-cosmetic** | pause 位置对 · 但 IDE 显示 "stepping" 而非 "breakpoint" | pause 停对位置但状态栏文字不同 | 用户偏好决定(可接受 = 采纳;不可接受 = 退 M2) |

分层判据比"一态 landing / 一态 fail 退 M2"更精准 · **fail-severe 是新故障**(pause 消失比漂位置更痛)· 不是 fail-mild 的加剧。

---

## gate 埋点方案矩阵(A/κ/C)

`_emit_tb_gate` L104 里的 `debug_break(gate_idx, anchor_kind='gate', class_id='tb')` · `sys._getframe(1)` = `_emit_tb_gate` frame(wrapper 层)· 而不是 detector 内(`_find_start_idx` / `_find_end_idx`)· 若采 M1 默认策略 pause 落 L105 `on_gate(...)` · 用户拿不到 `depth`/`peak`/`i`/`atr` 上下文。

三个方案:

### 办法 A · gate 埋点侧显式传参(**pydevd_v2 推荐**)

- **改动**:debug_break 签名 +1 可选 kwarg `stop_at_frame=None` · `_emit_tb_gate` 内传 `stop_at_frame=sys._getframe(1)` · 其他 4 处埋点零改动走 default
- **代价**:debug_ctx.py 签名 +1 kwarg · throwback.py L104 1 处显式传参(加 3 字符 `sys` import + kwarg)· backward-compat 完美
- **适用**:M1 采纳时的默认选择(v3 契约兼容度最高)

### 办法 κ · 5 处埋点全显式传 frame(**skeptic 推荐 · 与 v4 A 线合并优雅**)

- **改动**:每处 debug_break 改成 `debug_break(..., stop_at_frame=sys._getframe(1))` · 埋点侧决定 caller
- **收益**:每处埋点独立控制 · gate 埋点可传 `_getframe(0)` 停在 gate 侧或 `_getframe(1)` 停在 detector 层 · 任意变体细粒度可选;**消除办法 A 的"gate 例外"抽象泄漏**
- **代价**:throwback.py 5 处埋点各加 kwarg · **但与 v4 A 线补 `class_id='tb'` 是同批改动** · rebase 一次 landing 二价值
- **不豁免 IDE 反抗风险**:κ 只是把"传哪个 frame"的决定权从 debug_ctx 移到埋点侧 · 不能救 M1 的 IDE 反抗风险(与 A 同等 landing 硬前置)
- **skeptic 立场**:κ 是 A 的推广 · 抽象干净 · v4 A 线合并优雅

### 办法 C · 接受(兜底之兜底)

- gate 埋点默认停 `_emit_tb_gate` L105 · 用户点 stack 上一层看 detector 上下文(与当前 M0 漂痛度相当 · 位置从下游变旁支)
- 若 A/κ 都因某种理由不可行

**Team 立场**:M1 采纳时 **办法 A 或 κ 二选一** · 视是否与 v4 A 线并 rebase 决定:
- 分开 landing(v4 先 · 本任务后) → **办法 A** 更简
- 合并 landing(v4 + 本任务一批) → **办法 κ** 更清

---

## 已证伪的方向(不再考虑)

| 方向 | 证伪证据 |
|---|---|
| **α · 加形式 executable line**(L163 后加 `_ = trough_idx` 等) | 用户 2026-07-17 现场实测 3 种形式全 fail(`print` / `_ = trough_idx + 0` / `_ = trough_idx` 都无效) · 与 cpython_v2 实验 1/2/4 一致(CPython/pydevd core 层本来就没漂 · 加多少行都不改 IDE 侧行为) |
| **γ · `set_next_statement` API** | 是"手动改 next 执行行"(jump-to-line goto 用法)· mutates running frame · 与 settrace-suspend 语义不匹配 · skeptic 独立判"危险不推荐" |
| **δ · sys.monitoring 单飞**(不通过 pydevd) | cpython_v2 明确排除 · 已被 λ 收编(λ 是 "pydevd 已有 PEP 669 实现 · env var opt-in 即可" 的正确表述 · δ 是 "在 pydevd 之外自建 monitoring consumer" 会与 pydevd 抢 monitor slot 打架) |
| **ι · sys.settrace 手动 attach**(不通过 pydevd) | 与 pydevd 争 trace hook · sys.settrace 只有一个 tracer slot · 覆盖后 pydevd 自身 trace 停 · debugger 挂 |
| **θ · 挪 debug_ctx 出 helper 目录** | η 证实 root cause 后的 workaround · 侵入面较大(touch 6 处 import)· 若 η 就能秒解不需要 θ |

---

## 与 v4 的解耦(需注意 merge 冲突)

### 功能层完全解耦

- v4 A 线(class 门机制预留):`debug_break` 加 `class_id` kwarg + 5 处埋点补 `class_id='tb'`
- v4 B 线(handler cache):request-level cache
- η / λ:零代码
- M1(办法 A):debug_ctx.py 加 `stop_at_frame` kwarg + gate 埋点 1 处显式传参
- M1(办法 κ):5 处埋点全显式传 `stop_at_frame`
- M2:移 trough 埋点

**关注面正交** · 独立 spec / plan / impl / revert。

### 物理层冲突预警

| 方案 | 与 v4 A(埋点加 class_id) | 与 v4 B(handler cache) |
|---|---|---|
| **η / λ** | 无冲突(零代码) | 无冲突 |
| **M1 办法 A** | 与 v4 A 同触 throwback.py L104(gate 埋点补 stop_at_frame + class_id)· 需 rebase 但"补内容不删原有"顺序执行无冲突 | 无冲突 |
| **M1 办法 κ** | 与 v4 A 同触 throwback.py 5 处埋点行 · **rebase 一次 landing 二价值**(推荐同批) | 无冲突 |
| **M2** | 与 v4 A 同触 throwback.py 该 1 处埋点行 · 需 rebase | 无冲突 |

### 时序推荐(pydevd_v2 rev5 + skeptic_v2 rev3 一致)

**η/λ 前置**(可立即做 · 零代码 · 无 rebase 风险):
- η 探索若通过 · 本任务完成 · v4 独立走
- λ 探索若通过 · 本任务完成 · v4 独立走

**η/λ 都不通过**:v4 先展开 impl · 本任务作为独立 v4.5 立项 · v4 landing 后再做:
- v4 spec 已定稿(final_report R1-R12)· 立即可展开 impl
- 本任务 landing 需用户现场实测 · gating 卡在人不在 team
- 本任务放 v4 后可**借势** v4 A 已 landing 的 5 处埋点结构 · 若走办法 κ 实施更简洁

### 不解决问题 1(pause 双 fire)

η/λ/M1/M2 都只改 pause 位置 · 不改 fire 次数。问题 1(handler `_dag_diagnose` + `_dag_analyze_engine` 双跑 detector)与本任务完全正交 · 修复方向见 `docs/tmp/2026-07-17-path2-debug-pause-quirks.md` 问题 1 章节。

---

## 严重度定级(skeptic 独立 · team 未反对)

**P3 · cosmetic annoyance** —— 不是 P1/P2 blocker:

- 单次成本 = 约 1 次点击 · 亚秒级 · 无信息丢失(stack 完整 · 变量面板可切)
- workflow 频次 = 日 1-2 次点击(entry/trough/end 三条中只有 trough 漂 · debug 频次本来低)
- 无功能丢失 · 无正确性风险
- 有明确 stack 导航兜底

**用户明确"失去快速定位便失去意义"是偏好** vs **绝对痛度错位** —— team 立场是**尊重用户偏好**但**拒绝为满足此偏好接受高侵入面 workaround**(如 γ/δ)。η/λ/M1/M2 都是低侵入 · 落在偏好可接受范围。

---

## 下一步 · 待用户决策

### 决策 1 · v4 vs 本任务时序

**team 推荐**:
- **η/λ 前置探索**(3+3 分钟 · 零代码 · 无 rebase 风险 · 立即可做)
- η 或 λ 通过 → 本任务完成 · v4 独立走
- 都不通过 → v4 先展开 impl · 本任务放 v4 后(v4.5 独立立项)

**alternative**:若你倾向先修 debug UX pain · 也可跳过 η/λ 直接做 M1 现场实测 · 通过则 v4 A 线要注意 rebase(补 class_id 时保留 M1 的 debug_break 内部改动)。

### 决策 2 · 现场 5 分钟探索(η + λ 组合)

**立即可做**:

1. **η**:PyCharm Settings → Debugger → Stepping → Do not step into files · 检查 debug_ctx.py · 若在移出 · 跑 FV2 J2 · 观察 pause
2. **λ**(η 不通过时试):shell export `USE_LOW_IMPACT_MONITORING=1` · 重启 uvicorn · 跑 FV2 J2 · 观察 pause
3. **都不通过** → 采 M1 或 M2:
   - M1 实测(landing checklist 10 条)· 通过 → 采纳 · gate 埋点用办法 A(v4 后)或 κ(v4 同批)
   - M1 fail(见 failure mode 分层表)→ M2 兜底

### 决策 3 · gate 埋点办法选(M1 采纳后)

- **办法 A**(pydevd_v2 推荐):v4 后独立做 · 简单 · debug_ctx.py 签名 +1 kwarg · throwback.py L104 1 处显式传参
- **办法 κ**(skeptic 推荐):v4 A 线同批 · 与 补 class_id='tb' 一起改 5 处 · rebase 一次 landing 二价值
- **办法 C**(接受):不做 gate 埋点 caller-perfect · 用户点 stack 上一层看 detector 上下文

---

## 关联文档

### 中间稿(team v1 + v2 讨论过程 · 供未来审计参考)

- `docs/research/2026-07-17_pydevd-suspend-pause-position/pydevd_expert.md`
  - rev1 → rev2 → rev3 → rev4 → **rev5**(承 skeptic_v2 rev3 · 补 CMD_THREAD_RUN clear + PYDEVD_DEBUG 观察工具 + IDE 状态栏 UX + η 独立评估 + cpython_v2 实验 5 acknowledge + 5 项 minor gap 交 lead)
- `docs/research/2026-07-17_pydevd-suspend-pause-position/cpython_expert.md`
  - rev1(三份实验决定性证据 · 定位 drift 在 PyCharm Java 侧)→ rev2(补实验 4 全 5 埋点 return + 实验 5 M1 反抗机制 pydevd 层实证 + 实验 6 in_project_scope 负面证据 + sys.monitoring 修正引出 λ)→ **rev3 lock**(补实验 7 · PHASE A warm-up 全覆盖 + PHASE B mock 主动 flip CMD_STEP_OVER · pause 位置零变化 · skeptic 2a/2b 从 partial clear 升级 实证 clear)
- `docs/research/2026-07-17_pydevd-suspend-pause-position/skeptic.md`
  - rev0.5 → rev1 → rev2(补第一轮时序未赶上的挑 · 提议 η/θ/ι/κ 新方案)→ rev3(pydevd_v2 rev4 应答评估 · 3 blocker clear 2.5 · 提议 λ · 最终 rank η/M2/M1/λ/κ · 送 lead 8 项 minor blocker)→ **rev4 lock**(承 cpython_v2 rev3 实验 7 · 2a/2b 升级实证 clear · 明确"无需 cpython_v2 出 rev4"· 建议 lead 直接搬 cpython §边界声明表格作 7a/2c 修正)

### 背景

- 触发文档 `docs/tmp/2026-07-17-path2-debug-pause-quirks.md`(问题 1 + 问题 2 + v4 解耦分析)
- v3 SDD progress `.superpowers/sdd/progress.md`
- v3 e2e checklist `docs/tmp/2026-07-16-v2-event-debug-e2e-checklist.md`
- v4 spec `docs/research/2026-07-16_path2-web-event-class-filter-redesign/final_report.md`

### 涉及代码

- `path2/debug_ctx.py`(M1 改点 · 加 kwarg + settrace 加 stop_at_frame)
- `path2/atoms/throwback.py:104,163,219,224,250`(M1 若采办法 A · L104 1 处显式传参;办法 κ · 5 处;M2 · L163 移位)
- `path2_web/api.py:198-254`(问题 1 root cause · 与本任务正交)

### Team lock 状态

- **pydevd_v2 · rev5 · idle · lock**(承 skeptic_v2 rev3 全部 minor blocker · 5 项交 lead 综合 · pending 一 ping 核对实验 7 PHASE B 与反复 fire 契约 · 非硬 gap)
- **cpython_v2 · rev3 · idle · lock**(rev2 4 项 + rev3 补实验 7 · PHASE A warm-up 全覆盖 + PHASE B mock 主动 flip CMD_STEP_OVER · pause 零变化)
- **skeptic_v2 · rev4 · idle · lock**(主 blocker 全 clear · 承 cpython_v2 rev3 实验 7 把 2a/2b 从 partial clear 升级 实证 clear · 明确"无需 cpython_v2 出 rev4"· 建议 lead 直接搬 cpython §边界声明表格作 7a/2c 修正)
- **lead(主会话)**:综合三方 lock 稿 → 覆盖 rev1 → rev2 → **rev2.1 定稿**(补 cpython rev3 实验 7 + skeptic rev4 升级判定)

Team 走完 rev5/rev3/rev4 收敛 · 三方独立会师同一核心方案(M1) · pydevd 层无 drift 结论从 rev1 六轮实验支撑升到 rev3 七轮(补 warm-up 全覆盖 + IDE 回发命令实证) · rev2.1 覆盖 rev1 · **本 report 定稿**。
