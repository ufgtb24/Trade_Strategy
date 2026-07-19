# Event Debug · 对偶埋点 + Multi-Anchor 菜单 · final report v2

**Agent team**:arch2(opus) + fe2(opus) + skeptic2(opus) + v1 fe/skeptic 二次入场 · lead 主会话综合
**日期**:2026-07-15
**背景**:v1 final_report 拍板 1 采 skeptic 的 "1 处/attempt 纪律",本 v2 基于用户对偶性论点推翻拍板 1。v1 报告作为 baseline 保留:`docs/research/2026-07-15_event-level-debug-breakpoint/final_report.md`。

**用户诉求原文**:

> "如果在选中的 trough 处(throwback.py:163 `return trough_idx`)埋点,是不是和漏检的 on_gate 更加对偶?关键位置要么成功,要么失败。而由于成功和失败的埋点位置总是伴生,甚至可以考虑合并埋点(因为在同一位置)。这样便相当于复用,不增加更多复杂度。这种多处埋点的好处是让用户可以一键跳转到关键位置。与此同时还可以添加一个和方案吻合的独立的入口处埋点,来允许用户从开始调试。"

---

## 一句话结论

**方案 A' · 对偶埋点 + UI 三 anchor 菜单**:后端 `throwback.py` 物理 4 处 `debug_break`(entry L244 · trough L163 · rise_end L215 · timeout_end L219),前端 marker 右键菜单展 **3 项**(entry / trough / end,rise+timeout 由 pydevd 栈自然区分,不上升到 UI),前端 `anchorsOf` 硬编码把 `event.class_id` 映射到 3 个 anchor bar → 复用 v1 已定 `/diagnose` 契约(`start_bar==end_bar==anchor_bar` + `DEBUG_BAR_RANGE` env)。**零新协议、零新端点、零新契约字段**;后端 +4 行 debug_break、前端相较 v1 UX 从"1 项菜单"升级为"3 项菜单"(+ ~40 行 anchorsOf 表 + pending 卡片 anchor 字段扩展)。

---

## 与 v1 final_report 的冲突点清单与更新

| v1 位置 | v1 内容 | v2 更新 |
|---------|---------|---------|
| **拍板 1** | 采 skeptic 1 处/attempt(evaluate_throwback 顶部)| **推翻**:1 处 entry + 3 处关键 return(trough / rise_end / timeout_end),物理 4 处埋点、UI 3 项菜单 |
| **契约不变量 1** | "每类 event 埋且仅埋 1 处 debug_break, 位于 attempt entry" | **改写**:"对偶纪律(若为关键分岔点)+ attempt entry 恒埋 1 处 + UI 菜单项数 ≤ 后端埋点数 + `_DEBUG_MODE=False` dead-code 保护" |
| **L254** | "任何 detector 若需 ≥2 处埋点,必须 spec 显式论证,默认拒" | **松绑**:"任何 detector 增加埋点,需在 spec 附录列该 detector 的关键分岔点清单(bo/trend/burst 每类不同,见附录 A);不搞'全 detector 强制对偶'教条,'若'字兜底" |

**v1 fe1 承认原 3 项菜单方案自相矛盾**(据 fe2 立场声明);**v1 skeptic1 认账 "1 处/attempt 纪律" 被削弱**(`_emit_tb_gate` 一次 attempt 可 emit ≤4 gates,失败端已破例、成功端坚持是双标)。用户新论点是对该双标的直接指出。

---

## 4 处埋点具体位置(行号已核 `path2/atoms/throwback.py`)

| # | 位置 | 语义 | debug_break 参数 | 对应 event 字段 |
|---|------|------|------------------|----------------|
| 1 | `evaluate_throwback` L244 `bo_idx = bo.end_idx` 后 | attempt entry | `bo_idx` | `anchor_bo_id` → 反查 bo.end_idx |
| 2 | `_find_start_idx` L163 `return trough_idx` 之前 | 阶段一成功 | `trough_idx` | `event.start_idx` |
| 3 | `_find_end_idx` L215 `return i - 1` 之前 | 阶段二大涨 | `i - 1`(⚠ **必须 i-1 不是 i**,与 event.end_idx 对齐) | `event.end_idx` |
| 4 | `_find_end_idx` L219 `return end_scan` 之前 | 阶段二超时 | `end_scan` | `event.end_idx` |

**skeptic R11 澄清**:埋点参数**必须是即将 return 的 idx**(#3 是 `i-1` 不是 loop 内 `i`),否则前端 `DEBUG_BAR_RANGE=[event.end_idx, event.end_idx]` 与后端 debug_break bar 不匹配、断点不命中——**这是隐 bug**,spec 需显式强调。

**失败对偶**:`_emit_tb_gate:104` 已埋(现状),覆盖 4 个 gate:phase1_break / phase1_pullback_shortage / phase1_no_trough_timeout / phase2_break。成功 4 处 vs 失败 4 gates 结构对齐(每个成功 return 都对应"另一 bar 的失败退出")。

---

## 前端菜单 3 项 UX(fe2 定稿)

**结构**:marker 右键弹菜单 · 平铺(不下拉)· 每项两行(主行 + 灰字副行,继承 v1 约定):

```
Debug tb entry (bar 218)
  ↳ 停在 evaluate_throwback 入口 · 看 anchor / atr 起点(F10 可下潜到子函数)
Debug tb trough (bar 221)
  ↳ 停在 _find_start_idx return 前 · 已算好 trough_idx, 可看 depth / base_min
Debug tb end (bar 224)
  ↳ 停在 _find_end_idx return 前 · 大涨 / timeout 两分支(pydevd 源码行区分)
─────────
复制 driver 脚本
```

**顺序** = tb 时间线(entry → trough → end),与 K 线 x 轴左→右对齐。

**触发行为**:点击 → `view.triggerEventDebug(eventId, anchorKey)`(v2 新签名) → store action 提取 anchor bar → 复用 `getTimeDiagnose(pattern, symbol, w.start, w.end, bar, bar, event.class_id, signal)`(v1 已定 8 参含 AbortController signal) → 后端 handler `os.environ["DEBUG_BAR_RANGE"] = f"{bar},{bar}"` → analyze 触发 pydevd。

**fe2 定稿的关键 UX 决策**:
- **不加 "Debug all"**:IDE debug 是单点执行语义,queue 化会稀释 v2 "一键跳转关键位置" 的诉求。用户想依次看 3 处 → PyCharm 手动打 3 breakpoint + F9 是正确姿势。
- **label 带 "(bar N)" 非冗余**:marker 位置是几何位置(可能是 3 个 anchor 之一),用户看不到会盲跳。bar 号在主行提供空间锚定。
- **平铺不下拉**:下拉多一步 hover/click,与"一键跳转"诉求冲突。
- **单入口**:sidebar **不加** 3 项按钮(重复入口);仅扩展 v1 已定的 pending 卡片,加 anchor 字段(见 store action)。
- **右键分流 whitelist**(D5):marker 右键 + class 在 `DEBUG_ENABLED_CLASSES`(v2 仅 `tb`)→ 3 项 debug 菜单;marker 右键 + class 不在 whitelist(bo/burst/trend) → 降级到空白 K 线的 driver 脚本菜单(保底手动 debug 路径);空白 K 线右键 → driver 脚本菜单不动。**避免"菜单显示但 breakpoint 不 hit"的无声失败**

---

## Anchor 映射硬编码(TS 形态,fe2 定稿)

**anchorsOf 表**(前端 store 或 view 层)

```typescript
type DebugAnchor = {
  key: 'entry' | 'trough' | 'end'
  bar: number
  label: string
  hint: string
  disabled?: boolean
  disabledReason?: string
}

const anchorsOf: Record<string, (e: SerializedEvent, events: SerializedEvent[]) => DebugAnchor[]> = {
  tb: (e, events) => {
    const boBar = findBoBar(e.anchor_bo_id, events)
    return [
      { key: 'entry',
        bar: boBar ?? e.start_idx,  // fallback 避免 null 传导; disabled 阻塞点击
        label: 'entry',
        hint: '停在 evaluate_throwback 入口 · 看 anchor / atr 起点(F10 可下潜到子函数)',
        disabled: boBar == null,
        disabledReason: boBar == null ? `未找到 anchor bo event (id=${e.anchor_bo_id}), 契约可能漂移; 可从 trough/end 断点` : undefined },
      { key: 'trough',
        bar: e.start_idx,
        label: 'trough',
        hint: '停在 _find_start_idx return 前 · 已算好 trough_idx, 可看 depth / base_min' },
      { key: 'end',
        bar: e.end_idx,
        label: 'end',
        hint: '停在 _find_end_idx return 前 · 大涨 / timeout 两分支(pydevd 源码行区分)' },
    ]
  },
  _default: () => [],  // ★ D7 · 不给未埋点 class 生成菜单项(防"菜单显示但后端未埋 debug_break"的无声失败)
}

function findBoBar(anchor_bo_id: string, events: SerializedEvent[]): number | null {
  const bo = events.find(x => x.event_id === anchor_bo_id)
  return bo?.end_idx ?? null
}

// ★ D8 · DEBUG_ENABLED_CLASSES 与 anchorsOf 硬耦合,避免两处维护漂移:
// 后端埋新 detector 时,前端只改 anchorsOf,whitelist 自动同步
const DEBUG_ENABLED_CLASSES = Object.keys(anchorsOf).filter(k => k !== '_default')
```

**store action**:

```typescript
async function triggerEventDebug(eventId: string, anchorKey: 'entry' | 'trough' | 'end') {
  const event = analysis.events.find(e => e.event_id === eventId)
  if (!event) return
  const anchors = (anchorsOf[event.class_id] ?? anchorsOf._default)(event, analysis.events)
  const anchor = anchors.find(a => a.key === anchorKey)
  if (!anchor || anchor.bar == null) { toast.warning(`anchor "${anchorKey}" 不可用`); return }
  debugAbortRef?.abort()
  const controller = new AbortController()
  debugAbortRef = controller
  debugTarget = { eventId, bar: anchor.bar, className: event.class_id, anchor: anchor.label }  // ★ v2 新增 anchor 字段
  debugPending = true
  activeDetailCard = 'debug'
  try {
    await getTimeDiagnose(patternId, symbol, w.start, w.end, anchor.bar, anchor.bar, event.class_id, controller.signal)
  } catch (e) {
    if (e.name !== 'AbortError') toast.error(String(e))
  } finally {
    if (debugAbortRef === controller) debugPending = false
  }
}
```

**pending 卡片 v2 显示**:`Debugging tb entry at bar 218, waiting for breakpoint...`(anchor 名新增,防用户切窗口后忘"我停哪")。

**cancel 按钮 tooltip**(D4):`取消 = 放弃本次 fetch; IDE 断点需自行 F9/F8 unblock; 新 debug 请求会 abort 本次`(防用户误以为取消能 unblock IDE)。

**state 清理约束**(D9):`clearDetailCard()` 必须同步清 `debugTarget / debugPending / debugAbortRef`(与 clearTime / clearPair 一致);`selectSymbol()` / `setActivePattern()` 触发 `clearDetailCard` 里的 `debugAbortRef?.abort()`,避免切股/切 pattern 后旧 debug 挂着(v2 触发频率 3× v1,清理不同步会残留 stale state)。

---

## end_idx 二义性处理(rise vs timeout)

`_find_end_idx` 有 2 处成功 return:
- **L215** `return i - 1` — 大涨触发(`high[i] - base_min ≥ big_rise_k*atr`)
- **L219** `return end_scan` — 扫满窗无破位无大涨(timeout)

**arch2/fe2/skeptic 一致立场**:后端物理 2 处埋点,UI **合并为 1 项 "end"**。理由:

1. **技术无歧义**(skeptic R10):前端 range=[event.end_idx, event.end_idx],detector 两处 debug_break 中"事实上只有一个是那根 bar"(rise 时 L215 命中、timeout 时 L219 命中,逻辑互斥)。
2. **pydevd 栈自然揭示**:用户停在 L215 vs L219,pydevd 显示的函数位置和源码行不同,一眼看出"我停在哪种 end"。
3. **反过度设计**:3 项 (entry/trough/end) 是 tb 生命周期的自然阶段;4 项 (entry/trough/rise/timeout) 破坏"阶段" abstraction、让菜单产生"选哪个"的决策负担。
4. **anchor 表天然 3 项**:rise/timeout 传入 `debug_break` 的 bar 都 == `event.end_idx`,菜单显示"end at bar N" 与 range=[N,N] 一致,前端不需感知 2 处物理埋点。

**物理二义性 → UI 一致性,靠"两处 debug_break 传入相同 bar"这个后端事实吸收,不上升到前端。**

---

## Corner case 表(skeptic2 二轮 audit,15 条 · 高严重度 0)

| # | 场景 | 严重度 | 处理 |
|---|------|--------|------|
| 1 | anchor_bo_id 反查失败(3 种失败模式:①`anchor_bo_id === ''` 空串;②bo 被 dropped_matches 过滤/不在当前 window/被 level 过滤隐藏;③`analysis.events` 未完全加载异步竞态) | 中 | entry 项 disable(`opacity: 0.5` + `pointer-events: none`)· 主行 `Debug tb entry (未定位)` · tooltip `未找到 anchor bo event (id=xxx), 契约可能漂移; 可从 trough/end 断点` |
| 2 | 同 bar 多埋点同时命中(**真场景 = rise_end == trough**,首轮就大涨 `i-1=start_idx`,skeptic 证伪了 arch2 max_start_gap=1 的例子,因 L155 强制 `trough_idx ≥ bo_idx+2`)| 中 | 允许自然发生(F9 依次断 2 次);spec 加提示 "trough 与 end 同 bar 时 PyCharm 会依次断 2 次"。前端**不做去重** |
| 3 | `_find_end_idx` 空扫(数据末尾 start==len-1)→ end_idx == start_idx | 低 | 接受;UI 菜单 trough/end 同 bar 时"自然合并" |
| 4 | timeout 边界模糊(len-1 截断的"假 timeout")| 低 | 接受;用户看 `end_scan` 值自判(是 max_window 还是 len-1) |
| 5 | v1 finally pop env 继承 | 低 | 接受(v2 无新冲击) |
| 6 | 埋点在 return 前 → F10 一步就出去,看不到"过程" | 低-中 | draft 不动;spec 附文档分工:"想看过程用 entry+F10 下潜;想看结果用 trough/end 直接查栈变量" |
| 7 | 多次连续 debug 幂等 | 低 | 接受(handler 每次全量重算,幂等) |
| 8 | "对偶纪律" 泛化到 bo/trend/burst | 中 | 契约文本用"**若**为关键分岔点"兜底;spec 附录 A 列每类 detector 对偶清单(bo=1↔1 · trend=按 seg 结束 · burst=aggregate 语义,可能仅 entry) |
| R9 | UI 菜单项数 ≤ 后端埋点数(方向核对) | 低 | 接受(3 ≤ 4 ✓) |
| R10 | UI "end" 1 项 → 后端 2 处的选择歧义 | 低 | 技术无歧义(range 匹配) |
| **R11** | **`_find_end_idx` L215 埋点参数必须 `i-1` 不是 `i`** | **中(**⚠ **必写)** | draft 显式强调埋点参数=即将 return 的 idx |
| R12 | 不同 anchor 的 range 交叠顺序 | 低 | 无交叠、无 race |
| R13 | entry 反查一致性(前端 anchor_bo_id → bo.end_idx == 后端 bo_idx) | 低 | 一致 ✓ |
| R14 | 两次 debug 之间 env 时序 | 低 | **前提**:uvicorn 单 worker 串行(v1 已定);spec 明说依赖 |
| R15 | gate 失败无 event marker → 用户不会误点 | 低 | 接受 |

**skeptic2 未越权**:全审 how 不评 should,不 double down v1 保守方案。**无 [BLOCKING]**。

---

## 非目标(明确不做)

1. **不加 "Debug all" 依次触发选项** — IDE 单点执行语义,queue 化过度设计
2. **不加 sidebar 3 项按钮入口** — 与 marker 右键重复,稀释触发心智锚
3. **不区分 UI end rise/timeout** — 栈自然区分,不上升到菜单
4. **不动 debug_break 位置到 return 前几行** — F10 单步"过程 vs 结果"分工文档说明足够
5. **不搞"全 detector 强制对偶"教条** — 契约"若"字兜底,spec 附录列每类 detector 具体判定
6. **不做 anchor_bo_id 反查失败时静默降级到 trough** — 混淆概念;disable + 明确 tooltip
7. **不做 uvicorn 多 worker 兼容** — spec 明说依赖单 worker(v1 已定)
8. **不引入新 API 端点/新协议字段/新 event dataclass 字段** — 复用现有 `/diagnose` + `DEBUG_BAR_RANGE` + `SerializedEvent.anchor_bo_id`

---

## v2 新契约不变量(替代 v1 契约不变量 1)

> **对偶纪律 + 全局入口 + 项数守恒 + dead-code 保护**
>
> 1. **对偶纪律(若)**:detector 的成功 return 与失败 emit 若为**关键分岔点**,应对偶埋点(避免菜单显示但用户点了不触发)。"关键分岔点" 由该 detector 的 authoring 阶段判定并在 spec 附录 A 列出;非分岔点不强制埋。
> 2. **attempt entry 恒埋**:每个 detector 的 attempt 入口(evaluate_<class> 顶部)必须埋 1 处 debug_break,作全局入口(用户从头看流程)。
> 3. **项数守恒**:UI 菜单展开项数 **≤** 后端埋点数(不允许菜单项无对应埋点导致无声失败;允许后端多处埋点合并到 UI 单项如 rise/timeout → end)。
> 4. **参数对齐**:每处 `debug_break(x)` 的 `x` 必须是即将成为 `event.<field>` 的 bar 值(见附录 B 每 detector 参数表);前端 `anchorsOf` 映射按此 field 直取,前后端 bar 一致。
> 5. **dead-code 保护**:所有 debug_break 必须在 `_DEBUG_MODE=False` 时是 dead code(零生产开销);`_emit_tb_gate` 内的 debug_break 也走 `on_gate is None` 早退双闸。
> 6. **同 detector 类新增/修改埋点需同 PR 落地前后端**:后端 debug_break 与前端 `anchorsOf` 映射必须同 PR,避免漂移。
> 7. **env cleanup 显式化**(D10 · v2 必要契约,不再仅"v1 拍板 3 继承"):handler 必须 `try/finally pop os.environ['DEBUG_BAR_RANGE']`;v2 触发频率 3× v1,每 request 结束必清,防跨 request 污染。

**替代 L254**:去掉"默认拒 ≥2 处埋点",改为"任何 detector 增加埋点,需在 spec 附录 A 论证该 detector 的关键分岔点清单;附录 A 通过评审即可,不搞默认拒教条"。

---

## 附录 A · 每 detector 对偶清单(spec 后续扩展)

| detector | 关键分岔点判定 | v2 埋点数 |
|----------|--------------|---------|
| tb (throwback) | entry / 阶段一成功(trough)/ 阶段二成功(rise+timeout 合并 UI) | 后端 4 · UI 3 |
| bo (breakout) | evaluate_bo 内 1 处判 breakout,成功→emit 1 event / 失败→1 gate,对偶存在(1↔1) | 后端 1 · UI 1(仅 entry) · 未来扩展时判定 |
| trend | seg 结束是关键分岔点,可对偶(具体待 authoring 时细读) | 未来扩展 |
| burst | aggregate 非 step,"关键分岔点" 语义不天然,可能仅 entry 一处 | 未来扩展 |

## 附录 B · debug_break 参数表(throwback.py)

| # | 埋点位置 | 参数 | 与 event field 对应 |
|---|---------|------|-------------------|
| 1 | L244 `evaluate_throwback` 入口后 | `bo_idx` | anchor_bo_id 反查 → bo.end_idx |
| 2 | L163 `_find_start_idx` return 前 | `trough_idx` | event.start_idx |
| 3 | L215 `_find_end_idx` return 前(大涨)| `i - 1` (⚠ 不是 `i`)| event.end_idx |
| 4 | L219 `_find_end_idx` return 前(超时)| `end_scan` | event.end_idx |

---

## 实施建议

**下一步**:
1. `superpowers:writing-plans` 把本 final_report 转为可执行 spec + plan(fe2 判断 v1 未落地,v2 一次到位不留过渡步 → plan 直接从零实施 3 项菜单 + 4 处埋点 + pending 卡片 anchor 字段)
2. Task 顺序:
   - **Task 1**:后端 4 处 `debug_break` + handler `finally pop env`(v1 拍板 3 继承)+ 单元测试
   - **Task 2**:前端 `anchorsOf` 表 + `findBoBar` helper + `triggerEventDebug` 新签名
   - **Task 3**:KlineChart marker 右键 3 项菜单(平铺 + entry 灰化降级 + label 带 bar)
   - **Task 4**:DetailSidebar pending 卡片 `anchor` 字段扩展
   - **Task 5**:端到端手动验证(entry/trough/end/entry-degraded 4 场景)
3. 全部 subagent-driven,每 task 双审(spec + code quality)+ final holistic

---

## 红线检查

- ✅ `feedback_argument_discipline`:fe2/skeptic2 均认账 v1 论据被削弱,无动机性推理护旧结论
- ✅ `project_path2_nesting_mechanism`:全审 how 不评 should,不越权推翻用户已定意图
- ✅ `project_path2_web_ui_levels_lanes` 反过度设计:不加 "all"/不加 sidebar 入口/不区分 UI rise/timeout/不搞全 detector 教条对偶
- ✅ v1 contract 兼容:复用 `/diagnose` + `DEBUG_BAR_RANGE` + `SerializedEvent.anchor_bo_id`,零新协议

---

## agent team 协作说明

- **arch2**(opus)出 draft + 综合 · fe2 硬事实精确对齐(4 处埋点行号 + bar 语义表)· skeptic corner 分级 · v2 契约起草
- **fe2**(opus)一轮定稿 UX 7 问(3 项/平铺/label bar 号/灰化降级/单入口/新签名/F10 论点保留)· 补充 pending 卡片 anchor 字段扩展 · 强论"F10 论点保留、多 anchor 是路径缩短非心智替代"
- **skeptic2**(opus)一轮 15 corner 分级(高 0/中 4/低 11)· 认账 v1 论据 · 关键澄清 R11(埋点参数 `i-1`)+ 8 号契约"若"字兜底 · 证伪 arch2 corner 2 错误举例、给出真场景(rise_end == trough 首轮大涨)
- **v1 fe/skeptic**(opus)也被 arch2 二次入场咨询(name 混用),独立产出 v2 UX 评估与 corner audit,与 v2 team 结论一致
- **lead**(主会话)集成产出,v2 spec 落此文件
