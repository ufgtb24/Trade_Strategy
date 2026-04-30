# Requirements

Synthesized from manifest-tagged SPEC `2026-04-27-phase1-librarian-inducer-mvp.md` (precedence 1, subordinate to ADR `2026-04-25-feature-induction-framework-design.md`). Phase 1 scope only — later-phase requirements will be ingested when their specs land.

Each requirement carries an ID, the source SPEC reference, description, and acceptance criteria. Acceptance criteria are taken verbatim from §9 of the SPEC unless noted.

---

## REQ-phase1-package-skeleton

- **source**: `docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md` §2.1, §9 AC1
- **scope**: Package layout
- **description**: Add 7 new Python modules under `BreakoutStrategy/feature_library/` (`inducer.py`, `inducer_prompts.py`, `embedding_l0.py`, `feature_store.py`, `observation_log.py`, `librarian.py`, `feature_models.py`) plus matching test files; modify `glm4v_backend.py` to add `batch_describe`.
- **acceptance**:
  - All 7 new modules + test files exist
  - `glm4v_backend.py` retains `describe_chart` and adds `batch_describe`
  - `ls BreakoutStrategy/feature_library/` shows the package

## REQ-inducer-batch-induce

- **source**: §3, §9 AC4
- **scope**: Inducer module (Python, NOT subagent — see implementer note §11.1)
- **description**: Implement `batch_induce(sample_ids, backend, *, max_batch_size=5) -> list[Candidate]`. Loads chart.png + meta.yaml + nl_description.md for each sample, calls `GLM4VBackend.batch_describe`, parses YAML output into `Candidate` dataclass `(text, supporting_sample_ids, K, N, raw_response_excerpt)`. Filters supporting_ids not in batch; drops K<2.
- **acceptance**:
  - `batch_describe` returns non-empty including `candidates` YAML when called against AAPL × 5 samples
  - Invalid YAML → empty list (no crash)
  - sample_ids count > max_batch_size → ValueError
  - Sample 三件套 missing → FileNotFoundError

## REQ-inducer-prompt-protocol

- **source**: §3.2
- **scope**: LLM prompting
- **description**: Provide `INDUCER_SYSTEM_PROMPT` (Chinese instruction with K≥2 constraint, strict YAML output, no markdown) and `build_batch_user_message(samples_meta) -> str` injecting per-sample (ticker, bo_date, consolidation length/height/volume_ratio/tightness, breakout_day OHLCV).
- **acceptance**:
  - SYSTEM_PROMPT contains constraint keywords
  - build_batch_user_message contains all samples' metadata blocks

## REQ-glm4v-batch-describe

- **source**: §2.2, §9 AC4
- **scope**: GLM4V backend extension (only modification to existing Phase 0 code)
- **description**: Add `batch_describe(chart_paths: list[Path], user_message: str) -> str`. Single zhipuai call with multiple `image_url` blocks + 1 text block. Hard cap 5 (server-side limit, error 1210); raise `ValueError` on >5.
- **acceptance**:
  - mock zhipuai client → multi-image_url + 1 text block constructed correctly
  - >5 charts → `ValueError`
  - existing `describe_chart` interface unchanged

## REQ-embedding-l0

- **source**: §2.1, §8.1
- **scope**: L0 cosine
- **description**: Thin wrapper exposing `embed_text(text) -> np.ndarray (384-d)` and `cosine_similarity(a, b) -> float`. Implementation reuses `news_sentiment.embedding` to avoid cross-package direct dependency.
- **acceptance**:
  - embed_text returns 384-d
  - cosine self-similarity = 1.0
  - identical text → cosine = 1.0

## REQ-feature-store

- **source**: §2.1, §6, §8.1
- **scope**: features/<id>.yaml CRUD
- **description**: `load(id) / save(feature) / list_all() / next_id() / exists(id)`. Filename rule `F-NNN-<text-slug>.yaml` (slug = lowercase alnum + hyphen, ≤30 chars; non-ASCII dropped, fallback `F-NNN.yaml` if slug empty).
- **acceptance**:
  - save → load round-trip preserves all fields
  - next_id increments correctly
  - list_all returns all features

## REQ-observation-log-granularity

- **source**: §5, §9 AC7
- **scope**: ObservationLog
- **description**: ObservationLog stored INLINE in `features/<id>.yaml` `observations:` array (NOT a separate file). One entry per (sample_id, feature_id), NOT per batch. Schema per main ADR §4.2: `id, ts, source, epoch_tag, sample_id, K, N, C, alpha_after, beta_after, signal_after, superseded_by, notes`. `append_entry` and `get_active_entries` (filter `superseded_by is None`) APIs.
- **acceptance**:
  - Each obs entry contains `sample_id`
  - Same batch produces multiple obs entries (one per sample × candidate target)
  - get_active_entries skips entries where `superseded_by is not None`
  - Phase 1 writes `epoch_tag = null`, `superseded_by = null` (schema future-proof)

## REQ-librarian-upsert-candidate

- **source**: §4.1, §9 AC9
- **scope**: Librarian core API
- **description**: `upsert_candidate(candidate, *, batch_sample_ids, source="ai_induction") -> Feature`. Steps: (1) embed candidate.text; (2) `lookup_by_cosine(embedding, threshold=L0_MERGE_THRESHOLD=0.85)`; (3a) hit → merge into top-cosine match (tie-break smallest id); (3b) miss → create new feature. For each `sample_id ∈ supporting_sample_ids` write Event(K=1, N=1, C=0); for `sample_id ∈ (batch_sample_ids − supporting)` write Event(K=0, N=1, C=0). (4) recompute. **Phase 1 only implements `merge_policy = full` semantics**; merge-policy parameter deferred to Phase 1.5.
- **acceptance**:
  - Two near-identical candidate texts collapse to a single feature
  - Distinct texts → distinct features
  - obs entries correctly partition supporting vs silent samples

## REQ-librarian-recompute

- **source**: §4.3, §8.1, §9 AC8
- **scope**: Beta-Binomial replay
- **description**: `recompute(feature_id) -> Feature`. Reload obs (skip superseded), apply Phase-1 simplified update: `α = ALPHA_PRIOR(=0.5) + Σ K`, `β = BETA_PRIOR(=0.5) + Σ(N-K-C) + γ·ΣC`. Phase 1 has γ=1.0 placeholder, λ=1.0 (no decay), C=0 always. Derive `signal = scipy.stats.beta.ppf(0.05, α, β)`; derive `status_band` per band table.
- **acceptance**:
  - Unit tests cover (α, β) for typical K/N cases
  - signal correctly derived
  - status_band edge values (P5 = 0.05 / 0.20 / 0.40 / 0.60) classify per main ADR §3.4

## REQ-librarian-lookup-by-cosine

- **source**: §4.1
- **scope**: L0 lookup
- **description**: `lookup_by_cosine(embedding, threshold=0.85) -> list[Feature]` returning matches sorted by descending cosine.
- **acceptance**: returns hits ≥ threshold ordered by cosine desc; empty list when below threshold.

## REQ-features-yaml-schema

- **source**: §6, §9 AC6
- **scope**: features/<id>.yaml schema
- **description**: Full schema per main ADR §4.2: `id, text, embedding, alpha, beta, last_update_ts, provenance, observed_samples, total_K, total_N, total_C_weighted, observations[], research_status, factor_overlap_declared`. Phase 1.5+ fields (epoch_tag, superseded_by) present at obs level with null default. Derived fields (`signal`, `status_band`) NOT stored.
- **acceptance**:
  - yaml.safe_load + dataclass deserialization succeeds without error
  - All 14 top-level fields present
  - obs entries carry all 13 fields with null defaults where applicable

## REQ-entry-script-feature-mining-phase1

- **source**: §7, §9 AC3
- **scope**: Entry script
- **description**: `scripts/feature_mining_phase1.py` with parameters declared at top of `main()` (NO argparse, per CLAUDE.md). Default `ticker="AAPL"`, `sample_count=5`, `skip_preprocess=False`, `inducer_max_batch=5`, `breakout_detector_params={}`. Pipeline: ensure_samples (reuse Phase 0) → batch_induce → upsert_candidate per candidate → print_library_summary.
- **acceptance**:
  - script runs end-to-end without exception
  - exits with code 0
  - prints summary block in format shown in §7.3

## REQ-test-coverage

- **source**: §8, §9 AC2
- **scope**: Tests
- **description**: 30–40 new tests across all new modules, total 65–75 PASS combined with Phase 0's 35.
- **acceptance**:
  - `uv run pytest BreakoutStrategy/feature_library/tests/ -v` PASS
  - Coverage matrix per §8.1 satisfied

## REQ-end-to-end-smoke

- **source**: §8.2, §9 AC5
- **scope**: Smoke validation
- **description**: Run entry script with ticker=AAPL, sample_count=5; produce ≥ 1 candidate; write features/F-*.yaml; print summary.
- **acceptance**:
  - exit 0
  - feature_library/features/F-*.yaml ≥ 1
  - each yaml passes schema validation
  - obs count = candidates × batch size

## REQ-runtime-data-gitignored

- **source**: §2.3 note, §9 AC10
- **scope**: Repo hygiene
- **description**: `feature_library/` (incl. `samples/`, `features/`, `history/`) must remain in `.gitignore`.
- **acceptance**: `git status` shows no feature_library/* tracked files after running.

## REQ-invariant-blind-inducer

- **source**: §12.1
- **scope**: Hard invariant
- **description**: Phase 1 entry script must NOT inject any existing feature text into the Inducer prompt. Inducer remains blind to library state.
- **acceptance**: code review of build_batch_user_message + entry script confirms no feature-library reads on Inducer's path.

## REQ-invariant-cli-no-feature-content

- **source**: §12.4
- **scope**: Hard invariant
- **description**: Phase 1 entry script (CLI surrogate) only exposes sample_ids to Inducer, never feature texts.
- **acceptance**: code review confirms.
