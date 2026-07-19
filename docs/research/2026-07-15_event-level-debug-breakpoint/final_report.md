# 成功 event 精准断点 · 设计研究 final report

**Agent team**:arch(opus) + fe(opus) + skeptic(opus) · lead 主会话综合
**日期**:2026-07-15
**用户诉求**(原文):

> "我能不能通过这种方式调试没有漏检的 event,比如说我想看一个被检测出的 tb 是通过哪些数值计算最后被检测出的。我希望通过网页浏览选中目标 event 的方式,并在相应计算处命中断点。"

---

## 一句话结论

**方案 A · anchor bar 精准触发**:用户在 K 线上 event marker 右键 → 菜单出现两行文案(主行 "Debug \<class\> at bar=X" + 灰字副行 "停在 evaluate_\<class\> 入口, F10 step 到内部计算细节",详见 §端到端流程 步骤 2)→ 前端按 class_id 硬编码 anchor 规则提出该 event 的 attempt 入口 bar → 复用现有 `/diagnose` 的 `start_bar=end_bar=anchor` 契约 → 后端写 `DEBUG_BAR_RANGE` → detector 在 attempt 入口埋 `debug_break(bo_idx)` 精准命中一次 → 用户在 PyCharm F10 下潜到 `_find_start_idx`/`_find_end_idx` 细看每步中间量。

**零新协议、零新端点、零新契约字段;后端 <6 行、前端 ~130 行。**

---

## 与已实施方案的边界

**已实施(commit 待定)**:
- `path2/debug_ctx.py`:`_DEBUG_MODE` 启动读一次 + `_read_range` 动态读 + `debug_break(i)` 双闸
- `path2/atoms/throwback.py`:**失败链路**在 `_emit_tb_gate` on_gate 早退后埋 `debug_break(gate_idx)`
- `path2_web/api.py::/diagnose`:handler 顶部按 `start_bar/end_bar` 写 `DEBUG_BAR_RANGE`

**本方案增量**:
- `path2/atoms/throwback.py`:**成功链路**在 `evaluate_throwback` 顶部再埋一处 `debug_break(bo_idx)`(与 `_emit_tb_gate` 出口对偶)
- `path2_web/api.py::/diagnose`:handler 加 `try/finally`,`finally` 中 pop env(**修复现存 bug**,见 skeptic Corner 3)
- 前端:菜单 + store action + AbortController 单槽位并发覆盖

---

## 端到端流程(定稿)

1. 用户在 K 线 event marker(tb 三角 / bo 方框 / burst 区间)上**右键** → 弹菜单(marker 分支)
2. 菜单展示 **1 项** debug 入口 · **两行结构**(主文案 + 灰字副标题,fe UX 补丁 · 契约不许简化):
   ```
   Debug tb at bar 220
     ↳ 停在 evaluate_throwback 入口, F10 step 到 trough/end 计算细节
   ```
   - 每 event 只 1 项;不为每种 anchor(bo_idx/trough/end)分列(见拍板 1 · 采 skeptic 埋点纪律)
   - 副标题必须保留 —— 让用户第一眼知道"停在哪里 + 怎么下潜",避免"debug 没到我想看的地方"的困惑
3. 用户点击 → `view.triggerEventDebug(eventId)`
4. 前端按 class_id **硬编码** anchor 映射(~10 行 TS):
   ```typescript
   const anchorOf = {
     tb: e => e.anchor_bo_id ? findBoBar(e.anchor_bo_id) : e.start_idx,
     bo: e => e.start_idx,                          // 未来扩展
     burst: e => e.members?.[0]?.start_idx ?? e.start_idx,  // 未来扩展
     _default: e => e.start_idx,                    // 兜底(通用契约字段)
   }
   ```
   - `findBoBar(anchor_bo_id)`:helper,前端从 `analysis.events` 里按 `event_id === anchor_bo_id` 反查对应 bo event 的 bar(tb 的 anchor 语义 = 触发它的那根 bo bar)
   - **菜单 whitelist**:仅在 event.class_id 已埋 `debug_break` 时显示菜单项(当前 iteration = **仅 tb**);未来扩展 bo/burst/trend 埋点时前端同步扩 whitelist。**防 fe 遗漏 9 的"无声失败"**(菜单显示但 fetch 不命中 breakpoint 让用户困惑)
5. 调用现有 `getTimeDiagnose(pattern, symbol, w.start, w.end, bar, bar, event.class_id)` — 复用已实现 endpoint,无需新增
6. 后端 `/diagnose` handler:
   - `start_bar==end_bar==bar` → `os.environ["DEBUG_BAR_RANGE"] = f"{bar},{bar}"`
   - handler body 走 `attach_and_collect` + `_dag_analyze_engine`
   - **`finally` 块 `os.environ.pop("DEBUG_BAR_RANGE", None)`**(新增,fix skeptic Corner 3)
7. `throwback.evaluate_throwback` 入口 `bo_idx = bo.end_idx` 之后 `debug_break(bo_idx)` 命中该 bar → PyCharm pydevd hook → 用户看栈变量、F10 下潜细看 `_find_start_idx` / `_find_end_idx` 每根 bar 的比较

---

## 具体改动清单

### 后端(<6 行)

**`path2/atoms/throwback.py`**(+1 行):

在 `evaluate_throwback` 入口 `bo_idx = bo.end_idx` 之后插入:

```python
debug_break(bo_idx)
```

只 1 处(skeptic 埋点纪律:"一次调用 = 一次 attempt",与 `_emit_tb_gate` 失败出口对偶)。**不加** 4 处(`_find_start_idx` return / `_find_end_idx` 两处 return)—— PyCharm F10 下潜是 debug 用户标准操作。

**`path2_web/api.py::/diagnose`**(+3 行 · **修现存 bug**):

将 handler body 包 `try/finally`,`finally` 块 pop env:

```python
try:
    # ... existing body (build_pattern → attach_and_collect → analyze → derive_response)
    return response
finally:
    os.environ.pop("DEBUG_BAR_RANGE", None)
```

**目的**:每次请求结束都清 env,不留污染。修 skeptic Corner 3(现存 bug + 成功 debug 显著放大):
- overall diag(不带 bar)之前保留上次 range,若下次触发 `debug_break` 会命中残留 bar
- 若 debug 后端启用 `/scan`,`ProcessPoolExecutor` fork/spawn worker 继承父 env → worker 挂在残留 bar

**不改**:bo/burst/trend detector 埋点(用户只提 tb,按需增量);`_emit_tb_gate` 失败埋点保留不动。

### 前端(~130 行)

**`path2_web_ui/src/components/KlineChart.vue`**(~60 行 diff):

- 现有 `handleContextMenu` + `contextMenuVisible` + `copyDriverScript` 基础设施复用(fe 发现)
- 改用 `chartMain.getZr().on('contextmenu', e => ...)` 分流右键落点(按 `e.target` 判定 seriesName):
  - marker 上 → event debug 菜单
  - 空白 K 线 → 保留现有 driver 脚本菜单
- 菜单模板 · **两个分支菜单**:
  - **marker 分支(新增)**:1 项 "Debug this event"(两行文案,DOM 结构见下)
  - **空白 K 线分支(现有)**:1 项 "复制 driver 脚本"(保留不动)
  两分支共用 `contextMenuPos` + `contextMenuVisible` + `driverMenuEl` state;分流只在 contextmenu handler 里按 target 判定
- **菜单项 DOM 结构约束**(防实施者用 innerHTML 拼一行 / 单 span 换行):两行文案必须用两个独立 `<div>`——主行 `<div class="menu-item-title">` + 副行 `<div class="menu-item-hint">`(灰字 · font-size 比主行 ↓2px)
- 菜单项 `@click.stop` 防冒泡(fe 遗漏 8)
- **v-if 生产隔离**:所有 debug 菜单项/DetailSidebar debug 卡片渲染时判 `import.meta.env.VITE_API_BASE` — 若指向生产 (默认或 8000)则不渲染(~3 行 v-if,详见「部署约定」段)

**`path2_web_ui/src/stores/view.ts`**(~35 行):

- 新 state:`debugPending: boolean` / `debugTarget: {eventId, bar, className} | null` / `debugAbortRef: AbortController | null`
- `activeDetailCard` 值域扩展 `'debug'`
- 新 actions:
  - `triggerEventDebug(eventId)`:按 class_id 硬编码提 anchor bar,调 `postDebugDiagnose`
  - `cancelDebug`:abort 旧 controller
- 多 debug 并发:单槽位覆盖(新请求 abort 旧的,fe 遗漏 6)

**`path2_web_ui/src/api.ts`**(~15 行):`getTimeDiagnose(patternId, symbol, start, end, startBar, endBar, eventClass?, signal?)` — 新增可选第 8 参数 `signal?: AbortSignal`,内部 `fetch(url, {signal})` 透传。其他 diagnose 函数(getDiagnose / getRolesDiagnose / getPairDiagnose)本轮不改。

**`path2_web_ui/src/components/DetailSidebar.vue`**(~25 行):`activeDetailCard === 'debug'` 卡片(spinner + 引导文案「等待 IDE 断点命中,请在 PyCharm 按 F9 继续,或点取消放弃本次 debug」+ 取消按钮)

> ⚠ **UX 语言冲突**(需用户拍板):CLAUDE.md line 41 "界面英文,注释/文档中文",但项目现有 UI 实际全中文(右键菜单「复制 driver 脚本」/框选/等)。arch 建议遵 CLAUDE.md 英文,fe 建议随项目实际中文。本 final 采 fe 建议(一致性优先),若用户偏好英文可回退到原文 "Waiting for breakpoint... continue in IDE via F9, or cancel";同时建议 CLAUDE.md line 41 与项目实际 UX 同步更新。

**不加**:`SerializedEvent.debug_targets` 字段(见拍板 4)。

### 部署约定(vite 层,零代码)

Debug 前端独立启动:

```bash
VITE_API_BASE=http://localhost:8009 npm run dev -- --port 5174 --strictPort
```

**生产前端(VITE_API_BASE 未设 = 默认 8000)不加任何 debug 相关 UI**:右键 marker 时菜单不出现 debug 项、DetailSidebar 不注册 `'debug'` 卡片、不加 sessionStorage probe(前端渲染判 `import.meta.env.VITE_API_BASE` 加 `v-if`,~3 行)。**debug 前端顶部红色 "DEBUG MODE" badge**(读 VITE_API_BASE 判断,若不是生产默认则显示,~5 行 Vue),避免用户看错窗口以为在生产上操作。

**取代原"静默降级 + badge 未来加"策略**。两条硬论据:

1. **静默降级 = 无声失败**:用户在生产 tab 点了 fetch 200 但 breakpoint 不 hit,会怀疑整个 debug 系统坏了,反去 IDE 检查 debug_ctx.py;tooltip hover 才见弥补不了菜单常显的误导
2. **skeptic Corner 3 side effect 消失**:生产菜单排除 debug 项后,生产 backend 根本不会收到 `start_bar==end_bar` 请求,`finally pop env` 那 side effect 完全没必要执行(只是空 pop,语义冗余);仍保留 `finally` 是防手动 curl / 其他前端 client 场景

---

## Lead 拍板结果(4 项)

### 拍板 1 · 埋点数量 — **采 skeptic 1 处/attempt**
- **arch v2 裁决**:采 skeptic(evaluate_throwback 顶部 1 处)
- **fe 完整版反驳**(Q2):推"菜单同级子项 3 项"(bo_idx/trough/end 各一 debug 入口),理由是用户原文"想看完整计算流"若只 start_idx 会漏 bo 触发段
- **lead 复核后仍采 arch v2**。理由:
  - arch 埋点在 `evaluate_throwback` 顶部(bo 之后立即命中),F10 下潜到 `_find_start_idx` / `_find_end_idx` 就能看完整计算流 —— **恰好覆盖 fe 想要的"完整流"需求**,fe 论点建立在"只看 start_idx"的误解上
  - spec §2.4.2 已定义 "一次调用 = 一次 attempt",与 `_emit_tb_gate` 失败出口对偶
  - PyCharm F10 下潜是 debug 用户标准操作,不需前端菜单糖
  - 反过度设计:1 处埋点 vs 4 处,代码量 4×
  - 未来若 F10 下潜成高频痛点,增量补埋

### 拍板 2 · 独立 `/debug/event` 端点 — **拒 fe**
- **arch v2 裁决**:拒(_DEBUG_MODE 静态短路即够)
- **lead 同意**。理由:
  - `_DEBUG_MODE` 启动读一次,生产 backend `DEBUG_MODE=0` → `debug_break` 完全零成本短路,**没有挂死风险** —— fe 担忧建立在错误前提上
  - 生产误配 DEBUG_MODE=1 是运维问题(启动脚本 assertion / systemd unit 隔离),不是代码问题
  - 独立端点意味着新 route + 新 handler + 新前端 fetch,违反"零协议扩展"
  - **补偿**:spec 显式记入运维约定"生产 backend 必须 DEBUG_MODE=0"

### 拍板 3 · uvicorn 单 worker 串行化 — **已就位**
- **arch v2 请求**:确认 debug 后端启动脚本是 `--workers 1`
- **lead 确认**:`path2_web/main.py::main()` 里 `uvicorn.run(..., host=HOST, port=PORT, reload=RELOAD)` — **不传 `workers`**,默认单 worker。已就位,无需改动
- **部署约束**(spec 显性化 · 防未来破单 worker 前提):debug 后端启动脚本**严禁**传 `workers` / `--workers` 参数,多 worker 会各自 hang 在 `breakpoint()`、pool 死锁

### 拍板 4 · `SerializedEvent.debug_targets` 字段 — **拒 fe**
- **arch v2 裁决**:拒(前端硬编码 anchor 规则 ~10 行 TS 足够)
- **lead 同意**。理由:
  - 采拍板 1 后每 event 只 1 项菜单,不需列表结构
  - anchor 规则映射表变化频率 ≈ detector 类型新增频率(极低)
  - 后端 `serialize.py` 已成熟,不该为 debug 便利污染契约
  - fe 论点"哪些 bar 真的有埋点"由 spec 文档化(哪些 detector 埋了 `debug_break`)+ 前端硬编码同步维护;若漂移只影响 debug 便利、不影响正确性

---

## 契约不变量(spec 需显式写入)

arch v3 收口时明确列出的 4 条硬契约(实施 spec/plan 里必须逐字保留,不许简化):

1. **每类 event 埋且仅埋 1 处 `debug_break`,位于 attempt entry**(如 tb 的 `evaluate_throwback` 顶部、未来 bo 的 detect entry、burst 的 detect entry 等);扩展新 detector 类型必须遵守此纪律。**任何 detector 若需 ≥2 处埋点,必须在 spec 显式论证,默认拒**(见「后续增量口子」章节)
2. **菜单文案两行结构**(主 + 灰字副标题) —— 见「端到端流程」step 2 示例;不许实施时简化为单行(避免"debug 没到我想看的地方"的认知错位)
3. **生产 backend 必须 `DEBUG_MODE=0`** —— 运维约定;`_DEBUG_MODE` 是启动时 `os.environ.get` 一次的 module-level bool(`path2/debug_ctx.py:9`),运行时变化不生效
4. **handler `finally` pop env** —— `DEBUG_BAR_RANGE` 请求级作用域,每次请求结束都清,不留污染(scope 与 legacy 路径都覆盖)

---

## 强 recommend · 前置 fix(高优先)

**skeptic Corner 3(高严重度 · 现存 bug)**:handler `finally` pop `DEBUG_BAR_RANGE` env。

**为什么强 recommend 与方案同 PR**:
- 是当前 spec 落地版就有的隐患(overall diag 保留上次 range),成功 debug 会**显著放大**(用户切 pattern/切 scope 频繁 → env 残留概率高)
- 若 debug 后端启用 `/scan`,ProcessPool worker 继承父 env → **随机断在残留 bar 上、pool 挂**
- fix 成本 = 3 行 try/finally,无副作用

即使暂不实施方案 A 主体,这个 fix 也该做。

---

## Corner cases 与处理(skeptic 8 高 + 5 中/低 完整表)

| # | 类别 | 严重度 | 处理 |
|---|---|---|---|
| 1 | anchor bar 语义歧义 | 中 | 接受 + spec 列每类 event 的 anchor 规则(前端硬编码映射) |
| 2 | 同 bar 多 detector 撞车 | 低(当前)→ 中(扩展后) | 接受 + 埋点范围纪律(一处/attempt);PyCharm 里 disable 无关断点化解 |
| **3** | **`DEBUG_BAR_RANGE` 遗留污染** | **高** | **修 · handler `finally` pop env**(前置 fix) |
| 4 | 成功链路埋点位置选择 | 中 | 接受 · 埋点定 `evaluate_throwback` 顶部 |
| 5 | `_DEBUG_MODE` 静态 vs UX | 中/低 | 采 fe P1-2 patch 后 tooltip 需求消失:生产菜单根本不显示 debug 项(v-if 隔离) = 不用提示 8009 生效,不显示 = 不需要提示 |
| **6** | **`breakpoint()` 挂 uvicorn worker** | **高** | 接受(是 debug 后端本质) + 前端 UX 提示 · lead 已确认单 worker 已就位 |
| 7 | 序列化契约漂移(新 event 类型) | 低 | 接受 · 前端默认 `event.start_idx` 兜底 |
| 8 | `/scan` 与 `/diagnose` 共享 env | 高 | 合并 #3 修复;debug 后端约定不启用 `/scan` |
| R9 | handler 内 env vs 未来 async | 低→中 | 接受 · 注释警戒(未来加 await 时改 request-scoped) |
| R10 | 静态/动态设计不对称 | 低 | 接受 · spec 注释说明 |
| R11 | 按钮启用探测 | 中(UX) | 前端启动时探测 8009 存活(未来 polish) |
| R12 | 无 marker 的 event 类型 | 低 | 接受 · 复用 `DetailSidebar.vue` 候选表行 `focusEvent` 入口 |
| R13 | 埋点行数增长 | 低 | 接受 · dead-code 零成本 |

**无 [BLOCKING]** —— 方案 A 技术上完全可行。

---

## UX 决定(与 fe 一致)

- **触发姿势**:右键菜单(fe 发现现有 `handleContextMenu` 基础设施,复用心智一致)
- **视觉反馈**:spinner + AbortController + **无 timeout**(fe "timeout 误杀 debug session" 硬道理)
- **多 debug 并发**:单槽位 + 覆盖(新请求 abort 旧)
- **DEBUG_MODE 环境隔离**:生产前端根本不显示 debug 入口(菜单/sidebar/probe 全隐藏,v-if 判 VITE_API_BASE);debug 前端顶部红色 "DEBUG MODE" badge 强制显示。取代静默降级——生产用户看不到 debug 项 = 不会误点
- **无冲突模式**:与既有 shift+click(pair 累积)、click(focus)、brush(time diag)并行的第 4 modifier 姿势(右键 marker)

---

## 非目标(明确排除)

- ❌ **方案 B**(event_id 精准匹配):event_id 需 start/end 都定后才能算,**无法看计算过程**
- ❌ **方案 C**(`Event.anchor_bar` 通用协议字段):tb 有 3 个候选 anchor(bo_idx/trough/end),强制一个反而限死
- ❌ **`DEBUG_MODE` 动态化**:by design 静态短路;debug 后端 8009 端口架构已够清晰
- ❌ **`DEBUG_TARGET_CLASS` class_id filter**:同 bar 多 detector 撞车靠 F9 化解足够
- ❌ **前端 `/health` 探测 debug 模式**:独立 dev server 化解此需求
- ❌ **独立 `/debug/event` 端点**:见拍板 2
- ❌ **`SerializedEvent.debug_targets` 字段**:见拍板 4
- ❌ **bo/burst/trend 一次性铺开埋点**:用户只提 tb,按需增量(未来某类 debug 频繁时再补一行)

---

## 后续增量口子

方案 A 打好了基础设施(`debug_break`+ `DEBUG_BAR_RANGE`+ 前端右键菜单 + `triggerEventDebug`),后续扩展:

1. **bo/trend/burst debug**:各自 detector 主入口加一行 `debug_break(<anchor_bar>)` + 前端菜单加对应 class_id;每处增量 ~5 行,无需新协议。**强不变量**:每类 detector **仅**在其主 attempt 入口埋 1 处 `debug_break`(与 `evaluate_throwback` 顶部同规格);未来任何 detector 埋点若需 ≥2 处,必须在 spec 显式论证(默认拒)
2. **F10 下潜痛点解决**:若"从 attempt 入口 F10 到某内部计算"成为高频操作,`_find_start_idx` / `_find_end_idx` return 前各埋一处
3. **多点 anchor(fe 分歧 1 的复活)**:若用户明确需要"想看 trough 就直接停 trough"这层前端糖,菜单展开 3 项、后端埋 4 处;当前不做
4. **DEBUG_TARGET_CLASS**:多 detector 埋点撞车成为真问题时再加

---

## 实施建议

**下一步**:
1. 用 `superpowers:brainstorming` 或直接 `superpowers:writing-plans` 把本 final_report 转为可执行 spec + plan
2. 实施顺序建议:
   - **Task 1**:handler `finally` pop env(前置高优 fix,独立可 ship)
   - **Task 2**:throwback `evaluate_throwback` 顶部埋点 + 单元测试
   - **Task 3**:前端 `triggerEventDebug` + KlineChart 右键菜单 + DetailSidebar debug 卡片
3. 全部使用 subagent-driven,每 task 双审(spec + code quality)+ final holistic

**执行前置**:
- 现有 3 task(debug_break helper / throwback failure 埋点 / handler env set)commit 落地(否则本方案叠在未 commit 的改动上不清晰)

---

## 红线检查

- ✅ `feedback_argument_discipline`:所有分歧裁决基于硬事实(spec §2.4.2 / `_DEBUG_MODE` 短路机制 / 契约稳定性代价);无动机性推理
- ✅ `project_path2_nesting_mechanism`:arch/skeptic 均未越权裁"该不该做";只裁"怎么做"
- ✅ 反过度设计(CLAUDE.md):零新 API 端点、零新协议字段、埋点 1 处 vs 4 处、总代码增量 <150 行
- ✅ `project_path2_duplicate_event_id`:event_id 稳定契约前提无冲突

---

## 附录 · agent team 协作说明

- **arch**(opus)首轮 baseline 预判 → 收到 fe/skeptic 二轮真实反馈 → 出 v2 final(3 处推翻自己初判)
- **fe**(opus)一轮回 4 UX 判断 + 6 遗漏项(独立 dev server 方案 / 菜单分流 / AbortController 覆盖 / 无 timeout / 按钮冒泡 / marker vs 空白分流)
- **skeptic**(opus)一轮回 8 高 + 5 中/低 风险清单,直发 lead 作独立视角对照
- **lead**(主会话)集成 3 方产出,4 拍板项全同意 arch v2 裁决,落 final_report.md

**关键分歧解决**:
- arch 首版 baseline "4 处埋点" ← skeptic "1 处/attempt" 覆盖(spec 语义 + 反过度)
- arch 首版 "overall diag 不清 env" ← skeptic Corner 3 覆盖(现存 bug + scan pool 挂死风险)
- fe "独立 /debug/event 端点" ← arch v2 拒(`_DEBUG_MODE` 静态短路无风险)
- fe "SerializedEvent.debug_targets 字段" ← arch v2 拒(硬编码 anchor 规则 10 行 TS 足够)
