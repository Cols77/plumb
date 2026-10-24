# INT-110: every question asked on the spot, through the agent

Records: INT-110, SR-361 (asked when raised, supersedes SR-334), SR-362 (the agent rewords,
merges and pushes back), SR-363 (no question count at turn end), DEC-340, DEC-341; reworded
SR-223, SR-265, SR-268, SR-295, SR-333, SR-335, SR-336, SR-337.

Proof (all three, post-merge, live session): after the plugin is reloaded from main, a request
makes the judge raise questions; the agent asks them all right away, in plain words and merged
by principle; one that repeats an earlier answer is pushed back and withdrawn (shown in the
log); the turn ends with no "N questions for you" line and the band shows nothing waiting.

## 1. No per-turn limit (SR-361, SR-223)
- `src/plumb/understand/cmd_clarify.py`: remove `ASKED_PER_TURN` and the `room` count in
  `_judged`; `_by_principle` returns every blocking question, then one question per other
  principle, every principle; `mid_task` no longer narrows to blocking ones.
- Tests (`tests/understand/test_clarify_pacing.py`, new): SR-361 EX-1 (five raised mid-task,
  all returned), EX-2 (twelve, eight on two principles: six returned), EX-3 (principle answer
  settles dependents: existing judge test relinked), EX-4 (dismissed question not re-asked in
  a loop; counted by the status card). Remove the SR-334 pacing tests.

## 2. No question count at turn end (SR-363, SR-265, SR-268, SR-295)
- `src/plumb/understand/summary.py` `owner_line`: drop `asks` and `WAITING_KEY`; keep applied
  answers, touched/checks and regression parts.
- Tests: SR-363 EX-1..3; update SR-265 EX-1, SR-268 EX-4, SR-295 EX-1 tests that expect the
  count.

## 3. The agent's wording (SR-362)
- `plumb question reword --covers KEY[,KEY...] --question Q --header H --options JSON`:
  records the agent's wording for the judge questions it covers in the session's question
  store; `clarify --wait --json` keeps returning the judge's text and keys.
- `src/plumb/hosts/claude_code/question_answer.py`: an answer to a registered wording answers
  every covered key (`asked` names each), so the judge re-reads with the owner's words; the
  "missed" check (SR-212) counts a registered wording as matched.
- Tests: SR-362 EX-1 (no id in the asked text; covered keys answered), merge of two keys.

## 4. Push-back to the judge (SR-362)
- `plumb question pushback KEY --reason R`: queues a judge job that reads the question with the
  agent's reason against the owner's logged words and approved records (SR-218's withdrawal);
  the judge withdraws it quoting what answers it, or keeps it; both logged with the reason.
  No command drops a question without the judge.
- Tests: SR-362 EX-2 (withdrawn, quoting the earlier answer), EX-3 (kept, meaning unchanged),
  EX-4 (no path drops a question; the log shows push-back and ruling), with a scripted judge.

## 5. What the agent is told
- The shared "Questions and approval" block (plumb-command, plumb-clarify, plumb-intent,
  plumb-records, plumb-debug templates and `plugin/skills`, claude-md-block): ask every
  question at once; put each in the owner's terms with `plumb question reword`, merging those
  on one principle; push an obvious one back with `plumb question pushback`; never drop,
  answer or default one. Rebuild the plugin bundle (`tests/plugin/test_bundle_fresh.py`).

## Order and coordination
Items 1 and 2 are small and independent; 3 and 4 share the question store; 5 last. INT-109's
lanes (feat/band-red-lines touches the judge's waiting line and the band) run now and hold the
heavy test lock: build in a worktree, run tests under the lock, rebase on their landing.
