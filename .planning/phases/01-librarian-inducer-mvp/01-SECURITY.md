---
phase: 1
slug: librarian-inducer-mvp
status: verified
threats_open: 0
invariants_open: 0
asvs_level: 1
created: 2026-04-29
last_audit: 2026-04-29
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Local filesystem (datasets/pkls, configs/) → dev tool process | 本地 pickle 历史数据与 yaml 配置 → BreakoutStrategy.dev FSM/UI | 本地受信数据，非 untrusted |
| Local filesystem (BreakoutStrategy/dev/library/) → librarian renderer | sample_meta.yaml 与历史 df_window 切片 → 本地 PNG 渲染 | 本地受信数据 |
| Dev UI (Tk) → 本机用户 | 单用户 dev 工具，无网络监听端口 | 本机 GUI 输入 |

*所有 boundary 均位于本机受信任开发环境内；本 phase 不引入新的外部网络端点、不接收 untrusted 输入、不持久化敏感凭证。*

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| — | — | — | — | 无外部 attack surface — STRIDE 不适用 | — |

*Phase 1 由 5 个 plan 组成（FSM 重构、librarian picker 集成、sample_renderer 渲染、prompt pivot 公式修正、E2E + UAT），每个 plan 的 `<threat_model>` 均显式声明 "无外部 surface — STRIDE 不适用"。所有改动均在本机 dev 工具内部，无新增网络端点、无 untrusted 输入路径、无凭证或 PII 处理。*

---

## Application Invariants Register

ROADMAP Phase 1 SC #5 / SPEC §9 要求人工 code review 验证的两条"硬不变量"
（blind-inducer protocol，源自 ADR-008 / ADR-020）。这两条不属 STRIDE 但属安全语义层不变量，
路由到 `/gsd-secure-phase 1` 审计。

| Inv ID | Requirement | Subject | Status | Verified Via |
|--------|-------------|---------|--------|--------------|
| INV-1 | REQ-invariant-blind-inducer | Inducer prompt path 不读取 `feature_library/features/*` 任何状态 | CLOSED | 静态 grep + 模块依赖追溯（2026-04-29） |
| INV-2 | REQ-invariant-cli-no-feature-content | Phase 1 entry script 调用 Inducer 时仅传 `sample_ids` / `backend`，不传 feature 文本 | CLOSED | `scripts/feature_mining_phase1.py` `batch_induce` call site review（2026-04-29） |

### INV-1 Evidence — REQ-invariant-blind-inducer

Inducer 调用链上各模块的 imports：

| Module | feature_library 读取 imports | 结论 |
|--------|------------------------------|------|
| `BreakoutStrategy/feature_library/inducer.py` | `paths` (sample 路径常量)、`feature_models.Candidate`、`glm4v_backend`、`inducer_prompts`。**无** `FeatureStore` / `Librarian` / `features/` 文件读取 | blind |
| `BreakoutStrategy/feature_library/inducer_prompts.py::build_batch_user_message` | 只接收 `samples_meta: list[dict]`（来自 `samples/<id>/meta.yaml`）。函数体内 0 次 file IO | blind |
| `BreakoutStrategy/feature_library/glm4v_backend.py::batch_describe` | 仅 chart.png + user_message + system_prompt。无 feature_library 读取 | blind |

`inducer.batch_induce` 数据流：
- 入参：`sample_ids`, `backend`, `max_batch_size`
- 读盘：仅 `paths.chart_png_path(sid)` + `paths.meta_yaml_path(sid)` (per-sample artifacts)
- prompt 构造：`build_batch_user_message(metas, return_id_map=True)` ← 只用 sample meta
- 出参：`list[Candidate]`（无任何 library 状态嵌入）

**结论**：Inducer 路径上 0 次 `features/F-*.yaml` 或 `FeatureStore` / `Librarian` 读取。Inducer 完全 blind to library state。

### INV-2 Evidence — REQ-invariant-cli-no-feature-content

Entry script `scripts/feature_mining_phase1.py` 中 Inducer 调用 site：

```python
# scripts/feature_mining_phase1.py:181-184
candidates = batch_induce(
    sample_ids=sample_ids[:inducer_max_batch],
    backend=backend,
)
```

仅传 `sample_ids` (str list) 与 `backend` (GLM4VBackend instance)。`FeatureStore()` 实例化发生在 line 196（Inducer 调用之后），用途仅限 upsert + library summary print，不参与 prompt 构造。

`_print_library_summary`（line 122-140）会打印 `text=\"{text_preview}\"` 等 feature 内容，但该输出指向用户 stdout，不是 Inducer prompt 通道。SPEC 约束 "仅向 Inducer 暴露 sample_ids"；用户终端展示已有 features 列表不在约束范围内。

**结论**：entry script → Inducer 通道仅暴露 `sample_ids`，未泄漏 feature 文本。

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Scope | Threats Total | Closed | Open | Invariants Total | Closed | Open | Run By |
|------------|-------|---------------|--------|------|-------------------|--------|------|--------|
| 2026-04-29 | STRIDE register | 0 | 0 | 0 | — | — | — | gsd-secure-phase (artifact-only audit, empty register) |
| 2026-04-29 | Application invariants (INV-1 / INV-2) | — | — | — | 2 | 2 | 0 | gsd-secure-phase (inline code review,无 agent spawn) |

**Audit notes:**
- 首轮 audit (STRIDE)：源 `01-01-PLAN.md` … `01-05-PLAN.md` `<threat_model>` + `01-01-SUMMARY.md` … `01-04-SUMMARY.md` `## Threat Flags`；全部 5 个 plan 一致声明无外部 surface；因 `threats_open: 0` 跳过 gsd-security-auditor。
- 二轮 audit (Invariants)：CONTEXT.md `<deferred>` 路由的 REQ-invariant-blind-inducer / REQ-invariant-cli-no-feature-content；通过静态 grep + 模块依赖追溯 inline 完成（无 STRIDE 范畴，无需 spawn auditor agent）。

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer) — 空 register，无需 disposition
- [x] Accepted risks documented in Accepted Risks Log — 无
- [x] `threats_open: 0` confirmed
- [x] `invariants_open: 0` confirmed (INV-1 / INV-2 closed via code review)
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-29 (re-affirmed after invariants audit)
