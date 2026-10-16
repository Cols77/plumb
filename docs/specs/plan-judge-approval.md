# Plan: the judge cascade approves v2 records on the owner's behalf

Serves SR-209, SR-248, SR-251, SR-250, SR-252, SR-212, SR-267, SR-210, SR-242, SR-245 and
SR-208, under DEC-140 (no number rule; already in the code, see Review notes), DEC-141 (a judge
model's self-reported confidence is never a bar) and DEC-142 (each record's recommended proof
stands as the plan). Principles: P2, P3, P5, P6, P8, P9 and P12 in
`docs/specs/v2-principles-confirmed.md`.

The owner never types an id and never reads a record to approve it (P2, P12). Every task
reuses the code that exists today: the judge job (`understand/judge.py`), the verdict cascade
(`understand/verdict.py`), the fast-track checks (`capture/autoapprove.py`), the
question-answer hook and the worker's write path. Nothing is rewritten from scratch.

State today: the fast-track switch is on, calibration does not pass (0 real 'no' examples) and
JEV is reachable. JEV is not asked at all today (`_ask_jev` stops at "no calibration"); task 1
makes it score anyway so task 7 can collect labels. Until calibration passes, every record goes
the question route and is approved only by the judge model's `clear` after a round (SR-248;
SR-251: an auto-jev entry needs "a JEV score above 0.9 and the calibrated threshold").

## 1. Target flow

1. Capture writes proposed INT/SR/DEC and queues one judge job. Capture no longer calls JEV.
2. Judge job (worker): it rebuilds each record's premise from the logs: the owner's hook-logged words and the pre-intents (question, options, answer, context).
3. JEV scores every record with a premise and a claim kind, calibrated or not; the score is logged. If the fast track is in effect, the premise is the owner's verified words and the score is strictly above max(0.9, the calibrated threshold), the record is approved `by: auto-jev`. No question is asked.
4. Otherwise the judge model gives a verdict per record, a `clear` flag, and question-tool questions about the owner's intent only (one per principle, recommended option first, the owner's words, no ids).
5. The questions go to a session file only the worker writes. `clarify --wait` answers `ask` and lists them; the agent asks them with AskUserQuestion, verbatim.
6. The owner answers. The PostToolUse hook logs the answer with its question, options and the asked records at their hash, and drops a bare judge job (record ids only). The worker writes the pre-intent.
7. The pre-intent and its question go into the premise, so JEV and the judge model receive the question with the answer.
8. JEV judges again: with a passing calibration and a score above max(0.9, threshold), approved `by: auto-jev` with `answers` cited. Otherwise, when the judge model says `clear`, approved `by: auto-model` (model and confidence logged, never compared), or it asks the next round.
9. Each approval is marked judge-approved and carries its trail (pre-intent, answer and verdict digests). Intents included. A set is approved whole.
10. The turn-end line counts judge approvals. Status, show and brief label them "judge-approved (auto-jev, jev-1.13, 0.96)" or "(auto-model, haiku, 0.8)". An entry below the bar is inert and validate warns.

## 2. Tasks, in order

Each task lists the SR examples it serves, the code it changes, what it deletes, the existing
tests to adapt (found with grep in `tests/`) and its new tests (one per example served). "Kept"
means today's code already serves the example and its named test stays as it is.

### Task 1: One cascade. The fast track moves into the judge job

Serves: SR-248 EX-1, EX-3, EX-6, EX-9; SR-242 EX-1, EX-2, EX-5; SR-250 EX-4 to EX-7; SR-245
EX-3, EX-6. Kept: SR-250 EX-1, EX-2 (`tests/capture/test_typed_auto_approve.py`: `test_ex1_*`,
`test_ex2_agent_running_config_auto_approve_is_refused_and_logs_nothing`; rerun in task 8).

Changes:
- `capture/capture.py`: remove the `autoapprove.gate` call and its `(confirmed by JEV)` line; capture only queues the judge job.
- `understand/verdict.py`:
  - `_ask_jev` no longer returns early on "no calibration" or a form gap; it asks JEV whenever a backend exists (a form gap only means nothing clears).
  - `jev_verdict` scores whenever a claim kind and a premise exist, and returns `{score, clears, judge, model_version, confidence_label, fingerprints, parts, calibration (digest or None), threshold (or None), claim_kind}`. `clears` is True only with a passing same-version calibration and every part strictly above `max(0.9, threshold)` (SR-242 EX-5). With no threshold, `clears` is False and the record goes to the judge model.
  - The verdict entry logs `jev_score` even when it does not clear (task 7). `_premise_text` takes `answers` (task 3).
- `capture/autoapprove.py`: `gate` is deleted. `fast_track(core, record, jev)` decides eligibility and builds the `auto` payload from the `jev_verdict` fields, as `gate` builds it today (`prompt_via: hook`, `parts`, `fingerprints`, `calibration`, `threshold`, `min_confidence`). Checks moved from `gate`:
  - `auto_approve_state(core).effective` (the owner's switch event, a passing same-version calibration);
  - `triage.premise_problem` is None: every quote, examples included, verbatim in a hook-logged prompt (this covers `gate`'s `quote_in_prompt` checks); otherwise the verdict is logged `premise: quote-only`;
  - the `min_confidence` label; not `unconfirmed-edit`, not in `approved_before`, not in an escalated set.

  Dropped on purpose: the decision exclusion (SR-248 names decisions; none fast-tracks until a decision claim kind exists, section 3) and "written in the same capture" (one cascade, SR-242).
- `understand/judge.py` `apply`: a clearing JEV verdict that passes `fast_track` becomes an `approval by: auto-jev` entry carrying `session`; every other record goes to the judge model (task 2).
- `autoapprove.recheck`: strict comparison (`<=` floor is refused); 0.9 stays the minimum of the floor.
- `log.py`: `WORKER_ONLY_BY` gains `auto-jev` (SR-210). `_validate_append` also requires the worker token for kind `pre-intent` (task 6). `pre-intent` stays in the `events` stream, the default of `STREAM_OF_KIND`.
- `judgment/verdict.py`: the docstring and `refusal` say a model verdict approves only after a question round (task 4).

Deleted: `autoapprove.gate`, the capture-time JEV call, and the `escalate`-to-agent call on this
path (SR-242 EX-4; `judgment/cascade.py` stays for its other callers).

Adapt: `tests/capture/test_auto_approve.py`, `tests/understand/test_judge_cascade.py`,
`tests/understand/test_one_judge.py`, `tests/capture/test_escalated_membership.py`,
`tests/capture/test_jev_form.py`, `tests/core/test_no_judge.py`,
`tests/understand/test_judge_waiting.py`, `tests/core/test_log_worker_token.py`. Every test that
logs an `auto-jev` approval by hand wraps it in `as_worker(root, session)` from
`tests/understand/fakes.py`: also `tests/capture/test_relay_grounding.py`,
`tests/importer/test_provenance.py`, `tests/merge/test_glance.py`, `tests/present/test_labels.py`,
`tests/present/test_status_card.py`.

New: `tests/understand/test_cascade_fast_track.py`, one test each:
- SR-248: EX-1 (INT at 0.96, threshold 0.93), EX-3 (0.92 below 0.93), EX-6 (quote-only at 0.97), EX-9 (an owner-answered edit at 0.97);
- SR-242: EX-1, EX-2, EX-5 (equal to the threshold);
- SR-250: EX-4 (config.yaml on, no event), EX-5 and EX-6 (version drift, normalized name), EX-7 (agent edits config.yaml);
- SR-245: EX-3 (key missing: holds, one line), EX-6 (two by JEV, three wait);
- no calibration: JEV is asked, `jev_score` logged, nothing fast-tracked, the record goes to the model;
- an `auto-jev` or `pre-intent` entry written without the worker token is refused.

### Task 2: The judge model returns questions about the owner's intent. No trial card

Serves: SR-248 EX-3, EX-7; SR-252 EX-6; SR-267 EX-4, EX-9; SR-245 EX-7, EX-8, EX-9; SR-209 EX-5.

Changes:
- `understand/schemas/judge.json`: each verdict gains `clear` (bool) and `answer_corrects` (bool, task 7). The answer gains `questions`; each has `question`, `header`, `options` (2 to 4, each `label` and `consequence`: what it does and what it leaves undone, recommended first), `recommended_reason`, `request` (the owner's words and date) and `records` (ids, kept by plumb, never shown).
- `understand/agents/judge.md`:
  - First resolve each record from the recorded intent and the owner's logged words (P5). A record not fast-tracked and with no answered question at its current hash needs a question before it can be approved (SR-248, DEC-141), but one question covers every record that shares a principle: ask the fewest.
  - Ask only about what the owner meant or a contradiction between intents. Never name a record or quote its text: phrase the question about what the owner asked, quoting their dated words.
  - Doubts about the agent's own records (consistency, convergence, tests, links, diff) are never a question (SR-267 EX-9, P5 addendum): the verdict says `waiting` with a reason and the record waits with the waiting line.
  - Confidence is reported and approves nothing by itself (DEC-141).
- `understand/judge.py` `apply`:
  - It validates each question's shape (options, consequences, a reason). A question lacking any waits with the waiting line (SR-245 EX-7).
  - It folds `request` into the question text and `recommended_reason` into the recommended option's description, so AskUserQuestion shows them.
  - It runs `present/owner_text` over every owner-visible field (question, header, labels, descriptions), then sends to the waiting line any question still matching an id or digest pattern or the words proposed, settled, trial, record, judge (SR-267 EX-4).
  - It writes `files.session_dir(root, session)/judge_questions.json`: `[{key, job, records: [{id, hash}], question, header, options}]`, `key` being the normalized question text (lowercase, collapsed whitespace, "(Recommended)" removed). Only the worker writes it.
  - Fragments (records whose words were not found) take the same question route instead of a trial card (SR-248 EX-6).
- `understand/cmd_clarify.py` `wait`:
  - Judge jobs are found by session and kind `judge`, queued after the owner's latest prompt or question-answer entry, whatever their digest (a new `_judge_jobs_since(root, session, at)`; `_jobs_of` stays for clarify jobs, which key on the message digest).
  - The early `ready` (no commanded words, gate open) first checks those judge jobs: while one runs it waits; when `judge_questions.json` holds open questions it answers `ask`. This also holds when no clarify job exists and after an answer with no new prompt.
  - `ask` lines say "ask these N questions with the question tool, one at a time, as given"; `--json` adds `questions`, ready for AskUserQuestion (first option labelled "(Recommended)", consequence as description).
  - Its lines report approvals by title: "approved on your behalf: <title> (judge-approved, auto-jev, 0.96)".
  - The consumers of the outcome state learn `ask`: `cmd_clarify.run` (exit code, lines), `cmd_intent.py` (a `wait` caller) and the skills (task 9); a grep for `Outcome(` and `.state` in `understand/` finds no other.
- `understand/clarify.py` `apply`: the `judge.pending_lines` call (line 640) goes, and the read-back card is no longer built. The gate rule `len(cards) > 1` becomes "a choice card is raised" (the blocking-gap or spec-session card keeps `GATE_REASON_CARD` / `GATE_REASON_ESCALATION`); otherwise `intent_change_hold`, otherwise `gate.open` as today. Judge questions never hold the gate (P6: "A question never closes the gate"). The `early` branch keeps its answered cards.
- `understand/backlog.py` `after_job`: supported records and fragments take the question route. `understand/summary.py`: `trial.top_up` is no longer called.

Deleted: in `judge.apply` the trial `Candidate` list, `trial.cards_for` and `_confirms` (task 4
replaces it); `doubt_line`, `pending_lines`, `_request_card` and their callers. `trial.py` stays:
its `effect` answers a trial card already open, and `answer.py` and `mod/offers.py` use
`_proposal`. A test asserts no trial or read-back card is raised for a record the judge handles.

Adapt: `tests/understand/test_judge_job.py`, `tests/understand/test_backlog.py`,
`tests/mod/test_trial_press.py`, `tests/understand/test_threshold.py`,
`tests/understand/test_e2e_flows.py`, `tests/understand/test_clarify_wait.py`,
`tests/understand/test_judge_model_follows.py`, `tests/understand/test_judge_labelled.py`,
`tests/understand/test_clarify_card_lines.py`, `tests/understand/test_card_shapes.py`,
`tests/understand/test_clarify_job.py`, `tests/understand/test_gate.py`,
`tests/understand/test_gate_digest.py`.

New: `tests/understand/test_judge_questions.py`, one test each:
- SR-248: EX-3 (questions written), EX-7 (linked code, passing tests, consistent model: stays proposed, no settled line);
- SR-252: EX-6 (no trial or read-back card); SR-209: EX-5 (no ok offer, no read-back card in the brief);
- SR-267: EX-4 (ids, digests and "settled" stripped from every visible field, or the question waits); EX-9 (a consistency doubt puts nothing to the owner, the record waits);
- SR-245: EX-7 (out of schema: wait), EX-8 (diff too large: wait, size named), EX-9 (all answered: no line);
- three records sharing one gap give one question; a question carries no record title;
- `wait` after capture with no clarify job answers `ask`; `wait` after an answer re-collects the judge job; open questions leave the gate open, a blocking-gap choice card closes it, answering it opens it.

### Task 3: The owner's answer is kept with its question and the judge runs again

Serves: SR-212 EX-5, EX-6, EX-7, EX-8, EX-10; SR-209 EX-4; SR-208 EX-5.

Changes:
- `hosts/claude_code/question_answer.py` `handle` (inside the 5 s `post_edit` budget):
  - It logs as today, adding `via: "question-tool"` and the `options` with their descriptions.
  - It matches each question to `judge_questions.json` by normalized key, falling back to the session's single open question when exactly one is open. A match adds `asked: {job, records: [{id, hash}]}`.
  - It then enqueues a bare judge job (`{records: ids}`, no premise); `judge.recompute` builds the inputs in the worker. No `judge.build` and no index read in the hook.
  - A dismissed question logs nothing, as today. The docstring sentence "only a card press or the owner's typed command" goes.
- `cmd_clarify.wait`: when questions are open and an answer logged since matched none, it says once "ask these questions as given; the last answer matched none of them", instead of a fresh `ask`.
- `understand/premise.py`: `Premise` gains `answers`: question-answer entries whose `asked.records` names the record at its current hash (an answer to an older version is left out, SR-209 EX-4). `as_input` passes them as `{question, options, answer}`; `input_digest` covers `answers` only when non-empty, so existing verdict digests stay valid. Old entries without `via` or `asked` never count.
- `understand/verdict.py` `_premise_text` appends "Question: ... Options: ... Answer: ..." per answer. A full sentence is passed unchanged (SR-212 EX-10).

Kept: SR-212 EX-1 to EX-4, EX-11 (text answers of SR-163/167 in `clarify.py`) and EX-12.

Adapt: `tests/host/test_question_answer.py`, `tests/understand/test_premise.py`,
`tests/understand/test_answer_once.py`, `tests/understand/test_question_card.py`,
`tests/host/test_hook_limits.py`, `tests/host/test_hook_perf.py` (a case: the hook with 200
records and 500 prompts logged stays under its budget).

New: `tests/host/test_answer_rejudge.py`, one test each: SR-212 EX-5, EX-6 (proposed until the
verdict), EX-7, EX-8 (JEV's claim holds the question and "A"), EX-10; SR-209 EX-4; SR-208 EX-5
(read from the tool record, not the agent's restatement); a reworded question matches by key; an
unmatched answer gives the one line; an empty `answers` keeps the premise digest.

### Task 4: Approval after a question round, and sets approved whole

Serves: SR-248 EX-4, EX-5; SR-209 EX-1; SR-251 EX-2; SR-210 EX-3.

Changes:
- `understand/judge.py` `apply`, for a record whose premise holds at least one answer:
  - When `jev.clears` (a passing calibration and above `max(0.9, threshold)`), approved `by: auto-jev` with `answers`. The switch is not needed: it governs approval without a question (SR-248: "with the fast track off, nothing is approved without a question round"). With no passing calibration JEV approves nothing (SR-251).
  - Otherwise, when the model's verdict is `supported` with `clear: true`: approved `by: auto-model` with `auto: {model, model_version, confidence, clear: true}`, `answers` and `session`.
  - Otherwise the model's next questions follow (task 2). An escalated set is one approval entry, written only when every member is clear at its current hash; until then each member's line says it waits for its set.
- `capture/autoapprove.py` `recheck`, for an answer-cited `auto-jev`: `prompt_digest` is the pre-intent or answer digest; the prompt-event and `prompt_via: hook` checks are replaced by "each cited answer is a `question-answer` entry logged before it, `via: question-tool`, whose `asked` names that record at that hash"; the switch check is skipped; calibration, the strict floor and the `min_confidence` label still apply.
- `understand/recheck_model.py`: the intent exclusion goes; the rule is the same answer check plus `clear: true`. The confidence is never compared.
- `confirm.py` `checked_entries`: `model_floor` is not applied to `auto-model`; an `auto-*` entry naming one member of an escalated set must name every member; an `owner` or `study-room` entry with no hook-logged prompt or question-answer at that hash is refused (SR-210 EX-3). `capture/autoapprove.py`: `model_floor` is deleted.

Deleted: `model_floor` and the "never an intent" rule for model approvals.

Adapt: `tests/understand/test_auto_model.py`, `tests/core/test_confirm.py`,
`tests/understand/test_worker_authority.py`, `tests/capture/test_set_approval.py`.

New: `tests/understand/test_round_approval.py`, one test each: SR-248 EX-4 (0.7, answers, 0.95),
EX-5 (0.85 and haiku clear at 0.8: approved); SR-209 EX-1 (cites the words and the pre-intent);
SR-251 EX-2 (auto-jev at 0.6 refused, proposed); SR-210 EX-3, both variants (owner-quoted, and
study-room with no question at that version); no calibration, an answer and JEV 0.92: no
auto-jev, the model decides; a set with one member unclear approves nothing.

### Task 5: Marked and counted wherever listed, and no approve hint shown

Serves: SR-251 EX-1, EX-2 (the validate warning); SR-267 (no ids in what the owner reads).

Changes:
- `present/cards.py` `BY` gains `auto-model`. `judge_label(status)` gives "judge-approved (auto-jev, jev-1.13, 0.96)" or "judge-approved (auto-model, haiku, 0.8)"; `status`, `show` and `brief` use it.
- `understand/summary.py` `_confirmations`: `CONFIRM_BY_MODEL` (an id and an undo) becomes "N approved on your behalf by the judge", for both kinds; `present/owner_text.py` drops `{id}`.
- `validate.py`: an `auto-jev` or `auto-model` approval failing its re-check is a `warning` `inert-approval`; other approval problems stay errors.
- Sweep: grep `src/plumb` for `approve`, `confirm`, `ok to`, `IDs` and `{id}` in owner-visible strings (`present/`, `owner_text.py`, `hosts/claude_code/session_start.py`, `render.py`, `importer/consent.py`, `capture/spec.py`, `boundary/report.py`, `boundary/glance.py`, `view/`, refusal messages). Each becomes a counted, id-free line. `status`'s "what awaits the owner" lists the open questions (count and request), a hold line or "waiting on a judge", never records to approve.

Adapt: `tests/present/test_labels.py`, `tests/present/test_status_card.py`,
`tests/mod/test_turn_end.py`, `tests/mod/test_turn_line.py`, `tests/core/test_validate.py`,
`tests/merge/test_glance.py`, `tests/merge/test_report.py`, `tests/present/test_view.py`.

New: `tests/present/test_judge_approved.py`: SR-251 EX-1, EX-2; status, brief, the turn line and
the session start print no approve or confirm hint and no id.

### Task 6: The pre-intent with its context, and the trail

Serves: SR-208 EX-4; SR-212 EX-9; SR-248 EX-2; SR-209 EX-2.

Changes:
- `understand/judge.py` `recompute` and `apply` (worker side, with the worker token):
  - For each premise source not logged yet, one `pre-intent` entry: `{source: prompt or question-answer digest, text verbatim, question, options, context}`; the context is the last reply excerpt (`clarify.frozen_context`, or `clarify.conversation` on the transcript).
  - Approval entries carry `trail: [pre-intent digests]`. Nothing comes from an agent-written file (SR-208 EX-11 kept).
- A free-text message answering what the last reply showed (a capture source of SR-212): `understand/read.py` already reads it by meaning per item the reply showed. Its outcome now writes a pre-intent whose `asked` names only the records the reading covers, at their hash, instead of calling `typed.confirm_now`. So in SR-209 EX-2 the rounding record is judged with the owner's words, the amount decision gets a `contradicts` verdict whose line asks the agent to reword it (the edit goes back to the judge), and the reminder intent, not mentioned, stays proposed.
- `capture/capture.py`: an intent quoting a short answer ("A", "2", "yes") with no stored question and no answered question-answer gets one warning, "this answer needs its question"; it is still recorded.

Adapt: `tests/capture/test_capture.py`, `tests/capture/test_quote_only.py`,
`tests/understand/test_premise.py`, `tests/understand/test_read_apply.py`,
`tests/understand/test_read_cards.py`, `tests/understand/test_read_job.py`.

New: `tests/understand/test_pre_intent.py`, one test each: SR-208 EX-4, SR-212 EX-9, SR-248 EX-2,
SR-209 EX-2 (partial answer: one judged with the words, one sent back, one proposed); a prose "ok"
with no question open approves nothing.

### Task 7: Calibration labels from the owner's answers

Serves: SR-252 EX-4. Kept: EX-1, EX-2, EX-3, EX-5.

Changes:
- `understand/judge.py` `apply`: when a re-judge after a round says `answer_corrects`, one `rejection` entry `reason: capture-error`, pinned at the asked hash, with the premise, the hypotheses and the `jev_score` logged at judgment time (task 1). `calibrate.labelled_set` reads it as a real 'no'.
- `capture/calibrate.py`: a pinned item with `jev_score` uses it, with no new model call; an approval citing `answers` with no correction counts as 'yes' (source `answer`).
- `jev status` shows per kind: the owner's answers, real 'no' examples, generated ones and the threshold (added where missing).

Adapt: `tests/capture/test_calibrate.py`, `tests/capture/test_calibrate_rejections.py`,
`tests/capture/test_calibrate_jev_only.py`, `tests/capture/test_jev_cli.py`.

New: `tests/capture/test_calibrate_answers.py`: SR-252 EX-4; a fixture with too few real 'no'
examples shows not passing, with the four counts.

### Task 8: No approval command

Serves: SR-210 EX-1, EX-2, EX-5; SR-209 EX-3, EX-6. Kept: SR-248 EX-8, SR-208 EX-6 (relay
refused), SR-210 EX-4, SR-250 EX-1 and EX-2 (`tests/capture/test_typed_auto_approve.py`, rerun
here because `typed.py` and `guard.py` change).

Changes:
- `commands.py`: `approve`, `revoke` and `relay` print "plumb: <verb> no longer exists; nothing was recorded" and exit `EXIT_REFUSED` (3), whoever runs them, whatever stdin holds; `cmd_approve` and `cmd_revoke` lose their bodies; the relay text stops naming `/plumb approve`.
- `cli.py` `_HELP`: the `approve` and `revoke` lines go (SR-210 EX-5).
- `capture/triage.py --approve` and `spec approve`: refused the same way.
- `guard.py`: the `Row`s for these verbs stay, so the legacy deny rules still match.
- `understand/typed.py`: `parse` no longer returns `approve` or `confirm`; the words go to the reader as prose (SR-209 EX-6). `confirm_now` and `TYPED_NEEDS_IDS` are deleted; `understand/read.py` line 228, its only caller, takes task 6's path. `confirm.py` keeps re-checking past `via: command` entries.
- `approvals.py`: `approve` and `revoke` stay as library functions for history and fixtures.

Deleted: the owner's `approve` and `revoke` commands, typed `/plumb approve|confirm <IDs>`,
`triage --approve`, `spec approve`.

Adapt (from `grep -rlE '"approve"|"revoke"|plumb approve|confirm_now|"confirm"' tests`, rerun
before the gate):
- the commands themselves: `tests/core/test_approvals.py`, `tests/understand/test_typed.py`, `tests/understand/test_typed_namespaced.py`, `tests/understand/test_no_prose_relay.py`, `tests/understand/test_owner_only.py`, `tests/plugin/test_guard.py`, `tests/capture/test_triage.py`, `tests/capture/test_set_approval.py`, `tests/core/test_primitives.py`, `tests/mcp/test_server.py`, `tests/ids/test_owner_text.py`, `tests/understand/test_contracts.py`, `tests/capture/test_skills.py`;
- the CLI as a fixture, switched to `approvals.approve(core, ids)` as `tests/core/test_links.py:491` does: `tests/core/test_drift.py`, `tests/core/test_links.py`, `tests/core/test_merge.py`, `tests/core/test_stale_resolve.py`, `tests/integration/test_session_e2e.py`, `tests/hosts/hosts_helpers.py`, `tests/host/test_install.py`, `tests/merge/test_glance.py`, `tests/merge/test_report.py`, `tests/plugin/test_launcher_fixes.py`, `tests/plugin/test_unadopted.py`, `tests/present/test_view.py`, `tests/understand/test_clarify_job.py`, `tests/mod/helpers.py`, `tests/mod/test_press.py`.

New: `tests/core/test_no_approval_commands.py`, one test each: SR-210 EX-1, EX-2 (no marker,
"y" piped), EX-5; SR-209 EX-3 (a bare "ok", no question open), EX-6.

### Task 9: What the agent is told

Serves: SR-208 EX-10; SR-267 EX-8; SR-248 EX-3 (the agent side).

Changes:
- `templates/skills/plumb-records/SKILL.md`, `plumb-clarify/SKILL.md`, `plumb-intent/SKILL.md` and `templates/plumb-command.md`: remove every "typed `/plumb approve <IDs>`", "the owner confirms on the cards", "the read-back's ok confirms", and `approve <IDs>` in the argument hint. Add one paragraph with four rules:
  1. After `capture`, run `{plumb} clarify --wait --json`. On `ask`, pass each `question`, `header` and option `label` and `description` to AskUserQuestion verbatim, one call per question, in order. Never restate a question in prose.
  2. Never answer, infer or default a question for the owner, never pick the recommended option for them, and never write or read `judge_questions.json` or any approval. plumb's judge approves on the owner's behalf; no approval command exists.
  3. If the question tool is unavailable (a subagent or headless run) or the owner dismisses a question, stop asking, tell the owner in one plain line that the work waits for their answer, and do not rerun `ask` in a loop. `clarify --wait` names a dismissed question once, then answers `waiting`.
  4. Any other question to the owner also goes through the question tool, with options and their consequences.
- Gate step zero: `scripts/build_plugin.py` regenerates `plugin/` before pytest runs. The plugin is never edited by hand.

Adapt: `tests/capture/test_skills.py`, `tests/host/test_install_skills.py`,
`tests/plugin/test_bundle_fresh.py`.

New: in `tests/capture/test_skills.py`: SR-208 EX-10 and SR-267 EX-8 (ask through the tool, one at
a time, verbatim, no relay or approve), and the four rules present in each skill.

## 3. Out of this slice, and why

- The study room (SR-267 EX-3, EX-6; study-room answers in SR-212 and SR-210 EX-4): a browser surface with its own records. Here the question tool is the one channel.
- Log compaction and the v2 tidy (P15): a separate job at the merge.
- Other hosts (Codex, Pi, Hermes): their question tools and hook records differ (P14). SR-208 EX-7 stays as today.
- The debug workflow (SR-245 EX-11, the "what cannot settle" half of SR-267 EX-9, P5): it does not exist yet, so those records wait with the waiting line. It also owns non-convergence; no record states a cap on rounds.
- Conflict and merge question shapes (SR-267 EX-1, EX-2, EX-7) and the refusal of an agent-filed question (SR-267 EX-5): other producers of questions, and the refusal needs a PreToolUse check on AskUserQuestion. A follow-up; task 9 rule 4 tells the agent the shape meanwhile.
- The switch asked through the question tool when the owner says it in a sentence (SR-250 EX-3): the reader's path, not the cascade.
- Remaining cards: the clarify choice card for a blocking gap or a spec session, cards already open (`trial.py`, the mod panel's press) and the merge driver's cards. They are the only card kinds left, none is raised for a judged record (task 2's test), and turning the choice card into a `judge_questions.json` entry is the first task after this slice (P12).
- `/plumb undo <ID>` (P2: no owner command takes an id). P3's reversal "by saying so in conversation" goes through the reader (task 6's path reads "undo the rounding requirement" by meaning); dropping the id form comes with the card retirement.
- Confirming a `trace.exempt` glob added on a branch (SR-028 EX-3, EX-5): its only route was `plumb approve --exempt`, which task 8 refuses, and the judge and question route covers records only. Until a follow-up decides the route (one question-tool question in the owner's words, or a judge verdict that writes the entry), the merge check holds such a glob and says to remove it to merge (SR-288).
- Decision fast track: `CLAIM_KIND` has no decision kind, so decisions always take the question route until one is calibrated (SR-252: an uncalibrated kind never fast-tracks). A follow-up adds the kind.

## 4. Staleness: code the records describe differently

- `capture/autoapprove.py` `gate` approves in capture, apart from the judge job (SR-242), excludes decisions, and compares the floor with `<` (SR-242 EX-5 wants strictly above).
- `understand/verdict.py` `jev_verdict` and `_ask_jev` never ask JEV without a passing calibration, accept a probability equal to the threshold, and log no score below it (SR-252 EX-4).
- `understand/judge.py` `_confirms` gates `auto-model` on confidence against the owner's floor (DEC-141), never approves an intent and needs no round; supported records go to trial cards with doubt lines (SR-209, SR-252 EX-6).
- `judgment/verdict.py` says "nothing approves on a judge model's verdict alone". `understand/recheck_model.py` refuses intents and checks the premise, not a round.
- `hosts/claude_code/question_answer.py` says an answer never confirms anything; it now feeds the judge.
- `understand/typed.py`: `/plumb approve|confirm <IDs>` confirms at once (SR-209 EX-6); `/plumb undo <ID>` takes an id (section 3). `commands.py`, `cli.py`: `approve` and `revoke` exist and are in help; `relay` names `/plumb approve` (SR-210).
- `capture/calibrate.py` takes 'no' labels only from card rejections and revocations, and re-scores with JEV (SR-252 EX-4).
- `understand/summary.py` names an id and an undo in the model-approval line; `validate.py` reports every re-check problem as an error (SR-251). `log.py` `WORKER_ONLY_BY` leaves out `auto-jev` (SR-210).
- The skills and `plumb-command.md` tell the owner to type `/plumb approve <IDs>` (SR-208 EX-10, SR-209).
- `understand/read.py` confirms prose answers at a reader confidence (a self-reported number) through `typed.confirm_now`; task 6 routes it into the cascade.
- `capture/triage.py` `view` still rates by `textjudge.contradiction` (a flipped will/won't); it is off the judge path, which uses only `premise_problem`.
- No pre-intent entry and no "judge-approved" mark exist today. Tasks 3 to 6 add them.

## 5. The proof per requirement (DEC-142: the recommended proof stands)

| SR | Kind | Recommended proof, as the record states it |
|---|---|---|
| SR-209 | live-session | The owner states a small intent; status shows the requirement judge-approved with the trail to their sentence, nothing read or approved by them |
| SR-248 | live-session | Fast track on and calibrated: a plain intent approved by JEV with its score and no question; an ambiguous one brings questions and, after the answers, shows approved with both verdicts |
| SR-251 | live-session | The turn-end line counts a judge approval and status shows its judge and score; a hand-made entry under the bar is a warning and the record stays unapproved |
| SR-250 | live-session | `/plumb auto-approve on` shows the fast track on; the agent's attempt to switch it is refused |
| SR-252 | command | Calibration status per kind: the owner's answers, the 'no' examples, how many generated, the threshold; a fixture with too few 'no' examples is not passing |
| SR-212 | live-session | A question-tool answer kept with its question and no new question follows; "maybe, not sure" brings the question back once |
| SR-267 | live-session | The recorded proof (a conflict question, then an agent-filed question refused) is wholly outside this slice (section 3). This slice shows the narrower part: a judge question reaches the owner with options and consequences, recommended first, no id |
| SR-210 | live-session | The agent tries to approve, relay and write an approval by hand; each is refused or reported, the record stays proposed |
| SR-242 | command | `judge_model: sonnet`, JEV unsure on one of two intents: the plumb line shows one approved on JEV and one on Sonnet; `/plumb jev status` names Sonnet |
| SR-245 | hook | JEV key and model unreachable: one line names the judge and why, the records wait, the turn goes on; key restored, the line is gone |
| SR-208 | hook | A peer message and a task notification, then the owner's sentence: only the sentence becomes a pre-intent, with its context |

The live walks run once in a scratch repository after task 9: SR-245, SR-242, SR-248 (question
half), SR-209 (with a reversal said in conversation), SR-251, SR-210, SR-212, SR-208. The JEV
fast-track halves of SR-248 and SR-250 wait for a passing calibration, which task 7 makes
reachable.

## 6. Running the tests under the CPU cap

One pytest invocation at a time, `-n 2`, never the full suite, from the worktree with `src` on
the path. Each list is a shell variable, checked non-empty first:

```
cd C:/coding/plumb-wt/judge && [ -n "$LIST" ] || exit 1
PYTHONPATH=src C:/coding/plumb/.venv/Scripts/python.exe -m pytest -n 2 $LIST
```

Each task's list is its Adapt and New files above. Task 2's `tests/understand/test_e2e_flows.py`
runs alone. In task 8, `tests/hosts/` is run only through the files importing `hosts_helpers.py`:
`test_codex.py`, `test_conformance.py`, `test_hermes.py`, `test_hosts_self_recorded.py`,
`test_pi.py`, `test_stated_display.py`, `test_turn.py`, `test_turn_gates.py`,
`test_turn_watchdog.py`. Task 9 runs `scripts/build_plugin.py` first. Before the merge:
`plumb tests select --changed`, its list checked non-empty, run as one invocation.

Each task's gate is its own list passing. The next task starts only after it passes.

## Review notes

- "DEC-140 is cited but no task removes the rule": the rule is already gone. Commit e8ee2bfe
  ("the judge's number rule goes", SR-239, DEC-140) removed it; `judgment/textjudge.py`
  `contradiction` now says "A number the owner never said is the agent's formalization, not a
  contradiction (DEC-140)". `triage.premise_problem` (triage.py:169-195) checks only that each
  quote is verbatim in a hook-logged prompt, and the judge path (`judge.py:271`, `:319`,
  `recheck_model.py:31`) calls `premise_problem`, never `_contradiction`. A record with a number
  absent from its quote is not marked quote-only. Section 4 notes the remaining flipped-word
  check in `triage.view`, which is off the judge path.
- "Questions cover every record" is kept in part: SR-248 says "Otherwise the judge model returns
  question-tool questions", and DEC-141 lets the model approve "only when it says the intent is
  clear after a question round", so a record JEV does not clear needs a round to be approved at
  all. Task 2 narrows it: one question per principle covers many records, in the owner's words,
  never a record's title.
