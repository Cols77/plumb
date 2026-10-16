# plumb version 2: the owner's principles, as answered on 2026-10-16

The owner answered each draft principle through the question tool (session 99dc7575, plumb-b1). Confirmed as written, or reworded from the owner's own answer; the answer is quoted where it changed the principle. These fourteen govern the 41 clusters of `v2-clusters.json`; every v2 record derives from one of them.

## P1. Drift is caught while the work happens
plumb exists to keep what the owner means and what is being built in step, and it catches drift while the work happens, not afterwards. Confirmed as drafted.

## P2. The agent with plumb is the owner's interface
The owner speaks plain words and never needs shell commands, plumb's internals, or record ids: no owner command takes an id, and the owner is never asked to read what the AI wrote in order to approve it. Confirmed, then sharpened by the owner on 2026-10-16: "I disagree with command plumb approve <IDs>. The user does not keep track of ID. And cards should be resolved only through question clarifications, not by reading what the AI writes."

## P3. Approximate words are formalized, and a validated interpretation counts
The owner's words are approximate, so the agent formalizes them. plumb keeps the owner's sentence with the context it was said in as a pre-intent; the agent rewords it into coherent, formal intent and requirements; a judge (JEV, then a model such as Sonnet or Haiku) validates that interpretation against the owner's words and context, and a validated interpretation is recorded as approved on the owner's behalf, with the trail from pre-intent to formal record kept. The owner is asked only to arbitrate contradictory intent: a trade-off that drops new intent or changes older intent, through the question tool or the browser's study room with its diagrams. There is no owner approval command and no read-back card: whether the records make sense and converge is the AI's judgement (the judge cascade of P9), never the owner's reading. The owner reverses a judge-approved record by saying so in conversation, which plumb reads as an answer (P4).
Owner: "it is important that the agent rewords my intent into something coherent and formalized ... I think it is fine if the agent writes my approvals as long as the agent's interpretation of my intent is somewhat validated by a judge like JEV and Sonnet or Haiku. We could record a pre-intent with a set of context elements rather than just one user sentence."

## P4. Intent is captured when given, and rationalized into one coherent set
Intent is captured only when the owner gives it: the /plumb intent command, an answer to an intent conflict, an answer in the question tool, a card press, or a message that answers what the last reply showed. Every captured piece is rationalized against the existing intent into one set that is coherent on its own and between its elements; plumb reads answers by meaning, not wording, and takes the clear part without re-asking. Confirmed reworded.

## P5. Ask only about intent and trade-offs; route what cannot settle to a debug workflow
plumb asks the owner only about intent and trade-offs, at the level of the principle, resolves from the recorded intent everything that intent already answers, and withdraws by itself a card whose question no longer stands. When plumb cannot converge or settle (a bug, missing information), the case is routed to a debug workflow that works out what happened and what is missing, and only in last resort puts questions to the owner to resolve plumb's own issue.
Owner: "there will probably be bugs, or moments where plumb is not able to converge/settle. These situations should be routed to a debug workflow ... and in last resort expose the human some questions".

## P6. Clarification on command, every blocking question through the question tool
Intent is clarified the way a brainstorming partner would, on the owner's command (/plumb intent), with every blocking question asked specifically through the question tool, scaled to the request; outside the loop the edit gate closes only when a request would contradict or extend confirmed intent; big requests are handled as a set approved in one step. Confirmed as drafted. (A question never closes the gate; the 2026-10-16 false positive on DEC-054 is a defect against this principle.)

## P7. Few records, one durable behaviour each, never lost
The records are the owner's intent written down: few, one durable observable behaviour per requirement, hashed so a change of meaning shows, never lost, only retired with a trail; a fix of a stated behaviour goes under its requirement, never as a new one; one intent per principle. Confirmed as drafted.

## P8. An independent judge, and a hold when none is reachable
An independent judge checks every new or changed record against the owner's whole logged words and context: JEV first above its calibrated threshold, else the configured judge model; when no judge is reachable plumb says so and holds the step rather than deciding by rule. Everything about verdicts follows one judge_model setting. Confirmed as drafted.

## P9. The fast track: JEV above 0.9, else Sonnet asks, then JEV again
Approval without the owner's own words rests on the judge's validated interpretation (P3): calibrated on the owner's own answers, marked as judge-approved everywhere, reversible by the owner, switched by the owner, and including intents. The cascade: when JEV's confidence is above 0.9 the record is fast-tracked; otherwise the interpretation is handed to Sonnet, which comes back with a set of question-tool questions so the owner can express the intent further; then JEV judges again, and so on; when Sonnet and/or JEV say the intent is clear enough, the loop moves to the next step.
Owner: "fast track if JEV confidence is >0.9 otherwise offload to Sonnet so that Sonnet comes back with a set of question tools ... Then go through JEV again and so on. If Sonnet AND/OR JEV say intent is clear enough, let's move to next step".

## P10. Done means shown working the way the owner chose
Every requirement carries a proof; the AI researches what the best proof to show would be and recommends one, and the owner has the final say on what the proof is. Done and the merge refuse without the proof's evidence; verification is by targeted covering tests rather than the full suite, and a merge is never green while an affected acceptance test lacks a passing run.
Owner: "the proof should be specified at some stage by the user. The AI could research what would be the best proof to show to the user and recommend one. But the user has the final answer on what should be the proof".

## P11. Parallel work by awareness; the merge is the one hold
Intent in flight is shared, record files merge field by field, a same-field conflict becomes one intent conflict the owner arbitrates, ids never collide, and the merge boundary is the one place where unconfirmed or conflicting intent is held. Confirmed as drafted.

## P12. plumb shows the owner little
A small status with progress, one plumb line at turn end, and questions: a contradiction to arbitrate comes as a question through the question tool, or in the browser study room with its diagrams when there is more to study. Cards as a thing the owner reads and presses are retired; the agent gets everything as text. Confirmed, then sharpened by the owner's 2026-10-16 words quoted under P2.

## P13. plumb runs in the background with generous limits and visible progress
plumb's model work runs in the background within time limits the owner can set, and those limits may be larger than today's (the owner: "the watchdogs can be bigger than that ... it could be a bit more heavier"); long work shows a progress bar through a small mod with an animation saying what plumb is doing; background processes spawn no window. Dropped from the draft: "keeps the agent's context small" and "never blocks the owner's work on its own failure" are not requirements of the owner's ("Not sure those are requirements").

## P14. Any repository, any coding agent, each host installs only its own things
One host-neutral core with thin adapters; the Claude Code plugin installs only the Claude Code related things, and the Codex, Pi and Hermes adapters likewise install only their own; plumb adopts a repository idempotently, stays silent where not adopted, and builds itself with itself.
Owner: "claude code plugin should only install the claude code related things. Same for Codex and other coding agents. Otherwise yes agreed."

## P15. plumb keeps the repository fit
What the records say is the only specification: documents a record set supersedes go; log entries older than the records they served are compacted into one archive segment per kind that validate still chains but a session start never reads; working files of a rewrite are removed when it lands; a tidy job at the merge keeps it so. Added on 2026-10-16 from the owner's question "We might have a lot of garbage now that rationalisation is on going, what do you reckon?" and their answer: yes to the principle, and for the v2 landing: delete the sub-project specs and plans of sub-projects 1 to 8 and followups.md, compact the logs, remove the v2 working files and the pruned-worktree archive after landing.

## Addendum to P5, from the same message
"Only the AI considers whether its context make sense, converges or not": convergence is judged by plumb's judges and the agent, never by the owner reading records; the owner only answers questions.
