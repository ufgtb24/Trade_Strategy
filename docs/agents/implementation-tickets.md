# Implementation tickets

Read this document before splitting, publishing, migrating, executing, accepting
or interpreting local Markdown implementation tickets. It owns the detailed
artifact layout, numbering, publication and execution contract, extending the
Matt Pocock ticket format without replacing its five triage roles.
[issue-tracker.md](issue-tracker.md) is the tracker entry point; decision synthesis
belongs in [spec-synthesis.md](spec-synthesis.md).

Mechanism instructions and reusable templates are English. Actual ticket titles,
Purpose/Direction text, deliverables, acceptance criteria, results and board UI are
Chinese. Keep protocol fields, enum values, commands and identifiers unchanged.

## Artifact layout and publication

For a Wayfinder effort, keep decision work and implementation work in separate
sibling directories. The following rules define their shared boundary; generic
features without a Wayfinder effort keep the default store documented by the
tracker.

```text
.scratch/
├── <effort>/
│   ├── map.md                         # decision map
│   ├── spec.md                        # sole authoritative implementation spec
│   └── issues/<NN>-<slug>.md           # Wayfinder decision tickets
└── <effort>-implementation/
    ├── ticket-breakdown.md             # implementation breakdown and review entry
    ├── issues/<NN>-<slug>.md           # published implementation tickets
    ├── questions/Q<NN>-<slug>.md       # user questions (see User questions)
    └── evidence/<NN>/                  # committed evidence per ticket (see Completion artifacts)
```

- Reuse the decision effort's exact slug with the `-implementation` suffix.
  Keep the approved spec at `.scratch/<effort>/spec.md`; the breakdown and each
  implementation ticket link directly to it. Do not copy it into a second spec
  or move it merely to match the implementation directory.
- Decision and implementation tickets have independent numbering, each starting
  at `01`. Keep reviewed numbers when publishing. Cross-store references
  must include a path/link, not just an ambiguous ticket number.
- `ticket-breakdown.md` lists proposed titles, prerequisites and deliverables,
  links to the individual tickets, and states whether the breakdown is awaiting
  approval or published. This filename is our local convention, not an upstream
  `to-tickets` requirement. Do not use `README.md` as a substitute for this entry.
  After publication, append to it only when the ticket set changes.
- Review the proposed breakdown in conversation or `ticket-breakdown.md`, then
  publish approved tickets into implementation `issues/` in dependency order.
  New work does not require a separate draft lifecycle or drafts directory.
  Keep planning material out of the decision effort's research directory.
- When presenting the breakdown for review, flag tickets whose execution likely
  needs a human in the loop: repeated judgment while it runs (for example training
  that is tuned as results arrive), external access, or manual testing. Give each
  flagged ticket a recommended role and a one-sentence reason, and let the user
  confirm the roles in the same review round; this is part of that review, not a
  separate approval step.
- Whoever adds implementation tickets or `Blocked by` prerequisites, by any route
  (a breakdown, a decision answer, a follow-up to a closed ticket, a question's
  resolution, a scope adjustment), drafts the tickets and their prerequisites
  first, then reads and follows [review-planning.md](review-planning.md) to settle
  where the user reviews results, including its upstream check for older results
  that gain a new consumer, before presenting them; the reviews are presented in
  the same review round. The acceptance criteria then carry the review; executors
  do not decide it.
- Published tickets default to `ready-for-agent` unless the user chose
  `ready-for-human` in that review, including those waiting for
  prerequisites; readiness is derived separately. Update overview links without
  retaining duplicate editable drafts. Existing approval covers publication.
  Inspect existing drafts before any authorized migration; installing these
  rules neither approves nor publishes them.
- Every implementation ticket has explicit acceptance criteria and `Blocked by:`
  prerequisites from the implementation store (write `none` if empty). These
  edges form an acyclic graph of technical prerequisites. Source decision tickets
  are evidence links, not implementation blockers; do not copy the Wayfinder
  decision order as the development schedule. A Mermaid diagram is optional;
  the per-ticket dependency declarations are required.
- Authoring or publishing implementation tickets does not change the parent spec,
  resolve decision tickets, or authorize implementation/training by itself. The
  Wayfinding lifecycle in `decision-tickets.md` applies to decision tickets, not implementation.
- Publication-time consistency checks describe the pre-implementation state (for
  example, that production code is unchanged). Once implementation starts, retire
  them or scope them explicitly to publication so their expected failures are not
  read as implementation defects. Freeze generated manifests too; no check may
  require copying a ticket field or editing unchanged content.

For existing efforts, inspect their current layout before applying this convention;
changing the rule alone is not an instruction to relocate existing artifacts.

Keep the official vertical-slice and expand–contract requirements when preparing
the breakdown. Inspect existing ticket content and execution evidence before
migrating old metadata; unclear historical states cannot be mapped to completion
mechanically.

## Purpose, inherited direction and deliverable

Each ticket must be understandable in a fresh context and deliver an independently
verifiable behavior. Reuse equivalent sections instead of duplicating text.

| Content | Requirement |
| --- | --- |
| Purpose | One sentence explaining the ticket's contribution to the product outcome; not a restatement of a module name or a technical preference. |
| Source | Link the authoritative spec and applicable clauses; link approved decisions or prototypes when needed for traceability. These are evidence, not implementation blockers. |
| Inherited Direction | Extract relevant approved trade-offs and boundaries. Give each hard constraint with the reason the source states for it (what it guards against), so an executor can tell whether a later case is one it was meant to cover. Do not copy the whole spec or invent a direction the source never approved. |
| What to build | Describe the observable behavior or deliverable, including verifiable outcomes for preparatory refactors. |
| Scope and exclusions | Define responsibility and prevent incidental refactors, research expansion or changes to unrelated work. |
| Blocked by | Identify actual prerequisite deliverables from the same implementation ticket store; do not copy decision-solving order. |
| Acceptance criteria | Provide checkable behavior and a reproducible verification route, not merely "matches spec" or "tests pass". |
| Validation responsibility | Link each contract by ID to its spec clause instead of copying it; identify a closure owner where multiple tickets supply evidence. |

Purpose answers why; What to build answers what; Direction records trade-offs that
have already been decided. They are content, not labels or new workflow stages.
Official tickets without these added sections remain readable in the board.

Pin in a ticket only what downstream work or acceptance depends on: interface
contracts, data boundaries and the definition of done. Refer to tunable values
(hyperparameters, thresholds, budgets) and mechanisms owned elsewhere by their authoritative location, such as a
spec clause or configuration file, instead of copying the numbers, and do not
harden values the source calls starting defaults into constraints that cannot
change during execution. The values actually used belong in run records and the
completion explanation, so tuning does not require editing the ticket.

## Keep direction; challenge decisions that cause problems

Extract Purpose and Direction when preparing the breakdown, while the whole spec
is in view, and review them with it. At claim time, verify understanding and
actual prerequisites; do not ask the user to approve the same direction again.

The user's latest decision outranks earlier records, including decisions they
approved; mention a conflicting one as information, never as grounds to resist.
A clear direction from the user is the approval: draft the wording, say in one
line what it touches, and apply it on their go-ahead.

Existing code, customary practice, papers and reference branches cannot override
approved requirements; choose details within them, and polish only while it
improves the product. Changes to goals, interface contracts, adopted approaches or
acceptance standards go through a user question. If information is missing or
evidence contradicts the spec, keep the evidence and pause affected work. Do not
rewrite the spec, other tickets or failure statistics merely to pass. Shared code
needs no extra approval.

Decisions serve the ticket's Purpose, not the other way round. Either keep a
decision silently or raise it; there is no keeping it and reporting it. Keep it
while respecting it costs little. When a fix would work around it or cost more
than revising it, when its reason does not cover the case, or when a problem
survives two fix rounds, list the decisions your fixes have respected, name the
likely culprit, and raise a question that quotes it with its reason and
recommends keeping or revising it, with wording; never keep compensating
silently past that point. Replace approaches adopted only during implementation
yourself. Never break or rewrite a decision on your own; the user decides.

## Triage status and execution progress

`Status` retains the official triage meaning. Interpret project-specific names
through the project `triage-labels.md` when present. Official setup may omit this
file when triage is not installed; then use the five canonical names below. This
is a name-to-role mapping, not a second state store or new lifecycle semantics.

| Official role | Meaning | Execution eligibility |
| --- | --- | --- |
| `needs-triage` | Needs assessment | Not executable yet. |
| `needs-info` | Needs additional information | Not executable yet; may also describe an information gap discovered after work started. |
| `ready-for-agent` | Can be carried to completion without a human in the loop | Check progress, claim and dependencies as well. |
| `ready-for-human` | A human drives the execution (human in the loop) | Distinguish from agent work; does not mean awaiting human acceptance, nor that a human writes the code by hand. |
| `wontfix` | Will not be actioned | Not successful completion and does not automatically satisfy dependencies. |

Tickets published by `to-tickets` default to `ready-for-agent` even when blocked by
unfinished prerequisites. Do not re-triage them or substitute `Status: blocked`.
Use `ready-for-human` when a human drives the execution: the work itself needs one
in the loop (repeated judgment while it runs, external access, manual testing), or
a human has taken it over. Who types the code does not decide the role: a
human-driven ticket is often carried out in an agent session the human works
with, and a `ready-for-agent` ticket may be executed by a dispatched background
agent or by an ordinary session, which stops only at points the ticket or the
rules define and asks there through a question. Moving a published ticket, started or not, to or from
`ready-for-human` because of who executes it is not re-triage; record the reason in
Comments. Such tickets stay out of the agent frontier (see Prerequisites, frontier
and anomalies) and agent orchestration leaves them alone whatever their progress;
a human claims them like any other ticket.

The local `Progress` extension has only three values:

| Value | Meaning |
| --- | --- |
| `not-started` | Not currently started, or released for another executor to resume after a documented handoff. |
| `in-progress` | Claimed work, including implementation, testing, review and acceptance. |
| `done` | Ticket acceptance and applicable workflow requirements met, with a recorded completion explanation. |

New tickets record `Progress` explicitly. For compatibility, an official ticket
without it and without a structured claim/completion record defaults to not
started. If such records exist without a progress value, report ambiguity instead
of guessing from prose or checked boxes. Do not write lifecycle values in `Status`.

Use `Claimed: YYYY-MM-DD <executor or session>` with `in-progress`. Keep the claim
at completion for traceability. An active ticket lacking a claim is not free to
claim; show a warning. A claim with `not-started` is contradictory.

Put the explicit completion explanation and evidence in `## Completion` (Chinese
body), or the equivalent recognized headings `## 完成记录`, `## 完成说明`, or
`## 完成结果`. A legacy `Completed:` field signals that progress cannot safely be
assumed absent, but does not replace the completion explanation. A completion
record with a non-done progress value is contradictory: move historical reports
to clearly marked history/Comments when handing off unfinished work.

For an already approved implementation ticket, information gaps may change
`Status` to `needs-info` while preserving progress and
claim history; explain what is paused. When the gap needs a user decision, record
it as a question (see User questions): the question explains the pause, `needs-info`
blocks the ticket. When clarified, restore the appropriate ready role. `wontfix` may preserve earlier not-started/in-progress history, but it
means work is no longer executing. Do not use `done` to clear abandoned work.
`done` combined with needs-info, needs-triage or wontfix is contradictory.

A `done` or `wontfix` ticket is a closed record: never edit it, Comments included;
follow it up through a new ticket or a question.

- Do not put a spec version on tickets; every revision would then touch them all.
  At completion, recheck the ticket's clauses if the spec changed since the claim.
- Shared code changed while a ticket is in progress does not edit other tickets.
  At completion, name the shared mechanisms and earlier results it changed and
  recheck once the not-started tickets that use them, rewriting only clauses
  that became false.

Accept both `Status: ...` and official `**Status:** ...` syntax, and similarly for
the other metadata fields. Fields must be unique and explicit in the preamble;
fenced code and quoted examples are not metadata.

## External-request triage is a separate workflow

Do not re-triage tickets generated from an approved spec by to-tickets. When a
local file represents an incoming request being processed by triage, preserve
that skill's requirements: exactly one category (bug/enhancement) and one state,
AI-triage disclaimer, durable brief/comments, and its needs-info-to-needs-triage
re-evaluation after a reporter replies unless the maintainer explicitly overrides.
The implementation-resumption rule above does not bypass that re-evaluation.
Category and triage notes remain ticket content, not extra execution stages.
Remote PR-specific role meanings belong to a configured remote tracker; this
local customization does not enable external-PR discovery or merging.

## Prerequisites, frontier and anomalies

An agent frontier ticket is published, ready-for-agent, not started, unclaimed,
and has all prerequisites validly completed with no eligibility-affecting data
errors. Apply the same dependency check to human work, but do not put it in the
agent-grabbable set.

- Always declare `Blocked by`; use `none` or official `None (can start immediately)`
  when empty. Separate multiple references with commas. References may be numbers,
  unique exact titles, number-plus-matching-title, or links to sibling ticket files.
  Do not silently discard trailing tokens or infer cross-store dependencies.
- A valid `Progress: done` record can satisfy successors. The board displays the
  declaration; it does not rerun tests or infer completion from code or commits.
- Missing information, interruption, failure and wontfix are not completion. If a
  dependency is no longer needed, change the consumer through a justified scope
  adjustment rather than silently treating the edge as satisfied.
- Preserve completed edges. Derive dependents and waiting lists from prerequisites;
  do not maintain another editable frontier/dependency file.
- A shared frontier is not a guarantee of conflict-free parallel execution. Check
  interfaces, shared files and compute resources before assigning simultaneous work.
- Put parallelism where it pays most. A compute-bound long job (a formal training
  run, a full-batch generation) is sized to use all the CPU cores, GPU memory and
  RAM the machine can give it (RAM within the project's heavy-work budget) and is
  never shrunk to make room for other tickets; other tickets run beside it only in
  the CPU, GPU memory and RAM it leaves, and wait otherwise. Long jobs run one at a
  time; with none in play, tickets run in parallel.
- Missing/ambiguous prerequisites, duplicate IDs, cycles, self-dependencies, unknown
  values and contradictory fields are visible errors, not grounds to drop tickets
  or guess eligibility. Retain original values and stages.
- Active/done tickets with unfinished prerequisites need an anomaly warning; the
  board must not silently roll them back or use invalid completion to unlock work.
- The board also keeps a ready, not-started ticket off the frontier while an
  unresolved user question lists it, with a warning. This is a safeguard against a
  missed `needs-info`, not a replacement for it.

## User questions

A decision only the user can make (a spec gap, a rule that would make later tickets
impossible, a decision whose cost now outweighs its purpose, a long job to approve,
an undeclared dependency, a build-on step about to use a result whose user-only
part was never reviewed) gets one question file. That last case is the fallback
for build-on points that review planning missed or that appear during execution:
a prerequisite's `未安排人审：` part, or a default or measure an executor set and
marked to be validated (待验证), counts as never reviewed.
It is the single durable place for what is being decided, the routes, their costs
and the recommendation. The board lists unresolved questions first; a session that asks
the user reads the same file.

- **Location and naming:** `<effort>-implementation/questions/Q<NN>-<slug>.md`,
  numbered independently of tickets: take the highest existing number plus one while
  holding whatever lock the project uses for tracker writes. Never delete a question;
  merge a duplicate into the lower number and mark the other `withdrawn` ("merged
  into Qmm"). Write under a hidden temporary name (`.Q<NN>-<slug>.md.tmp`) and rename,
  so the board never reads half a file.
- **Preamble fields:** `Status`, `Blocks`, `Raised`, `Recommended`.
  - `Status`: `drafting` (raised, brief being written) → `open` (waiting for the
    user) → `applying` (an approved decision revision is being propagated) →
    `resolved`; or `withdrawn`. `drafting`, `open` and `applying` are unresolved.
  - `Blocks`: ticket numbers separated by commas, or `none`. In-progress tickets may
    be listed; their state does not change.
  - `Raised`: date and who raised it.
  - `Recommended`: the short name of one route, exactly as its heading spells it.
- **Body** (in the project's prose language): what is being decided, in plain words
  (the observation, why it needs the user, what happens if nobody decides); at most
  three routes, each a `### A. <short name>` heading followed by how it works, its
  cost and consequences, and whether it changes a decision or the spec; why the
  recommendation; the exact revision wording when the recommended route changes a
  decision or the spec; evidence (unmerged evidence as `<branch>:<path>` in code
  format until it is merged); the user's answer (date, chosen route, verbatim words);
  and Comments for the lifecycle.
- **The user decides direction, not parameters.** Explain in prose first, numbers
  after; propose defaults marked as to be validated instead of asking for values.
- **Approving a long job is not a review.** Approval commits the machine's time,
  which the user also plans other work around; a human review gate confirms a
  result. They are never one question: a passed gate does not approve a launch,
  and an approved launch does not stand for a review. The dispatcher tooling may
  let the user pre-authorize launches for a time window or until the user
  revokes it; gates still stop.
- **Blocking stays in ticket files.** Set each affected not-started ticket to
  `needs-info` and append a Comment linking the question. When the question resolves,
  restore the ready role and append a release Comment naming it. The board
  cross-checks: a ready, not-started ticket still listed by an unresolved question, or
  by a question that fails to parse, stays off the frontier with a warning; a
  `needs-info` ticket whose listing questions are all closed gets a warning.
- **Decision revisions:** a route that changes an approved decision or the
  spec carries its exact wording: the new text of each affected spec clause and
  a one-line list of the unfinished tickets it falsifies. Choosing that route is
  the approval (`decision-tickets.md`, "Sign-off before anything leaves the
  ticket"). Record the answer, move the question to `applying`, apply the
  wording to the spec and those tickets only, telling the executor of an
  in-progress one, then resolve the question and release the tickets. For
  another spec-changing route or an answer in the user's own words, draft that
  wording, say in one line what it touches and apply it on their go-ahead;
  return to `drafting` only when the direction is unclear.
- `needs-info` without a question remains valid, for example during triage.

## Claim, complete, fail and hand off

1. Read the ticket, applicable spec clauses and actual prerequisite artifacts, plus
   each prerequisite ticket's `未安排人审：` lines and the values its completion
   record marks to be validated (待验证). Verify eligibility and record the claim
   before implementation, then implement in the ticket's worktree (see Execution
   in linked worktrees).
2. Execute acceptance checks, retaining inputs, versions and reproducible evidence.
   Perform the applicable tests and commit requirements, then an independent code
   review: run the code-review skill on the ticket branch against its base, so two
   separate sub-agents check the diff against the documented coding standards (with
   the skill's smell baseline) and against the ticket and its spec clauses, without
   seeing how the work was done. Fix standards violations and spec findings and
   rerun the tests; a smell may be declined with a reason in the completion record.
   Do not review again after the fixes. Keep the review reports under
   `evidence/<NN>/`. A human review gate at the end of the ticket comes after these
   fixes and any regeneration they require (review-planning.md, Where and when the
   review sits). All of these remain in-progress; there is no separate
   awaiting-acceptance stage.
3. Write the completion explanation with observed behavior, commands/results,
   artifact or commit references, limitations and validation-item outcomes; for a
   human review gate, the reviewed version (commit or artifact hash) and whether the
   result changed materially afterwards. Do not present unexecuted checks as passed.
4. Set `Progress: done` only after this ticket's requirements are satisfied. Do not
   invent a universal human sign-off, but honor human review gates
   (`人审闸（停在 X 之前）：`) and explicit calibration gates in the spec or ticket.
5. A contributing ticket records which ticket closes the full validation contract;
   passing a local part is not passing the whole. A closure ticket lacking required
   evidence is not complete merely because it produced a report.
6. Failure/interruption retains causes and resume instructions.
7. **Release** returns a started ticket to not-started, so it comes back to the
   frontier once it is eligible again. It works the same whichever side manages
   the ticket; only the way its current executor is stopped differs.
   - **When:** work cannot continue until other tickets finish, typically because
     a change added a prerequisite to the started ticket, or its executor hands it
     back unfinished. A change that adds a prerequisite to a started ticket
     releases it in that change, unless whoever manages the ticket records in
     Comments that work can still progress meanwhile; the board's
     started-before-prerequisites warning then remains the reminder. If the
     executor is still working, the change tells whoever manages the ticket
     instead, and the ticket is released once the executor has stopped.
   - **Before:** confirm the current executor has stopped. Ask the user how to
     treat uncommitted changes in the ticket's worktree (keep, commit as WIP,
     discard). Stop the ticket's running jobs, or keep them running and record
     them for the handoff.
   - **Record** a handoff Comment: why (with the user's words when the user asked
     for it), the claim being cleared, the worktree and branch, what is done and
     what comes next, what is kept and where, and any job left running.
   - **Change** only the claim (removed) and `Progress: not-started`. Keep the
     triage role, the worktree and the branch; the next executor continues on them
     (see Execution in linked worktrees).
   - **Verify** on the board that the ticket is no longer in progress, carries no
     new integrity warning, and is either blocked by unfinished prerequisites or
     back on the frontier.

Checkboxes index evidence; they do not let the board verify quality. Integrity
checks expose inconsistent records without replacing testing or required review.

## Completion artifacts

Keep only what someone still needs; everything else is temporary.

- **Keep** what the product needs (code, tests, configs, pinned records such as
  frozen manifests), what later tickets consume (checkpoints, generated data), and
  what proves the result (evidence under `evidence/<NN>/`, including the scripts that
  produced it or a deliverable). Record identity — a full-length hash or a
  verification command — for kept artifacts and for external inputs the ticket read;
  read inputs from stable locations, not from caches that may be rebuilt.
- **Place** kept items in Git by default, even when regenerable. Large binaries and
  caches go to a project-designated ignored location; privacy- or licence-restricted
  files stay outside the working tree with restrictive permissions, recorded by path
  and verification route only.
- **Document** where readers look when they need it: module usage and run advice in
  the module's own docs, test purpose and requirements in the test file's header,
  a ticket's history in its completion explanation. Every session loads the project
  instruction file (AGENTS.md / CLAUDE.md), so add to it only rules needed before
  acting, one map line for a new module, or project facts the code cannot show; do
  not append per-ticket module, test or history narratives there.
- **Temporary** is everything else, wherever it lives: repository, shared data
  reached through links, session scratch. Never cite it; delete sensitive items at
  completion or once the user confirms, noting any still pending.
- Evidence identifies the code it ran (commits, or blob ids for uncommitted code in a
  shared checkout) and, for test runs, the working-tree state. It carries no
  sensitive content; commit summaries or hashes instead.
- Before `done`, check `git status --porcelain --ignored`, confirm every cited file
  is tracked, and state what was written to shared locations. The implementation
  store is the validation ledger; it outlives the effort.

## Execution in linked worktrees

Every implementation ticket runs in its own linked `git worktree` checkout, whoever
executes it and whether or not other work runs at the same time. Ticket state still
changes only in the tracker checkout (on the branch whose store the board reads,
normally the primary checkout). The executing session performs the tracker-side
steps itself, before entering and after leaving its worktree; only if it cannot
reach the tracker checkout does the user or a session there perform them. A ticket
runs in the tracker checkout instead only when the project instruction file says so
with its reason, or the user directs it for that ticket.

- **Identity:** the ticket's branch is `impl/<ticket file stem>`. Its worktree sits
  beside the tracker checkout as `<repository directory>-<ticket file stem>`, unless
  the project instruction file designates another location.
- **Base:** cut the branch from the tip of the branch the ticket's code lands on —
  the tracker branch, or the shared integration branch of an expand–contract batch —
  and name it explicitly: `git worktree add <path> -b impl/<stem> <base>`. Without
  it, git branches from whatever HEAD the session happens to sit on.
- **Starting point:** the session may start anywhere. When the ticket's worktree or
  branch already exists (`git worktree list`, `git branch --list 'impl/*'` in the
  tracker checkout), continue on it; otherwise create it. A worktree on any other branch — another ticket's, or one a tool
  created for the session — stays untouched and unadopted. When the session cannot
  move its working directory into the ticket's worktree, address it by absolute path
  in every command (`git -C <worktree>`, `cd <worktree> && …`).
- **Provisioning:** supply ignored resources (data, dependencies, build products,
  local configuration) by the project's worktree preparation instructions. Without
  them, find and supply what the run needs, then propose recording the list in the
  project instruction file.

1. **Claim** in the tracker checkout, committing only the ticket file:
   `Claimed: YYYY-MM-DD <executor> @ worktree <branch>`. The board shows it
   verbatim; put notes in Comments, not after the branch. Where the personal
   `parallel-tickets` dispatcher is installed (`~/.agents/skills/parallel-tickets/`),
   every session executing an agent-role ticket, dispatched or not, claims, stops
   and resumes by its `references/ticket-agent.md`. The dispatcher leaves a claim or
   stop written in any other form alone as an anomaly, so a ticket left waiting for
   the user would not be resumed after the answer.
2. **Work** in the worktree. Its branch commits code and evidence, never ticket
   or question files; revert any copy of them edited there. Its store copy is stale
   by design: read tickets, questions, the board and these rules from the tracker
   checkout, and
   never replace the store with a symlink (git then treats its tracked files as
   deleted).
3. **Settle artifacts before leaving** (see Completion artifacts). Removing a
   worktree silently deletes its ignored files, so commit whatever is kept or
   cited, even if ignored.
4. **Merge the base branch in**, resolve conflicts and rerun the suite.
5. **Review**: run the independent code review and apply its fixes (Claim,
   complete, fail and hand off, step 2). If the ticket ends with a human review
   gate, stop for it now, on the fixed version.
6. **Leave the worktree, keeping it.** In the checkout holding the base branch (the
   tracker checkout for the tracker branch) merge back with `--no-ff`, never squash
   or rebase: evidence pins commit ids and the completion record cites the merge
   commit. If the merged tree differs from the tested one
   (`git diff --quiet <tested> HEAD` fails), rerun the suite.
7. **Record completion**, and only then set `Progress: done`, so successors are
   not released before their prerequisite code is reachable.
8. **Remove the worktree** from the tracker checkout: links as links, any ignore
   entry added for it, then `git branch -d`.

Worktrees isolate code only: interfaces, data reached through links and compute stay
shared, so check them before simultaneous work. Sessions sharing one checkout stage
by explicit path, check the staged diff, stop processes only by recorded PID, and
never stash or commit another session's uncommitted changes; if they block a merge,
wait.

This defines where each executor works and where ticket state lives; it does not add
remote PR handling or orchestration across executors.

## Board and distribution boundaries

Ticket state belongs only in ticket files; question files explain decisions and
record answers, but do not replace ticket state. Label mappings are interpretation rules;
spec/evidence links are references; maps, overviews and generated manifests are not
state authorities. The board is read-only. Layout, colors, sorting and refresh
belong in its design, without a separate definition of done or dependency semantics.

Distribute these rules through `customize-issue-tracker`, preserving documented
project differences. Rule installation does not modify official plugin caches,
unrelated projects, models or existing ticket artifacts.
