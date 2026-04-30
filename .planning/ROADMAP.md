# Roadmap: AI Feature Induction Framework

## Overview

从已完成的 Phase 0 数据基线(5 盘整字段 + chart 渲染器 + nl_description 预处理)出发,Phase 1 落地 Librarian + Inducer 的 MVP 闭环——把"5 张图喂 GLM-4V → YAML candidates → cosine 合并 / Beta-Binomial 累积 → features yaml 持久化"端到端跑通。Phase 1.5 / 2 / 3 把 epoch_tag、CLI Scheduler、Critic 三道硬防线补齐,形成 ADR-020 定义的 MVP 闭环;Phase 4a / 4b / 4c 是 optional 高级回路(reshuffle、archetype hint、Critic 高阶动作)。本次 ingest 仅 SPEC 了 Phase 1,其它 phase 在 ROADMAP 中保留 placeholder + 一句 scope 摘要,等待各自 SPEC 文档摄入。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): 主路线,按 ADR-020 顺序
- Decimal phases (1.5): ADR-020 中明确编号的细化阶段
- Suffixed phases (4a / 4b / 4c): ADR-020 中 Phase 4 的并列子阶段(各自可选,可独立挑选)

- [x] **Phase 0: Data Baseline** — Phase 0 已完成,提供 sample 三件套与 GLM-4V backend 接口
- [ ] **Phase 1: Librarian + Inducer MVP** — Python 模块版 Inducer (GLM-4V batch=5) + 文件系统 Librarian + Beta-Binomial 重算 + AAPL×5 端到端 smoke
- [ ] **Phase 1.5: epoch_tag + Merge Semantics + Replay queue** — 把 Phase 1 中 null 占位字段激活,落地 Replay 阻断与三种 merge_policy
- [ ] **Phase 2: CLI Scheduler + dev UI** — `feature-mine` 命令族(ingest/reinduce/apply-replays/review-critic 等)+ 开发态 UI 接入
- [ ] **Phase 3: Critic core + three hard defenses** — Critic Opus 短 subagent + 三道硬防线(blind / mutation discipline / replay 阻断)联调
- [ ] **Phase 4a: Reshuffle Re-induction** — anti-correlated 批次,supersede-only 强制,cooccurrence.yaml,4 终止条件
- [ ] **Phase 4b: L2 archetype hint + advanced reinduce** — Python-maintained archetype hint,Critic 不参与,epoch≠null 时强制关
- [ ] **Phase 4c: Critic advanced actions split/merge/abstract** — Critic 高阶动作 + apply-replays 通路完整化

## Phase Details

### Phase 0: Data Baseline
**Goal**: 提供"用户挑样本 → 标准化 sample 目录(chart.png / meta.yaml / nl_description.md)"的数据底座
**Depends on**: Nothing
**Requirements**: PHASE0-DATA-BASELINE
**Success Criteria** (what must be TRUE):
  1. 5 个盘整字段 (length / height / volume_ratio / tightness / breakout_day OHLCV) 可被下游模块按 sample_id 检索
  2. 多周期 chart 渲染器能产出 chart.png
  3. nl_description 预处理 pipeline 能产出每个 sample 的 nl_description.md
  4. 35 个 Phase 0 测试 PASS,端到端 vertical slice 跑通
**Plans**: 完成(无后续 plan 需写)
**Status**: done

### Phase 1: Librarian + Inducer MVP
**Goal**: 用户跑一行命令即可让 GLM-4V 跨样本归纳出 candidate features,经 cosine 合并、Beta-Binomial 重算后持久化到 `feature_library/features/F-*.yaml`,并且三道硬防线的 Phase 1 子集(blind inducer / CLI 不暴露 feature 文本 / state 全在 filesystem)在 code review 中可验证
**Depends on**: Phase 0
**Requirements**: REQ-phase1-package-skeleton, REQ-inducer-batch-induce, REQ-inducer-prompt-protocol, REQ-glm4v-batch-describe, REQ-embedding-l0, REQ-feature-store, REQ-observation-log-granularity, REQ-librarian-upsert-candidate, REQ-librarian-recompute, REQ-librarian-lookup-by-cosine, REQ-features-yaml-schema, REQ-entry-script-feature-mining-phase1, REQ-test-coverage, REQ-end-to-end-smoke, REQ-runtime-data-gitignored, REQ-invariant-blind-inducer, REQ-invariant-cli-no-feature-content
**Success Criteria** (what must be TRUE):
  1. 用户执行 `uv run python scripts/feature_mining_phase1.py`(参数在 `main()` 顶部声明,无 argparse),AAPL × 5 样本端到端跑完,exit 0,打印 §7.3 格式 library summary
  2. 运行后 `feature_library/features/F-*.yaml` ≥ 1 条,每个 yaml 含 14 个顶层字段且通过 dataclass 反序列化,obs 数 = candidates × batch_size,所有派生字段 (`signal`, `status_band`) 不持久化
  3. 两条文本相近的 candidate 通过 L0 cosine ≥ 0.85 合并到同一 feature_id;Beta-Binomial 重算用 Jeffreys prior 0.5、Phase 1 锁 γ=1.0、λ=1.0、C=0,signal=Beta_P5(α,β),status_band 在 P5={0.05,0.20,0.40,0.60} 边界正确分类
  4. `uv run pytest BreakoutStrategy/feature_library/tests/ -v` 通过 30–40 个新测试,合 Phase 0 共 65–75 PASS
  5. Code review 确认 Inducer prompt 不含任何 feature_library 读取,entry script 仅暴露 sample_ids;`git status` 显示 `feature_library/*` 全部 untracked / ignored
**Plans**: 5 plans (gap-fix scope; Phase 1 主体已 commit at 3c6b933)
  - [x] 01-01-PLAN.md — Picker 三态机重构(D-01..D-04)
  - [x] 01-02-PLAN.md — canvas_manager 集成新 picker(D-10..D-11)
  - [x] 01-03-PLAN.md — chart 渲染窗口 + 视觉脱敏 + BO close pivot + 字号(D-05..D-07, D-09)
  - [x] 01-04-PLAN.md — prompts 文本通道切到 BO close pivot(D-08)
  - [x] 01-05-PLAN.md — 端到端集成验证 + dev UI 烟测

### Phase 1.5: epoch_tag + Merge Semantics + Replay queue (placeholder)
**Goal**: 激活 Phase 1 中 null 占位的 `epoch_tag` / `superseded_by`,落地 ADR-010 三种 merge_policy 与 ADR-008 Replay 阻断,跑通 `pending_replays.yaml` lifecycle
**Depends on**: Phase 1
**Requirements**: TBD(等待 Phase 1.5 SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**Scope summary** (来自 ADR-020): "Phase 1.5 — epoch_tag + Merge Semantics + Replay queue (3-4d)"

### Phase 2: CLI Scheduler + dev UI (placeholder)
**Goal**: 实现 `feature-mine` 命令族(`ingest` / `reinduce` / `apply-replays` / `review-critic` / 状态查询等),按 ADR-007 用户驱动节奏 + 被动提醒,接入 BreakoutStrategy/dev UI 的特征查看面板
**Depends on**: Phase 1.5
**Requirements**: TBD(等待 Phase 2 SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**UI hint**: yes
**Scope summary** (来自 ADR-020): "Phase 2 — CLI Scheduler + dev UI (1w)"

### Phase 3: Critic core + three hard defenses (placeholder)
**Goal**: 上线 Critic Claude Opus 短 subagent(只发 proposals,不动 (α,β) / 不改 prompt),并把三道硬防线(blind inducer / Critic mutation discipline / Replay 阻断)以集成测试形式锁死
**Depends on**: Phase 2
**Requirements**: TBD(等待 Phase 3 SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**Scope summary** (来自 ADR-020): "Phase 3 — Critic core + three hard defenses (1w),与 Phase 0–2 共同形成 MVP 闭环"

### Phase 4a: Reshuffle Re-induction (placeholder, optional)
**Goal**: 实现 Shuffled Re-induction(anti-correlated batching,forced supersede-only,provenance lock,cooccurrence.yaml ≥0.7 等 4 终止条件),支持 `--dry-run` cost guard
**Depends on**: Phase 3
**Requirements**: TBD(等待 Phase 4a SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**Scope summary** (来自 ADR-020): "Phase 4a — Reshuffle Re-induction (~5d)"

### Phase 4b: L2 archetype hint + advanced reinduce (placeholder, optional)
**Goal**: 加入 Python 维护的 archetype hint(Critic 不参与,epoch_tag != null 或 `shuffle-*` 时强制关)与高级 reinduce 模式
**Depends on**: Phase 4a
**Requirements**: TBD(等待 Phase 4b SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**Scope summary** (来自 ADR-020): "Phase 4b — L2 archetype hint + advanced reinduce (~3d, optional)"

### Phase 4c: Critic advanced actions split/merge/abstract (placeholder, optional)
**Goal**: Critic 高阶动作 split / merge / abstract 全链路接入,经 user-approve → CLI enqueue → apply-replays(forced full,无 override)
**Depends on**: Phase 4b
**Requirements**: TBD(等待 Phase 4c SPEC 摄入)
**Success Criteria**: TBD
**Plans**: TBD
**Scope summary** (来自 ADR-020): "Phase 4c — Critic advanced actions split/merge/abstract (~5d, optional)"

## Progress

**Execution Order:**
Phase 0 → 1 → 1.5 → 2 → 3 → 4a → 4b → 4c

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Data Baseline | n/a | Done | Phase 0 (pre-Phase-1) |
| 1. Librarian + Inducer MVP | 0/5 | In progress (gap-fix planned) | - |
| 1.5. epoch_tag + Merge Semantics + Replay queue | 0/TBD | Not started | - |
| 2. CLI Scheduler + dev UI | 0/TBD | Not started | - |
| 3. Critic core + three hard defenses | 0/TBD | Not started | - |
| 4a. Reshuffle Re-induction | 0/TBD | Not started | - |
| 4b. L2 archetype hint + advanced reinduce | 0/TBD | Not started | - |
| 4c. Critic advanced actions | 0/TBD | Not started | - |
