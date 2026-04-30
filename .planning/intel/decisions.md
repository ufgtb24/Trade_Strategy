# Decisions (Architectural)

Synthesized from manifest-tagged ADRs in the ingest set. All entries below are **LOCKED** unless otherwise noted.

---

## ADR-001 — Decouple feature-induction framework from mining pipeline

- **source**: `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md` §0.3
- **status**: Accepted, LOCKED (manifest precedence 0)
- **scope**: Framework boundary vs `mining/` pipeline
- **decision**: The AI feature-induction framework only produces `observed_feature` library entries (which patterns universally exist). It does NOT judge whether patterns favor uptrends. mining/ pipeline is unchanged; framework is its upstream candidate generator. Existing 13 factors are not modified.

## ADR-002 — User-picked samples define the framework's domain (no base rate, no control corpus)

- **source**: §0.5
- **status**: Accepted, LOCKED
- **scope**: Statistical philosophy; sampling assumptions
- **decision**: The target domain IS the user-picked sample set. Non-randomness of user picking is NOT a defect, it is the domain. ρ (sampling correction) defaults to 1.0 (off). p0 base rate not used. No control corpus / negative-sample pool.

## ADR-003 — Three AI roles + CLI Scheduler (research-team metaphor)

- **source**: §1.1, §6 decision #4
- **status**: Accepted, LOCKED
- **scope**: Top-level architecture; role decomposition
- **decision**: Four components only:
  - **Inducer** = Claude Opus short subagent — multi-image cross-sample comparison (sole source of new candidate features)
  - **Librarian** = pure Python module (NOT AI) — mechanical (α, β) accumulation, L0/L1 lookups, merge-policy execution
  - **Critic** = Claude Opus short subagent — disputed adjudication, split/merge/rewrite/abstract proposals
  - **CLI Scheduler** = pure Python `feature-mine` tool (NO LLM) — command parsing, mode resolution, queue management, passive reminders
  Original "AI Orchestrator (long-session Opus)" is rejected (备选 7).

## ADR-004 — Role responsibility hard boundaries (cannot cross)

- **source**: §1.2
- **status**: Accepted, LOCKED
- **scope**: Mutation authority by role
- **decision**:
  - Modify (α, β) — **only Librarian** (mechanical replay/recompute)
  - Modify text/embedding — **only Librarian** (executing Critic-approved proposals)
  - Threshold band (candidate/supported/consolidated/strong) — **derived**, no executor
  - Propose split/merge/rewrite/disputed adjudication — **only Critic**
  - Discover new patterns / multi-image comparison — **only Inducer**
  - Full-library health check — **only Critic**
  - Schedule batch/Replay/Reshuffle/Critic invocation — **only CLI Scheduler**
  Core principle: (α, β) is a cached accumulator; ObservationLog is the source of truth. NEVER manually adjust (α, β); always go through ObservationLog → recompute.

## ADR-005 — Beta-Binomial conjugate posterior as the SOLE statistic

- **source**: §3, §6 decision #10
- **status**: Accepted, LOCKED
- **scope**: Statistical model
- **decision**: Each feature carries only `(α, β, ts, provenance, observed_samples)`. Update formula `α += K, β += (N-K-C) + γ·C`. Signal `S = Beta_P5(α, β)` derives 5-band semantics. Eliminates `rule/hypothesis` split, `batch/incremental` split, and `obs/episodes/counter` multi-field schemes. Jeffreys prior `α₀ = β₀ = 0.5`.

## ADR-006 — Three-tier cost ladder (L0 / L1 / L2)

- **source**: §1.1, §6 decision #2, §3.7
- **status**: Accepted, LOCKED
- **scope**: AI backend selection
- **decision**: L0 = fastembed cosine (cheap pre-filter); L1 = DeepSeek yes/no/ambiguous verifier; L2 = Claude Opus (Inducer + Critic). L2.5 (codified verifier) is out of scope. L0 default cosine threshold 0.85; reshuffle uses stricter 0.75.

## ADR-007 — User-driven CLI rhythm; passive reminders only; NO automatic scheduling

- **source**: §2.2, §2.3, §6 decisions #3, #21, #22
- **status**: Accepted, LOCKED
- **scope**: Trigger / scheduling behavior
- **decision**: Four explicit user-triggered modes (Batch / Incremental / Re-induction / Shuffled Re-induction). Trigger checklist (T_init / T_orphan / T_period / T_critic_*) emits passive reminders at command end; nothing auto-executes. Critic NEVER runs automatically — only via `feature-mine review-critic`. Spec's "weekly/monthly cadence" descriptions are removed.

## ADR-008 — Replay blocking rule (math consistency hard constraint)

- **source**: §2.3 T_pending_replays, §4.7, §6 decision #18
- **status**: Accepted, LOCKED
- **scope**: Critic-mutation lifecycle
- **decision**: After Critic-approved mutations, `pending_replays.yaml` becomes non-empty. New ingest is BLOCKED (sole ERROR-level reminder; all others are WARN) until user runs `feature-mine apply-replays`. This is required because Critic split/merge changes feature identity; old observations must be replayed to keep (α, β) consistent.

## ADR-009 — Multi-epoch four mechanisms

- **source**: §2.6, §6 decision #14
- **status**: Accepted, LOCKED
- **scope**: Re-evaluation lifecycle
- **decision**:
  - **Replay** — mandatory after Critic split/merge/rewrite (merge-policy: `full`)
  - **Re-induction** — user-triggered exploration over a sample subset (default `full`, user may switch `supersede-only`)
  - **Re-verification** — implicit in incremental Path V (no merge step)
  - **Shuffled Re-induction** — user-triggered, anti-correlated default, 4 termination conditions, **forced** `supersede-only` + provenance lock

## ADR-010 — Merge Semantics: three policies (`full` / `supersede-only` / `reject-merge`)

- **source**: §2.5, §6 decision #16
- **status**: Accepted, LOCKED
- **scope**: Path U candidate-merge behavior
- **decision**:
  - `full` — default for ingest (cold-start/incremental) and reinduce; default for Critic split/merge replays (mandatory)
  - `supersede-only` — **forced** for reshuffle (prevents counter-evidence compounding from i.i.d. violation); optional for reinduce
  - `reject-merge` — rare; user-explicit for "only produce truly new features"
  Reshuffle FORBIDS `full` (would create artificial counter-evidence compounding).

## ADR-011 — ObservationLog at (sample, feature) granularity + epoch_tag + superseded_by

- **source**: §2.6, §4.2, §6 decision #15
- **status**: Accepted, LOCKED
- **scope**: Audit log schema; double-counting defense
- **decision**: One ObservationLog entry per (sample_id, feature_id) pair, NOT per batch (original design's per-batch aggregation cannot supersede correctly). Each entry carries `epoch_tag` (null for first eval; `replay-after-*`, `reinduction-*`, `shuffle-*-*` otherwise) and `superseded_by` (chains old→new). Same (sample, feature, source, epoch_tag) is rejected. Same (sample, feature) with different epoch_tag → old entry marked superseded; only the new entry counts in recompute.

## ADR-012 — Feature-level `provenance` + Shuffled-born candidate lock

- **source**: §2.6, §4.2, §6 decision #17
- **status**: Accepted, LOCKED
- **scope**: Anti–false-promotion defense for shuffle epoch
- **decision**: Each feature stores `provenance` = source/epoch_tag at birth. If `provenance` startswith `shuffle-`, the status_band is force-locked to `candidate` regardless of P5, until ≥ 1 ObservationLog entry with `source != shuffle-*` exists (configurable `provenance_lock_unlock_min_events`).

## ADR-013 — Inducer is BLIND (no library lookup, no rule/hypothesis classification)

- **source**: §4.3, §6 decision #5
- **status**: Accepted, LOCKED
- **scope**: Inducer prompt / context discipline
- **decision**: Inducer MUST NOT read the features library, MUST NOT classify rule vs hypothesis, MUST NOT know existing features exist. Deduplication and classification belong to Librarian. This protects Beta-Binomial i.i.d. assumption and prevents reward hacking.

## ADR-014 — Critic does NOT touch (α, β) and does NOT modify Inducer prompt

- **source**: §4.5, §4.7, §6 decision #13, 备选 8
- **status**: Accepted, LOCKED
- **scope**: Critic constraint surface
- **decision**: Critic only emits proposals (`split / merge / rewrite / demote / abstract`). Mutations route through user approval → CLI enqueue → `apply-replays` → Librarian. Critic-modified Inducer prompt (L3 archetype hint) is REJECTED — would leak library content to Inducer and break i.i.d.

## ADR-015 — All state lives in `feature_library/` filesystem

- **source**: §1.3, §4.1
- **status**: Accepted, LOCKED
- **scope**: Persistence model
- **decision**: CLI Scheduler is stateless per command (read files → execute → write files → exit). Inducer/Critic subagents return only structured summaries. Librarian is functional (no class-internal mutable state). Interrupt/restart loses no state.

## ADR-016 — Time decay applied lazily (no cron job)

- **source**: §3.2, §3.3
- **status**: Accepted, LOCKED
- **scope**: Decay implementation
- **decision**: λ = 0.995 (half-life ~138 days). Decay applied at access time using `(now - last_update_ts).days`, not via global daily job. Mathematically equivalent.

## ADR-017 — γ = 3 default counter weight

- **source**: §3.3
- **status**: Accepted, LOCKED (with config-driven override per §3.7)
- **scope**: Counter-evidence weighting
- **decision**: One explicit L1 `no` ≈ 3 silent samples in counter weight. Convertible to `dict[source, float]` via `gamma` switch.

## ADR-018 — Anti-multi-view augmentation; multi-epoch ONLY via the sanctioned 4 paths

- **source**: §2.6 禁止事项, §6 implicit, 备选 10
- **status**: Accepted, LOCKED
- **scope**: i.i.d. preservation
- **decision**: Generating multiple `nl_description` for the same sample and counting each as an independent observation is FORBIDDEN (breaks Beta-Binomial i.i.d.). Only Replay / Re-induction / Re-verification / Shuffled Re-induction count as legitimate re-observation, all protected by epoch_tag + supersede.

## ADR-019 — Reshuffle uses anti-correlated batching only (NOT stratified-by-feature)

- **source**: §6 decision #20, 备选 9
- **status**: Accepted, LOCKED
- **scope**: Reshuffle batch-selection strategy
- **decision**: anti-correlated (default) or random — both feature-agnostic. Stratified-by-source-feature is REJECTED (would leak feature membership to Inducer, violating §4.3 blind constraint).

## ADR-020 — Phase roadmap (0 → 4c with optional Phase 4+ extensions)

- **source**: §5.4
- **status**: Accepted, LOCKED (Phase 0–3 form MVP closed loop)
- **scope**: Delivery sequencing
- **decision**:
  - Phase 0 — data baseline (3-4d) — DONE per Phase 1 spec preface
  - Phase 1 — Librarian + Inducer MVP (1w)
  - Phase 1.5 — epoch_tag + Merge Semantics + Replay queue (3-4d)
  - Phase 2 — CLI Scheduler + dev UI (1w)
  - Phase 3 — Critic core + three hard defenses (1w)
  - Phase 4a — Reshuffle Re-induction (~5d)
  - Phase 4b — L2 archetype hint + advanced reinduce (~3d, optional)
  - Phase 4c — Critic advanced actions split/merge/abstract (~5d, optional)
  Total Phase 0–3 ≈ 4 weeks.

## ADR-021 — Out-of-scope items (explicitly shelved)

- **source**: §5.6
- **status**: Accepted, LOCKED
- **scope**: Scope discipline
- **decision**: Coder subagent / L2.5 codified verifier; Critic split/merge/abstract advanced actions (until Phase 4c); archetypes/ abstraction layer; cross-archetype analogy; quantitative 13-factor overlap; algorithmic paths (Apriori / FP-Growth); p0 / control corpus; L2 archetype hint (until Phase 4b); NL Adapter `feature-mine ask`; reshuffle stratified-by-source-feature (PERMANENTLY rejected).
