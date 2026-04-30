# Synthesis Summary

Single-entry-point summary of doc ingest synthesis. Read this first; per-type intel files (`decisions.md`, `requirements.md`, `constraints.md`, `context.md`) and conflict report (`../INGEST-CONFLICTS.md`) follow.

---

## Ingest set

- **Mode**: `new` (net-new bootstrap; no pre-existing `.planning/` content)
- **Total classified docs**: 2
  - 1 ADR (precedence 0, LOCKED): `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`
  - 1 SPEC (precedence 1, non-locked): `docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md`
- **Cross-ref graph**: SPEC → ADR (parent reference). Acyclic.
- **UNKNOWN/low-confidence docs**: 0

## Decisions extracted (LOCKED)

21 architectural decisions from the ADR, all LOCKED (manifest precedence 0):

- ADR-001 — Decouple feature-induction framework from mining pipeline
- ADR-002 — User-picked samples define the framework's domain
- ADR-003 — Three AI roles + CLI Scheduler (Inducer / Librarian / Critic + `feature-mine`)
- ADR-004 — Role responsibility hard boundaries
- ADR-005 — Beta-Binomial conjugate posterior as the SOLE statistic
- ADR-006 — Three-tier cost ladder (L0 fastembed / L1 DeepSeek / L2 Opus)
- ADR-007 — User-driven CLI rhythm; passive reminders only
- ADR-008 — Replay blocking rule (math consistency hard constraint)
- ADR-009 — Multi-epoch four mechanisms (Replay / Re-induction / Re-verification / Shuffled Re-induction)
- ADR-010 — Merge Semantics three policies (`full` / `supersede-only` / `reject-merge`)
- ADR-011 — ObservationLog at (sample, feature) granularity + epoch_tag + superseded_by
- ADR-012 — Feature-level `provenance` + Shuffled-born candidate lock
- ADR-013 — Inducer is BLIND (no library lookup, no rule/hypothesis classification)
- ADR-014 — Critic does NOT touch (α, β) and does NOT modify Inducer prompt
- ADR-015 — All state lives in `feature_library/` filesystem
- ADR-016 — Time decay applied lazily (no cron job)
- ADR-017 — γ = 3 default counter weight (configurable)
- ADR-018 — Anti–multi-view augmentation; multi-epoch ONLY via 4 sanctioned paths
- ADR-019 — Reshuffle uses anti-correlated batching only
- ADR-020 — Phase roadmap (Phase 0 done; Phase 1–4c sequence)
- ADR-021 — Out-of-scope items (explicitly shelved)

## Requirements extracted

17 Phase-1-scoped requirements from the SPEC:

- REQ-phase1-package-skeleton
- REQ-inducer-batch-induce
- REQ-inducer-prompt-protocol
- REQ-glm4v-batch-describe
- REQ-embedding-l0
- REQ-feature-store
- REQ-observation-log-granularity
- REQ-librarian-upsert-candidate
- REQ-librarian-recompute
- REQ-librarian-lookup-by-cosine
- REQ-features-yaml-schema
- REQ-entry-script-feature-mining-phase1
- REQ-test-coverage
- REQ-end-to-end-smoke
- REQ-runtime-data-gitignored
- REQ-invariant-blind-inducer
- REQ-invariant-cli-no-feature-content

## Constraints extracted

19 constraints:

- 5 protocol (GLM-4V batch cap; Replay blocking; reshuffle cost guard; CLI lifecycle)
- 8 schema (OHLCV lowercase; feature-id naming; features yaml schema; obs granularity; cooccurrence yaml; pending_replays yaml; archetype hint discipline; double-counting defense)
- 6 nfr (no argparse; language policy; Beta-Binomial defaults; runtime data gitignored; state in filesystem; …)
- 5 api-contract (update formula; merge-policy defaults; Inducer blind prompt; Critic mutation discipline; double-counting defense)

(Total exceeds 19 because some constraints span multiple types; counted distinctly per content category.)

## Context topics

10 background topics covering project domain, design philosophies, Phase 0 status, P5 intuition, Orchestrator-downgrade rationale, predecessor design docs, FORBIDDEN multi-view rationale, Phase 1 implementation deviation, 19 open implementation-time questions (Q1–Q19), and external (non-ingested) cross-refs.

## Conflicts

- **0 BLOCKERS**
- **0 WARNINGS**
- **3 INFO** (Phase 1 SPEC self-documented deviations from ADR; recorded for transparency)

The ADR and SPEC share a clean parent→child relationship. SPEC explicitly subordinates to ADR §5.4 Phase 1 row and labels its three deviations (subagent → Python module; batch 8-12 → batch 5; epoch_tag/decay/γ deferred) in §11. No genuine architectural contradiction.

See `/home/yu/PycharmProjects/Trade_Strategy/.planning/INGEST-CONFLICTS.md` for the full conflict report.

## File map

- `/home/yu/PycharmProjects/Trade_Strategy/.planning/intel/decisions.md` — 21 LOCKED ADR decisions
- `/home/yu/PycharmProjects/Trade_Strategy/.planning/intel/requirements.md` — 17 Phase-1 requirements with acceptance
- `/home/yu/PycharmProjects/Trade_Strategy/.planning/intel/constraints.md` — schema / api-contract / protocol / nfr constraints
- `/home/yu/PycharmProjects/Trade_Strategy/.planning/intel/context.md` — background notes
- `/home/yu/PycharmProjects/Trade_Strategy/.planning/INGEST-CONFLICTS.md` — three-bucket conflict report

## Provenance

Every entry across all four intel files carries a `source:` reference to the originating doc (path + section anchor where applicable). Downstream consumers (`gsd-roadmapper`, manual review) can trace any claim back to the ADR or SPEC.

## Status

**READY** — safe to route to roadmapper. 0 blockers, 0 variants. ADR is LOCKED; SPEC is in scope for Phase 1 only. Phase 1.5 / 2 / 3 / 4a–c will require separate spec ingest passes when their docs land.
