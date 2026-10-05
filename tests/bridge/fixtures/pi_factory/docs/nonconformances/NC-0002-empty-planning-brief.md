---
id: NC-0002
title: Guided planning intent.json never populates the brief object
external_ref: null
detected_by: FEAT-018 intent-review-agent
status: corrected
corrected_by: T-106
---

## Symptom

`intent.json`'s materialized `brief` object (`goal`, `scope`, `constraints`, `non_goals`,
`done_when`, `open_questions`) is always emitted as empty arrays by
`coherence.planning.guided_entrypoint`/`coherence.planning.intent`, regardless of how much
capture Q&A a run actually records. Observed independently on two runs: FEAT-013's
`intent.json` and FEAT-018's `intent.json` (this run) both show an all-empty `brief` after
substantial capture content. There is no structured "done" statement anywhere in the intent
document itself; a reader has to manually reconstruct success criteria from scattered answer
text.

Detected during FEAT-018's planning capture, by the read-only intent-review subagent
dispatched per the `/coherence-plan` finalize step (two separate passes both flagged it; see
FEAT-018 capture journal answers a30 and a69).

## Correction

Not yet corrected. This is a backend/tooling gap in the guided planning pipeline
(`coherence.planning.intent`'s replay/materialization logic never derives or writes `brief`
fields from captured answers), not something a single planning run's capture content can fix.
Filed here so a future session addresses it as its own scoped change rather than rediscovering
it during another run's finalize.

## Correction applied

T-106: `append --brief <field>` tags an answer as the goal, scope, a constraint, a
non-goal, or the done criteria; replay copies the tagged answer's text verbatim into that
`brief` field. `/coherence-plan` step 3 tells the host when to tag. Runs captured before
this fix keep an empty brief; their journals are not rewritten.
