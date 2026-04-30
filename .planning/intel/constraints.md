# Constraints

Synthesized from the SPEC `2026-04-27-phase1-librarian-inducer-mvp.md` and architectural constraints lifted from the ADR `2026-04-25-feature-induction-framework-design.md`. Each constraint includes type and source.

---

## CONSTRAINT-glm4v-batch-size-cap

- **source**: SPEC §0.3 #2, §11.2; ADR §1.1
- **type**: protocol (external service hard limit)
- **content**: GLM-4V-Flash server enforces a 5-image cap per call (error code 1210). Phase 1 default `batch_size=5`. Phase 1.5+ `≥6` requires chunked dispatch + Librarian L0 dedup aggregation. Switching to Anthropic Opus API later restores the spec's 8-12 batch_size.

## CONSTRAINT-ohlcv-lowercase-columns

- **source**: SPEC §0.3 #3
- **type**: schema (data contract)
- **content**: PKL files use lowercase OHLCV column names; all new feature_library modules must consume/produce lowercase. Phase 0 already standardized this.

## CONSTRAINT-no-argparse-in-entry-scripts

- **source**: SPEC §0.3 #4; CLAUDE.md
- **type**: nfr (project convention)
- **content**: Entry scripts under `scripts/` MUST declare parameters as variables at the top of `main()`; argparse is forbidden.

## CONSTRAINT-language-policy

- **source**: SPEC §0.3 #5; CLAUDE.md
- **type**: nfr (project convention)
- **content**: Comments in Chinese; print/log strings in Chinese; UI text in English; identifiers in English.

## CONSTRAINT-feature-id-naming

- **source**: SPEC §2.3, §11.4
- **type**: schema
- **content**: Feature filename `F-NNN-<text-slug>.yaml` where NNN is 3-digit zero-padded sequence and slug is lowercase ASCII alnum + hyphen, ≤30 chars. Non-ASCII characters dropped. Empty slug → `F-NNN.yaml`.

## CONSTRAINT-features-yaml-schema-frozen

- **source**: SPEC §6; ADR §4.2
- **type**: schema
- **content**: Top-level fields locked: `id, text, embedding, alpha, beta, last_update_ts, provenance, observed_samples, total_K, total_N, total_C_weighted, observations, research_status, factor_overlap_declared`. Derived fields (`signal`, `status_band`) MUST NOT be persisted. Phase 1.5+ fields (`epoch_tag`, `superseded_by`) present in obs schema with null default starting in Phase 1.

## CONSTRAINT-observation-log-granularity

- **source**: SPEC §5.2; ADR §4.2 重要变化
- **type**: schema
- **content**: One ObservationLog entry per (sample_id, feature_id), inline in features yaml. Per-batch aggregation (the legacy design) is FORBIDDEN — supersede/replay correctness depends on per-sample granularity.

## CONSTRAINT-beta-binomial-priors-and-defaults

- **source**: ADR §3.1, §3.3, §3.7; SPEC §4.2
- **type**: nfr (math defaults)
- **content**:
  - `ALPHA_PRIOR = BETA_PRIOR = 0.5` (Jeffreys)
  - `λ = 0.995` default (half-life ~138d); Phase 1 forces `λ = 1.0` (no decay) until Phase 1.5
  - `γ = 3` default counter weight; Phase 1 forces `γ = 1.0` (placeholder, C=0 always)
  - `ρ = 1.0` default (off; user-pick is the domain)
  - `L0_MERGE_THRESHOLD = 0.85`; reshuffle uses 0.75
  - Status bands (P5): `forgotten <0.05`, `candidate [0.05, 0.20)`, `supported [0.20, 0.40)`, `consolidated [0.40, 0.60)`, `strong [0.60, 1.0]`
  - Disputed overlay when `counter_ratio > 0.3`
  - All values configurable via §3.7 retreat switches

## CONSTRAINT-update-formula-frozen

- **source**: ADR §3.2
- **type**: api-contract (math)
- **content**: Single update path:
  ```
  days = (e.ts - feature.last_update_ts).days
  decay = LAMBDA ** max(0, days)
  α = max(ALPHA_PRIOR, α * decay)
  β = max(BETA_PRIOR,  β * decay)
  α += K
  β += (N - K - C) + GAMMA * C
  ```
  Time decay is lazy (no global cron). All accumulation paths (Path U, Path V, Replay) MUST use this same formula.

## CONSTRAINT-merge-policy-defaults-locked

- **source**: ADR §2.5
- **type**: api-contract
- **content**:
  - `feature-mine ingest` (cold-start / incremental) → default `full`
  - `feature-mine reinduce` → default `full`, user may switch `supersede-only`
  - `feature-mine reshuffle` → forced `supersede-only`; `full` PROHIBITED; only `reject-merge` allowed as alternative
  - Critic split / merge → apply-replays → forced `full`, no override

## CONSTRAINT-replay-blocking-rule

- **source**: ADR §2.3 T_pending_replays, §4.7
- **type**: protocol (CLI lifecycle)
- **content**: When `pending_replays.yaml` is non-empty, `feature-mine ingest` MUST refuse to run (sole ERROR-level passive reminder). User MUST run `feature-mine apply-replays` first. No override flag is provided in the spec for this gate.

## CONSTRAINT-inducer-blind-prompt

- **source**: ADR §4.3, §6 #5; SPEC §12.1
- **type**: api-contract (Inducer)
- **content**: Inducer prompt MUST NOT contain existing feature texts, IDs, or any library-derived state. Inducer MUST NOT classify rule/hypothesis. Reshuffle MUST use feature-agnostic batching strategies (anti-correlated or random); stratified-by-source-feature is permanently rejected.

## CONSTRAINT-critic-mutation-discipline

- **source**: ADR §4.5, §4.7
- **type**: api-contract (Critic)
- **content**: Critic MUST NOT directly mutate features library, (α, β), text, or embeddings. Critic MUST NOT modify Inducer prompts. All mutations route: Critic proposal → user approve → CLI enqueue `pending_replays.yaml` → Librarian executes via `apply_replays`. Demote action is FORBIDDEN.

## CONSTRAINT-double-counting-defense

- **source**: ADR §2.6
- **type**: api-contract
- **content**:
  - Same `(sample_id, feature_id, source, epoch_tag)` → Librarian rejects write
  - Same `(sample_id, feature_id)` with different `epoch_tag` → mark old `superseded_by=<new>`; only new counts in recompute
  - Critic split exception: same sample → both new feature_ids each get one entry (NOT double-counting because feature_ids differ)
  - Multi-view augmentation (same sample → multiple `nl_description`) is FORBIDDEN

## CONSTRAINT-state-in-filesystem

- **source**: ADR §1.3, §4.1
- **type**: api-contract
- **content**: All state must live under `feature_library/`. CLI commands are stateless (read → execute → write → exit). Subagents return only structured summaries (no long-lived session). Librarian must be functional (no class-internal mutable state). Interrupt/restart must lose nothing.

## CONSTRAINT-runtime-data-gitignored

- **source**: SPEC §2.3 note, §9 AC10, §12.5
- **type**: nfr (repo hygiene)
- **content**: `feature_library/` is in `.gitignore` (Phase 0 already added). Phase 1+ MUST keep it out of git.

## CONSTRAINT-cooccurrence-yaml-schema

- **source**: ADR §4.1
- **type**: schema (Phase 4a, deferred — recorded for forward compatibility)
- **content**: `cooccurrence.yaml` shape:
  ```
  last_updated, matrix (upper triangular keyed "S03|S05"), total_samples,
  total_pairs, covered_pairs, coverage_ratio
  ```
  Default termination threshold `coverage_ratio ≥ 0.7`.

## CONSTRAINT-pending-replays-yaml-schema

- **source**: ADR §4.1
- **type**: schema (Phase 1.5+, deferred)
- **content**: `pending_replays.yaml` items: `id, kind (replay-after-split | replay-after-merge | replay-for-new-feature), target_feature_ids, sample_ids, epoch_tag, merge_policy=full, created_ts`.

## CONSTRAINT-archetype-hint-discipline

- **source**: ADR §6 #19, 备选 8
- **type**: api-contract (Phase 4b, deferred)
- **content**: When implemented, archetype hints MUST be Python-maintained, MUST NOT expose specific feature texts, and Critic MUST NOT participate. Archetype hints MUST be force-disabled when `epoch_tag != null` or epoch tag startswith `shuffle-` (prevents dynamic-prompt compounding bias).

## CONSTRAINT-reshuffle-cost-guard

- **source**: ADR §7 Q17
- **type**: protocol (Phase 4a, deferred)
- **content**: When implemented, `feature-mine reshuffle` MUST display estimated Opus token spend; `--dry-run` is mandatory before non-dry-run; non-dry-run defaults to `--confirm` (interactive enter).
