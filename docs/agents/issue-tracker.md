# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`, on the
current branch. There is no GitHub Issues usage; do not reach for `gh`.

## Conventions

- For a feature without a Wayfinder decision effort, keep its spec and
  implementation issues in `.scratch/<feature-slug>/spec.md` and
  `.scratch/<feature-slug>/issues/<NN>-<slug>.md`.
- For a Wayfinder effort and its implementation, follow the separate-store rules linked below.
- Keep one file per ticket, numbered from `01` within its own store; never use
  one combined file as the ticket store.
- Triage state is recorded as a `Status:` line near the top of each issue file
  (use `triage-labels.md` when configured; otherwise retain canonical role names)
- Comments and conversation history append to the bottom of the file under a
  `## Comments` heading

## Artifact boundaries

Wayfinder decision tickets and implementation tickets use separate directories.
The decision effort's `.scratch/<effort>/spec.md` remains the sole authoritative
specification; implementation tickets reference it rather than copy it.

## When a skill says "publish to the issue tracker"

Publish Markdown files in the configured local store, not remote tracker issues.
Use the canonical spec path for specifications, the implementation store for
implementation tickets, and the Wayfinding operations entry below for decisions
and their assets. Follow each workflow's existing review/sign-off requirements;
publication does not add another approval round. Keep incoming triage requests
in their identified local store rather than silently treating them as decisions.

## When a skill says "fetch the relevant ticket"

Read the referenced local file, including its body and comments. Resolve a bare
number only within the identified effort and ticket store. Decision and
implementation stores may reuse numbers: if context does not identify one
unambiguous file, ask for the intended ticket instead of choosing arbitrarily.
This also applies to local issue references found during code review. A reference
to the parent spec or a decision is evidence, not an implementation dependency.

## Wayfinding operations

Before charting, creating, claiming or resolving Wayfinder decision tickets, or
propagating their answers, read and follow [Decision ticket rules](decision-tickets.md).
They define map/ticket structure, Purpose, Direction, assets, sign-off and validation
handoffs. This applies to Wayfinder and adapted local workflows.

## Implementation tickets

Before splitting, publishing, migrating, executing or accepting implementation
tickets, read and follow [Implementation ticket rules](implementation-tickets.md).
They define detailed layout, numbering, publication and execution, including
Purpose and inherited Direction. This applies to Matt Pocock to-tickets/implement,
adapted variants and equivalent manual workflows.

## Spec synthesis

When using the Matt Pocock `to-spec` workflow (including adapted/plugin-prefixed
versions), or collapsing approved Wayfinder decision tickets into an implementation
specification, first read and follow [Spec synthesis rules](spec-synthesis.md).
Ordinary software specification writing does not trigger this requirement by itself.

## Boards

Both boards are read-only local viewers. They display recorded work and derive
frontiers; they do not claim, publish, complete or resolve tickets themselves.

| Board | Purpose | Business data | Start command | Default address |
| --- | --- | --- | --- | --- |
| Decision | Decision progress and decision frontier | Effort `map.md` and decision `issues/*.md` | `python3 scripts/wayfinder_board.py .scratch/<effort> --serve` | http://127.0.0.1:8765 |
| Implementation | Development progress and executable frontier | Formal implementation `issues/*.md` and `questions/*.md` only | `python3 scripts/implementation_board.py .scratch/<effort>-implementation --serve` | http://127.0.0.1:8766 |

Implementation triage mappings interpret names only; neither an overview nor a
manifest supplies ticket state. Empty formal stores do not trigger draft publication.
Stop a foreground viewer with Ctrl-C; use each script's `--help` for optional
arguments. Decision and implementation lifecycle semantics remain in their respective
specialized ticket documents linked above.

Mechanism documents and reusable instructions are English; actual ticket prose
and board interfaces are Chinese. Protocol identifiers remain unchanged.
