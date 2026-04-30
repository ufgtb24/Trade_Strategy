# Context

Free-form context notes. The ingest set contains 1 ADR + 1 SPEC; no DOC-typed material was tagged. Notes here capture relevant background extracted from the ADR/SPEC that informs (but does not formally constrain) downstream planning.

---

## Topic: Project domain (why this framework exists)

- **source**: ADR §0.1
- **note**: Existing live system matches breakouts that look "high-blowoff" rather than user's preferred "base-then-mild-breakout". Root cause: users can intuitively distinguish good vs bad K-line patterns but cannot articulate them, much less translate them into factor code. The framework's role is to delegate "pattern summarization" to AI (specifically Claude Code, NOT deep learning).

## Topic: Five design philosophies underlying the architecture

- **source**: ADR §0.4
- **note**:
  1. Patterns are NOT iron laws — must support upgrade/downgrade/forget/disputed
  2. User picking samples IS the supervision signal — no extra positive/negative samples needed
  3. Cross-sample comparison is essential for pattern emergence — Opus multimodal handles it; statistics cannot replace it
  4. Accumulation/evaluation/decay must be mechanical (Beta-Binomial) to prevent AI free-form drift
  5. Multi-agent context isolation — each role short session, state lives in filesystem

## Topic: Phase 0 status

- **source**: SPEC preface
- **note**: Phase 0 (data baseline — 5 consolidation fields, chart renderer, nl_description preprocess) is COMPLETE. 35 tests PASS, end-to-end vertical slice runs. Phase 1 builds directly on it (reuses `paths`, `sample_id`, `sample_meta`, `consolidation_fields`).

## Topic: Status band intuition (P5 examples)

- **source**: ADR §3.5
- **note**:
  - 1/1 (single appearance, single success) → P5 ≈ 0.32
  - 10/10 → P5 ≈ 0.74
  - 100/100 → P5 ≈ 0.97
  - 2/10 → P5 ≈ 0.08
  Resolves the original "2/10 stronger than 1/1" inversion: P5(1/1) > P5(2/10).

## Topic: Why Orchestrator was downgraded to Python CLI

- **source**: ADR §1.1, 备选 7
- **note**: Original Orchestrator's scheduling decisions (mode selection / trigger monitoring / queue management / status reporting) are all deterministic rules. AI value is zero or negative — adds uncertainty, token cost, debug difficulty. User scenario is ingest-driven; all timing comes from user commands. AI orchestration has no leverage. Python CLI gives zero LLM calls, instant decisions, replayability.

## Topic: Three feature-induction paths comparison

- **source**: ADR §5.3
- **note**: Earlier designs (`feature_mining_via_ai_design.md`, philosophy_decision, v2_unified_decision, unified_schema, orchestration_revisit, shuffled_reinduction) are sources/predecessors. Mining pipeline and `add-new-factor` skill are unchanged downstream consumers. Existing 13 factors untouched until Phase 4+ optional `factor_overlap_declared` field.

## Topic: Failure-mode rationale for FORBIDDEN multi-view augmentation

- **source**: ADR 备选 10
- **note**: Generating multiple `nl_description` for the same physical sample and counting each as independent observation is forbidden. It violates Beta-Binomial i.i.d. — same physical sample disguised as multiple observations equals fabricating evidence. The only legitimate "re-observation" paths are Replay, Re-induction, Re-verification, Shuffled Re-induction, all of which use `epoch_tag + supersede` to preserve i.i.d.

## Topic: Phase 1 entry script differs from spec's "subagent" framing

- **source**: SPEC §11.1
- **note**: Main ADR §1.1 describes Inducer as a "Claude Opus short subagent". Phase 1 implements it as a Python module calling GLM-4V-Flash API, because: framework entry is a Python script (not a Claude Code session), so subagents are unspawnable. Critic in Phase 3 may reach for `subprocess.run(["claude", "-p", ...])` for true subagent semantics. This is an implementation-time deviation with explicit rationale; the architectural intent (isolated, short-lived, multimodal) is preserved.

## Topic: Open implementation-time questions (Q1–Q19)

- **source**: ADR §7
- **note**: 19 unresolved questions, all explicitly deferred to implementation:
  - Q1 θ_consolidated calibration (default 0.40, recalibrate after 3-6 induction rounds)
  - Q2 γ value (default 3, retune if L1↔human agreement < 80%)
  - Q3 λ value (0.995 vs 0.997)
  - Q9 Split replay choice — Option A (re-induce) vs Option B (proportional approximation); spec recommends starting with B, upgrade to A if precision insufficient
  - Q12 provenance lock unlock policy (no fallback path planned)
  - Q13 default merge-policy for reinduce (`full` vs align with reshuffle's `supersede-only`)
  - Q19 ObservationLog YAML scale — at N=1000 / F=50 ≈ 50,000 entries (~10MB); switch to SQLite once N ≥ 500
  Roadmapper should treat these as future tasks/decisions, NOT block on them.

## Topic: Cross-document reference (ingest set internal link)

- **source**: SPEC line 4
- **note**: Phase 1 SPEC explicitly references main ADR §5.4 Phase 1 row. The cross-ref forms a parent→child relationship (ADR scopes the program; SPEC implements one phase). No cycle. ADR's scope set is a strict superset of the SPEC's scope set.

## Topic: External (non-ingested) source references

- **source**: ADR cross_refs
- **note**: ADR cross-refs to research docs not in this ingest set:
  - `docs/research/feature_mining_v2_unified_decision.md` (math skeleton)
  - `docs/research/feature_mining_unified_schema.md` (schema details)
  - `docs/research/feature_mining_stats_models.md` (model comparison)
  - `docs/research/feature_mining_base_rate.md` (p0 study)
  - `docs/research/feature_mining_philosophy_decision.md` (3-tier architecture + 3 hard defenses)
  - `docs/explain/ai_feature_mining_plain.md` (early plain-language design)
  These are NOT ingested as classified docs; they are background. If conflicts arise downstream that reference these, manual review is required.
