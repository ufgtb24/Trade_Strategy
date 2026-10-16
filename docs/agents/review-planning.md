# Review planning for implementation tickets

Read and apply this document once proposed implementation tickets are drafted with
their prerequisites (`Blocked by`), and before they are presented for review,
whether in a breakdown (`to-tickets` or an equivalent workflow) or in a decision
answer that proposes them. The prerequisites must come first: finding a build-on
point (Step 2) follows them. This document settles, ticket by ticket, how each
result will be reviewed, so that the acceptance criteria carry the review and
executors never decide it.
[implementation-tickets.md](implementation-tickets.md) governs everything else
about the tickets.

The user decides direction, not parameters (see User questions there): this
document asks the user only where a wrong choice of review would be expensive, and
fills in the rest from a recommendation the user can still change.

## When the source already says

If the spec, a decision or an approved validation item already specifies how a
result is reviewed, copy it into the ticket and skip the steps below for it. Do
not ask again.

Project rules that force a review regardless of planning, such as a preview before
every long job, still apply. Account for them in the plan instead of planning a
second review of the same thing.

## Step 1: can a machine verify it?

Split each ticket's result into what a machine can verify (tests, metrics against
an approved reference, invariants, comparisons with recorded outputs) and what is
left: whether it is what the user wants, looks real, reads well, feels right. Put
everything quantifiable into machine acceptance. Only the remainder needs a human
review. If nothing remains, the ticket is **tier 1**.

## Step 2: is anything built on it?

A result's **build-on point** is the first later step whose result would have to
be redone, not merely rerun, if this result turned out wrong, and that happens
before the user would otherwise see this result:

- an expensive or irreversible run: a long job, an output generated only once
  (such as a fixed validation set), a release;
- a judgment made from this result's behaviour: a decision, a tuned parameter or
  calibrated threshold, a reference other work is accepted against;
- substantial human effort on it, such as labelling or manual repair.

The step may lie inside the ticket itself (its own long job) or in a successor.
Code that uses the result only through an interface is not a build-on point:
fixing the result behind the same interface leaves that code valid.

Find it by walking downstream from the ticket: the tickets that list it in
`Blocked by`, then theirs, and so on, until the first step that would have to be
redone. A ticket that would only rerun on a corrected result is passed through,
not stopped at. Look beyond the drafted breakdown too: already published tickets,
and work outside tickets that the spec or decisions say will consume the result,
such as jobs the user runs or a release.

Keep the term `build-on point` untranslated in tickets, breakdowns, questions and
other prose in the project's language, so every session uses the same word.

If a later review already shows this result before its build-on point, the
review belongs there; record that instead of planning another one.

- Human review needed and no build-on point: **tier 2**.
- Human review needed and a build-on point exists: **tier 3**.

## Tiers

Tiers run from least to most constraining: the higher the tier, the more the user
is involved and the earlier work waits for them.

| Tier | At breakdown | In the ticket |
| --- | --- | --- |
| 1: machine-verifiable | Listed; confirmed by the round's single summary question | Machine acceptance criteria |
| 2: human review, not built on | Recommendation written in; confirmed by the same summary question | A post-completion review that does not block successors |
| 3: human review, built on | One question per ticket, with a recommendation | A review gate before the build-on point |

## Make sure a gate holds

A tier-3 gate placed in an upstream ticket, before it is done, holds the build-on
point back only through prerequisites: the ticket containing the build-on point
waits because it lists the upstream ticket, directly or through others, in
`Blocked by`. Check that it does. If it does not, add the missing prerequisite
when it reflects a real technical dependency; otherwise move the gate into that
ticket, just before its build-on step.

## The recommendation

Write one for every tier-2 and tier-3 ticket, choosing the method from the
ticket's content rather than from a fixed list:

- **What the review covers**: what machines check, what is left for the user, in
  one or two sentences.
- **Method**: how the user judges the remainder, for example inspecting rendered
  samples, trying the interface, reading output excerpts, listening, or comparing
  with real or reference cases side by side.
- **Timing**: where the review sits. For tier 3, before the build-on step, and in
  the ticket where the method is iterated, so that a failed review is fixed there
  rather than handed back from a ticket that cannot change it. Name the build-on
  point it protects.
- **Samples**: picked by machine, not at random: the most suspicious by the
  metrics (extremes, values near thresholds, failures), two or three typical
  ones, at least one per category, within a size the user can review in one
  sitting. Each sample is labelled so the user can point at it.
- **Outcome handling**: what a pass approves (at a gate before a long job, the
  launch as well); on failure, fix within the ticket and review again, or return
  to the decision process if the fix changes an interface or an approved decision.
- **Alternatives**: one or two other methods or timings with their cost, such as
  reviewing after completion instead of gating, or merging into a later gate.

## Asking the user

Ask in the round where the proposed tickets are reviewed, not in a separate round.
Use the interactive question tool (AskUserQuestion in Claude Code): the
recommended option first, labelled as recommended, then at most two alternatives
and a "decide later" option; free-form answers go through the tool's own "Other".
It takes at most four questions per call, so split larger rounds into several
calls, keeping tickets that share a build-on point together.

- **Tier 3: one question per ticket.** The header names the ticket. The question
  states what machines cannot verify, the build-on point the review protects, and
  the recommended method and timing. The recommended option's description gives
  method, timing and cost; alternatives include downgrading to a
  post-completion review or merging into a later gate. Tier-3 tickets that share
  a build-on point go in the same call, and the question says whether one review
  can cover them.
- **Tiers 1 and 2: one question for the whole round.** The breakdown first lists
  every tier-1 and tier-2 ticket on one line each: ticket, tier, review method,
  and for tier 2 why it has no build-on point. One question in the last call then
  confirms them: "apply tiers 1 and 2 as listed" (recommended), or "change some"
  with ticket numbers and changes written in "Other", most often moving a tier-2
  ticket to tier 3. If the breakdown itself is approved through the question
  tool, fold this into that question instead of asking separately.

## Writing it into the ticket

Executors stop only where the acceptance criteria name a review, so write it there,
in the project's prose language:

- **Tier 1**: the machine checks, as ordinary acceptance criteria.
- **Tier 2**: an acceptance item naming the post-completion review: method and
  samples, stating that it does not block successors. The executor prepares it,
  completes the ticket and flags the result for review.
- **Tier 3**: an acceptance item naming the review gate: the step it precedes, what
  is shown and how, how samples are picked, what a pass approves and what happens
  on failure. The executor stops there and asks through a question.
- Record in Comments where the review came from: copied from the source, chosen
  by the user at breakdown, or written from the recommendation.

Reviews that only become apparent during execution follow
implementation-tickets.md: something expensive about to be built on an unreviewed
result stops the ticket as a gap; anything else is flagged for review in the
completion record.
