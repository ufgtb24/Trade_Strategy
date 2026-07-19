# frontend_ux · event_class 过滤器重设计（UI/状态层 rev 3）

> 视角：Vue 3 / Pinia / UX 架构。只谈 UI + 状态 + 交互语义 + 前后端契约里前端诉求的一半；不写代码。
> 相关同仁：`backend_debug`（DEBUG env / debug_ctx / handler）· `skeptic`（第一性原理挑战）· `leader`（综合 final_report.md）。
> Rev 3 收编 backend_debug rev 1 契约对齐 + skeptic Round 2 硬挑战：命名 `DEBUG_EVENT_CLASS` · 契约 C（后端 `debug_enabled_classes`）从可选升级为必需 · pydevd bug 修正 cache spec · 命名从「本回合调试焦点」收窄为「入口 A 的调试焦点 + 镜像 sidebar 展示」· 加 localStorage per (pattern×symbol) key · 撤回 Ctrl+P 类比换第一性论证 · 加发现性混合方案（highlight pulse + brush 前 tooltip）。变更逐条见文末 §10 changelog。

---

## 0. TL;DR

- **过滤器改名「入口 A 的调试焦点 + 镜像 sidebar 展示」**（rev 3 · 接受 skeptic C2 三分诚实）：一个既控 sidebar 展示、也控入口 A brush 触发时的 debug_break 命中的**单一 UI 控件**，**入口 D 独立通道不受此控件影响**（scope 收窄，不再包 D）。前端 SSoT = `viewStore.currentTimeEventClass`。**技术阶段不同**（post-hoc 投影 vs pre-hoc 控运算）不等于 UX 应分层——**用户意图折叠、后端消费展开**是正确的分层原则（详见 §2.4 反 skeptic P1）。
- **UI 位置**：**KlineChart 顶部 toolbar 中一枚常驻 pill/chip「A 焦点：<first-enabled|bo|burst|tb…>」**，独立于任何 detail card 生命周期，只要有 activePattern 就存在。老的 FailedAttemptsCard 内下拉保留、镜像绑同一 ref（老肌肉记忆无缝）。**pill 在 `debugClassOptions.length ≤ 1` 时降级为静态标签**（今天 tb 唯一有埋点 → pill 事实上休眠；明天 backend_debug 埋 bo/gate → 自动激活）。
- **生命周期**：**在 (symbol × activePatternId) 会话内粘性**；切股/切 pattern 才复位到「第一个含 debug_break 的 class」。刷回 brush、关卡片、活动 card 切走 → **一律不清**（当前实现清得过狠，是坑）。
- **默认值不是「全部」**（rev 2 修正 · 接受 skeptic §3）：sidebar 显示 filter 默认「全部」是合理，但**debug pause 语义下「全部」意味着「所有 detector 的 gate 全停」**——这是用户自己在原文里承认的隐患。合并 UI 后默认改为 **pattern 中第一个 ∈ `DEBUG_ENABLED_CLASSES` 的 class**；「全部」保留为下拉选项之一但非默认。
- **filter 变 = 显式重新 debug 意图**（rev 2 新增 · 反 skeptic P2 cache 方案）：filter 变时**允许触发 detector 重跑 + debug env 重写 + 断点可 pause**——这是**用户改 filter 的直觉**，不是缺陷。cache 是优化层用于减少同 filter 下的重复运算，与 debug 语义正交。skeptic 的「改 filter cache hit + 额外按钮才 pause」方案把用户明示的意图外化为额外交互，破坏 debug 直觉（详见 §2.5 反 skeptic P2）。
- **入口 D 与本过滤器解耦**：D 是「针对某 marker 的外科手术」，class_id 已由所点 marker 定死，过滤器不干预；仅在 D 的 target class 与当前 filter 不一致时给一次**非阻断的提示 toast**（防用户以为设了 filter 就万事大吉）。
- **下拉选项**：从 `effectivePattern.topology.nodes[].class_id` 去重 ∩ `DEBUG_ENABLED_CLASSES`（即 `anchorsOf` 键去 `_default`）——只暴露真装了 debug_break 埋点的类；无埋点的类连选项都不出现，避免用户选完发现「怎么点了没停」。
- **过滤命中 debug_break（用户主诉）**：契约上需要 backend_debug 在 v3 之上再增一维 `DEBUG_EVENT_CLASS` env，与 `DEBUG_ROLE` 正交合取；handler 把 `event_class` 从 query param 提升为 env 写入（而非只用于 serialize）。这一维具体怎么落是 backend_debug 的地盘，本 doc 只声明前端契约诉求。**注**：今天 class 门价值 = 0（tb 唯一有 gate 埋点），机制预留是为**backend_debug 未来给 bo/burst 埋点**准备的，避免那天 emergency UI 重设。
- **契约 C 从可选升级为必需**（rev 3 · 接受 skeptic C4）：`/patterns` 必须在 pattern_spec 上暴露 `debug_enabled_classes: list[str]`（后端由 `has_debug_hooks: bool = False` 类属性遍历派生）。前端**完全丢弃**用 `anchorsOf` 键做 fallback 的原方案（那是入口 D 的 anchor 计算表，与 debug_break 埋点无因果关系，今天巧合明天漂移）。
- **localStorage per (pattern×symbol) key 记忆用户选择**（rev 3 · 接受 skeptic C5）：`debug_focus:<pattern_id>:<symbol>` 存 user 选择；加载时若命中且值 ∈ `debugClassOptions` 用之，否则 fall back `first-enabled-class`。消除「每次新 session 都被教育」的痛点。

---

## 1. 问题重述（去 leader 转述的层）

用户主诉是**四条纠缠**：

1. **表意分裂**：`event_class` 参数从来没有真正 gate 过 detector，它只在 serialize 阶段裁 `GateFailure` 列表。这是「结果过滤」不是「运算过滤」。debug_break 只被 v3 的 `DEBUG_ROLE` gate；`role` 与 `event_class` 是两个正交维度，前端却当一个来使。
2. **前置性**：过滤器只在第一次 brush 完成、`FailedAttemptsCard` 挂载后才浮现。用户还没框就想「我这次只看 tb」是够不到的。
3. **一套过滤两处消费**：sidebar 显示过滤 + debug_break 命中过滤，用户希望**一个心智模型、一个 UI、一个状态**。
4. **规模化的隐性成本**：今天只 tb 一家埋 debug_break，未来 bo/burst 都埋后，「全部」默认下 resume 会打空炮无数次。

四条中 (1) 是**契约级 bug**（class_id 维度对 detector 求解不可见），(2)(3) 是 **UX 病**（组件与状态错配），(4) 是**默认策略**（默认「全部」以后越来越贵、要么有绕过手段）。

第 (1) 条是前端做不到的：debug_ctx 得多一维 class_id。但**前端要求这一维存在，才能兑现 (2)(3)(4)**。所以本 doc 会把这个契约诉求写死并交给 backend_debug 落实。

---

## 2. 关键概念对齐（防 skeptic 挑）

**class_id vs role vs anchor.key** 三个词有必要摆清，误用会推错设计：

| 维度 | 值举例 | 定义 | 谁在生产 | 谁在消费 |
|---|---|---|---|---|
| `class_id` | `tb`, `bo`, `burst`, `trend_seg` | detector class 名（`ClassId(detector)` 注册键） | detector 类 | 事件 event 上 `class_id` 字段；filter 想按此过滤 |
| `role` | `first_drought`, `tb`, `trend`, `gate` | 拓扑 node id（多个 role 可复用同一 class_id）；v3 `DEBUG_ROLE` 直接消费 | pattern spec 的 topology.nodes | v3 debug_break kwarg |
| `anchor.key` | `entry` \| `trough` \| `end` \| `gate` | 单个 event 上的语义锚点（不是 node id、不是 class） | 前端 `anchorsOf[class_id](event)` 计算 | 入口 D marker 右键；v3 handler 把它当 `role` 送后端 |

**观察**：v3 把 `role` 一个字段做了两种事：
- 入口 A：`role='gate'` 硬编码 —— 这里 `role` 语义 = 「anchor kind」，不是 topology role id
- 入口 D：`role=anchor.key`（entry/trough/end）—— 同上，也是 anchor kind

所以 v3 里 `DEBUG_ROLE` 实际上不是「topology role」，而是「anchor kind」。名字有点误导，但**机制上**这是一个 anchor 维度的 gate。

**这就意味着**：用户想加的过滤器**在这个坐标系里是正交第二维**，不是取代或改写 v3。v3 的锚点 gate（`DEBUG_ROLE`）和用户想要的 class gate（`DEBUG_EVENT_CLASS`）应该**合取**：`fire ⟺ range 命中 ∧ (DEBUG_ROLE 未设 ∨ role 匹配) ∧ (DEBUG_EVENT_CLASS 未设 ∨ class_id 匹配)`。

这样的好处：
- 入口 A：设 `role='gate'` + `class=<filter>` → 只在选定 class 的 gate 停
- 入口 D：设 `role=anchor.key` + `class=marker.class_id` → 单 bar 单 class 单 anchor，本来就精准，class 维度事实上冗余
- 全部/未设：都退化为 v1 行为

### 2.4 反 skeptic P1：技术阶段不同 ≠ UX 应分层（意图折叠原则 · rev 3 强化）

skeptic rev 1 §1.2 有一个真观察：sidebar 「只看」是 **post-hoc 投影**（作用于 JSON 数组，零运算成本），debug pause 是 **pre-hoc 控运算**（作用于 CPU 执行流，运算已结束就无法追溯 pause）。这一层事实**接受**。

但 skeptic 从「技术阶段不同」滑到「合成一个控件 = 模态混淆」是**滑坡**。反驳如下：

**用户切 filter 时不做模态区分**——他脑中就是「我在调 tb」。UI 不该逼用户在心里回答「我这次是想'看什么' vs '停在哪儿'」。

**rev 3 撤回 Ctrl+P 类比**（skeptic counter D 拆得对）：Ctrl+P 是「filter → open 因果承接」（open 是从 filtered 结果中选一个），我的 pill 是「filter → 两独立后果」（sidebar 展示 + debug pause 无因果承接，只是同源）。类比失当。

**改走第一性论证**：
- 用户脑中意图是**原子** `focus on X`。UI 折叠到一个控件比强分成两个更贴近直觉。
- 后端展开实现（handler 既写 env 也 filter serialize）是**实现选择**，不应反向逼 UX 分层。
- 反过来若 UI 强 fork 成两个 filter，用户必须**主动维护两处一致**（改 debug filter 时想「sidebar 显示要不要也改」→ 每次都做一次心智同步）——这才是真模态负担。

**反 skeptic「先 fork 后 union」的论证**：
- 我方案**不改动** FailedAttemptsCard 里的 sidebar dropdown（§3.6 保留镜像），所以「已用 dropdown N 天」的 muscle memory **无破坏**
- fork（两个控件独立）才是**主动增负担**：用户从今天「一个 filter」变成明天「两个 filter，一个显示一个 debug」——两个新概念要教育
- 「union → 未来真需要时 fork」的代价 <1 天（把 `currentTimeEventClass` 拆两 ref）；「fork → 未来发现是伪需求」的代价 = 教育回滚 + N 天 muscle memory 逆向
- **union 是弱假设、fork 是强假设**——弱假设错了容易修，强假设错了难修

**skeptic 引「debug tb 时同时用 sidebar 看 bo」+「debugger call stack + watch」类比 · rev 3 反驳**：
- debugger call stack + watch 是**同 debug session 内两视图共存**（本项目里已经存在：debug card + FailedAttemptsCard 在同 sidebar 内并列），不是「filter 应该分两个」
- skeptic 引 §7.1「debug card 会有 class=bo 而 pill=tb 的不一致」作证据 → **误用**：那是**入口 D 独立通道**造成的（对应 C2 三分诚实命名），与 sidebar filter 无关。入口 D 场景不能作为「sidebar filter 应与 debug filter 分开」的证据

**结论**：接受 skeptic 的技术层观察，反对 UX 分层结论。**合一控件（scope = 入口 A + sidebar 镜像）+ 入口 D 独立通道 + 后端双消费**是正确抽象。

### 2.5 反 skeptic P2：cache 是优化层，filter 是语义层（不引入「再跑一次」按钮）

skeptic rev 1 §4 提出真正的 root smell：`onTimeEventClassChange` filter 一变即 `triggerTimeQuery` → `/diagnose` handler 重跑 detector + 写 debug env。**这个观察是对的**——耦合是设计缺陷，可以拔除。

**但 skeptic 的具体方案有反直觉问题**：改 filter 变 cache hit（纯投影，不 pause）+ 加「再跑一次」按钮才 pause。这把**用户明确的意图**（改 filter = 换调查目标）**压回成隐式**（cache 状态 + 显式按钮）。用户体感：改 filter → 怎么没停？→ 找按钮 → 每次 debug 两次点击。

**正确分层**（rev 2 主张）：

| 层 | 语义 | 用户可见 | 实现 |
|---|---|---|---|
| Cache | 相同输入避免重复运算 | 否（透明优化） | handler 内 request-hash memoize，key = symbol+start+end+pattern_id+spec_hash+event_class+start_bar+end_bar |
| Filter | 用户显式聚焦意图 | 是（就是 pill） | filter 变 = key 变 = cache miss = 写 env = 允许 pause |

**关键**：cache key **包含** event_class + start_bar + end_bar。这意味着：
- 同 filter + 同区间 + 反复 brush 相同区间 → cache hit → 无重跑无 pause（skeptic 的核心收益兑现）
- 改 filter → key 变 → cache miss → 重跑 → pause（用户改 filter 的直觉兑现）
- 改 brush 区间 → key 变 → cache miss → 重跑 → pause（用户框新区域，本来就该看新断点）

**cache-hit 严格 spec**（rev 3 · 修正 skeptic 抓到的 pydevd bug）：cache-hit 分支必须**跳过 detector 全跑 + 跳过写 env**。原文误说「下次 handler 会重写 env 但断点是同一个，pydevd 不重复停」——错。参 `debug_ctx.py:56` doc string：`pydevd.settrace(suspend=True)` **每次都 fire**（`breakpoint()` 才只报一次）。所以 hit 时若走 detector 会重停。**正确 spec**：handler cache-hit → 直接从 cached result 走 `derive_response` → 不 attach_and_collect、不 analyze、不写 env、不 pause。

**结论**：接受 skeptic 拔耦合的方向，反对具体方案。**cache 是优化层用户看不见，filter 是语义层用户改就是显式重新 debug**。无需「再跑一次」按钮，root smell 已拔。

---

## 3. 设计决策（对应 leader 提出的 7 问）

### 3.1 过滤器住哪里？（推荐：KlineChart 顶部 toolbar 常驻 pill）

**推荐方案**：在 KlineChart 主图上方（现在放 pattern 切换 dropdown、brush 触发按钮的那条 toolbar）**新增一枚常驻 pill**：

```
[ pattern: bottom_breakout_burst ▾ ] [ 🔲brush ] [ 🎯调试焦点: 全部 ▾ ]
                                                    └── 点开：全部 / bo / burst / tb / …
```

- **形态**：pill/chip，非 dropdown 全长控件；点击展开菜单
- **状态可视化**：
  - `全部` → 灰底 + 靶心图标虚化，副标题 hover 提示「命中所有已装 debug 断点的 detector」
  - 具体 class → accent 底色（用 `event_styles[class_id]` 里的颜色做左边一条竖线，与 K 线 marker 用色贯穿）+ 类名醒目
- **位置理由**：
  1. 与「brush」按钮**空间邻近**——这一枚 pill 定义「下一次 brush 的调试焦点」，物理耦合能自解释
  2. 与「pattern 切换」**同轴**——两者都是「本次调试的宏观选择」，不是 detail card 内的局部过滤
  3. 不与 K 线画布抢像素——toolbar 是既有区域，不新开层

**否决的其它位置**（附理由）：

| 位置 | 否决理由 |
|---|---|
| KlineChart 右上角浮动 chip（absolute over 画布） | 遮 K 线右上区域的 marker 与价格轴，浮层与画布无边界感 |
| 全局左侧 sidebar 一栏 | 全局侧栏当前是「pattern list + 扫描历史」的宏观区，加入「调试焦点」是错位的**上下文错配**（调试焦点是 chart 上下文的属性，不是 app 全局） |
| Command palette（`Ctrl+K` 类） | 项目**尚无 command palette**，为一个过滤器搭 palette 是过度设计；发现性依赖用户「知道有这功能」 |
| KlineChart 右键菜单扩展一项「设置调试焦点」 | 隐藏在 marker 右键里，与 marker 语义混（marker 右键是「针对这个 event」的），错位 |
| FailedAttemptsCard 内下拉保留、加一个「记住我的选择」checkbox 冒充前置 | 后置本质没变，只是拖延；用户第一次 brush 前依然见不到 |

### 3.2 过滤态生命周期（推荐：symbol × pattern 会话粘性）

**当前实现**（问题）：
- `clearDetailCard()`（view.ts:494–508）在 close/undo/切股/切 pattern 全清 → 太狠
- `watch(activeDetailCard, ...)`（DetailSidebar.vue:370）activeCard 切走 → 清 → 更狠
- 净效果：只要卡片一切换就丢过滤态，用户几乎不可能沉淀「本次调试就看 tb」

**推荐规则**（重写清空触发 · rev 2 修正「重置到什么值」）：

| 事件 | 是否清 filter | 复位到什么值 | 理由 |
|---|---|---|---|
| brush 完成（`triggerTimeQuery` 结束） | **不清** | — | 用户循环 brush 找漏检时最需要沉淀 |
| detail card 关闭（closeDetailCard） | **不清** | — | 关卡片 ≠ 换调试目标 |
| activeDetailCard 从 time → debug/pair | **不清** | — | 切个查询上下文 ≠ 换目标 |
| undoSwap（pair card 撤回） | **不清** | — | 与 filter 无关 |
| **symbol 变** | **清** | first-enabled-class（见下） | 换股 = 换语境 |
| **activePatternId 变** | **清** | first-enabled-class（见下） | 换 pattern = 换 class 全集 |
| **loadScanFile / clearScanFile** | **清** | first-enabled-class（见下） | 换 dataset |
| **preview 开启/关闭** | **不清** | — | preview 是同 pattern 的另一路参数快照 |

**核心变化**：从「组件生命周期挂钩」改为「语义域切换才清」。两处硬清（`clearDetailCard` 里那行 + `watch(activeDetailCard)`）都删。

**默认值不是「」（"全部"）·rev 2 修正 · 接受 skeptic §3**：

用户原文承认「默认全部有隐患」（一次 brush 会 pause 所有 detector 的 gate）。skeptic 主张两个控件两个默认。我方案是**一个控件、按 debug 语义定默认**：
- **first-enabled-class** = `debugClassOptions[0]`，即 `topology.nodes[].class_id ∩ DEBUG_ENABLED_CLASSES` 交集的第一项
- 今天效果：唯一有埋点 = tb → 默认 tb
- 未来 bo 埋点后：默认可能是 bo 或 tb（取决于 pattern 声明顺序）
- 「全部」保留为下拉选项之一，用户显式点选后才生效

对 sidebar 显示 filter 的**影响**：默认过滤到 first-enabled-class → 首次 brush 后 attempt 列表只显示 tb 的（若未来 bo 也有埋点，视 first 是谁）。这与「显示 filter 默认全部」的直觉稍有出入，但**用户既然是 debug 语境（brush entry A），显示与 debug 焦点一致是合理的**——用户看的和停的是同一件事。若用户想看全部，一次点击切「全部」即可。

**若 `debugClassOptions` 为空**（活动 pattern 没任何埋点）：pill 隐藏；filter 值维持空串（`''`），走既有 v1 行为。

**关于 filter 变的语义（rev 2 新增 · 呼应 §2.5 反 skeptic P2 cache）**：

- 用户改 filter = **显式重新 debug 意图**
- 若 backend_debug 采纳 cache 方案，filter 变即 cache key 变 → cache miss → 重跑 → 允许 pause
- **不引入「再跑一次」按钮**——用户改 filter 就是重新聚焦，不需要额外交互兑现

**localStorage 持久化跨 session · rev 3 采纳**（接受 skeptic C5）：
- key = `debug_focus:<pattern_id>:<symbol>`（per pattern×symbol）
- 加载时：若 key 存在且值 ∈ `debugClassOptions` → 用；否则 fall back first-enabled-class
- pill 改动时同步写入
- 「全部」也可入 localStorage（若用户显式选了）
- rev 2 原反对理由「pattern 变旧值失效」在 first-enabled-class 兜底规则下已不成立（skeptic C5 抓到），保守减状态面不再是压过教育成本的理由

### 3.3 空屏时的发现性

矛盾：pill 常驻很好，但初次登录用户不知道这枚 pill 是干嘛的。

**发现性策略**（rev 3 · 分层，接受 skeptic Round 2 counter E 混合方案）：

1. **首选：pill 的静态自解释**
   - 文案：`🎯 A 焦点: tb` —— 靶心图标 + scope 明示（rev 3 从「调试焦点」收窄为「A 焦点」，反映 skeptic C2 三分诚实：pill 只控入口 A + 镜像 sidebar，不控入口 D）
   - hover tooltip：`brush 框选时,只在此 detector 的 debug_break 处暂停;sidebar 展示同步过滤。入口 D（marker 右键）不受此约束。`
2. **改 pill 时短暂 highlight pulse**（rev 3 · 采 skeptic 混合方案）
   - 用户改 pill 值 → pill 边框做一次 800ms 的 pulse 动画 + 底色短暂加深 → 显式反馈「你改了」
   - 消除「粘性 pill 被误当默认」的隐蔽感
3. **首次 brush 前若 pill 值非 first-enabled → 强制 tooltip 一次**（rev 3 · 采 skeptic 混合方案）
   - 首次调 `triggerTimeQuery` 时（每 session 一次，localStorage 记「已提示」），若 pill 值 ≠ first-enabled-class → 短暂 tooltip：`本次 brush 只在 {当前 pill 值} 的 debug 断点处暂停。`
   - 目的：跨 session localStorage 恢复选择时，用户容易忘上次选了什么——此提示是「你上次选的还在用」的显式提醒
4. **首次 debug 会话 onboarding**
   - 用户第一次进入 debug 模式（`activeDetailCard === 'debug'` 首次触发时），pill 旁弹一个 6 秒的定向 tooltip 箭头：`看,这枚 pill 决定下一次 brush 只在哪个 detector 的 gate 停。设为 tb 就只看 tb。`
   - localStorage 记「见过一次」即隐藏，不吵
5. **命中数反馈闭环**
   - brush 完 → FailedAttemptsCard 头部已有 `框内 N 个 attempt`。补一行 `本次调试焦点: tb（其他 detector 的 gate 已跳过）`。让用户看到 filter 生效。

**否决**：不做 modal onboarding、不做每-brush 强制 modal chip（skeptic Round 2 counter E 已 concede 粘性 pill + 显式反馈的组合优于纯 modal）。

**否决**：不做 modal onboarding、不做 highlight pulse 动画。用户 brainstorming 明确说界面朴素/低干扰。

### 3.4 与入口 D（marker 右键）的组合

**决定：入口 D 不受 pill filter 影响。**

理由：
- D 的语义 = 「针对具体 marker 的外科手术」，marker 本身已经承载了 `event.class_id` 与所选 `anchor.key`
- 若强制 D 也过 filter → 用户点 bo marker 时若 filter=tb，会**看似操作生效实则被静默 skip**——这是最糟的 UX
- 若给 filter 加豁免逻辑「D 无论 filter 都 fire」→ 反而是最一致的（pill 只管 A）

**边界处理：Class 冲突时的软提示**
- 用户 filter=tb，右键点 bo marker → 弹 D 之前给一个 3 秒 toast：`当前调试焦点是 tb,但你正准备停在 bo 的 [entry] 断点。继续将忽略焦点。` + `[取消] [继续]` 两键
- 或者更轻：只在 pill 上短暂闪一次不匹配提示，D 无阻断继续
- 不做静默 no-op（用户的问题里明确说这是 anti-pattern）

**决策规则总表**：

| 入口 | class 维度取自 | role/anchor 维度取自 | pill filter 是否 gate |
|---|---|---|---|
| 入口 A（brush） | pill filter | 硬编码 `gate` | **是** |
| 入口 D（marker 右键） | marker 的 event.class_id | anchor.key | **否**（但 class 与 filter 不一致时软提示） |

### 3.5 下拉选项的来源

**从代码派生，不写死**（rev 3 · 完全丢弃 `anchorsOf` fallback，改用后端契约 C）：

```
debugClassOptions = computed<string[]>(() => {
  const p = effectivePattern.value
  if (!p) return []
  const inPattern = new Set(p.topology.nodes.map(n => n.class_id))
  // ★ rev 3: 数据源改为后端 pattern_spec.debug_enabled_classes（契约 C）
  return (p.debug_enabled_classes ?? []).filter(c => inPattern.has(c))
})
```

- `p.debug_enabled_classes` = 后端 serialize_pattern 遍历 spec.nodes 拿 `detector.event_cls.class_id where detector.has_debug_hooks == True` 派生（契约 C）
- `inPattern` = 当前 activePattern 用到的 class 全集（多个 role 复用同 class 时 dedupe）
- 交集才进下拉：pattern 里没用到的类不出现，埋点没装的类不出现

**为什么丢弃 `anchorsOf` fallback**（rev 3 · 采 skeptic C4）：
- `anchorsOf` 原语义是「入口 D marker 右键的 anchor 计算表」，与 debug_break 埋点无因果关系
- 今天 tb 两者重合是巧合（tb 唯一同时有 anchor + 埋点）
- 未来若 detector X 埋 debug_break 但没在 `anchorsOf` 定义 → UI pill 选不到但断点会触发 → 用户困惑
- 反过来若 detector Y 有 anchor 但未埋 debug_break → UI 出现选项但选完点了不停 → 用户困惑
- 用后端权威数据（作者显式 `has_debug_hooks = True`）避免两向漂移

**若 debugClassOptions 只有 1 个**：pill **仍显示但降级为静态标签**，不出下拉——只有一个选项时选择行为无意义，反而让用户以为可以切别的。文案：`🎯 A 焦点: tb（本 pattern 仅 tb 装了 debug 断点）`。

**若 debugClassOptions 为空**：pill 隐藏。当前状态 = 无可选 → 「全部」也无意义。

**今天 pill 事实上休眠**（呼应 skeptic §7.3 「先量 N」的量化建议）：
- 今天后端契约 C 派生：唯一 `has_debug_hooks == True` 的 detector = tb → `pattern_spec.debug_enabled_classes = ['tb']` → `bottom_breakout_burst` pattern 里 tb 唯一 → `debugClassOptions = ['tb']` → pill 走「1 项静态标签」分支
- **pill UI 事实上不出现下拉、用户看到的是只读标签**——今天 class 门价值 = 0，与 skeptic 量化一致
- 明天 backend_debug 给 bo/burst 加 debug_break + 类上开 `has_debug_hooks = True` → 后端 `debug_enabled_classes` 自动扩展 → `debugClassOptions.length > 1` → pill 自动激活为可切下拉
- **机制预留 + UI 休眠 = 不 emergency 重设，不做 speculative UI**——是对 skeptic §6 YAGNI 挑战的回应

**契约 C 从可选升级为必需**（rev 3 · 已通告 backend_debug）：
- 若 backend_debug 因故不做（比如觉得作者纪律难维持）→ 前端只能回退到 hardcode 白名单，需要在 PR 里同步；这是**失败模式**不是可接受方案
- 好在 backend_debug rev 1 已 propose `has_debug_hooks: bool = False` 类属性，双方对齐

### 3.6 向后兼容

用户旧肌肉记忆 = 「brush → card 出 → dropdown 出 → 调」。新设计**不打断**：

- **FailedAttemptsCard 里的 dropdown 保留**，只是绑同一个 `view.currentTimeEventClass` ref
- 老路径（brush → card 里改）→ 修改镜像到 pill；下一次 brush 用新值
- 新路径（pill 里改 → brush）→ FailedAttemptsCard 出现时 dropdown 已是选中态
- 两处 UI 视为**同一控件的两个 rendering**，就像 email client 里侧栏收件人 & 打开邮件里显示的收件人是一致的

唯一行为差异：以前 dropdown 改一下会**立刻 refetch**（`onTimeEventClassChange` 里 `triggerTimeQuery`）。新设计下如果保留这一 refetch 行为，从 pill 改一下也应该 refetch（若 card 已开着）——不然两处 UI 不对称。所以：

- pill 修改 → 若 `activeDetailCard === 'time' && timeScopeResponse` 有内容 → 用 payload.frame 重发 `triggerTimeQuery`（复用现有 `onTimeEventClassChange` 逻辑）
- pill 修改 → 若无 open card → 只更新 ref，等下次 brush

无迁移友际（不需要 migration），零 breaking。

### 3.7 SSoT

**保留 `viewStore.currentTimeEventClass: Ref<string>` 作为唯一状态**。理由：
- 已存在，已被 KlineChart（读）、FailedAttemptsCard（写）、DetailSidebar（写）三处消费——**改变命名/位置无收益且有 diff 噪声**
- 与其他 store ref（`shiftSelectedEvents`, `activeDetailCard`, `debugTarget`）同层同风格
- 用 composable 是**过度设计**（无跨组件的复杂逻辑，只是 ref + 几个 setter）

**改动**：
1. JSDoc 更新，明确它现在有**两层含义**：
   - sidebar 展示过滤（既有）
   - debug_break 命中过滤（新增，由 URL query 提升为 env）
2. 是否重命名？倾向**不改**——`currentTimeEventClass` 的 `Time` 是历史命名（对应 scope=time），不是精准命名，但改名会波及 3+ 文件，收益低。可在 JSDoc 里备注「名字有历史包袱，语义已泛化到 debug 焦点」。若必须改，候选：`debugFocusClass`。**推迟到 v4 收口时决定，rev 2 不动**。
3. 消费者列表（改后）：
   - **KlineChart** brush handler：读，透传给 `triggerTimeQuery`（已有）
   - **KlineChart** 新增 toolbar pill：读 + 写
   - **FailedAttemptsCard** 内下拉：读 + 写（镜像）
   - **KlineChart.debug-menu.ts**（入口 D）：**不读**（决策 3.4），仅在 class 冲突提示时读一次做对比

---

## 4. 契约诉求（→ backend_debug）

前端 UX 蓝图能兑现，前提是后端配合几件事。我把前端需要的**最小契约**列在这里，实现细节留给 backend_debug：

### 契约 A（必需）：`DEBUG_EVENT_CLASS` env 新维

- handler `/diagnose` 收到 `event_class` query param 且 debug 模式下 → 写 `os.environ["DEBUG_EVENT_CLASS"] = event_class`；finally pop
- `debug_break(i, *, role, class_id)` 签名加 `class_id` 必填 kwarg
- 判定：`fire ⟺ _DEBUG_MODE ∧ range ∧ (DEBUG_ROLE 未设 ∨ role 匹配) ∧ (DEBUG_EVENT_CLASS 未设 ∨ class_id 匹配)`
- 现有 5 处 `debug_break` 调用点补 `class_id='tb'` 等
- 未来 detector 加 debug_break 时，标准签名带 class_id（**detector 内部可以直接用 self class_id 常量**，无用户输入）

### 契约 B（必需）：`event_class` 从 serialize-only 提升为 pre-detect gate + serialize filter 双重消费

- 现状：`event_class` query 只走 `Query.event_class` → `derive_response` 里 filter GateFailure 列表
- 新：既写入 env（供 debug_break gate），也保留 serialize 过滤（前端 sidebar 展示 filter 语义不变）
- **两个用途同源同参数**，前端一个 filter state 出，后端两个消费点

### 契约 C（可选）：`/patterns` 暴露 `debug_enabled_classes`

- 后端知道自己哪些 detector 装了 `debug_break` 埋点，前端硬编码 `DEBUG_ENABLED_CLASSES` 是漂移风险
- 未做时用「约定同步」；若 backend_debug 认为漂移风险大，可先做

### 契约 D（可选，若做多选过滤器）：`event_class` 允许 CSV

- 目前设计单选，不需
- 若未来做「多选调试焦点」（如 tb + bo 同时看），`event_class` query 与 DEBUG_EVENT_CLASS env 都可接受 CSV，后端拆开做 `∈` 判定
- **rev 1 不做，YAGNI**

### 契约 E（澄清项）：DEBUG_EVENT_CLASS 与 DEBUG_ROLE 正交时的语义

- 若 UI 明确 filter=tb + role=gate（入口 A）→ 后端两个 env 都设 → fire iff tb 的 gate
- 若 filter=全部（未设 DEBUG_EVENT_CLASS）+ role=gate（入口 A）→ 只按 role 过 → 所有 detector 的 gate 都停（对应用户「全部」语义）
- 若 filter=tb + 未设 DEBUG_ROLE（假设某场景）→ 只按 class 过 → 只 tb 的所有 breakpoint 都停
- **正交合取**是自然行为，backend_debug 只要按 §2 的公式实现即可

---

## 5. 前端要动的地方（骨架，非代码）

按依赖顺序：

1. **stores/view.ts**
   - 保留 `currentTimeEventClass`
   - 新增 computed `debugClassOptions`（3.5）
   - `clearDetailCard()` 里 **删** `currentTimeEventClass.value = ''`（3.2）
   - `selectSymbol/setActivePattern/loadScanFile/clearScanFile` 保留清空（本来就有）
   - 无需新 action，setter 由组件通过 `view.currentTimeEventClass = v` 直改

2. **components/KlineChart.vue（新增 toolbar pill）**
   - toolbar 区新增一个 pill 组件（可独立成 `DebugFocusPill.vue`）
   - 读 `view.currentTimeEventClass`, `view.debugClassOptions`, `view.effectivePattern?.event_styles`
   - 写 `view.currentTimeEventClass`
   - 修改时若 `activeDetailCard === 'time' && timeScopeResponse` → 触发 refetch（复用 `onTimeEventClassChange` 逻辑，抽到 store 或 composable）

3. **components/DetailSidebar.vue**
   - `watch(activeDetailCard, ...)` 里 **删** `view.currentTimeEventClass = ''`（3.2）

4. **components/FailedAttemptsCard.vue**
   - 无结构变化，dropdown 保留；options 从 `debugClassOptions` 派生（不再硬编码 `''/burst/bo/tb`）

5. **components/KlineChart.debug-menu.ts**
   - 3.4 的软提示：右键 marker 时若 `event.class_id !== currentTimeEventClass && currentTimeEventClass !== ''` → 一次 toast，不阻断

6. **api.ts / triggerTimeQuery**
   - 无签名变化（`event_class` 已在 URL 里）；只是**后端消费面**要按契约 A/B 扩，前端调用不动

---

## 6. 交互流示例

### Flow 1：用户想找 bo 的漏 gate（新工作流）

```
1. 打开股票 A / pattern P (pill: "🎯 调试焦点: 全部")
2. 点 pill → 菜单展开: [全部] [bo] [burst] [tb] → 选 [bo]
3. pill 变: "🎯 调试焦点: bo" (accent 底色)
4. 主图 brush [200, 350]
5. PyCharm 断在 bo detector 的 debug_break 处（如果 bo 装了 gate 埋点）
6. resume → 断在下一个 bo gate ... resume ...
7. brush 结束 → FailedAttemptsCard 出现,dropdown 已选中 bo,列出框内 bo 的 gate failure
8. 关卡片 → pill 仍是 bo（不清）
9. 换 brush 区间 → 依然只停 bo
```

### Flow 2：老用户 muscle memory（brush first）

```
1. 打开股票 A / pattern P (pill: "🎯 调试焦点: 全部")
2. 直接 brush → 所有 detector 的 gate 全炸（今天也是这行为,resume 多次通过）
3. FailedAttemptsCard 出,dropdown 显示 [全部],改为 [tb]
4. refetch → 显示 tb 的 gate failure；pill 同步变 "🎯 调试焦点: tb"
5. 下一次 brush → 只停 tb
```

### Flow 3：右键 marker + filter 冲突

```
1. pill = "🎯 调试焦点: tb"
2. 右键 bo marker → 弹菜单 [entry] [trough] [end]
3. 点 [entry] → 3 秒 toast: "调试焦点 tb 与 bo marker 不匹配,本次操作忽略焦点"
4. 断点触发（class=bo, role=entry, bar=marker.bar）
5. resume → 因为 bar 单点单 class,不会误停别处
```

---

## 7. 尚未解决 / 需 peer review 关注

### 7.1 生命周期：debug card 与 filter 互动

`activeDetailCard === 'debug'` 出现在入口 D 触发时。若 filter=tb + 用户点 bo marker（决策 3.4：D 不 gate），debug card 上会有 `className: 'bo'`，pill 上是 `tb` —— UI 不一致。补救：debug card 上显示 `本次断点 class: bo（不受调试焦点约束）`。用户能理解。**是否需要 pill 在 debug card 打开时打个「~忽略~」删除线** → **过度**，不做。

### 7.2 pill 与 pattern toolbar 挤占

KlineChart 顶部 toolbar 现在还挂哪些东西需要 spot check。若已经很挤，pill 可考虑放右侧对齐（`justify-content: space-between`），或者收窄成图标 + 数字 badge 形态。**rev 2 视 pattern toolbar 现况定，我会补一张 wireframe 或让 backend_debug 帮我看**。

### 7.3 多选是否值得

用户描述里没说要多选，但「同时看 tb + bo」场景合理。**rev 1 单选**，YAGNI；若 skeptic 认为「单选是错的默认」需要重议。

### 7.4 「全部」的默认是否应改为「无」（不停任何断点）

用户明说「当前的过滤器默认应该是"全部"」——按用户意图默认「全部」。但用户又说 (4)「将来带 gate 的 detector 很多，也许会有掺杂大量非目标运算的隐患」。**读起来矛盾**：默认全部 = 隐患，默认无 = 静默。

我的解读：默认「全部」是**语义一致**（不选 = 不过滤），隐患由 (2)(3) 的前置访问性化解——用户在 brush 前就能改，不再需要「事后补救」。这是可接受的 tradeoff。若 skeptic 觉得默认应该是「无」（stop 0 breakpoints unless 显式选），欢迎挑战。

### 7.5 与「入口 A 硬编码 role='gate'」的耦合

view.ts:515 `triggerTimeQuery` 硬编码 `role='gate'`。如果未来入口 A 想支持「brush 后按 trough 停」，这条硬编码就是障碍。**当前不改**，与本 doc scope 无关；但**留个记号**：入口 A 的 role 未来可能也需要 pill 化（第二枚 pill 或与调试焦点合并成「debug filter」组合控件）。

### 7.6 `event_class` 命名 vs `debug_class`

前端 pill 上叫「调试焦点」，URL query 叫 `event_class`，后端 env 叫 `DEBUG_EVENT_CLASS`。**命名有点漂**。是否统一？三处都改代价大，且 `event_class` 已在多个 API 使用（不止 debug 场景）。倾向：
- URL query 保留 `event_class`（既定契约，广义「事件类别过滤」）
- 后端新 env 就叫 `DEBUG_EVENT_CLASS`（明确 debug 用途）
- 前端 UI 文案「调试焦点」（用户看到的高层语义）
- **不追求三处同名**，各层有各自命名合理

---

## 8. 我预设的 skeptic 挑战 + 回应

- **Q**：「统一 filter」是不是把两件不同事强绑了？sidebar 展示过滤本质是「后处理」，debug 命中是「前处理」——阶段不同、性质不同，UI 合一会掩盖阶段差异。
- **A**：用户明说要合一，且**用户的心智模型就是同一个**——「我想调试/查看 tb」。UI 只暴露一个 knob；后端消费面两个（env + serialize filter）用同一个值；架构上两个消费点，但 UX 上一个心智。这不是掩盖差异，是**在正确的层级抽象**。

- **Q**：pill 常驻是不是喧宾夺主？chart toolbar 是给「chart 视图控制」的（切 pattern 是），不是给「后端行为控制」的（filter 是）。
- **A**：语义分层视角对，但用户实际 workflow 里 pill 的**触发时机**与 brush 强绑（brush 之前必须先决定 focus）。放在 brush 按钮旁边是**触发耦合**，不是层级混淆。

- **Q**：为什么不做「点 K 线上 marker 直接把这个 class 设为 filter」？
- **A**：会和入口 D 冲突——marker 点击本身已经是 D 的领地。硬塞新语义会污染 D。pill 是**独立命名的显式控件**，用户意图明确。

- **Q**：3.2 说「symbol 变要清」，但用户可能是「换股同题」（还是看 tb 漏检）—— 清空反而扰。
- **A**：可以选择性放宽——若下一个 symbol 在同 pattern，keep filter。但会让规则复杂。**保守：symbol 变清 + 用户很快能重选**（pill 常驻，一次点击）。若 skeptic 或用户回来说要放宽，rev 2 再改。

- **Q**：入口 D 不受 filter 影响，是不是违反了「一个 filter 一处生效」的对称性？
- **A**：一处生效指的是 UI 一处而不是执行一处。入口 D 是**外科手术**，class 已由所点 marker 定死，filter 冗余；filter 主战场是入口 A（brush 是「粗筛」，需要 filter 做二级筛）。设计上是**清晰的分工**，不是不对称。

### rev 2 追加：反 skeptic 的额外 punch

- **Q（自问 skeptic 的方向）**：你 §4 cache 方案让 filter 变 = cache hit + 额外「再跑一次」按钮 pause，这是不是把 debug 意图外化了？
- **A**：是的。用户改 filter 的直觉 = 「我换调查焦点了」，这个动作**天然是重新 debug 的信号**。skeptic 的方案把这个信号切成两步（改 filter + 点按钮），破坏 debug 直觉。**正确做法**：cache key 包含 filter → 改 filter 即 miss 即重跑即 pause。skeptic 拔耦合的方向对，具体方案错。详见 §2.5。

- **Q**：skeptic §6 说「用户描述的痛是纯想象场景，今天只 tb 有埋点」——你为什么坚持设计 class 门？
- **A**：用户原文「将 gate 作为将来创建 detector 的**标准行为**」是**产品愿景声明**，不是「试想」。YAGNI 前提是「未来可能不发生」；用户是唯一产品所有者，说会发生就是路线图。**但**接受 skeptic 的量化观察——今天 class 门价值 = 0。所以我方案是**「机制预留 + UI 休眠」**：debug_break class_id kwarg、DEBUG_EVENT_CLASS env 都加，UI 只在 `debugClassOptions.length > 1` 时激活；今天用户看不到 pill 下拉，只看到只读标签（因为唯一选项 tb），明天 backend_debug 埋 bo/gate 自动激活。**零 speculative UI，零 emergency 重设**。

- **Q**：skeptic §8 Design X 推「brush 前弹瞬时 modal chip」，你为什么反对？
- **A**：debug 是**高频重复动作**（iterate 找漏检、试参、复现 case）。每次 brush 前弹 modal 是 workflow 税；用户第 5 次 brush 时想的是「快点框」，不是「先确认调试焦点」。粘性 pill（改一次沉淀一整个 session）才符合 debug 的迭代本质。skeptic 的短暂 modal 假设「每次 brush 都是新决策」，与 workflow 不符。

- **Q**：skeptic §1.2 反例「若我 debug 时想停在 tb 但 sidebar 里想看 bo」，一个控件办不到，你如何回应？
- **A**：这个场景**技术上存在、workflow 上极其罕见**。debug 语境下用户注意力聚焦一个 class；若 bo 是调查对象，用户就切 filter 到 bo。**先做 union、rare 场景后 fork**是 UX 演进正解。**若真出现高频反例**，未来加「advanced：sidebar 与 debug 分离」toggle 代价极低（`currentTimeEventClass` 拆成两个 ref）。今天为 1% 场景牺牲 99% 场景的意图统一 = 过早分层。

---

## 9. rev 2 需要 collect 的东西

- backend_debug 对契约 A/B/C 的回应（有无更简的实现路径、有无我漏掉的场景）
- skeptic 对 §7.4 默认值、§8 全部 8 个 Q 的回应（rev 1 收到，rev 2 已收编，见下方 §10 changelog）
- 若我 §7.2 pill 拥挤真是问题，加 wireframe

（Idle 判据：本 doc rev 2 写完 + 已回所有 peer 消息。）

---

## 10. Changelog（rev 1 → rev 2）

**收编 skeptic rev 1 挑战的具体位置**：

| skeptic 点 | 我的响应 | rev 2 落点 |
|---|---|---|
| P1「融合 = 模态混淆」 | 部分接受（技术阶段不同）+ 反对结论（UX 应分层）| §2.4 新章「意图折叠原则」+ VSCode Ctrl+P 类比 |
| P2「cache 是真 root smell」 | 接受方向 + 反对具体方案（不加「再跑一次」按钮）| §2.5 新章「cache 优化层 vs filter 语义层」；§3.2 加「filter 变 = 强制 cache invalidation」表述 |
| P3「用户痛是纯想象」 | 反驳（用户产品愿景声明 ≠ 试想）+ 部分接受（今天 N=1）| §0 TL;DR 加「机制预留 + UI 休眠」；§3.5 加「今天 pill 事实上休眠」段 |
| §3「默认全部错」| 接受修正 | §0 TL;DR + §3.2 默认改为 `first-enabled-class` |
| §7.3「先量 N」| 接受作为量化前提 | §3.5 明说今天 N=1、class 门价值=0 |
| §8 Design X「短暂 modal chip」| 反对 | §8 新 Q/A「debug 是高频重复动作」 |
| §5「env 迁 contextvars」| 判为 backend_debug 地盘 | 契约 §4 保持只声明诉求、实现细节让 backend_debug 定 |

**未收编的 skeptic 挑战**（rev 2 · 保留原立场）：
- skeptic §1.3 「Sidebar 一控件 + brush 时短暂 modal 一控件」的两控件模型 — 坚持一控件（§2.4）
- skeptic §7.2 「event_id 门未来可能需要」 — 承认可能但延后（rev 2 不做，v3 role gate 已覆盖 gate 断点在同 role 下重复 pause 的痛，用户没提 event_id 粒度）
- skeptic §8 Design X 「今天不加任何后端代码，只做 cache」 — 反对（用户产品愿景明确要求 class 门，机制预留是必要的）

---

## Rev 3 changelog（rev 2 → rev 3）

**收编 skeptic Round 2 (C1-C5 + counter D/E)**：

| skeptic 点 | 我的响应 | rev 3 落点 |
|---|---|---|
| C1「cache 你绕开了」 | 已在 rev 2 §2.5，指他未看时点；抓到 pydevd bug 承认修正 | §2.5 加 cache-hit 严格 spec（skip detector + skip 写 env） |
| C2「D 豁免 = 三分不是二合」 | 接受，命名收窄 | §0 全文改「入口 A 的调试焦点 + 镜像 sidebar 展示」；pill 文案「A 焦点」而非「调试焦点」 |
| C3「env 扁平化 vs contextvars」 | 前端立场中立，交 backend_debug | 无 rev 3 落点，backend_debug rev 2 §14 覆盖 |
| C4「DEBUG_ENABLED_CLASSES 语义偷换」 | 接受，契约 C 升级为必需 | §0 明说契约 C 必需；§3.5 数据源改 `pattern_spec.debug_enabled_classes`；丢弃 `anchorsOf` fallback |
| C5「localStorage 反对理由不成立」 | 接受 | §3.2 加 localStorage per (pattern×symbol) key 规则 |
| counter D「Ctrl+P 类比不 apply」 | 撤回类比，改第一性论证 | §2.4 删 VSCode 类比，改「用户意图原子性」论证；反驳「先 fork」用「sidebar dropdown 保留镜像 → union 不破坏 muscle memory」 |
| counter E「Design X modal 你打错靶 + 混合折中」 | 接受混合方案 | §3.3 加「改 pill 时 highlight pulse + 首次 brush 前 tooltip 一次」 |

**收编 backend_debug rev 1**：

| backend_debug 点 | 我的响应 | rev 3 落点 |
|---|---|---|
| 命名 `DEBUG_EVENT_CLASS` 而非 `DEBUG_CLASS` | 采纳（他 handler 层字面可读性论据强） | 全文 sed（DEBUG_CLASS → DEBUG_EVENT_CLASS） |
| 契约 A/B/D/E 对齐 | 无改动 | — |
| 契约 C `has_debug_hooks` 类属性 | 采纳 + 升级为必需（受 skeptic C4 推动） | §0 + §3.5 |
| §2 anchor kind 术语他 rev 2 会补 spec 术语表 | 感谢 | — |
| §5.1 clearDetailCard 删清空无后端影响 | 采纳 | §3.2 表格已确认删清空 |
| cache 段他 rev 2 会改写接我 §2.5 key 含 filter | 加 pydevd 修正强 spec | 已通告 |

**仍分歧（供 leader 综合裁定）· rev 3 Round 3 lock 后 update**：
- **入口 A 的 pill 是否管 sidebar 显示 filter**（双方 downgrade 到 leader-defer · 缩窄自「一控件 vs 两控件」大分歧）
  - 我立场（union）：sidebar dropdown 保留镜像 → 无 muscle memory 破坏 + union→fork 拆 ref 代价 <1 天 + 弱假设错了容易修
  - skeptic Round 3 立场（弱推 fork）：从「强推 fork」downgrade 到「弱推 fork · leader judgment call」，承认 union 论点真实
  - 判据：leader 的 UX 一致性倾向——若「每 UI 控件语义单一 · 抽象层不留 union」则 fork；若「用户意图折叠优先」则 union
- localStorage 是否也存「全部」（我 rev 3 允许，skeptic 未反对）
- env → contextvars 时点（backend_debug 定 v5 独立 refactor，前端立场中立）

**收敛判定（rev 3 Round 3 lock）**：
- **skeptic Round 3 concede 全部 5 项**（C1 pydevd/C2 命名收窄/C4 契约 C/C5 localStorage/E 混合发现性）+ **撤回 debugger call stack + watch 类比**
- **backend_debug rev 2 lock**：cache 段接我 §2.5 spec · 契约 C 采 `has_debug_hooks: ClassVar[bool]` + AST lint 兜底 · env→contextvars 定 v5 独立 refactor · 命名 `DEBUG_EVENT_CLASS` 双方对齐
- **frontend_ux rev 3 lock**：无 rev 4 触发条件，等 leader 综合 final_report.md
