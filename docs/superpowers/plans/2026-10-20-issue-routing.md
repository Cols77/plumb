# Issue routing (INT-099): question tool first, paced by principle, studies ahead, no cards

Intent: INT-099. Requirements: SR-333 (question tool first; room on request), SR-334 (backlog by
principle, three per turn), SR-335 (the owner's own words settle), SR-336 (a study ahead of a hard
decision), SR-337 (no cards; Hide stays hidden). Decisions: DEC-283 to DEC-294 (DEC-287 supersedes
DEC-035; DEC-294: the room opens from a brass band line, as a study does). Proof (all five): a live
session on this repository (`iaso proof SR-33x --evidence`).

Branch `intent/issue-routing` from main 9b77b8ee, worktree `C:\coding\iaso-issue-routing`.
Tests in the worktree run with `PYTHONPATH=src`, at most `-n 2`, under `.git/iaso-heavy.lock`;
the mod tests through `python tests/plugin/mod/stand.py`.

The question store (`understand/cardstore.py`, `understand/cards.py`, `mod/offers.py`,
`mod/press.py`, `present/cards.py` labels) stays: the question tool and the study room run on it.
Only the mod's drawing and pressing of cards goes.

## Items

Each item names its acceptance tests (one per example); a test carries `@pytest.mark.sr("SR-3xx")`
or the mod test's title names `SR-3xx EX-n`.

1. **SR-337 band without cards** (plugin). Remove `plugin/hooks/cards.tsx` (move `NOOP` and the `Ui`
   type to register.tsx); in `register.tsx` drop the card parts of `drawBand`, the showall/fewer/
   pane/back/next/press: keys, the pane's card half (the loop pane stays, SR-305), `band.shown`,
   `snap.fresh` and its un-hide (`isHidden: false` at the turn's end); in `iaso.ts` drop `draw`,
   `press`, `drawn` and the card part of `snapshot`. The "N await you" count comes from a new
   `awaiting` field of `.iaso/session/status.json`, written by `hosts/claude_code/snapshot.py` from
   the open questions (judge questions not answered plus open cards). Types and `text.ts` strings
   follow. Tests: band.test.tsx SR-337 EX-1 (two waiting: the line says two, no card or button),
   EX-2 (Hide, then a turn ends with a new question: still hidden), EX-3 (Show draws the line);
   delete cards/states/buttons/trial/diagram tests and the card cases of band/pane tests (the
   removal map in this session's notes), strip card fixtures from fixtures.ts/harness.ts.
2. **Card retirement, Python side.** `mod/cli.py` loses `draw` and `press`; `mod/handshake.py` loses
   the draw content for the panel; `stale.py` says "ask the owner with the question tool" where it
   said "bring it to the owner as a card" (tests/core/test_stale.py, test_edit_check.py,
   test_stale_resolve.py follow); the retired `present.card` setting reads as off. tests/mod card
   draw/press tests deleted; the room's press semantics tests kept (renamed if needed).
3. **SR-333 question tool first.** `cmd_clarify._judged` appends a "Study it in the room" option to
   a question with more to see (a diagram, or evidence over a size limit), inside the 4-option cap.
   `hosts/claude_code/question_answer.handle`: that answer does not rejudge; it writes the judge
   question as a card in the store, marks it waiting in the room and sets a pending-room mark that
   the band draws as a brass line "a question waits in the room"; pressing it opens the room on it
   (DEC-294, same key-gated path as a study, SR-294 EX-2 kept). SR-268's room behaviour (Back/Next,
   groups, blocked when changed) is kept; its tests move to SR-333. Tests: SR-333 EX-1 (short:
   no room option), EX-2 (diagram: the option, the room stays closed), EX-3 (the option chosen: the
   band line, the press opens the room on it), EX-4 (three in the room, Next shows '2 of 3' with the
   diagram), EX-5 (an answer in the room leaves the waiting list).
4. **SR-334 backlog by principle.** The judge schema and `judge._shaped` gain `principle` (a short
   name) and `blocking` (bool). `_judged` groups open questions by principle, asks one per
   principle, at most three per call, blocking ones first and beyond the cap; an answer to a
   principle is passed to the judge with every record of its group (`premise.answers_of` through
   `asked.records`). `summary.owner_line` counts the questions still waiting. Tests: SR-334 EX-1
   (62 waiting, four principles: three asked, the line counts the rest), EX-2 (an answer settles the
   group), EX-3 (a blocking question is asked beyond three), EX-4 (mid-task: none asked; the skill
   text asks between tasks).
5. **SR-335 the owner's own words settle.** `judge._said_in` reads `question-answer` events with
   `via: question-tool` (and typed answers) as the owner's words with their date; `_answered_by`
   and `tidy._settle` count a decision whose `chosen` comes from a logged owner answer, approved or
   not; a decision only the agent wrote still settles nothing. Tests: SR-335 EX-1 (DEC-229's case:
   the question never reaches the owner), EX-2 (an agent-only decision settles nothing), EX-3 (a
   wording that misquotes the answer settles nothing and is one question).
6. **SR-336 a study ahead of a hard decision.** `study candidates` lists the waiting questions'
   topics missing from the picture; `study propose --for <question key>` is allowed outside a loop
   step when it serves waiting questions (still one at a time, never on a known or declined
   topic); `_judged` adds "Study it first" to the questions a proposed or written study serves;
   choosing it marks the study for the band's line, the room opens on the owner's press. Tests:
   SR-336 EX-1 (three questions on an unknown topic: one study proposed, each question offers it),
   EX-2 (chosen: the band line opens the study; the question waits), EX-3 (nothing waits: the
   DEC-207 study path unchanged).
7. **Defects found opening this loop** (each with its regression test):
   a. `intent open` and `clarify --wait` take the newest *commanded* prompt of the session, so a
      later slash command does not lose the loop (`cmd_clarify.latest_prompt`).
   b. `typed.parse` reads `/iaso:iaso-intent <words>` and `/iaso:iaso-clarify <words>` as the
      command (`typed.py`, keep `PREFIX`).
   c. A retyped identical request gets its own check: the prompt's time joins the clarify job's
      `message` input (`clarify.build`, `on_prompt`, `recompute`); `test_same_job_never_runs_twice`
      keeps its meaning for one sending.
   d. `approvals.prompt_origin` logs `<agent-message ...>` and `[Cross-session idle notice]` as
      notifications, not the owner's prompts (tests/host/test_prompt_origin.py SHAPES).
   e. A question-tool answer "Build anyway" to the couldn't-check question releases the gate
      (`question_answer.handle` -> `gate.release(..., "button")`).
8. **Skills.** iaso-records rule 5 and iaso-clarify's card wording name the question tool;
   iaso-intent's "card it when the meaning changed" becomes "ask it with the question tool";
   iaso-clarify asks the couldn't-check question through the question tool with its exact
   labels. Line limits of tests/capture/test_skills.py hold.
9. **Records.** SR-268's room tests are relinked to SR-333 (markers), its pane tests retired with
   the pane's card half (`iaso unlink --note`); SR-267's links to cards.tsx and the card draw test
   move to the files of items 1 and 3; DEC-130, DEC-155 and SR-266 are read for card wording and
   reworded or superseded where they still require cards; `iaso stale` is clean for the new and
   moved links; `iaso repin --after-tests` pins them.

## Order and gates

Items 7 and 2 first (small, unblock the loop and remove the press path), then 1, then 3 to 6 (each
on the store), then 8 and 9. Each item ends with its tests green (`-n 2`, under the lock) and a
commit with an `SR:` trailer. The build ends with the mod stand and the touched Python test files
green, `iaso stale` clean, then the live-session proof for SR-333 to SR-337 and `iaso intent done`.
Handover to iaso-6f, who lands it (main's untracked copies of INT-099, SR-333..337 and
DEC-283..294 are removed at the handover).
