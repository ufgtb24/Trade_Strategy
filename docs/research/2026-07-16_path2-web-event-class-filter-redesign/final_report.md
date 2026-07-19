# Path2 Web · Debug 过滤器重设计 · Final Report

**日期**: 2026-07-17
**上下文**: v3 role gate 刚 landed (7 commits `79c1c8c..c84bcbd`,未合 master)。用户报告切换 sidebar 「只看」下拉每次都真发新的 `/diagnose` 请求、每次都重命中 tb gate 断点,并提出更深的设计问题:能否让同一个过滤器同时服务于"sidebar 显示过滤"和"gate 调试过滤",且**过滤器必须能在 brush 之前设置**。
**Team**: `frontend_ux` (Vue3/Pinia/UX opus) · `backend_debug` (Python detector/handler/debug_ctx opus) · `skeptic` (tom 视角 opus) · `leader` (综合)
**Rev 状态**: frontend_ux rev3 · backend_debug rev3 · skeptic rev4 均 idle · 用户拍板 D1-D4 已收(2026-07-17)

---

## 一句话结论

**方向**: v3 之上平行叠加"class 门"作为第五层 gate,前端 KlineChart toolbar 常驻 pill「A 焦点」显式控制入口 A + 镜像 sidebar 展示(**union · tom 第一性裁决**)。**入口 D 完全独立不受 pill 影响**。v4 scope 已锁定:class 门 = **机制预留 + UI 休眠**(与 auto source_tag 同风格)· cache **v4 做 P1**(拔 root smell)· env → contextvars **N/A · 不做**(本机单用户前提下 env 污染 race 不会实际发生)· pill 选择 localStorage per (pattern×symbol) **on**。

---

## 载入前提约束(2026-07-17 用户确认)

**Web UI 永远只是本机应用**,只借助浏览器操作 —— 单用户 · 单浏览器 · 本机 backend · 不面向多用户共享 · 不打算做 SaaS/多租户。

**受此前提影响的决策**: R11(D4a env → contextvars)从"v5 独立 refactor"改为"**N/A · 不做**"—— 见 R11 详细论证。

**推翻边界**: 若未来项目场景切换为多用户 / SaaS / 后端并发承载多客户端,需重新评估 R11。届时也要重估 handler `finally` env pop 的软护栏是否够用。

---

## 一级发现(升级自 frontend_ux §2)

**v3 `DEBUG_ROLE` 名字虽从 topology role id 借来,实际承载语义已是"anchor kind"**。

三个概念的正确坐标系:

| 维度 | 值举例 | 定义 |
|---|---|---|
| `class_id` | `tb`, `bo`, `burst`, `trend_seg` | detector class 名(`ClassId(detector)` 注册键) |
| `topology role id` | `first_drought`, `tb`, `trend` | pattern spec `topology.nodes[].node_id`(多个 role 可复用同一 class_id) |
| **anchor kind** | `entry` \| `trough` \| `end` \| `gate` | 某 detector 内部特定的 attempt entry / phase-success bar / gate 失败点(5-elements enum) |

v3 的两入口都是把 anchor kind 塞进 `DEBUG_ROLE`(入口 A 硬编码 `'gate'`;入口 D 传 `anchor.key` ∈ {entry, trough, end})——**topology role id 从未参与 debug 门限**。今天 tb 是单 topology role · 单 class · 两者字面偶然相等,漂移未暴露;未来 detector 若一个 class_id 挂在多个 topology role 上,v3 spec 里"anchor.key ≡ role"的简单映射就会崩。

**裁决**(2026-07-17 team 时点): v4 **不做名字重构**(改名波及多文件、纯符号收益)。但 **v4 spec 必须显式标注**:`DEBUG_ROLE` 承载"detector anchor kind",与 topology role id 无因果关系。任何后续设计文档引用 v3 时必须澄清这一点。

**这是 team 讨论最有价值的概念澄清,无论 D2 决策走向都值得记录。**

**更新(refactor 已落地)**: 上述"不做名字重构"的裁决已被用户推翻并执行——`debug_break` 的 `role` kwarg / `DEBUG_ROLE` env / URL query `role` 已全部重命名为 `anchor_kind`(Python)/`anchorKind`(TS)/`anchor_kind`(URL query 和 env),与 topology role id 的命名冲突已消除。本节上文的三坐标系表格与概念澄清作为历史记录原样保留;下文 R1-R12 等其余章节里出现的 `DEBUG_ROLE`/`role` 字样是 team 讨论发生时点的原始命名,未随本次 refactor 追溯改写,阅读时请以本段更新为准。

---

## 已裁决决策(leader 单方裁定)

### R1 · Cache-hit spec (承 frontend_ux §2.5 修正 pydevd bug)

**决策**: 若做 handler cache,cache-hit 分支必须 **完全跳过 detector 全跑 + 跳过写 env**。

- **前置事实**(pydevd doc string 确认): `pydevd.settrace(suspend=True)` 每次都 fire;`breakpoint()` 才只报一次。skeptic rev1 原案假设"下次 handler 会重写 env 但断点是同一个,pydevd 不重复停"是错的。
- **正确 spec**: handler cache-hit → 直接从 cached result 走 `derive_response` → **不** attach_and_collect、**不** analyze、**不**写 env、**不** pause。
- **cache key**: `(symbol, start, end, pattern_id, spec_hash, event_class, start_bar, end_bar, role)` — 显式包含 filter 与 bar range,filter 变即 miss 即重跑即允许 pause;同 filter + 同区间反复 brush = hit。

**为什么单方裁**: 纯技术事实,pydevd 行为不可讨论。

### R2 · Cache 与 class 门是正交能力(承 skeptic C-A concede)

**决策**: cache 与 class 门解决不同 pain,可独立进入,优先级由 D2/B1 决定。

- **cache** 解决 "filter 变(或用户 undo 回同 filter)重复重跑" 的 UX pain
- **class 门** 解决 "未来 bo/burst 埋 debug_break 后单次 brush 内跨 class 争抢" 的 scaling pain
- skeptic rev1 P2 punch "cache 让 class 门无必要"是错的(rev2 已承认):cache 只解决 filter 变的重复,不解决单次 brush 内多 class 埋点同时炸

**为什么单方裁**: team 内已达成事实共识(skeptic rev2 §Rev2 delta C-A 明写"收窄")。

### R3 · Debug filter 默认 = first-enabled-class(不是"全部")

**决策**: `debugClassOptions[0]` = pattern.debug_enabled_classes ∩ pattern.topology.nodes[].class_id 的第一项。今天效果 = tb(pattern 里唯一有埋点的 class)。

- 用户原文承认"默认全部有隐患"(将来 detector 多时 resume 打空炮)
- team 内已收敛(frontend_ux rev2 §0 + skeptic rev1 §3 双方同意)
- 「全部」保留为下拉选项,用户显式点选后才生效

**为什么单方裁**: team 内已达成共识。

### R4 · 入口 D 不受 pill filter 影响 · sidebar dropdown 保留镜像

**决策**:
- 入口 D(marker 右键)完全独立通道:class_id 由所点 marker 定死,不受 pill 约束
- 边界处理:当 D target class 与 pill filter 不一致 → 3 秒非阻断 toast 提示,不做静默 no-op
- sidebar `FailedAttemptsCard` 内 dropdown **保留**,绑同一 `viewStore.currentTimeEventClass` ref(镜像)—— 老用户 muscle memory 无破坏

**为什么单方裁**: frontend_ux + skeptic + backend 三方基本同意入口 D 独立;dropdown 保留是零改动。skeptic 用"debug card 显示 class=bo 而 pill=tb 时需 disclaimer 文案"作为"融合是抽象泄漏"证据 —— 这个证据是**由 R4 造成**(D 独立),而非融合的固有问题。R4 意味着接受"一枚 pill 只管入口 A + sidebar 镜像"三分实际形态(参 D1)。

### R5 · 命名 `DEBUG_EVENT_CLASS`(非 `DEBUG_CLASS`)· 采纳 backend 命名

**决策**: env 名 = `DEBUG_EVENT_CLASS`;URL query = `event_class`(既有);前端 pill 文案 = 「A 焦点」;detector kwarg = `class_id`。

- 与 URL query `event_class` 字面对齐,handler 可读性最强
- 与既有 `DEBUG_BAR_RANGE` / `DEBUG_ROLE` 命名模式一致度(全大写、单义)
- `DEBUG_CLASS` 有歧义(读者可能猜"class 是不是 Python class")

**为什么单方裁**: 纯命名争议,不涉及产品价值观;frontend_ux rev3 已表态"命名各层合理即可"(rev3 §0),skeptic 未明确反对。

### R6 · 契约 C(`has_debug_hooks` ClassVar flag)与 class 门同做

**决策**: 若 class 门本轮做(D2 = 本轮),则契约 C 一并做:
- Detector 类加 `has_debug_hooks: ClassVar[bool] = False`,作者埋 `debug_break` 时同 diff 改 `True`
- `serialize_pattern` 遍历 `pattern.nodes[].detector.has_debug_hooks == True` 派生 `debug_enabled_classes`
- AST lint 兜底:静态扫 detector 文件,有 `debug_break` call 但类上 flag 未 True → test fail

**为什么单方裁**: 若 D2 = 本轮,契约 C 与 class 门同时性 = 免除"前端硬编码 vocabulary + 后端埋点漂移"的可预测失败模式(用户选到不存在的 class / 有埋点的 class 前端没暴露)。增量 <30 行,防护价值显著大于成本。若 D2 = 推迟,契约 C 自然一起推。

### R7 · IDE 条件断点方案不重议

**决策**: 保留 web UI 独立价值(用户明说要"过滤器")。IDE 条件断点是零后端成本 fallback,可写进 tips 文档,**不取代 web UI**。

- skeptic rev2 §Rev2 delta C-C 已 concede 为"speculative pain 场景的兜底方案,非取代 web UI"
- backend 立场成立:IDE-only 让用户失去 UI 层能力,是 downgrade 到 v3 之前

**为什么单方裁**: skeptic 自己承认弱论。

### R8 · D1 一控件 vs 两控件 = **union**(tom 第一性裁决 · 2026-07-17)

**决策**: 采 union · KlineChart toolbar 常驻 pill「A 焦点」+ sidebar `FailedAttemptsCard` dropdown 保留镜像绑同一 `viewStore.currentTimeEventClass` ref。

**论证**(tom · opus):

1. **第一性:UI 控件 = 用户意图表达,非技术阶段显影**。用户改「只看 tb」和「只停在 tb」时脑中同一原子意图「我在调 tb」。skeptic 的技术分层观察(post-hoc 投影 vs pre-hoc 控运算)真实成立,但从"技术阶段不同"滑到"用户心智应分层"缺一环推导 —— skeptic Round 3 自 downgrade 为"弱推 leader-defer"承认此论弱。
2. **可逆性不对称,union 是弱假设、fork 是强假设**。sidebar dropdown 保留镜像 → 老用户 muscle memory 无破坏,pill 只是同一 state 的第二个 rendering;若未来真发现分离需求,拆 `currentTimeEventClass` 成两 ref 代价 <1 天 = 减弱耦合、不是新概念。反向 fork→union 是引入新耦合,是真概念反向教育。
3. **入口 D 独立造成的 disclaimer 文案不是 union 的抽象泄漏证据,是 R4 的伴随代价**。fork 方案也需要处理 D → bo 而 pill/sidebar → tb 的三分情形,fork 亦无法免疫此 disclaimer;此泄漏与 union/fork 之争正交。
4. **speculative pain 不能压真 pain**。"未来可能需要独立控制显示 vs debug"场景今天不存在,而"今天用户想'调 tb'时被逼在两个控件间同步"心智同步税是 100% 真发生的。为 1% speculative 场景付 99% 主用例的分层代价 = 过度设计,违奥卡姆。
5. **用户原文的一手证据**。用户原话"同时服务于两种需求的**过滤器**"用**单数** —— 是产品意图声明,不是措辞随意。产品所有者已声明意图是折叠,设计者的洁癖不应反向推翻。

**skeptic 的技术观察**保留为**已知抽象泄漏、接受为代价** —— pill 文案「A 焦点」已显式收窄 scope(不再号称"全局 debug focus"),这就是 union 对 skeptic 观察的诚实妥协形态。

### R9 · D2 class 门 scope = **机制预留 + UI 休眠**(用户裁定 · 2026-07-17)

**决策**: v4 只做机制预留 —— `debug_break` signature 加 `class_id: str` required kwarg + `DEBUG_EVENT_CLASS` env + 5 处 tb 埋点补 `class_id='tb'` + 判据 `range ∧ role ∧ class`(class=None 时匹配任意 class)。UI pill 因 `debugClassOptions.length ≤ 1` 自动休眠为只读标签(今天事实上不出现)。bo/burst 埋点当天再补 pill 激活 + 契约 C 由静态标签升级为下拉。

**论证**:
- 与用户先前 auto source_tag 决策同风格(机制预留但今日无用,避免二次 breaking window)
- backend rev3 撤回沉没成本论 · 但作者纪律"早晚"论仍成立 · 预留 signature 让未来埋点 diff 极小
- bo/burst roadmap 未明 · cache(R12)已消解用户当前实体 pain · 3 sprint 内做 pill 激活极快

### R10 · D3 localStorage 记忆 = **on · per (pattern×symbol) key**(用户裁定 · 2026-07-17)

**决策**: 前端 pill 选中值 localStorage 记忆 · key = `debug_focus:<pattern_id>:<symbol>` · 加载时值 ∈ `debugClassOptions` 则用,否则 fallback first-enabled-class。跨 session 恢复选择时用「首次 brush 前 tooltip 一次」提示"你上次选的还在用"(R4 已含混合发现性)。

**论证**: team 已收敛(rev3 双方同意) · 每 session 重教育税不划算 · fallback first-enabled 化解陈旧值风险。

### R11 · D4a env → contextvars 迁移 = **N/A · 不做**(用户前提确认 · 2026-07-17)

**决策**: v4 保持 env 结构不变,只在既有三 env 之上加第四个 env `DEBUG_EVENT_CLASS`(mirror 现有 `DEBUG_ROLE`)。**env → `contextvars.ContextVar` 迁移不做** —— v4 不做、v5 也不做,直接从 roadmap 删除。

**前提**: Web UI 永远只是本机应用(用户 2026-07-17 明确) —— 单用户 · 单浏览器 · 单 backend 进程。

**论证**:
- `contextvars` 迁移**唯一**的技术动机 = 解决 `os.environ` 进程全局多请求并发污染问题(FastAPI sync handler 在 uvicorn threadpool 并行,多线程共享 env,请求 A 写 `DEBUG_ROLE='gate'` 与请求 B 写 `DEBUG_ROLE='trough'` 会互相踩)
- **本机单用户场景下**:一次只有一个 brush 请求在跑,`os.environ` 事实上是**每请求独占**;handler `finally` pop 是充分护栏
- 唯一残留 race = 用户开多 tab · 在第一次 debug pause 挂住期间到第二个 tab 再点 brush · 现象是"第一次 resume 后 detector 后续 `debug_break` 读到被第二次 pop 的空 env,走 v1 fallback 全 fire"。发生率极低 · 现象可预测非崩溃 · 用户可自我规避
- 100 行 wholesale refactor(三 env 全换 `ContextVar.set/reset` · handler 全改 · 单元测试 fixture 全改 · 集成测试 monkeypatch 全改 · v3 landed 的 test 全 revalidate)换一个"几乎不发生 · 发生了行为可预测"的 race = 违 YAGNI、违奥卡姆
- fork 与 backend 原推 v5 独立、skeptic 弱推本轮迁 —— **三方论证都建立在"未来一定要迁"的前提上**;此前提在本机单用户场景下不成立,收益归零

**推翻边界**: 若未来项目场景切换为多用户 / SaaS / 后端并发承载多客户端,需重新评估;届时也要重估 handler `finally` env pop 是否够用。当前不做。

### R12 · D4b backend cache 时机 = **v4 P1**(用户裁定 · 2026-07-17)

**决策**: handler 加 dict 缓存完整 detector 结果 · cache key = `(symbol, start, end, pattern_id, spec_hash, event_class, start_bar, end_bar, role)` · cache-hit 严格 skip detector + skip 写 env(见 R1) · 作为 v4 P1 与 class 门机制预留并行(相互独立,可独立 commit / 独立 revert)。

**论证**: team 共识(backend + skeptic 独立立项建议) · 拔"filter 变即重跑"root smell,直接消除用户报告的 sidebar dropdown 切换重命中 gate 断点噪音 · 不阻塞低风险明显收益 · 不该等 v5。

---

## 完整方案(按裁决落地 · 待 D1-D4 敲定后展开为 plan)

### 前端(frontend_ux rev3 §3-5)

1. **UI**:
   - KlineChart 顶部 toolbar 新增 pill「🎯 A 焦点: <class>」,brush 按钮邻近
   - pill 在 `debugClassOptions.length ≤ 1` 时降级为只读标签(今天事实上休眠)
   - 修改时若 `activeDetailCard === 'time' && timeScopeResponse` → 复用 `onTimeEventClassChange` refetch 逻辑
2. **状态**(`viewStore.currentTimeEventClass`):
   - 删 `clearDetailCard` 里 `currentTimeEventClass.value = ''` 一行
   - 删 `DetailSidebar.vue` `watch(activeDetailCard, ...)` 里的清空
   - 保留 `selectSymbol/setActivePattern/loadScanFile/clearScanFile` 里的清空(换语境才清)
   - 复位到 first-enabled-class(不是空串)
   - 加 localStorage per (pattern×symbol) key,fallback first-enabled(R10 已定 on)
3. **发现性**(rev3 §3.3):改 pill 时短暂 highlight pulse(800ms) + 首次 brush 前若 pill 值 ≠ first-enabled → tooltip 一次
4. **数据源**:`debugClassOptions` 从后端契约 C `pattern_spec.debug_enabled_classes` 派生,不再用 `anchorsOf` 键 fallback
5. **入口 D**:不接 pill filter,冲突时 3 秒 toast 提示(R4)

### 后端(backend_debug rev2 §2-3)

1. **`debug_break` signature**: `(i: int, *, role: str, class_id: str)` —— 双 required kwarg,无 default
2. **判据**: `range_match ∧ role_match ∧ class_match`(三 gate all-and 短路)
3. **`_read_class()`** mirror `_read_role()`,读 `DEBUG_EVENT_CLASS` env,未设或空串返 None
4. **Handler**:
   - `if event_class:` 才写 env(mirror `if role:`)
   - `finally` 无条件 pop 三 env(`DEBUG_BAR_RANGE` + `DEBUG_ROLE` + `DEBUG_EVENT_CLASS`)
5. **5 处 tb 埋点**: 追加 `class_id='tb'` kwarg(逐处 Edit)

### 契约 C(R9 · v4 机制预留下 · 简版)

1. Detector 类加 `has_debug_hooks: ClassVar[bool] = False`(默认 False)
2. tb 的 `ThrowbackDetector.has_debug_hooks = True`
3. `serialize_pattern` 派生 `debug_enabled_classes: list[str]` · 今天单元素 `['tb']` · 前端读到只有 1 项时 pill 降级为只读标签
4. AST lint 兜底(`test_debug_break_class_contract.py`):静态扫 detector 文件,有 `debug_break` call 但类上 flag 未 True → test fail

### backend cache(R12 · v4 P1 · 与 class 门机制预留并行)

1. Handler 加 module-level dict cache · key = `(symbol, start, end, pattern_id, spec_hash, event_class, start_bar, end_bar, role)`
2. cache-hit: 从 cached 走 `derive_response`,**不** attach_and_collect、**不** analyze、**不**写 env、**不** pause(见 R1)
3. cache-miss: 走 v3 现有 detector run 路径,run 后把结果存入 cache
4. cache 大小 / TTL:先无限制(单 handler 进程 · 单开发环境)· v5 后再评估 LRU 上限
5. sidebar `DetailSidebar.vue::onTimeEventClassChange` 保持原语义(仍发新请求 · cache 自然命中不重跑)—— 无前端改动

### 测试(backend_debug rev2 §7)

- **单元** `test_debug_ctx.py`: +8 class gate 测试 + 4 组合测试
- **契约锚** `test_throwback_debug_roles.py`: role Counter → (role, class_id) 二维 Counter
- **通用契约** `test_debug_break_class_contract.py`(新):跨 detector 静态扫 class_id str literal + 值 ∈ registered set
- **handler env** `test_diagnose_role_env.py`: +5 class env 生命周期测试(mirror role env)
- **集成** `test_diagnose_role_integration.py`: +4 class-purity + 组合矩阵测试

### e2e checklist(参 v3 场景 J 模式)

场景 K1(pill 一控件): brush + pill=tb → 只 tb.gate pause
场景 K2(默认 first-enabled): 打开新 pattern → pill 自动 = tb
场景 K3(D 独立): pill=tb + 右键 bo marker → toast 提示 + 断点仍 fire
场景 K4(v1 兼容): curl 无 event_class → 所有 detector fire(未来 bo 埋点后验证跨 class union)

---

## 收敛的共识(供未来 impl plan 参考)

1. v3 role gate 是既成事实,v4 只叠加不重写(commits `79c1c8c..c84bcbd` 不动)
2. `debug_break` 三 gate all-and 短路组合(range → role → class 顺序)
3. env `_read_*` 空串等同未设(v1/v3 兼容 fallback)
4. Handler `if X:` 判据写 env(空串 skip),`finally` 无条件 pop
5. 前端两入口的 role 契约不变(入口 A 硬编码 `'gate'`,入口 D `anchor.key`)
6. 契约锚测试用 str literal + AST 静态解析(抗 lineno 漂移)
7. 集成测试 monkeypatch `pydevd.settrace` 为 counter,避免真 pause
8. `viewStore.currentTimeEventClass` 保持,不重命名(名字有历史包袱但改动波及大)
9. sidebar `FailedAttemptsCard` 内 dropdown 保留(镜像同 state)
10. 入口 D 完全独立通道(不受 pill 约束)

---

## 推迟到 v5 及以后的项

- **多选 class filter**(`DEBUG_EVENT_CLASS="tb,bo"` CSV):YAGNI,单选特例已覆盖用户诉求
- **排除 class 语义**(`"!tb"`):YAGNI
- **event_id 门**(skeptic §7):同 role 同 class 但不同 attempt 的争抢过滤 —— 用户未提,当前 UI 通过入口 D 已能定位单 event
- **DAG 剪枝方案**(skeptic §2.2):"只跑选中 class 的 detector 及其上游"是结构性正确但今天不划算
- **v3 `DEBUG_ROLE` 重命名为 `DEBUG_ANCHOR_KIND`**:纯符号 refactor,不做

## 明确不做的项(即使 v5 也不做,除非前提变)

- **env → contextvars 迁移**:R11 已判 N/A · 本机单用户前提下污染 race 事实上不会发生 · 100 行 wholesale refactor 收益归零 · 只有场景切多用户 / SaaS 才重新评估

---

## Provenance

### Draft 路径(rev 终稿)

- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/frontend_ux.md` (rev 3, 545 行)
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/backend_debug.md` (rev 2, 898 行)
- `docs/research/2026-07-16_path2-web-event-class-filter-redesign/skeptic.md` (rev 2, 505 行)

### 关键交锋节选

- **frontend_ux 反 skeptic P1(合成 = 模态混淆)**: rev3 §2.4 撤回 Ctrl+P 类比 → 改第一性论证 "先 union 后 fork 是弱假设"
- **frontend_ux 反 skeptic P2(cache 方案)**: rev3 §2.5 修正 pydevd bug + 提出 cache key 含 filter 规格 → 促成 backend rev2 §8 cache 立场从"拒"变"正交"
- **backend 反 skeptic 沉没成本论**: rev2 §4.4 显式论证 "今做增量 ~10 行 vs 迟做 ~15+ 行分散多 PR + 打破作者习惯"
- **skeptic C-A concede**: rev1 P2 punch "cache 消解 class 门" 承认收窄 → 两者正交
- **skeptic C4 推动契约 C 升级**: rev1 "anchorsOf fallback" → rev3 完全丢弃 fallback,契约 C 从可选升级为必需
- **frontend_ux §2 anchor-kind 观察 → 一级发现**(skeptic rev2 O-1 提议 · leader 采纳)

### 收敛判据

- frontend_ux rev3 明确"若 skeptic Round 3 无硬新论点则 rev3 定稿" —— 已 idle
- backend_debug rev2 明确"peer round 2 若有新 challenge 会补 rev3;否则视 idle" —— 已 idle
- skeptic rev2 明确"backend_debug rev 2 若提硬新论点会解 idle 补一轮;否则不再挑" —— 已 idle
- 三方全部 idle · [BLOCKED-for-leader] 4 决策点全部整理进 §待用户裁决决策

---

_Final report 定稿 · 全部决策已收(R1-R12 · 一级发现 · 载入前提约束)· 用户拍板 2026-07-17 · 可展开为 v4 impl plan · 建议 v4 分两条 commit 线并行:(A) class 门机制预留 = signature + 第四 env + 5 处 tb 补 class_id + 契约 C 简版 · (B) backend cache P1 · 独立可 revert · 前端 pill UI 因 debugClassOptions.length≤1 静态标签 · Task 5 e2e checklist 场景 K1/K3/K4 手动验证 · env → contextvars 迁移 N/A(本机单用户前提)_
