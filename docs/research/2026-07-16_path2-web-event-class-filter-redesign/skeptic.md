# Skeptic 批判稿 · event_class 过滤器/gate 断点重设计

**角色**：skeptic（一等公民地否定用户提案的前提；不做 implementation，只做 counter-proposal）
**同组**：frontend_ux（Vue 3 / Pinia / UX） · backend_debug（detector / handler / debug_ctx）
**日期**：2026-07-16 起草 / 2026-07-17 rev 2 / rev 3 / rev 4
**Rev**：4（收编 backend rev 3 大量 concessions · 前 rev 主体保留于下方作 provenance）

---

## Rev 4 delta（backend rev 3 collapse 后的最终态）

backend_debug rev 3 采纳 5 项 substantive concessions，rev 3 → rev 4 delta：

**A · backend concede C1 沉没成本算术漏洞**
- backend rev 3 §4.4 撤回"3× 差异"论 · 剩轻量"作者纪律"论据（v3 role guide 已存 · class_id 同规格延续 · authoring guide diff ≤ 10 行）
- 把我 counter-counter 的"class 粒度未来可能不适合 bo · 需 event_id / gate_name"新论点抬到 leader 决策 1（"预建 vs 随需增建"哲学分歧）
- D2 判据依然是 bo/burst 埋点 roadmap，但**算术层面 skeptic 立场已被 backend 采纳**

**B · backend 采纳 C2 AST 反射 `_CLASS_ID_REGISTRY`** — 双源消除，S-3 挑战消解。

**C · backend 具体化 C3 contextvars 阻力 · 中立化立场**
- rev 3 §14.1 列出：测试 fixture ~75 行 + authoring guide 模板重写 + integration test 5 个 + contract #7 术语 = ~100 行 refactor
- **"边际近零"具体化后不成立** · skeptic C3 论据被削弱
- backend 不推也不反 · leader 若判可接受可顺手做
- **D4 状态更新**：skeptic 立场从"中等推本轮" downgrade 到"弱推本轮 · leader-defer" · ~100 行 refactor 是真代价

**D · backend 采纳 C4 default sync**
- rev 3 §5.4 明标：前端 pill = first-enabled-class · URL 永远发具体 event_class · handler `if event_class:` skip 分支实际几乎不走 · fallback 保为 curl 兼容 + hypothetical 演进余量
- S-4 挑战全消解

**E · backend 采纳 C5 §4.2 vs §6.3 双标**
- rev 3 §4.2 删除 composite forward-compat 段落 · 硬约束 class_id == event_cls.class_id · 与 §6.3 拒 role optional 统一 YAGNI
- S-5 挑战消解

**F · IDE 条件断点文档化（零代码）**
- backend rev 3 §15 决策 4 建议 v4 spec 加"IDE 条件断点作为替代路径"文档化
- speculative pain 场景下用户始终有 fallback · skeptic §2.1 替代 A 实质纳入

**G · minimum viable v4（§15.2）· backend 给出随需增建路径的具体 spec**
- 若 leader 走 D2 = 推迟 class 门：**契约 C（has_debug_hooks）+ cache + IDE 断点文档化 · 不含 class 门 · class 门推迟到 bo 埋点当天**
- **这是 skeptic 立场的具体化 spec**——backend rev 3 已经把两条路径都给 leader 备选（做 vs 不做 class 门）
- skeptic READY

**H · cache-hit spec 收紧**
- backend rev 3 §8.3 选项 X 严格必需 · 选项 Y 撤回（响应 frontend_ux 击 2 pydevd bug）
- cache-hit 分支根本不走 detector · 不假装 pydevd 幂等

### 决策点更新（rev 3 → rev 4）

| ID | rev 3 状态 | rev 4 状态 |
|---|---|---|
| **D1** | 弱推 fork · leader-defer | 不变 |
| **D2** | 判据=bo/burst 埋点 roadmap | 不变 · **但 backend rev 3 §15.2 已给"minimum viable v4"具体 spec 供 leader 走 skeptic 路径** |
| **D4** | 中等推本轮迁 contextvars | **downgrade 到弱推本轮 · leader-defer**（backend 具体化 ~100 行代价） |
| ~~D3~~ | ~~localStorage~~ | 已消解（frontend_ux concede） |

### skeptic 最终 READY 判定

- 全部 5 项 Round 2 挑战：backend 4 接受 + 1 具体化中立化（C3 只是 downgrade 不是被否）
- 全部 substantive 修正落地：backend 5 项 concessions + frontend_ux 5 项 concessions（前 rev 已记）
- 剩余 3 决策点全部 [BLOCKED-for-leader] · 判据明列
- **skeptic READY**（对应 backend rev 3 征询）

skeptic idle 状态维持。等 leader 综合 final_report.md。

---

_[以下为 rev 3 delta · rev 2 delta · rev 1 主体 · 全部保留作 provenance]_

---

# ==== Rev 3 delta 起（保留作 provenance）====

---

## Rev 3 delta（速览：从 rev 2 到 rev 3 的最终收敛态）

> Peer rev 已 landed：frontend_ux rev 3、backend_debug rev 2。本节反映**最终 skeptic 立场** + **供 leader 决策的 3 项 [BLOCKED-for-leader]**（rev 2 的 D3 已因 frontend_ux concede 而消解）。

### peer rev 落地的 substantive 修正（skeptic 认可）

**frontend_ux rev 3** 采纳 5 项 substantive 修正：
- pydevd bug 修正（cache-hit 分支不走 detector · 消除"下次 handler 会重写 env 但 pydevd 不重停"错论）
- 命名收窄（「本回合调试焦点」→ 「入口 A 的调试焦点 + 镜像 sidebar 展示」· D 独立通道诚实标）
- 契约 C 从可选升级为必需（`/patterns` 暴露 `debug_enabled_classes` · 前端丢弃 `anchorsOf` fallback）
- localStorage per (pattern×symbol) key（消除新 session 反复教育）
- 混合发现性（highlight pulse + brush 前 tooltip · 非纯粘性 pill）

**backend_debug rev 2** 采纳 4 项 substantive 修正：
- §8 cache 重写（采 frontend_ux hybrid 形态 · cache 与 class 门正交）
- §14 contextvars 长期方向（v5 独立 spec · 完整 pseudocode）
- §13 契约 C has_debug_hooks flag（静态可枚举 debug_enabled_classes）
- §1.1.5 anchor kind 泛化承认（对应 frontend_ux §2 一级 finding）

### skeptic 撤回/退让的立场

- **撤回 debugger call stack + watch 类比**（frontend_ux 反驳有效：call stack + watch 是同 sidebar 内共存两视图，对应 debug card + FailedAttemptsCard 本来就已经共存，不是"filter 应该分两个"的证据）。**但原论点（"入口 A pill 同时管 sidebar 显示 + debug gate 是两语义 union"）不依赖该类比，仍成立**。
- **D1 立场从「强推 fork」downgrade 到「弱推 fork · leader judgment call」**：frontend_ux "保留 dropdown 镜像 = 无 muscle memory 破坏 · 未来 fork 拆 ref 代价 <1 天" 是有效反驳。
- **D3 消解**：frontend_ux rev 3 已 concede localStorage per (pattern×symbol) key。
- **沉没成本论 & contextvars 本轮迁 = 判断题，不再打**：我 counter-counter C1（算术漏洞）+ C3（本轮 breaking window 顺手迁）backend 未完全吸收，但两侧都真——backend 有 second-order 论 & operational 论证，我有边际成本论 & 随需增建论，属 leader judgment，不属论证错误。

### skeptic 保留的立场（未被推翻）

- **入口 A pill 的 concept conflation 弱残留**：即使 frontend_ux rev 3 命名收窄，入口 A pill 同时管 "sidebar 展示（post-hoc 投影）" 和 "debug gate（pre-hoc 控运算）" 仍是两语义 union · 抽象泄漏证据（如 §7.1 debug card 显示 class 不一致时的 disclaimer 文案）仍存在。**下调到弱推、非强推**。
- **backend §4.2 vs §6.3 forward-compat 双标**：backend rev 2 未回应。建议 leader 让 backend rev 3 统一 YAGNI 立场。
- **AST test EXPECTED_CLASS_IDS 硬枚举**：backend rev 2 未明确响应，但 §13 has_debug_hooks 已给出反射源头，backend 若延伸到 AST test 反射同源即消解。

---

## [BLOCKED-for-leader] · 3 决策点（rev 2 的 4 点中 D3 已消解）

Leader 综合 final_report 时无法回避的 3 个决策：

### D1 · 入口 A 的 pill 是否同时管 sidebar 显示 filter（一控件 union vs 两控件 fork）

- **frontend_ux 立场**：union（pill 常驻 KlineChart toolbar · sidebar dropdown 保留镜像同 state · 用户 muscle memory 无破坏 · 未来 fork 拆 ref 代价 <1 天）。
- **skeptic 立场（弱推）**：fork（sidebar 保留独立"只看" post-hoc filter · debug 焦点单独控件 · 每 UI 控件语义单一）。
- **判据**：leader 需裁定"UX 意图折叠 · 隐藏 pre-hoc/post-hoc 差异" vs "语义清晰 · 每控件单一职责"哪个优先。
- **skeptic 立场强度**：**弱推 fork · leader-defer** · union 若走通接受 · rev 3 明写"接受 union 意味着 debug card class 不一致时的 disclaimer 文案是已知抽象泄漏、接受为代价"。

### D2 · class 门本轮做 vs 推迟到 bo/burst 埋点当天

- **backend_debug 立场**：本轮做（v3 role guide 已建 kwarg required 纪律 · class 是同规格增量 · 沉没成本论 5 行 vs 15 行）。
- **skeptic 立场**：推迟（预建 framework 用户零收益 · 沉没成本算术把 20 测试隐藏 · 随需增建吸收未来知识）。
- **判据**：**bo/burst debug_break 埋点距今多远**（leader 需从 backend_debug 拿具体 roadmap）。
  - 下一 sprint 就埋 → backend 立场明显对
  - 3+ sprint 才埋 → skeptic 立场明显对
  - 灰区 → judgment call

### D4 · env → contextvars 本轮迁 vs v5 独立 refactor

- **backend_debug 立场**：v5 独立（v4 单 commit ~10 行 · git revert 兜底成本极低 · 混做增 blast radius / leader 独立评估难）· §14.2 已给完整 v5 spec pseudocode。
- **skeptic 立场（中等推）**：本轮顺手（本轮已是 breaking window · 顺手迁三 env 边际成本近零 · 两 commit 分开 preserve revert 粒度 · 避免二次 breaking window）。
- **判据**：leader 决定本轮 scope 是"最小 class 门增量" vs "class 门 + env 结构性升级"。
- **skeptic 立场强度**：**中等推 · leader-defer** · 若 leader 保守走 v5，建议至少 backend rev 3 明写 v5 时间线（防无限期拖延）。

---

## Leader 综合建议

- **若 D2 = 推迟 class 门**：D1/D4 都不迫近讨论 · 本轮只做 cache（frontend_ux 击 2 hybrid 形态）+ IDE 条件断点作 speculative pain fallback + backend rev 3 §14 明写"class 门待 bo/burst 埋点当天回顾"。工作量最小、风险最低。
- **若 D2 = 本轮做 class 门**：D1（union vs fork · 弱推 fork）+ D4（本轮 vs v5 · 中等推本轮）需连带决策 · localStorage 已锁定 on。
- **不论 D2 走向**：
  - sidebar「只看」下拉的 refetch 副作用（`DetailSidebar.vue:362-367`）改为纯前端 filter + backend cache hybrid（frontend_ux 击 2 形态）是**低风险明显收益**，不应被任何决策阻塞。
  - frontend_ux §2 anchor-kind 观察（v3 `DEBUG_ROLE` 实际承载 anchor kind 而非 topology role id）**升为一级 finding**，即使 D2 推迟仍值得在 v3/v4 命名反思里记录（backend rev 2 §1.1.5 已承认此事实）。

## 收敛判定

- skeptic 侧对两 peer 挑战全部收敛或 downgrade 到 leader-defer ✓
- rev 3 delta 已落 · rev 1/rev 2 主体保留 provenance ✓
- 3 项 [BLOCKED-for-leader] 明列 + 判据 + skeptic 立场强度 ✓
- 一级 finding 建议已给 ✓

**skeptic idle 中**，等 leader 综合 final_report.md。

---

_[以下为 rev 2 delta · rev 1 主体 · 保留作 provenance]_

---

# ==== Rev 2 delta（保留作 provenance）====

---

## Rev 2 delta（速览：从 rev 1 到 rev 2 的变化）

> 完整交锋记录见 SendMessage 历史（两 peer 各挑我 5 硬点 / 我挑他俩各 5 硬点 / 双向 counter）。本节只列**结论迁移**。

### 已 concede（peer 反驳有效，我方立场放弃或收窄）

**C-A · cache 不是消解 class 门的银弹**（backend_debug 击有效）
- rev 1 P2 punch：cache 让 filter 变永不重跑 → 用户所有痛点消解 → 不需要 class 门。
- backend 反驳：cache 只解决"filter 变的重复 pause"，不解决"第一次 brush + 未来多 detector 埋点后的单次多 pause"。cache 与 class 门是**正交**能力，各服务不同 pain。
- **收窄**：rev 1 的"cache 让 class 门无必要"是错的。cache 与 class 门各有独立价值域。
- rev 2 立场：cache 该做（服务 filter 变的 pain），class 门是否做**独立决定**（依赖 bo/burst 埋点 roadmap，见 D2）。

**C-B · frontend_ux 击 2 具体 cache 形态优于我原案**
- rev 1 §4 原案：cache miss 走 debug pause · cache hit = 纯投影 · "再跑一次"按钮 = 强制 recompute
- frontend_ux 反案：**filter 变 = 强制 cache invalidate + 允许 pause · filter 不变 = cache hit**。用户改 filter 就是显式换 debug 目标，语义直白无需按钮。
- **接受**该形态作为 Design X 修正版。

**C-C · IDE 条件断点与 web UI 是替代而非取代**（backend_debug 立场）
- rev 1 §2.1 替代 A 主张：IDE 断点条件 `class_id == 'tb'` 覆盖 speculative pain 90%。
- backend 立场：web UI 单点控制是独立价值——用户明说"过滤器"是 UI 概念，IDE-only 让用户失去 UI 层能力，是 downgrade 到 v3 之前。
- **收窄**：IDE 条件断点是 speculative pain 场景的**零后端成本 fallback**（不需要建 UI 就能解决 pain），但 web UI 独立价值成立。若 leader 决定 class 门本轮做，IDE 论证不再重要；若推迟 class 门，IDE 是覆盖 pain 的兜底。

### 保留的挑战（peer 未推翻，rev 2 立场未变）

**S-1 · 融合 filter 是 concept conflation（rev 1 P1）**
- frontend_ux 反驳：Ctrl+P 类比 · "UX 意图折叠" · 用户心智模型是"我在调 tb"。
- 我 counter：Ctrl+P 的 filter+action 是**因果承接**（open = pick from filtered list），而"sidebar 过滤 + debug 命中"**没有因果承接**——只是被同一 state 触发的两个独立动作。类比不成立。
- 更硬证据：frontend_ux §3.4 决定"D 入口完全不受 pill filter 影响" + §7.1 承认 debug card 显示 class=bo 而 pill=tb 时需专门 disclaimer 文案。**他自己已经把"统一 filter"打成了"A gate + sidebar 展示 + D 完全绕过"三分**，兜底文案是抽象泄漏证据。
- 立场保留：**两个 concept 应两个控件**（sidebar 保留独立"只看"下拉、debug 焦点单独控件），而非一 state 同源。

**S-2 · env 应迁 contextvars 而非扩到第四**（rev 1 §5）
- backend conditional accept：倾向迁但看 leader；rev 2 §14 加"长期方向"。
- 我立场：本轮已是 breaking window（加 class_id kwarg 破坏 debug_break signature），顺手迁三 env（DEBUG_BAR_RANGE/DEBUG_ROLE/DEBUG_EVENT_CLASS）到 contextvars 边际成本近零。backend 自己 §11.3 承认 async 时必须迁——那时迁 4 env 比现在迁 3 env 只多 1 单位工作，但会产生第二次 breaking window。
- 立场保留：本轮顺手迁 contextvars。

**S-3 · AST test EXPECTED_CLASS_IDS 硬枚举 = 双源**（Round 2 C2）
- backend 未回应（隐含接受）。
- 立场保留：AST test 反射 `path2/core.py::_CLASS_ID_REGISTRY`，不硬枚举副本。

**S-4 · "全部"作为 debug filter 默认是错的**（rev 1 §3）
- frontend_ux **完全 concede**：sidebar 默认全部 / debug 默认 first-enabled-class。
- backend §5 仍建模"默认全部 = handler 不写 env"——**未 sync 前端最新态**，我 Round 2 C4 指出，等 rev 2 落定。
- 立场收敛：sidebar 全部 / debug first-enabled-class。

**S-5 · §4.2 vs §6.3 backend 双标（forward-compat 选择性 YAGNI）**（Round 2 C5）
- backend 未回应。
- 立场保留：backend 要么都为 hypothetical 保 forward-compat，要么都拒；不能选择性用 YAGNI。推荐删 §4.2 composite 规约段落。

### 已被 peer 反驳但我保留的（我方立场未被打服）

**H-1 · Ctrl+P 类比不 apply**（frontend_ux 击 1 vs 我硬推回 D）
- frontend_ux 未 counter 我的类比拆解（因果承接 vs 无因果承接）。
- 立场保留：Ctrl+P 类比不适用；"意图统一"是包装词，掩盖了 sidebar 与 debug gate 无因果关系的事实。

**H-2 · 沉没成本论算术漏洞**（backend counter vs 我 counter-counter C1）
- backend 说"现在 10 行 vs 未来 30 行"，我拆算发现他把测试从"20 个新测试 ≈ 400 行"隐藏；真沉没成本 ≈ 相当（延后无本质代价）。
- backend 未回。
- 立场保留：沉没成本论是**假**理由 · 真理由是"预建 framework vs 随需增建"的判断题（→ D2）。

---

## [BLOCKED-for-leader] 剩余争议 · 4 决策点

Leader 综合 final_report 时无法回避的 4 个决策：

### D1 · 一控件 vs 两控件（融合 vs 分开）

- **frontend_ux 立场**：一控件（pill 常驻 KlineChart toolbar），sidebar 下拉镜像同 state。理由：UX 意图折叠、用户心智是"我在调 tb"。
- **skeptic 立场**：两控件（sidebar 保留独立"只看"下拉 = 显示过滤 · Debug 焦点单独控件或每-brush modal chip）。理由：concept conflation、抽象泄漏证据（D 绕过、debug card disclaimer 文案）。
- **判据**：leader 需裁定是"UX 意图折叠 · 隐藏实现层差异"优先，还是"语义清晰 · 显式 concept 分离"优先。
- **skeptic 强推**：两控件。若 leader 选一控件，rev 2 需明写"D 完全绕过 filter + debug card 显示 disclaimer 文案"是**已知抽象泄漏、接受为代价**。

### D2 · class 门本轮做 vs 推迟

- **backend_debug 立场**：本轮做（预建 framework · v3 authoring guide 已建 kwarg required 纪律 · 未来 detector 作者自然带 · 沉没成本对称）。
- **skeptic 立场**：推迟到 bo/burst 埋点当天（随需增建 · 保护未来知道正确形态 · 沉没成本论有算术漏洞）。
- **判据**：**bo/burst debug_break 埋点距今多远**：
  - 下一 sprint 就埋 → backend 立场明显对
  - 3+ sprint 才埋 → skeptic 立场明显对
  - 灰区 → judgment call
- **leader 需从 backend_debug 拿具体 roadmap 决断**。若 leader 无 roadmap 信息（backend_debug rev1 §6.2 说"我没看到 backend_debug 有近期 roadmap"——他自己就是 backend_debug），倾向推迟。

### D3 · localStorage 是否用于 debug filter 值

- **frontend_ux 立场**：不用（"陈旧问题" · "跨 session 复用意义弱"）。
- **skeptic 立场**：用（新 session 又回 first-enabled-class · 用户被反复教育 · localStorage 一次收敛）。frontend_ux §7.4 反 localStorage 的原理由在新规则（debug 默认 first-enabled）下已不成立。
- **判据**：leader 需权衡"跨 session 记忆负担"与"每 session 重新教育"两侧成本。
- **skeptic 强推**：per-symbol×pattern key 存储，pattern 变自动 fall back 到 first-enabled。

### D4 · env → contextvars 本轮迁 vs 未来 refactor

- **backend_debug 立场**：conditional accept · 看 leader 是否接受作用域外扩（rev1 §11.3 明写"async 时一起迁"作为长期方向）。
- **skeptic 立场**：本轮顺手迁（breaking window 复用 · 边际成本近零 · 避免二次 breaking）。
- **判据**：leader 需决定本轮 scope 是"最小 class 门增量" vs "class 门 + env 结构性升级"。
- **skeptic 中等推**：迁。若 leader 保守，至少在 rev 2 §14 明写"下一 sprint 强制迁"的时间线，防止无限期拖延。

---

## Leader 综合时的补充建议

- **若 D2 = 推迟 class 门**：那 D1/D3/D4 都不迫近讨论——本轮只做 cache（frontend_ux 击 2 hybrid 形态）+ IDE 条件断点作 fallback + rev 2 §14 明写"class 门待 bo/burst 埋点当天回顾"。工作量最小、风险最低。
- **若 D2 = 本轮做 class 门**：D1 迫近（一/两控件）· D3 建议加 localStorage（避免教育税）· D4 强推顺手迁 contextvars。
- **不论 D2 走向**：sidebar「只看」下拉的 refetch 副作用（`DetailSidebar.vue:362-367`）该改为纯前端 filter（cache hybrid 落地的先决条件），这个是低风险明显收益、不该被任何决策阻塞。

---

## 补充 · rev 1 未提但 rev 2 应记录的观察

**O-1 · frontend_ux §2 anchor-kind 观察是全组最锐利的洞察**
- frontend_ux 拆清 v3 `DEBUG_ROLE` 实际承载"anchor kind"而非"topology role id"——**是这轮讨论最有价值的概念澄清**。
- 我在 Round 2 C3 用这个观察反打他（"两个都塞 env 是扁平化结构化配置"），是这一点的延伸论证。
- 建议 leader final_report 把这个观察**升为一级 finding**——即使 D2 决定推迟 class 门，这个观察值得记录在 v3/v4 命名反思里。

**O-2 · backend 与 frontend 独立 draft 的时间差导致 sync 缺失**
- backend_debug rev1 §5 建模的"默认全部 = handler 不写 env"未收到 frontend_ux 击 5 的"debug 默认 first-enabled"concede。
- 这不是任何 peer 的错，是 draft 时序问题。**rev 2 双方需 sync 后同步落定**，我 Round 2 C4 已经推给 backend。

---

_[以下为 rev 1 主体 · 保留作 provenance · 交锋概览已在 §Rev 2 delta 覆盖]_

---

# ==== Rev 1 主体（provenance）====

---

## 一句话总结

**用户描述的痛在今天不存在**（只有 tb 有 debug_break，"多 detector 争抢 gate 断点"是纯想象场景），**用户提出的解**（融合"显示过滤器" ↔ "debug 过滤器"、前置过滤器发生阶段）**在概念上把两个功能强行捏合**，并且**回避了真正的 root smell**——`/diagnose` 每次 filter 变都重跑一整轮 detector，把"看结果"和"跑运算"耦死了。真正应该问的问题不是"如何设计一个既能做显示又能做 debug 的过滤器"，而是"能否把'看'和'跑'解耦，使得过滤器不再触发运算，从而根本不用担心 filter 命中噪声 gate"。

---

## 顶部三连击（读到这里能引起同组警觉即可）

1. **P1 融合不是设计目标，是错的 UI 简化**。sidebar 过滤器（post-hoc 显示范围）和 debug 过滤器（pre-hoc 命中范围）代表两种完全不同的心智模型，捏合成一个控件会让"过滤器"这个词在下一个阶段的沟通里同时承担两义、埋下设计债。用户以为在追求 parsimony（一个控件解决多需求），实际是在追求 conflation（两个不相干概念被强行同名化）。
2. **P2 真正的 root smell 是"filter 变就重跑"**。今天 `onTimeEventClassChange` 直接调 `triggerTimeQuery` 触发一次新的 `/diagnose` 请求（`api.py:198-254`），而 `/diagnose` handler 又会同时写 `DEBUG_BAR_RANGE`+`DEBUG_ROLE` env。这才是"filter 命中噪声 gate"的物理源头——filter 变本不应该触发 detector 运算。若把最后一次完整 run 的 `gate_failures` 缓存在前端（或 handler 内 memoize），filter 变 = 纯前端筛，永远不会重新命中断点。这条路径一旦选定，用户的所有 pre-brush 疑虑都自动消失。
3. **P3 用户的痛是纯想象场景**。当前代码只有 `throwback.py` 埋了 5 处 `debug_break`（`throwback.py:104, 163, 216, 221, 247`），bo/burst/trend 尚未埋点。用户说"试想下将来每个 detector 都有 gate…"——这是 speculative pain。我们应该问：这个 pain 什么时候真正会发生？会以什么形态发生？我们对未来 detector 埋点的口径根本没有 v3 之外的经验数据，现在就锁死"class 门"字面这种解，很可能到第三个 detector 埋点时就得推翻重设（比如那时候我们发现真需求是"命中 bo 的 gate 但排除 bo 的 trough"——那时 class 粒度不够）。

---

## 1. 是"融合过滤器"这个目标本身错了？

### 1.1 用户的框架

用户原话：

> "有没有可能设计出同时服务于'sidebar 显示过滤'和'gate 调试过滤'两种需求的过滤器？"

隐含前提：一个控件覆盖两种需求是 parsimony、是好设计。

### 1.2 反前提：这两种"过滤"是不同物

- **Sidebar 过滤器**（今天 `FailedAttemptsCard.vue:29`「只看」下拉）：**post-hoc、纯投影**。语义 = 结果集已经算完，我在结果里挑视觉子集。作用对象 = `TimePayload.failed_attempts` 数组。零运算成本、可即时切换。
- **Debug 过滤器**（用户希望的新东西）：**pre-hoc、控运算**。语义 = 决定 detector 内 `debug_break` 会不会在某个 call site 触发 pause。作用对象 = 进程执行栈的 pause 行为。要 pause 只能发生在运算过程中，运算已经结束就无法追溯 pause。

**两种过滤器的作用阶段不同**（一个 pre-run，一个 post-run），**作用对象不同**（一个是 CPU 执行流，一个是 JSON 数组），**用户的心智模型不同**（"我要看什么"vs "我要在哪儿停下来"）。把它们做进一个控件，只有名义上的"parsimony"，真实的代价是：
- 用户切换控件值时要在心里回答"我这次是想'看什么' 还是 '停在哪儿'？"——每次选择都要主动做模态区分。
- 未来若有一个只想改动其中一维的需求（例如"我 debug 时想停在 tb，但 sidebar 里想看 bo 的失败"），单控件模型直接办不到，必须再拆。到那时会撞上 v1 已经上线的用户教育成本。

### 1.3 counter-proposal：不融合，反而分开

- Sidebar 保留今天的「只看」下拉，语义**恒定为"post-hoc 显示筛"**——不再触发 `/diagnose` 重跑（见 §4 caching）。
- Debug 过滤这一步单独放在**框选动作里**（一次性、非全局）：用户按下 Brush → 弹一个瞬时 chip「命中：tb / bo / burst / 全部（默认 tb 或 last-used）」→ 按 confirm 后才走 `/diagnose` with `DEBUG_EVENT_CLASS`。
- 两个控件在视觉上根本不需要放在同一个面板；一个是 sidebar 里的过滤下拉（长驻），一个是 brush 交互时才出现的 modal chip（短暂）。

**推论**：用户以为在追求"一个控件解决两问题"，实际是在追求"一个词覆盖两语义"——那不是设计的进步，是概念混淆的开始。

---

## 2. 是"改 debug_break 加 class 门"这个架构本身错了？

用户的解假设：debug_break 应该 gated on `DEBUG_ROLE` + `DEBUG_BAR_RANGE` + `DEBUG_EVENT_CLASS`（新增第四个 env / 命名可变）。我列三种更根本的替代，然后论证每个的适用性。

### 2.1 替代 A：IDE 条件断点

PyCharm / VSCode 都支持行断点上加表达式条件（`condition: class_id == 'tb'` 或 `condition: current_symbol.get() == 'AAPL'`）。用户在 `throwback.py:104` 加断点、条件写死类，命中即停。

**优点**：
- 零后端代码增量、零 UI、零 env 污染。
- 条件表达式远比 class 门灵活（可以写 `class_id == 'tb' and gate_name == 'phase1_break'` 之类细颗粒条件）。
- 已经是 debug 用户的原生技能，无需学习新工具。

**痛点/反驳**：
- 用户需要打开源码找到 `throwback.py:104`。但**用户已经知道文件行号**（brief 里出现 `throwback.py:145`），所以这个痛点在 skeptic 视角是弱论。
- 无法从网页直接触发 pause——但真的需要吗？网页触发的价值是"看一眼股票、圈一段时间、看断点"——IDE 条件断点 + 网页只观察 GateFailure 结果卡片本来就能覆盖 90%。剩下 10% 是"我不知道要停在哪、想让系统告诉我最近的一次失败在哪停"——但这是 GateFailure 结果卡片解决的问题，不是 debug_break 解决的问题。
- **必答的疑问**：整个 v2/v3 debug 机制到底比 IDE 条件断点多出了什么？看现有代码：
  - `DEBUG_BAR_RANGE` = 网页 brush → 后端把 bar 范围通知 debug_break，让用户不用在 IDE 手写 `if 200 <= i <= 300` 条件。**这个价值是真的**，因为 bar 是数据驱动、不是硬编码常量。
  - `DEBUG_ROLE` = 五个 role 中挑一个（gate/trough/end/end/entry），避免每个 attempt 停 5 次。**这个价值也是真的**，同一函数的多个断点位置在 IDE 里要手动 enable/disable、繁琐。
  - `DEBUG_EVENT_CLASS`（用户新提议） = 多 detector 中只停一个。**这个价值在今天为零**（只有 tb 有断点），在未来是否为真取决于埋点节奏——见 §6 的 YAGNI 论证。

**skeptic 立场**：v2/v3 的两 env 各有自己的独立价值论证，`DEBUG_EVENT_CLASS` 却没有——它是对一个尚未发生的问题的预备。

### 2.2 替代 B：DAG 剪枝——只跑用户选中的 class 的 detector

用户提"过滤命中的 gate 断点"，等价说法可以是"只跑我选中的 class 的 detector"。前者是 detector 都跑但只在选中的地方 pause；后者是干脆不跑其他 detector。

**问题**：pattern spec 里的 DAG 有跨 detector 的边（tb 消费 bo 流，见 `throwback.py:280` `ThrowbackDetector.detect(bo_stream, df)`）。若用户只想 debug tb，必须先跑 bo detector 得到 bo 流才能给 tb 消费。所以"只跑一个"实际是"跑到用户选中的 class 为止 + 用户选中的 class 之前的整条上游"。

这个变体架构上更干净（因为它消除了"跑但不 pause 的浪费运算"），但设计代价高：需要 spec 上有"截断到某 node"的语义，需要重构 analyze 使得部分子图可执行。**投入产出比明显低于 A/C**，除非未来 detector 数量大到跑全 DAG 成本本身不可接受。

**skeptic 立场**：B 是"结构性正确但今天不划算"的方案，值得记录但不推。

### 2.3 替代 C：结果缓存，filter 变永不重跑

这是我最认真推的替代（对应顶部 P2 punch）。核心洞察：**filter 变化本不应该触发 detector 运算**。今天的耦合是设计缺陷、不是必然。

**具体形态**：

- `/diagnose scope=time` 第一次调用时，handler 层跑完 analyze + collect gate_failures，把 result 放进一个 request-hash-keyed cache（key = symbol + start + end + pattern_id + spec_hash）。
- 后续对同一 hash 的 `/diagnose scope=time` 请求（不管 event_class 是什么），handler **直接投影 cached gate_failures**，不重跑 detector、不写 `DEBUG_BAR_RANGE`/`DEBUG_ROLE` env。
- Debug pause 只发生在**第一次**触发 brush 的时刻——那次 fetch 会带 debug env、会 pause。之后 filter 切换是纯投影，不会再 pause。

**这条路径解决了用户描述的所有痛点**：
- "命中噪声 gate 的几率非常大" → 不再发生，因为 filter 切换不再触发运算，运算只发生一次。
- "多次 resume 才能抵达 tb gate" → 不再发生，因为只在 brush 时触发一次；一次 brush 内如果确实有多次 pause（bo/burst/tb 都有断点），那是 debug 本身设计选择的问题（见 §7 的 event_id 讨论），不是 filter 引发的重跑。
- "过滤器只有运行完才出现在界面上、启动框选时没有过滤器" → 变得**无关**：因为 filter 是 post-hoc，用户根本不需要在 brush 之前设置它。第一次 brush 结果拿到后再挑 filter，改 filter 不再重跑、也就没有 gate 噪声风险。

**代价**：
- 需要一个 request-hash-keyed cache。handler 层的实现小坑：cache 生命周期（LRU size / TTL / config 变更失效）需要拍板。skeptic 建议：**per-process 内存 dict + LRU=16**，配合 spec 变更（config PUT 时）显式 `.clear()`。
- 需要一个"forced re-run"逃生阀（用户显式想再次 pause 时）。skeptic 建议：URL 加 `?force_recompute=1` 或 UI 增加"再跑一次"按钮，语义清晰。

**skeptic 强主张**：这才是真正的架构正解。用户提出的"融合 filter + 前置阶段"是没有意识到"filter 触发重跑"是可拔除的耦合。

### 2.4 三个替代的对比

| 方案 | 后端代码增量 | UI 改动 | 用户痛点覆盖 | 副作用 |
|---|---|---|---|---|
| A（IDE 条件断点） | 0 | 0 | 90% | 需要用户熟 IDE 条件语法 |
| B（DAG 剪枝） | 中（analyze 拆分） | 中（class 选中前置） | 100% | spec 语义扩展、跨 detector 依赖处理复杂 |
| C（结果缓存） | 小（handler cache 层） | 小（保留 sidebar 下拉、去掉重跑触发） | 100% | 需要 cache 失效纪律、需要 forced-rerun 逃生阀 |
| 用户方案（DEBUG_EVENT_CLASS 第四 env） | 小（debug_break 加 class 门、handler 加第四 env） | 中（pre-brush filter 前置） | 100% | 环境变量污染面扩大、"融合过滤器"埋概念混淆 |

按 blast-radius / 值得程度看：**C > A > B > 用户方案**。

---

## 3. "全部"作为默认是错的

用户原话：

> "当前的过滤器默认应该是'全部'，将来如果带有 gate 的 detector 很多，也许会有掺杂大量非目标运算的隐患。"

用户自己已经在这句话里承认"全部"作为默认有隐患。但同时他说"当前的过滤器默认应该是'全部'"——这是**为了保持今天的行为不变**。**这个"不改变行为"的动机本身就是错的**，理由如下：

### 3.1 "全部"的语义不成立

在**显示过滤器**语境下，"全部"有明确语义——不隐藏任何 attempt。这没问题。

在**debug 过滤器**语境下，"全部"意味着"所有 class 的 gate 都 pause"。今天 = tb 一个 class，跟"只 tb"没差别；但根据用户设想的未来（每个 detector 都有 gate），"全部"= 一次 brush 会连续 pause 数十次跨 class 的断点。**这个默认行为一旦发生一次，用户会立刻切走它、并且再也不切回来**。也就是"全部"这个选项在 debug 语境下**根本没有实用价值**，除非"全部"就是当天默认（用户尚未接触任何 debug 之前）。

### 3.2 三选一

在 debug 过滤语义下，四种默认可选：
- **默认 = "全部"**（用户方案）——即刻违背用户自己写的"命中噪声 gate 的几率非常大"警告。**淘汰**。
- **默认 = 上次选择**（per-pattern 或全局记忆）——需要状态持久化（localStorage 或后端 config）。中等实现代价。有个隐患：跨 session 不显式，用户可能忘记上次选了什么。
- **默认 = pattern spec 第一个含 debug_break 的 class**——deterministic，无记忆需要。但需要一个"class 是否已埋 debug_break"的元数据（今天没有；`DEBUG_ENABLED_CLASSES` 是前端硬编码的，见 `view.ts:63`）。
- **默认 = null（必须显式选）**——最保守，最防误命中。但每次 brush 都要多一步交互，对高频 debug 用户是税。

**skeptic 立场**：显示过滤器的默认 = "全部"，debug 过滤器的默认 = "pattern spec 第一个含 debug_break 的 class"。**两个控件、两个默认**，各按自己的语义合理化。用户的方案（一个控件、一个默认）逼你在两语义间选一个折中，怎么选都拧巴。

---

## 4. 重跑 /diagnose 才是真正的 root smell

**这一节和 §2.3 是同一个论点，从不同角度剖**。

### 4.1 现状描述

打开 `DetailSidebar.vue:362-367`：

```
function onTimeEventClassChange(v: string) {
  view.currentTimeEventClass = v
  const frame = timeScopeResponse.value?.payload.frame
  if (!frame) return
  view.triggerTimeQuery(frame[0], frame[1], v || undefined)
}
```

filter 一变 → 立刻 `triggerTimeQuery` → 后端 `/diagnose scope=time` → handler 会（`api.py:212-215`）写 `DEBUG_BAR_RANGE` + `DEBUG_ROLE` env → detector run 全跑一遍 → 若 debug_break 命中就 pause。

**这个链条的每一节都是设计选择，都可以断掉**。

### 4.2 为什么会有这个链条

历史推测（我没读全 commit log，欢迎同组补正）：`/diagnose` 一开始就是"一入口按参数返回结果"，`event_class` 作为查询参数自然进 query。filter 变即 query 变即请求变，一切自然。

但**这个自然是数据请求的自然、不是 debug 语义的自然**。debug 语义应该是"用户操作动作触发一次运算 + 一次 pause"，filter 只是操作结果的投影。今天这个链条把"投影"和"运算"绑死了。

### 4.3 拔除耦合的代价

在 handler 里加一层内存 cache：
- key = (symbol, start, end, pattern_id, spec_hash)（不含 event_class、start_bar、end_bar 之外的会引发 detector 结果变化的字段——注：`start_bar/end_bar` 只影响 debug env，不影响 detector 运算结果本身，故 key 不含）
- value = `(diag, spec, result_with_gate_failures)`
- LRU=16，spec change / config PUT 时 clear。
- handler 逻辑：cache hit → 走 `derive_response` with cached values；cache miss → 正常跑 attach_and_collect + analyze + cache（cache miss 才写 DEBUG_BAR_RANGE，因为只有这次才真会 pause）。

**代码增量估计**：cache dict + LRU + hit/miss 判断 + config-clear hook，约 30-50 行。

**破坏面**：
- `spec_hash` 需要一个稳定的 spec 哈希函数。若没有，实现代价上涨。
- 跨 process 不共享（handler 是 sync + single-process，这不是问题；但如果未来 handler 拆多 worker，cache 就失效——不过那时候 debug 语义本身也要重设，见 §5）。

**破坏面 vs 收益**：明显收益压倒代价。

### 4.4 拔除后的世界

- 用户操作 = brush → 一次 `/diagnose`（cache miss → 运算 → 结果 + 一次 debug pause，若埋点命中）→ 结果卡片出现。
- filter 变 = 前端筛已有 gate_failures 或 backend cache hit 快速投影 → 无 detector 运算 → 无 pause。
- 若用户想"再命中一次断点"，显式点"再跑一次"按钮 → 强制 cache miss → 运算 → 又一次 debug pause。

**这个世界不需要 pre-brush 过滤器**，不需要"融合 sidebar+debug"，不需要 DEBUG_EVENT_CLASS。用户描述的所有痛点全消解，只多了一个"再跑一次"按钮。

---

## 5. env 耦合是真隐患还是 FUD

### 5.1 现状

`api.py:212-254`：

```
if start_bar is not None and end_bar is not None:
    os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
if role:
    os.environ["DEBUG_ROLE"] = role
try:
    ...
finally:
    os.environ.pop("DEBUG_BAR_RANGE", None)
    os.environ.pop("DEBUG_ROLE", None)
```

代码注释里明确写了：

> ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env，undefined under concurrency, single-user debug tool.

作者自己承认这是单用户 debug 工具、并发下行为 undefined。今天没炸，因为：
- handler sync，一个 request 完全处理完才处理下一个。
- debug 工具默认单用户。

### 5.2 加第四 env 会加剧吗

`DEBUG_EVENT_CLASS` 加进来 = env 数量 +1。若 handler 保持 sync + single user，行为没退化。但一旦哪天 handler 走 async / 多 worker，就有：
- 请求 A 写 `DEBUG_EVENT_CLASS=tb` → 请求 B 写 `DEBUG_EVENT_CLASS=bo` → 请求 A 的 detector run 里 env 已经被 B 覆盖。
- 单 env 就有 race，多 env 只是 race 面积线性扩大，不是本质加剧。

### 5.3 有没有更好的耦合形状

**替代 D**：thread-local storage / context vars。`debug_break` 从 contextvars 读 config，handler 用 `contextvars.copy_context()` 装配 context 再 run。这在 async 世界里天然隔离，sync 世界里也没退化。

**替代 E**：detector protocol 加一个 `debug_config` 可选参数。detector.detect(bo_stream, df, *, debug_config=None) → detector 内部把 debug_config 透传给 `debug_break`。彻底去 env。

**代价对比**：
- E 需要改 Detector protocol，破坏面大（所有 detector 都要接这个可选参、`run()` 变参透传要传第三参）。今天不划算。
- D 只改 debug_ctx.py + handler 两点，破坏面小。

**skeptic 立场**：env 是今天的合理妥协、但不是长期正解。若这一轮设计有余力，值得顺手迁 D（把 `_DEBUG_MODE`/`DEBUG_BAR_RANGE`/`DEBUG_ROLE` 全部搬进 contextvars）。若没余力，**这一轮至少不要新增第四个 env**（加第四 env 是把技术债从"3 个 global env"扩到"4 个 global env"，方向错）。

**推论**：若你接受 §4 的 cache 方案，本节的疑虑几乎自动消失——因为 cache hit 时根本不写 env，只有 cache miss 才写一次；而 cache miss 恰好对应用户的显式 debug 意图，那时候 env race 也不是敌人（一次 request、一次 run、一次 pause）。

---

## 6. 用户的痛现在真存在吗（YAGNI）

用户原话：

> "试想下，如果我将创建 gate 作为将来创建 detector 的标准行为后，每个 detector 都会有一个 gate，那么命中噪声 gate 的几率就会非常大。"

**关键动词：试想**。用户在提出的是一个假想的未来痛点，而不是今天的痛点。

### 6.1 今天的埋点分布

`grep -rn 'debug_break' path2/`：
- `path2/atoms/throwback.py`：5 处（entry + trough + 两个 end + gate）
- 其他 detector（breakout.py / distribution.py / platform.py / trend.py）：0 处

一次 brush 触发 tb 计算时：
- brush 一段跨越 3 个 bo 事件 → 每 bo 尝试一次 evaluate_throwback → 每 attempt 触发 `debug_break(bo_idx, role='entry')` → 若阶段一 gate 失败还触发 `debug_break(gate_idx, role='gate')` → 若成功也触发 `debug_break(trough_idx, role='trough')` 和 `debug_break(end_idx, role='end')`。
- 一次 brush 可能 pause 十几次。

**这个"pause 十几次"的问题今天已经存在**，用户提到"想查看 tb gate 是否命中，但还有很多 detector 也有 gate"是错的——今天只有 tb 有 gate，多 gate 的问题体现在**tb 自己的 role 之间**（entry vs trough vs end vs gate），不是跨 detector。

`DEBUG_ROLE` v3 恰好解决了这个"role 之间过滤"的问题。**如果 v3 role gate 已经解决了 5 处 tb 断点的过滤**，那用户的下一次 brush 只会 pause 一次（选中 role='gate' 就只在 gate 处停）。

### 6.2 那"跨 detector 过滤"的痛什么时候真会来

当 bo/burst/trend detector 各埋 5 处 debug_break（对齐 tb 的密度）时，一次 brush 会 pause = 4 detector × 5 role = 20 次（若不做任何过滤）。若用户对 DEBUG_ROLE = 'gate' 做过滤，则每 detector 1 处、共 4 次 pause。**4 次里想只保留 tb**，class 门确实有价值。

**但**：4 detector 都埋 debug_break 这件事，今天并不迫近。看 backend_debug 的当前 roadmap（我不知道具体，欢迎补正），如果这一轮或下一轮就要给 bo/burst 埋点，那 class 门有硬需求；如果 6 个月内都不会碰其他 detector 的埋点，那 class 门是纯 speculative。

**skeptic 主张**：**现在设计 class 门的最合理形态是"占位"**——留一个 pluggable extension point（例如 `debug_break` 已经支持 kwarg，`class_id` 通过第二个 keyword 传入，DEBUG_EVENT_CLASS 只是决定 gate），代码增量控制在极小（<20 行），UI 完全不动。等真的第二个 detector 埋点、真的第一次遇到跨 class 争抢时，那时候的实际使用形态会决定 UI 应该长什么样。**过早设计 UI 是浪费**。

---

## 7. class_id 是正确的过滤维度吗

用户说"event_class"。我想追问：一次 brush 内如果确实有多个 tb attempt 都命中断点，用户能只挑其中一个吗？

### 7.1 场景

Brush 一段跨越 5 根 bo → 5 次 evaluate_throwback → 5 次 `debug_break(bo_idx, role='entry')`。用户设 DEBUG_ROLE='entry' + DEBUG_EVENT_CLASS='tb' → 依然 pause 5 次。

**用户能不能说"我只想在第 3 个 bo 触发的那次 tb attempt 里 pause"？** class 门不够粒度，需要 event_id 门。

### 7.2 event_id 门是否 YAGNI

- 优点：真正的 pinpoint pause，一个 attempt 一次 pause。
- 缺点：用户要能"选中一个 event"。今天的 UI 已经允许通过 KlineChart marker 右键选中一个 event（`KlineChart.debug-menu.ts`），并且这就是"入口 D"的模式。所以 UI 侧的选中机制不缺，缺的是把"选中的 event_id 传给 debug_break"的通路。

**skeptic 观察**：现状里入口 A（brush，硬编码 role='gate'，见 `view.ts:515` "★ v3 · 入口 A 硬编码 role='gate'"）和入口 D（右键选 event，触发 event-anchored debug）本来就是**两套并列的 debug 触发路径**。入口 A 是"框段区间，看所有失败 attempts"；入口 D 是"点某个成功 event 的 anchor bar，看它是怎么算出来的"。**class 过滤只在入口 A 里有意义**；入口 D 已经是 event_id 精度。

**推论**：class 门对入口 A 是补丁，但对入口 D 是重复。若真要设计 class 门，必须明确它**只作用于入口 A**，不要污染入口 D 的 code path。这也是"两 control 分开"的另一佐证：入口 A 有自己的 class-picker（在 brush 交互里），入口 D 不用。

### 7.3 什么样的"精度"是刚好

- class 门：解决"跨 detector 争抢"（今天为零、未来看埋点节奏）。
- role 门：解决"同 detector 内不同 call site 争抢"（v3 已上）。
- event_id 门：解决"同 role 同 class 但不同 attempt 争抢"——**这个痛点用户没提**。是否要做取决于用户提没提。

**skeptic 立场**：**class 门是 v3 role 门自然的下一档粒度**，但未必是必然的下一档。倘若 v3 role 门在今天的埋点密度下已经把"一次 brush pause N 次"的 N 缩到用户可接受，那 class 门整个是浪费。**先量一下 N**。

---

## 8. Counter-proposal：三种 counter-design（不是实施提案，是让 leader 选择的 shape）

### Design X · 保守（skeptic 首推）

- **不加**任何新 env，**不改**任何 debug_break 签名。
- 在 `/diagnose scope=time` handler 加一层 request-hash cache（§4）。filter 变化不再触发重跑。
- Sidebar 「只看」下拉保留，语义收敛为"post-hoc 显示筛"，去掉 `triggerTimeQuery` 副作用改成纯本地 filter。
- KlineChart brush 交互里挂一个瞬时 modal chip「本次 brush 命中的 class」（选项：tb / bo / burst / 全部）——UI 只在**未来 debug_break 覆盖 >1 class 时启用**，今天禁用。
- 未来 backend_debug 埋 bo/burst 断点时，同 PR 打开这个 chip 的 UI。

**投入产出**：C+D 加起来 ~80 行后端 + ~30 行前端。100% 覆盖用户痛点，且不引入任何用户-面的新概念。

### Design Y · 中庸

- Sidebar 「只看」下拉不动。
- 加 DEBUG_EVENT_CLASS env（第四 env），contextvars 迁移（§5 替代 D）。debug_break 加 class 门。
- Sidebar 下拉不作为 debug 过滤触发源——完全 post-hoc。
- KlineChart brush 前弹一个 class 选择器 modal（`view.ts` `triggerTimeQuery` 加 event_class 参数从 modal 输入而非 sidebar 下拉）。
- Filter 变化仍然重跑（不做 cache），保留今天的重跑语义。

**投入产出**：debug 过滤和显示过滤分开，用户教育成本清晰。但仍有"重跑触发 pause"的 root smell 未拔。

### Design Z · 激进（用户当前思路的字面兑现）

- Sidebar 「只看」下拉进化为"融合过滤器"，pre-brush 阶段就出现（可能挂在 K 线右上角、不依赖框选结果）。
- DEBUG_EVENT_CLASS env 加进来。
- Filter 变化触发重跑 + debug env 写入。
- 用户在 brush 之前先选 filter，brush 后按选中的 filter 触发运算 + 命中。

**投入产出**：字面满足用户，但从此把两个 concept 绑死一个控件，未来拆分成本高。

**skeptic 推荐**：X。若 backend_debug 论证今天就必须支持 class 门（例如他自己近期就要埋 bo detector），则退到 Y。**任何情况下都不建议 Z**。

---

## 9. What the leader must decide

Leader 综合时不能回避的 2-4 决策：

1. **cache-first 还是 filter-first？** 是先做 handler cache（§4）让 filter 永不重跑，然后 filter 就不再是问题；还是先做 filter 门（§2 用户方案）让 filter 变的时候只 pause 一次？**这两个方案不冲突但先后决定架构走向**。skeptic 强推前者。
2. **class 门今天必需 or 未来预留？** 今天只有 tb 有断点，class 门的价值取决于 bo/burst 是否近期就要埋点。**这一条 leader 必须问 backend_debug 拿出 roadmap 决断**——若近期埋，class 门做实（设计 Y）；若不埋，class 门占位（设计 X）。
3. **一个控件 or 两个控件？** 用户方案 = 一个，融合。skeptic 立场 = 两个，语义分开。frontend_ux 可能有 UX 论据支持任一方向，leader 必须裁定。
4. **env 是否顺手迁 contextvars？** §5 讨论的替代 D。这是与本 spec 松耦合的重构，leader 可决定"本轮做 / 下一轮做 / 永远不做"。

---

## 10. 送同组的 pointed challenges

### 送 backend_debug 的核心挑战

> **你打算怎么给 bo/burst 埋 debug_break？如果你的 roadmap 里 bo 埋点在 3 个 PR 之外，那 class 门今天设计就是 speculative；如果在下一个 PR 就要埋，那 class 门是刚需但设计形态要跟你埋的方式契合。请把 bo 埋点的意图先说清，再讨论 class 门。**

### 送 frontend_ux 的核心挑战

> **你把 sidebar 「只看」和 debug 过滤合成一个控件，用户切换值时要在心里回答"这次是想'看什么' 还是 '停在哪儿'？"——每次都要做模态区分。请举一个 UX 原则说明"一个控件承担两语义"是好设计，而不是"更少组件 == 更好 UX"的滑坡。**

### 送两位共同的挑战（P2 punch）

> **今天 filter 一变就走 `triggerTimeQuery` 就走 `/diagnose` 就写 `DEBUG_BAR_RANGE`。这个链条把"筛结果"和"跑运算"绑死了。若我们在 handler 加一层 request-hash cache，filter 永不重跑，用户描述的"命中噪声 gate"物理上就发生不了。你们的 spec 有没有考虑过这条路径？如果没有，为什么？**

---

## Meta：Rev 2 前的自我检查表

Round 2 我要读 backend_debug 和 frontend_ux 的 draft，然后针对下列点找证据反驳/被反驳：

1. 他们有没有正面回应 §4 cache 方案？如果他们绕开这个方案没有讨论，那是重大 gap。
2. 他们的 class 门实现是否耦合到入口 D？如果耦合，我要指出 §7.2 的边界。
3. 他们提出的默认值是否是"全部"？如果是，我要用 §3 反驳。
4. 他们是否用 contextvars 或仍在扩 env？如果仍在扩 env 但没论证 §5 的替代 D，我要问。
5. 他们的 UI 是否让 filter 长驻还是短暂 modal？我倾向短暂 modal（§8 Design X），我要看他们的选择及论据。
