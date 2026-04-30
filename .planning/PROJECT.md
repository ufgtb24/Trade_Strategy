# AI Feature Induction Framework

**Developer Success Metric (中文):**
最终能够将归纳出的 feature 通过 add-new-factor skill 落实到代码上,完成股票筛选。

## What This Is

一个基于 Claude / GLM-4V / DeepSeek / fastembed 多模型协作的"K 线形态特征归纳框架",通过用户挑选样本 → AI 跨样本对比归纳 → Beta-Binomial 累积评估的闭环,把用户对 K 线形态的直觉显性化为可被 mining 流水线和 `add-new-factor` skill 复用的 `observed_feature` 库。框架是 mining 流水线的上游候选生成器,与 `BreakoutStrategy/dev`、`BreakoutStrategy/live`、`BreakoutStrategy/mining` 解耦(ADR-001)。本 PROJECT.md 仅覆盖 AI Feature Induction Framework,不覆盖既有 13 个因子或现有突破策略代码。

## Core Value

**让 AI 把用户在 K 线图上的"直觉好坏"翻译成可累积、可超越、可遗忘的特征条目,最终通过 `add-new-factor` skill 转写成因子代码,完成股票筛选。**

特征质量必须由机械的 Beta-Binomial 后验主导(ADR-005),AI 只负责"看图归纳",绝不允许 AI 自行调整 (α, β) 或绕过 Replay/Re-induction 通路自我增强。

## Requirements

### Validated

<!-- Phase 0 已经完成 -->

- ✓ **PHASE0-DATA-BASELINE**: 5 个盘整字段 + 多周期 chart 渲染器 + nl_description 预处理 pipeline (Phase 0 完成,35 测试 PASS,端到端 vertical slice 跑通) — Phase 0

### Active (v1 = Milestone 1: Feature Induction Framework MVP)

#### Phase 1 — Librarian + Inducer MVP (本次 SPEC 范围)

- [ ] **REQ-phase1-package-skeleton**: 在 `BreakoutStrategy/feature_library/` 下新增 7 个 Python 模块 + 测试,并在 `glm4v_backend.py` 添加 `batch_describe`
- [ ] **REQ-inducer-batch-induce**: 实现 `batch_induce(sample_ids, backend, *, max_batch_size=5) -> list[Candidate]`,产出新 candidate features
- [ ] **REQ-inducer-prompt-protocol**: 提供 `INDUCER_SYSTEM_PROMPT` (中文,K≥2,严格 YAML) + `build_batch_user_message`
- [ ] **REQ-glm4v-batch-describe**: GLM-4V backend 扩展多图调用,硬上限 5,>5 抛 ValueError
- [ ] **REQ-embedding-l0**: 384-d fastembed 文本嵌入 + cosine 相似度封装 (复用 `news_sentiment.embedding`)
- [ ] **REQ-feature-store**: features/<id>.yaml CRUD,`F-NNN-<text-slug>.yaml` 文件名规则
- [ ] **REQ-observation-log-granularity**: ObservationLog 内联在 features yaml,粒度为 (sample_id, feature_id),`epoch_tag/superseded_by` 在 schema 中预置 null
- [ ] **REQ-librarian-upsert-candidate**: cosine 命中合并 / 未命中新建,supporting/silent 两类 obs 写入,Phase 1 仅实现 `merge_policy=full`
- [ ] **REQ-librarian-recompute**: Beta-Binomial 重算 (Jeffreys prior 0.5; Phase 1 锁 γ=1.0、λ=1.0、C=0),signal=Beta_P5(α,β),5-band 派生
- [ ] **REQ-librarian-lookup-by-cosine**: cosine 阈值检索 (默认 0.85),按余弦降序返回
- [ ] **REQ-features-yaml-schema**: 14 个顶层字段固定,obs 13 个字段 (含 null 默认的 epoch_tag/superseded_by),signal/status_band 派生不持久化
- [ ] **REQ-entry-script-feature-mining-phase1**: `scripts/feature_mining_phase1.py`,无 argparse,参数声明在 `main()` 顶部
- [ ] **REQ-test-coverage**: 30–40 个新测试,合 Phase 0 共 65–75 PASS
- [ ] **REQ-end-to-end-smoke**: AAPL × 5 样本,产出 ≥1 candidate,生成 features/F-*.yaml
- [ ] **REQ-runtime-data-gitignored**: `feature_library/` 持续保持在 `.gitignore`
- [ ] **REQ-invariant-blind-inducer**: Inducer 永远不读 library,prompt 不含任何已存在 feature 内容
- [ ] **REQ-invariant-cli-no-feature-content**: CLI/入口脚本只暴露 sample_ids 给 Inducer,不暴露 feature 文本

### v2+ (Milestones 2+, 待 spec 摄入)

Phase 1.5 / Phase 2 / Phase 3 / Phase 4a / Phase 4b / Phase 4c 的 requirements 在各自 SPEC 文档摄入后再补。当前仅在 ROADMAP.md 中以 placeholder + scope 摘要存在。

### Out of Scope (来自 ADR-021)

- Coder subagent / L2.5 codified verifier — Phase 1–3 不引入
- Critic 高阶动作 split / merge / abstract — 推迟到 Phase 4c (optional)
- Archetypes / 抽象层 / 跨 archetype 类比 — 不在 v1
- 量化的 13-factor overlap 评分 — Phase 4+ 才考虑 `factor_overlap_declared` 字段
- 算法路径 (Apriori / FP-Growth) — 与 AI 归纳路线互斥,不采用
- p0 base rate / 控制语料 — 与 ADR-002 矛盾,永久剔除
- L2 archetype hint — 推迟到 Phase 4b (optional)
- NL Adapter `feature-mine ask` — 不在路线图
- Reshuffle stratified-by-source-feature — **永久拒绝** (会泄漏 feature 身份给 Inducer,违反 §4.3 blind 约束)
- 多视角增强 (同 sample 多 nl_description 计独立观测) — **永久禁止** (违反 Beta-Binomial i.i.d.)

## Context

- **依赖既有 repo**: 框架住在 `BreakoutStrategy/feature_library/` 下,与同 repo 的 `BreakoutStrategy/dev`、`BreakoutStrategy/live`、`BreakoutStrategy/mining` 通过 ADR-001 解耦。
- **下游消费者**: mining 流水线和 `add-new-factor` skill,均不需修改即可消费 framework 产出的 `observed_feature` 库。
- **预置文档来源**: 历史 research 文档 (`docs/research/feature_mining_v2_unified_decision.md`、`...philosophy_decision.md`、`...unified_schema.md` 等) 和 `docs/explain/ai_feature_mining_plain.md` 是设计前史,不在 ingest 集中,只作背景。
- **Phase 0 完成态**: 5 个盘整字段、多周期 chart 渲染器、nl_description 预处理 pipeline 已上线,35 测试 PASS,Phase 1 直接复用 `paths`、`sample_id`、`sample_meta`、`consolidation_fields` 接口。
- **Phase 1 偏离记录** (源自 SPEC §11):
  - Inducer 用 Python 模块调用 GLM-4V-Flash 而非 Claude Code subagent (框架入口是 Python 脚本,subagent 不可生成);
  - 单批 batch_size 从原 ADR 8–12 降到 5 (GLM-4V-Flash 服务端硬限);
  - epoch_tag / decay / γ 推迟到 Phase 1.5,但 schema 字段已就位 (null 默认)。
- **19 个开放问题 (Q1–Q19)**: 全部为实施期问题,不阻塞 roadmap (例如 Q9 Split replay 起步用 Option B 比例近似;Q19 N≥500 时 obs 切 SQLite)。
- **i.i.d. 防御**: Beta-Binomial 的代价是,任何"同 sample 重复观测"必须经 Replay / Re-induction / Re-verification / Shuffled Re-induction 四条 sanctioned 通路并戴 `epoch_tag + superseded_by`(ADR-009 / ADR-011 / ADR-018)。

## Constraints

- **Tech**: Python 3 + uv 包管理;LLM 后端 GLM-4V-Flash (Phase 1)、DeepSeek (L1)、Claude Opus (L2 Inducer/Critic);fastembed 384-d 文本嵌入 (L0);scipy.stats.beta 计算 P5;PyYAML 持久化。
- **Persistence**: 所有状态住在 `feature_library/` 文件系统;CLI 命令 stateless (read → execute → write → exit);Librarian 函数式无内部可变态。
- **Repo hygiene**: `feature_library/` (含 `samples/`、`features/`、`history/`) 在 `.gitignore` 中,Phase 1+ 永远不 commit。
- **Conventions**: 入口脚本禁用 argparse,参数声明在 `main()` 顶部;注释/print/log 中文,UI 文本英文,标识符英文;OHLCV 列名小写。
- **Math defaults**: ALPHA_PRIOR = BETA_PRIOR = 0.5 (Jeffreys);λ=0.995 (Phase 1.5+ 启用,Phase 1 锁 1.0);γ=3 默认 (Phase 1 锁 1.0,C=0);ρ=1.0;L0_MERGE_THRESHOLD=0.85,reshuffle 用 0.75。
- **Service limits**: GLM-4V-Flash 单次调用最多 5 张图 (服务端 error 1210);Phase 1.5+ 如需 ≥6 必须分块 + Librarian L0 dedup 聚合。
- **CLI lifecycle**: `pending_replays.yaml` 非空时 `feature-mine ingest` 必须拒绝运行(唯一 ERROR 级被动提醒,无 override 旗标),用户必须先跑 `feature-mine apply-replays`。
- **Inducer blind invariant**: Inducer prompt 永远不能含 library 内容、不能做 rule/hypothesis 分类;reshuffle 只能用 anti-correlated 或 random 批次,stratified-by-source-feature 永久禁止。
- **Critic mutation discipline**: Critic 永远不直接改 library / (α,β) / 文本 / embedding,也不改 Inducer prompt;mutations 必经 Critic proposal → 用户批准 → CLI 入队 `pending_replays.yaml` → Librarian apply-replays。
- **Double-counting defense**: 同 (sample_id, feature_id, source, epoch_tag) 拒写;同 (sample_id, feature_id) 不同 epoch_tag → 旧记 `superseded_by=<new>`,recompute 只算新的;Critic split 例外 (feature_ids 不同)。
- **Update formula 锁定**: 所有累积路径 (Path U / Path V / Replay) 走同一公式 `α += K; β += (N-K-C) + γ·C`,decay 在访问时懒计算。

## Key Decisions

<decisions status="LOCKED" total="21">

下述 21 条 ADR 决策来自 `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md` (manifest precedence 0,LOCKED)。任何修改必须经过显式的 ADR 修订流程,不得在普通 plan 中改动。

| ID | Decision | Rationale | Source | Status |
|----|----------|-----------|--------|--------|
| ADR-001 | Decouple feature-induction framework from mining pipeline | 框架只产 `observed_feature` 库,不判断 favors-uptrend;mining 流水线不变,既有 13 因子不动 | ADR §0.3 | LOCKED |
| ADR-002 | User-picked samples define the framework's domain (no base rate, no control corpus) | 用户挑样本本身就是监督信号,ρ 默认 1.0,p0 base rate 不用 | ADR §0.5 | LOCKED |
| ADR-003 | Three AI roles + CLI Scheduler (Inducer / Librarian / Critic + `feature-mine`) | Inducer/Critic 是 Opus 短 subagent,Librarian 是 Python,CLI 是 Python 无 LLM 调度;原 AI Orchestrator 备选 7 拒绝 | ADR §1.1, §6 #4 | LOCKED |
| ADR-004 | Role responsibility hard boundaries (cannot cross) | (α,β) 只 Librarian 改;split/merge/rewrite/disputed 只 Critic 提议;新模式只 Inducer 发现;调度只 CLI | ADR §1.2 | LOCKED |
| ADR-005 | Beta-Binomial conjugate posterior as the SOLE statistic | 单一 (α,β,ts,provenance,observed_samples) schema;消灭 rule/hypothesis、batch/incremental、obs/episodes/counter 多套 schema | ADR §3, §6 #10 | LOCKED |
| ADR-006 | Three-tier cost ladder (L0 fastembed / L1 DeepSeek / L2 Opus) | L0 cosine 0.85,reshuffle 0.75;L2.5 codified verifier 不在 v1 | ADR §1.1, §3.7, §6 #2 | LOCKED |
| ADR-007 | User-driven CLI rhythm; passive reminders only; NO automatic scheduling | 4 个用户触发模式 + 触发清单只发被动提醒;Critic 永不自动跑 | ADR §2.2, §2.3, §6 #3/#21/#22 | LOCKED |
| ADR-008 | Replay blocking rule (math consistency hard constraint) | `pending_replays.yaml` 非空时 `feature-mine ingest` 唯一 ERROR 级阻断,必须先 `apply-replays` | ADR §2.3, §4.7, §6 #18 | LOCKED |
| ADR-009 | Multi-epoch four mechanisms (Replay / Re-induction / Re-verification / Shuffled Re-induction) | 仅这 4 条 sanctioned 路径可重观测,均戴 `epoch_tag + supersede` | ADR §2.6, §6 #14 | LOCKED |
| ADR-010 | Merge Semantics three policies (`full` / `supersede-only` / `reject-merge`) | reshuffle 强制 supersede-only,full 禁;Critic split/merge replay 强制 full | ADR §2.5, §6 #16 | LOCKED |
| ADR-011 | ObservationLog at (sample, feature) granularity + epoch_tag + superseded_by | 一条记录对一对 (sample,feature),非 per-batch;同 (s,f) 跨 epoch → 旧记 superseded | ADR §2.6, §4.2, §6 #15 | LOCKED |
| ADR-012 | Feature-level `provenance` + Shuffled-born candidate lock | provenance 以 `shuffle-` 起头的 feature 强锁 candidate,直到出现 ≥1 条非 shuffle 来源观测 | ADR §2.6, §4.2, §6 #17 | LOCKED |
| ADR-013 | Inducer is BLIND (no library lookup, no rule/hypothesis classification) | Inducer 不读 library、不分类、不知道有现存 feature;去重和分类归 Librarian | ADR §4.3, §6 #5 | LOCKED |
| ADR-014 | Critic does NOT touch (α, β) and does NOT modify Inducer prompt | Critic 只发 proposals,经用户审 → CLI enqueue → apply-replays;L3 archetype hint 改 prompt 备选 8 拒 | ADR §4.5, §4.7, §6 #13 | LOCKED |
| ADR-015 | All state lives in `feature_library/` filesystem | CLI stateless;subagents 只回结构化摘要;Librarian 函数式;中断/重启零状态丢失 | ADR §1.3, §4.1 | LOCKED |
| ADR-016 | Time decay applied lazily (no cron job) | λ=0.995 (~138 天半衰期);access 时按 (now − last_update_ts).days 计算,等价于全局 daily job | ADR §3.2, §3.3 | LOCKED |
| ADR-017 | γ = 3 default counter weight (configurable) | 一个显式 L1 `no` ≈ 3 个沉默样本的反向权重;可经 §3.7 切 dict[source, float] | ADR §3.3 | LOCKED |
| ADR-018 | Anti–multi-view augmentation; multi-epoch ONLY via 4 sanctioned paths | 同 sample 多 nl_description 各自计观测违反 i.i.d.,**永久禁止** | ADR §2.6, 备选 10 | LOCKED |
| ADR-019 | Reshuffle uses anti-correlated batching only (NOT stratified-by-feature) | stratified-by-source-feature 会泄漏 feature 身份给 Inducer,**永久拒绝** | ADR §6 #20, 备选 9 | LOCKED |
| ADR-020 | Phase roadmap (Phase 0 done; Phase 1 → 1.5 → 2 → 3 → 4a / 4b / 4c) | Phase 0–3 形成 MVP 闭环;4a 可选 reshuffle;4b/4c 可选 archetype hint / Critic 高阶动作 | ADR §5.4 | LOCKED |
| ADR-021 | Out-of-scope items (explicitly shelved) | Coder/L2.5、archetype 抽象、cross-archetype 类比、p0、stratified-by-source-feature、多视角增强 等永久剔除/推迟 | ADR §5.6 | LOCKED |

</decisions>

---
*Last updated: 2026-04-29 — Phase 1 (Librarian + Inducer MVP) gap-fix complete. dev UI 三态 picker FSM + chart.png 视觉脱敏(BO close pivot / 字号统一 / Bar Count) + prompt 文本通道同步落地;UAT approved 含 7 处 follow-on UX fixes;203/203 tests PASS;deferred → /gsd-verify-work 1 (real GLM-4V smoke) + /gsd-secure-phase 1 (REQ-invariant 三道硬防线 review)。*
