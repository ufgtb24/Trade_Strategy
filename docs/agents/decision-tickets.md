# Wayfinder decision tickets

Before charting an effort, creating or claiming a decision ticket, resolving it,
or propagating its answer, read and follow this document. It applies to Wayfinder
and adapted workflows using the local Markdown tracker.

[issue-tracker.md](issue-tracker.md) supplies shared tracker and board entry points.
These rules govern decision work, not implementation progress. Once decisions are
approved, follow [spec-synthesis.md](spec-synthesis.md) and then
[implementation-tickets.md](implementation-tickets.md) for the handoff to delivery.

## Local backend overrides

These approved local conventions specialize the generic backend defaults of
Wayfinder and its research/prototype detours: retain assets under the effort on
the current branch, record the answer in the ticket, and obtain the required
sign-off before resolving or propagating it. Do not create remote issues or
throwaway asset branches merely because a generic skill describes those defaults.
Keep the skills' investigation methods and decision evidence requirements.

This is a scoped override for decision work; it does not govern implementation
branches or worktrees.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.
An effort's map, tickets and research all live under one directory:

```
.scratch/<effort>/
├── map.md                       ← the map
├── issues/<NN>-<slug>.md        ← child tickets, numbered from 01
├── research/<NN>-<slug>.md      ← findings from research tickets
├── prototypes/                  ← code from prototype tickets
└── scripts/                     ← throwaway analysis scripts and raw output
```

- **Map**: `.scratch/<effort>/map.md`, holding the Destination / Notes /
  Decisions so far / Not yet specified / Out of scope body, each under a `##`
  heading spelled exactly that way.
- **Destination**: two sentences. The first is the **product goal**: the
  outcome this effort ultimately serves. The second is the **output goal**:
  where this map ends — the spec, decision, or change it is finding its way
  to — and what stays off the map. Every ticket's purpose is written in terms
  of the first; the second fixes the scope.
- **Child ticket**: `.scratch/<effort>/issues/<NN>-<slug>.md`, numbered from
  `01`. The file opens with a `# <title>` line: that title is the ticket's
  name, the one narration and the map refer to it by. The question follows in
  the body under a `## Question` heading, opening with a `### Purpose`
  subsection (see **Ticket framing**). A `Type:`
  line records the ticket type (`research`/`prototype`/`grilling`/`task`),
  optionally suffixed `(HITL)` or `(AFK)` where the type alone doesn't settle
  it. A `Status:` line records
  `open`/`claimed`/`resolved`. A `Claimed:`
  line records the claim date as `YYYY-MM-DD`, optionally followed by a
  pointer to the session (a session id, a branch, a short note). It is added
  at claim time and left in place after the ticket resolves: every session is
  the same agent, so the date is what carries information, and it is how a
  claim that went stale gets noticed.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked
  when every ticket it lists is `resolved`. Keep the line after a blocker
  resolves; it is the record of why the ticket waited.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open,
  unblocked, and unclaimed; lowest `NN` wins.
- **Resolve**: on a prototype ticket, first reduce its assets to a minimal
  reusable package: final code, necessary inputs, and representative results
  supporting the decision. Remove redundant or obsolete artifacts, keep
  regenerable bulk output out of Git, and verify the retained package runs
  independently. Do this before writing the answer, so the answer links only
  to what is kept and the user approves the package as it will stay.
  Then append the answer under an `## Answer` heading that opens with
  the ticket's confirmed direction (see **Ticket framing**), set
  `Status: resolved`, then append a context pointer to the map's Decisions so
  far in `map.md`: one bullet per resolved ticket, shaped
  `- [<title>](issues/<NN>-<slug>.md): <one-line gist>`, the link relative to
  the effort directory. Tooling that reads the map matches on that shape.
- **Refer by name**: in narration and in the map, name maps and tickets by
  their title, never by a bare number. The number rides inside the link.

### Ticket framing

- A resolving session no longer has the map in view: it sees one question and
  drifts toward whatever detail that question opens onto. So the ticket's
  `## Question` opens with a `### Purpose` subsection, written when the ticket
  is created while the whole map is still in view: one sentence saying what
  role this ticket plays in reaching the product goal the Destination opens
  with. A purpose is a fact about
  the ticket's place on the map, not a judgment about its answer. Restating the
  question is not a purpose, and words of degree — enough, simpler, rather
  than — do not belong in one; they are the direction, settled later.
- The purpose is set by whoever creates the ticket with the whole map in view:
  the charting session, or the answer that graduates the ticket, which writes
  it into that answer so the approval covers it. It holds for the life of the
  ticket and is revisited only if the destination is redrawn. A question whose
  purpose can't be stated in terms of the product goal lies beyond the
  destination and belongs under **Out of scope**. Anything without a direct
  causal link to the product goal must not become a hard requirement.
- The **direction** is settled with the user right after claiming, before the
  question is worked: from the purpose and what is known, the session proposes
  in a sentence or two which way to lean when details compete, and the user
  confirms or corrects it. Findings may revise it with the user along the
  way. The confirmed direction opens
  `## Answer`, so the approval covers it and later readers know which way the
  answer leaned. A session that finds the purpose itself wrong says so there,
  with the reason, and never re-aims the ticket on its own.
- Industry standards, research findings, and existing code are **soft priors
  or candidate implementations** by default, not business goals.
- Before resolving a ticket, ask: **Would solving this perfectly materially
  improve the final deliverable?** If not, downgrade, simplify, or remove it.

### Assets produced while resolving a ticket

- **Research tickets** write their cited findings to
  `.scratch/<effort>/research/<NN>-<slug>.md` (same `NN` as the ticket), linked
  from the ticket's `## Answer`. This overrides the `/wayfinder` default of a
  throwaway branch.
- **Prototype tickets** write their code under `.scratch/<effort>/prototypes/`,
  linked from the ticket, rather than a `prototype/<name>` branch.
- **Scripts and raw output** produced while working a ticket (survey scripts,
  dumps, cross-checks) go under `.scratch/<effort>/scripts/`, prefixed with the
  ticket number. They are working material, not findings: the conclusions they
  support belong in the research file or the ticket's answer.

### Sign-off before anything leaves the ticket

A session writes freely in two places: **the ticket it has claimed**, and **its
own assets** — anything it produces under `research/`, `prototypes/` and
`scripts/`. Those are its own working output; no other session reads them until
the ticket's answer points at them.

Everything else is **shared state that other sessions read**: `map.md`, any
other ticket, new tickets, `Blocked by` edges, and the repo's domain docs.
None of it changes until the user has approved the answer — nor does this
ticket's own `Status`, which stays `claimed` until then.

**An unconfirmed answer is not a conclusion.** Resolving a ticket ends by
writing `## Answer` and stopping there, with the answer in front of the user.
Once they approve it, **that single approval covers every change that follows
from it**. Make them all, without asking again.

The reason is propagation, not caution. A line in `Decisions so far` makes a
conclusion globally true for every later session. The worst version is
rewriting another ticket's `## Question` in light of your own unconfirmed
answer: it deletes the premise that ticket was written to examine, invisibly to
whoever picks it up next. One round of review is cheap; unpicking a conclusion
from five files is not.

Claiming is the exception: set `Status: claimed` and the `Claimed:` line
before any other work. It touches only the ticket you are about to resolve.
The next step, still before working the question, is settling its direction
with the user (see **Ticket framing**).

## Implementation-stage validation

- Questions that require implementation, training, or runtime evidence may be
  deferred with the decision. The original ticket's answer must state **what
  remains to be validated, what triggers validation, how it will be judged,
  what may proceed before validation, and what happens or which decision is
  revisited on failure**. Format is flexible; "check during implementation"
  alone is insufficient.
- Deferral must be approved with the answer. A resolved decision ticket does
  not mean its assumptions have been validated. If reasonable adoption
  conditions or failure handling cannot yet be defined, the question still
  blocks the decision.
- Each validation item must remain unambiguously referenceable. Carry it in
  full into the spec, then assign execution responsibility, prerequisites,
  and acceptance requirements when creating implementation tickets. Do not
  lose items at handoffs.
- During implementation, record validation evidence against the item. Failure
  or insufficient evidence must not count as a pass. Changes to the original
  decision and propagation to shared documents remain subject to sign-off.

