# Spec synthesis from approved decisions

Use these rules when running the Matt Pocock `to-spec` workflow (including
adapted/plugin-prefixed versions), or collapsing approved Wayfinder decision
tickets into an implementation specification. They do not apply merely because
someone asks for an ordinary software specification.

The purpose is to establish which approved clauses remain effective where
tickets overlap, before drafting the spec. This document defines the shared
method; each project produces its own adoption record. Do not copy another
project's ticket numbers, decisions, or acceptance thresholds into that record.

## Read the complete source set first

1. Establish the requested effort/feature and list its relevant source tickets.
   Read the map/spec context and every ticket in that set, including approved
   answers and later approved amendments. Follow references when they affect a
   clause's meaning or a consumer's interface. This is a bounded traversal of
   the relevant effort, not a scan of every ticket in the repository.
2. Separate confirmed decisions from original questions, abandoned proposals,
   unapproved comments, experiment observations, and approved-but-unexecuted
   validation. A `resolved` status alone does not make every historical paragraph
   in that file the final rule.
3. Extract concrete decision items with their source section, applicable scope,
   conditions, and approval evidence. Normalize synonymous topic names into a
   topic index. A clause may belong to several topics when it affects several
   interfaces.

Start with traversal and indexing, rather than repeated keyword searches or
comparing every whole ticket against every other ticket. Compare clauses within
relevant topic groups; then check cross-topic constraints and consumer interfaces.
Targeted searches are useful for resolving a specific ambiguity, but cannot
replace reading the source set. This reduces redundant work; it is not a claim
that semantic overlap detection always has linear complexity.

## Resolve overlap at clause level

Record these relationships where they actually occur:

| Relationship | Treatment |
| --- | --- |
| Duplicate | State the rule once and retain the supporting sources. |
| Supplement | Combine compatible details; preserve the original scope and constraints. |
| Explicit replacement | Replace only the identified clause and scope, with its approval evidence; identify what remains effective. |
| Different scopes | Keep both rules with explicit conditions; do not manufacture a conflict. |
| Unresolved conflict | Record the incompatible clauses and missing decision; do not silently choose one. |

A later date, higher ticket number, or `Blocked by` edge does not establish
replacement. In Wayfinder, that edge primarily records the order in which
decisions could be settled. It is neither a clause-precedence rule nor an
implementation schedule. A dependency graph is not required for this synthesis;
use a view of the recorded relationships only when it helps inspect a real issue.

Evidence for replacement must be a confirmed answer/amendment or an explicit
user-approved change, with a traceable source. An experiment, current code, or
the synthesizer's preference cannot silently override an approved decision.
If approval or scope is unclear, return to the exact source passage. If the
conflict remains, identify the decision requiring clarification through the
project's decision process; do not turn synthesis into a new unrecorded decision.
Independent sections may proceed, but a spec with a blocking unresolved conflict
must not be published as ready for implementation.

## Keep one overlap-and-adoption table

Create the table before drafting the affected spec sections. Include only actual
overlap, mutual constraints, or conflicts; non-overlapping clauses go directly
into the spec. Compatible rows with the same adoption result may be combined.
No overlap means no empty table or extra file: record that outcome briefly in
the synthesis audit.

| Decision item | Source clauses | Applicable scope | Relationship | Adopted rule and retained boundaries | Approval evidence | Spec destination |
| --- | --- | --- | --- | --- | --- | --- |

Use source paths and stable section/record identifiers sufficient to find the
actual clauses and approval. The adopted rule must say what is effective, not
just "latest wins" or "see ticket B". For partial replacement, explicitly retain
the unaffected rules. An unresolved row must say what remains undecided rather
than present a proposed answer as adopted.

Reuse an existing equivalent adoption/audit table instead of creating a second
authority. Otherwise place it at
`.scratch/<effort-or-feature>/research/spec-adoption.md` and link it from the
spec; a spec appendix is also suitable when that keeps a small record together.
Choose one location. This is synthesis evidence, not a new decision ticket, and
does not need separate approval when it only records already-approved decisions.
New decisions still follow the project's sign-off rules.

## Synthesize and check

Write the spec from the adopted clauses, not by concatenating historical ticket
bodies. State the effective rules in full so that implementation does not require
reconstructing their history. Keep the adoption table for traceability, not as a
substitute for the specification.

Carry forward the complete approved implementation-validation contracts required
by the decision-ticket rules’ “Implementation-stage validation” section in
[decision-tickets.md](decision-tickets.md).
Preserve their identifiers and unverified status; do not infer that resolved
decisions mean experiments or acceptance checks have passed. Classify remaining
work as implementation, conditional validation, or a genuinely unresolved
decision; lack of code alone is not a reason to reopen a settled decision.

Before finishing, verify:

- Every source in the declared set was read, including relevant approved amendments.
- Each overlap has an adoption result and evidence, or an explicitly unresolved conflict.
- The spec follows the adoption table and retains unaffected clauses, boundaries,
  failure handling, and validation obligations.
- No rejected/superseded proposal has silently returned, and no project-specific
  choice has been promoted to a universal requirement.
- Source links and spec destinations resolve; reused records are not duplicated.
- Readiness reflects unresolved decisions and validation prerequisites accurately.

If a source changes during synthesis, revisit its affected topic groups and
dependent clauses before finalizing; do not overwrite concurrent source edits.
