# plumb version 2: the owner's principles (draft)

Drafted from `v2-dump.json` and `v2-clusters.json` for the owner to confirm. Each principle, once confirmed, settles the behaviours of the clusters it governs; "Would settle" names the decisions still awaiting and the clusters whose members contradict each other. Quotes are the owner's own words, verbatim from the INT records' quote fields. Order runs from what plumb is to the most specific (hooks, hosts).

14 principles cover all 41 clusters (C0 to C40, numbered in `v2-clusters.json` order); each cluster sits under exactly one principle. The one-off records follow the cluster they go under.

## P1. plumb exists to keep what the owner means and what is being built in step, and it catches drift while the work happens, not afterwards.

**In the owner's words**

- "the goal of coherence tooling is to ensure the alignment between user's intent and understanding of what he wants to build and the current state of the system being built." (INT-001, confirmed)
- "Plumb should fix those problems during the design/development instead of afterwards." (INT-058, awaiting)
- "stale detection should also be a hook and be resolved as soon as possible" (INT-027, confirmed)

**Governs**

- C4: Plumb catches stale links and untested changes in the turn that makes them, repins silently when covering tests pass and a judgment says the meaning is kept, and goes to the owner only when meaning may have changed.
- C16: A changed source path that no requirement owns is read back with a judge-proposed owning requirement, never a written link, using one shared definition of source code.

**Would settle**

- DEC-061 (awaiting): when code or tests linked to a confirmed requirement change, is the owner asked by default, or never unless the requirement should change fundamentally?
- DEC-066 (awaiting, in no cluster): how the links left stale from before the drift gate are cleared in one baseline pass.
- C4 members disagree: SR-111 and SR-113 (proposed) send a changed meaning to the owner at the edit, while SR-175 (proposed) checks coverage and repins first.
- C16: SR-026 (proposed) puts an unowned change to the owner, SR-044 (confirmed) only proposes an owner requirement; which one reaches the owner.

## P2. The agent, with plumb, is the owner's interface to the system: the owner speaks plain words and never needs shell commands or plumb's internals.

**In the owner's words**

- "the agent and plumb is the interface for the User to interact with the system" (INT-024, confirmed)
- "I dont want to have to know those uv run commands" (INT-023, confirmed)
- "It should never assume the user understands internals of the system." (INT-023, confirmed)
- "don't forget the user don't necessarily know the code" (INT-016, confirmed)

**Governs**

- C26: The owner reaches every plumb capability through /plumb in plain words and is answered in the owner's terms, naming no shell command, while internal mechanisms stay internal.

**Would settle**

- C26: SR-064, SR-033 and SR-122 are still proposed while SR-088 and SR-089 are confirmed; the principle settles that every owner command takes plain words and answers in the owner's terms.

## P3. Only the owner decides, and only words plumb itself saw from the owner count: never the agent's relay, another session, a notification or a hook.

**In the owner's words**

- "we should have a mechanism that prevents what can go wrong." (INT-059, awaiting)
- "use agents that verify that my intent based on that conversation is respected." (INT-012, confirmed)

**Governs**

- C6: A confirmation pins the exact content confirmed, so any later edit, a changed acceptance test included, leaves the record an unconfirmed edit awaiting the owner.
- C7: Only the owner confirms a record: a typed command handled by the prompt hook, a secret-proved button press, or the owner's own words read by plumb; never the agent's relay or words from other sessions, notifications or hooks.
- C28: A conflict is answered only by the owner, on its card, by typed choose or by a chat reply that clearly picks one version, and the agent may recommend a resolution shown first.

**Would settle**

- DEC-057 (awaiting): what counts as the owner's answer (a card press, a typed /plumb command, the owner's message read by plumb).
- DEC-067 (awaiting): every edit to a confirmed record is reconfirmed, asked once per principle.
- DEC-051 (awaiting): a merge conflict is answered on its card, or in chat read by plumb.
- C28 members disagree: SR-150 (a conflict is answered on its card) against SR-170 (a chat answer read by plumb also counts).
- C7 against C8: SR-005 ("only the owner's explicit words") against a reader model that takes meaning, not wording (INT-028).

## P4. plumb understands what the owner means with language models, not fixed word rules, and takes the clear part of an answer without asking again.

**In the owner's words**

- "most of the time the system shouldn't rely on deterministic tooling to understand intent or process text, unless we're sure the deterministic solution can handle any type of situation." (INT-029, confirmed)
- "this whole approval workflow should not rely on specific wording but understand user's approval or denial directly from the prompt semantic or through the mods UI buttons." (INT-028, confirmed)
- "When a user clearly answers to a specific question, that should be logged as an intent without having to have a new card created and re-asked the same question." (INT-057, confirmed)
- "It should be able to understand that." (INT-035, confirmed)

**Governs**

- C8: A reader model independent of the coding agent reads the owner's whole message against the records shown and returns accepted, rejected, change asked or open for each, applying the clear part and asking again only the unclear part.
- C9: A short owner answer, typed or through the question tool, is logged with the question it answered, judged together with it, closes its card and raises no new card, but never confirms a record by itself.

**Would settle**

- DEC-070 (awaiting): a message that does only part of what the reader looks for: the clear part is applied, only the rest is asked.
- C8: SR-101, SR-098, SR-096 and SR-187 are proposed beside confirmed SR-130 and SR-090; the principle settles the reader's outcomes as a whole.
- C9: SR-091 (proposed, a bare "yes" remembers what it answered) follows from SR-097 once the principle holds.

## P5. plumb asks the owner only about intent and trade-offs, at the level of the principle, and resolves from the recorded intent everything that intent already answers.

**In the owner's words**

- "only question user for intent/tradeoffs related problems" (INT-023, confirmed)
- "So that the user gives highlevel decisions that convert into lower level card answers." (INT-061, awaiting)
- "plumb tools should always look at the available intent to be able to try resolve issues before presenting them to the user." (INT-070, awaiting)
- "I shouldnt have to ask for those clean up resolutions, they should be cleaned up automatically at the relevant moment." (INT-056, awaiting)
- "should only track cards related to the system under development in itself" (INT-046, confirmed)

**Governs**

- C23: A card lives only while its question stands: plumb withdraws cards replaced, merged, answered by confirmed records or duplicated, logging each, and settles cards that hinge on one principle from the owner's answer to that principle.

**Would settle**

- DEC-067 (awaiting): reconfirmation asked once per principle with the derived records listed, never one card per record.
- C23: SR-172 and SR-162 (proposed) let a confirmed principle withdraw, repin and reword detailed cards; whether a model may do so, logged and undoable.

## P6. Intent is clarified the way a brainstorming partner would, on the owner's command, with every blocking question asked specifically through the question tool, scaled to the request.

**In the owner's words**

- "claude code should use some kind of brainstorming skill to improve intent capture capability" (INT-018, awaiting)
- "Clarify should ask specific questions that clarify the intent to make the intent clear for the next steps." (INT-068, awaiting)
- "use commands like clarify and other commands to make it clear that the intent should analysed and when a message shouldn't be analysed" (INT-060, awaiting)
- "how do you ensure that people defining their system will have their intent succesfully translated?" (INT-004, confirmed)

**Governs**

- C20: The clarifier reads a request with the last reply, recent messages and repository facts, acts only on requests that change the system being built, turns recommendable options into flippable assumptions, and asks every blocking question, specific, through the question tool, keeping cards for complex record-changing decisions.
- C18: Typing /plumb intent opens one intent loop that clarifies through the question tool, checks answers against confirmed records and passes one judge gate, each stage refusing to run until the previous gate passed.
- C17: Outside the intent loop the edit gate closes only when a request or edit would contradict or extend a confirmed record, judged against its confirmed examples; the gate is keyed by session and prompt and cannot be switched off by accident.
- C11: Big requests are handled as a set: plumb suggests an up-front spec once, checks and repairs a big plan before offering it, triages proposed records by faithfulness, and the owner approves a set or group in one step.

**Would settle**

- DEC-072 (awaiting): all blocking questions, specific, through the question tool.
- DEC-079, DEC-080, DEC-081, DEC-082 (awaiting): the intent loop runs on /plumb intent, as one loop with one judge gate, each stage refusing to run without the previous stage's gate.
- C18 against C17 and C20: SR-171 (a request is analysed only on /plumb clarify) against SR-010 and SR-196 (every prompt gets an intent-change flag and the edit gate closes on one) and SR-128 (every request is read with its conversation).
- C20 members disagree: SR-167 (a record-changing question always has a card) against SR-157 (the question tool by default, a card only for a complex decision).

## P7. The records are the owner's intent written down: few, one durable observable behaviour per requirement, hashed so a change of meaning shows, and never lost, only retired with a trail.

**In the owner's words**

- "I fear that there are actually many duplicates, or that the actual definition of an SR is actually blur currently in the plumb project." (INT-073, awaiting)
- "the hash is important for staleness detection." (INT-006, confirmed)
- "think of re-using the existing artifacts no? SRs FEATs..?" (INT-010, confirmed)

**Governs**

- C3: A requirement states one durable observable behaviour; a superseded record is retired with its history kept, its examples' tests unlinked, and it no longer reaches the owner or is checked for staleness.
- C0: Plumb keeps every record as a Markdown file identified by its frontmatter id, with a hash that changes only when the record's meaning changes.
- C1: Links pin the hash of both ends, go stale when an end moves, and are removed or repointed only through logged unlink and relink commands.
- C2: Plumb's log is append-only: one never-edited, hash-chained file per entry, with tampering reported.
- C21: Capture writes a read-back as proposed intent, requirement and decision records with pinned links in one call and names the existing requirements the new intent changes; decisions keep their alternatives and change only by a superseding decision.
- C5: Plumb imports pi-agent-factory's records read-only and idempotently, as proposed unless an upstream human consent pins their current content.

**Would settle**

- DEC-083, DEC-084 (awaiting): the version 2 rebuild, and what a requirement is.
- DEC-065, DEC-088 (awaiting): a retired example keeps no test; a newer decision wins over an older example's test.
- DEC-048, DEC-049 (awaiting): link numbers after a removal, and who may unlink or relink.
- C0, C1, C2: SR-002, SR-003, SR-006 and SR-073 are still proposed although they are the base contract their confirmed siblings rely on.

## P8. An independent judge checks every new or changed record against the owner's whole logged words, and when no judge is reachable plumb says so and holds rather than deciding by rule.

**In the owner's words**

- "I think it might be usefull to integrate it in this new version too?" (INT-011, confirmed)
- "Calibrating JEV might be perturbed by wrong intent capture, no?" (INT-025, confirmed)
- "unless we're sure the deterministic solution can handle any type of situation." (INT-029, confirmed)

**Governs**

- C13: An independent judge decides whether each new or changed record is supported by the owner's whole logged words, wherever plumb runs, marks a quote-only premise, and anything beyond or against those words reaches the owner as one line on the request's read-back card.
- C14: Verdicts come from a cascade, JEV first above its calibrated no-false-accept threshold, else the configured judge model, whose backend, credential, output form and model are settings; with no judge reachable plumb says so once, holds the steps needing one and decides nothing by rule.
- C15: Plumb judges code against a requirement on a scoped fidelity packet, edge by edge weakest first, advisory only, escalating low-confidence judgments to the host agent and listing unjudged touched requirements at the merge.

**Would settle**

- DEC-055, DEC-056 (awaiting): Sonnet as a judge option; JEV's choice output kept as a configuration.
- DEC-060, DEC-064, DEC-068, DEC-069 (awaiting): no judge reachable, the cascade, partly answered judge jobs, judge_model as the one setting.
- DEC-074 (awaiting): a worktree reads the owner's words from the main checkout's log.
- C14 members disagree: SR-114 (the repin check names Sonnet) against SR-186 (everything about verdicts follows judge_model).
- C14 against C15: SR-021 (judgment has no fallback) against SR-024 (low-confidence judgments go to the host agent).

## P9. Approval without the owner's words is narrow: off until the owner switches it on, calibrated on the owner's own answers, never for an intent, marked and reversible.

**In the owner's words**

- "there should be a command for that" (INT-017, confirmed)
- "Switch on the automatic approval if possible." (INT-032, confirmed)
- "remember that it should maximize reliability and minimize human intervention." (INT-023, confirmed)
- "Calibrating JEV might be perturbed by wrong intent capture, no?" (INT-025, confirmed)

**Governs**

- C10: Auto-approval is off by default and switched only by the owner's typed command; when on and calibrated, the judge's supported verdict on verified owner words may confirm requirements and decisions, never intents, marked and reversible, and nothing settles by context.
- C12: The judge is calibrated on the owner's own yes/no answers to trial cards, at most three open, each the read-back of one record with its source words, before it may auto-approve.

**Would settle**

- DEC-073 (awaiting): a judge model's verdict may confirm requirements and decisions, never intents.
- DEC-089 (awaiting): a refused automatic approval is an error or a warning at the merge.
- C10 members disagree: SR-117 (confirmed: project context settles the clearly safe requirements) against the cluster's "nothing settles by context" and SR-134 (one judge path).
- C12: SR-106 (proposed: settling starts with a trial) against SR-042 (confirmed: calibration before any auto-approval) on which comes first.

## P10. Work is done only when it is shown working the way the owner said they would see it, checked by targeted tests rather than the full suite.

**In the owner's words**

- "we need claude code and plumb to actually show the user it is working" (INT-034, confirmed)
- "at the end proove by showing the browser automatically" (INT-062, awaiting)
- "I'd rather not run plumb test full if possible and only perform targeted validation as much as possible" (INT-027, confirmed)

**Governs**

- C19: Every requirement carries the proof the owner stated, how they will see it working, and plumb names requirements not yet shown working before a merge without blocking it.
- C32: A merge is never green while an affected acceptance test lacks a passing run on the current identity: evidence is pinned and reused only on an exact match, a previously passing test that fails is a regression, and a same-tree flake is recorded as flaky.
- C33: For a turn's changed files plumb selects covering tests from a grep-able test map, by the functions each test executed plus the requirement's linked tests, within a time budget.

**Would settle**

- C19 against C32: requirements not yet shown working are named "without blocking" the merge, while a merge is never green without a passing acceptance run; which one holds the merge.
- SR-197, SR-020, SR-017 (proposed): the owner-stated proof, the regression rule, the per-turn test budget.

## P11. Parallel work runs by awareness, not locks, and the merge is the one place where unconfirmed or conflicting intent is held for the owner.

**In the owner's words**

- "We should always work from a clean or managed environment." (INT-027, confirmed)
- "it should be possible for the agent to suggest conflict resolutions when confidence is high" (INT-048, confirmed)
- "a lighter, more elegant and interactive way to leverage coherence." (INT-003, confirmed)

**Governs**

- C31: The merge check is one lightweight process, run at pre-push, that holds a merge on unconfirmed or widened touched requirements, undeclared paths, stale links or broken logs, checking commit SR trailers against declared paths.
- C27: Record files merge field by field, a same-field conflict becomes an intent conflict inside the record, and the merge check holds it as one choice card until the owner chooses.
- C29: Record ids never collide across worktrees and clones: new ids are reserved through a shared git ref, merge-fix renumbers colliding incoming ids with their references, and the merge check reports collisions.
- C30: Plumb shares intent in flight as claims, reads other worktrees cheaply and read-only, warns when another branch changes the same record and catches conflicting claims at capture.

**Would settle**

- DEC-085 (awaiting): done work lands on the owner's word with per-record holds bypassed and logged, against SR-008 (unconfirmed touched requirements refuse the merge).
- DEC-071, DEC-075 (awaiting): two branch-version conflicts, on SR-184 and SR-182.
- C27: SR-075, SR-076, SR-077 (proposed) field-by-field merge, and the quick check holding conflicts.
- C30: SR-078, SR-080, SR-081 (proposed) claims shared in flight and caught at capture.

## P12. plumb shows the owner little: a small status, one plumb line at turn end, and a card only for a complex decision, complete enough to choose from, with its diagram.

**In the owner's words**

- "a proper way to present the relevant information to the user, but only when it is important." (INT-020, confirmed)
- "Cards are only for complex decisions to make, allowing to see tradeoffs, context presented fully, and allowing the user to really study the pros and cons." (INT-070, awaiting)
- "those mods need to show all the content so that the user choose with all the required elements in mind" (INT-031, confirmed)
- "it should be obvious that it is plumb talking." (INT-049, confirmed)
- "render it cleanly in the cards so that the user gets visual block diagram explanations with the questions asked" (INT-041, confirmed)
- "it should be the same behavior as it is the case now with cards and mods." (INT-055, awaiting)

**Governs**

- C22: Every card is one request's read-back or one choice with one-line consequences, stands alone, is drawn by the one card renderer in the owner's words, and is raised only for real intent changes, unsettled records or regressions.
- C24: Plumb draws a status band, panel and cards inside Claude Code for the owner, connecting reliably or saying why not, while the agent gets the brief and warnings as text and the end of a turn carries one short plumb line.
- C25: The card pane shows one waiting card at a time with its diagram, steps with Back and Next, opens only on click, and groups cards by state with an answered card leaving the waiting list at once.
- C38: Plumb ships the architecture-diagram skill, draws its output as SVG or box text, and a card naming a diagram shows it above its question.
- C39: A local browser workspace lists one project's issues with evidence and diagrams, and its answers queue a follow-up delivered once to the source session, never as an approval; its tests run only on request.
- C40: Long plumb executions report their current step and progress at least once per second, in the terminal and the status line.

**Would settle**

- DEC-059 (awaiting): the agent gets everything as text, the owner sees cards only, the full/compact/off setting retired; SR-062 (confirmed, C22) still promises that setting.
- DEC-087 (awaiting): SR-125 (confirmed: the panel always connects) against SR-173 (proposed); two panel tests fail until it is settled.
- C22 against C20: SR-012 and SR-105 (cards at the end of a turn for what needs the owner) against SR-157 (cards only for complex decisions).
- C38 against INT-039: SR-141 (plumb ships the diagram skill) against the owner's "should be put out of plumb".
- DEC-053 (awaiting) with INT-054: whether the browser workspace gets its own resolving coding agent.

## P13. plumb stays light: it never blocks the owner's work on its own failure, keeps the agent's context small, and runs its model work in the background within time limits the owner can set.

**In the owner's words**

- "they seem pretty heavy" (INT-003, confirmed)
- "Isnt the risk to bloat the context way too fast with redundant tokens?" (INT-016, confirmed)
- "Also increase the timeout for all hooks" (INT-072, awaiting)
- "Why are there still windows spawning during executions?" (INT-071, awaiting)
- "There should be a progress bar indicating the progress of long executions with a message indicating what's going on" (INT-030, confirmed)

**Governs**

- C34: Hooks finish within configurable time limits, never block work when plumb fails, push model work to batched background jobs, and on Windows spawn no console window.
- C35: The agent's context is a short session brief of about 30 lines plus only relevant, new records, passed through one emitter that deduplicates and enforces a token budget.

**Would settle**

- DEC-078 (awaiting, supersedes DEC-009) against DEC-063 (awaiting): hook limits of 30 s / 20 s, or 6 s / 4 s.
- DEC-077 (awaiting): the Windows creation flags of background processes.
- C34: SR-014 (hooks stay within their budgets) and SR-181 (limits are settings that survive a loaded machine) are both proposed; which budget is the contract.

## P14. plumb works in any repository and for any coding agent, through one host-neutral core with thin adapters, installed as a Claude Code plugin.

**In the owner's words**

- "I guess the CLI / lib can be re-used from pi-agent-factory?" (INT-007, confirmed)
- "Make plumb a plugin that you can install using claude code so that then all commands are built in" (INT-023, confirmed)
- "Would be nice to dogfood the version to itself as soon as possible and build with it." (INT-009, confirmed)

**Governs**

- C36: Plumb installs as a Claude Code plugin running its own private copy of its tools; init adopts a repository idempotently, unadopted projects stay silent, and old-style setups keep working.
- C37: A host-neutral core serves every host through thin adapters for Codex, Pi and Hermes and a read-only MCP server, preserving the owner's own entries.

**Would settle**

- C37: SR-053 (one host-neutral turn API with a CLI-only fallback) is its only proposed member.
- C36: SR-015 (proposed: an installer writes hooks, status line, guard and commit hook) against SR-082 (confirmed: the plugin runs its own private copy of its tools); which one sets plumb up.
