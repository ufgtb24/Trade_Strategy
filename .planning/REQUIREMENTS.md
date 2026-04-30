# Requirements: AI Feature Induction Framework

**Defined:** 2026-04-29
**Core Value:** 让 AI 把用户在 K 线图上的"直觉好坏"翻译成可累积、可超越、可遗忘的特征条目,最终通过 `add-new-factor` skill 转写成因子代码,完成股票筛选。

## Milestones

- **Milestone 1 — Feature Induction Framework MVP** (Phase 0 done; Phase 1 是本次 SPEC,后续 Phase 1.5 / 2 / 3 形成闭环)
- **Milestone 2 — Optional advanced loops** (Phase 4a / 4b / 4c,均 optional)

只有 Milestone 1 的 Phase 1 在本次摄入中带 SPEC,因此当前 v1 requirements 只覆盖 Phase 1。Phase 1.5 / 2 / 3 / 4 的 requirements 在各自 SPEC 摄入后再补;ROADMAP 中保留 placeholder。

## v1 Requirements (Milestone 1, Phase 1 — Librarian + Inducer MVP)

来源:`docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md` (SPEC,precedence 1)。
所有 acceptance 条目来自 SPEC §9。

### Package Skeleton

- [ ] **REQ-phase1-package-skeleton**: 在 `BreakoutStrategy/feature_library/` 下新建 7 个 Python 模块 (`inducer.py`, `inducer_prompts.py`, `embedding_l0.py`, `feature_store.py`, `observation_log.py`, `librarian.py`, `feature_models.py`) + 测试文件;`glm4v_backend.py` 保留 `describe_chart` 并新增 `batch_describe`;`ls BreakoutStrategy/feature_library/` 显示该 package。

### Inducer (Python module, NOT subagent — SPEC §11.1 偏离记录)

- [ ] **REQ-inducer-batch-induce**: `batch_induce(sample_ids, backend, *, max_batch_size=5) -> list[Candidate]`,产出 Candidate(text, supporting_sample_ids, K, N, raw_response_excerpt);batch_describe 返回的 YAML 可解析为非空 candidates;无效 YAML 返回空列表不崩;sample_ids 数 > max_batch_size → ValueError;sample 三件套缺 → FileNotFoundError;过滤 supporting_ids ∉ batch;丢 K<2。
- [ ] **REQ-inducer-prompt-protocol**: `INDUCER_SYSTEM_PROMPT` 包含 K≥2 / 严格 YAML / 无 markdown 等约束关键字;`build_batch_user_message(samples_meta) -> str` 注入每个 sample 的 ticker、bo_date、consolidation length/height/volume_ratio/tightness、breakout_day OHLCV。

### GLM-4V Backend Extension (Phase 0 代码唯一改动)

- [ ] **REQ-glm4v-batch-describe**: 新增 `batch_describe(chart_paths, user_message) -> str`,单次 zhipuai 调用包多 image_url + 1 text,硬上限 5 (服务端 error 1210),>5 抛 ValueError;mock zhipuai 验证 multi-image_url 构造正确;原 `describe_chart` 接口保持不变。

### L0 Embedding

- [ ] **REQ-embedding-l0**: `embed_text(text) -> np.ndarray (384-d)` + `cosine_similarity(a, b) -> float`,实现复用 `news_sentiment.embedding`;返回 384-d;self-similarity = 1.0;同字串 cosine = 1.0。

### Feature Store

- [ ] **REQ-feature-store**: `load(id) / save(feature) / list_all() / next_id() / exists(id)`;文件名 `F-NNN-<text-slug>.yaml` (slug 小写 ASCII alnum + 连字符,≤30 chars,非 ASCII 丢弃,空 slug 退化 `F-NNN.yaml`);save→load round-trip 字段全留;next_id 单调递增;list_all 返回全部 features。

### Observation Log

- [ ] **REQ-observation-log-granularity**: ObservationLog 内联在 `features/<id>.yaml` `observations:` 数组(不是单独文件);粒度为 (sample_id, feature_id),非 per-batch;每条 obs 含 `id, ts, source, epoch_tag, sample_id, K, N, C, alpha_after, beta_after, signal_after, superseded_by, notes`;`append_entry` + `get_active_entries` (filter superseded_by is None);Phase 1 写 `epoch_tag = null`、`superseded_by = null`(schema future-proof)。

### Librarian Core API

- [ ] **REQ-librarian-upsert-candidate**: `upsert_candidate(candidate, *, batch_sample_ids, source="ai_induction") -> Feature`。流程:embed → `lookup_by_cosine(threshold=0.85)` → 命中合并 (tie-break 取最小 id) / 未命中新建;对 supporting_sample_ids 写 Event(K=1,N=1,C=0),对 (batch − supporting) 写 Event(K=0,N=1,C=0);最后 recompute。Phase 1 仅实现 `merge_policy=full` 语义;近似文本合并到同一 feature;不同文本分别建 feature;obs 正确切分 supporting vs silent。
- [ ] **REQ-librarian-recompute**: `recompute(feature_id) -> Feature`。重载 obs (跳过 superseded),Phase 1 简化更新 `α = 0.5 + ΣK; β = 0.5 + Σ(N-K-C) + γ·ΣC`,γ=1.0、λ=1.0、C=0;`signal = scipy.stats.beta.ppf(0.05, α, β)`;`status_band` 按 5-band 表派生;P5 = 0.05 / 0.20 / 0.40 / 0.60 边界正确分类。
- [ ] **REQ-librarian-lookup-by-cosine**: `lookup_by_cosine(embedding, threshold=0.85) -> list[Feature]`,返回 ≥ threshold 的命中按 cosine 降序,< threshold 返回空。

### Schema

- [ ] **REQ-features-yaml-schema**: 14 个顶层字段 (`id, text, embedding, alpha, beta, last_update_ts, provenance, observed_samples, total_K, total_N, total_C_weighted, observations, research_status, factor_overlap_declared`);obs 13 个字段含 null 默认 (epoch_tag, superseded_by);派生字段 `signal/status_band` **不持久化**;`yaml.safe_load` + dataclass 反序列化无错。

### Entry Script

- [ ] **REQ-entry-script-feature-mining-phase1**: `scripts/feature_mining_phase1.py`,参数声明在 `main()` 顶部,**禁用 argparse**;默认 `ticker="AAPL"`、`sample_count=5`、`skip_preprocess=False`、`inducer_max_batch=5`、`breakout_detector_params={}`;管线 `ensure_samples (复用 Phase 0) → batch_induce → upsert_candidate → print_library_summary`;端到端无异常,exit 0,打印 §7.3 格式摘要块。

### Tests & Smoke

- [ ] **REQ-test-coverage**: 30–40 个新测试,合 Phase 0 共 65–75 PASS;`uv run pytest BreakoutStrategy/feature_library/tests/ -v` PASS;覆盖矩阵满足 SPEC §8.1。
- [ ] **REQ-end-to-end-smoke**: `ticker=AAPL, sample_count=5` 跑出 ≥1 candidate;`feature_library/features/F-*.yaml ≥ 1`;每个 yaml 通过 schema 校验;obs 总数 = candidates × batch_size。

### Repo Hygiene

- [ ] **REQ-runtime-data-gitignored**: `feature_library/`(含 `samples/`、`features/`、`history/`)在 `.gitignore` 中;运行后 `git status` 不显示任何 feature_library/* tracked 文件。

### Hard Invariants (必须 code-review 验证)

- [ ] **REQ-invariant-blind-inducer**: Phase 1 entry script 不可向 Inducer prompt 注入任何 library feature 文本;Inducer blind to library state;`build_batch_user_message` + entry script 的 review 必须确认 Inducer 路径上无 feature_library 读取。
- [ ] **REQ-invariant-cli-no-feature-content**: Phase 1 entry script 仅向 Inducer 暴露 `sample_ids`,绝不暴露 feature 文本;code review 确认。

## v2+ Requirements

待 SPEC 摄入。占位:

- **Phase 1.5** — `epoch_tag + Merge Semantics + Replay queue` (3-4d, ADR §5.4)
- **Phase 2** — CLI Scheduler (`feature-mine` 命令族) + dev UI (1w)
- **Phase 3** — Critic 核心 + 三道硬防线 (1w)
- **Phase 4a** — Shuffled Re-induction + cooccurrence.yaml (~5d)
- **Phase 4b** — L2 archetype hint + 高阶 reinduce (~3d, optional)
- **Phase 4c** — Critic 高阶动作 split/merge/abstract (~5d, optional)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Coder subagent / L2.5 codified verifier | ADR-021,Phase 1–3 不引入 |
| Archetypes / 抽象层 / 跨 archetype 类比 | ADR-021,不在 v1 |
| 量化 13-factor overlap 评分 | ADR-021,Phase 4+ 才看 `factor_overlap_declared` |
| 算法路径 (Apriori / FP-Growth) | ADR-021,与 AI 归纳路线互斥 |
| p0 base rate / 控制语料 | ADR-002 + ADR-021,与"用户挑样本即领域"哲学矛盾 |
| L2 archetype hint | ADR-021,推迟到 Phase 4b |
| NL Adapter `feature-mine ask` | ADR-021,不在路线图 |
| Reshuffle stratified-by-source-feature | ADR-019,**永久拒绝**(违反 §4.3 blind) |
| 多视角增强 (同 sample 多 nl_description) | ADR-018,**永久禁止**(违反 i.i.d.) |
| Critic 自动调度 / Critic 改 (α,β) / Critic 改 Inducer prompt | ADR-007 + ADR-014,Critic 只发 proposals |

## Traceability

Phase 1 SPEC 的 17 条 requirements 全部映射到 Phase 1。Phase 0 的 baseline 已完成,不在本次 v1 列表(出现在 PROJECT.md Validated 段)。

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-phase1-package-skeleton | Phase 1 | Pending |
| REQ-inducer-batch-induce | Phase 1 | Pending |
| REQ-inducer-prompt-protocol | Phase 1 | Pending |
| REQ-glm4v-batch-describe | Phase 1 | Pending |
| REQ-embedding-l0 | Phase 1 | Pending |
| REQ-feature-store | Phase 1 | Pending |
| REQ-observation-log-granularity | Phase 1 | Pending |
| REQ-librarian-upsert-candidate | Phase 1 | Pending |
| REQ-librarian-recompute | Phase 1 | Pending |
| REQ-librarian-lookup-by-cosine | Phase 1 | Pending |
| REQ-features-yaml-schema | Phase 1 | Pending |
| REQ-entry-script-feature-mining-phase1 | Phase 1 | Pending |
| REQ-test-coverage | Phase 1 | Pending |
| REQ-end-to-end-smoke | Phase 1 | Pending |
| REQ-runtime-data-gitignored | Phase 1 | Pending |
| REQ-invariant-blind-inducer | Phase 1 | Pending |
| REQ-invariant-cli-no-feature-content | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-29*
*Last updated: 2026-04-29 after new-project-from-ingest bootstrap*
