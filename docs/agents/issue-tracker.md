# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`, on the
current branch. There is no GitHub Issues usage; do not reach for `gh`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at
  `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a
  single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file
  (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a
  `## Comments` heading

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
- **Resolve**: append the answer under an `## Answer` heading that opens with
  the ticket's confirmed direction (see **Ticket framing**), set
  `Status: resolved`, then append a context pointer to the map's Decisions so
  far in `map.md`: one bullet per resolved ticket, shaped
  `- [<title>](issues/<NN>-<slug>.md): <one-line gist>`, the link relative to
  the effort directory. Tooling that reads the map matches on that shape.
  Before closing a prototype ticket, reduce its assets to a minimal reusable
  package: final code, necessary inputs, and representative results supporting
  the decision. Remove redundant or obsolete artifacts, keep regenerable bulk
  output out of Git, and verify the retained package runs independently.
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

## Board

`scripts/wayfinder_board.py` renders an effort's map and tickets as a local
page: `python3 scripts/wayfinder_board.py .scratch/<effort> --serve`, then open
http://127.0.0.1:8765. It re-reads the files on every refresh, so editing
tickets needs no restart; only a change to the script itself does. Ctrl-C stops
it; a detached one is stopped with
`pkill -f '^python3 scripts/wayfinder_board.py'` (the leading `^` keeps the
pattern from matching the shell that runs it). It is also the reference parser
for the shapes above: a ticket or a Decisions so far line the board cannot
parse shows up on the page as missing.

The board treats every `Blocked by` line as permanent topology: resolving a
ticket satisfies an edge but does not hide it. It derives reverse edges by
scanning all tickets, so ticket files do not need a separate dependents field.
Dependency badges use red for predecessors and blue for dependents, with the
ticket number as their only visible content. An unresolved related ticket uses
the full-strength fill, while a resolved related ticket keeps white text on a
more transparent fill of the same hue. The current ticket's status never
changes an edge's direction color or emphasis.

Selecting a ticket also marks its direct neighbors in the tree with an 8px
row-left stripe: red for predecessors and blue for dependents. The stripe is
inset 4px from the row's top and bottom so adjacent tickets stay visually
separate; it is full-strength on an unresolved neighbor and uses a 50% color
mix on a resolved neighbor. Resolved dependency badges also use a 50% fill.
All dependency badge numbers remain
white. The selected item has no
stripe, only its selected background. Compact `前置` / `后续` checkboxes below the map
entry independently control the two stripe directions and persist per effort.
Relation marks are transient, are cleared when another view is selected, and
never expand a collapsed group automatically.

The whole visible ticket row is a pointer target, including its padding, date,
and gaps around badges. A dependency badge keeps priority over that row target
and navigates to the related ticket; the title link remains for keyboard and
modified-click navigation.
