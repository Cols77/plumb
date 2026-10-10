# Follow-ups

Medium and low review findings that were not fixed in the change that raised them.
Each entry names the source review, the severity, and the finding.

<!-- Add entries below as: - [SEVERITY] (source) finding -->

## Concept spec intent review (2026-10-05, docs/concept.md)

- [MEDIUM] (intent review, concept 11) The 9-hour time box (brief decision 11) is not mentioned and sub-project 1 has no cut line. Fix: add a must-ship-tonight slice (records, hashing, pins, check, approvals log, SR trailers, a map from `verified_by` links and markers, verify with the cheap `env_key`, the four hooks, the status line) and mark import-closure selection, full environment identity, owner waivers and the judgment interface as follow-on within sub-project 1. Largely resolved by the round-2 HIGH fix (roadmap slice 1a/1b; import closure stays in 1a).
- [MEDIUM] (intent review, concept 3.4/4.1/4.7/7.3/7.5) Test evidence lives only in the gitignored cache until the merge boundary (sub-project 3), yet the cache is called derivable and deletable "without losing information"; the log-integrity check is also deferred. The KEEP item "append-only evidence" is missing in sub-project 1. Fix: have `plumb verify` append evidence entries under `.plumb/log/evidence/` from sub-project 1 and keep only the reuse index in the cache (or record the deferral as a known gap), and move a minimal log-integrity check (digests of committed entries, run by `plumb check`) into sub-project 1.
- [MEDIUM] (intent review, concept 6.6 trigger 3) Red-step test failures counted as regressions. Resolved in the same change by the HIGH fix that narrowed trigger 3 to tests with prior passing evidence; kept here for traceability.
- [MEDIUM] (intent review, concept 6.2 step 3) The change-language heuristic (also, change, don't, ...) will fire on most prompts that overlap a confirmed record, pushing the agent to ask too often, with no measurement of false positives. Fix: require an ID match or strong term overlap first, tell the agent to ask only for a real contradiction or extension and otherwise note it in the summary, log every flag for audit, and add a fixture-based precision test in sub-project 1.
- [MEDIUM] (intent review, concept 4.6/11/12) No bootstrap approval source for plumb's own requirements, since the owner will not review them. Fix: define agent-for-owner approvals that cite verbatim quotes from the owner intent brief plus the brief's digest, marked as derived from the brief, and list this in the sub-project 1 exit criteria.
- [MEDIUM] (intent review, concept 11 exit criteria) Dogfooding exit criteria include no INT or DEC records, so plumb's SRs have no `derives_from` link to the owner's words. Fix: seed the brief's quotes and decisions as INT and DEC records approved with the brief as evidence, and require every plumb SR to have a pinned `derives_from` link to an INT.
- [MEDIUM] (intent review, concept 8/11 sub-project 2) Fidelity judging (KEEP) exists only through optional JEV, deferred to sub-project 2; with JEV disabled nothing checks that a `verified_by` test encodes its EX-n or that code still fits its requirement. Fix: define a no-JEV fidelity path in which the stop hook asks the host agent once, for requirements changed in the turn, whether each linked test still matches its example, logged as an advisory judgment; state which sub-project delivers it. Resolved by the round-2 HIGH fix (section 6.4 fidelity request, roadmap 1b).
- [MEDIUM] (intent review, concept 4.6/6.2) Agent-for-owner approvals cannot be checked once gitignored session state (the prompt text) is deleted. Fix: at recording time, check that the quote is a verbatim substring of the stored prompt text and write the result into the entry (or commit the digest of the quoted span). The summary line for each agent-for-owner approval was added by the passive-confirmation HIGH fix.
- [LOW] (intent review, concept 4.6) Same verifiability gap as above, low-severity variant: make the check "digest of the quoted text equals the recorded prompt-fragment digest".
- [LOW] (intent review, concept 10/11) The importer appears only as the full importer in sub-project 5, and `by: import` approvals assume every upstream record was owner-approved. Fix: stage a read-only minimal SR/FEAT/NC importer right after sub-project 1, and give `by: import` approvals only to records with an upstream approval or consent; import the others as proposed.
- [LOW] (intent review, concept 5.2/6.6) "plumb suggests escalation, and the owner decides" leaves the accept/decline step undefined. Fix: state that the suggestion appears in the end-of-turn summary and the owner accepts or declines by replying or with a command (for example `plumb escalate` / `plumb decline`); no question unless another trigger fires.
- [LOW] (intent review, concept 10) The fork plan referred to in section 10 does not exist yet in docs/. Fix: write the fork plan document and link it from section 10.
- [LOW] (intent review, concept 1) The decision table renumbers the brief's 12 decisions and omits brief decisions 10 and 11. Fix: use the brief's numbering 1-12 and add rows for decisions 10 and 11. Resolved by the round-2 HIGH fix (decision table D1-D12).
- [LOW] (intent review, concept 5.2) Prompt-time escalation triggers ("more than 3 requirements", "more than one feature") have no stated evaluation method in the deterministic hook. Fix: evaluate them from the records matched in 6.2 (matched SRs and features, shared-surface path terms) and have the agent re-check after its read-back, adding the suggestion to its reply.
- [LOW] (intent review, concept 6.2 step 3) Intent-change extensions phrased without change keywords are missed; the hash backstop only catches edits to the record itself. Fix: document the limitation and add a stop-hook backstop that flags new code or test changes linked to a confirmed SR whose examples were not updated.

## Concept spec intent review, round 2 (2026-10-05, docs/concept.md)

Raised by the second intent review. The three HIGH findings of that review (approval guard,
default fidelity path without JEV, decisions 10 and 11 with the 9-hour slice) were fixed in
the same change. Some entries below repeat entries of the first round; they are kept so each
review's findings can be traced.

- [MEDIUM] (intent review 2, concept 4.1/4.7/7.3/7.5/11) Until sub-project 3, test evidence lives only in the gitignored `.plumb/cache/`, so it is neither append-only nor inspectable in git, and nothing checks that committed log entries were not edited. Fix: have `plumb verify` in sub-project 1 append a small evidence entry (node ids, outcome, `closure_digest`, `env_key`) to `.plumb/log/evidence/`, keep only the reuse index in the cache, and add a minimal per-entry self-digest integrity check to `plumb check`.
- [MEDIUM] (intent review 2, concept 11) Sub-project 1 had no ordered must-ship cut for the 9-hour time box. Largely addressed by the HIGH fix that added slice 1a/1b and the drop order; remaining suggestion: also move the failure-policy waiver, the full environment identity and AST symbol-level hashing explicitly behind map and verify (now the case in 1b) and keep this cut in sync with the plans.
- [MEDIUM] (intent review 2, concept 6.6 passive path, basis no-objection) The agent records an owner approval whenever the next prompt does not object, even when it is about something else, so the agent's own reading decides confirmation. Fix: show these as "confirmed (passive)" in the status line and summary, and limit no-objection to prompts that continue the same work (term overlap with the stated records); otherwise leave the records proposed.
- [LOW] (intent review 2, concept 6.6 trigger 1 backstop) Any hash change to a confirmed record without re-approval, including a typo fix or rewording that normalization does not cover, becomes a question to the owner. Fix: surface it first in the summary and status line; escalate to a question only when the heuristic or judgment backend classifies the edit as material, or when `statement` or `examples` changed.
- [LOW] (intent review 2, concept 10/11 roadmap 5) The importer is scheduled last, so pi-agent-factory format compatibility (decision 1, A/B) gets no early validation. Fix: add a read-only import dry-run (parse and report findings, no writes) to sub-project 1 or 2.
- [MEDIUM] (intent review 2, concept 4.1/4.7/7.3/7.5) Test evidence in sub-project 1 lives only in the cache, which contradicts the KEEP item "append-only evidence" and principle 4 (caches deletable "without losing information"). Fix: append test evidence to `.plumb/log/evidence/` from sub-project 1 (promotion then only adds merge-level records), or state explicitly that cached evidence is reproducible by rerunning tests and that append-only test evidence is deferred to sub-project 3.
- [MEDIUM] (intent review 2, concept 6.6 trigger 1 backstop) The backstop turns the agent's own edit of a confirmed record (rewording, typo) into the owner's first trigger, which the owner defined by the request contradicting or extending a requirement. Fix: show such edits as an "unconfirmed edit" drift signal in the summary and status line; ask only when the prompt or a judgment indicates a semantic change, or only for edits to `statement` and `examples`.
- [MEDIUM] (intent review 2, concept 4.6/6.6 no-objection) A no-objection approval rests on a model judgment that the prompt does not object, in tension with the non-goal "No model that ... confirms intent" and with "Trust comes from evidence". Fix: make downstream states visible by basis (for example "confirmed (no-objection)" in status output), optionally limit no-objection to prompts continuing the same task, and let `plumb approve --proposed` upgrade them to explicit.
- [LOW] (intent review 2, concept 8 and roadmap 2) Fidelity judging was defined only as a JEV use. Resolved in the same change by the HIGH fix that added the default host-agent fidelity request (section 6.4, roadmap 1b); kept here for traceability.
- [LOW] (intent review 2, concept 10) The fork plan and the dogfooding plan are referenced but do not exist in the repository. Fix: add `docs/plans/fork.md` and `docs/plans/dogfood.md` (or similar) and link them from sections 10 and 11.
- [LOW] (intent review 2, concept 11 roadmap 1) Dogfooding was only an exit criterion, with no build order putting plumb's own SR records and trailers first. Largely addressed by the HIGH fix (slice 1a orders record model and check, then approvals, then plumb's own SR records and trailers, then each hook installed in plumb as it lands); kept here so the plans follow that order.
- [LOW] (intent review 2, concept 6.6) The sentence "Only a decision with `matters: true` can block work, and only through trigger 2." conflicts with triggers 1 and 3, which also stop work. Fix: say that the three triggers are the only things that can stop work, and that proposed records never block.
- [MEDIUM] (intent review 2, concept 4.2/4.6/6.6 step 2) A no-objection approval makes a record "confirmed" exactly like an explicit "yes", although the owner may never have read the examples; such records can later trigger trigger 1 when edited, and the basis is not visible in derived states or the status line. Fix: keep basis visible in the derived state (an "accepted" state between proposed and confirmed, or counts such as "confirmed 10 (3 by no-objection)"); count only explicit or command approvals for trigger 1; list no-objection records in the session brief so the owner can promote them with `plumb approve`; reword the non-goal so it is honest about the agent classifying the prompt.
- [MEDIUM] (intent review 2, concept 4.2/4.5/5.1/7.5) Traceability is checked only downward from SRs. Nothing requires an INT's `will` items and `assumptions` to map to an SR or DEC, and an SR without a `derives_from` link to an INT is not flagged, so stated intent can be read back but never turned into a requirement without any drift signal. Fix: give each `will` item and assumption an id (W-n, A-n); have `plumb check` and the session brief report INT items with no derived SR (assumptions with no DEC) and SRs with no `derives_from` link (warning for imported records); show "untranslated intent items" as a count in the summary and status line.
- [LOW] (intent review 2, concept 4.2 DEC `matters`, 6.6 trigger 2) The agent alone sets `matters`, so marking every decision `matters: false` silently suppresses trigger 2, and nothing defines when a decision matters. Fix: define a deterministic floor (a DEC that decides a confirmed record or touches an escalation surface counts as mattering whatever the flag says) and list every `matters: false` DEC in the session brief.
- [LOW] (intent review 2, concept 11 roadmap 1/2) Escalation triggers, set approvals and the read-back/example/decision helpers are all in sub-project 2, and the concept does not state which intent-translation guarantees the 9-hour deliverable provides. Fix: add a short paragraph to section 11 stating what sub-project 1 guarantees (record kinds, pinned approvals, passive confirmation, drift and the coverage state) and that escalation suggestions are deferred by design.

## Concept spec intent review, round 3 (2026-10-05, docs/concept.md)

Raised by the third intent review. Its two HIGH findings were fixed in the same change: a
shared-infrastructure change no longer selects the full suite in a turn (it marks "full
rerun due at merge", and per-turn `plumb verify` is capped by a time budget; sections 3,
6.4, 6.5, 7.2, 7.4, 7.5, 11, 12), and `basis: no-objection` is dropped, so only the owner's
own affirming words or `plumb approve` confirm a record, quote-checked for an affirmation
term and limited to the records just stated (sections 4.2, 4.6, 5.1, 5.2, 6.6, 9, 10, 11,
12). The "passive confirmation path" is renamed the "in-flow confirmation path"; earlier
entries above keep the old name.

- [MEDIUM] (intent review 3, concept 4.6 guard item 2, 6.3, 9) The latency budget is per hook process, but the PreToolUse guard runs on every shell and edit call and PostToolUse on every edit; a 30-tool-call turn on this 2-core Windows machine could spawn 30+ Python processes importing PyYAML, adding 6 to 10 s per turn. Fix: set a per-turn total budget as well as a per-hook one; make the guard and edit-tracking hooks a stdlib-only fast path (no yaml, no plumb.records import); use the narrowest host matcher; exit early unless the command contains "plumb" or the path is under `.plumb/log`; add a latency test summing hook time over a simulated 30-call turn.
- [MEDIUM] (intent review 3, concept 4.6, 6.6 step 2, 4.2) `basis: no-objection` let a non-objecting next prompt count as confirmation, so confirmed/covered/verified did not distinguish affirmed examples from unread ones. Fix suggested: keep basis visible in the derived state and count implicit confirmations separately. Resolved by the round-3 HIGH fix, which drops no-objection confirmation entirely.
- [MEDIUM] (intent review 3, concept 6.4) The stop hook hands the agent extra work every coding turn (run `plumb verify`, then one `plumb judge` call per changed requirement), described as "no extra cost"; the fidelity request is uncapped when many requirements change. Fix: cap the fidelity request (for example 3 requirements per turn, the rest queued for `plumb status`); let `config.yaml` turn the per-turn verify nudge off or down to once per N turns; say the cost is extra agent time. (The round-3 HIGH fix already caps the test run with `verify.turn_budget_s`; the judge request remains uncapped.)
- [MEDIUM] (intent review 3, concept 11 roadmap vs 5.2) Escalation triggers, set approvals and the intent/example/decide helpers are all in sub-project 2, so the morning build has no escalation suggestion at all, although planning was the owner's explicit concern. Fix: add a minimal deterministic escalation hint to the 1a prompt hook (more than one feature named, or a confirmed record matched together with change language), or list escalation as the first item of sub-project 2 here, with its state.
- [LOW] (intent review 3, concept 4.6 prompt-digest log, 4.8 claims) One committed JSON file per owner prompt under `.plumb/log/prompt/` fills git history with noise, and the claims check does not exempt `.plumb/**` by default, repeating the pi-agent-factory problem where undeclared touched paths broke the gate. Fix: make `.plumb/**` (at least `.plumb/log/**`) a default claims exemption; consider batching digests into one append-only file per session, created no-replace and closed at session end.
- [LOW] (intent review 3, concept 11 1a item 1 and 1b) In 1a, link ends are hashed as whole files, so any edit to a test or source file marks every link into it stale, flooding the summary with false drift and teaching the owner to ignore staleness; the 6.4 summary example also uses a symbol end (`links.py:repin`) that 1a cannot produce. Fix: move test-node hashing (function source by `ast`) into 1a, or label whole-file staleness "file changed" so it reads less loudly than a symbol-level stale; make the example consistent with 1a.
- [LOW] (intent review 3, concept 10 importer, 11 item 5) The importer appears only in roadmap item 5, so the KEEP aspect of reusing SR/FEAT artifacts cannot be exercised in sub-project 1. Fix: record a minimal read-only `plumb import pi-agent-factory --dry-run` (parse SR and FEAT, report mapping findings) as an early follow-up right after 1b.
- [MEDIUM] (intent review 3, concept 4.6, 6.6) Under `basis: no-objection`, any next prompt that did not object, even an unrelated one, became a confirmation, close to treating inattention as consent. Fix suggested: a separate state ("tentatively confirmed") or a term-overlap threshold; count only explicit or terminal approvals for trigger 1. Resolved by the round-3 HIGH fix (no-objection dropped; explicit approvals must quote an affirmation term and target only the stated set or records named by ID).
- [MEDIUM] (intent review 3, concept 6.6 trigger 1) The "deterministic backstop" asks the owner whenever a confirmed record's hash changed this turn without a new approval, so an agent's wording fix to a confirmed SR interrupts the owner although no request changed intent, which goes beyond the agreed triggers. Fix: make the backstop a drift signal in the summary and status line ("unconfirmed edit of SR-004"); escalate to a question only when the statement or examples differ materially (judged like intent-change detection) or when the turn's prompt was flagged as an intent change.
- [MEDIUM] (intent review 3, concept 4.1, 4.7, 7.3, 11 1a item 5) Test evidence reaches the committed append-only log only when promoted at merge boundaries (sub-project 3); until then `plumb verify` results sit in the gitignored, deletable `.plumb/cache/`, so the morning deliverable has no append-only test evidence, and the spec does not say so outright. Fix: state where 1a evidence lives; either write `plumb verify` results as append-only entries under `.plumb/log/evidence/` from 1a, or record here that append-only evidence is deferred to sub-project 3, with the reason. (The round-3 HIGH fix derives "full rerun due" from the latest full-suite evidence, which also needs that evidence to be durable.)
- [LOW] (intent review 3, concept 4.6, 6.2 step 1) Every owner prompt creates a committed JSON file under `.plumb/log/prompt/`; the spec does not say who commits these files or when, or what happens to approvals whose prompt-digest entry was never committed. Fix: state the commit policy, for example digests are committed together with the approval that cites them, and digests no approval references are pruned from session state and never committed.
- [LOW] (intent review 3, concept 10; docs/ holds only concept.md and followups.md) The fork plan and the dogfooding plan are deferred to separate documents that do not exist yet, so decisions 9 and 10 stay unserved. Fix: make sure the workflow produces `docs/plans/dogfooding` and `docs/plans/fork` (or equivalent) and link them by path from sections 10 and 11.
- [MEDIUM] (intent review 3, concept 4.5 `plumb repin`, 11 1a vs 1b) In 1a, drift is detected only as stale pins, and the agent can clear any stale `implemented_by`/`verified_by` link with `plumb repin` with no check that the changed code still fits the requirement (the fidelity request and `plumb judge` arrive in 1b); the repin is only logged, never surfaced as a distinct signal. Fix: in 1a, show every repin of a link whose code or test end changed in the end-of-turn summary (for example "repinned SR-007 -> links.py (code end, unjudged)") and count such repins as "unjudged" in the status line until a fidelity judgment or covering-test pass exists for the new hashes.
- [MEDIUM] (intent review 3, concept 11 roadmap item 2) The escalation suggestion and the read-back/example/decision helpers (`plumb intent`, `plumb example`, `plumb decide`) are deferred to sub-project 2, so the morning deliverable has no "tool suggests when to escalate" and agents must hand-write YAML records with pins. Fix: acceptable within the time box, but list the escalation suggestion and the record helpers here as the first sub-project 2 items, and have the 1a skill tell the agent how to create INT/SR/DEC records by hand (or with `plumb repin` to compute pins) so read-backs and examples are recorded from day one.
- [MEDIUM] (intent review 3, concept 6.2 step 3) Intent-change detection needs both term overlap with a confirmed record and a change word, so a contradicting or extending request phrased without those words ("make the summary ten lines" when a confirmed SR says five) is not flagged, and the agent is not told to compare the request with the injected records. Fix: whenever relevant confirmed records are injected (step 2), add a one-line instruction to compare the request with them regardless of change words; keep the change-word heuristic only to raise priority; note the false-negative risk and a measurement plan here.
- [LOW] (intent review 3, concept 6.1, 6.2) The session brief and per-prompt context do not say that records superseded through `supersedes` links are excluded, so superseded intents or decisions could be injected as current intent. Fix: state that the brief and prompt context include only non-superseded records, reachable otherwise only through `plumb log` / `plumb status`.
- [LOW] (intent review 3, concept 4.2 DEC `matters`, 6.6 trigger 2) The agent sets `matters` on its own DEC records and can keep a decision out of trigger 2 by marking it `matters: false`, with no check or visibility. Fix: list new `matters: false` decisions in the end-of-turn summary (for example "assumed: DEC-003 (minor)") so the owner can see and promote them without being interrupted.

## Owner-proxy rulings R1-R7 integrated (2026-10-05, docs/concept.md)

The brief's binding rulings were applied to the concept spec. No `[HIGH]` entry was open in
this file. The rulings settle these recorded entries, which need no further action:

- R1 (non-blocking read-back and examples; trigger 2 at the merge boundary, for an escalated
  spec or on a contradiction; every touched requirement confirmed at merge): settles the
  trigger-1 backstop entries (round 2 "Any hash change to a confirmed record", round 2
  "The backstop turns the agent's own edit", round 3 "The deterministic backstop asks the
  owner"). An unrequested edit of a confirmed record is now an "unconfirmed edit" drift signal
  that the merge boundary asks about (concept 6.6, 7.5). Also settles the round-2 LOW
  "Only a decision with `matters: true` can block work" (sentence removed; concept 3, 4.2,
  6.6) and part of the round-2 LOW on what sub-project 1 guarantees (`plumb check --merge`
  is now 1a item 4).
- R2 (`agent-relayed` approvals with quote and prompt digest; no no-objection approval;
  merge-boundary glance list; honest trust model): confirms the round-2 and round-3
  no-objection resolutions. The log is now hash-chained (`prev` digests) and the trust model
  says tamper-evident, not tamper-proof (concept 3, 4.6, 4.7).
- R3 (regression = previously passed with recorded evidence): confirms the round-1 red-step
  resolution (concept 6.6 trigger 3).
- R4 (`plumb fidelity <SR>` packets for the host agent, on demand or listed at merge,
  advisory; JEV only accelerates): settles the round-3 MEDIUM "The stop hook hands the agent
  extra work every coding turn" (the per-turn fidelity request is gone) and refines the
  round-1 and round-2 no-JEV fidelity entries (concept 6.4, 8, 7.5). It also partly answers
  the round-3 MEDIUM on unjudged repins: a repinned code or test end shows as
  `fidelity unjudged` until judged; a distinct "repinned" summary line remains open.
- R5 (`full verification pending`, bounded sample on unknown coverage): renames the round-3
  "full rerun due at merge" state and adds the unknown-coverage sample (concept 7.2, 7.4).
- R6: the decision table rows D10 and D11 now carry "owner does not review; agents verify"
  and "implementation available by tomorrow morning (9 hours)" (concept 1, 11).

Still open after the rulings (unchanged severity): append-only test evidence before
sub-project 3, change-language heuristic precision, bootstrap INT/DEC records for plumb's
own SRs, prompt-digest commit policy and noise, escalation hint in 1a, per-turn total hook
budget, importer dry-run, the fork and dogfooding plan documents, superseded records in
context, `matters: false` visibility.

- [LOW] (rulings integration, concept 4.7) The log head pointer lives in the gitignored cache,
  so two concurrent sessions can write entries with the same `prev`; `plumb check` accepts
  such forks like branch merges, which weakens ordering evidence slightly. Fix if needed: take
  a short file lock on the head pointer when appending.

## Concept spec intent review, round 4 (2026-10-06, docs/concept.md)

Raised by the fourth intent review, after the owner-proxy rulings were integrated. It found
no HIGH finding. The entries below are recorded and not fixed; several repeat open entries of
earlier rounds and are kept so each review's findings can be traced.

- [MEDIUM] (intent review 4, concept 11 item 1a steps 1-6) Slice 1a is large for the 9-hour time box (full record model, hash-chained log, pinned approvals with the three-part self-approval guard, prompt-digest log, trailers with a commit-msg hook, merge check, five hooks plus status line and installer, AST map, covering-test selection with budget and sampling, identity-keyed verify). The drop order removes items from the end first, but nothing marks the minimum dogfoodable cut inside 1a, and steps 5-6 (hooks, map and verify), where the grounding loop actually happens, are the most likely to be dropped. Fix: mark an explicit "morning minimum" inside 1a (for example records, hashes, check, approvals, trailers, the session-start and stop hooks, the status line), and move the guard hook's PreToolUse string matching and the unknown-coverage sampling behind that line, so the grounding loop is present in the morning even if verify is not.
- [MEDIUM] (intent review 4, concept 11 1a item 6 and the drop-order paragraph) Covering-test verification (`plumb map`, covering-test selection, `plumb verify`) is the last item of 1a, so the drop rule removes it first, and the guaranteed morning slice leaves out what decision 6 names as part of the first scope. This is a sequencing risk, not a contradiction: 1a still includes the item. Fix: state that a minimal covering-test path (`verified_by` links plus `plumb verify` recording evidence) belongs to the guaranteed morning core; if it cannot, move a reduced form of item 6 ahead of the later parts of item 5, such as the install polish.
- [MEDIUM] (intent review 4, concept 10 importer vs 11 roadmap) Section 10 specifies an importer, but the roadmap lists only the full importer and migration in sub-project 5, with no earlier basic importer. Decision 1B (pi-agent-factory can later migrate) and decision 7 (reuse existing SR/FEAT artifacts) have no early deliverable, and format compatibility goes unverified until the end. Fix: add a minimal read-only `plumb import pi-agent-factory --dry-run` (SR/FEAT/NC parse plus findings, no writes) to sub-project 1b or 2.
- [LOW] (intent review 4, concept 11 importer only in sub-project 5) No early step checks import compatibility, so a format choice made in 1a could quietly break round-trip compatibility with the pi-agent-factory register. Fix: add a small compatibility test in 1a or 1b that parses one real SR, FEAT and NC file from the pi-agent-factory register (read-only) into plumb's model.
- [MEDIUM] (intent review 4, concept 4.6, 6.2) Every owner prompt writes a committed JSON file under `.plumb/log/prompt/`, adding steady git churn and noise to every commit, a visible cost of the kind the owner called heavy; most prompts never back an approval. Fix: keep prompt digests in gitignored session state and commit a digest only when an agent-relayed approval cites it (embedded in the approval entry, or written to the prompt log at approve time). Every check in section 4.6 stays the same.
- [MEDIUM] (intent review 4, concept 7.2) The default per-turn verify budget (`verify.turn_budget_s`) is 30 s with a 60 s hard limit (2x budget), so a turn that edits code and runs `plumb verify` can add close to a minute, at the edge of "seconds, not minutes", and worse on this 2-core machine. Fix: lower the default budget to about 10-15 s and the hard limit to about 1.5x the budget; deferred tests carry to the merge boundary as already designed.
- [LOW] (intent review 4, concept 6.4) The end-of-turn summary (up to five lines plus one line per proposed record) has no length limit, since every newly proposed read-back or example adds a line; a turn that drafts several SRs with examples prints a long block, against "short alignment summary". Fix: cap the proposed lines (for example at 3) plus a "+N more (plumb status)" line.
- [MEDIUM] (intent review 4, concept 3.4, 4.1, 4.7, 7.3, 11 sub-project 3) Per-turn test evidence lives in the gitignored `.plumb/cache/` and reaches the committed append-only log only at the merge boundary (sub-project 3), so until then it is neither append-only nor committed. Principle 4 says caches can be deleted "without losing information", yet R3 regression detection depends on earlier passing evidence: deleting the cache silently erases the basis for a regression question. Fix: append per-test pass/fail evidence (or a compact summary keyed by node_id and identity) to a committed log in sub-project 1, or state that regression detection resets when the cache is deleted and narrow principle 4's claim to match.
- [MEDIUM] (intent review 4, concept 6.4 verification nudge) Covering tests run only when the stop hook nudges the agent to run `plumb verify` and coverage evidence is not fresh; an agent can ignore the nudge and the summary then shows "not yet run". R5 says per-turn checks "always run" covering tests within a budget, and hooks are for guarantees; the low-latency design weakens "always run" to "requested". Fix: show the outstanding-verification state in the status line and the summary until it is satisfied, and make the merge-boundary check (7.5, 1a) refuse, or at least list, touched requirements whose covering tests were never run.
- [LOW] (intent review 4, concept 7.5 first bullet) The merge boundary also requires every intent and decision a touched requirement derives from to be confirmed, while R1 requires this only for requirements. It is bundled into the same one-line question, so it adds no interruption, but it goes beyond the ruling without saying so. Fix: note it as a deliberate refinement of R1, or limit the mandatory set to requirements and list unconfirmed upstream INT and DEC records as information.
- [MEDIUM] (intent review 4, concept 4.5 link kinds, 7.5 first bullet) Section 7.5 requires "the intents and decisions it derives from" to be confirmed at merge, but the link table models a decision as DEC --decides--> SR, so a requirement never `derives_from` a DEC and the rule never covers decisions; it is also unclear whether `matters: false` decisions must be confirmed at merge. Decisions the work relied on can pass the merge boundary unconfirmed. Fix: state that the merge boundary covers every DEC with `matters: true` that decides a touched record (following `decides` links in reverse), and that DECs with `matters: false` are listed for a glance and never asked.
- [MEDIUM] (intent review 4, concept 5.1(2), 7.5, 11 1a exit criteria) Each confirmed example "becomes an acceptance test linked by `verified_by`", and a derived "covered" state exists, but nothing enforces or reports that link: the 7.5 merge report lists agent-relayed approvals, fidelity and verification state but no requirement whose confirmed examples have no `verified_by` test, so the examples-to-tests leg of the translation chain is never checked. Fix: add a non-blocking line to the 7.5 merge report (and to the session brief and status line) listing touched requirements that are confirmed but not covered, with the uncovered EX ids, and add "confirmed examples without a `verified_by` test" to the `plumb check` findings.
- [MEDIUM] (intent review 4, concept 6.2 step 3) Trigger-1 detection flags only prompts that match a confirmed record and contain one of a fixed list of change words (instead, remove, also, don't, ...); a prompt that contradicts a confirmed example without those words (for example "make the line show percentages" against a confirmed "SR 12/14" format) is never flagged, the agent is not told to read back and ask, and real intent changes can slip into code silently. Fix: also inject the matched confirmed records' examples whenever term overlap is high, with a one-line instruction to compare, or say in the plumb skill that the agent checks any injected confirmed record for contradiction; keep the keyword list as a ranking signal, not a gate.
- [LOW] (intent review 4, concept 11 sub-project 2) Escalation triggers, set approvals and the `plumb intent`/`example`/`decide` helpers are all in sub-project 2, so during the dogfooded sub-project 1 plumb never suggests escalation and escalated work has no set-hash approval path; consistent with D6, but decision 2's escalation half is unavailable in the first dogfood period. Fix: say (here or in section 11) that during 1a/1b escalation is manual: the owner asks for a spec, and per-record approvals stand in for the set approval.
- [LOW] (intent review 4, concept 6.4, 6.6) Proposed DECs that do not "matter" never appear in the end-of-turn summary (only read-backs and examples get "proposed" lines), so an assumption the agent turned into a DEC rather than an INT assumption is visible only on demand, and the owner may never see a choice made in their name. Fix: show one "proposed DEC-###: assumed A; B also fits" line in the summary for every DEC created in the turn, whatever its `matters` flag, without making it a question.

## SP1 spec and plan intent review (2026-10-06, docs/specs/sp1-grounding-loop.md, docs/plans/sp1-plan.md)

The HIGH findings of this review were fixed in the same change. Dogfooding now starts in the
first hour: records at D0, `SR:` trailers from the contract-phase commit, the trailer check at
D1, each hook installed at D2 as it lands, and the map at D3. Dogfooding also comes before
review. Every lane's must items fit in 150 min. Approvals, the merge boundary and trailers
moved to the TRUST lane (formerly BRIDGE), and the log moved to the contract phase. The
importer and the JEV adapter became stretch items. The drop order never removes the R1 merge
rule, the trailer check, the approval guard or the dogfood checkpoints (plan 4, 6, 12; spec 3
F13, 14.1). This also settles the round-2 LOW "Dogfooding was only an exit criterion ... kept
here so the plans follow that order".

The entries below are recorded and not fixed. Different verifiers raised some findings twice;
each one is kept so every review can be traced. The plan task numbers below are the ones the
findings cited: C12 is now TRUST T8 (a 1b item, no longer stretch), V10 is now VERIFY V13, H9 is now HOST H11, and B4 is now
TRUST T7.

- [MEDIUM] (SP1 intent review, plan C12 vs plan 11.3 and spec 14.2 item 9) `plumb claims check` is a stretch item, so it is dropped first, yet the dogfood gate and the definition of done both require it to accept the dogfood commits. The KEEP item is at risk and the plan contradicts itself; the concept also defers claims to 1b. Fix: make C12 a must item, or change the dogfood gate and DoD to say that the claims check is recorded in followups when C12 is dropped.
- [MEDIUM] (SP1 intent review, spec 10 and 6.4) A coding turn runs the stop hook twice (block, then with `stop_hook_active`), so the budgets give prompt 600 + stop 800 + stop 800 = about 2.2 s, while the table claims only prompt + stop under 1.5 s. If the host ignores `async`, each synchronous post-edit hook adds about 300 ms per edit. Every per-hook budget is also above the concept's p95 target of 500 ms. Fix: budget the second stop invocation as a cheap path that reuses this turn's state from `turn.json`, and make the benchmark measure a coding turn of prompt, stop-block, stop-summary and N edits.
- [MEDIUM] (SP1 intent review, spec 6.2 step 5, plan H9) The only part of D2's "the tool suggests when to escalate" in sub-project 1 is a stretch item, dropped first. The concept defers escalation triggers to sub-project 2, so this is not a contradiction, but D2's suggestion can be absent until then. Fix: make H9 a must item; it is a 10-minute heuristic on data the prompt hook already has.
- [MEDIUM] (SP1 intent review, spec F4 and 5.6) Under F4 the committed `prompt` event is written by the agent-invoked `plumb relay` in the same call as the approval, not by the prompt hook at prompt time, so the committed record no longer shows that the prompt existed before the agent acted. R2's honest trust model covers this and F4 is a DEC with `matters: true`. Fix: have the prompt hook append committed digest-only events (one line) at prompt time, or record in the DEC for F4 that the backstop is the merge-boundary list of relayed approvals.
- [LOW] (SP1 intent review, spec 7.4 freshness with 6.4 stop block) If the content environment identity cannot be computed, no node is ever fresh, and the stop hook blocks every coding turn to run tests that can never become fresh. Owner interruptions are unaffected, but it is per-turn noise. Fix: after a run whose identity is null, do not re-block within the session; show `tests ?` in the summary instead. (The 1a freshness rule now compares `env_key` only; the issue returns once the content identity, VERIFY V9, is built.)
- [MEDIUM] (SP1 intent review, plan C12 and V10, spec 7.5 and 15) Two KEEP items are stretch work outside the morning minimum: the claimed-vs-declared claims check (C12) and the owner waiver (V10), whose use in place of a full rerun is deferred to sub-project 3. The concept also defers both (1b and sub-project 3), so this is a deferral, not a drop, but the dogfood gate still requires `plumb claims check` when C12 is dropped. Fix: make C12 a must item (a small extraction of `coherence/register/claims.py`), or make the dogfood gate say what happens when it is dropped; record that the owner-waiver targeted rerun lands in sub-project 3.
- [MEDIUM] (SP1 intent review, spec 10 and 6.4; work-order 2-second rule) This repeats the 2.2 s entry above: the real hook total of a coding turn without fresh evidence is prompt + stop(block) + stop(summary), about 2.2 s, which is over the 2 s rule, and `bench_hooks` measures prompt + stop only once. Fix: budget and benchmark the turn shape that actually occurs, and make the second stop reuse the first stop's state from `turn.json` so it costs only interpreter start plus one read.
- [MEDIUM] (SP1 intent review, spec F10 and 7.5 vs R3) F10 narrows R3: a previously passing test whose own source hash changed since that pass is not a regression. So an agent that edits an existing passing test, which then fails, never triggers the regression trigger, and the test is shown only as "not yet passing". R3 exempts only a new test that starts red. Fix: treat a rewritten, previously passing test that now fails as a regression unless it is a new node; at minimum, surface it at the merge boundary as "previously passing, test edited, now failing".
- [MEDIUM] (SP1 intent review, spec 15 and the D9 row of spec 2) The spec defers the fork plan to "a separate document" and none exists in `docs/`; earlier rounds flagged it three times. Decisions 9 and 10 remain unserved. Fix: write `docs/plans/fork.md` (maintenance-mode trigger, extraction order, importer run, switch-over) and link it from spec 15 and concept 10.
- [LOW] (SP1 intent review, spec 6.2 step 5, plan H9) This repeats the escalation entry above at low severity: if H9 is dropped, the dogfooded tool never suggests escalation. That matches concept 11 (sub-project 2). Fix: keep H9 near the top of HOST's stretch order, or say in the skill that escalation is manual during sub-project 1.
- [MEDIUM] (SP1 intent review, spec 12.1 and 12.2; plan C10, B4, C11, V7, V8) The contracts are not precise enough for two cross-lane needs. (a) `fidelity unjudged` is computed in the judgment lane (B4, `judgment/fidelity.py`), but `validate --merge`, HOST's `StatusSnapshot.fidelity_unjudged` and the repin rule (5.5) all need it, and no factory function or protocol method exposes it, so each lane may reimplement it differently. (b) VERIFY's evidence `test_hash` and the F10 regression rule depend on `CoreAPI.hash_target(Target(test=...))`, which needs test-node hashing (C11, not a must item). Without it, `hash_target` for test and symbol targets is undefined, and so is the regression rule. Fix: add `unjudged(core, ids) -> Mapping[str, bool]` or a `CoreAPI.fidelity_state` method to the frozen contract with one owner. Then either make test-node hashing a must item, or specify in 12.1 that `hash_target` for a `test` or `symbol` target falls back to whole-file hashing until it lands and that VERIFY treats a whole-file `test_hash` that way.
- [MEDIUM] (SP1 intent review, spec 8.2 `judgment.hook_timeout_ms` vs 10 and 11) With the JEV backend enabled, the prompt hook calls `intent_change` with an 800 ms timeout. That is longer than the prompt hook's whole 600 ms budget, before the roughly 225 ms interpreter start is counted. Either the deadline skips the JEV call every time or the per-turn total is exceeded, so the budgets contradict each other. Fix: set the hook JEV timeout to the hook's remaining deadline, for example min(800, deadline minus elapsed), or give the prompt hook a separate, benchmarked budget when JEV is enabled.
- [MEDIUM] (SP1 intent review, plan C12, plan 11.1 step 7, 11.3 and 13, spec 14.2 item 9) This repeats the first claims entry above: the dogfood gate and the definition of done require `plumb claims check`, a stretch item dropped first, and give no fallback. Fix: make the trailer-only check (`check-msg`, a must item) the dogfood gate when the claims check is dropped and record the claims check in followups, or promote it to a must item once the lane rebalance frees time.

## SP1 spec and plan intent review, round 2 (2026-10-06, docs/specs/sp1-grounding-loop.md, docs/plans/sp1-plan.md)

The HIGH findings of this round were fixed in the same change:

- The grounding loop now runs on plumb's own work during the build; installing it is no
  longer treated as running it. The coordinating Workflow session is not rooted in
  `C:/coding/plumb`, and its subagents do not receive the prompt and stop events, so
  installing the hooks at D2 alone would never run them. From D2 on, every unit of the
  coordinator's work on `main` (later merges and checkpoints, integration items, completion
  steps, review fixes) is a loop step. A loop step is either a headless Claude Code session
  rooted in plumb's repository (host mode) or the real hook entry points driven around the
  work item (driven mode). Gate L requires evidence that the loop ran: the prompt entry,
  `status.json` rewritten, a `test-run` entry after each stop block asking for the covering
  tests, and a line in `docs/sp1-loop-log.md`. The handoff states which parts ran, in which
  mode, and that lane work was built outside the loop (plan 1, 4.1, 4.3, 4.4, 4.5, 11, 12,
  13; spec 1, 2, F13, 14.1, 14.2 item 9).
- The 9-hour box is anchored to an absolute deadline, 2026-10-06 08:00 local (the request
  came on the evening of 2026-10-05; the repository was initialized at 23:25 +11:00). Last
  must merge 06:30, clock rule 07:15 (deadline minus 45 min), handoff by 07:45. The slack is
  recomputed from a 01:00 phase-0 start: about 35 min before the clock rule, not 3 h 20 min.
  The lane stop rule's must-item extension ends at 06:30 (plan 1, 12, 13, 14; spec 1, 2,
  14.2 item 11).

The entries below are recorded and not fixed. Different verifiers raised some findings twice;
each one is kept so every review can be traced.

- [MEDIUM] (SP1 intent review 2, spec 7.4 and 7.5; plan 6 tiers, V9, V10, V13, T7, T8; plan 12 drop order) Several KEEP items sit in the droppable 1b or stretch tiers: the content environment identity (V9), the flaky same-tree rerun (V10), the owner waiver (V13, stretch), advisory fidelity (T7) and the claims check (T8). Under the drop order they are cut first if time runs short. Concept 11 also puts most of them in 1b, so this is a deferral rather than a contradiction. Spec 14.2 item 9 and plan 4.4 also require `plumb claims check` to accept the latest commits, although T8 is a droppable 1b item. Fix: make the claims check (T8) and fidelity (T7) part of the protected morning minimum, or make the DoD claims-check item conditional on T8 being built. Record any KEEP item left unbuilt in followups.md explicitly as a KEEP item still owed.
- [MEDIUM] (SP1 intent review 2, plan 4.4 last bullet; spec 5.6 relay stated-set check; spec 14.1 last paragraph) The handoff tells the owner that saying "ok" in a session confirms everything they agree with. Under spec 5.6, a relay approves only records in the previous reply's stated set or records named by ID in the quote. The stated set holds only records created or edited in that one turn, so a bare "ok" in a fresh morning session would confirm almost none of the roughly 50 proposed records, and the promised one-line path would fail silently. Only `plumb approve --proposed` works as advertised. Fix: offer `plumb approve --proposed` (owner terminal) as the one-line path in the handoff. Alternatively, define a stop or brief step that states the full proposed set so a following "ok" covers it, or tell the owner to name the IDs.
- [MEDIUM] (SP1 intent review 2, plan 1 four parallel lanes plus D0, plan 3.3 and 9 runner tests, plan 14 risks) The schedule assumes four lane agents run concurrently on a 2-core machine that already has other work running. Each lane runs pytest at every merge point, and VERIFY's runner tests start real pytest subprocesses. CPU contention can stretch every lane past its estimate, and the plan does not account for it beyond "run one at a time per lane". Fix: add a machine-wide limit of one or two pytest processes across all lanes (for example a shared lock file around lane gate runs). Alternatively, start CORE, TRUST and HOST in parallel and VERIFY's runner-heavy tests later, and add a 30-minute contention allowance to the slack. (The slack after this round's deadline fix is about 35 min, so this allowance would use nearly all of it.)
- [LOW] (SP1 intent review 2, spec 5.4; plan C2 vs C10; plan D1 whole-file links) In the must tier, link ends are hashed as whole files, so any edit to a module or test file makes every link into it stale. On plumb's own records this produces noisy drift signals that the agent will tend to clear with mass `repin --all-stale`. That weakens the staleness signal the owner cared about ("the hash is important for staleness detection"). Fix: keep C10 as the first 1b item in CORE, and have phase 3 switch plumb's own links to symbol or test-node ends when C10 lands (partly planned). If C10 is not built, this noise risk stands.
- [MEDIUM] (SP1 intent review 2, plan T8 tier 1b vs plan 4.4 and 13; spec 14.2 item 9) `plumb claims check` (T8) is a 1b item, which the plan drops before phase 3. But the phase-3 dogfood gate (4.4) and the definition of done (spec 14.2 item 9) require it to accept the latest commits. Phase 3 has a higher protection priority than 1b, so the gate can depend on a command that was legitimately dropped, which puts the KEEP claims-check item at risk. Fix: move T8 into TRUST's must items (20 min), or make the 4.4 and 14.2 checks conditional on T8 being built and record its absence here.
- [MEDIUM] (SP1 intent review 2, spec 14.1 last paragraph; plan 4.4 last check) This repeats the "ok" entry above. In a fresh morning session the stated set is empty, so a bare "ok" confirms nothing, and the one-line path offered to the owner (R1: "The owner confirms them in one line whenever they choose") would not work as described. Fix: name `plumb approve --proposed` (owner terminal) as the one-line path, or give `plumb status` or the brief a way to put all proposed records into the stated set, so that one "ok" after that reply works.
- [MEDIUM] (SP1 intent review 2, spec 3 F10 and 7.5) F10 narrows R3. A previously passing test whose body was edited and now fails is not treated as a regression, so it never interrupts the owner. This reads R3's test-first exemption reasonably, but it is not the ruling's literal wording. It also lets an agent's edit to an existing test hide a real regression. Fix: keep F10, but show an edited-then-failing previously passing test as its own drift line (for example `edited test now failing`) in the summary and at the merge boundary.
- [MEDIUM] (SP1 intent review 2, spec 10 budgets: prompt 600 ms, stop 800 ms, total 1.5 s) The per-hook budgets are above the concept's stated p95 target of 500 ms (concept principle 3). The difference is not listed as a refinement in spec section 3, although that section claims to list every refinement of the concept. Fix: add an F-row that explains the budgets, given the interpreter start of about 225 ms on this machine, or tighten them to the concept's target.
- [MEDIUM] (SP1 intent review 2, spec 7.5, plan V13 stretch; concept 11 lists owner waivers in 1b) The spec moves the owner waiver from the concept's 1b tier to a stretch item, and defers its use to sub-project 3 (inside F13). The KEEP failure-policy item ("owner-waiver targeted rerun") is therefore only partly present in sub-project 1. Recorded here as a deferred KEEP item: the owner waiver is still owed, and its use in place of a full rerun belongs to sub-project 3 (spec 15).
- [MEDIUM] (SP1 intent review 2, spec 15; docs/ has no fork plan) The spec defers the pi-agent-factory fork plan to "a separate document", but no such document exists in the repository. Decision 9 says "A fork plan is required", and decision 10 asks to plan "the kind of pi-agent-factory fork that is about to happen". Fix: name the expected path (for example `docs/plans/fork-plan.md`) and make sure the workflow produces it. Until then it stays open here.
- [LOW] (SP1 intent review 2, spec 6.4 "A turn with no changes prints nothing") A turn with no changes gets no summary, which differs slightly from decision 5's "a short alignment summary at the end of each turn". Fix: accept it as noise reduction and record it as a DEC, or print a one-line `plumb: no changes` summary.
- [LOW] (SP1 intent review 2, plan 1 orchestration paragraph "this plan does not grant it") The owner is unavailable overnight. If the coordinating session does not already have the workflow opt-in, implementation stalls and the morning deadline is lost. Fix: confirm that the coordinating session already has the opt-in, or fall back to sequential execution in one session.
- [MEDIUM] (SP1 intent review 2, plan 4.1 and gate 4.3 D2) The coordinating Workflow session runs with its working directory in pi-agent-factory, and its lane, phase-2 and review agents are its subagents. Hooks installed in `C:/coding/plumb/.claude/settings.json` are therefore unlikely to fire for any of them, so "phases 2 to 4 are made with plumb in the loop" could not happen as written. This round's HIGH fix addresses it (loop steps, plan 4.5, with gate L); the entry is kept here for traceability. If host mode cannot run, the loop runs only in driven mode during the build, and it first runs live in the owner's next interactive session on `C:/coding/plumb`. The handoff must say so.
- [MEDIUM] (SP1 intent review 2, spec 14.2 item 9 and plan 4.4 vs T8 tier 1b in plan 8 and 12) This repeats the claims-check entries above. If T8 is dropped, the phase-3 gate cannot pass and the definition of done cannot be met. The documents are inconsistent, and a KEEP item can silently disappear. Fix: make the claims check conditional in 14.2 and 4.4 ("if T8 was built; else recorded in followups"), or protect T8 above review scope in the order of protection, since it is a KEEP item and takes only 20 minutes.
- [MEDIUM] (SP1 intent review 2, spec 7.4 and 7.5 `test_hash` and F10 vs spec 12.1, 12.2 and plan C6, C10) VERIFY's must items (V7) need a test-node source hash for freshness and for the regression rule. The only contract that hashes a `Target(test=...)` is `CoreAPI.hash_target`, which CORE implements for whole files only in the must items (C6); test-node hashing is CORE 1b (C10). The contract does not say who computes `test_hash` before C10 lands, or what `None` means. Two lanes could implement this in incompatible ways: VERIFY with its own ast code, or treating `None == None` as unchanged. That would misclassify a rewritten red test as a regression, or the reverse. Fix: add to spec 12.4 a frozen phase-0 primitive `test_node_digest(path, nodeid) -> Hash | None` (in normalize.py or a new hashing primitive), used by both VERIFY and C10, and specify that a `None` test_hash never yields a regression or fresh reuse.
- [MEDIUM] (SP1 intent review 2, spec 10 "Per-turn synchronous hook total (prompt + stop) under 1.5 s" and 6.4 step 4) On every coding turn the stop hook blocks once, the agent runs the tests, and the stop hook runs a second time. The synchronous hook cost of such a turn is therefore prompt + 2 x stop (600 + 800 + 800 ms = 2.2 s at budget), which breaks the work order's "well under 2 seconds" rule. The test map, the bench script and `test_latency_subprocess` measure only prompt + stop. Fix: budget and benchmark the blocked-turn path (prompt + stop(block) + stop(summary)). Make the second stop reuse the first stop's computed state from `turn.json`, with a much smaller budget such as 300 ms, and assert this in `test_latency_subprocess` and `bench_hooks.py`.
- [MEDIUM] (SP1 intent review 2, plan 5 phase 0, 55 min) Phase 0 blocks all four lanes. In 55 minutes it must deliver all of spec 12.1, five primitives (including the locked hash-chained log with a concurrency test), the dispatcher, four fakes, the conftest fixtures and the conformance suite, all test-first, on a 2-core machine. An overrun delays every lane one for one, and the plan has no rule that cuts phase-0 scope. Fix: split phase 0 into a minimal freeze (contracts.py, normalize, paths, log.py, dispatcher and fakes), after which the lanes start, and make the conformance suite and config caching a coordinator follow-up while the lanes run. Alternatively, add phase 0 to the clock and drop rules. (With this round's absolute deadline, a phase-0 overrun now comes directly off the slack of about 35 min.)
- [LOW] (SP1 intent review 2, plan 3.3 and 11.1 lane merges with `git merge --no-ff`) Lane-to-main merges are not run through `plumb validate --merge`, and every record stays proposed. This is correct under R2, but the plan never states that lane integration merges are not owner merge boundaries, so a later reader could read it as bypassing R1. Fix: add one sentence: lane merges into main during sub-project 1 are internal integration steps, not owner merge boundaries; the owner's merge boundary is the morning handoff, where `validate --merge <phase-0 commit>` exits 4 by design.

## SP1 spec and plan intent review, round 3 (2026-10-06, docs/specs/sp1-grounding-loop.md, docs/plans/sp1-plan.md)

The HIGH findings of this round were fixed in the same change:

- The regression rule now matches R3 exactly. A node that has an earlier `passed` or `flaky`
  `test-run` entry and now fails is a regression whatever happened to its source since. The
  `test_hash` condition and "or a rewritten one" are gone. When the test source changed since
  the pass, `NodeEvidence.test_changed_since_pass` adds the note `test source changed since
  the pass` to the regression instruction; the note never suppresses the trigger. Only a node
  id with no earlier passing evidence is `not yet passing` (spec F10, 6.4 trigger 3, 7.5,
  12.1 `NodeEvidence`; plan SR-020 and the `test_policy.py` test names). This supersedes the
  round 2 MEDIUM entry "F10 narrows R3". It also narrows the round 2 entry on
  `test_node_digest`: a `None` `test_hash` still blocks fresh reuse, but it no longer affects
  the regression rule.
- The fork plan exists: `docs/plans/fork-plan.md` (D9, D10). It sequences the current
  integration batch landing (F0), maintenance mode (F1), extraction with a resync to the
  landed baseline (F2), import (F3) and the switch (F4), each with a gate. The SP1 plan adds
  coordinator task F0 (plan 11.4: keep its "State at handoff" section current and link it in
  the handoff), lists it as never dropped, and adds it to the definition of done. The spec's
  D9 row and section 15, and concept 10, point to the file. This resolves the round 2 MEDIUM
  entry on the missing fork plan.

The entries below are recorded and not fixed. Different verifiers raised some findings more
than once; each one is kept so that every review can be traced.

- [MEDIUM] (SP1 intent review 3, plan 4.4, 8 T8 tier 1b, 12 cutting order; spec 14.2 item 9) The claims check (T8) is a 1b item, and the cutting order drops it before the dogfood phase. Yet the phase-3 dogfood gate (4.4) and the definition of done (spec 14.2 item 9) both require `plumb claims check` to pass. Phase 3 has the second-highest protection, so its gate depends on an item that may be cut, and a KEEP item ("`SR:` commit trailers and claims checks") could be missing from the morning build with no fallback stated. MEDIUM because concept 11 also defers it to 1b. Fix: move T8 (20 min) into TRUST's must items (TRUST has 20 min of headroom: 130 of 150 min) and add it to the "never dropped" list, or state in 4.4 and 14.2 that the claims check is conditional on T8 and is listed in the handoff when missing.
- [MEDIUM] (SP1 intent review 3, spec F13 and 7.5 owner waiver as a stretch item; plan V9, V10, T7 at 1b, V13 stretch) Three KEEP items can be cut under time pressure: the full environment identity (V9), the flaky rerun (V10) and fidelity packets (T7) are 1b, and the owner waiver is a stretch item, below the concept's 1b tier. F13 gives no reason tied to the owner's words for that demotion. Fix: keep the owner waiver at the concept's 1b tier (10 min), and in the handoff list each KEEP item that is not built as a named gap against the owner's KEEP list, not only as a followup.
- [MEDIUM] (SP1 intent review 3, plan 1 and 4.5, "Lane work in the worktrees stays in workflow subagents and runs without the loop") Most of plumb's code is written by lane subagents outside the grounding loop; only the coordinator's merges and fixes run as loop steps. After D1 and D2 the lanes rebase onto `main`, so their worktrees contain `.claude/settings.json` and `.plumb/`, and their remaining segments could run in host or driven mode too. The plan is honest about the gap. Fix: after each lane's post-D2 rebase, run its remaining segments (1b items at least) as loop steps in that worktree, in driven mode if host mode is not available, and count them in the handoff's "Loop exercised during the build" section.
- [MEDIUM] (SP1 intent review 3, spec 6.4 step 4 "at most one block per turn") The stop hook blocks at most once per turn, and the "covering tests not run" block comes first. In a coding turn that also touches an unconfirmed `matters: true` DEC, the second stop runs with `stop_hook_active` and cannot block, so the trigger-2 instruction may never reach the agent, and the spec does not say whether the DEC is then recorded as asked in `turn.json`. A trigger-2 question can silently drop or be asked a turn late. Fix: when a test-run block happens first, carry any pending trigger-2 or trigger-3 instruction into the summary's `questions:` line on the second stop, or into the next prompt hook's output; mark it asked only once printed; add a test for a turn that has both.
- [LOW] (SP1 intent review 3, spec 9 CLI reference, about 25 top-level commands plus aliases) The command surface is wide for "a lighter, more elegant and interactive way to leverage coherence": approve/relay/revoke, validate/check, tests/map/verify, hooks/install, fidelity/judge/judgment, why/impact/brief/drift/status/log. The F7 aliases double the vocabulary the skill and the owner must learn. Fix: keep the aliases out of the help text and the skill, and document a core set of about 8 commands (init, new, link, status, brief, validate, tests run, approve) as the everyday surface.
- [LOW] (SP1 intent review 3, plan 1 phase 1: four parallel lanes, each running `uv sync`, pytest with real subprocess runner tests, and ruff) Four lanes run at once on a 2-core machine with other work running. The estimates assume lane test cycles do not contend for CPU, which puts the 06:30 and 07:15 cutoffs at risk. Fix: run lane gates (whole-lane pytest) one at a time across lanes, for example behind a shared lock file, and keep focused tests for iteration.
- [MEDIUM] (SP1 intent review 3, plan T8 tier 1b vs 4.4 dogfood checks and spec 14.2 item 9) This repeats the claims-check entry above. If T8 is cut under the drop order, the dogfood gate cannot pass, and a KEEP item can silently disappear from the morning build. Fix: promote T8 to M (20 min), or make the dogfood check and DoD item conditional, recording the missing claims check in followups and at the top of the handoff.
- [MEDIUM] (SP1 intent review 3, plan V9, V10 at 1b and V13 stretch; spec 7.4, 7.5) The content environment identity, the flaky rerun and the owner waiver are all droppable; the must build pins evidence only to the cheap `env_key`. This matches concept slice 1a, but a KEEP item could be missing in the morning with no notice beyond followups. Fix: keep the drop order, but name any of V9, V10 or V13 that is not built at the top of the handoff as a KEEP-list item not yet delivered.
- [MEDIUM] (SP1 intent review 3, plan H11 stretch, T10 stretch) The escalation suggestion (decision 2: "the tool suggests when to escalate") and the importer (decision 7: "the importer reads pi-agent-factory's register") are both stretch items, so the first build may contain neither. Concept roadmap sub-projects 2 and 5 and decision 6's first scope justify this. Fix: list both as deferred owner-decision items in the handoff if they are not built.
- [MEDIUM] (SP1 intent review 3, plan 4.5 lane work outside the loop) This repeats the "build with it" entry above from another verifier. Only the coordinator's work on `main` from D2 on runs as loop steps, so "build with it" (decision 6) is only partly met. Fix: keep the honest handoff statement, and consider running at least the phase-2 conformance fixes and HIGH review fixes in host mode, so the loop sees real code changes, not only merges.
- [LOW] (SP1 intent review 3, spec 6.4 "A turn with no changes prints nothing") A no-change turn shows no summary, a slight departure from decision 5's "a short alignment summary at the end of each turn". Fix: optionally print a single `plumb: no changes` line, or keep it and record it as a DEC. (Also raised in round 2.)
- [MEDIUM] (SP1 intent review 3, plan 4.3 D2 gate at H8, plan 1 wall-clock table, plan 12 "Never dropped"; spec 14.1) The D2 gate at H8 requires the whole loop: a stop block asking for the covering tests and the `test-run` entry it caused. That needs VERIFY's `plumb tests run` and `open_verify`, which merge only at V8, scheduled at about 04:55, at or after the HOST merge points (04:30 to 04:55). Without VERIFY the stop hook degrades to `verification: unavailable` and never blocks for tests, so the H8 gate cannot pass; since D2 is never skipped, a late VERIFY lane stalls the checkpoint chain and every loop step after it. Fix: make the full-loop part of the D2/H8 gate depend on V8 (before V8, check only the prompt and stop entries plus the summary, and move the stop-block and `test-run` check to the first loop step after D3), or schedule the VERIFY merge point before H8.
- [MEDIUM] (SP1 intent review 3, plan 8 T8 tier 1b, 4.4, 13; spec 14.2 item 9) A third verifier raised the claims-check conflict above. If T8 is cut, the dogfood gate and the definition of done cannot pass, and the KEEP item is missing from the morning deliverable. Fix: promote T8 to an M item (20 min, within TRUST's 20 min of headroom under its 150-min cap), or make 4.4 and 14.2 conditional on T8 and list it in followups otherwise.
- [MEDIUM] (SP1 intent review 3, spec 5.6, 12.1, 12.2, 12.4 `tests/fakes.py`, 12.5) Some cross-lane contracts are not precise enough for independent implementation: (1) the `revocation` event payload is not specified, although TRUST writes it and CORE's `confirm.py` reads it; (2) the spec does not say whether `FakeCore.status` derives confirmation from the approval and revocation events in the real log or returns canned values, so TRUST's `test_merge_passes_after_approval` and `test_approve_pins_current_hash` can pass against a fake whose reading differs from CORE's real derivation; (3) HOST's snapshot and stop summary show `fidelity unjudged`, but no factory function in 12.2 provides it (only `build_packet`); (4) the direction of `records_for_paths` (path to IDs, or ID to paths) is not stated. Fix: add the revocation payload to 5.6 and 12.5 (for example `{records:[{id}], by, prompt_digest, quote, quote_digest}`); put the confirmation derivation in a phase-0 primitive used by both FakeCore and CORE, or add a conformance test comparing FakeCore and `open_core` status on the same log; add `unjudged(core) -> tuple[str, ...]` to 12.2 with its degrade rule; document the `records_for_paths` mapping direction.
- [MEDIUM] (SP1 intent review 3, plan 1 wall-clock table, 4.5, 11.1) From D2 on, every coordinator merge is a loop step (a headless Claude session, or about six hook invocations plus a test run, a log line and gate L). Yet five merge points (C8, H6, H7, H8, V8) and their checkpoints are scheduled serially in about 40 min (04:15 to 04:55), and phase 2 holds about 10 loop steps in 45 min. The coordinator is a single serial bottleneck with no loop-step overhead budgeted, on a 2-core machine shared by four lanes and pi-agent-factory's integration, with about 35 min of slack before the 07:15 clock rule. Fix: budget the loop-step overhead explicitly (for example 5 min in driven mode); let the coordinator batch merges that land in the same window into one loop step; set a probe timeout on host mode at H6 that falls back to driven mode at once; stagger lane gate runs so that at most two pytest processes run at a time.
- [MEDIUM] (SP1 intent review 3, plan 4.5 host mode command) Host mode runs `claude -p ... --permission-mode acceptEdits`. That mode auto-accepts file edits, but Bash commands still need permission, and headless mode cannot prompt for it. The session's agent therefore cannot run `uv run plumb tests run --changed` when the stop hook blocks, nor `git commit`, nor its own tests, so host mode will likely fail gate L or stall, with no time limit before the driven-mode fallback. Fix: pass explicit tool allowances (for example `--allowedTools "Bash(uv run plumb:*)" "Bash(uv run pytest:*)" "Bash(git:*)"`) or the matching `permissions.allow` entries, and set a wall-clock timeout on each host-mode session, after which the step reruns in driven mode.
- [LOW] (SP1 intent review 3, spec 10 hook budgets vs concept 3 principle 3) The concept sets a per-hook p95 target under 500 ms; the spec's budgets are 600 ms (prompt), 800 ms (stop) and 900 ms (session start), with a 1.5 s per-turn total. This still meets "Per-turn overhead is seconds, not minutes" and "well under 2 seconds", but spec section 3 does not list it as a refinement, so the spec and the concept disagree silently. Fix: add an F14 row recording the change from the 500 ms target to per-hook budgets, with the reason (about 225 ms of interpreter start on this machine), or state the 500 ms figure as an aspiration the benchmark reports against. (Also raised in round 2.)
- [LOW] (SP1 intent review 3, plan 3.3, 4.4, 11.1) Lane merges into `main` use plain `git merge --no-ff` without `plumb validate --merge`. That is necessary overnight, since every record stays proposed, but the plan never says these internal merges are not merge boundaries in R1's sense, and phase 3 calls the full run "the owner's merge boundary for sub-project 1". A verifier or the owner could read this as R1 being bypassed. Fix: state once in the plan that lane-to-main merges are internal integration and that the sub-project 1 merge boundary is the owner's morning `plumb validate --merge <phase-0 commit>` (expected to exit 4 until the owner confirms); optionally run `validate --merge` at each loop-step merge in report-only mode and log its exit code in `docs/sp1-loop-log.md`. (Also raised in round 2.)
- [LOW] (SP1 round 3 fixer's note, spec 7.5) With the regression rule keyed by node id, a passing test that is renamed or deleted is not a failure, so it is not a regression under R3; its passing evidence simply stops being matched. That is R3's literal scope, but renaming or deleting a failing test leaves no visible signal. Fix: have `plumb tests run` or `plumb drift` list previously passing node ids that are no longer collected (`removed after passing N`) as a logged drift line, never as an interruption.

## SP1 lane CORE (2026-10-06)

Lane CORE built K1 to K7 (MUST) on branch `lane/core`; no SHOULD item was built in phase 1.

Unfinished (SHOULD, for `core-rest` in phase 3, in the plan's drop order):
- KS1 index and hash caches (`.plumb/cache/index.json`, `hashes.json`): not built. Measured on
  a scratch repository with 41 records: `plumb brief`, `status` and `validate` each take about
  420 ms end to end (bare interpreter about 160 ms), because every call parses every record
  and hashes every link end. HOST's hooks will pay this until KS1 lands.
- KS2 `plumb new`, `plumb show`; KS3 `plumb drift`, `plumb why`, `plumb log`: routed to
  `plumb.commands`, which answers `plumb: '<command>' is not available in this build` (exit 2).
- KS4 symbol and test-node ends: `plumb link` rejects a `path::name` target (exit 2). A
  hand-written `test: path::name` end hashes the whole file before `::` (stricter: any edit of
  that file moves the end) and is dangling only when the file is missing.
- KS5 wikilink checks and untranslated-intent warnings: not built.

Design choices made inside the spec (MEDIUM at most):
- [MEDIUM] Coverage is per named example: a `verified_by` link without `example` covers no
  specific example, so a requirement with examples is `covered` only when each example is named
  by a link. A requirement without examples is covered by any non-dangling `verified_by` link.
  Bootstrap links that name only test files will show uncovered examples until examples are
  named (`plumb link SR-001 verified_by tests/x.py --example EX-1`).
- [MEDIUM] Revocation removes the latest valid approval of the record (the revocation entry
  pins that approval's hash), so revoking a newer approval returns the record to its older
  approval, which reads as `unconfirmed edit`; with no older approval it returns to `proposed`.
- [MEDIUM] Approvals that fail their re-check never confirm: an owner approval written under
  the session marker, an agent-relayed approval without an earlier `prompt` event, affirming
  quote or matching quote digest, an entry whose digest no longer matches, and any `by: import`
  approval (F11: none are accepted in sub-project 1). `plumb validate` reports each as an
  error.
- [LOW] `plumb relay` accepts a record from the stated set only when the stated hash equals the
  record's current hash, and ignores a stated set written after the cited prompt; otherwise the
  quote must name the record.
- [LOW] `plumb relay` accepts a logged prompt whose text hashes to its digest either as raw
  UTF-8 (`approvals.prompt_digest`, the form the prompt hook should write) or normalized
  (`sha256_text`).
- [LOW] `plumb approve --proposed` outside a terminal requires `--yes` (exit 2 otherwise)
  instead of approving silently.
- [LOW] `plumb validate` adds one aggregated `proposed` warning listing records awaiting the
  owner (plan 4.1 step 4 expects it); spec 5.10 does not list it.
- [LOW] `plumb validate --merge` prints the validation findings, then the merge report; the exit
  is 1 when validation or log integrity fails, else 4 when confirmation is awaited, else 0. With
  `--json` both parts are one document `{validate, merge}`.
- [LOW] A list in `.plumb/config.yaml` replaces the default list (for example
  `verify.infra_globs` must repeat the defaults it keeps); a malformed `config.yaml` falls back
  to the defaults silently.
- [LOW] The merge report lists the deferred-by-budget tests only once VERIFY's API exposes
  them; CORE prints `verification: unavailable` until `plumb.verify.open_verify` imports.

## CORE lane review (2026-10-06)

The two HIGH findings of this review (merge-boundary log integrity read at the base tip instead
of the merge base; `plumb relay` accepting a quote cut from inside a word) were fixed in the
same change.

- [MEDIUM] (core review, src/plumb/commands.py) `cmd_validate` returns `code or merge_code`, so
  any validate error (exit 1) masks the merge boundary's exit 4 ("waits for your
  confirmation"), and a merge waiting for the owner is reported as plain findings. Scenario: one
  dangling link plus a touched unconfirmed SR makes `plumb validate --merge main` exit 1, not 4;
  plan section 12 expects exit 4 on plumb's own records, and a host adapter keying on exit 4 to
  ask the owner (R1) would miss the question.
- [LOW] (core review, src/plumb/approvals.py) `_stated` only rejects a stated.json written after
  the prompt; it does not check that the file belongs to the reply just before that prompt
  (spec 5.6), for example via `reply_after_prompt` or the session. Scenario: stated.json written
  by the stop hook in session A; in a later session the agent relays an affirming quote for a
  record in that old stated set without the quote naming it, and the stated-set check passes
  although the owner never saw that set in the reply they answered.
- [LOW] (core review, src/plumb/log.py) `_Lock.__enter__` retries with `continue` on any OSError
  from `stat()` or `remove()` of a stale lock without checking the deadline, so a persistent
  OSError other than FileNotFoundError (for example PermissionError from antivirus or ACLs)
  makes `append()` busy-loop past the 2 s budget without raising `LogLockTimeout`, and the hook
  hangs.

## CORE lane review, round 2 (2026-10-06)

The HIGH finding of this review (`plumb relay` recorded an approval from a quote cut out of a
negation or a question, such as "approve SR-001" from "no, do not approve SR-001 yet") was
fixed in the same change: the affirmation is now read in its sentence of the prompt, and a
negation before it or a closing `?` refuses the relay (exit 3). The spec 5.6 check list says
so.

- [MEDIUM] (core review, src/plumb/query.py) `relevant()` drops superseded records from term
  matching but still returns a superseded record whose ID the prompt names; spec 5.2 says
  superseded records are left out of the prompt context. Scenario: DEC-002 supersedes DEC-001;
  the prompt mentions "DEC-001" and `relevant()` returns DEC-001 first with score 100, so the
  prompt hook injects a superseded decision as current context. The brief also counts
  superseded records as 'unconfirmed edit', because `edited` is not filtered by `superseded`.
- [MEDIUM] (core review, src/plumb/approvals.py) The relay quote check accepted an affirmation
  term even when negated or inside an objection ("SR-003 is not ok" contains "ok" and names
  SR-003). Resolved by the HIGH fix above (negation before the affirmation in its sentence now
  refuses); kept here for the record. The merge-boundary glance list of quotes stays the R2
  backstop for phrasings the word list does not catch.
- [LOW] (core review, src/plumb/merge.py) `required_records` requires confirmation only for
  DECs with `matters: true`. Spec 5.10 says a DEC with `matters: false` that decides a
  confirmed record is 'reported as mattering anyway', but the merge boundary does not treat it
  so (partly tracked already as intent review 2/3/4). Scenario: an agent marks DEC-004 (which
  decides the touched SR-003) `matters: false` and never gets it confirmed; `validate --merge`
  exits 0 without listing DEC-004, and validate only warns `dec-matters` once SR-003 is
  confirmed.
- [LOW] (core review, src/plumb/merge.py) `changed_paths` uses `git diff --name-only`, whose
  default rename detection reports only the new path of a renamed file, so renaming an
  `implemented_by` or `verified_by` end does not mark its requirement as touched. Scenario:
  src/a.py (implemented_by of SR-001) is `git mv`'d to src/b.py; the diff lists only src/b.py,
  so SR-001 is not asked at the merge boundary (plain validate still reports the dangling link
  as an error). Fix: pass `--no-renames`.
- [LOW] (core review, src/plumb/validate.py) validate does not flag a `verified_by` link whose
  `example` names an example the requirement lacks (only `add_link` checks it), so a
  hand-edited link like this is silently ignored for coverage. Scenario: an SR has
  `{kind: verified_by, path: tests/x.py, example: EX-9}` but no EX-9; validate reports nothing
  and the link counts toward no example.
- [LOW] (core review, src/plumb/log.py) `append()` sets `prev` to null when the last line is
  not valid JSON, silently starting a new chain root after a corrupt line (verify_chain still
  reports the corrupt line). Scenario: a truncated last line in events.jsonl gives the next
  append `prev=null`; later readers see two chain roots and the new entry does not record why.
- [LOW] (core lane, tests/core/test_log.py) `test_concurrent_appends_do_not_interleave` failed
  once in a full-suite run on this 2-core machine under other load, then passed in the next
  full run and in 5 isolated runs. The assertion detail was not captured. It is probably the
  2 s lock budget (`LogLockTimeout`) or a Windows lock-file race when 4 threads contend. If it
  recurs, capture the traceback and check `_Lock` timing.

## SP1 dogfood bootstrap (2026-10-06)

- [MEDIUM] (bootstrap, approvals) The coordinator asked for the owner decisions quoted in the
  owner intent brief to be recorded as agent-relayed approvals, citing the brief's sha256
  (`sha256:ecd163d535b42ea9248f062649598607646a0102544cea7c179ac0140fbfb4fd`) as the prompt
  digest. The brief was logged as that prompt in `.plumb/session/prompts.jsonl` (gitignored;
  the HOST prompt hook is not built, so it was written in the hook's shape by hand), and
  `plumb relay` was tried for INT-004, INT-005, INT-006, INT-007, INT-008 and INT-009 with the
  owner's verbatim words. plumb's guard refused every attempt with exit 3 and wrote nothing.
  The reason: none of the owner's quoted words contains an affirmation term ("A / B", "C",
  "A", "Keep list looks fine", "can be the way to go", "Would be nice to ..."). Even with an
  affirmation, every record would still fail the stated-set check, because the records did not
  exist when the owner spoke and the quotes do not name them. The guard was not bypassed: no
  hand-written approval entries, no fabricated `stated.json`, and no affirmation terms added
  to the config to make the quotes pass. This follows R2 ("A confirmation requires the
  owner's explicit words"), the plan's rule that no agent writes an approval in sub-project 1,
  and the concept's "the owner's own affirming words in a prompt". All 54 records stay
  `proposed`. The owner can confirm them in one line (`plumb approve --proposed` in their own
  terminal), and `plumb validate --merge 598b079` exits 4 listing them, which is the expected
  morning question.
- [LOW] (bootstrap) The plan's INT table stops at INT-012. INT-013 (decision 9: maintenance
  mode and fork plan), INT-014 (decision 10: concept spec and plans) and INT-015 (decision 12:
  the name plumb) were added so every owner decision has an intent record.
- [LOW] (bootstrap) Links to test ends name whole test files (`verified_by` with `path`),
  because `::` symbol and test-node ends are a SHOULD item (KS4) that is not built yet. SR-010
  to SR-024 have no `implemented_by` or `verified_by` links until their lanes land on `main`.
  SR-007 links only the CORE trailer parser (`src/plumb/trailers.py`, EX-1).
- [LOW] (bootstrap) The records were written with plumb's own library (`Core.write_record`,
  `Core.add_link`) because `plumb new` is not built. Every link was pinned when it was added,
  so `plumb repin` had nothing to do.

## SP1 lane VERIFY (2026-10-06)

State: every MUST item (V1 to V6) and every SHOULD item (VS1 to VS6) is built on
`lane/verify`, test first, with `sr` markers. Merge point V6 (unlocks L-V) is commit `d6503c3`;
the SHOULD items follow on the same branch.

- [MEDIUM] (VERIFY) `plumb status` and `validate --merge` (CORE files) only show
  `full verification pending`. They do not yet show what VERIFY now knows: removed-after-passing
  nodes (`Verify.removed_after_passing()`, VS1), owner waivers (`waiver` events, VS6), deferred
  tests and the `tests ok|failing|regression` state. Wiring them in belongs to CORE or the
  coordinator (spec 7.5 asks `status` to list removed-after-passing nodes and `validate --merge`
  to list waivers).
- [MEDIUM] (VERIFY) The runner uses `sys.executable` as spec 7.3 says. In a repository where
  plumb is installed as a separate tool (not in the project's own environment), that interpreter
  lacks the project's dependencies, so its tests fail at import. Running the project's own
  interpreter with plumb's plugin on its path is a later decision.
- [LOW] (VERIFY) Selection works at test-file granularity, plus node ids named by `verified_by`
  links and `sr` markers. A file's expected duration is the sum of its known node durations
  (parametrized ids summed under their node), plus `default_test_s` once if any node is unknown.
- [LOW] (VERIFY) `full verification pending` for unknown coverage is derived from the map, not
  from the run log: a non-test Python file that no rule of the map covers is pending while its
  hash differs from the hash the latest full run recorded for it (full runs record every mapped
  file's hash). A non-Python file under a source directory with no covering test is sampled and
  flagged by `plumb tests select` and `run`, but `full_pending()` does not list it.
- [LOW] (VERIFY) The content identity (VS3) is cached under the env key plus the
  site-packages directory mtime. Without the mtime, installing a package without changing
  `uv.lock` would keep reusing a stale identity. On Windows the base interpreter hash covers
  `python.exe` and the `python3*.dll` runtime.
- [LOW] (VERIFY) Removed-after-passing nodes stay listed while their file exists, including
  tests renamed or deleted on purpose. There is no acknowledgement yet.
- [LOW] (VERIFY) The `ast` scan only knows pytest's default naming (`test*` functions, `Test*`
  classes, `test_*.py` and `*_test.py` files). Custom `python_functions`, `python_classes` and
  `python_files` settings are ignored. Literal mentions only consider string constants that
  contain `/` or `.`.
- [LOW] (VERIFY) The tree identity's `dirty` digest ignores `.plumb/`, `__pycache__` and
  `.pytest_cache`, so recording evidence or importing modules does not block the flaky rerun.
  The runner passes `-p no:cacheprovider` so runs do not write `.pytest_cache` into the
  repository.
- [LOW] (VERIFY) `src/plumb/__init__.py` maps to nearly every test in `test_map.txt`, because
  every import of `plumb.x` runs it. This is correct but noisy.
- [LOW] (VERIFY) The VERIFY lane's own tests start about 25 real pytest subprocesses. On this
  machine `tests/verify` takes about 50 to 70 s; the temporary projects turn the flaky rerun
  off except in `test_flaky.py`.
- [LOW] (VERIFY, collection-error regression fix) The runner passes
  `--continue-on-collection-errors`, so pytest's exit status for a collection error is 1, not
  2; plumb reads collection errors from the plugin report, never from the status. (Resolved by
  the aborted-run fix below: a session that ends early for another reason no longer leaves the
  selected nodes `stale`.)
- [RESOLVED, was HIGH] (VERIFY, aborted-run fix) A pytest run with no plugin report, an
  unfinished session, or an exit status other than 0 or 1 (or 5 on a selection with known
  tests) is `aborted`: every known node of the selected files counts as `failed` in phase
  `collect` (so earlier passes are regressions), `RunReport.ok` is false, `plumb tests run`
  exits non-zero, and an aborted full run never satisfies `full verification pending`. A
  selected node id the map does not know in its file (a renamed `verified_by` end) falls back
  to the file, so one stale id no longer aborts the whole selection.
- [RESOLVED, was HIGH] (VERIFY, evidence index) The reuse index keeps a digest of the first and
  last 64 KiB of `evidence.jsonl` before its offset; when a rebase, pull or branch switch
  rewrites those bytes, the index is rebuilt from byte 0 instead of resuming mid-file.
  Remaining gap (LOW): a rewrite that changes only bytes outside both windows of a log larger
  than 128 KiB, with the offset landing on identical bytes, is not detected; deleting
  `.plumb/cache/evidence_index.json` always rebuilds.
- [MEDIUM] (VERIFY, `src/plumb/verify/api.py`) The same-tree flaky rerun uses the full
  hard-limit timeout again, so one Stop-hook run can take about 2 x 1.5 x budget (about 45 s at
  the defaults), and a test-first red test is rerun on every turn. Scenario: a selection with a
  hanging or slow failing test uses its 22.5 s, then the rerun uses another 22.5 s, so the
  per-turn budget is exceeded. Recorded, not fixed.
- [LOW] (VERIFY, `src/plumb/verify/api.py`) `full_pending()` and `uncovered_sources()` look
  only at `.py` files in the test map. A changed non-Python source file that triggered the
  unknown-coverage sample (spec 7.2 `is_source`, for example `src/pkg/data.json` with no
  covering test) does not keep full verification pending. Separately, `removed_after_passing`
  lists a deliberately renamed passing test indefinitely. Recorded, not fixed.

## SP1 lane HOST (2026-10-06)

All HOST MUST items (H1 to H7) and SHOULD items (HS1 to HS5) are built. Merge points: H5 at
`1e7916a`, H7 at `f098b2a`, lane end with HS3 at `b54d9d8` (plus this note).

- [MEDIUM] (host, stop.py) The regression instruction reads `<node> passed in an earlier run
  and now fails (last run <id>)` instead of spec 6.4's `passed in run <id>`: `NodeEvidence`
  (spec 12.1) carries only `last_run`, which for a regression is the failing run, not the run
  that passed. Fix: add `last_pass_run` to `NodeEvidence` (contract change, coordinator).
- [MEDIUM] (host, stop.py) Trigger 3 blocks once per failing run (`asked["regression:<node>"]
  = last_run` in `turn.json`), and trigger 2 once per decision hash; later stops list them under
  `questions:` without blocking. `asked` lives in the session's `turn.json`, so a new session
  asks again once.
- [MEDIUM] (host, stop.py) The stop hook combines every reason of a turn (covering tests,
  trigger 2, trigger 3) into its single block, so "at most one block per turn" holds without
  dropping a trigger when the tests block comes first.
- [MEDIUM] (host, prompt.py) The prompt hook deletes the session's `touched.txt` at each turn
  start, so `touched.txt` holds the current turn's edits only. VERIFY's `tests run --changed`
  (which reads the touched lists of every session) therefore sees this turn's edits plus
  `git status`, not the whole session's history.
- [MEDIUM] (host, install.py) The skill and slash command are rendered with an agent prefix
  that differs from the hook prefix for the venv launcher: hooks run
  `"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" -m plumb`, the skill names
  `.venv/Scripts/python.exe -m plumb` (relative, because `CLAUDE_PROJECT_DIR` is not
  guaranteed in the agent's shell). Deny rules cover both the three standard prefixes and the
  agent prefix.
- [MEDIUM] (host, install.py) A foreign `statusLine` is kept and reported, never replaced, so
  plumb's status line does not show in a project that already has one.
- [LOW] (host, install.py) Deny rules follow spec 5.6 literally: `Bash(*PLUMB_AGENT_SESSION*)`
  depends on the host reading a leading `*`; `Edit(.plumb/log/**)` is resolved by Claude Code
  relative to the working directory; `MultiEdit` may no longer be a tool name in current
  Claude Code (inert). Layer 1 (the marker) holds regardless.
- [LOW] (host, stop.py) The stop hook computes the state of every record for the snapshot
  counts (about 550 ms end to end on plumb's own repository with `python -m plumb hook stop`,
  under the 800 ms budget). CORE's index cache (KS1) or an incremental snapshot would cut it.
- [LOW] (host, prompt.py) The escalation hint counts only strongly matched records (named by
  ID, or term overlap of at least 1.0); the threshold is a guess, not measured.
- [LOW] (host, prompt.py) Intent-change flags are logged to `.plumb/session/intent_flags.jsonl`
  (gitignored), a file name spec 12.5 does not list.
- [LOW] (host, hookio.py) A watchdog thread ends a hook process with `os._exit(0)` after
  1.9 s (the 2-second rule), after printing the budget notice; an atomic JSON write in flight
  at that moment leaves only a temporary file behind. The watchdog runs only from the CLI.
- [LOW] (host, install.py) `hooks uninstall` removes the git `commit-msg` hook only when it
  contains `plumb trailers check-msg` (BRIDGE writes it); a foreign hook is left alone.
- [LOW] (host, tests) HS3's in-process latency test was written after the hooks it measures,
  so it was green on its first run (no red step); the end-to-end subprocess latency test and
  the benchmark belong to phase 4.

## HOST lane review, UTF-8 round (2026-10-06)

The two HIGH findings of this review (hook stdin/stdout in the locale code page instead of
UTF-8, and a failed first write suppressing the skip notice) were fixed in the same change.

- [MEDIUM] (host review, stop.py) A regression found by the agent's own `plumb tests run`
  inside the stop-block cycle is never recorded as asked: on the second stop
  `stop_hook_active` is true and the asked map is not updated, so the next turn that touches
  the same covering selection blocks again with the same regression for the same failing run,
  and the owner can be interrupted twice for one regression.
- [MEDIUM] (host review, stop.py) Stop #1 of a blocking turn rewrites `stated.json` with a new
  `at` before the agent may run `plumb relay`. CORE's `_stated()` ignores a stated set written
  after the prompt, so a relay made after the first block loses the previous reply's stated
  set (records are refused unless the quote names their IDs).
- [MEDIUM] (host review, prompt.py) Per-turn hook latency on plumb's own repository, measured
  end to end without VERIFY, is about 800 ms for prompt (budget 600 ms) and about 900 ms for
  stop (budget 800 ms): about 1.7 s together, above spec 10's 1.5 s per-turn target though
  under 2 s. VERIFY's select/evidence will add to it; the phase-4 benchmark is likely to fail
  until CORE's KS1 caches land or the stop hook stops calling `core.status()` over all records.
- [MEDIUM] (host review, stop.py) A file deleted during the turn is dropped from the changed
  paths (the `os.stat` failure is skipped) unless the deletion went through a tracked edit, so
  deleting a linked implementation file (for example `git rm src/foo.py` through Bash) is not
  reported as touched or dangling and no covering tests are asked for. Also, `git status` has
  a hard 0.6 s timeout that silently returns no paths on a slow or large repository.
- [LOW] (host review, templates/SKILL.md) The skill tells the agent to record read-backs and
  examples as records under `.plumb/` instead of naming `plumb new` as spec 6.7 says, so
  agents may hand-write frontmatter with malformed IDs or unpinned links.

## HOST lane review, stop-deadline round (2026-10-06)

The HIGH finding of this review (the stop hook checked its deadline after the covering-tests
step had finished and then discarded every computed result) was fixed in the same change: the
deadline is now checked before a step starts, a skipped step is named in a
`check skipped (budget): <steps>` notice, and the stated set, snapshot, block and summary are
always produced from the results already computed.

- [MEDIUM] (host review, stop.py) The stop hook rebuilds `status.json` from this turn's
  covering selection only. When that selection is empty or doc-only (or the covering-tests
  step was skipped for the budget), the evidence is `{}` and `tests_state` returns `unknown`,
  overwriting the earlier snapshot's ok/failing/regression state: after a docs-only turn the
  status line shows `tests ?` (or loses a `regression N` it was showing).
- [LOW] (host review, statusline.py) Measured end to end, `plumb statusline` takes about
  500 ms here (`python -m plumb statusline --root <repo>` 504 ms against 355 ms for a bare
  `python -c pass`), above spec 10's 350 ms budget. Most of it is interpreter start-up plus
  routing through `plumb.cli`.
- [MEDIUM] (host review, CORE-owned approvals.py) `find_prompt()` keys `prompts.jsonl` entries
  by digest with `setdefault`, so when the owner repeats the same affirming prompt text
  ("ok, go on", "yes"), relay resolves the first, oldest entry. Its `at` predates the current
  `stated.json`, so `_stated()` discards the stated set and the relay is refused
  ("DEC-002 is not in the stated set of the reply before that prompt", exit 3), while the
  prompt hook's awaiting-confirmation line still prints the 12-hex prefix. Fails safe (no
  false confirmation), but the most common one-word confirmations break after first use. Fix
  in CORE: keep the latest entry per digest (or the latest whose `at` follows `stated.at`).
- [MEDIUM] (host review, stop.py, prompt.py) Commands the hooks print for the agent hard-code
  the bare `plumb` launcher (the stop block's "run 'plumb tests run --changed'", the prompt
  hook's "run plumb relay ..."), while the skill and slash command are rendered with the
  installed launcher's agent prefix (spec 6.7). With `plumb hooks install --launcher venv`
  and no `plumb` on PATH, the agent gets command-not-found and wastes a turn, or skips the
  covering tests and the relay. Fix: store the agent prefix at install time (config or an
  env var in settings.json) and render these lines with it.
- [LOW] (host review, hookio.py) The watchdog hard limit (1.9 s) and the per-hook deadline are
  measured from `start`, taken in `cli._hook` after interpreter start-up and the plumb import;
  process start-up (about 225-500 ms here) is not counted, so on a loaded 2-core machine with
  a cold cache the host can see about 2.3 s for one hook before the watchdog fires. Measured
  on the lane tree without VERIFY: session-start 794 ms, prompt 762 ms, stop 852-1018 ms,
  statusline 419 ms end to end. Partly recorded above under the latency item.

## SP1 lane BRIDGE (2026-10-06)

Built: B1 to B4 (MUST) and BS1 to BS4 (SHOULD); nothing of the lane is left unbuilt.

- [MEDIUM] (BS4) Intent-change heuristic on the 20 labelled prompts of
  `tests/bridge/fixtures/intent_prompts.json`: precision 1.0, recall 0.5 (tp 5, fp 0, fn 5).
  Every miss is a prompt that changes a requirement without naming its ID and whose term
  overlap stays under the prompt hook's strong-match threshold (1.0). The threshold was not
  tuned to the fixture; the prompt hook's "compare with the confirmed examples" line is the
  designed backstop for these (spec 6.2 step 3). Measure on real prompts from
  `.plumb/session/intent_flags.jsonl` before changing the threshold.
- [MEDIUM] (B1) With `require_trailer: true`, git's default messages for `git revert`,
  `git merge` and `git commit --fixup` carry no `SR:` trailer and are rejected; the author
  must add one (or use `--no-verify`, which bypasses the hook by design). A later revision
  could exempt messages whose changed paths are all exempt, as pi-agent-factory's
  `check_commit` does; the spec (5.9) does not ask for it, so it was not built.
- [MEDIUM] (B2, BS3) "One notice per session" is kept as one notice per 12-hour window in the
  gitignored `.plumb/session/judgment_notices.json`, because `get_backend` receives no
  session ID. The notices are exposed as `backend.notices` and printed by `plumb fidelity` and
  `plumb judgment status`; the prompt hook does not print them.
- [MEDIUM] (BS3) The JEV backend logs every judgment as a committed `judgment` event, as spec
  8.2 asks, so a JEV-enabled prompt hook appends to `events.jsonl` on each flagged turn. Not
  measured against the hook budget on the live service (the tests use a local stub).
- [LOW] (B3) A fidelity judgment covers a requirement only at tier `accept` (the host agent's
  `plumb judge`, or a JEV score accepted at a validated version); an escalated JEV score is
  logged but leaves the requirement `unjudged`, so the host agent still judges it.
- [LOW] (BS2) Symbol ends of pi-agent-factory bindings (`path` + `symbol`) are linked as whole
  files and reported as `symbol-narrowed` findings, because symbol hashing (CORE KS4) is not
  on `main`; relinking them to symbols is a follow-up once KS4 lands. A dry run of
  `C:/coding/pi-agent-factory` (HEAD 341e2a08) reads 85 SR, 24 FEAT and 22 NC records with
  958 findings (789 missing ends, 148 narrowed symbols, 8 skipped non-SR relations, 7
  verified legacy checksums, 6 membership differences); a real import into a scratch
  repository validates with no errors.
- [LOW] (B4) `plumb claims check` skips merge commits (`--no-merges`) and lists commits
  without a trailer that change non-exempt paths as `no SR: trailer`, without failing on them;
  the exit code reflects undeclared paths only.
- [LOW] (lane) The B1 and B4 code was written in one module before its tests were run red;
  later items (B2, B3, BS1 to BS3) were run red first. BS4 measures existing code.

## BRIDGE lane review (2026-10-06)

The review raised no HIGH findings. Some entries below repeat each other (the claims baseline
and the JEV hook timeout were each raised twice, at different severities); both are kept so
each finding can be traced.

- [MEDIUM] (bridge review, src/plumb/judgment/fidelity.py) `unjudged()` and `fidelity_state()`
  report every requirement with `implemented_by`/`verified_by` ends and no judgment at all as
  `unjudged`, whereas spec 8.3 defines unjudged as "an end changed and no judgment covers the
  current hashes". Scoped callers (`merge.py` passes the touched IDs) are fine, but an unscoped
  caller (`ids=None`, for example a status snapshot's `fidelity_unjudged`) lists every
  never-judged linked requirement, against the owner's "advisory fidelity judging, scoped to
  changed requirements". Scenario: 20 linked, confirmed requirements and no judgment events;
  `unjudged(core)` returns all 20 although no end changed since linking, so a status line or
  summary using `ids=None` shows 20 "fidelity unjudged" drift signals.
- [MEDIUM] (bridge review, src/plumb/claims.py) Spec 5.9 says the NC-backed baseline in
  `claims.yaml` "may only shrink", but `load_policy`/`claims_check` never enforce it, so a
  commit can add baseline entries that silently waive undeclared paths. Scenario: an agent adds
  `baseline: [{commit: <sha>, path: src/x.py, nc: NC-0001}]` to `.plumb/claims.yaml` in the same
  range; `claims check` reports `src/x.py` under "baseline" and exits 0, and nothing flags that
  the baseline grew.
- [LOW] (bridge review, src/plumb/judgment/jev.py) The hook timeout
  (`judgment.hook_timeout_ms`, 800 ms) is passed to `urllib.urlopen`, which bounds connect and
  read but not `getaddrinfo`; each hook is also a new process, so the in-process `_down` flag
  does not stop the next turn from retrying. With a key set and DNS stalling, a prompt hook can
  exceed the 2 s per-turn budget on every turn. Scenario: `backend: jev`, `TYPESAFE_API_KEY`
  set, offline laptop with a slow resolver; each prompt hook blocks for the DNS timeout (often
  several seconds) before falling back to the heuristic, and the notice is printed only once per
  12 h window, so the slowdown is silent.
- [LOW] (bridge review, src/plumb/judgment/tiers.py) `route()` skips the version-drift check
  when `validated_against` is None, so if a config drops `judgment.jev.validated_against`, JEV
  answers can reach `accept` with no validated version, whereas spec 8.2 suspends accept
  whenever the resolved version differs from the validated one. Scenario: `config.yaml` sets
  `judgment.jev` without `validated_against`; JEV returns confidence 0.95 from an unvalidated
  model version; the judgment is tier `accept` and its fidelity verdict covers the requirement in
  `latest_judgments`.
- [MEDIUM] (bridge review, src/plumb/importer/pi_factory.py) An imported ID that collides with
  an existing one is skipped as spec 8.1 says, but links, feature membership and the `feature:`
  field of the other imported records still point at that ID, so they attach to an unrelated
  local record. Scenario: importing pi-agent-factory into a repository that has its own
  SR-001..SR-025 and FEAT-001 (plumb itself); source FEAT-001 is skipped as a collision, but its
  imported SRs get `feature: FEAT-001` (plumb's own), `upstream` and `relates_to` links to SR-005
  are pinned to plumb's SR-005, and imported features list local SRs as members; validate
  reports no error. Fix: drop or report links and membership whose end is a colliding ID.
- [MEDIUM] (bridge review, src/plumb/importer/pi_factory.py) An imported feature's
  `requirements` field is the union of the feature file and the bundle, with no filter for SRs
  that exist in the target, so `--only FEAT`, or a source SR skipped as malformed or colliding,
  leaves `plumb validate` errors ("requirement X does not exist"). Scenario:
  `plumb import pi-agent-factory <src> --only FEAT` writes FEAT records naming SR-0xx that were
  not imported; `plumb validate` then exits 1 with feature errors in a repository that was clean
  before the import.
- [MEDIUM] (bridge review, src/plumb/judgment/jev.py) The 800 ms hook timeout is only urllib's
  per-socket timeout: DNS resolution and a slowly trickled response are not bounded, and `_down`
  lasts only for the current process, so every prompt-hook process tries JEV again and pays the
  timeout each turn while the service is down; the notice is still shown only once. Scenario:
  `judgment.backend: jev`, a key present and a degraded network (slow DNS, or a server that sends
  bytes slowly); each UserPromptSubmit hook can block for 800 ms to several seconds per turn,
  exceeding the per-turn latency goal and the 600 ms prompt budget on every turn. Fix: a
  persisted short circuit-breaker in `.plumb/session`, and/or running the call under a
  wall-clock deadline in a thread.
- [LOW] (bridge review, src/plumb/claims.py) `claims.yaml` baseline entries are loaded and used,
  but nothing enforces spec 5.9's "may only shrink": there is no comparison against the
  baseline at the merge base. Scenario: an agent adds a new baseline entry `{commit, path, nc}`
  to silence an undeclared path; `plumb claims check` passes and nothing flags that the
  baseline grew.
- [LOW] (bridge review, src/plumb/judgment/fidelity.py) `unjudged` (called by HOST's stop hook
  every turn) re-reads and scans the whole events log for judgment entries on every call, so its
  cost grows with the log. Scenario: after months of use `events.jsonl` holds many thousands of
  entries and every Stop hook scans all of them to compute `fidelity_unjudged`, slowly eating
  into the 800 ms stop budget. Fix: an offset-indexed cache of the latest judgment per subject.

## SP1 integration (2026-10-06)

Merges of lane/verify, lane/host and lane/bridge onto the bootstrapped `main`, the dogfood
steps, and the end-to-end session check (`tests/integration/test_session_e2e.py`,
`scripts/drive_session.py`).

Fixed during integration (found by the driven session on plumb's own repository):
- [HIGH, fixed] (driven session, stop hook) The Stop block asked for
  `plumb tests run --changed`, which selects the covering tests of every uncommitted path plus
  every session's touched list. With other uncommitted work in the tree, the budget deferred
  the turn's own covering tests (plumb's repository: 0 of 77 run, 22.5 s timeout), and the
  second Stop summarized them as `not run` with no further ask. The block now names
  `plumb tests run --paths <this turn's paths>` (up to 8 paths, else `--changed`), so the
  turn's own covering tests run within its budget.
- [HIGH, fixed] (driven session, SessionStart latency) Adding or removing one Python file made
  the test map re-resolve every import edge with stat and `resolve()` calls: about 1.7 s on
  plumb's repository, so SessionStart hit the 1.9 s watchdog and printed only
  `check skipped (budget)`. Edges now resolve on repository-relative strings against the
  scanned file set (`imports.resolve_edge_rel`, `known_files`): 0.13 s after adding a file.
- `plumb drift` (CORE KS3) built: stale and dangling links with the moved end, unconfirmed
  edits, uncovered examples of any requirement, and fidelity a judgment no longer covers.

Design choices and open items:
- [MEDIUM] (drift) A requirement never judged for fidelity is not a drift signal: `plumb drift`
  prints it as one advisory line, and the merge boundary lists it (R4: fidelity is on demand or
  at the merge boundary, scoped to changed requirements). Only a `drifts` or `unsure` verdict,
  or a judgment whose hashes moved, counts as drift. Spec 5.10 lists "unjudged fidelity" among
  drift signals without this distinction; align the spec.
- [MEDIUM] (latency) A fully cold test map (no `.plumb/cache/test_map.json`, for example right
  after a clone) still costs about 0.9 s of parsing in the first SessionStart on plumb's
  repository; the hook stays under 2 s (measured 0.9 to 1.1 s) but exceeds its 900 ms soft
  budget on that first run. KS1 (index and hash caches) is still unbuilt.
- [MEDIUM] (dogfood) Every plumb record is still `proposed` (no agent may approve, R2), so on
  plumb's own repository the prompt hook never raises the intent-change flag: the heuristic
  flags only confirmed records. The flag is exercised end to end in the temporary repository of
  `test_session_e2e.py`, where the owner's approval is simulated in the owner's terminal. It
  starts working on plumb itself once the owner runs `plumb approve --proposed`.
- [LOW] (stop hook) The stop summary counts selected nodes (a whole test file can be one node),
  while `plumb tests run` counts executed tests, so a turn can read "covering tests 1" after
  "ran 7 tests".
- [LOW] (plan 9.4) `scripts/bench_hooks.py` (20 runs per hook, p50/p95) was not written; the
  timings come from `scripts/drive_session.py` (one run per hook) and the e2e test asserts each
  hook under 2 s.
- [LOW] (CORE SHOULD) `plumb new`, `show`, `why` and `log` still answer `not available in this
  build`; KS1, KS4 and KS5 remain unbuilt.
- [LOW] (dogfood, plan 4.6) `plumb claims check --range 4c08b64..HEAD` reports the following
  undeclared (commit, path) pairs from the lane commits, recorded here instead of an NC-backed
  baseline: each lane commit claims the SRs of its task row, while the dogfood links attach the
  file to a sibling SR (or the file is a test helper or fake). Integration commits since
  553e843 report none.
  - 721008197f78 src/plumb/verify/cli.py (claims SR-020, SR-018, SR-017)
  - 721008197f78 tests/verify/test_aborted.py (claims SR-020, SR-018, SR-017)
  - ac958f4e49e3 src/plumb/verify/api.py (claims SR-020, SR-018)
  - ac958f4e49e3 tests/verify/test_plugin.py (claims SR-020, SR-018)
  - 51f9c0c89204 src/plumb/hosts/claude_code/statusline.py (claims SR-014, SR-005)
  - 51f9c0c89204 tests/host/test_encoding.py (claims SR-014, SR-005)
  - ad4cda487083 tests/bridge/conftest.py (claims SR-023)
  - ad4cda487083 tests/bridge/pi_source_fixture.py (claims SR-023)
  - ad4cda487083 tests/bridge/test_import_feat_nc.py (claims SR-023)
  - 3acc463d3bd4 tests/bridge/fixtures/intent_prompts.json (claims SR-010, SR-021)
  - 3acc463d3bd4 tests/bridge/test_precision.py (claims SR-010, SR-021)
  - 22c41bca1cd8 src/plumb/judgment/cli.py (claims SR-021)
  - 22c41bca1cd8 src/plumb/judgment/fidelity.py (claims SR-021)
  - 6fa612db7e13 tests/bridge/conftest.py (claims SR-023)
  - 6fa612db7e13 tests/bridge/fixtures/pi_factory/bundles/FEAT-001.json (claims SR-023)
  - 6fa612db7e13 tests/bridge/fixtures/pi_factory/docs/features/FEAT-001.md (claims SR-023)
  - 6fa612db7e13 tests/bridge/fixtures/pi_factory/docs/nonconformances/NC-0002-empty-planning-brief.md (claims SR-023)
  - 6fa612db7e13 tests/bridge/fixtures/pi_factory/requirements/SR-003.md (claims SR-023)
  - 6fa612db7e13 tests/bridge/fixtures/pi_factory/requirements/SR-077.md (claims SR-023)
  - 6fa612db7e13 tests/bridge/test_import_feat_nc.py (claims SR-023)
  - a0313483e958 tests/bridge/test_tiers.py (claims SR-021, SR-010, SR-022)
  - 72a366e7c90b tests/verify/verify_helpers.py (claims SR-019)
  - 62242709fc55 src/plumb/verify/cli.py (claims SR-019)
  - 62242709fc55 tests/verify/test_waive.py (claims SR-019)
  - b2cd821fba0f src/plumb/verify/api.py (claims SR-018)
  - b2cd821fba0f tests/verify/test_envid.py (claims SR-018)
  - d53b484e04b5 src/plumb/verify/api.py (claims SR-016)
  - d53b484e04b5 tests/verify/test_impact.py (claims SR-016)
  - 9bb16c96c62e src/plumb/verify/api.py (claims SR-019, SR-020)
  - 9bb16c96c62e src/plumb/verify/evidence.py (claims SR-019, SR-020)
  - d6503c34e09e tests/verify/test_cli_verify.py (claims SR-020, SR-016, SR-017)
  - a8e8281491fb src/plumb/verify/policy.py (claims SR-018, SR-017)
  - a8e8281491fb src/plumb/verify/testmap.py (claims SR-018, SR-017)
  - 510694fdc6ac tests/verify/test_plugin.py (claims SR-018)
  - 89f17dfb9528 src/plumb/hosts/claude_code/providers.py (claims SR-009)
  - 9530f19ed380 tests/verify/verify_helpers.py (claims SR-016)
  - 2277cc573c31 tests/host/fakes.py (claims SR-014, SR-011)

## Fork plan (2026-10-06, docs/fork-plan.md)

The draft `docs/plans/fork-plan.md` moved to `docs/fork-plan.md` (the path the SP1 spec and
plan name) and was completed with the extraction status, the remaining extraction
candidates, importer usage, the FEAT-022 and FEAT-023 task mapping and the risks. concept 10
and INT-013 W-1 now name the new path; the historical entries above keep the old one.

Measured on an exported copy of pi-agent-factory `main` 341e2a08 (`git archive`, read-only on
the source; 85 SR, 24 FEAT, 22 NC, 550 links):
- [MEDIUM] (fork plan K3; KS1) `plumb status` and `plumb brief` take about 5.9 s warm at that
  scale (`validate` 1.2 s, `drift` 1.6 s), over the 2 s hook budget. The KS1 index and hash
  caches, and a hook benchmark on that copy, are prerequisites of the F4 switch.
- [MEDIUM] (fork plan K4; importer) A real import into the copy takes 2 min 14 s, while the
  dry run into an empty target takes about 1 s; not profiled (likely the writes and the
  pinning of about 550 links).
  Acceptable for a one-off command; profile it in sub-project 5 (pin in one pass).
- [LOW] (importer) 50 `missing-end` findings remain in the copy: `verified_by` tests that
  pi-agent-factory requirements name before they are written (SR-077, SR-078, SR-091 and
  others). They are real gaps upstream, reported correctly.
- [LOW] (importer) 8 `relation-skipped` findings are `relates_to spec:SPEC-*` relations;
  sub-project 5 decides whether they become `relates_to` path links (fork plan F3, owner
  decision 4).

## Delivered-repository intent review (2026-10-06)

An intent review of the whole delivered repository, with plumb's own `validate`, `drift`,
`brief` and hooks run for real on plumb itself and on scratch repositories.

Fixed (HIGH):
- [HIGH, fixed] (stop summary, relay) A one-line "ok" could confirm content the owner was
  never shown. The summary cap counted lines (3). A turn that wrote INT-001, SR-002 (3
  examples, one a contradictory edge case) and DEC-001 showed only three head lines and
  "+3 more (plumb status)". The stated set still held all three records, so `plumb relay ...
  --quote ok` confirmed them, including the unseen assumption and edge case. Now the cap
  counts records (`hooks.summary_proposed_cap`). A shown record shows every line of its
  read-back (`plumb.readback.record_lines`: an INT's read-back, will, won't and labelled
  assumptions; an SR's statement and every given/when/then; a DEC's chosen option and
  alternatives). Each stated record carries `shown`. A record is `shown: false` when the cap
  cut it, when it has a line over 400 characters, or when the stop blocked; `plumb relay`
  refuses such a record unless the quote names its ID. The "+N more not shown" line names
  those records and the new `plumb show <IDs>` command, which prints them in full. The
  prompt hook's awaiting line lists the two groups separately.
- [HIGH, fixed] (verify runner, dogfooding) On plumb's own repository, a one-line edit to
  `src/plumb/hashing.py` selected 6 covering files estimated at 14.6 s. On this loaded
  2-core machine they take 22.7 s, so the run hit the 22.5 s hard limit. The runner dropped
  every result ("ran 0 tests ... no fresh evidence") and learned no duration, so every such
  turn waited 23 s for nothing. The `--paths` fix of the integration round did not cover
  this. Now the plugin streams each phase to `$PLUMB_REPORT.stream`, and a timed-out run
  keeps every test that finished through teardown. Each test-run entry carries
  `timing: {expected_s, elapsed_s}`, and the evidence index folds it into a pace scale: half
  way toward the observed ratio for a finished run of 2 s or more, at once for a timeout,
  within [1, 3]. The selection fills `verify.fill_fraction` (0.65) of the budget with the
  scaled estimates. Regression test: `tests/verify/test_budget_overrun.py`.

Recorded (MEDIUM and LOW, not fixed in this round):
- [MEDIUM] (dogfooding) All 54 of plumb's own records are proposed (`SR 0/25 ok | proposed
  54`). Trigger 1 fires only on confirmed records. A prompt that contradicts R5 ("always run
  the full test suite every turn") surfaced DEC-006 and SR-017 but raised no flag, and every
  merge boundary waits on 21+ records. This is correct under R1. Fix: in the README and the
  hand-off, point the owner to one `uv run plumb approve --proposed` (or the INT and SR set)
  in their own terminal. Optionally, add a brief line saying intent-change detection is idle
  until records are confirmed.
- [MEDIUM] (`/plumb` command) `.claude/commands/plumb.md` advertises `why <ID|path>`, but
  `plumb why` exits 2 ("not available in this build"). With no `plumb new`, the agent
  hand-writes YAML frontmatter. Fix: drop `why` from the hint and allowed-tools, or alias it
  to `impact`; record `plumb new`. (`plumb show` now exists.)
- [LOW] (merge boundary) `plumb validate --merge <base>` prints every pending requirement in
  full (the statement and every example, across 21+ records), against R2's "quick owner
  glance". Fix: one line per record by default (ID, title, example count), with the full
  text behind `--verbose` (or `plumb show`).
- [LOW] (README ~290) The README links `docs/plans/fork-plan.md`, but the fork plan is at
  `docs/fork-plan.md`. Fix: change the link.
- [LOW] (docs weight) The docs come to about 4.3k lines for a light tool: concept 887, sp1
  spec 1405, plan 772, fork-plan 446, followups 821. The runtime is light (0.3 to 1.2 s per
  hook and command). Optional: once sub-project 1 settles, condense the sp1 spec into the
  concept and keep this file pruned.
- [MEDIUM] (`plumb --help`, concept 6.6) `plumb log`, `plumb new` and `plumb why` are
  reserved and answer "not available in this build". `show` is now built, and the help text
  marks the rest as not available. Concept 6.6 names `plumb log` as the way to read logged
  items on demand; today the owner reads `.plumb/log/*.jsonl` or uses
  `status`/`drift`/`validate`. Fix: implement at least `plumb log` (a filtered, readable
  view of events.jsonl, evidence.jsonl and session errors).
- [MEDIUM] (importer, SR-023, concept 10) Concept 10 says an imported record whose upstream
  owner approval pins its current content gets an approval `by: import`. The importer and
  SR-023 import everything as proposed instead, so a migration loses every owner approval
  (about 100 SRs to re-confirm). This is safe, since it never manufactures a confirmation,
  but it contradicts the concept without a recorded decision. Fix: carry pinned upstream
  approvals over as `by: import` entries citing the upstream record, or record a DEC and
  update concept 10.
- [LOW] (hook latency, SR-014) Measured hook times: session-start 1194 ms against 900 ms,
  with two "watchdog: hard limit 1.9s reached" entries; prompt 616 to 697 ms against 600 ms;
  stop 510 to 876 ms against 800 ms; statusline about 290 ms. The per-turn total stays under
  2 s and the hooks degrade gracefully. Fix: re-baseline the SR-014 budgets, or trim
  session-start (reuse the cached snapshot instead of recomputing freshness for 373 tests).
- [LOW] (dogfooding bootstrap) `plumb validate --merge` exits 4 on plumb itself until the
  owner confirms the seeded records. Fix: state prominently, in the README's dogfooding
  section and the hand-off, that one `plumb approve --proposed` in the owner's terminal
  confirms the seeded INT/SR/DEC records, and that trigger 1 cannot fire until then.
- [LOW] (DEC-004 vs concept 4.6, 4.7) DEC-004 keeps prompt digests in gitignored session
  state and commits a digest only when an approval cites it, while concept 4.6 commits every
  prompt digest. R2 still holds: a relay produced an agent-relayed entry with the quote and
  digest, and a mismatched quote exited 3. Fix: update concept 4.6 and 4.7 to cite DEC-004
  and the events.jsonl single-file layout.
- [MEDIUM] (relay, trigger 2) A trigger-2 question is phrased as a choice ("I assumed
  integer floor division; true float division also fits. Which one?"), yet a bare "ok"
  passes the affirmation check and confirms the chosen option. Fix: for a DEC asked as a
  choice, require the quote to name the chosen option (or a term from it) or the DEC ID, and
  refuse a bare affirmation.
- [MEDIUM] (merge boundary, dogfooding) plumb's lanes were merged into `main` with every
  touched requirement unconfirmed, and `plumb validate --merge HEAD~5` exits 4. This was
  unavoidable without the owner and is reported honestly. But the README never says that
  the owner's first act is to confirm or revise plumb's own 15 INT, 25 SR and 13 DEC
  records, or that the bootstrap merges predate any confirmation. Fix: a short "first
  morning" note in the README and the fork plan (`plumb validate --merge <root>`, then
  `plumb approve --proposed` or per record).
- [MEDIUM] (intent-change detection) (a) In a scratch repository, the first prompt hook call
  printed only "check skipped (budget)" (cold start over 600 ms). (b) "make add return a
  minus b instead of the sum" was not flagged against confirmed SR-001; only the generic
  compare nudge appeared, while naming "SR-001:" did flag. (c) In plumb's own repository,
  "let approvals stay confirmed after a record is edited" did not surface SR-004. (d) An
  edit of a confirmed record showed as plain "proposed" in the summary and the status line.
  Fix: warm or trim the prompt hook's cold path; add lexical contradiction cues ("instead
  of", "no longer", "stop", negation of a statement term); label edits of confirmed records
  "unconfirmed edit".
- [MEDIUM] (merge boundary, examples to tests) `plumb validate --merge` exits 0 while it
  reports "confirmed but not covered" and "full verification pending", so the example-to-test
  chain is only advisory. The spec defers this gating to sub-project 3. Fix: a non-zero exit
  (1) when touched confirmed examples are uncovered or full verification is pending, or list
  it as the first sub-project 3 item in the fork plan.
- [MEDIUM] (record authoring) There is no `plumb new` or `why` (`show` is now built), so the
  agent hand-writes INT/SR/DEC YAML for every read-back, example and decision. Fix:
  prioritize `plumb new intent|requirement|decision` as the first sub-project 2 item.
- [LOW] (README, last paragraph) The same broken fork-plan link as above
  (`docs/plans/fork-plan.md` -> `docs/fork-plan.md`).
- [MEDIUM] (SessionStart cold start) In a fresh clone with a newly synced `.venv`, the first
  two SessionStart runs printed only "check skipped (budget)" (2.4 s, 2.1 s), so the agent
  gets no intent brief in the first sessions after a clone or a venv rebuild. The third run
  worked (0.9 s). Fix: when the budget runs out, print the brief from records alone and skip
  only the test-map and evidence part, or warm the caches on `plumb init` /
  `plumb hooks install`.
- [MEDIUM] (dogfooding activation) With 0 confirmed records, "drop the hash staleness check"
  raised no flag on plumb itself. In a clone, after SR-003 and INT-006 were approved, the
  same prompt was flagged. Nothing in the session names the one command that switches
  dogfooding on. Fix: have the brief or the status line name the next step ("run plumb
  approve --proposed ... to activate intent-change checks"), and add it to the README
  quickstart.
- [MEDIUM] (stop block launcher) The Stop block tells the agent to run a bare
  `plumb tests run --paths ...`. The installed hooks, SKILL.md and the CLAUDE.md block use
  `.venv/Scripts/python.exe -m plumb`, `plumb` is not on PATH in the dogfood repository, and
  the settings have no allow rule for the command. Fix: render the instruction with the
  installer's `--launcher`; optionally add a `permissions.allow` entry for it.
- [LOW] (NC authoring) The NC kind is parsed, validated and imported, but no command creates
  an NC or any other record (CORE SHOULD, scheduled above). Fix: build `plumb new`, NC
  included.
- [LOW] (trailer history) Several lane commits made after 4c08b64 (1e7916a, c48bf33,
  2277cc5, 95e4df3, 51f9c0c, 11feb57 and others) carry no `SR:` trailer. The 36 undeclared
  (commit, path) pairs are listed in this file rather than in an NC-backed baseline.
  Integration commits since 553e843 are clean and the commit-msg hook is installed. Fix:
  leave the history; optionally open an NC so the `claims.yaml` baseline exercises the KEEP
  item.
- [LOW] (status wording) `plumb status` says "25 total, 0 confirmed, 0 covered" while brief
  and drift say "uncovered examples 0": "covered" there means confirmed and covered. The
  verifier's hook runs also wrote `.plumb/session/verifier-deliv` (gitignored, harmless).
  Fix: label the figure "confirmed and covered", or show both counts.

## Delivered-repository intent review, round 2 (2026-10-06)

The round's HIGH finding (under load, the hooks dropped the read-back, confirmation and
relay lines first) is fixed in the same change. Intent lines are now computed first and kept
through any cut. Budgets sit near the 2 s ceiling. The record index, the platform name and
the map-derived answers are cached (spec 10). The medium and low findings below were not
fixed, except where the HIGH fix covers them, as noted.

- [MEDIUM] (Stop budget, stop.py) With `src/plumb/text.py` touched, Stop hit its 800 ms
  budget repeatedly (0.96 to 1.33 s). It printed "check skipped (budget): covering tests,
  confirmations" and then "questions: none", so the summary read as all clear although the
  covering-test check and the regression trigger (R3) had not run. The paths stay in
  touched.txt, so a later turn retries. Partly covered by the HIGH fix: the stop budget is now
  1400 ms, and a skipped covering-test step prints "questions: regressions not checked
  (budget)", never "none". Still open: carry a pending flag into the status line
  (status.json already records `skipped`, but the status line does not show it).
- [MEDIUM] (merge.py, merge-boundary wording) The merge boundary says "merge waits for your
  confirmation: `plumb approve ...`, or say ok in the session". But `plumb relay` accepts a
  bare "ok" only for records in the stop hook's stated set that were shown in full (cap 3).
  The merge listing (35 records on plumb itself) writes no stated set, so a bare "ok" after it
  is refused for nearly every record. Fix: have `validate --merge` write a stated set of the
  records it printed in full, or drop "or say ok in the session" from that message.
- [MEDIUM] (dogfooding activation, repeat) All 54 of plumb's records are proposed (status
  line "SR 0/25 ok | proposed 54"). Trigger 1 cannot fire on plumb itself, and neither the
  brief nor the status line names the step that turns it on. Fix: name `plumb approve
  --proposed` (run in the owner's terminal) in the brief or the status line, and put a
  "first morning" note at the top of the README.
- [MEDIUM] (importer, SR-023, DEC-011 vs concept 10) A dry-run import of pi-agent-factory
  (read-only, 1.6 s) imports every record as proposed. That drops every pinned upstream
  approval (about 100 SRs to re-confirm). It also reports 936 missing-end findings for links
  whose files are absent. This is safe under R2, but the B migration loses the KEEP item
  "approvals pinned to exact content" at migration time. Fix: carry pinned upstream approvals
  over as `by: import` entries that cite the upstream record and hash, so only changed
  content needs re-confirmation. Otherwise record the decision in the concept.
- [LOW] (`plumb log`, `plumb new`) `plumb --help` lists "new, why, log (not available in this
  build)". `plumb log` is the concept's on-demand reader for "everything else is logged".
  Without `plumb new`, the agent hand-writes YAML records with pins. Fix: build `plumb log`
  (a readable view of events.jsonl, evidence.jsonl and errors.log) and `plumb new` as the
  first sub-project 2 items.
- [LOW] (README, last paragraph; raised twice this round) The README links the fork plan at
  `docs/plans/fork-plan.md`, but the file is `docs/fork-plan.md`. Fix: change the link.
- [MEDIUM] (prompt hook, hookio SKIP_BUDGET path) On a scratch clone with SR-005 confirmed, a
  prompt that contradicts it went over the 600 ms budget at the "intent check" step. This
  happened in 1 of 3 warm runs and in every cold run. The hook printed only "plumb: check
  skipped (budget)" and discarded the records and the trigger-1 flag it had already computed.
  The first prompt hook in a fresh clone took about 2.2 s. Covered by the HIGH fix: the
  prompt hook now computes the relay line, the records, the intent check and the compare line
  before the covering tests, and keeps them through any cut. A cut names only the skipped
  step. Still open: the first hook in a fresh clone (no caches yet) can still reach the 1.9 s
  watchdog. Warming the caches on `plumb init` / `plumb hooks install` would remove that.
- [MEDIUM] (verify/policy.py `waive()`) `plumb tests waive` records a waiver pinned to a diff
  digest, but nothing reads that waiver to let a targeted rerun replace a full rerun. The
  docstring says "Using it in place of a full rerun belongs to sub-project 3", so this is
  already a recorded deferral. Fix in sub-project 3: the merge-boundary check accepts a
  waiver whose digest matches the diff in place of the full rerun.
- [LOW] (stop.py, no-change turns) On a turn with no file changes, the Stop hook prints
  nothing: no summary and no "questions: none". That is reasonable, but neither the README
  nor the concept says the summary appears only on turns that change files. Fix: say so in
  both, or print one line such as "plumb: no changes | questions: none".
- [LOW] (.plumb/.gitignore: session/, cache/, test_map.txt) Three things are readable locally
  but not in git: the prompt-digest log (session/prompts.jsonl) that agent-relayed approvals
  cite, the stated set, and the grep-able test map. So a relayed approval's prompt digest
  cannot be checked from a fresh clone unless that digest was committed. DEC-004 covers the
  digests. Fix: have `plumb relay` commit the cited prompt-log entry next to the approval, as
  DEC-004 intends, with a test. Say in the README that test_map.txt is generated by
  `plumb map`.
- [MEDIUM] (validate.py, merge.py; examples become acceptance tests) A requirement with no
  examples (SR-099 in a scratch clone) raises no warning in `plumb validate` or `plumb
  drift`. `validate --merge` neither lists nor gates touched examples that have no
  `verified_by` test. So "which become acceptance tests" is never checked where it counts.
  Fix: add a validate warning for a requirement with zero examples, and have `validate
  --merge` list touched requirements whose examples are uncovered (as an advisory or a gate).
- [MEDIUM] (judgment/heuristic.py `intent_change`) With SR-003 confirmed ("dangling links are
  errors"), two prompts were not flagged: "Make dangling links warnings, not errors." and
  "Links should no longer pin the hash of both ends; only pin the target end instead." Term
  overlap fell below STRONG_OVERLAP although change words were present. The generic compare
  line still reaches the agent, so trigger 1 rests on the agent tier. Fix: flag a prompt when
  a matched confirmed record is in the injected top-N and the prompt carries change words, or
  lower the threshold for confirmed records. Add both prompts to the precision fixture.
- [MEDIUM] (escalated mode, spec section deferred to sub-project 2) Escalated mode exists only
  as a prompt-hook hint. There is no set-hash approval of an escalated record set, no `plumb
  decline`, and nothing holds code until the set is approved. The README and the brief do not
  say that escalated specs cannot be approved yet. Fix: add one README line stating the
  deferral, and list it first among the sub-project 2 items.
- [LOW] (dogfooding, `/plumb` slash command) No plumb record is confirmed yet, so trigger 1
  cannot fire on plumb's own work. The lane merges were declared non-boundaries (sp1-plan).
  Separately, the `/plumb` slash command advertises `why`, which answers "not available in
  this build". Fix: have the morning brief point to `plumb validate --merge <base>`, and drop
  `why` from the slash command's argument hint until it exists.
- [MEDIUM] (merge.py `merge_check`, full verification pending) The delivered repository showed
  "full verification pending (src/plumb/verify/pytest_plugin.py changed)" in the brief, the
  status line and the stop summary. `plumb validate --merge main` exits 0 while it is
  pending, so nothing makes the full run happen at the boundary. Fix: make `validate --merge`
  exit non-zero, or print a one-line "run --full before merging" action, while full
  verification is pending (already scheduled above). This change ran `plumb tests run --full`
  once, so the delivered state has recorded full-run evidence.
- [MEDIUM] (R1 gate never exercised on plumb) All 25 of plumb's SRs are merged on main as
  proposed. With HEAD on main, `plumb validate --merge main` checks an empty range and reports
  "touched requirements: none", so the R1 gate has never run on plumb itself. Fix: add a short
  "Tomorrow morning: activate dogfooding" line to the README and the session brief (`plumb
  show INT-001..`, then `plumb approve <ids>` for the KEEP-critical SRs and INTs). Do future
  work on branches, so `validate --merge main` covers a real range.
- [LOW] (session-start latency) Measured: prompt 0.83 s, stop 0.55 to 1.06 s, statusline
  0.59 s, session-start 1.31 s warm, with two watchdog hits in errors.log. Covered by the HIGH
  fix: the session-start tests line is cached under the verify fingerprint (0.7 to 0.8 s warm,
  measured after the fix), and a cut prints the records brief with "tests: not checked
  (budget)".
- [LOW] (NCs and the claims baseline not exercised) `.plumb/ncs/` is empty and the claims
  baseline is `[]`, while this file lists 36 undeclared (commit, path) pairs from trailerless
  lane commits. Fix: open NC-0001 for the trailerless lane commits and reference it from the
  claims.yaml baseline, so both KEEP items are exercised on plumb itself.

## Intent verification round (2026-10-06): medium and low findings

The two HIGH findings of this round were fixed in the same change: untraced changes (a changed
source path no requirement owns) are now named by the stop hook, delivered to the agent as a
read-back instruction, and put to the owner at the merge boundary (SR-026); failing acceptance
tests show in `validate --merge`, `drift` and `status`, an unresolved regression makes the merge
report exit 5, and a full run that collected nothing or hit a collection error no longer clears
`full verification pending` (SR-027).

- [MEDIUM] (prompt.py `awaiting_line`; approvals.py `find_prompt`) The prompt digest that
  `plumb relay --prompt` needs is printed only in the "awaiting confirmation" line, and only
  for records in the previous reply's stated set. A prompt such as "ok, SR-002 is right" naming
  a proposed record outside that set got neither a digest nor a relay instruction, so the
  one-line confirmation path needs the agent to dig through `.plumb/session/prompts.jsonl`.
  Fix: when a prompt names proposed record IDs and carries an affirmation term, print the
  digest and the relay command whatever the stated set holds, or let `plumb relay --prompt
  latest` resolve the session's latest logged prompt.
- [MEDIUM] (prompt.py `intent_lines`; plumb's own `.plumb/` state) Every plumb record is still
  proposed, so trigger 1 never fires on plumb's own work. Concept 6.6 counts "a contradiction
  involving a proposed record" under trigger 2, but the hook does not detect one: "stop hashing
  link targets, just compare file mtimes" (against SR-002 and INT-006) printed no flag and no
  compare line, and "drop content hashes from links" did not retrieve INT-006 or SR-002. Fix:
  emit the compare line (or a low-confidence flag) when a strongly matched proposed record is
  relied on, seed relevance so KEEP-list terms (hash, staleness, pinned, trailer) retrieve
  INT-006 and its SRs, and say in the README that intent-change detection on plumb waits for
  the owner to confirm the INT and SR set.
- [MEDIUM] (stop.py summary; verify select budget) "covering tests 3: 3 fresh pass, ... 51
  deferred (budget)" ends with "questions: none" and the status line reads "tests ok", although
  about 95 % of the covering tests did not run this turn and nothing says whether they still
  have fresh evidence. Fix: separate deferred tests with fresh evidence for the current closure
  from deferred tests with stale evidence, show "tests partial" instead of "tests ok" while
  stale deferred tests remain, and carry them to the merge boundary as pending.
- [LOW] (repository weight) `src/plumb` is about 10.3k lines; the sp1 spec, the plan and this
  file add about 3.4k lines for one sub-project. Per-turn behaviour is light (hooks 0.4 to
  0.7 s), but the artifact surface works against the "lighter, more elegant" framing. Fix:
  prune resolved or duplicated follow-ups in a later sub-project, add a one-page "how it works"
  section and keep the long spec as reference only.
- [LOW] (README.md, last paragraph) The README points to `docs/plans/fork-plan.md`; the fork
  plan is at `docs/fork-plan.md`. Fix: correct the path.
- [LOW] (statusline after a session with no edits) A fresh session with no edits shows "tests
  not run" while the session brief reports "410/411 mapped tests with fresh passing evidence".
  Fix: have the session-start snapshot seed the status line's tests field from the brief's
  evidence summary.
- [MEDIUM] (links.py lines 81-86; importer/pi_factory.py; concept 4.4) Link pins and staleness
  work for whole files only. Symbol ends (`path` + `module:name`) and test-node ends
  (`path::name`) are refused ("wait for symbol hashing"), and the importer turns every
  pi-agent-factory symbol link into a whole-file link. Any edit anywhere in a linked file makes
  every link to it stale, which adds drift noise and weakens staleness on imported records.
  The KEEP item holds at file level (a missing refinement, R7). Fix: hash symbol and test-node
  ends with `ast` as concept 4.4 describes and let the importer keep symbol links; until then,
  say in the concept or the spec that links are file-level in sub-project 1.
- [MEDIUM] (docs/concept.md 4.1, 4.6, 4.7 vs sp1 spec deviations F1 to F11) The concept spec
  still describes one JSON file per log entry under `.plumb/log/<kind>/` (the code uses
  `events.jsonl` and `evidence.jsonl`), a PreToolUse shell guard (the code uses
  `permissions.deny` rules), a prompt digest committed on every prompt (the code commits it
  only when cited) and `plumb approve --prompt` for relays (the code uses `plumb relay`). The
  sp1 spec's F table justifies each change, but a reader of the concept gets the wrong picture
  of the trust mechanisms. Fix: add a short "as built in sub-project 1" note to concept 4.1,
  4.6 and 4.7 pointing to F1 to F4, or update the text.
- [LOW] (stop.py lines 249-252) A turn with no changed files prints nothing (0.36 s, empty
  output), so the "summary at the end of each turn" appears only on turns that change files;
  the status line still carries the counts. Fix: print a one-line "no changes; N proposed
  awaiting you" summary, or document that the status line is the summary on such turns.
- [LOW] (dogfood state; `plumb validate --merge`) A prompt contradicting SR-003 ("drop content
  hashes from links; staleness by mtime is enough") raised no intent-change flag because
  trigger 1 protects only confirmed intent (consistent with R1), and the first merge boundary
  will ask the owner to approve about 40 records in one command. Trigger 1 is not yet
  exercised by the dogfood records. Fix: point the owner early to `plumb approve --proposed`
  or the one-line in-session "ok".
- [LOW] (cli.py help text) `plumb --help` lists `new, why, log (not available in this build)`.
  Nothing creates a record or reads the log; the agent writes Markdown records directly. Fix:
  hide the commands that are not available, or keep tracking them here.
- [MEDIUM] (`plumb link` test-node ends) `verified_by` links can point only at whole test files
  ("symbol and test-node ends (path::name) are not available in this build"). Concept 4.4 and
  4.5 promise per-example acceptance tests pinned to the test function; with file-level links
  every example of a requirement links the same file, and an edit to an unrelated test in it
  makes every link stale. Fix: implement test-node (`path::name`) ends as concept 4.4
  specifies, or make it the first sub-project 2 item.
- [MEDIUM] (plumb's `.plumb/`, status line "SR 0/27 ok | proposed 56") No plumb record is
  confirmed, so trigger 1 cannot fire on plumb itself: "let the agent approve records when
  nobody objects" (against SR-005) produced no flag, only the record list. Consistent with R1
  and the owner not reviewing, but it should be stated. Fix: say in the README and the fork
  plan that dogfood protection becomes active once the owner confirms the INT records, with a
  one-line `plumb approve --proposed` step in the owner's own terminal for the 15 INT records
  that quote the owner verbatim.
- [LOW] (git log of plumb) Since the record model landed, most commits carry no `SR:` trailer,
  which thins code-to-requirement traceability in the dogfood repository. Fix: add trailers to
  future commits, or have the commit-msg hook warn when a commit changes paths an SR declares
  without naming it.
- [MEDIUM] (README.md first-morning step; brief and status line on plumb) All of plumb's records
  are proposed, and a contradicting prompt ("Drop the hash staleness check on links, it is too
  slow") surfaced SR-003 and SR-002 without an intent-change flag: trigger 1 idles until the
  owner confirms records (correct under R1 and R2). The README, the brief and the status line
  still do not name the one step that turns dogfooding on; three earlier rounds recorded this.
  Fix: a three-line "Tomorrow morning" note at the top of the README (`uv run plumb show
  INT-001..`, then `uv run plumb approve <ids>` in your own terminal) and one brief and
  status-line hint while confirmed == 0.
- [MEDIUM] (stop.py block reason) The Stop hook's block tells the agent to run a bare `plumb
  tests run --paths ...`, but `plumb` is not on PATH on this machine; the installed hooks,
  SKILL.md and the CLAUDE.md block use `.venv/Scripts/python.exe -m plumb`. Each blocked turn
  starts with a failing command (recorded earlier, still open). Fix: render the block
  instruction with the installer's launcher (the string the settings.json hooks use), and
  optionally add a `permissions.allow` entry for `tests run`. The new untraced-change line of
  SR-026 names no command, so it does not add to this.
- [MEDIUM] (verify/policy.py `waive`; merge.py) `plumb tests waive` records a waiver pinned to
  a diff digest, but nothing uses it: no targeted rerun replaces the full rerun at the merge
  boundary, and `validate --merge` exits 0 while "full verification pending" shows (a recorded
  regression now exits 5, SR-027, but pending alone does not). Scheduled for sub-project 3.
  Fix: keep it the first sub-project 3 item; make `validate --merge` exit non-zero, or print an
  explicit "run --full or waive" action, while full verification is pending.
- [MEDIUM] (importer/pi_factory.py; concept 10; DEC-011) The importer brings every
  pi-agent-factory record in as proposed, dropping every pinned upstream owner approval (about
  100 SRs would need re-confirmation), against decision 1B. Safe under R2, but concept 10
  promises `by: import` approvals. Fix: carry pinned upstream approvals whose hash matches as
  `by: import` entries citing the upstream record and hash, or align concept 10 with DEC-011.
- [LOW] (verify/runner.py covering-test budget) In a scratch clone, a deliberate regression in
  `src/plumb/hashing.py` made `plumb tests run --paths` run 8 tests in 21.6 s against the 15 s
  budget (25 tests in 3.9 s without it); the hooks stayed fast and the regression was caught
  and asked about. Fix: stop at the soft budget, not the 22.5 s hard limit, when failures make
  the run slower than estimated, or treat it as a pace-scale case.
- [LOW] (`.plumb/claims.yaml` baseline `[]`; no `.plumb/ncs/` records) The NC kind is parsed,
  validated and imported, but plumb has no NC, and the claims baseline is empty while this
  file lists 36 undeclared (commit, path) pairs from trailerless lane commits. Nothing creates
  an NC (`plumb new` is reserved for sub-project 2). Fix: open NC-0001 for the trailerless lane
  commits, reference it from the claims baseline, and build `plumb new` (NC included) first in
  sub-project 2.
- [MEDIUM] (observed while fixing this round; verify/evidence.py `node_evidence`) A
  whole-file selection aggregates every recorded node of the file, including nodes removed
  from the source since they passed (`removed after passing`). Their `test_hash` is now None,
  so the file's evidence stays `stale` (miss `test`) for good: on plumb, every turn that
  touches `stop.py` selects `tests/host/test_stop.py`, blocks with "run the covering tests",
  and after a passing run the summary still says "1 not run" (the removed node
  `test_summary_caps_proposed_lines`). Fix: leave recorded nodes that no longer exist in a
  mapped file out of the file aggregate (they stay reported as removed after passing).
- [LOW] (trace.py, this round) Eight of plumb's own modules (`__init__`, `__main__`, `api`,
  `cliutil`, `contracts`, `paths`, `text`, `validate`) are owned by no requirement, so their
  next change will be reported as untraced. That is the intended behaviour; the agent did not
  exempt them on the owner's behalf. Fix: link `validate.py` to SR-003 and the CoreAPI modules
  to SR-001 when they next change, or let the owner list the glue modules under
  `trace.exempt`.

## Delivered-repository verification, round 4 (2026-10-06, commit 0680662)

Raised by the verification of the round-3 fixes. Its four HIGH findings were fixed in the same
change: a requirement widened by a new `implemented_by`/`verified_by` link (through
`plumb link` or a frontmatter edit), or a `trace.exempt` glob added in the range, now goes to
the owner at the merge boundary (SR-028); a failing acceptance test of a touched requirement
is kept until a run passes it, an acceptance test with no passing evidence on the current
identity holds the merge (exit 5), and a full run with a failing test no longer clears
`full verification pending` (SR-027 EX-4..EX-7); the trace and the covering-test selection
share one source definition, and with `source_dirs` unset a code file anywhere outside the
test directories, `docs/` and dot directories is source, so flat layouts are traced (SR-029).
The round-3 LOW entry above that suggests linking unowned modules to existing SRs stays
valid: such a link now shows the requirement as extended at the merge, for the owner to
confirm. The MEDIUM entry above on removed nodes keeping a file stale was resolved in the
same change (the file aggregate leaves out nodes no longer in the source).

- [MEDIUM] (verification round 4; merge.py exit code; sp1 spec 5, full-suite gate deferred to
  sub-project 3) With full verification pending (src/app/y.py has no covering test),
  `validate --merge main` printed the pending line and exited 0. Nothing at the boundary
  enforces R5's "satisfied at the next merge boundary"; the spec defers that gate to
  sub-project 3, so it is a known gap rather than a contradiction. Reproduced again this round:
  a full run that failed a test of a requirement the range did not touch leaves
  "full verification pending (1 test(s) failed in the last full run ...)" and exit 0. Fix:
  until sub-project 3 lands, give a distinct non-zero exit while full verification is pending.
  The README merge section now says that exit 0 does not by itself mean the full suite ran.
- [MEDIUM] (verification round 4; trace.py `is_source`, source_dirs default) Untraced
  detection only looked at `source_dirs`, so a changed `lib/x.py` in a project not laid out as
  src/ was never reported. Largely resolved by the SR-029 fix (an unset `source_dirs` traces any
  code file outside tests, docs and dot directories). Remaining: once the owner sets
  `source_dirs`, code outside it is invisible again. Fix: let `plumb init` infer `source_dirs`
  from the layout (pyproject packages, top-level packages), or print the configured
  `source_dirs` in the brief so the owner can see the gap.
- [MEDIUM] (verification round 4; trace.py owned paths are never untraced; merge.py stale links
  and fidelity are advisory) New behaviour added inside a file a confirmed requirement already
  owns is not untraced: appending `delete_all_user_data` to src/app/calc.py, owned by SR-001,
  gave only a stale-link warning and "fidelity unjudged", the merge exited 0, and
  `plumb repin --all-stale` cleared the staleness without any confirmation. Consistent with R4
  (fidelity is advisory), but a second way around the read-back. Fix: at the merge boundary,
  list the requirements whose `implemented_by` ends changed in the range and were repinned
  without a fidelity judgment; consider showing repins in the range in the approvals glance.
- [MEDIUM] (verification round 4; merge.py, trace.py `trace.exempt`; .claude/settings.json deny
  list) Appending `trace: {exempt: ["src/**"]}` to .plumb/config.yaml, which the agent may edit
  (the guard denies only .plumb/log/**), removed every untraced path and the merge exited 0, and
  the report did not say the exemption list changed. Resolved by the SR-028 fix: a glob added in
  the range is listed for the owner, is not honoured until `plumb approve --exempt` (refused
  under the agent session marker) or a relayed affirmation that names the exemption, and
  confirmed exemptions appear among the approvals in range. Remaining suggestion: also put
  .plumb/config.yaml under the agent guard's deny rules for edits to `trace`.
- [LOW] (observed while fixing this round; merge.py `extended_requirements`) Approvals recorded
  before this change carry no `ends`, so a confirmed requirement whose links changed in a range
  is shown as extended with all its new ends even when the owner approved it after linking; the
  owner re-approves once and the new approval lists the ends. Fix: none needed beyond a note in
  the brief, or treat ends present at the approval's commit as listed.
- [LOW] (observed while fixing this round; merge.py exit precedence) When an agent widens a
  confirmed requirement, the merge may exit 5 rather than 4 because the touched requirement's
  other acceptance tests have no passing evidence on the current code; the extension is still
  listed in the same report. Fix: none needed; the sp1 spec states the precedence (1, then 5,
  then 4).

## Delivered-repository verification, round 5 (2026-10-06, commits 0680662 and 871296e)

Raised by the verification of the round-3 and round-4 fixes. Its HIGH findings were fixed in
the same change. An approval now pins each `verified_by` end, so a confirmed example's
acceptance test that changed, or was rewritten to pass after a regression, reaches the owner.
The stop hook asks about it as a regression, and the merge waits or holds (SR-030). The merge
boundary also checks the acceptance tests of every confirmed requirement whose tests cover a
changed path, and `full verification pending` holds it until a full run or an owner waiver of
this exact change (`plumb tests waive --merge BASE`) satisfies it (SR-031). This resolves
the round-4 MEDIUM entry above on the boundary exiting 0 while full verification was pending.
The prompt hook injects a per-session deduplicated delta, one line per record within a token
budget, and the session brief is a few lines plus a pointer (SR-032, R9). `plumb explain
<plain words|path|ID>` replaces the unavailable `why` (kept as an alias), and the installed
`/plumb` command routes it (SR-033, R9). The remaining R9 parts are scheduled in concept
section 11 item 2.

- [MEDIUM] (src/plumb/hosts/claude_code/prompt.py intent-change flag, heuristic backend) The
  flag fired on the wrong prompts. "Also tidy the add docstring for SR-001" was flagged "this
  may change SR-001 (confirmed) ... ask before editing" with an escalation hint, which is a
  false interruption. "make add subtract" (a direct contradiction) and "add a multiply
  function next to add" (an extension) were not flagged and only got the generic compare
  line. Owner: "questions ONLY on a real intent change (a request that contradicts or extends
  a confirmed requirement)". Fix: score contradiction or extension against the confirmed
  examples rather than on ID mentions, with example-based tests for contradict, extend and
  benign prompts.
- [MEDIUM] (src/plumb/trace.py owned_paths, file-level ownership; src/plumb/merge.py)
  Appending a new behaviour (`def mul`) to src/pkg/mod.py, a file the confirmed SR-001 already
  owns, raises no untraced-change signal, and after a covering run `validate --merge` exits 0.
  The only signals are a stale-link warning and advisory fidelity. Whole-file hashing is
  sanctioned for 1a, so this is a refinement. Fix: once symbol-level hashing lands (roadmap
  1b), treat new symbols in an owned file as untraced. Until then, list the stale
  `implemented_by` links of confirmed requirements in the merge report's waits section.
- [MEDIUM] (R9 remainder, scheduled in concept section 11 item 2) Not built in this change:
  - the one-line status card and the full intent card, configurable `full`, `compact` or
    `off`;
  - plain-language arguments for the other owner commands (`impact` resolves words only
    through the agent's `/plumb` instructions);
  - `plumb view`, the generated Obsidian vault.
- [LOW] (src/plumb/hosts/claude_code/statusline.py reads .plumb/session/status.json only)
  After a CLI `plumb tests run` that recorded a regression, the status line still read
  "SR 1/1 ok | stale 0 | tests not run" until the next stop hook refreshed the snapshot. Fix:
  have `plumb tests run` (and approve/relay) refresh status.json.
- [LOW] (src/plumb/trace.py is_code_path, CODE_SUFFIXES used when source_dirs is not
  configured) Inferred from the code, not reproduced. When source_dirs is unconfigured, a file
  outside the source directories counts as source only if its suffix is in CODE_SUFFIXES. So
  changes to .html, .css, .json, .yaml and .toml app files, Dockerfiles and Makefiles are never
  reported as untraced and can skip the read-back. The untraced path itself works. Fix:
  consider treating any tracked non-doc file outside test, docs and dot directories as
  source, with `trace.exempt` (owner-confirmed) as the escape hatch.
- [LOW] (observed while fixing this round; src/plumb/confirm.py approved_test_pins) An
  approval recorded before this change pins no `verified_by` content. A requirement confirmed
  that way is not shown as "acceptance test changed" until the owner approves it again. A
  regression hidden by rewriting its test is still caught, because a regression is resolved
  only by a pass on the original test body. Fix: none needed beyond one re-approval. A note
  in the brief would help.
- [LOW] (observed while fixing this round; src/plumb/commands.py drift_data) `plumb drift`
  does not list a confirmed requirement whose acceptance test went stale because another
  requirement's code changed. Only the merge boundary lists it ("acceptance tests this change
  can affect"). Fix: reuse `Verify.affected_requirements` over the working-tree changes in
  drift.
- [LOW] (observed in a scratch repository without a .gitignore; stop hook block) The stop
  hook's `plumb tests run --paths ...` command listed `__pycache__/*.pyc` files as changed
  paths. Fix: leave paths outside the source and test definitions out of the suggested
  command.
- [LOW] (.plumb/features/FEAT-001.md) The feature's `requirements` list stops at SR-025.
  SR-026 to SR-033 name FEAT-001 only in their own frontmatter. Fix: list them when the owner
  next confirms FEAT-001, so its hash moves only once.

## Next batch planning (2026-10-06, docs/specs/sp2-sp5, docs/plans/next-plan.md)

Written while drafting the specs for sub-projects 2 to 5 and the importer completion. No
review has run on them yet; these are the planner's own notes.

- [LOW] (records FEAT-002 to FEAT-005, SR-034 to SR-068, INT-017 to INT-020, DEC-014 to
  DEC-019) plumb has no record-creation command yet (`plumb new` and `plumb capture` are
  SR-035 and SR-034), so the records were written through plumb's library write path
  (`Core.write_record`, IDs checked against `Store.next_id`) and every link was added with the
  `plumb link` CLI. Fix: none; lane CAPTURE builds the commands.
- [MEDIUM] (docs/specs/sp4-hosts-mcp.md section 4) The Codex, Pi and Hermes event mappings are
  a design taken from the hosts' documented extension models and pi-agent-factory's Pi and
  Hermes adapters; they were not checked against the versions installed here. Fix: task H1
  records each installed host's surface in `docs/hosts.md` first; missing rows use the
  CLI-only fallback.
- [MEDIUM] (docs/specs/sp2-intent-capture.md 8.3, DEC-018) The calibration pass criteria (20
  items, 5 negatives with synthetic ones counting up to half, zero false accepts) are the
  planner's proposal, recorded as a decision that matters for the owner to confirm or change.
- [LOW] (docs/plans/next-plan.md 7) The Obsidian vault (`plumb view`) is a SHOULD item of lane
  PRESENT, dropped last; if it is dropped, it leads the next batch.
- [LOW] (FEAT-004) The importer completion shares FEAT-004 with the host adapters (DEC-015)
  because the work order names FEAT-002 to FEAT-005.

## Next batch spec review (2026-10-06): medium and low findings

From the review of `docs/specs/sp2-intent-capture.md`, `sp3-merge-boundary.md`,
`sp4-hosts-mcp.md` and `docs/plans/next-plan.md` against the brief and the concept. The one
HIGH finding (a host without the session marker let the agent write `by: owner` entries) is
fixed in the same commit: every owner-only write now goes through
`approvals.require_owner`, which refuses outside an interactive terminal on every host
(concept 4.6 check 4, sp4 3.4, SR-005 EX-6). Findings that two verifiers reported are merged
into one entry.

- [MEDIUM] (sp2 8.2 "Eligible only", sp2 3; reported three times) An `SR` becomes eligible for
  auto-approval when every example carries a quote span, but the SR's hash also covers its
  agent-written title, statement, feature and `implemented_by` ends, so auto-approving it
  confirms agent wording beyond the owner's given/when/then (R8 B lists only INT read-backs
  and examples). JEV entailment over the whole record narrows but does not match the owner's
  list, and sp2 3 does not declare the widening. 8.2 also says `plumb example` asks the gate
  without defining its case. Fix: add a C8 row to sp2 3 naming the mapping and its reason;
  require the SR's statement and title to be entailed by the quoted spans (claim kind
  `example-restatement`) or to carry their own verbatim `quote`; state that `plumb example`
  is never eligible (or define it); CS4 tests: an SR with a non-entailed agent statement and
  quoted examples is never auto-approved, and `plumb example` never auto-approves.
- [MEDIUM] (plan 4 CS2 and CS4, 7 PS2; reported twice) The R8 commands the owner asked for
  ("there should be a command for that": `plumb jev status`, `plumb jev setup`,
  `plumb config show`) and the R12 pieces the owner adopted ("Ok adopt the missing pieces")
  are SHOULD items early in the drop orders. Fix: promote `jev status`, `jev setup` and
  `config show` to MUST (they are cheap) or put them last in the drop order; name every
  dropped R8, R11 or R12 item at the top of the handoff, as the plan does for the vault.
- [MEDIUM] (plan 4 CS1, 12; reported twice) The R11 measurement ("the e2e session test covers
  one ambiguous request that yields exactly the questions that matter") is droppable, which
  would leave the clarify skill unmeasured. Fix: put CS1 in the never-cut list of plan 12, or
  make `test_clarify_e2e.py` a MUST with `plumb clarify` reduced to what the test needs.
- [MEDIUM] (sp2 5.1 first rule) `intent.quote` is checked against the logged prompt only when
  `--prompt` is given; without it an agent paraphrase is stored as the owner's words and then
  serves as the triage premise, inflating the low-risk group. Fix: require `--prompt` for any
  capture that writes an INT or example quote, or mark such records "unverified quote" and
  keep them out of the low-risk group.
- [MEDIUM] (sp4 4.2 stop row) On Pi the block instruction is sent as a user-role steering
  message; if Pi's input event fires for it, the prompt hook logs plumb's own text as an owner
  prompt, which a relay could then quote (the "say ok" offer wording). Fix: tag
  plumb-originated steering messages and skip them in the prompt-digest log, or deliver the
  block as a non-user context message; test that a block message never becomes a logged
  owner prompt.
- [MEDIUM] (sp2 3 C5 and 8.1, concept 4.6 "The offer names every record of the group by ID",
  against sp5 lines 81-83 and R9) sp2 and the concept put every ID of the low-risk group in
  the `plumb brief` line (about 50 IDs on plumb's own repository), which is the list of
  proposed records R9 forbids; sp5 says one count line with a pointer. Fix: sp5 wins for the
  brief and the agent's context (a count and `plumb triage`); exact IDs and hashes stay in
  `stated.json` groups and `plumb triage`; the owner-facing end-of-turn line lists IDs up to
  a small cap plus "+N more (plumb triage)". Align sp2 8.1, C5 and concept 4.6.
- [MEDIUM] (sp2 8.3, R12.1) Synthetic perturbations count toward `min_negatives` (up to
  half), so a calibration can pass with very few real owner revocations, loosening the gate
  R12.1 defines on "the owner's own confirmed and revoked records"; the departure is not in
  sp2 3. Fix: declare it in sp2 3; report owner-labelled and synthetic accuracy separately in
  the `calibration` event; require a minimum of real owner-labelled items, with synthetic
  negatives only adding to a passing real-label result.
- [MEDIUM] (sp2 5.3 and 9.1, concept 6.6 trigger 2) R11's timing rule (clarifying questions
  only when the owner starts or changes intent, never mid-implementation unless a
  contradiction appears) lives only in the skill text: a `matters: true` DEC the agent writes
  mid-implementation is asked by the stop hook. Fix: ask such a DEC only when it was written
  in a turn whose prompt started or changed intent (clarify depth incremental or escalated)
  or when a contradiction flag exists; otherwise show it as a labelled assumption; test that a
  mid-implementation DEC is not asked.
- [MEDIUM] (sp4 3.2 with sp3 3.2) The merge-boundary glance lists approval and revocation
  events but not `config` (auto-approve on/off) or `jev-setup` events. The HIGH fix makes
  `config auto-approve` refuse outside an interactive terminal on every host, so an agent can
  no longer write it on the normal path, but the owner still cannot glance at it. Fix: list
  the range's `config` and `jev-setup` events in the merge-check glance; have the brief say
  when a host runs without the marker.
- [LOW] (sp2 4) New event kinds (`config`, `calibration`, `escalation-declined`, `triage`,
  `jev-setup`) go into `events.jsonl`, which R10.2 calls implementation drift. sp2 12 routes
  every write through `log_append`, so this is only extra migration load. Fix: the SP6
  one-file-per-entry migration covers these kinds.
- [LOW] (sp2 6.2; reported twice) An unapproved escalated set is named "once per turn" as the
  open trigger-2 question, while other questions are asked once per hash, so the owner is
  re-asked every turn while deliberately waiting. Fix: ask once per set hash; afterwards show
  it on the status card and in the brief only, and keep the agent-side "do not write its code
  yet" instruction in the deduplicated delta.
- [LOW] (sp3 9 and the R10.5 row of sp3 2) `plumb check` is an alias of `validate`, so
  `plumb check --merge` runs `merge_report(run_full=False)` and never the one full suite R10.5
  names, contradicting "Same entry point". Fix: state that SP6's R10.5 hook uses
  `plumb merge-check`, and either document `check --merge` as the report-only form or route
  it to merge-check with the full run.
- [LOW] (sp2 6.2 and 8.1 step 5) `plumb spec show|approve` need an INT ID, against R9's
  plain-language arguments. Fix: resolve plain words through `plumb resolve` (sp5) and print
  the listed hashes before writing. (The triage y/N is now stated as the confirmation of R8's
  one step: it is the owner-terminal guard's question, which no flag skips.)
- [LOW] (sp2 7.1) The precision fixture sets no floor for `extends` prompts, though an
  extension is trigger 1; a heuristic missing every extension passes. Fix: add a minimum
  recall for `extends`, or report it as an advisory metric.
- [LOW] (src/plumb/approvals.py `require_owner`, this fix) Owner-only commands now need stdin
  and stdout to be terminals. Git Bash's mintty is not one for native Windows Python, so the
  owner there must prefix `winpty` (the refusal says so) or use Windows Terminal or
  PowerShell. `plumb approve --yes` is removed: the y/N is the guard's proof and no flag skips
  it. `docs/specs/sp1-grounding-loop.md` still documents `--yes` as history.
- [LOW] (concept 4.6 check 4) An agent that drives a pseudo-terminal could answer the y/N
  itself. This is a deliberate bypass inside the stated trust model (tamper-evident, not
  tamper-proof), not the normal path. Fix (optional, later): record in each `by: owner` entry
  that the answer came from a terminal, so the glance can show it.

## Next batch spec review, round 2 (2026-10-06): medium and low findings

Second review of `docs/specs/sp2-intent-capture.md`, `sp3-merge-boundary.md`,
`sp4-hosts-mcp.md` and `docs/plans/next-plan.md` (after c0bd18f) against the brief and the
concept. No HIGH finding; nothing below is fixed. Findings that verifiers reported more than
once are merged. Entries marked "repeat" restate a round 1 finding that is still open and
only add what round 2 found new.

- [MEDIUM] (sp2 8.2 Eligible, `.plumb/requirements/SR-041.md` statement; repeat, reported
  three times) R8 B: "eligible: ONLY records derived directly from the owner's own words (INT
  read-backs, and examples restating the owner's given/when/then)". An SR whose every example
  quotes the prompt is eligible as a whole, and its `by: auto-jev` approval pins the agent's
  title, statement and `implemented_by` ends too. New in round 2: SR-041's own statement
  carries the same widening, and the spec does not say whether link ends are outside the
  claim. Fix: a sp2 3 refinement row (examples have no record of their own, so an SR
  qualifies only when JEV judges its statement and every example entailed by the logged
  prompt), or limit eligibility to SRs whose statement is a verbatim span of the prompt;
  update SR-041 to match; a "never" test for an SR whose statement adds behaviour absent from
  the prompt.
- [MEDIUM] (sp2 5.1 quote rule and 8.1 step 2 premise; repeat, reported twice) R8 A: "scores
  each proposed record for faithfulness to the owner's words". Without `--prompt` an
  `intent.quote` is never checked, yet triage uses it as the owner's words, so a paraphrased
  or invented quote can rate a record "faithful to your words" and put it in the group the
  owner approves with one "ok". The owner still confirms, so no approval path opens; the trust
  claim of the rating breaks. Fix: treat a quote with no verified prompt digest as an empty
  premise (out of the low-risk group, shown individually as "quote not verified"), or require
  `--prompt` whenever the prompt hook logged a prompt this turn; one test per entry point
  (`capture`, `intent`, `example --quote`).
- [MEDIUM] (sp4 3.2 `plumb turn start --prompt-file`, R2) On the CLI-only fallback, which
  every host without prompt hooks uses, the agent itself supplies the prompt text that is
  logged, so `plumb relay`'s verbatim check compares the quote with what the agent wrote. R2's
  provenance ("logged by the prompt hook") drops to self-attested, and neither the record nor
  the sp3 3.2 glance shows it. Fix: tag prompt events with their source (`hook` or
  `agent-turn-start`); label relays resting on agent-logged prompts in `plumb show` and the
  merge-check glance; say so in the trust-model line of `plumb hosts status`.
- [MEDIUM] (plan 2, 3.4 and 10 step 4, R1) Every lane merges into `main` and the integrate
  step expects `plumb merge-check main` to exit 4 because all records are proposed. The sp1
  plan stated "Internal merges are not merge boundaries ... the merge boundary in R1's sense
  is the owner's ... validate --merge"; next-plan drops that, so the dogfooding plan reads as
  merging through plumb's own unconfirmed-requirement gate. Fix: restore the statement
  (lane-to-main merges are internal integration; the R1 boundary is the owner's merge-check
  after confirming the FEAT-002 to FEAT-005 records) and record each internal merge's exit
  code in its merge commit.
- [MEDIUM] (sp2 7.1, concept 6.6 trigger 2, R1) `intent_flags` scores confirmed records
  only. R1 makes a proposed record a question "because of a contradiction", but no reviewed
  spec owns detecting a request that contradicts a proposed read-back the work relies on.
  Fix: state in sp2 7.1 which component does it (the same `contradiction` judgment over
  proposed records, routed to trigger 2 rather than trigger 1), or declare the gap there.
- [MEDIUM] (sp2 11.2 last paragraph, sp2 3, R12, concept 8) A `judgment` event is logged
  only "when it comes from JEV". Heuristic intent flags, ownership choices, `diff_serves`
  warnings, hidden-dependency confirmations and clarify rankings are not logged, so
  calibration (8.3) and the owner's audit cannot see them. This narrows R12's "All judgments
  are logged" and the concept's "Every judgment is an append-only log entry" without a sp2 3
  refinement row. Fix: add the row with its reason (log size, hook budget), or log heuristic
  judgments compactly (one entry per turn or per command).
- [MEDIUM] (sp2 8.1 triage offer and 6.2, R9; partly repeat) Every turn while the low-risk
  group is non-empty, the offer is repeated naming every record by ID (35+ proposed SRs in
  this batch), and the unapproved escalated set is restated as a question each turn; neither
  section says the line is deduplicated. New in round 2: tie the repeat to the sp5 delta.
  Fix: show the offer again only when the group's hash set changes; above a small N, name the
  count and `plumb triage`, keeping the full ID list in `stated.json` so the exact-set
  guarantee holds.
- [MEDIUM] (sp2 8.3, R12.1; repeat) Synthetic perturbations count up to half of
  `min_negatives`, so a calibration can pass with 3 real owner negatives and turn R8 B on
  with less owner signal than "the owner's own confirmed and revoked records"; sp2 3 does not
  list it. New in round 2: show the real/synthetic split in `plumb jev status` too. Fix: list
  the refinement with its reason, or require a minimum of real negatives per claim kind
  before `passing`; record the split in the `calibration` event and `jev status`.
- [MEDIUM] (plan 4 CS1-CS6 and drop order, 7 PS2; repeat, reported twice) R8 B auto-approval
  (CS4), calibration (CS3), the R8 `jev status`/`jev setup` commands the owner asked for by
  name (CS2), the R11 e2e measurement (CS1) and R12.2 to R12.4 (PS2, CS5, CS6) are all
  droppable SHOULD items, and `plumb align` is the first PRESENT item dropped. Dropping is
  recorded, so this is prioritisation under D11, not a contradiction. New in round 2: rank
  CS2 above CS5 and CS6. Fix: the handoff opens with every dropped owner-requested item,
  quoting the owner's words; consider making CS1 a MUST, since the plumb-clarify skill (C7)
  cannot be verified without it.
- [MEDIUM] (sp2 3 C6 and 7.1, D5; repeat, raised from LOW) The precision fixture requires
  every `contradicts` prompt flagged and no `benign` one, but sets no recall target for
  `extends`; since change words alone never flag, a heuristic missing extensions passes and
  trigger 1 for extensions rests on the agent comparing the request with injected examples.
  Fix: a recall floor for `extends` (for example 80%) in the fixture assertion, or keep the
  sp1 "compare with examples" line whenever a confirmed record matches with no flag; print
  the measured recall in the test output.
- [LOW] (sp2 8.2 against plan 3.2 item 5; reported twice) sp2 says `plumb config show` is
  "denied by the installed deny rules", but the phase-0 installer adds deny rules only for
  `triage --approve`, `spec approve` and `config auto-approve`, and no guard test covers
  `config show`. R8 also says it is "logged in the event log", which sp2 does not state.
  Fix: add `plumb config show` to the deny rules and guard tests, or record in sp2 why a
  read-only command needs only the marker check; state whether it appends an event.
- [LOW] (sp2 6.2 last bullet, D5; repeat, now reported four times) An unapproved escalated
  set is named "once per turn" as the open trigger-2 question while a `matters: true` DEC is
  asked once per hash. Fix: ask once per set hash; afterwards show it in the status card and
  the brief as "awaiting your approval: INT-###", and keep the agent's "do not write its
  code" instruction.
- [LOW] (sp3 1, 2 and 9, concept 7.5 and D15, R10.5) R10.5 names `plumb check --merge`;
  sp3 introduces `plumb merge-check` and `validate --merge` and says "Same entry point"
  without defining the alias, and the concept uses both names. Related to round 1's
  `check --merge` entry. Fix: make `plumb check --merge BASE` an alias of `merge-check`, or
  document the rename with its reason, and use one name in the concept.
- [LOW] (sp3 3.2 glance lines ending `plumb revoke SR-034`; sp2 6.1 and 6.2
  `spec approve INT-###`, `escalate decline --intent INT-###`; R9) The owner-facing lines offer
  only raw-ID commands; the plain-language path (say it in chat, the agent relays it) exists
  but is not offered. Fix: after each glance and escalation line, also offer "or say 'revoke
  <title>'" or `/plumb confirm ...`.

## Next lane IMPORT (2026-10-06)

Built: I1 to I5 (MUST) and IS1 to IS3 (SHOULD), nothing dropped. The rehearsal (IS2) is in
`docs/import-rehearsal.md`; one-pass pinning (IS3) took the exported-copy import from 2 min
14 s to 17 s. Phase 0 had not run when the lane started, so the lane wired its own entry
points; the coordinator should check them while merging.

- [MEDIUM] (plan 3.2 item 3, phase 0) The `importer/recheck.py` stub and its lazy call from
  `validate.py` were not in place. IMPORT added `recheck_import_approvals` with a call at
  the end of `validate()`, and a `by == "import"` branch near the top of
  `confirm.entry_problem` (both CAPTURE files, away from CAPTURE's hunks). The older
  `if by == "import": return "... not accepted"` line further down is now dead code, left
  in place so the merge with CAPTURE's adjacent `auto-jev` branch stays clean. Fix at
  integration: delete that line.
- [MEDIUM] (next-plan 9.3, R10.2) `confirm` accepts a `by: import` approval only when it was
  written right after the `import` event it cites (`prev == import_event`), with every
  record citing its consent path, consent digest, consented digest, run and upstream hash.
  The check that the import event approved that exact `{id, hash}` runs in
  `plumb validate` only. When R10.2 moves the logs to one file per entry, `prev` chaining
  no longer orders entries: replace it with a check that has the log context (for example
  in `checked_entries`).
- [MEDIUM] Stale links left for the coordinator, because their records are not IMPORT's and
  CAPTURE also edits the same files: SR-004#1, SR-005#3, SR-030#2 (`confirm.py`), SR-030#10
  (`validate.py`), SR-025#2 and SR-025#3 (`tests/core/test_cli_core.py`). Repin them after
  the merge. IMPORT repinned only links whose ends it changed and reviewed: SR-002, SR-003,
  SR-023, and DEC-011#1, which decides SR-023 (DEC-011 deferred `by: import` to this
  importer).
- [MEDIUM] (owner glance) SR-023's statement now says that every record is imported
  proposed except a requirement whose upstream consent pins its current content
  (SR-059). It stays proposed.
- [MEDIUM] (performance, R5 budgets at pi-agent-factory scale) On the exported copy,
  `plumb drift` takes 10 to 23 s and `plumb status` 11.7 s. Most of that time is in
  `verify/testmap.verified_tests` (5.2 s of a 10 s drift, quadratic in links). Symbol ends
  add about 1.3 s, because each call re-reads and hashes its file before the parse cache
  hit. Fix: index `verified_tests` once per map; add a stat-keyed digest cache in front of
  the content-keyed parse cache.
- [LOW] `tests/core/test_cli_core.py` (coordinator-owned) changed with I3: `plumb link ...
  path::name` is now accepted (a test node for `verified_by`, a symbol otherwise), and an
  empty name after `::` is a usage error.
- [LOW] (concept 4.5) The link table says `relates_to` goes from SR to SR. `links.ALLOWED`
  now also allows a path, for an imported `spec:<id>` relation (next-plan 9.1). Add the row
  to the concept (coordinator, `docs/**`).
- [LOW] (claims) Fixture and helper files are declared as `implemented_by` ends: the consent
  fixtures and the fixture SR-078 for SR-059, and `tests/importer/importer_helpers.py` for
  SR-060. This way their changes select the importer tests, and `verified_by` never points
  pytest at a JSON file. A support-file link kind, or an owner-approved exempt glob for
  `tests/**/fixtures/**`, would say it better.
- [LOW] (IS1) The claims import adds the upstream exempt globs (for example `**/*.md`) to
  the target's `.plumb/claims.yaml` with no owner step. At F4, the owner should review the
  merged policy before `require_trailer` gates commits.
- [LOW] (I3) Resolving a symbol end ignores the module part of `module:Qual.name`. A name
  that is only re-exported (imported, never defined in the file) falls back to the whole
  file and is reported as `symbol-narrowed`.
- [LOW] `plumb link --help` (CAPTURE's `commands.py`) still says "record ID or
  repository-relative path". Add `path::Qual.name`.
- [LOW] Pre-existing, not IMPORT's: `tests/core/test_primitives.py::
  test_every_route_names_a_module_path` already fails on the lane's base commit 9dd86c6.

## IMPORT lane review (2026-10-06): medium and low findings

Two HIGH findings were fixed in the lane: a `by: import` approval now confirms only what an
earlier `import` event written outside the agent session approved at that hash (checked in
`confirm.checked_entries`, so status, hooks, merge and validate agree), and the import
writes its approvals only after the owner answers `approvals.require_owner` in their own
terminal (refused under the agent marker; the records then arrive proposed with an
`approval-withheld` finding). The rest is recorded here.

- [MEDIUM] (`src/plumb/importer/apply.py`) When `_links` updates a record, it re-pins every
  existing link the import does not own (`derives_from` and the like) to the new record hash
  and the end's current hash. Staleness that no judgment resolved disappears, with no repin
  event and no M2 glance ("repinned without a judgment"). Example: SR-X `derives_from
  INT-5`, INT-5 changes, drift reports the link stale; a re-import that updates SR-X re-pins
  it silently. Re-pin only the links the import owns, or log the re-pin as one.
- [MEDIUM] (`src/plumb/importer/pi_factory.py`) A partial import (`--only FEAT`, or a source
  whose features list SRs that were skipped or absent) writes features whose `requirements`
  name records that do not exist, so `plumb validate` reports errors ("requirement SR-00x
  does not exist") instead of the importer reporting membership findings. Seen with the
  fixture source (10 FEAT-001 errors). Filter `requirements` to known IDs and report a
  missing-end or membership finding for the rest.
- [MEDIUM] (`src/plumb/importer/plan.py`) Re-importing an unchanged upstream source turns
  local plumb-side changes into an `update`: the plan compares with the target's current
  file, not with the previous import's `upstream_hash`. A local edit to an imported record,
  or an `implemented_by`/`verified_by`/`upstream`/`relates_to`/`corrects` link added in
  plumb (all import-owned kinds), is reverted or stripped on the next import, and the
  owner's confirmation no longer pins the record. The dry-run diff shows it but does not
  tell a local edit from an upstream change. When `source.upstream_hash` is unchanged, treat
  the record as unchanged (or emit a local-divergence finding) and keep links the import did
  not originally write.
- [MEDIUM] (`src/plumb/importer/recheck.py`, trust model) Fixed in part by the HIGH fixes:
  a `by: import` approval now needs no agent marker and the owner's terminal answer. Still
  open: consent validity rests on the shape of a JSON file in the source tree, so an owner
  who imports a tree an agent could write to confirms whatever consent it holds. Show the
  consent files' paths and reasons in the terminal question, and list `by: import`
  approvals with their source tree in the merge-boundary glance (MERGE lane).
- [MEDIUM] (`src/plumb/confirm.py`, integration) The lane edited CAPTURE-owned `confirm.py`
  and `validate.py`, and coordinator-owned `tests/core/test_cli_core.py`, outside the plan's
  ownership table (3.1), because the phase-0 recheck stub was missing. The HIGH fix adds the
  `imports` context to `entry_problem` and `checked_entries`. lane/capture rewrites the same
  functions (auto-jev branch, `remaining_entries`). At integration keep IMPORT's early
  `by: import` branch and the `imports` map in `checked_entries`, delete the dead branch,
  and run `tests/importer/test_provenance.py` after the merge; otherwise every `by: import`
  approval fails, or forged ones confirm again.
- [MEDIUM] (performance, `docs/import-rehearsal.md`, R5 budgets) At pi-agent-factory scale
  on the imported copy, `plumb drift` takes 10 to 23 s and `plumb status` 11.7 s, far above
  the seconds budget for anything a per-turn hook or status line calls; validate went from
  1.2 s to 3.2 s. Most of it is VERIFY's quadratic `verified_tests`; symbol ends add about
  1.3 s by re-reading and hashing each file before the content-keyed parse cache. After F4
  this blocks the migration target. Fix: a stat-keyed digest cache in front of
  `hashing._parse` (IMPORT), and index `verified_tests` once per map (MERGE/VERIFY).
- [LOW] (`src/plumb/confirm.py`) The second `if by == "import": return "import approvals
  are not accepted in this build"` branch is unreachable dead code that misleads readers.
  Remove it at integration.
- [LOW] (`src/plumb/importer/claims.py`) `plan_claims` overwrites the target's claims
  `epoch` with upstream's and adds upstream exempt globs (for example `**/*.md`) to
  `.plumb/claims.yaml` with no owner step. A target with its own epoch then checks claims
  from a different starting commit, and the docs-wide exemptions silently widen what needs
  no `SR:` trailer. Keep the target's epoch and make the merged policy an owner step.
- [LOW] (`src/plumb/hashing.py`) `find_definition` searches only the direct bodies of
  module, class and def nodes. A symbol or test defined under `if`/`try` (`if
  TYPE_CHECKING:`, `try: ... except ImportError:`, platform-conditional tests) resolves as
  missing: a `symbol-narrowed` finding at import, or `plumb link` exit 1, though the
  definition exists.
- [LOW] (`docs/import-rehearsal.md`) The rehearsal ran before the owner-terminal step: its
  9 `by: import` approvals were written without a terminal question. A rehearsal now run
  from a script or an agent shell gets `approval-withheld` and proposed records instead;
  re-run the approval part in the owner's terminal.
- [LOW] (tests) `tests/importer/test_claims.py` shared its basename with
  `tests/bridge/test_claims.py`, so collecting both directories in one pytest run failed
  ("import file mismatch"). Renamed to `tests/importer/test_import_claims.py` (SR-058 links
  follow). `tests/bridge/test_fidelity.py::test_merge_lists_unjudged_fidelity` already fails
  on lane commit 61697ea (`validate --merge` exits 5, the verification hold, not 4); not
  IMPORT's, check it at integration.

## IMPORT lane review, round 2 (2026-10-06): ownership and claims-range fixes

Two HIGH findings were fixed in the lane.

1. **The import lane's approval re-check broke the ownership contract (plan 3.1).** Guarantee:
   `confirm.checked_entries` re-checks every approval source, and IMPORT's `by: import`
   re-check never shares lines with CAPTURE's re-checks there, so the integration merge
   cannot drop either one. Entry points that confirm through it: `Core.status` and
   `confirmation_of` (status, brief, hooks, merge), `plumb validate`, and
   `recheck_import_approvals`. Fix at one choke point: the `by: import` approval now carries
   a copy of the `import` event it cites (`import_entry`), so
   `importer.recheck.import_problem` checks it from the entry alone. The copy must hash to
   the cited digest, which must be the approval's `prev`. The event must have been written
   outside the agent marker, and it must approve each `{id, hash}`. `checked_entries` and
   `entry_problem`'s signature are back to the base commit 9dd86c6. `confirm.py` keeps only
   the module docstring lines and the early `by == "import"` branch. `git merge-tree` of the
   lane with lane/capture and lane/hosts no longer conflicts in `src/plumb/confirm.py` or
   `src/plumb/validate.py`. Tests: `test_checked_entries_rechecks_import_and_auto_jev_approvals`
   runs a real `by: import` approval and an uncalibrated `auto-jev` approval through
   whichever `checked_entries` the branch has. Before the CAPTURE merge the auto-jev entry
   has an unknown source; after it, CAPTURE's recheck refuses it. Run it right after the
   CAPTURE merge. `test_hand_written_approval_with_a_made_up_event_is_flagged` covers the
   one case the confirmation path cannot see without log context: a hand-written log line
   carrying an import event that was never written. It confirms, but `plumb validate`
   reports it ("not the log entry right before it") and the broken hash chain. This is
   tamper-evident, as concept 4.6 states, and no weaker than before: an agent that writes
   outside the marker can forge both entries either way. This supersedes two earlier
   entries in this file: the "IMPORT lane review" MEDIUM about keeping the `imports` map in
   `checked_entries`, and the 9.3 note asking for a check with log context.
2. **The lane's commit range failed `plumb claims check --range 9dd86c6..HEAD`.**
   `tests/importer/test_claims.py` was added in e4105c9 and renamed in 3a02f02. The check
   itself enumerated every entry point of the class (a path in the range that no longer
   exists at HEAD): only these two commit/path pairs. Fixed with NC-0002
   (`.plumb/ncs/NC-0002.md`, open) and two NC-backed baseline entries in
   `.plumb/claims.yaml`; the check now reports no undeclared path. **Known integration
   conflict:** lane/capture also replaced the `baseline: []` line (NC-0001, its skill
   template move), so `.plumb/claims.yaml` conflicts when CAPTURE merges after IMPORT.
   Resolve it by keeping all three entries. The class fix belongs in MERGE-owned
   `claims.claims_check`: a path renamed or deleted later in the range should count as
   declared when its successor is declared at HEAD, or when the claiming record declared it
   at that commit. Once that lands, NC-0001, NC-0002 and their baseline entries can be
   closed. Coordinator decision.

Medium and low findings from the same review:

- [MEDIUM] (`src/plumb/hashing.py`) Test-node ends now hash the Python AST segment. This
  changes the meaning of existing `test:` ends with no migration. A test node in a
  non-Python file (one that fails `ast.parse`) now returns None, so the link dangles;
  before, the whole file was hashed. Existing approvals' `verified` pins of test-node ends
  were whole-file digests and no longer match. Example: a requirement the owner confirmed
  before the upgrade, with `verified_by test: tests/x.py::test_a`, is reported by
  `confirm.changed_tests` as changed. Status and merge then ask for re-approval, and the
  link shows target-moved until it is repinned. A `verified_by` node in a .ts or .js test
  file (pi-agent-factory has pi-ext TS tests) is always missing. Plumb's own log has no
  `verified` pins, so dogfooding does not show it.
- [MEDIUM] (`src/plumb/importer/plan.py`) A re-import treats every
  `implemented_by`/`verified_by`/`upstream`/`relates_to` link on an imported SR (and
  `corrects` on an NC) as import-owned, so it removes any such link added later in plumb
  with `plumb link`. Example: import SR-077, run `plumb link SR-077 implemented_by
  src/new.py`, then re-import the same source. The plan marks SR-077 `update` with
  `- link implemented_by src/new.py`, and apply drops that link. After the fork
  (decision 9), a refresh from pi-agent-factory silently loses plumb-side traceability,
  which shows only as one diff line.
- [MEDIUM] (`src/plumb/importer/claims.py`) An import (agent-runnable, no owner gate)
  merges the source's `exempt` globs and baseline entries into the target's
  `.plumb/claims.yaml`, which weakens the claims check with no owner confirmation. The
  merge boundary gates new `trace.exempt` config globs (merge.py ~395) but not claims.yaml
  exemptions or baseline entries. Example: `plumb import pi-agent-factory <src>` writes 8
  exempt globs and 371 baseline entries; later `plumb claims check` stops flagging
  undeclared paths that match them, and nothing asks the owner.
- [MEDIUM] (`src/plumb/importer/apply.py`, plan 9.3) Plan 9.3 says the importer writes the
  `by: import` approval directly from upstream consent. The lane first asks the owner a y/N
  in their own terminal (`require_owner`). This is stricter, consistent with R2, and stated
  in SR-059, but it changes the contract. If the coordinator or an agent shell re-runs the
  rehearsal recipe or the F4 import, it gets `approval-withheld` and every record arrives
  proposed, which contradicts the rehearsal doc's DoD-3 table. Re-run the approval step in
  the owner's terminal and update `docs/import-rehearsal.md` at integration.
- [MEDIUM] (`src/plumb/confirm.py`, integration) The phase-0 recheck stub was missing, so
  the lane edited CAPTURE-owned `confirm.py` and `validate.py` and coordinator-owned
  `tests/core/test_cli_core.py`. With fix 1 above, those edits no longer conflict, but a
  hand resolution could still drop the early `by == "import"` branch in `entry_problem`.
  Every legitimate `by: import` approval would then fail ("unknown source", or the dead
  "not accepted" branch). Run `tests/importer/test_provenance.py` right after the CAPTURE
  merge (integration order: IMPORT, then CAPTURE).
- [LOW] (`docs/import-rehearsal.md`) The rehearsal record reports 9 requirements "confirmed
  by import" from an agent-run import. That predates 3a02f02, which gates `by: import`
  approvals behind `approvals.require_owner`. Run by the agent now, it would show 0
  approvals and an `approval-withheld` finding, so the documented DoD 9.5 item 3 result
  cannot be reproduced as written.
- [LOW] (`src/plumb/importer/cli.py`) `--only` silently drops unknown kinds, so a typo
  imports nothing (or less than asked) and still exits 0. Example: `plumb import
  pi-agent-factory <src> --only SRS` leaves `wanted` empty, so the plan has 0 records; it
  prints "0 created ... 0 finding(s)" with no usage error.
- [LOW] (`src/plumb/hashing.py`) A `test:` end without `::` used to hash its whole file. It
  now goes through `hash_test_node`, gets an empty qualname and resolves as missing
  (dangling). Every test-node pin also switches from a whole-file hash to a
  function-segment hash, so all existing test-node links in other plumb repositories go
  stale at once after the upgrade. Example: a hand-written `verified_by: {test:
  tests/test_x.py}` link dangles after this lane merges, and pinned test-node links report
  `target moved` until they are repinned. Plumb's own records have no such link (all 33
  test ends carry `::`).
## Next lane CAPTURE (2026-10-06, branch lane/capture)

Built: every CAPTURE item of next-plan 4 (C1 to C7 and CS1 to CS6, all MUST under R13 Q5),
with R13 Q1 to Q4: `plumb capture`, `new`, `intent`, `example`, `decide`, `escalate check|
decline`, `spec show|approve|state`, `triage [--approve low-risk]`, `relay --group|--set`,
`config auto-approve on|off|show|card`, `jev status|setup|calibrate`, `clarify`; the skills
`plumb` and `plumb-clarify`; `plumb.capture.api` (sp2 11.1) and the `JudgmentBackend`
additions (sp2 11.2). New records: INT-021 (the R13 answers), SR-069 (Q4 "self-recorded
message"), NC-0001 (claims baseline for the moved skill template); all proposed.

Phase 0 had not run when this lane started (no contracts, routes or installer changes on
the base 9dd86c6). The lane wrote the phase-0 pieces it needed, kept to small additions,
and the coordinator should expect conflicts there at merge:

- `contracts.py`: `ApprovalBy` "auto-jev"; `JudgmentAction` values; `Judgment.probability`
  and `confidence_label`; the protocol methods; `CaptureResult`, `IntentFlag`, `DiffStats`,
  `EscalationSuggestion`, `TriageItem`, `TriageView` (with `offer`), `IntentCardData`,
  `AutoApproveState`, `Proposal`, `ClarifyView`. Not written: `TurnEvent`, `TurnOutput`,
  `MergeReport`, `Resolution`, `CardMode`, the `StatusSnapshot` additions.
- `config.py`: `triage`, `auto_approve`, `calibration`, `clarify` (answered_min 0.6),
  `hints`, `escalation.shared_globs|irreversible`, `judgment.jev.credential_env`. Not
  written: `present`, `resolve`, `merge`, `hooks.stop_tokens`, `capture`.
- `cli.py`: routes and help for the CAPTURE verbs only.
- `pyproject.toml`: the `jev_live` marker (shared test infrastructure: full verification
  pending until the integrate run).
- `install.py` (PRESENT/HOST): installs every `templates/skills/<name>/SKILL.md` (the skill
  moved there; SR-015, SR-030 and SR-032 re-pointed and repinned); deny rules for
  `triage --approve`, `spec approve`, `config auto-approve`, `config show`.
- `stop.py` (PRESENT): one decision that matters per message (R11), the earliest first.
- `prompt.py` (PRESENT): prompt-log entries carry `"via": "hook"` (R13 Q4).
- `readback.py` (PRESENT): `plumb show` labels "confirmed by JEV" and "self-recorded message".
- `commands.py`: `relay --group|--set`, and `plumb drift` prints hint lines (never signals).

Interfaces the other lanes still have to call (not wired by CAPTURE):

- PRESENT: the stop hook writes `stated.json` `groups` from `capture.api.stated_group(
  capture.api.triage(core))` and prints `TriageView.offer` (R8 A, Q2), deduplicated; the
  brief carries the same offer line; the prompt hook prints `capture.api.escalation` lines
  and may replace its flag lines with `capture.api.intent_flags` + `flags.flag_line` (the
  heuristic `intent_change` already uses the contradiction scoring); the stop hook names an
  unapproved escalated set with `capture.spec.waiting_line` (once per set hash); the status
  line uses `confirmation_counts` ("N by JEV", "self-recorded") and `auto_approve_state`
  ("auto-approve suspended: model changed, recalibrate"); the untraced instruction can
  append `ownership_proposals(...)[path].line`; `card.render` is the plain card PRESENT may
  replace with `present.render.intent_card`.
- MERGE: `trailers check-msg` calls `capture.api.diff_serves` (MS2); the glance lists
  approvals whose payload has `by: auto-jev` (with `auto.score`) or `self_recorded: true`
  ("self-recorded message", Q4); `capture.spec.set_state` gives a set's state.
- HOSTS: a host whose own hook records the owner's prompt writes `"via": "hook"` in
  `.plumb/session/prompts.jsonl`; a prompt the agent records itself (CLI fallback) leaves
  it out, and every confirmation resting on it is labelled "self-recorded message" (Q4),
  which the host status should show.
- IMPORT: `confirm.entry_problem` still refuses `by: import`; the phase-0
  `importer/recheck.py` hook in `validate.py` was not written by this lane.

Medium and low findings, and open notes:

- [MEDIUM] Triage with JEV makes one call per uncached record (no batching): up to 8 s on
  the command line, 0.6 s in a hook; records not scored in time stay "unrated" and
  individual. Fix: batch the Noul questions of several records in one request.
- [MEDIUM] Calibration uses the current content of confirmed and revoked records (the log
  keeps hashes, not the text the owner saw); a revoked record edited afterwards is labelled
  by its new text. Fix: keep the approved text digest-addressed in the cache, or calibrate
  only records unchanged since their approval or revocation.
- [MEDIUM] The heuristic fixtures (36 intent prompts, the e2e questions) were written with
  the heuristic in view: they guard against regressions, not real-world precision.
- [LOW] The pre-existing failure `tests/bridge/test_fidelity.py::
  test_merge_lists_unjudged_fidelity` also fails on the base 9dd86c6 (merge-check output);
  MERGE's area.
- [LOW] The commit-msg hook installed from `C:/coding/plumb/.venv` checks trailer presence,
  not the claims; three of this lane's commits had undeclared paths, caught by `plumb claims
  check` and declared afterwards (c2aa6c4). Fix: run the claims check for the commit's own
  paths in `trailers check-msg`.
- [LOW] Links of SP1 requirements made stale by this lane's edits (SR-010, SR-017, SR-021,
  SR-026, SR-027, SR-029, SR-030, SR-032 and others) are left stale for review: the
  heuristic intent-change behaviour changed on purpose (sp2 C6).
- [LOW] IDs INT-021, SR-069 and NC-0001 were allocated without the R10 reservation; another
  lane may have used the same numbers (`plumb merge-fix` is SP6).
- [LOW] sp2 4's decision field `asked` is not written: writing it would change the record
  hash and re-ask; the stop hook's session `asked` map keeps that state.
- [LOW] `plumb config show` is refused under the session marker as sp2 8.2 says; the agent
  reads the same state through `plumb jev status`, which is not owner-only.
- [LOW] The JEV `choose` and `contradiction` wire shapes are verified against the local stub
  only; the `jev_live` test covers `entailment`.

## CAPTURE lane review (2026-10-06, lane/capture)

Raised by the review of lane/capture. Both HIGH findings were fixed in the same change: `plumb
relay --set` now checks every set id against the stated set (`approvals._check_set_shown`),
and auto-approval refuses a prompt the prompt hook did not log, in `autoapprove.gate` and in
the validate re-check (`autoapprove.recheck`).

- [RESOLVED, raised to HIGH under R7] (capture review, src/plumb/capture/capture.py) Records captured against an existing escalated INT (`intent: "INT-x"` as a reference) are not added to the anchor's `members`, so they fall outside the set approval and the escalated-set exclusions: `autoapprove.gate` can auto-approve such an SR and triage can put it in the low-risk group, although it belongs to an up-front spec (R8 B: never for an escalated spec set). Scenario: with an escalated INT-021 and auto-approve on, `plumb capture` with intent "INT-021" and one requirement whose examples quote the prompt auto-approves the new SR by: auto-jev instead of waiting for the owner's set approval.
- [MEDIUM] (capture review, src/plumb/hosts/claude_code/stop.py) R11's one-question-per-message rule rests on a 4-line edit to the PRESENT-owned stop.py, which lane/present rewrote heavily and whose version still computes `open_decisions` over every decision. Fix: PRESENT calls `capture.api.next_question`, and tests/capture/test_clarify_e2e.py runs on the merged result. Scenario: the merge keeps PRESENT's side of stop.py, two matters DECs are asked in one message, and `test_ambiguous_request_yields_exactly_the_questions_that_matter` fails.
- [MEDIUM] (capture review, src/plumb/contracts.py) Phase 0 never ran: the lanes branch from 9dd86c6, and this lane wrote coordinator-owned contracts.py, config.py and cli.py and PRESENT-owned prompt.py, stop.py, readback.py and install.py while lane/present and lane/hosts edit contracts.py, config.py, cli.py and prompt.py. The frozen interface contracts (plan 3.2, 3.5) are no shared base; integration reconciles the dataclasses and routes by hand. Scenario: choosing either side wholesale drops CAPTURE's TriageView.offer, AutoApproveState and routes, or PRESENT's StatusSnapshot additions.
- [MEDIUM] (capture review, src/plumb/contracts.py) The same ownership break, seen from the merge: lane/present's IntentCardData has fields (kind, statement, alternatives) this lane lacks, and this lane edits PRESENT-owned stop.py (one DEC per message), prompt.py (`via: hook`), install.py and readback.py, which lane/present rewrote (stop.py +328 lines). The integrate merge needs a careful union. Scenario: resolving stop.py/prompt.py with PRESENT's side drops `via: hook` from prompt-log entries, so every relayed confirmation is labelled "self-recorded message" and auto-approval never fires, and the stop hook asks every matters-DEC at once again.
- [MEDIUM, membership part RESOLVED] (capture review, src/plumb/capture/autoapprove.py) `recheck()` checks the record kind only by ID prefix. It did not re-check membership of an escalated set (now fixed: see the next section), nor the Q3 rule that the wording and every example were judged (`parts` against the record's examples). Scenario: a hand-written auto-jev approval of an escalated-set member with a valid score, calibration and hook-logged prompt passes `plumb validate`.
- [MEDIUM] (capture review, src/plumb/capture/cli.py) sp2 8.2 says `plumb capture` and `plumb example` ask the gate for each record they wrote; `cmd_example` never asks it. Not unsafe (it only narrows auto-approval). Scenario: with auto-approve effective, `plumb example SR-x --given .. --when .. --then .. --quote <owner span>` leaves the SR proposed.
- [LOW] (capture review, src/plumb/capture/triage.py) The triage score cache is keyed by backend|version|record.hash, but the premise also depends on the parent INT's quote and on derives_from links. Scenario: SR-x scored faithful keeps that rating, and its place in the low-risk offer, after its INT's quote is edited or re-linked to say something else.
- [LOW] (capture review, src/plumb/capture/jevcmd.py) `plumb config show` is refused only under the session marker (plus an installer deny rule), not through the interactive-terminal check. It is read-only, so the risk is small. Scenario: an agent shell on a host whose adapter cannot set the marker runs `plumb config show`.
- [LOW] (capture review, src/plumb/approvals.py) On lane/capture nothing writes `groups` into .plumb/session/stated.json; only test helpers do, so `plumb relay --group low-risk` (the in-session "ok" of R8 A / Q2) always refuses on this branch. lane/present's stop hook (triage_offer, write_stated(group=...)) supplies the writer: verify it in the integrate phase. Scenario: on lane/capture alone, the agent's `plumb relay --group low-risk` exits 3 with "no group low-risk in the stated set".
- [LOW] (capture review, src/plumb/capture/hints.py) The hidden-dependency budget (`hints.hidden_deps_s`) is checked only before each backend.ask; the per-subject `git show HEAD:<path>` calls (1 s timeout each) run outside it, and `plumb drift` AST-parses every bare verified_by test file. No hook calls it today. Scenario: twenty changed confirmed records or docs mean twenty sequential `git show` calls before the first deadline check, so drift_hints takes several seconds.

## CAPTURE lane review, round 2 (2026-10-06, lane/capture)

Three HIGH findings were fixed as two classes, each at one choke point with one test per entry
point:

- Open decisions that matter: `plumb.capture.clarify.open_decisions` (unconfirmed AND not
  superseded, linked by `decides`/`derives_from`, earliest first) is the one rule read by the
  stop hook (`stop.matters_decisions`), `next_question` and the escalation trigger. A DEC
  superseded with `plumb decide --supersede` no longer blocks the one-question-per-message
  queue (tests/capture/test_open_decisions.py).
- Escalated-set membership: `plumb.capture.spec.escalated_sets` counts declared members AND
  every record deriving from or deciding the anchor or another set record (`plumb capture`
  with `"intent": "INT-x"`, `plumb new`/`decide` against it). The set hash covers them, so the
  set needs the owner again. Read by `autoapprove.gate`, the validate re-check
  (`autoapprove.recheck` via `confirm.checked`/`remaining`/`statuses`), triage's exclusion and
  `spec.set_state` (tests/capture/test_escalated_membership.py).

- [MEDIUM] (capture review 2, src/plumb/merge.py) `merge.approved_ends` still calls
  `confirm.checked_entries` without the escalated set (merge.py is rewritten on lane/merge, so
  this lane left it). An auto-jev approval of a record of an escalated set, rejected
  everywhere else, still lends its `ends` to the owned-ends check. Fix at integrate: call
  `confirm.checked(core)`. Scenario: a hand-written auto-jev approval of a set member lists
  ends, and `approved_ends` treats them as owner-confirmed ownership.
- [LOW] (capture review 2, src/plumb/capture/spec.py) A record joins an escalated set through
  links, so the owner's set approval of an older set hash no longer holds once a record
  derives from it. `plumb spec show` lists the joined records, but the stop hook's waiting
  line does not say which record reopened the set. Scenario: after `plumb new requirement
  --derives-from INT-021`, the stop hook says only that INT-021 waits for the owner.
## Next lane MERGE (2026-10-06)

Built on branch `lane/merge` (worktree `C:/coding/plumb-merge`): M1 to M6 (MUST) and MS1 to
MS3 (SHOULD; MS2 is R12.3 and so MUST under R13 Q5). Nothing of the lane is left unbuilt.
`plumb merge-check main --no-run` on plumb itself takes about 3.6 s and exits 1 only on the
three `src/plumb/cli.py` stale links named below; after their repin it exits 5 (full
verification pending, unverified acceptance tests), and after its one full run, 4 (the
records await the owner), as the plan expects.

Notes for the coordinator (phase 0 had not run when the lane started from `work`):

- [MEDIUM] (contracts) `MergeReport` lives in `plumb/boundary/report.py` (re-exported by
  `plumb.boundary`), not in `contracts.py`; move it there when the contracts are frozen. The
  lane added one route (`merge-check` -> `plumb.boundary.cli`) and one help line to the
  coordinator's `cli.py`, and reads `merge.default_base` and `merge.prepush_run_full` from
  `core.config.merge` when it exists, else straight from `.plumb/config.yaml`.
- [MEDIUM] (records) `src/plumb/cli.py` links SR-012#8, SR-031#6 and SR-033#2 are left stale
  for the coordinator to repin after every lane's route is merged (a stale link of a touched
  requirement now holds the merge with exit 1). SR-044 (CAPTURE) is not linked to
  `src/plumb/claims.py` or `tests/bridge/test_trailers.py::test_diff_serves_warning_never_blocks`;
  link it at integration (the MS2 commit claims SR-049 and SR-007 instead).
- [MEDIUM] (R13 Q4 convention) The glance labels a relay "self-recorded message" when the
  approval payload, its committed `prompt` event or its `.plumb/session/prompts.jsonl` line
  carries `self_recorded: true`, `via: turn|turn-start|cli|agent|self` or `host: cli`. Nothing
  writes these fields yet: HOSTS (`plumb turn start`) and CAPTURE (`plumb relay`) should set
  `self_recorded: true` on prompts the agent logs itself, so `plumb show` and the host status
  read the same field.
- [MEDIUM] (pre-existing, CAPTURE file) `tests/bridge/test_fidelity.py::test_merge_lists_unjudged_fidelity`
  fails on `work` before this lane (it expects exit 4; the fixture has a test file and no full
  run, so full verification is pending and the exit is 5). Fix the test (record a full run, or
  expect 5); the merge boundary is right.
- [LOW] (sp3 4) The full run starts whenever it is needed, even when exit-1 findings (claims,
  links, integrity) already hold the merge, as the spec says. Skipping it then would save a
  suite run that cannot turn the report green; it would also mean a second merge-check runs it
  after the fix, which is still one run per invocation.
- [LOW] (SR-052 EX-1) `--no-run` may rebuild the gitignored, derived `.plumb/test_map.txt` (the
  test map); the lane's test counts it with `.plumb/cache/` as a cache, not state.
- [LOW] (sp3 6, MS1) The 5 s JEV budget is checked between packets; one slow JEV call can
  overrun it by the client timeout. The pre-score runs through a no-write view of the core, so
  no `judgment` event is logged; JEV's own notice file under `.plumb/session/` may be written.
- [LOW] (sp3 8) Hook mode checks only pushed refs that point at the checked-out HEAD (the
  report covers the working tree); other refs are skipped with a message, and uncommitted
  changes count in the report although they are not pushed.
- [LOW] (sp3 5) Validation errors anywhere in the repository (not only on touched records)
  hold merge-check with exit 1, so `plumb validate --merge` (whose validate part already did)
  and `plumb merge-check --no-run` give the same exit (SR-047 EX-3). An `auto-jev` approval in
  the range is an approval error until CAPTURE's CS4 teaches `confirm.entry_problem` the new
  source, so it holds with exit 1 meanwhile.
- [LOW] (claims) `tests/merge/merge_helpers.py` is declared as an `implemented_by` end of
  SR-047 so the claims check accepts it; a `verified_by` link would make the helper an
  acceptance test with no evidence. A `support` link kind, or a claims exemption for
  `tests/**/*_helpers.py`, would say this better.

## Next lane MERGE review (2026-10-06, lane/merge b5ce535): medium and low findings

The review's one HIGH finding (hook mode started a second full run for a second pushed base) is
fixed in `plumb.boundary.cli._hook_pre_push`: once a report has run the suite, the remaining
bases only report. The findings below are recorded, not fixed.

- [MEDIUM] (`src/plumb/boundary/report.py`, SR-052, sp3 7) merge-check is not one screen. The
  awaiting list is capped at 10 records, but each record prints its full statement, every
  example and its new ends, so the cap counts records rather than lines.
  `python -m plumb merge-check main --no-run` on plumb itself prints 77 lines; ten awaiting
  records take about 40 of them, and the fidelity, verification and links lists add more. sp3 7
  asks for at most 12 lines outside the lists, with each list capped at 10 rows.
- [MEDIUM] (`src/plumb/cli.py`) The lane edited the coordinator-owned `cli.py` (merge-check
  route and help line) and left three stale links on it: SR-012#8, SR-031#6 and SR-033#2. Phase
  0 had not run. `plumb merge-check main --no-run` exits 1 on the lane branch because of those
  links, where sp3 10 item 6 expects exit 4. The integrate phase must repin them and reconcile
  the route with the phase-0 ROUTES, or every merge-check on the merged tree exits 1.
- [MEDIUM] (`src/plumb/boundary/report.py`) `MergeReport` is defined in `plumb.boundary.report`,
  not in `contracts.py` as plan 3.2 and sp3 9 require, and `merge_report` has an extra `runner`
  keyword, so the frozen coordinator contract and the lane's type can diverge. If phase 0 adds
  `contracts.MergeReport` with the sp3 9 field list, PRESENT's `/plumb review` may import it; it
  lacks the fields this lane added (`required`, glance `self_recorded`, `verification`,
  `evidence`, `error`).
- [MEDIUM] (`src/plumb/boundary/glance.py`, R13 Q4) The "self-recorded message" label depends on
  a convention no lane has agreed: `self_recorded`, or `via: turn|cli`, or `host: cli`, on the
  approval, the prompt event or the prompt-log line. HOSTS sets `via=turn` only in
  `HookContext.extra`, and neither CAPTURE's relay nor PRESENT's prompt hook is contracted to
  persist it. On a CLI-fallback host, `plumb turn start` logs the prompt and the agent relays the
  owner's "ok"; without the field on the prompt-log line the glance shows a plain AGENT-RELAYED
  row with no "self-recorded message" label, contradicting Q4 until integration wires it.
- [MEDIUM] (`src/plumb/boundary/prepush.py`, sp3 8, R1) When the remote ref exists, hook mode
  uses the remote sha as BASE, so a push that updates an existing branch checks only the new
  commits; pushes of refs other than HEAD are skipped and allowed with exit 0. A feature branch
  pushed earlier with an unconfirmed SR in its first commits passes on a later one-commit push;
  `git push origin other-branch` passes unchecked. This matches the letter of sp3 8 but weakens
  the R1 boundary.
- [LOW] (`src/plumb/claims.py`) The commit-msg hook calls `capture.api.diff_serves` with no time
  budget. Once CAPTURE wires JEV into `diff_serves`, each `git commit` may block up to the JEV
  client timeout per claimed SR. The warning is non-blocking, but latency is unbounded there.
- [LOW] (`src/plumb/boundary/report.py`) `claims.yaml` "problems" rows print under the header
  "claims hold the merge:" although `claims_gate` does not hold the merge on them; the exit stays
  0 or 4, which misleads the glance.
- [LOW] (`src/plumb/merge.py`) `show_many` parses `git cat-file --batch` headers by whitespace
  split. A missing path containing a space gives a 3-token header (`<commit>:a b missing`) and
  `int(b"missing")` raises ValueError, crashing `merge_report`. Record paths are `SR-###.md`
  today, so this is latent.

## Next lane MERGE review, round 2 (2026-10-06, lane/merge a37b752): medium and low findings

The HIGH findings in this round were fixed in this lane: `exit_code` now fails closed when
verification is unavailable (exit 5, with the error rendered), and the glance reads auto-jev
fields through one `auto_fields` helper that accepts CAPTURE's nested `payload["auto"]` shape
(label in `confidence_label`) and the flat sp2 8.2 shape. Integration should add a test that
drives `capture.autoapprove.gate` end to end into `glance_rows`, because the test here
reproduces the writer's payload literally and capture's JEV stub fixtures are not on this
branch. It should also settle which shape sp2 8.2 states.

- [MEDIUM] (`src/plumb/cli.py`) The lane edits coordinator-owned `src/plumb/cli.py` to add the
  merge-check route (plan 3.1 gives cli.py to the coordinator in phase 0), and it does not repin
  the links this makes stale: SR-012#8, SR-031#6 and SR-033#2 (implemented_by
  src/plumb/cli.py). `plumb merge-check main --no-run` on lane/merge exits 1 ("links of touched
  requirements hold the merge: stale link SR-012#8 ... src/plumb/cli.py"), where sp3 DoD 6
  expects 4, and the plan 3.4 ownership-diff gate fails. CAPTURE, HOSTS and PRESENT edit cli.py
  too, so phase 0 apparently never ran: the coordinator must reconcile ROUTES and repin at
  integration.
- [MEDIUM] (`src/plumb/boundary/report.py`) `MergeReport` lives in `boundary/report.py`, not in
  `contracts.py` as plan 3.2 and sp3 9 require. When phase-0 or lane contracts land, two
  diverging definitions can exist. PRESENT imports `MergeReport` from `plumb.contracts` per the
  plan, and a coordinator-defined class with different fields will not match what
  `merge_report` returns.
- [MEDIUM] (`src/plumb/boundary/report.py`, sp3 7) `render()` does not fit one screen. The
  awaiting list caps rows at 10, but each row expands to the full statement, every example and
  the new-link lines. On plumb's own repo, `plumb merge-check main --no-run` prints 77 lines,
  with lines 3-44 alone holding 10 awaiting rows. The spec allows at most 12 lines outside the
  lists, with each list capped at 10 rows.
- [MEDIUM] (`src/plumb/boundary/prepush.py`) `hook_bases` skips any pushed ref that is not the
  checked-out HEAD, and any ref with neither a known remote sha nor a resolvable
  `default_base`; when nothing remains, `_hook_pre_push` returns 0. `git push origin feature-x`
  with another branch checked out, or a new branch in a repo whose default branch is not
  `main` and that has no `merge.default_base`, prints "merge-check skipped" and pushes
  unchecked. The hook should refuse a pushed ref it cannot check, or report a non-zero exit.
- [MEDIUM] (`src/plumb/boundary/report.py`) The full run starts even when the report is already
  certain to hold with 1 (claims, links, integrity) or 4. It pays for the whole suite, writes
  no merge evidence, and adds latency to the pre-push hook. Example: a branch with a stale link
  and a conftest.py change runs the entire suite once and then exits 1. The next invocation
  reuses the run only when the tree identity is unchanged.
- [MEDIUM] (`src/plumb/boundary/report.py`, sp3 10 item 6) The definition of done is not met.
  On plumb's own tree, `plumb merge-check main --no-run` exits 1 instead of 4 because three
  links to src/plumb/cli.py are stale (SR-012#8, SR-031#6, SR-033#2). The lane repinned 54
  other links but not these after adding the merge-check route. Run in C:/coding/plumb-merge,
  `.venv/Scripts/python.exe -m plumb merge-check main --no-run` prints "links of touched
  requirements hold the merge: stale link SR-012#8 implemented_by src/plumb/cli.py ..." and
  exits 1.
- [MEDIUM] (`src/plumb/cli.py`) The lane writes outside its ownership row in plan 3.1:
  src/plumb/cli.py (the ROUTES entry and help text) and `.plumb/**` are coordinator-owned.
  Phase 0 never ran on this base (9dd86c6), so `MergeReport` is defined in
  `boundary/report.py` instead of `contracts.py`, and the merge config section is read through
  a local fallback. The lane gate step "git diff --name-only main...HEAD: every path in the
  lane's row" fails for src/plumb/cli.py. A duplicate `MergeReport` type and a conflicting
  ROUTES or help edit will need reconciling at integration.
- [MEDIUM] (`src/plumb/boundary/report.py`, KEEP failure policy) An owner waiver of the full run
  also suppresses the run that would verify unverified touched acceptance tests:
  `waived = full_waived or ((pending or unverified) and _waived(...))` makes `needed` false,
  but `exit_code` still returns 5 for `report.unverified`. The check holds with no run, while
  the full-run line says "waived by the owner". When infrastructure changes, the owner waives
  (`plumb tests waive --merge main`), and a touched requirement also has a never-run
  acceptance test, `plumb merge-check main` runs nothing and exits 5 on every call until
  someone runs `plumb tests run --nodes` by hand. The KEEP policy expects a targeted rerun
  after an owner waiver.
- [LOW] (`src/plumb/boundary/fidelity.py`) The 5 s JEV budget is checked only between calls, so
  one slow `backend.fidelity` call can exceed it. `jev_scores` also runs under
  `plumb validate --merge` (run_full=False). With JEV configured and a slow network, a single
  scoring call blocks merge-check or `validate --merge` for as long as the backend's own
  timeout.
- [LOW] (`src/plumb/boundary/glance.py`, R13 Q4) The "self-recorded message" label depends on
  writers setting the `self_recorded`, `via` or `host` markers. A relay whose prompt digest
  appears in neither the prompt log nor the prompt events is not labelled self-recorded. On a
  CLI-fallback host whose relay writer does not set these markers, the glance shows a plain
  AGENT-RELAYED row with no label, although no prompt hook ever logged the digest.
- [LOW] (`src/plumb/boundary/prepush.py`) The pre-push hook is written into the common hooks
  directory, which every worktree shares, but it hard-codes the installing worktree's venv
  interpreter. Pushes from other worktrees run that worktree's plumb code. If the hook is
  installed from C:/coding/plumb-merge and that worktree is later removed, every `git push`
  from C:/coding/plumb fails with "not found" (exit 127) and git refuses the push.
- [LOW] (`src/plumb/boundary/prepush.py`) `hook_bases` uses the remote sha as BASE, as the spec
  says, so a re-push of an existing branch checks only the commits since the last push, not the
  change against main. Pushed refs other than the checked-out HEAD are skipped with exit 0.
  Example: a branch pushed once with exit 4 and `--no-verify`, then pushed again after one more
  commit, is checked only on that commit's touched requirements. Likewise,
  `git push origin feature` from a main checkout passes without any check.
- [LOW] (`src/plumb/boundary/fullrun.py`) In pre-push hook mode, a green report appends a
  merge-evidence entry to the committed evidence log after the commits being pushed, so the
  pushed history never contains the evidence for that push. A green `git push` leaves
  `.plumb/log/evidence.jsonl` modified in the working tree, and the remote has no
  merge-evidence for the pushed head until a later commit adds it.
## Next lane PRESENT (2026-10-06)

Built: P1 to P6 and PS1, PS2 (all items, R13 Q5). Integration notes for the coordinator first,
then medium and low findings.

- [INTEGRATION] Phase 0 did not run before the lanes, so PRESENT wrote its own contract
  pieces; keep the union at merge: `contracts.py` (`StatusSnapshot.state`, `intent_summary`,
  `confirmed_by`, `auto_approve`; `CardMode`, `Resolved`, `Resolution`; an
  `IntentCardData` identical to CAPTURE's plus `kind`, `statement`, `alternatives`, all
  defaulted, which the cards need to show a record in full), `config.py` (`present`,
  `resolve`, `hooks.stop_tokens`), `cli.py` (status, brief, drift, show, explain, why and
  impact now route to `plumb.present.cli`; `help_text()` filters `_HELP` to importable
  verbs, so the other lanes' help lines merge as text; `main` returns a module's argparse
  exit code instead of raising `SystemExit`).
- [INTEGRATION] Still to do in CAPTURE-owned `commands.py`: the `init` config template
  lines for `present`, `resolve` and `hooks.stop_tokens`, and `view/` in
  `GITIGNORE_LINES` (plumb's own `.plumb/.gitignore` has it already).
- [INTEGRATION] `tests/integration/test_session_e2e.py` lines 173 and 176 (coordinator
  file) assume the sp1 summary: the first line is now the status card, and in the default
  `compact` mode "questions: none" ends the second summary line
  (`plumb: covering tests ... | questions: none`). Update to `lines[1].startswith("plumb:
  touched SR-001")` and `"questions: none" in summary`.
- [INTEGRATION] `hosts/neutral.py` was written by HOSTS; PRESENT left it alone. It
  delegates to the Claude Code handlers, so every host already gets the emitter, the
  status card and the cards. HOSTS' own copies of `tests/host/test_statusline.py` and
  `test_latency.py` assertions on the old status line format are superseded by PRESENT's.
- [MEDIUM] `plumb confirm` writes the stated set mid-turn. A relay for the current
  prompt made after `plumb confirm` in the same turn is refused (the set is newer than the
  prompt). The skill should say "relay before confirm"; fix: keep the previous reply's set
  under a `previous` key that `approvals._stated` reads.
- [MEDIUM] The stop hook computes the triage offer for this turn's proposed records only
  (latency); `plumb confirm`, `plumb review` and the brief's offer line use every proposed
  record. sp5 3 does not say which set the summary offers.
- [MEDIUM] `plumb align` with the heuristic reads each code and test file (4000 characters)
  per edge; on plumb itself `plumb view` (which aligns every requirement) takes about 8 s.
  Fine on demand; the fingerprint cache makes reruns cheap, but a large repository wants a
  per-file text cache.
- [LOW] With `present.ascii`, `to_ascii` drops characters outside ASCII from a card, so the
  shown text can differ from the record by accents; the stated set still pins the hash.
- [LOW] `plumb view --open` uses the platform opener on the folder, not the
  `obsidian://open?path=` URI (sp5 7 offers either).

## PRESENT lane review (2026-10-06): HIGH findings fixed, the rest recorded

Fixed in this lane (HIGH, each as a class at one choke point, one test per entry point):
- One-shot agent lines are never cut by the budget (`present.delta.Line.oneshot`): the
  prompt hook's untraced-change instruction, its queued cascade escalations and the
  blocked stop's untraced-change instruction. Their source is consumed when read, so a cut
  lost them for good. Tests: `tests/present/test_delta.py`.
- `/plumb confirm` reaches the owner through the confirm turn's stop hook only
  (`hosts/claude_code/stop.confirm_view`): `plumb confirm` prepares records (`shown:
  false`) and its triage group (`confirm_groups`, not relayable). Every stop path (no
  change, with changes) renders each record as a full intent card plus the group's offer
  line, marks shown exactly what it rendered, and promotes the group to `groups` for
  `plumb relay --group`. A blocked stop keeps them unshown. Tests:
  `tests/present/test_confirm.py`.
- Who confirmed a record has one label (`present.cards.confirmed_label`: you, you
  (relayed), JEV, plus CAPTURE's "self-recorded message"). It is used by `plumb show`,
  `plumb explain`, the vault notes and the cards. Tests: `tests/present/test_labels.py`.

Recorded, not fixed:
- [MEDIUM, fixed in round 2 below] `src/plumb/present/__init__.py`: the PRESENT-owned cross-lane interface
  `plumb.present.api` (sp5 9: brief, relevant, show, explain, impact, drift, resolve) is
  missing. Phase 0 never ran, so there is no stub or delegation either. HOSTS' MCP server
  (`src/plumb/mcp/server.py:_resolve` on lane/hosts) imports
  `plumb.present.api.resolve`, gets ImportError, and silently passes the owner's words
  through unresolved. The `Resolution` type here has no `best` or `ref` attribute, which
  HOSTS reads. The impact and explain CLIs resolve plain words themselves, so the loss is
  limited today, but the plan 3.5 contract is unmet.
- [MEDIUM, fixed in round 2 below] `src/plumb/hosts/claude_code/stop.py`: with `present.card: off`, `summary()`
  hides the triage offer line (extra lines are kept only when they contain "escalated"),
  but `write_stated` still pins the triage group. The owner's next "ok" to something else
  (for example a DEC question card) could be relayed with `--group low-risk` and approve
  records whose offer was never shown. Fix: pin the group only when its offer line was
  rendered.
- [MEDIUM] `src/plumb/align.py`: `collect()` stops at test and code nodes. It does not
  expand to evidence (sp5 8: "... -> test -> code -> evidence") and never reports the
  spec's example gap "an example with no evidence". An SR whose example has a
  verified_by test that never ran shows no gap, so /plumb review and the vault's edge
  badges present the chain as complete.
- [LOW] `src/plumb/present/review.py`: `_glance` lists every agent-relayed or auto-jev
  approval since the last merge evidence, including revoked ones, which suggests they are
  still in force. It also omits the "self-recorded message" label (R13 Q4) on
  CLI-fallback confirmations; `present.cards.confirmed_label` is the label path to reuse.
- [MEDIUM] `src/plumb/hosts/claude_code/session_start.py`: `triage_offer_line` (session
  brief and `plumb brief`) prints only a count ("N records rated faithful to your words
  await you"). R13 Q2 (DEC-017) says the offer names up to about 5 records by title, then
  "+N more (see plumb triage)". The stop summary uses CAPTURE's `offer_line`, which
  follows Q2. The brief's line pins no group, so it is a pointer rather than a
  confirmable offer, which limits the risk.
- [MEDIUM] `src/plumb/hosts/claude_code/prompt.py`: `escalation_lines` advances
  `escalations.offset` before the lines are emitted, so a budget cut dropped a queued
  escalation for good. Addressed by the one-shot class fix above (escalation lines are
  `oneshot`); recorded here for the review trail.
- [LOW] `src/plumb/contracts.py`: this lane wrote coordinator-owned phase-0 files
  (`contracts.py`, `config.py`, `cli.py`, the `.plumb/requirements` repins) because phase 0
  was not done on main. CAPTURE and HOSTS define overlapping dataclasses
  (`IntentCardData`, `StatusSnapshot`) in the same file. Merging lane/capture then
  lane/present conflicts on `IntentCardData` (PRESENT adds `kind` and `statement`) and on
  the `StatusSnapshot` fields; resolve by hand before the focused sets run.
- [INTEGRATION] `plumb confirm` now writes its triage group under `confirm_groups` with
  an `offer` key. CAPTURE's `approvals._stated_group` reads only `groups`, which the stop
  hook fills after it renders the offer. On a host with no stop hook, a prepared group is
  therefore never relayable, and the owner names the records or uses `plumb triage
  --approve` in the terminal. This is the intended safe default (R2).

## PRESENT lane review, round 2 (2026-10-06): HIGH findings fixed, the rest recorded

Fixed in this lane (HIGH, each as a class at one choke point, one test per entry point):
- Per-turn lines fire once per turn, never once per session. Guarantee: every turn whose
  covering tests lack fresh evidence blocks once, and every affirming prompt that follows
  a stated set is told how to relay, even when the owner repeats the same words ("ok",
  "continue"). Choke point: `present.delta.Line.per_turn`, whose key carries the
  emitter's turn (`turn_id`, a nonce the prompt hook writes to `turn.json`). Entry points:
  the stop hook's covering-tests instruction (was keyed by the prompt digest), the prompt
  hook's awaiting-confirmation relay line (was keyed by its text, which holds the prompt
  digest). Tests: `tests/present/test_delta.py` (the emitter, the stop entry point and the
  prompt entry point); SR-063 EX-5. The blocked stop's skipped-check notice is marked
  `per_turn` too; it has no test of its own (it rides on a block another line causes).
- A triage group is pinned in the stated set only when its offer line reached the owner
  (R2, R13 Q2). Choke point: `hosts/claude_code/stop.write_stated` pins `group` only when
  every offer line is a line of the message the owner is shown (`stop.offered`). Stop
  paths: compact, full and off (`tests/present/test_intent_card.py`, parametrized; off
  pins nothing), and the no-change and with-change paths of a `/plumb confirm` group with
  the card off (`tests/present/test_confirm.py`). SR-062 EX-4.
- `plumb.present.api` exists with the sp5 9 signatures (brief, relevant, show, explain,
  impact, drift, resolve), read-only, and `plumb brief` prints `api.brief`, so the CLI and
  the MCP server show the same lines. `Resolution.best` is the one clear match (None when
  ambiguous or empty), which HOSTS' `mcp/server._resolve` reads. Tests:
  `tests/present/test_api.py`; SR-064 EX-5.

Recorded, not fixed:
- [MEDIUM] `src/plumb/hosts/claude_code/prompt.py`: the trigger-1 intent-change
  instruction ("this may change SR-x (confirmed) ... ask before editing") is keyed
  `flag:SR-x` plus the record's hash, so the agent gets it once per session for an
  unchanged record. A later, different prompt in the same session that also contradicts
  SR-x is still judged and flagged (turn.json gets `flagged`), but the agent is not told to
  ask before editing; only the owner-facing card appears, after the edit. sp5 3 asks for
  this deduplication, so this is not HIGH, but it weakens the "questions on a real intent
  change" trigger. Consider keying the flag by the prompt as well (`per_turn=True` on the
  flag line is the one-line change at the same choke point).
- [MEDIUM] `src/plumb/hosts/claude_code/session_start.py`: the brief's triage line
  (`triage_offer_line`, used by the session brief and `plumb brief`) prints only a count.
  R13 Q2 (DEC-017) wants up to about 5 records by title, then "+N more (see plumb
  triage)"; the stop summary uses CAPTURE's `offer_line`, which follows Q2, so the two
  offers disagree. The brief line pins no group, which limits the risk. (Also recorded in
  the first review round.)
- [MEDIUM] `src/plumb/hosts/claude_code/stop.py`: `plumb view` writes its vault to
  `.plumb/view/`, but the stop hook's `IGNORED_PREFIXES` does not exclude `.plumb/view/`,
  and `plumb init` (CAPTURE's `commands.GITIGNORE_LINES`) does not add `view/`. In a
  consumer repository `/plumb view` runs through the agent, so that turn's stop hook sees
  every generated note as a changed path (`records_for_paths`, `verify.select`, the
  summary's touched line). Fix: add `.plumb/view/` to `IGNORED_PREFIXES`, and `view/` to
  `GITIGNORE_LINES` at integration.
- [MEDIUM] `tests/integration/test_session_e2e.py` (coordinator-owned): still asserts
  the sp1 summary format. The first line is now the status card, and in compact mode
  "questions: none" is joined into the second line. The Integrate phase's single
  full-suite run fails at lines 173 and 176 unless the coordinator applies the edits noted
  in the first round's [INTEGRATION] entry first.
- [MEDIUM] `src/plumb/align.py`: `collect()` stops at test and code nodes. It never
  expands to evidence (sp5 8 and R12.2: intent -> ... -> test -> code -> evidence) and
  never reports the spec's example gap "an example with no evidence", so /plumb review and
  the vault's edge badges show an unrun chain as complete. (Also recorded in the first
  round.)
- [LOW] `src/plumb/hosts/claude_code/templates/plumb-command.md`: `allowed-tools` omits
  `{plumb} relay`, although its own `confirm` instruction tells the agent to "relay them at
  once", so every `/plumb confirm SR-034` triggers a permission prompt. Separately,
  plumb's own installed `.claude/commands/plumb.md` (coordinator-owned) still advertises
  the old brief, explain and impact set until it is reinstalled at integration.
- [LOW] `src/plumb/present/review.py`: `_glance` lists revoked agent-relayed and auto-jev
  approvals as if they were still in force, and omits the R13 Q4 "self-recorded message"
  label although `present.cards.confirmed_label` exists. The merge-boundary glance itself
  belongs to MERGE. (Also recorded in the first round.)
- [INTEGRATION] HOSTS' `mcp/server.py` can now import `plumb.present.api.resolve`; its
  `_resolve` reads `result.best`, which `Resolution` now provides. `plumb_brief` can call
  `api.brief` directly instead of the `brief` command (same lines either way).
- [LOW, flaky] `tests/host/test_latency.py::test_intent_lines_survive_cpu_contention`
  failed once in this round's focused run (the prompt hook printed only "plumb: check
  skipped (budget)": the watchdog's hard limit hit before the relay line was kept) and
  passed when rerun alone. The machine (2 cores) was also running other lanes' tests on
  top of the test's own CPU contention. If it recurs on an idle machine, keep the relay
  line before `open_core` (it needs only `stated.json` and the record states).
## Next lane HOSTS (2026-10-06)

Lane HOSTS (sp4) built H1 to H6 and HS1, HS2 on `lane/hosts`; nothing is left unbuilt.
Integration notes for the coordinator (there was no phase 0, so the lane wrote the parts of
the phase-0 contract it consumes):

- [INTEGRATE] `src/plumb/contracts.py` gains `TurnEvent` and `TurnOutput` (sp4 3.1) at the
  end of the file; CAPTURE also appends there: keep both sections.
- [INTEGRATE] `src/plumb/hosts/neutral.py` is the phase-0 delegation (PRESENT owns it from
  then on): `handle_event(event, *, deadline, kept, verify, backend, unjudged)` over the
  Claude Code handlers. If PRESENT adds its own `neutral.py`, keep its rendering and keep
  `via(event)`: a `host == "cli"` event (`plumb turn start`) logs its prompt `via: turn`.
- [INTEGRATE] `src/plumb/hosts/claude_code/prompt.py` `log_prompt` writes
  `"via": ctx.extra.get("via") or "hook"`; CAPTURE's branch writes `"via": "hook"` on the same
  line. Take this lane's line: with CAPTURE's, a `plumb turn start` prompt (recorded by the
  agent itself) would be logged as hook-recorded and lose the "self-recorded message" label
  (R13 Q4).
- [INTEGRATE] `src/plumb/hosts/claude_code/cli.py` `_hook` hands `--host`/`--format` to
  `plumb.hosts.cli.hook_main` (four lines); `src/plumb/cli.py` routes `hosts`, `turn`, `mcp`.
- [INTEGRATE] My edits to shared files leave links of other lanes' SRs stale (SR-010, SR-012,
  SR-014, SR-026, SR-027 among them); the lane repinned only SR-053 to SR-057.
- [MEDIUM] (sp4 4.1, R2) Codex feeds a Stop hook's `reason` back to the model; whether it
  also fires `UserPromptSubmit` for that continuation is not documented. If it does, plumb's
  own block text would be logged as an owner prompt `via: hook`. Pi's follow-up and Hermes'
  `pre_verify` never reach the prompt hook. Fix: the stop event records the digest of the
  block it emitted per session, and the prompt event logs a prompt equal to it as
  `via: plumb`, which relay refuses as a quote source. Check with a live Codex session first.
- [MEDIUM] (sp4 4.1) The Codex rows rest on the 0.160 binary's embedded hook schemas and
  strings (`.codex/hooks.json`, `hooks.state.<key>.trusted_hash`), not on a live run: run one
  Codex session in a trusted project to confirm the hooks fire and the JSON output is read.
- [LOW] (sp4 6.4) Hermes keeps MCP servers in the user's `config.yaml`
  (`HERMES_HOME`, `%LOCALAPPDATA%\hermes` on Windows), not in the project: `plumb mcp install
  hermes` writes there, with the project as `cwd`; when the file already has `mcp_servers`
  it prints the entry instead of editing the owner's YAML.
- [LOW] (sp4 6.2) `plumb_impact` resolves plain words through `plumb.present.api.resolve`
  when PRESENT's resolver is in the build (its result's `best` or `ref`); until then the
  reference is passed as given. Align the attribute name when PRESENT lands.
- [LOW] (sp4 6.3) Inside a tool call the MCP server swaps `plumb.verify.testmap.build_map` for
  a non-writing wrapper so the derived `.plumb/test_map.txt` is not refreshed. A
  `write_text=False` option on `open_verify` (VERIFY's file) would make that a parameter.
- [LOW] (sp4 4.3) Hermes' `/plumb` falls back to returning the words for the owner to send
  when `ctx.inject_message` is unavailable (gateway sessions without the injection grant).

## HOSTS lane review (2026-10-06): fixes, integration notes, medium and low findings

Fixed (HIGH, whole class):

- Codex hook commands that neither cmd nor PowerShell could run (`'.venv\Scripts\python.exe'`
  in POSIX single quotes). Guarantee: every command plumb writes into a host's configuration
  for the platform shell runs there as written. Entry points: the three `.codex/hooks.json`
  commands (SessionStart, UserPromptSubmit, Stop); Codex `notify`, the Pi and Hermes spawns
  and the MCP configurations are argv arrays executed without a shell. Choke point:
  `plumb.hosts.common.shell_command` (Windows: backslashed program path, no quoting, refuses a
  token that would need quoting). Test: `tests/hosts/test_codex.py::
  test_hook_commands_run_in_the_platform_shell` runs the rendered command in cmd and
  PowerShell (sh on POSIX).
- R13 Q4 "self-recorded message" existed only as a log tag. Guarantee: every confirmation
  resting on a message the agent recorded itself is labelled. Writer (one choke point):
  `approvals.relay` writes `self_recorded: <cited prompt via == "turn">` into the approval's
  payload (digest-protected). Reader (one choke point): `confirm.is_self_recorded`, surfaced as
  `RecordStatus.self_recorded`. Surfaces: `plumb show`, `plumb explain`, the merge glance
  (text and JSON) and `plumb hosts status` (all three hosts); one test each in
  `tests/hosts/test_self_recorded.py`.
- [INTEGRATE] These fixes touch files of other lanes: `approvals.py` and `confirm.py`
  (CAPTURE, core), `contracts.py` (`RecordStatus.self_recorded`, defaulted, additive),
  `readback.py` and `explain.py` (PRESENT), `merge.py` (MERGE). If CAPTURE rewrites
  `relay`/`find_prompt`, keep the `self_recorded` payload key; if PRESENT moves show/explain,
  keep the label. Re-run `tests/hosts/test_self_recorded.py` after every merge.
- [MEDIUM] (R13 Q4, R2) The label rests on the prompt log's `via`, which the agent can still
  defeat by running `plumb hook prompt --host codex` itself (logged `via: hook`) or editing
  `.plumb/session/prompts.jsonl` (not hash-chained). Within the tamper-evident trust model,
  but the merge glance should also flag a relayed approval whose prompt's `via: hook` arrived
  from a shell carrying the session marker, once a host's hook environment is known to lack it.

Medium and low findings recorded (not fixed in this lane):

- [MEDIUM] (src/plumb/hosts/cli.py, R9) `plumb turn start/end` fall back to the fixed session
  id `cli` when `--session` and `PLUMB_SESSION_ID` are both absent, so every agent session
  shares one state: the session-start brief is shown once for the repository's lifetime and
  seen.json deduplication carries over. A fresh agent starts without the relevant records.
  Fix: derive a session id per agent session (or require `--session` and say which id in the
  instruction block).
- [MEDIUM] (src/plumb/hosts/cli.py) The first `turn start` of a session runs session-start
  and prompt in one process, each with its own 1.9 s watchdog that ends the process with
  `os._exit(0)`. If session-start hits the watchdog, the owner's prompt is never logged and
  turn.json is not written; worst-case latency is about 3.8 s. Fix: one deadline for the pair,
  log the prompt first.
- [MEDIUM] (src/plumb/hosts/cli.py) `turn end` treats the turn as already continuing
  (`stop_active`) only when turn.json has a prompt digest; without a preceding `turn start`
  every `turn end` blocks again (the `not_run` tests reason repeats). Fix: record the block in
  the session state independently of the prompt digest.
- [MEDIUM] (src/plumb/mcp/server.py, sp4 6.2/6.3, plan H6) The MCP tools run CLI commands
  in-process (`cli.main` inside `redirect_stdout`) instead of the frozen `plumb.present.api`
  functions, so the read-only guarantee holds only for today's commands. If PRESENT's
  brief/show/explain write session or judgment state, an MCP read becomes a write. Re-run
  `test_tools_are_read_only_plumb_unchanged` after the PRESENT merge; switch to the API.
- [MEDIUM] (src/plumb/hosts/claude_code/prompt.py, R13 Q4) Cross-lane conflict on the `via`
  line: this lane writes `"via": ctx.extra.get("via") or "hook"`, CAPTURE hard-codes
  `"via": "hook"`, PRESENT rewrote log_prompt. Keeping either other version logs `plumb turn
  start` prompts as hook-recorded and drops the label. Guard: `tests/hosts/test_turn.py::
  test_turn_start_logs_digest_and_prints_delta` and `tests/hosts/test_self_recorded.py` must
  run after that merge.
- [MEDIUM] (src/plumb/hosts/pi/templates/index.ts) The Pi `/plumb` command calls
  `pi.sendUserMessage(...)` without `deliverAs`; Pi throws while the agent is streaming, so
  `/plumb` typed during a running turn fails and the words reach neither the agent nor the
  prompt log. Fix: pass `{ deliverAs: "followUp" }`.
- [MEDIUM] (src/plumb/hosts/codex/install.py, R13 Q4) `hosts status codex` says prompts are
  "recorded by the host's prompt hook" as soon as the entry is in .codex/hooks.json, before the
  owner has trusted the hooks in Codex; until then the CLI fallback (self-recorded) runs. Fix:
  read `hooks.state.<key>.trusted_hash` (or say "installed, trust pending").
- [MEDIUM] (src/plumb/contracts.py, plan 3.1) The lane edited coordinator and PRESENT files
  (contracts.py TurnEvent/TurnOutput, cli.py ROUTES/help, hosts/neutral.py,
  hosts/claude_code/cli.py and prompt.py, the new hosts/common.py) with no phase 0; the
  lane-gate `git diff --name-only main...HEAD` check fails on its 3.1 row. Resolving the
  CAPTURE or PRESENT conflicts the wrong way silently drops `via: turn`.
- [LOW] (src/plumb/mcp/cli.py) `plumb mcp uninstall codex` (and Hermes) rewrite the config
  file even when it holds no plumb block: trailing newlines are trimmed (reported as changed)
  and a whitespace-only file is deleted. Fix: write only when a block was removed.
- [LOW] (src/plumb/hosts/codex/install.py) On Codex both the Stop hook and `notify` run the
  stop event after every turn (notify with stop_active=True): twice the per-turn stop work
  (about 1 to 1.4 s each), and notify can overwrite the stated.json the Stop hook wrote, which
  `plumb relay` checks the owner's quote against. Fix: notify only refreshes the summary and
  never rewrites stated.json, or skip notify when the Stop hook is installed.

## HOSTS lane review, round 2 (2026-10-06): fixes and medium findings

Fixed (HIGH, by class):

- Owner words only (R2): Hermes runs delegated subagents, its background review and cron
  runs in-process, and their turns fire the plugin's hooks with `parent_session_id`. The
  plugin's one gate (`_owner_session`) now skips those sessions in every hook: no prompt is
  logged `via: hook`, and no stop or summary runs for them. Tests:
  `tests/hosts/test_hermes.py::test_child_agent_turns_are_never_the_owner` and the real
  plumb check in `test_real_plumb_through_the_plugin`.
- `shown` only when the owner sees the summary (R1, R2, R13 Q4): the stated set's one writer
  (`hosts/claude_code/stop.py::write_stated`, a PRESENT/CAPTURE-owned file, edited at that
  choke point only) applies the `display` that each entry point passes to
  `hosts.neutral.handle_event`. `owner` is the Claude Code and Codex Stop hooks, Pi
  `agent_end` and `plumb turn end`; the fallback block now tells the agent to put the
  summary in its final reply. `status` is Codex `notify`, which no longer rewrites the stated
  set that `plumb turn end` or the Stop hook wrote. `unseen` is `plumb hook stop --unseen`:
  no record is marked shown. Hermes now shows `owner_lines` by appending them to the reply
  (`transform_llm_output`). When the reply did not carry them (another plugin's transform
  won, the turn was interrupted, or a Hermes without the hook), the plugin reruns the stop
  `--unseen`. Tests: `tests/hosts/test_stated_display.py` (turn end, Codex notify, Codex
  Stop hook, `--unseen`, the fallback block) and
  `tests/hosts/test_hermes.py::test_unshown_summary_reruns_stop_unseen`. This also resolves
  the stated.json part of the earlier LOW item on Codex's double stop run.

Medium:

- [MEDIUM] (src/plumb/hosts/cli.py) When `--prompt-file` is not given, `plumb turn start`
  reads the prompt with `sys.stdin.read()` whenever stdin is not a TTY. If an agent's shell
  tool runs the command with an inherited stdin pipe that never closes, the read waits for
  EOF with no timeout or watchdog: the watchdog starts only inside `run_event`, after the
  read. A host whose shell tool holds an open, non-TTY stdin and an agent that runs `plumb
  turn start --session s1` without piping the message (the AGENTS.md block allows "with the
  owner's message on stdin") block until the host's tool timeout. That breaks the "seconds
  per turn" bar. Fix: read stdin only when data is available, apply the watchdog before the
  read, or require `--prompt-file`/stdin to be explicit.
- [MEDIUM] (src/plumb/hosts/claude_code/prompt.py) The lane edited files owned by other lanes
  (approvals.py, confirm.py, contracts.py, explain.py, readback.py, merge.py,
  hosts/neutral.py, hosts/claude_code/*, cli.py) instead of stopping and asking the
  coordinator, as plan section 2 requires. CAPTURE implements the same Q4 label with
  opposite semantics: its prompt.py hard-codes `via: hook` and its relay and escalation code
  test `via != "hook"`, while HOSTS tests `via == "turn"`. If the coordinator takes CAPTURE's
  `log_prompt` line, `plumb turn start` prompts are logged as hook-recorded, and
  confirmations on the Codex and Pi fallback lose the "self-recorded message" label.
  `tests/hosts/test_self_recorded.py::test_relay_marks_an_approval_resting_on_a_turn_prompt`
  catches this only if it is rerun after the merge. Round 2 adds `stop.write_stated` (the
  `display` gate) to the files to reconcile: keep it, and rerun
  `tests/hosts/test_stated_display.py` after the merge.
- [MEDIUM] (src/plumb/hosts/pi/templates/index.ts) Loop protection on Pi depends on
  `blockedThisTurn`, which `before_agent_start` resets for any prompt not in `injected`. Pi
  documents `before_agent_start` as firing "after user submits prompt". If it also fires for
  the `followUp`/`triggerTurn` custom message with an empty or different `event.prompt`, an
  empty prompt is logged as the owner's (`via: hook`) and the stop block can repeat:
  `agent_end` blocks (tests not run) and sends followUp with triggerTurn, `before_agent_start`
  fires with prompt "", resets `blockedThisTurn` and logs "", the next `agent_end` sends
  `stop_active=false`, and `tests_instruction` (which has no once-guard) blocks again. The
  block also fires on `agent_end`, which Pi says may precede auto-retry or compaction; Pi
  recommends `agent_settled` for this. Unverified against a live Pi.
- [MEDIUM] (src/plumb/hosts/codex/install.py) With trusted hooks, Codex runs the full stop
  event twice per turn: the Stop hook, then notify. Each run repeats git status, verify.select
  and evidence, and covering-test selection on a 2-core machine, so every Codex turn spends
  two stop-handler runs of up to about 1.9 s each. Notify no longer rewrites stated.json
  (round 2), but it still rewrites status.json from a recomputation the owner does not see,
  and a slow notify can race the owner's next prompt. Fix: skip notify's stop work when the
  Stop hook ran for this turn, or make notify refresh only status.json from the last snapshot.
- [MEDIUM] (src/plumb/hosts/hermes/templates/plugin.py) The Hermes plugin keeps
  `_children`, `_summaries` and `_stopped` in module memory for the life of the Hermes
  process. They are never pruned, which is harmless but grows slowly with every delegated
  child session. A child whose `on_session_start` fires before its first `pre_llm_call`
  still runs the session-start event once, which is a read-only brief and logs no prompt.
  Unverified against a live Hermes: whether `pre_verify` and `transform_llm_output` carry the
  child's own `session_id`. The code reads them as Hermes 0.21 does
  (`agent/conversation_loop.py`, `agent/turn_finalizer.py`).

## Integrate phase (2026-10-06): sub-projects 2 to 5 and the importer on main

Merged on main (`work`, then IMPORT, CAPTURE, MERGE, PRESENT, HOSTS, the plan's order); the
lane worktrees are removed and the `lane/*` branches kept. The one full run: 802 tests,
800 passed, 1 skipped (`jev_live`), 1 regression (`tests/verify/test_impact.py`, fixed:
`plumb impact <path>` resolved an exact path to its owning records; a targeted rerun on the
fix passed). `plumb merge-check 9dd86c6 --no-run` on plumb exits 4: 87 records await the
owner, and one untraced deletion (the moved skill template). Integration decisions, then
medium and low findings:

- [DECISION] R13 Q4 "self-recorded message": CAPTURE (`via != "hook"`) and HOSTS
  (`via == "turn"`) disagreed. Kept one rule, fail-closed: `plumb relay` writes
  `self_recorded: true` unless the cited prompt was logged by a host's prompt hook
  (`via: hook`); the prompt hook logs `via` from the host event (`turn` for `plumb turn
  start`). `confirm.is_self_recorded` is the one reader (show, explain, cards, the merge
  glance, hosts status, auto-approval). Prompt-log lines written before `via` existed count
  as self-recorded (a label only).
- [DECISION] The stop hook's one stated-set writer keeps PRESENT's confirm cards and
  triage groups and applies HOSTS' display gate: `unseen` marks nothing shown and pins no
  group; `status` writes nothing.
- [DECISION] Helper and fixture files (`*_helpers.py`, `jev_fixtures.py`,
  `fixtures/intent_prompts.yaml`, `tests/conftest.py`) were `verified_by` ends, so the merge
  boundary waited forever for evidence they cannot have (exit 5). They are `implemented_by`
  ends now; a `support` link kind would say it better (as the lanes noted).
- [DECISION] Two colliding test modules were renamed so the whole suite collects:
  `tests/present/test_confirm.py` -> `test_present_confirm.py`,
  `tests/hosts/test_self_recorded.py` -> `test_hosts_self_recorded.py`. NC-0003 backs the
  claims baseline for them and for lane commits whose trailers named SRs that do not declare
  the path. The range-aware claims fix (a renamed path counts as declared when its
  successor is) is still open.
- [MEDIUM] Phase 0 never ran. Not built: `tests/integration/test_contracts.py` (stubs
  against protocols), `tests/integration/test_mcp_smoke.py` (the MCP server is covered by
  `tests/mcp`), `scripts/bench_hooks.py` (hook timings come from
  `scripts/drive_session.py`); `MergeReport` lives in `plumb.boundary.report`, not in
  `contracts.py`.
- [MEDIUM] (latency) On plumb's own repository the session-start hook takes 1.6 to 2.0 s and
  cuts its tests line ("tests: not checked (budget)"); the stop hook 1.5 to 1.6 s, the
  prompt hook 0.55 to 0.75 s. Within the seconds bar, but session start sits at its budget.
- [LOW, flaky] `tests/host/test_latency.py::test_intent_lines_survive_cpu_contention` and
  `tests/present/test_present_confirm.py::test_relayed_ok_then_confirms_exactly_the_shown`
  each failed once in a focused run on the loaded 2-core machine (other sessions' Python
  processes running) and passed on the same tree when rerun; both passed in the full run.
- [LOW] `plumb import --dry-run` writes the derived `.plumb/cache/config.json` in the target
  (gitignored cache); records, logs and the claims file are untouched, and the source is
  unchanged (git status compared).
- [LOW] The status line after a relay keeps the stop hook's snapshot ("3 awaits you") until
  the next stop recomputes it.
- [LOW] In the driven capture flow, "add a subtract helper next to add" also raises the
  intent-change card for confirmed INT-001 (an extension, trigger 1). Correct by the rule;
  the heuristic's extension recall may be broad for "next to X" phrasing.

## Whole-plumb audit after SP2-SP4 and the importer (2026-10-06)

The audit drove the real CLI, the hooks, merge-check and the MCP server on scratch projects
and on a clone of plumb. Four HIGH findings were fixed in this change, each as a class:

- [FIXED, HIGH] R2 "an objection is not an approval": a relayed "ok" confirmed a record the
  owner had rejected in the same prompt ("SR-001 is ok but DEC-001 is wrong, use floats" ->
  `plumb relay DEC-001 INT-001 SR-001 --quote "SR-001 is ok"` confirmed all three, and the
  prompt hook suggested exactly that command). Guarantee: a relayed confirmation covers only
  the records the owner's words affirm. One choke point, `approvals.owner_scope`, read by
  `plumb relay` (IDs, `--group`, `--set`) and by the prompt hook's relay line: when the
  clause the quote comes from (or the quote) names records, only those are confirmed; a
  record named next to objection or change words anywhere in the prompt is never confirmed;
  a group or set relay is refused when the ok objects to one of its records or names records
  instead. Tests: relay with `--quote`, `--group`, `--set`, the Claude prompt hook's relay
  line and the CLI-fallback `plumb turn start` path. This also fixes the round's MEDIUM "yes
  I know SR-007 is wrong, rewrite it" (an objection after the affirmation).
- [FIXED, HIGH] Decision 5 trigger 1: the intent-change flag was deduplicated per record hash
  for the whole session (sp5 3 "Instructions too"), so a second, different request that
  contradicts or extends the same confirmed record reached the agent with no "ask before
  editing" instruction. The flag line is now `per_turn` at the one emitter; record lines stay
  deduplicated (R9). sp5 3 and concept 6.2 corrected. Tests: the prompt hook, the
  host-neutral turn API and `plumb turn start`. This supersedes the round-2 MEDIUM on the
  same dedup (toy sessions s3/s4).
- [FIXED, HIGH] R13 Q2 / R1 "say ok to confirm": `find_prompt` kept the FIRST prompt-log
  entry of a digest, so the second "ok" ever sent in a repository resolved to an old prompt
  whose time precedes the current stated set, and every later relayed "ok" (IDs, `--group`,
  `--set`) was refused. `find_prompt` now returns the latest entry of the digest (the log is
  append-only). Tests: relay IDs, `--group low-risk` and `--set INT` after an earlier
  identical "ok". Supersedes the host-review MEDIUM above (find_prompt `setdefault`).
- [FIXED, HIGH] concept.md and sp2 contradicted R13 (the triage offer "names every record of
  the group by ID"; R13 absent from the reference). Concept: R13 in the preamble, D18 in the
  decision table with the owner's answers, 4.6 triage paragraph (top 5 titles + "+N more",
  the ok approves exactly the pinned hashes), Q3 in 4.6 auto-approval, Q4 in 4.6 and 9, Q1
  in 8 (calibration) and the offer line in 8. sp2 C5, 8.1 offer example, 8.2 (Q3) and 8.3
  (Q1 split); sp4 3.2 (Q4).

Recorded, not fixed (owner rule: HIGH only):

- [MEDIUM] (R13 Q4, R2) `self_recorded` rests on `via: hook` read from the gitignored
  `.plumb/session/prompts.jsonl`, a plain file the agent's Edit/Write tools are not denied:
  appending `{"text": "ok SR-001", "via": "hook"}` and relaying it gives "confirmed by you
  (relayed)" with `self_recorded: false`. Within the stated trust model (a determined agent
  can forge a digest), but the Q4 label is lost with a one-line edit. Fix: deny
  Edit/Write/MultiEdit (and the Bash string match) on `.plumb/session/prompts.jsonl` in the
  hooks install set; have the prompt hook write a session-scoped HMAC or hook-only nonce per
  line and relay verify it before trusting `via: hook`, else label `self_recorded`.
- [MEDIUM] (R3) File-level `verified_by` links attribute a file's failures to every
  requirement verified by it: breaking `add` and adding a red `test_sub` to
  `tests/test_mod.py` showed "Regression SR-002 (mul)" while `test_mul` passed, and marked
  SR-001 and SR-002 "acceptance test changed since you confirmed it". Fix: attribute evidence
  per test node (marker or example) even for a whole-file end; pin acceptance-test changes to
  the AST segment of the requirement's own test nodes; teach node-level links in the README
  Quickstart.
- [MEDIUM] (latency, decision 5) On plumb's own repository (69 SR, 117 proposed, 726 KB test
  map) SessionStart took 2.06-2.32 s (watchdog 1.9 s hit, "check skipped (budget): tests")
  and Stop 1.97-2.09 s ("check skipped (budget): confirmations"; once "regressions not
  checked (budget)"); the README's 0.55-1.2 s come from the toy project. Fix: profile both
  paths on plumb, cache the record index, status and test-map parse across hooks (keyed by
  HEAD and mtimes), never drop the regression check first (it is intent-level), add the
  dogfood repository to drive_session's timing assertions, update the README timings.
- [MEDIUM] (R8 A, R13 Q2) The heuristic triage rates every one of plumb's 117 proposed
  records "riskier" (INT-004..INT-010 and INT-005, whose quote is the owner's verbatim
  "A / B", score 0.00); a fresh near-verbatim capture scored 0.40/0.36; reasons say "not in
  the owner's words: power" when the prompt said "power". It compares against the captured
  quotes only, penalises structural tokens (given, call, return, app, calc), and the 0.8
  `triage.low_risk_min` suits no paraphrase. So the grouped one-line offer never appears
  without JEV. Fix: score against the full logged prompt of the record's capture digest plus
  its quote, will/won't and examples, with stemming, synonyms and numbers; drop
  given/when/then and code-path boilerplate; calibrate a heuristic-specific threshold on the
  dogfood records; say "unrated" rather than "riskier" when the heuristic cannot
  discriminate; add a test where a verbatim capture lands in low_risk and the brief prints
  the offer.
- [MEDIUM] (design weight) About 23.5k lines in `src/`, about 45 subcommands in `plumb
  --help`, and this file at 248 KB with 468 entries (244 MEDIUM). The owner-facing surface
  is small, but the engine and agent surface approach the weight the owner wanted to leave
  behind. Fix before SP6: a consolidation pass (merge new/intent/example/decide into capture;
  status --card/review/brief), cap the agent-facing commands the skill lists, and triage
  this file into a short ranked list, archiving the rest.
- [MEDIUM] (R9 card) Stop-summary intent cards show "○ not run" for tests that ran this turn
  (two regressions `test_mul_ex1/ex2`; a not-yet-passing `test_div`); only the separate
  regression line is right. Fix: read the node's latest evidence from the turn's run (the
  regression line's source) when rendering card test states.
- [MEDIUM] (decision 5) A heuristic false positive ("Also add power ..." flagged INT-001 on
  "also") renders a full "▸ Intent change INT-001" card in the owner's summary although the
  request only added intent. Fix: show the card only when the turn confirmed a change (a
  read-back or decision recorded against the flagged record); otherwise log the flag.
- [MEDIUM] (R1) `plumb review` section 1 says "awaits you: nothing" while its section 5 and
  `plumb merge-check main` say SR-001 (extended by `verified_by` links added after
  confirmation) awaits confirmation. Fix: feed the merge boundary's extended/widened set
  into review's "awaits you".
- [MEDIUM] (quality bar, full suite at the merge boundary) `plumb merge-check master` printed
  "full run: not needed (latest full run ... holds)" and exited 0 after a new untested
  `mul()` landed under confirmed SR-001 via an agent-run repin; the full run was on an older
  tree. Fix: run the one full suite whenever the tree differs from the latest full run's
  tree identity; treat a repinned `implemented_by` link of a confirmed requirement as
  needing the owner's confirmation at the merge.
- [MEDIUM] (R12.3) With the heuristic the commit-msg hook says nothing about "does this diff
  serve its claimed SRs?": a commit adding untraced `src/plumb/statusline.py` claiming SR-002
  passed with no warning and no "no judgments available". `diff_serves` warns only on a
  high-confidence "no". Fix: print "plumb: does this diff serve SR-002? no judgments
  available", or a degraded warning (the claimed SR declares none of the staged paths);
  non-blocking; a test at the commit-msg entry point.
- [LOW] README Quickstart step 3 says "This build has no `plumb new` command, so create the
  file yourself", but `plumb new requirement --title ... --statement ...` exists. Fix: use
  `plumb new` and `plumb example` there.
- [LOW] After a relay the status line still reads "3 awaits you · 1 question" until the next
  hook. Fix: rewrite `status.json` at the end of relay, approve, revoke and triage --approve.
- [LOW] (R9 status card) The card showed "plumb ✓ aligned · SR 3/3 ok" while confirmed SR-003
  had no implementation and two uncovered examples. Fix: never "aligned" while a confirmed
  requirement has uncovered examples or no fresh passing evidence ("confirmed, unbuilt").
- [LOW] (decision 5) Intent-change heuristic precision: "now make add faster" flagged INT-002
  (the subtract intent); on plumb, "Add a subtract helper" pulled in five unrelated records
  (SR-038, SR-030, FEAT-003, ...) and "Add a subtract helper next to add" flagged SR-001 and
  suggested escalating. Fix: require a subject-term match against the record's statement or
  examples before flagging; do not read a sibling behaviour as a change; log precision on
  the dogfood session.
- [LOW] (R9) `plumb why "the subtract thing"` found exactly one candidate (INT-002) and still
  asked "which one do you mean?". Fix: answer directly for a single candidate above the
  threshold.
- [LOW] `plumb turn start --help` ran a turn start and the session brief (writing session
  state) instead of printing help. Fix: parse with argparse before acting.
- [LOW] A later turn's summary repeats "confirmed DEC-001, INT-001, SR-001 on your prompt
  ..." from an earlier turn, and test links added after confirmation in the same turn force
  a re-confirmation at merge ("extended"). Fix: emit the confirmation line once, in its
  turn; consider exempting `verified_by` links added before the merge range was confirmed.
- [LOW] (R9) In a repository whose default branch is not `main`, `plumb review` prints
  "merge state against main: exit 2 (0 awaiting you, 0 untraced)" while two records await
  the owner; `plumb merge-check` prints "fidelity: every touched requirement judged" for an
  SR with no linked ends. Fix: report a usage error or missing base plainly; say "no linked
  ends to judge".
- [LOW] `plumb triage` is a read view but appends a committed `triage` event listing every
  proposed record (117 hashes on plumb) whenever the view changes; the main checkout carries
  such an uncommitted `events.jsonl` line now. Fix: keep the snapshot in gitignored cache or
  session state; log a committed event only when the owner acts (triage --approve or a group
  relay).
- [LOW] (R10) Next: SP6 parallel work. Not started, and no SP6 spec yet. Its state: IDs are
  allocated without `refs/plumb/ids` (no compare-and-swap reservation, no `plumb
  merge-fix`); `events.jsonl` and `evidence.jsonl` are still single streams (`plumb init`
  still creates them; the one-file-per-entry layout of concept 4.7 and its chain-keeping
  migration are pending); no frontmatter-aware merge driver or intent-conflict card; no
  cross-worktree awareness in the brief and status line; `plumb check --merge` on the merge
  result is not a hook yet. Everything else of SP2-SP5 was found as specced or explicitly
  deferred: CLI, hooks (session start 1.8 s, prompt 0.75 s, stop 1.6 s, status line 0.3 s
  on the toy), the guard (exit 3 without a TTY or under the marker), the commit-msg hook,
  merge-check (exit 4/5/1, one full run), the MCP server (6 read-only tools), the host
  adapters, the importer (idempotent, all proposed) and plumb-clarify with its e2e test.

## Whole-plumb audit, round 2 (2026-10-06): HIGH findings fixed, the rest recorded

The audit drove the real CLI, the hooks, merge-check and the MCP server on scratch projects
and on fresh clones of plumb. Four HIGH findings were fixed in this change, each as a class:

- [FIXED, HIGH] R2 / R9 / concept 4.6 check 3, "an objection is not an approval": objections
  counted only when the owner named a record by its ID. "No, the pow example is wrong, it
  should return 9. Ok, carry on with the tests" let `plumb relay INT-005 SR-005 --quote "Ok,
  carry on with the tests"` confirm the pow records, and the prompt hook suggested exactly
  that relay; "ok but div should return a float" and "Looks good except the pow example: it
  should be 2 and 4 giving 16. ok go ahead" were relayed the same way. Guarantee: a relayed
  confirmation never covers a record the same prompt objects to or asks to change, however
  the owner names it. One choke point, `approvals.owner_scope`, now resolves plain words
  against the record index: a record counts as named when an objection clause holds its ID
  or a distinctive word of its title, statement, examples or quote (generic words such as
  "function", "return", "example" never name one); an objection that refers to "the example"
  in general objects to every record; "should", "must", "rather", "replace", "rename" join
  the objection words. `plumb relay` (IDs, `--group`, `--set`) and the prompt hook's relay
  line (Claude Code and `plumb turn start`) read it. Tests:
  `tests/capture/test_plain_objection.py`, one per entry point. SR-005 EX-9 (proposed).
- [FIXED, HIGH] R8 A / R13 Q1: the low-risk group admitted records that contradict the
  owner's words, or rest on invented ones, under "rated faithful to your words" (a will
  "change add" against "Do not change add", an example returning 2 against "returns -2", a
  quote captured without `--prompt` that the owner never wrote). Guarantee: a record enters
  the low-risk group only if its premise is the owner's verified words and nothing in it
  contradicts them. One choke point, the low-risk admission in `triage.triage()`: (a) every
  quote must be verbatim in a prompt the host's prompt hook logged (`via: hook`; an INT's
  `prompt` digest, a requirement's intents, each example quote in one of those prompts or
  its own `prompt`), else the record is shown individually as "quote not verified"; (b)
  `textjudge.contradiction` finds a changed number (sign included), a will/read-back/result
  holding everything the owner's words negate, or a won't/negated result whose words the
  owner states positively, and the record is shown as "contradicts your words". `capture`
  with `--prompt` now checks example quotes too and pins them (`prompt` on the example);
  `capture`, `intent`, `new intent` and `example --quote` without `--prompt` say "quote not
  checked", and `plumb explain` and the vault call such a quote "quoted, not checked against
  your logged prompt", never "your words". Tests: `tests/capture/test_triage_admission.py`
  (capture with no prompt, intent, example --quote, a flipped will/won't, a changed number,
  and every calibration variation). SR-040 EX-5, EX-6 (proposed). The earlier MEDIUM on the
  unchecked capture quote is superseded.
- [FIXED, HIGH] Decision 5 / concept 6.2 trigger 1: a heuristic-only flag became an owner
  "Intent change" card (an unrelated "add a negate function returning minus a" flagged as
  extending a confirmed "add a sub function" because both start with "add a"; also with
  `card off`). Guarantee: the agent, the cascade's LLM tier, gates the card. The prompt hook
  keeps the flag as an agent instruction and records its judgment (`flags` in `turn.json`);
  `stop.concluded_flags` shows the card only when the agent edited the flagged record or
  wrote or edited a record linking to it (supersedes, corrects, relates to, derives from,
  decides), or a backend other than the heuristic rated it `accept`. The heuristic no longer
  reads a leading "add a/create a ..." or generic words (function, returning, number) as a
  subject in common, a new thing ("add a", "another", "new") extends a record only when the
  request attaches it to that record ("... to sub"), and "make sub faster" is a quality, not
  a contradiction (the result's first word was compared with its leading space). Tests:
  `tests/hosts/test_turn_gates.py` over the Claude Code hooks, `plumb turn end` and the
  Codex, Pi and Hermes adapters; `tests/present/test_intent_card.py` (the card appears once
  the agent updates the record). SR-062 EX-5 (proposed).
- [FIXED, HIGH] R5 / R3 / decision 6: on a fresh checkout (`.plumb/cache/` is gitignored)
  the stop hook built the test map inline (about 5 s on plumb), hit the 1.9 s watchdog every
  turn and printed only "check skipped (budget): covering tests ... regressions not checked".
  Guarantee: every turn with code changes selects covering tests or falls back to R5's
  bounded sample plus `full verification pending`, and the regression check is never the
  step that gets dropped. One choke point, `VerifyAPI.select` in hook mode (`open_verify(core,
  hook=True)` from the hook providers, and every VerifyAPI opened while `run_hook` runs): a
  map with more than `HOOK_PARSE_MAX` files to parse raises `MapUnavailable`, a detached
  `plumb map` builds it outside the hook (`spawn_map_build`, once per 5 minutes), and the
  turn gets `unknown_selection` (changed tests plus the nearest tests, at most
  `verify.sample_size`) with `full_pending` "coverage unknown"; `evidence`, `tests_for` and
  `full_pending` degrade the same way, and the derived cache now keys on the map file. The
  stop hook reads the regressions this turn's runs recorded (`recorded_regressions`, from
  the evidence index alone) before any budgeted step, and asks the agent for the turn's
  covering tests when the budget cut the selection. Measured on a fresh clone of plumb:
  stop 1.75 to 1.84 s with "covering tests 10 ... full verification pending (coverage
  unknown ...)", then the map landed in the background and the next turn selected
  covering tests. Tests: `tests/hosts/test_turn_gates.py` (no map, every entry point: the
  sample's tests instruction, the pending flag, the regression question, the background
  build). SR-017 EX-5 (proposed).

Residual of the R5 fix, recorded (not fixed):

- [MEDIUM] (quality bar "seconds, not minutes"; R5) On plumb, the stop hook still spends 1.0
  to 1.7 s in `core.status()` hashing the 721 link ends (no hash cache across processes).
  With a cold OS file cache (the first turns on a fresh clone) the watchdog fired before the
  early summary, so that turn printed only "check skipped (budget)". The session-start tests
  line is cut on plumb every time ("tests: not checked (budget)") because its derived cache
  is never written before the watchdog. Fix: cache link-end hashes by file fingerprint in
  `.plumb/cache/` (as the test map does), and write the derived brief_tests value as soon as
  it is computed.

Recorded, not fixed (owner rule: HIGH only):

- [MEDIUM] (R8 A, R12) With the default heuristic the low-risk group is empty in practice,
  so the one-line grouped confirmation the owner chose never appears without JEV. On plumb,
  `plumb triage` lists all 117 proposed records individually (INT-004..INT-010 score 0.00).
  In a toy project, examples quoting the owner's logged prompt word for word ("2 times 3 is
  6") still scored 0.17 (SR) and 0.33 (INT), under the 0.8 threshold; with `low_risk_min:
  0.1` the group, the brief hint and `--approve low-risk` all worked. Fix: score against the
  whole logged prompt as well as the quote fragment; treat given/when/then restatements of a
  verbatim-quoted example as entailed; pick the heuristic threshold from a fixture of real
  captures. Tests at the triage entry point and the brief/summary offer line.
- [MEDIUM] (R9 context economy) The MCP tool `plumb_brief` with no arguments returns the long
  brief (all features, the 21 proposed INT records one per line with quotes), although its
  description promises a few lines; the session-start hook gives the compact brief. Fix:
  return the compact brief without `full`, keep the long form behind `full=true`; test the
  MCP tools/call entry point.
- [MEDIUM] (quality bar; decision 5) Owner views are slow and long on plumb (69 SR, 721
  links): `plumb status` 12.5 s cold and 3.4 s warm; `plumb review` (behind `/plumb review`)
  11.5 s and 140 lines, 117 of them one per proposed record. The hooks stay near 2 s. Fix:
  let status and review read the derived status the hooks compute; group what awaits the
  owner in review (the triage group, then riskier records, capped with "+N more").
- [LOW] (R11, dogfood) `scripts/drive_session.py --capture` on a scratch clone of plumb exits
  2 ("implemented_by src/pkg/mod.py does not exist": CAPTURE_DOC hard-codes the example
  project's path), then crashes with UnicodeEncodeError on "●" under cp1252. Fix: derive the
  path from the target root or create the file on the scratch copy; reconfigure stdout to
  UTF-8 as the hooks do.
- [LOW] (R2 trust model) The installed deny rules protect `.plumb/log/**` but not
  `.plumb/session/prompts.jsonl`, where relay reads the prompt and its `via: hook` label
  (which also gates auto-jev eligibility and, now, triage's verified premise). Fix: add
  Edit/Write/MultiEdit(.plumb/session/**) to the deny rules, or have the prompt hook also
  write a digest where the deny rules reach; state the residual risk in the README trust
  paragraph. (Same class as the round-1 MEDIUM above.)
- [LOW] (R9 status card) `plumb triage` and `plumb review` print "riskier 0.33" where the
  number is the faithfulness score (higher is better); "riskier 0.00" reads as safe. Fix:
  print "faithfulness 0.33 (below 0.80)" or "riskier: little support in your words".
- [LOW] (R1) `merge-check main --no-run` on a clone with one change touching SR-002 and
  SR-058 printed "merge waits for your confirmation" but exited 1 because a stale link was
  also present; the README says such a merge exits 4. Fix: document the precedence, or exit
  4 while confirmation is pending and list the stale links; test the merge-check entry point.
- [LOW] (decision 5) With a session id that has no SessionStart or prompt record, post-edit
  drops the edit and both Stop calls print nothing (no covering-test request, no summary)
  although a test file changed. Fix: create the session state lazily in post-edit and stop,
  or log "no session state; summary skipped" and print one summary line.
- [MEDIUM] (decision 5, R9) Paraphrased contradictions are missed: after SR-001 (sub) was
  confirmed, "make the subtraction reject decimal numbers" injected no record line and no
  compare instruction; only "Actually sub should raise an error on floats instead", sharing
  terms with the record, was flagged (partly recorded above). Fix: when no record matches by
  terms, fall back to the `plumb explain` resolver (or the judgment backend) so plain-language
  requests still bring in their confirmed records and the compare instruction.
- [MEDIUM] (R1, concept 6.6 trigger 2) A request contradicting a proposed record the work
  relies on is never flagged: "mul should no longer multiply a and b, instead it should
  return a to the power b" against proposed SR-003 produced only the record lines. Fix: emit
  the per-turn change instruction for proposed records the turn's work relies on (the stated
  set, for example), phrased as trigger 2.
- [MEDIUM] (R11) The stop hook asks "I assumed A; B also fits. Which one?" while the card
  printed with it says "(proposed — say "ok" to confirm)", so a bare "ok" answering "Which
  one?" confirms option A without choosing; the same summary listed two decision questions
  ("questions: DEC-001; DEC-002"). Fix: for a decision that matters, prompt for a choice
  ("say A or B") and have relay require the chosen option's words, or the ID with "ok"; cap
  the summary at one decision question per message.
- [MEDIUM] (R1) DEC-002 (matters: true, proposed, created on the branch) was missing from
  "merge waits for your confirmation" (only SR and INT records were listed), and merge-check
  exited 1 because claim findings took precedence over the documented 4 and 5. Fix: list
  unconfirmed decisions that matter linked to touched records at the boundary; report the
  most specific exit code (4 or 5) even with claim findings.
- [LOW] (R13 Q1) DEC-018 adds a condition the owner did not state: "and accept at least half
  of the owner's confirmed records". Fix: mark it as an agent assumption in the record (it
  stays proposed), or drop it.
- [LOW] (concept 4.6) The prompt digest lives in the gitignored `session/prompts.jsonl` and
  reaches the committed events log only when a relay cites it, so the committed log does not
  hold every owner prompt as the concept says. Fix: append the digest at prompt time, or
  correct concept 4.6 to describe the lazy logging.
- [MEDIUM] (R5) On a loaded 2-core machine, 2 of 4 edit turns on a scratch clone of plumb ran
  the stop hook into the 1.9 s watchdog and ended with "check skipped (budget): covering
  tests ... regressions not checked (budget)", no covering-test request and no pending flag
  (`validate --merge` did report "full run: needed"); session start cut "tests" every time.
  Fix: always emit the cheap "run plumb tests run --paths <changed>" block when the turn
  changed code, or set a pending flag the status line shows. (The HIGH R5 fix above now does
  both when the selection step itself is cut; a watchdog cut before the early summary is the
  residual MEDIUM above.)
- [MEDIUM] (R1, README "Your 'ok' ... confirms only what was shown") The stop hook's message
  showed four cards each saying "(proposed — say "ok" to confirm)" (DEC-001, INT-001, SR-002,
  SR-001); after the owner's "ok", `plumb relay SR-001 --quote ok` was refused ("SR-001 is
  not in the stated set of the reply"). It fails safe but invites an "ok" that cannot
  confirm, and a fourth record got a full card although the README says records past the
  three-record cap are named. Fix: render "say ok to confirm" only for records written into
  the stated set; mark the others "name it to confirm".
- [MEDIUM] (R9) `plumb explain sub` finds SR-002, but "subtract", "subtraction" and "the
  subtraction thing" return "nothing in plumb's records matches", from the CLI and the MCP
  `plumb_explain` tool; MCP `plumb_impact` on `src/app/calc.py` returns "plumb impact SR-001
  / records: none" while the CLI says "records: SR-001". Fix: stemming or prefix matching in
  the resolver; the same path resolution in the MCP impact tool as in the CLI.
- [LOW] (decision 5, R12) The affirmation "ok, SR-002 is right and also approve INT-001" (via
  `plumb turn start`) produced "this may change SR-002 (confirmed)" and "consider escalating
  to an up-front spec"; `plumb turn start --help` runs a turn instead of printing help; the
  commit-msg ownership warning ("does this diff serve its claimed SRs?") prints nothing with
  the heuristic backend, where R12 asks for a degraded form or "no judgments available".
  Fix: exclude affirmation prompts from intent-change and escalation hints; handle --help in
  turn_main; print "no judgments available" under the heuristic.
- [MEDIUM] (R9) `plumb explain the relay check` named SR-047 (merge-check) as the best match,
  not SR-005 or DEC-003 ("Relayed approvals use plumb relay"), which define the relay check.
  Fix: rank records whose title or statement holds the query's content terms above records
  that only mention them in passing.
- [MEDIUM] (decision 5, R9) On a fresh clone the first SessionStart hit the watchdog and
  printed only "plumb: check skipped (budget)", with no brief or pointer; the status line
  read "plumb | no status yet" until a later Stop wrote status.json. Fix: print the
  record-only brief before any cache-building step, so the R9 brief always appears on a
  cold start. (Observed again in this round: the first stop and session start on a clone
  with a cold file cache; see the residual MEDIUM above.)
- [LOW] (exit codes) `plumb merge-check --no-run HEAD~3` with 48+ unconfirmed touched
  requirements exited 5 (verification), not 4: the owner's confirmation, the primary hold,
  hides behind the code for a full run that `--no-run` does not perform. Fix: let 4 take
  precedence when touched records await the owner, or document the precedence.
- [LOW] (quality bar) `plumb view` took 31 s on plumb's records (602 notes). It is on demand,
  not per turn. Fix: rewrite only the notes whose source hash changed.

## Whole-plumb audit, round 3 (2026-10-06): medium and low findings

The round's HIGH findings are fixed in the same commit, each as a class at one choke point:
a self-recorded message never grounds a relay where the prompt hook runs
(`approvals.owner_prompt`; deny rules for `plumb turn start` and `plumb hook prompt`); an
"ok" beside a correction the agent cannot place confirms nothing, a quote beside any
objection is the owner's whole statement, and the glance prints the whole message
(`approvals.owner_scope`); every CLI verb prints UTF-8 through a cp1252 pipe
(`plumb.cli.utf8_output`); `plumb turn start` logs the prompt before the brief, so the
watchdog never drops it; every untraced-change instruction names the proposed owner
(`plumb.trace.trace_instruction`) and `plumb review` reads uncommitted changes. Recorded
here without fixing:

- [MEDIUM] (decision 5, R3, concept 7.5) `verified_by` links pin the whole test file: an
  unrelated, passing `test_mul` appended to the shared `tests/test_calc.py` turned the
  owner-confirmed SR-001 (sub) and SR-002 (add) into unconfirmed edits ("SR 0/2 ok"),
  merge-check exit 4 asked to re-confirm them and `plumb review` said "SR-001 changed since
  you confirmed it" though the record did not change. In a regression turn where only add
  broke, the card also showed "Regression SR-001 'sub returns the difference' ... regression"
  while test_sub passed, and counted "2 questions" for one regression. Fix: pin and
  attribute acceptance tests at node level (hash the test function a `verified_by` link
  names); make capture and link default to node ids (drift already proposes them); keep
  whole-file pins as a fallback that does not de-confirm the record on additions.
- [MEDIUM] (decision 5 / R1, concept 6.6 "asked once per hash") `turn['asked']` is per
  session: three sessions each making a one-line comment tweak to `src/plumb/claims.py` asked
  the same unconfirmed DEC-002 question again; with 19 unconfirmed decisions that matter in
  the dogfood repository, routine edits keep re-raising questions. The question text is also
  malformed ("I assumed ... check.; A PreToolUse hook ... also fits. Which one?"). Fix:
  persist asked-decision hashes per repository (a cache keyed by the DEC hash), and fix the
  phrasing join.
- [MEDIUM] (decision 6, quality bar) On plumb's own repository the session-start hook hits
  the 1.9 s watchdog ("tests: not checked (budget)", "check skipped (budget)") and the stop
  hook sometimes skips the covering-test request ("regressions not checked (budget)", no
  block); a claims.py change defers 110 of 111 covering tests. The hooks degrade honestly,
  but on the dogfood repository the loop's verification is often not exercised per turn.
  Fix: precompute the per-turn data (status snapshot, test selection) asynchronously in
  post-edit so the stop hook only reads a cache; track hook-skip rates in `plumb status`.
- [MEDIUM] (R9 plain-language arguments) `plumb explain "how subtraction works"` and
  `plumb align "subtraction"` say "nothing in plumb's records matches" for SR-001 "sub
  returns the difference": resolution matches literal terms only, and the /plumb command
  relies on the agent to rephrase. Fix: a stemming and synonym pass, a backend Choice over
  the top candidates when term overlap is zero, and a /plumb instruction to retry with
  record titles before reporting no match.
- [LOW] (R8 A, quality bar) In the dogfood repository all 117 proposed records fall into
  "individually": their quotes come from the pre-plumb brainstorm, so no hook-logged prompt
  holds them and the grouped one-line confirmation never applies to the backlog.
  docs/followups.md has grown to about 276 KB and 2.9k lines. In a repository whose default
  branch is not `main`, `plumb review` shows "merge state against main: exit 2". Fix: a
  one-time bootstrap path (`plumb triage --source brief`, checking quotes against an
  owner-provided transcript file); summarise and archive closed followups; default the merge
  base to the repository's HEAD branch.
- [MEDIUM] (decision 5 trigger 1) "make multiply handle decimal numbers like 2.5", which
  contradicts the confirmed DEC-001 "integers only" and SR-001, got no flag and no record
  lines: the records were already injected (deduplicated), "make ... handle" is not change
  language and "multiply" does not overlap "mul". "rename mul, pow and sub ..." flagged only
  INT-001 and missed the sub records. A recall gap in a heuristic (MEDIUM under R7). Fix:
  when a prompt matches confirmed records by a stem or synonym, or names a value outside a
  confirmed decision's chosen option, emit the "this may change" instruction even for
  records already injected; add the decision's chosen and alternative terms to the match
  set.
- [MEDIUM] (R9 card format "Tests ... passing") The card's Tests line printed
  "tests/test_calc.py::test_mul (not run)" right after `plumb tests run --full` recorded 2
  passes, and "not run" in the Regression card right after the same test was recorded as a
  regression, while the summary beside it said "1 fresh pass" or "1 regression". Fix: the
  card reads the same evidence lookup as the covering-tests line (node id plus test-source
  hash); a card test with recorded pass and fail evidence.
- [MEDIUM] (decision 2 drift signals, quality bar) `plumb capture` pins `implemented_by` to
  the code as it is before the change, so the first implementation edit always makes the
  link stale ("SR-001#1 -> src/app/calc.py (target moved)") and merge-check holds on stale
  links the agent routinely clears with `plumb repin`; staleness every normal turn produces
  trains both agent and owner to ignore it. Fix: treat an `implemented_by` link whose code
  end changed in the turn or range that created it as "pending first pin", repinned
  automatically when its covering tests pass; keep staleness for changes after a pinned,
  verified state.
- [LOW] (R3) A never-passed test shows as "plumb failing ... 1 failing" (red state) in the
  status card next to "not yet passing": it does not interrupt, but the red state suggests a
  problem during test-first work; a single regression is also counted as "2 questions"
  (file and node). Fix: "not yet passing" wording and a neutral glyph for tests that never
  passed; deduplicate a regression's file and node entries.
- [MEDIUM] (R8 commands "owner-terminal only") `plumb config show` with stdin from
  /dev/null printed the full auto-approve state with exit 0 in a non-interactive shell,
  unlike `config auto-approve on`, which refuses. Claude Code's deny rules block it; on other
  hosts nothing does. Read-only, so no harm. Fix: route `config show` through the
  owner-terminal guard, or record (with a DEC) that the read-only view is deliberately open
  to agents.
- [LOW] (R3, decision 5) For a single regressed test (`tests/core/test_zz.py::test_a`) the
  stop-hook block repeated the regression at file level and at node level. The behaviour is
  right (it blocks on a previously passing test; a new red test does not interrupt). Fix:
  deduplicate regression lines per node in the stop summary.
- [LOW] (R9) `plumb turn start --help` runs a real turn and prints the session brief instead
  of the help text; when a merge both waits for confirmation and has stale links or a claims
  finding, `merge-check --no-run` exits 1 (integrity) rather than 4. The owner-facing text is
  right in both cases. Fix: handle --help after the subcommand; document or adjust the exit
  code precedence.
- [MEDIUM] (R12 degraded form, R12.3) A new untraced `src/app/other.py` committed with "SR:
  SR-001": `plumb trailers check-msg` and the commit-msg hook printed nothing and exited 0,
  neither a degraded warning nor "no judgments available" (`capture.ownership.diff_serves`:
  "the heuristic answers nothing"; `claims.py` 187-196). Already recorded (round 1 MEDIUM,
  round 2 LOW) and still open. Fix: under the heuristic, print a degraded warning (the
  claimed SR declares none of the staged paths) or "no judgments available"; keep it
  non-blocking and test it at the commit-msg entry point.
- [MEDIUM] (R12.4) Changing one number in docs/concept.md ("under 2 seconds" to "under 3
  seconds") made `plumb drift` propose SR-005, SR-040, SR-063, SR-064 and SR-032 "by shared
  terms: adapter, affirm, affirmation / add, affirm, agent / ...": terms of the whole
  document, not of the changed text, where sp2 10.2 says "its changed terms". Fix: compute
  the overlap from the diff hunks' terms only (for a record, from its changed fields); a test
  where a one-line numeric change yields no unrelated hints.
- [MEDIUM] (quality bar, R9 session state) The read-only view `plumb triage` appended a
  committed `triage` event to `.plumb/log/events.jsonl`, leaving the tree dirty; agents
  running it leave uncommitted log lines in every worktree, against SP6's no-conflicting-logs
  goal. Already recorded as LOW and reproduced again. Fix: keep the triage snapshot in
  gitignored cache or session state; log a committed event only when the owner acts
  (`triage --approve`, or a group relay).
- [LOW] (quality bar "seconds, not minutes") On a clone of plumb: session-start 1.8-2.3 s,
  prompt 1.0-1.3 s, stop 1.9-2.2 s, status line 0.35 s. The first cold SessionStart printed
  only "plumb: check skipped (budget)" with no brief; later runs cut "tests: not checked
  (budget)" and the stop hook cut "covering tests, confirmations". The README still says
  0.55-1.2 s and "never the intent lines". Matches round-2 MEDIUMs; within the owner's
  "seconds". Fix (as recorded): cache link-end hashes across processes, emit the record-only
  brief before any cache-building step, update the README timings to the dogfood numbers.
- [LOW] (this round's fixes, trade-offs) The unplaced-objection rule (R2) also refuses
  "Not that one. ok for SR-001" and "ok for SR-001, but do not touch the docs" unless the
  objection names a record by ID or a word of it: a false refusal leaves the record proposed
  (non-blocking under R1), which the owner's ruling prefers over confirming a record the
  owner corrected. On Codex, a self-recorded message is refused only once the Codex prompt
  hook has logged a prompt (no repository file says whether the owner trusted the hooks);
  the prompt log now records the logging host for that reason.

## Whole-plumb audit, round 4 (2026-10-06, commit 32c3db8): medium and low findings

Two HIGH findings were fixed as one class in this round (R2, decision 2): an "ok" beside a
correction written in plain words, with no objection word and no but/though/except opening
("ok, please also accept floats", "ok. Actually multiply by 0 gives 1 for us", "ok, and make
cube accept floats too"), confirmed every record shown, including the decision and the
example it contradicted. `approvals.change_clauses` is now the one change-clause reader
behind `owner_scope`, the relay's whole-statement quote, `prompt_objects`, the prompt hook's
relay line (and so `plumb turn start`) and the merge-boundary glance (concept 4.6, SR-005
EX-12, `tests/capture/test_plain_change.py`). The findings below were recorded, not fixed.

- [MEDIUM] (R13 Q2) After the stop hook's low-risk offer line ("approve the 8 records rated
  faithful to your words: ... +3 more (see plumb triage)? say \"ok\"") and the owner's "ok",
  the prompt hook's relay line (`hosts/claude_code/prompt.py` `awaiting_line`) never
  mentions the group: it suggests relaying only the records shown in full and says the others
  "were not shown in full: relay them only if the owner's words name them", against the skill
  (`--group low-risk`) and R13 Q2. Safe (records stay proposed, R1). Fix: when stated.json
  holds a group whose offer was shown and the prompt affirms without naming records, suggest
  `plumb relay --group low-risk --prompt <digest> --quote "<owner's exact words>"` for the
  pinned list.
- [LOW] (R13 Q4) CLI fallback: in a new session where proposed records exist but none was
  touched this turn, `plumb turn end` prints nothing and the stated set is empty, so the owner
  never sees a card for them and a chat "ok" cannot confirm them unless the agent runs
  `plumb confirm`. Non-blocking under R1. Fix: on a session's first turn end, render the
  records awaiting the owner (capped), or point the agent to `plumb confirm`.
- [MEDIUM] (R13 Q4, R9) Confirmations resting on a message `plumb turn start` recorded
  (via: turn) are labelled "self-recorded message" in `plumb show` and the merge-check glance,
  but `plumb review` section 2 lists them as "relayed from your words ..." with no label, and
  `plumb hooks status` (Claude Code) prints no count of them while `plumb hosts status codex`
  does. Fix: every glance renderer reads the self-recorded flag from one helper; add the label
  and the count to `plumb review` and `plumb hooks status`.
- [MEDIUM] (R2) `approvals.host_logs_prompts` refuses a self-recorded prompt on Claude Code only
  when `PLUMB_AGENT_SESSION` is set. In a repository whose prompt log already holds
  hook-logged prompts from host claude-code, `env -u PLUMB_AGENT_SESSION plumb relay ...
  --prompt <turn digest>` confirmed both records (labelled self-recorded). For Codex a
  hook-logged prompt in the log already proves the host has a prompt hook. Fix: also return
  True when the prompt log holds a via: hook entry from any host.
- [MEDIUM] (R10.1, concept 4.3; baseline for SP6, not a defect of 32c3db8) Two worktrees of one
  repository capturing in parallel both allocated INT-003 and SR-003; merging both gave
  add/add conflicts on the record files, and after a plain resolution `plumb validate` reported
  0 errors and merge-check "log integrity: ok" while feat-b's intent was lost and its code and
  "SR: SR-003" trailer pointed at feat-a's requirement. Fix in SP6: reserve IDs through
  `refs/plumb/ids` inside `Store.next_id`; a two-worktree test with concurrent captures
  asserting distinct IDs; the merge driver or validate reports the same ID with divergent
  content as an intent conflict.
- [LOW] (R12.3) A new untraced `src/app/util/powerhelp.py` ("power helper for negative
  exponents") next to confirmed SR-004 "power works": the stop-hook block, `plumb turn end` and
  `plumb review` all say "no requirement owns it; record a new SR", although the terms overlap
  clearly (allowed degraded mode; latency fine: stop 0.8 s, turn end 0.7 s). Fix: when the code
  map has no entry for the file, fall back to term overlap with requirement titles and
  statements and offer the top candidate as a proposal.
- [LOW] (this round's fix, trade-offs) The widened change-clause reader errs towards refusing:
  a directive beside a word that does not only restate a shown record ("ok, and also add a
  divide function", a new request beside the ok) objects to the records it names, or to every
  shown record when it names none; a clause praising a record by its title ("ok, the multiply
  looks good", "ok, go ahead and add the cube") and one repeating a decision's chosen option
  ("ok, orders only") still confirm. A false refusal leaves records proposed
  (non-blocking under R1). A sentence that is the bare affirmation ("ok." then the correction)
  remains a whole statement: it may confirm the records the correction does not name, and the
  approval carries `prompt_objects`, which the merge-boundary glance flags with the whole
  message. Numbers count as content of a clause but never place a correction on a record (too
  many records share them); a clause naming no shown record but holding a number objects to
  every shown record ("ok, 3 minus 5 is 0 for us"; also "ok, see you at 5", a false refusal).
  Residual: a correction that shares no word with any shown record and holds neither a
  directive nor a number ("ok, negative exponents are supported" when no shown record
  mentions exponents) is still read as a plain ok; the stored quote and the glance's whole
  message remain the owner's backstop. Fix: when a judgment backend is configured, ask it
  whether each content clause beside the ok changes a shown record (Noul), and treat a clause
  with distinctive words the heuristic cannot place as a change.

## Delivered-repository verification, round 6 (2026-10-06, commits 32c3db8 and 6fa3228)

The HIGH finding of this round (exclusion, scoping and deferral replies such as "yes, apart
from the zero example", "go ahead, skip the zero example", "ok for the intent; I'll look at
the examples later", "ok for the examples only" and "would that be ok if I sleep on it"
confirmed the requirement the owner held back) was fixed in the same change: beside an
affirmation, any clause with a word beyond the closed vocabulary of assent is a reservation
(`approvals.owner_scope` / `change_clauses`, SR-005 EX-13). The residual named in the previous
round ("ok, negative exponents are supported" read as a plain ok) is closed by the same rule.

- [MEDIUM] (R13 Q4, R2) `plumb review` section 2 ("approvals you did not type",
  `present/review.py` `_glance`) prints `relayed from your words "ok, go"` with no
  "self-recorded message" label for a relay of a message `plumb turn start` logged (via:
  turn), and flags an objection only from the stored `prompt_objects`, never re-reading the
  message as `boundary/glance.py` does. `plumb show`, the merge-boundary glance and
  `plumb hosts status` do label it, so the three surfaces R13 Q4 names are covered (already
  recorded earlier). Fix: render review._glance rows through `boundary.glance.glance_rows`,
  `self_recorded` and `_message`, so every approval glance shares one labeller.
- [MEDIUM] (R2) The prompt hook tells the agent to relay with `--quote "<owner's whole
  sentence>"` beside an objection, but when the objection names a different record ("ok, but
  SR-002 should also accept floats", relaying SR-001) the whole sentence is refused (exit 3,
  "the owner's words name SR-002, not SR-001") while `--quote "ok"` succeeds, storing "ok" with
  `prompt_objects: true`. The whole message survives only in the gitignored per-worktree
  `prompts.jsonl` (DEC-004), so after merging from another checkout the merge-check glance
  and `plumb review` show only the bare "ok" (still flagged and revocable). Fix: beside any
  objection, require and accept the owner's whole statement as the stored quote and copy it
  into the committed approval event, so every glance shows it from any checkout; one test per
  entry point (relay by IDs, --group, --set, the prompt hook line, turn start) where the
  objection names a different record, and one two-worktree test whose glance runs in a
  checkout without the prompt log.
- [LOW] (R9) In a repository whose only records are SR-001 and SR-002, `plumb confirm SR-001
  SR-002` prints `the owner's own "ok" (or "ok SR-034") ...`, a hard-coded ID that does not
  exist there (`confirm.py` header). Fix: use one of the records shown (or a title) in the
  example phrase.
- [LOW] (quality bar: no hidden state) `plumb turn start --help` runs a real turn instead of
  printing help (reproduced again; already recorded): it appended an empty-text prompt entry
  (digest sha256:e3b0c442..., via: turn) to the gitignored `.plumb/session/prompts.jsonl` and
  rewrote `.plumb/session/cli/turn.json`. Fix: handle `--help` after the turn subcommand
  before any logging.
- [LOW] (this round's fix, trade-offs) The reservation rule errs towards refusing: beside an
  affirmation, a word outside the vocabulary of assent ("ok, see you tomorrow", "hmm, ok",
  "yes, exactly as discussed") holds back every shown record it cannot place, a false refusal
  that leaves records proposed (non-blocking under R1). Sentences before the affirmation's
  sentence count only through objection and change words ("Is the build green? Yes, approve
  SR-001" confirms). A reservation that refers to a kind ("the examples") holds back the
  records of that kind, not the intent. An ok scoped to "the intent and the examples" is not
  read as scoped. Fix: when a judgment backend is configured, ask it whether each clause beside
  the ok holds something back (Noul), and widen the vocabulary of assent from the owner's
  confirmed replies.

## SP6 spec and plan review (2026-10-06)

Review of `docs/specs/sp6-parallel-work.md` and `docs/plans/sp6-plan.md` against the concept
and the brief (R10). The one HIGH class (R14: SP6 owner-visible strings that named bare CLI
verbs, such as "(plumb log migrate)" in the merge report the pre-push and pre-merge-commit
hooks print, "plumb merge-fix fixes a collision later" and "+N more (plumb status)") is fixed
in the spec and the plan: spec 11.1 lists every SP6 owner-visible surface, phrases each one as
a `/plumb` command or plain words, routes the log migration behind "migrate the logs" (spec 11
table), puts every string in one coordinator-owned module (`plumb.present.owner_text`, plan
3.2 item 9) with `bare_cli_verbs`, and adds one test per surface to the lanes' test lists.
Medium and low findings, not fixed:

- [MEDIUM] (R14) The same "+N more (plumb ...)" pattern already runs through the codebase,
  outside SP6: `query.py` ("+N more (plumb brief --all)", twice), `align.py`
  ("+N more (plumb align)"), `boundary/report.py` `MORE` ("+N more (plumb merge-check
  --json)"), the `approvals.require_owner` refusal ("An agent relays the owner's words with
  plumb relay instead") and README lines such as "(plumb show <ID> for examples and tests)".
  The records carry it too: SR-009 EX ("+N more (plumb brief --all)"), SR-052 EX ("+15 more
  (plumb merge-check --json)"), and R13 Q2's own wording "(see plumb triage)" (DEC-017). These
  belong to the R14 class fix: route each through `plumb.present.owner_text` (spec 11.1) with
  a `/plumb` command or plain words ("+N more (/plumb status)", "/plumb review"), and update
  the record examples through `plumb capture` (they stay proposed). One test per surface with
  `bare_cli_verbs`.
- [MEDIUM] (R1, R10.5) Under DEC-021 git completes the merge with the conflict block in place,
  and the plan (8.2) deliberately leaves the pre-merge-commit hook uninstalled in plumb's own
  repository. A local merge into main can therefore record an unresolved intent conflict in a
  commit on main; the hold arrives only at push, or never in a repository without a remote or
  without the pre-push hook. The design respects R10.3 ("shown at the merge boundary") and the
  owner's choice of hooks, but the boundary can silently move after the merge commit. Fix:
  keep DEC-021; have the session brief and the status card raise an open IC on the default
  branch as "1 conflict awaits you" (spec 8.3 partly does this); state in the README and the
  concept 7.5 update that without the pre-merge-commit hook a local merge can carry an open
  conflict until push.
- [MEDIUM] (R10.5: "one full suite") `merge.premerge_run_full: false` lets the
  pre-merge-commit hook skip the full suite (spec 10 and 12; plan D7). The default is true, so
  this is not a contradiction, but the switch weakens the boundary and the spec does not say
  the pre-push hook still runs the suite when it is off. Fix: state that with the switch off
  the pre-merge-commit hook only defers the suite (it sets `full verification pending`,
  satisfied by the pre-push or merge-check run), or drop the switch.
- [MEDIUM] (KEEP: approvals pinned to exact content; R10.3) Spec 8.4 "Applying a choice writes
  the record with the chosen side's exact fields and body" is ambiguous about fields the
  driver already merged on their own: with theirs changing `title` cleanly and both sides
  changing `statement`, choosing "ours" either silently drops theirs's title change (the card
  shows only the conflicting fields, so the owner never sees it) or keeps it, and then the
  result hash matches no side and the re-confirmation claim fails. Fix: choosing a side
  replaces only the conflicting fields and keeps every field merged on its own;
  re-confirmation applies only when the resulting hash equals an approved hash, otherwise the
  record stays proposed with a read-back; add a test with one merged and one conflicting field.
- [MEDIUM] (R10.1) Spec 5.2: for a working-tree duplicate with no merge in progress, "the
  record whose file was added later in git log --diff-filter=A is the incoming one". After a
  committed merge, commit time can name the first-parent side's record as incoming when the
  other clone created its record later, contradicting DEC-022 ("The first parent ... keeps its
  IDs"): the record main relies on would be renumbered and its approvals moved to the alias
  path. Fix: for a committed duplicate, find the merge commit that brought the two records
  together and apply the first-parent rule to it (the side reachable only through the second
  parent is incoming); fall back to commit time only when no such merge exists, with a test.
- [LOW] (KEEP: approvals pinned to exact content) Spec 5.4 carries approvals across a renumber
  through `ids.approval_aliases`: an approval then confirms content whose hash differs from
  its pin (only the id differs), through an alias the agent-run merge-fix writes. It is
  tightly bounded (the carry holds only while the content with the old id hashes to the pin,
  and validate re-checks every renumber entry), but the merge-boundary glance does not show
  it. Fix: label carried approvals ("carried from SR-070 by renumber") in `plumb show` and in
  the merge-boundary glance, like agent-relayed and auto-JEV approvals.
- [LOW] (owner rule: no full suite except the single Integrate run) Plan D7 tests
  `test_hook_refuses_merge_commit_on_ic` and `test_commit_completes_after_choice` run a real
  merge-check, which runs the configured full suite with `merge.premerge_run_full: true` by
  default; the plan does not say they use a stub suite. Fix: run them in a temporary
  repository with a stub test command, or set `merge.premerge_run_full: false` there.
- [LOW] (R10.4) Spec 9.3's branch scan (branches without a worktree, one `git diff` per branch
  at session start) goes beyond reading the other worktrees' `.plumb`: it is capped (8
  branches, 400 ms) and consistent with "another worktree or branch", but a cold start with
  many branches spreads over several sessions with no sign that awareness is incomplete.
  Optional fix: the brief says "awareness: N branches not yet scanned" when the cap was hit.
- [LOW] (owner rule: disjoint ownership) Plan 3.1's coordinator row lists `cli.py` twice and
  `prompt.py`, `stop.py`, `post_edit.py`, `snapshot.py` and `install.py` without their
  `hosts/claude_code/` prefix, so the lane gate's `git diff --name-only` check against the row
  (3.4) cannot be applied mechanically. Fix: list full paths once each.

## SP6 spec and plan review, round 2 (2026-10-06)

Second review of `docs/specs/sp6-parallel-work.md` and `docs/plans/sp6-plan.md` against the
concept and the brief (R10), after 56d864b. No HIGH findings. Medium and low findings, not
fixed. Where an entry restates one from the round above, it says so; the fix here supersedes
or extends that entry.

- [MEDIUM] (R10.3: "Non-overlapping changes merge automatically. A content conflict becomes
  an INTENT CONFLICT, shown at the merge boundary as one intent card with both versions";
  quality bar: "Trust comes from evidence: hashes, pinned approvals") Spec 8.4 ("Applying a
  choice writes the record with the chosen side's exact fields and body ... keeps the merged
  links"; "Choosing a side whose content the owner confirmed on that side makes the record
  confirmed again"), SR-076 EX-3 and plan D6 `test_choosing_a_confirmed_side_reconfirms` do
  not say what happens to fields that merged on their own (7.3) when the owner picks a side.
  If "the chosen side's exact fields" means the whole record, the other side's non-overlapping
  changes (main's title change, say) are dropped silently although the card listed them as
  "Merged on their own", against principle 3.4 ("plumb never silently picks a side"). If they
  are kept, the result hash matches neither side and re-confirmation through the existing
  approval cannot hold. The pinned hash keeps this safe: a missing detail, not a
  contradiction. Same as the round-1 8.4 entry. Fix: the choice applies only to the
  conflicting fields and every other merged field is kept; re-confirmation through an
  existing approval happens only when the result hash equals that side's approved hash,
  otherwise the record stays proposed and the card says so ("keeps main's title too; needs
  your ok"); change SR-076 EX-3 and the D6 test to match.
- [MEDIUM] (R10.1: "`plumb merge-fix` renumbers at merge and rewrites every reference") Spec
  5.3's enumerated places and 7.3's driver EX renumbering leave references out. merge-fix
  does not rewrite references the incoming side added outside `.plumb` records, test files,
  claims and the merge message: docs (a `docs/specs` page naming SR-070), source comments and
  docstrings, CLAUDE.md, and `SR-070/EX-n` markers in test files outside the changed set.
  When both sides add the same EX-n, the driver renumbers theirs to EX-(n+1) and rewrites only
  the links inside that record, so the incoming test files' `@pytest.mark.sr("SR-005/EX-3")`
  markers silently point at ours's EX-3 and test evidence is attributed to the wrong example.
  Fix: merge-fix, plus a post-merge step for the driver's EX renumbers, scans every text file
  the incoming side added or changed since the merge base for the old ID or example reference
  (the same "introduced by the incoming side" rule), and reports what it cannot rewrite
  safely as drift; one test per place, including the EX renumber's test markers.
- [MEDIUM] (R10.1, the same words) Spec 5.3 and the SR-071 statement narrow "every
  reference" to "every reference the incoming side introduced", and rewrite test markers only
  in test files the incoming side added or changed since the merge base. That is the right
  reading (references from our side name our record, which keeps its ID; EX-4), but the spec
  does not say why, so a verifier can read it as an omission. Fix: one sentence in 5.3 and in
  the SR-071 statement: references from our side name our record, which keeps its ID, so
  "every reference to the incoming record" is exactly the set the incoming side introduced.
- [MEDIUM] (R10.5: "`plumb check --merge` on the merge result (confirmations, claims, links,
  intent conflicts, one full suite) as a pre-merge or pre-push hook") Spec 8.2 and 10 keep the
  pre-merge-commit hook optional, plan 8.2 says it "is NOT run on plumb's repository without
  the owner's request", and plumb's `.git/hooks` holds only `commit-msg`, so neither the
  pre-merge-commit hook nor the sp3 pre-push hook is installed on plumb. Under DEC-021 git
  completes a merge carrying an open intent conflict; a merge on main can record an IC block,
  and nothing holds it until someone runs /plumb merge-check. The owner's words describe the
  check running as a hook; the plan's caution (it changes the owner's merges) is reasonable
  but is not a ruling. Extends the round-1 DEC-021 entry. Fix: `/plumb init` (R15) offers the
  boundary hook as part of adopting a repository, with a one-line ask in the init summary; or
  record here, as an open owner question, which hook (pre-push or pre-merge-commit) is the
  default; and the status card says "merges are not checked by a hook" when neither is
  installed.
- [MEDIUM] (R10.3, R10.5, the same words) Spec 8.2 (DEC-021), plan 8.2: the driver exits 0
  and git records the merge commit with an open `conflict` block unless the optional
  pre-merge-commit hook is installed, which the plan leaves uninstalled on plumb, so on
  plumb's main an unresolved intent conflict can be committed and stay until the pre-push
  check. This stays within R10.5's "pre-merge or pre-push" wording: a design refinement.
  Same as the round-1 DEC-021 entry. Fix: the stop hook or the session brief keeps surfacing
  open ICs on the current branch until they are resolved (spec 8.3 already counts them), and
  this entry records that without the pre-merge-commit hook IC-carrying merge commits can
  land locally.
- [MEDIUM] (KEEP: "approvals pinned to exact content (simplified consent)") Spec 5.4
  (`approval_aliases`): a renumber changes the record hash, because the hash covers `id`, and
  approvals are carried through an alias only while the content with the old ID hashes back
  to the pin. That keeps the exact-content guarantee in substance, but the carried
  confirmation is a new trust path, not listed in the merge-boundary glance the way
  agent-relayed and auto-JEV approvals are (R2, R8 B). Same as the round-1 `approval_aliases`
  entry, raised to MEDIUM. Fix: list approvals carried by a renumber in the merge-boundary
  glance and in `plumb show`, labelled as carried by a renumber with the from and to IDs.
- [LOW] (R15: "The plugin's hooks and commands invoke the plumb CLI from the plugin's own
  bundled environment ... never from the target repository's .venv") Spec 7.1 writes
  `merge.plumb-record.driver = <launcher> merge-driver ...` into the repository's git config
  as an absolute launcher, and plan 8.2 installs it through `uv run plumb hooks install`.
  Once R15 lands that path points inside a versioned plugin install, so a plugin update can
  leave a stale driver path, and git then fails the record merge or falls back to a text
  merge without warning; the dogfood install also binds plumb's own driver to the repository
  `.venv`. Fix: point the driver at a stable shim, or re-check the launcher in the
  session-start hook and in `hooks status`, reporting "merge driver: stale launcher (/plumb
  init fixes it)".
- [LOW] ("a lighter, more elegant and interactive way to leverage coherence"; R10: "awareness
  instead of locks: git is the coordinator") Spec 5.4 to 5.5 (`approval_aliases`,
  `trailer_aliases`), 6.3 (pack cache) and 8.2 (held merge plus "finish the merge"): every
  part maps to an R10 item and none reintroduces leases, admission or transactions, but the
  alias layers and the per-stream pack cache add read-path complexity every reader must
  respect. A refinement concern. Fix: keep the aliasing behind the one choke point the spec
  names (`ids.approval_aliases` / `trailer_aliases`), with a conformance test showing no other
  reader resolves renumbers; revisit whether the pack cache is needed once real log volumes
  are measured.
- [LOW] (R10.2: "one file per entry under .plumb/log/<kind>/, as concept 4.7 says") Spec 6.1
  and 6.5 give migrated entries a suffix derived from the digest (`digest[8:16]`) and a
  `.000000` stamp, not the uuid8 of concept 4.7 (`<UTC-stamp>-<uuid8>.json`, "os.link with a
  uuid suffix"). A justified refinement (it makes the migration idempotent) that the concept
  does not mention. Fix: in the phase-2 concept update (spec 14 item 7), describe the
  deterministic suffix for migrated entries in concept 4.7.
- [LOW] (owner rule: "Hook latency stays in seconds. Awareness must stay cheap.") Spec 9.2 and
  9.3 add git processes to hooks: the session-start branch scan (up to 8 `git diff`
  processes, capped at 400 ms) and the stop-hook publish (2 git processes when HEAD moved).
  They are bounded and within budget, but on a 2-core machine with many branches the cap is
  reached often and some branches keep stale cached results. Related to the round-1 branch
  scan entry. Fix: keep the caps; measure the session-start cost on plumb's own repository
  after Integrate.
- [LOW] (owner rule: "Run no full suite except the single run in Integrate.") Spec 10
  (`merge.premerge_run_full: true`), plan 8.2: with the pre-merge-commit hook and the pre-push
  hook both installed, the full suite can run twice per merge-and-push. plumb avoids it by not
  installing the pre-merge-commit hook, but the default config makes the duplicate run
  possible for users. Fix: pre-push reuses the pinned full-run evidence when the
  pre-merge-commit run already covered the same tree identity (sp3 evidence reuse).
- [LOW] (plan hygiene) Plan 3.1's coordinator row lists `cli.py` twice and gives the hook
  modules without their `hosts/claude_code/` prefix after the first entry, so the paths are
  ambiguous for lane agents. Same as the round-1 coordinator-row entry. Fix: remove the
  duplicate and spell out the full paths for `prompt.py`, `stop.py`, `post_edit.py`,
  `snapshot.py` and `install.py`.

## SP6 lane LOGS (2026-10-07)

State: L1 to L7 done on branch `lane/logs` (worktree `C:/coding/plumb-logs`); SR-073 and
SR-074 linked to their modules and tests and still proposed (no agent approved them);
SR-006's statement and EX-2 restated for per-entry files through `plumb capture` (proposed).
plumb's own logs are NOT migrated here: that is Integrate (plan 8.1), and it must run
`plumb log migrate` after merging this lane.

- [MEDIUM] (coordination) Phase 0 had not run when the lane started (no `tests/logutil.py`,
  no `present/owner_text.py`, no `log` route). The lane wrote the minimum it needed in
  coordinator files: `LogEntry.name`, `MigrationReport` (`contracts.py`), `since` on
  `CoreAPI.log_read` (`contracts.py`, `api.py`), the `log` route and help line (`cli.py`),
  `present/owner_text.py` with only `LEGACY_LOG` and `bare_cli_verbs`, the legacy-log warning
  in `validate.py`, `MergeReport.legacy_log_lines` and its render line (`boundary/report.py`),
  `tests/logutil.py` and the rewiring of the ten test files. Fix at Integrate: merge LOGS
  first, then reconcile the other lanes' copies of `owner_text.py` (an add/add) and of the
  contract classes.
- [MEDIUM] (outside the lane's row, fixed because it broke a guarantee) `verify/api.py`'s
  derived-cache fingerprint used the size and mtime of `evidence.jsonl`; with one file per
  entry that file never changes again, so the cached verify views would never see new
  evidence. It now uses `log.stream_stamp(paths, "evidence")` (per kind directory: mtime,
  entry count, last name). `load_index` uses the same stamp to skip reading when nothing
  changed.
- [MEDIUM] (spec 6.5 step 3 wording) "with `merge=union`, base lines removed on one side and
  lines appended on the other leave exactly the appended lines" is not what git does: the
  emptied base lines and the appended lines form one adjacent hunk, and union keeps both
  sides, so the old lines come back next to the new ones. Nothing breaks: readers dedupe by
  digest, `verify_chain` accepts them, and the next migration skips the lines that already
  have files and writes only the new ones (`tests/logs/test_migrate.py::
  test_pre_migration_branch_merges_then_migrates`). Fix: correct the spec sentence.
- [LOW] (design notes, deviations from the spec's letter, not its contract) The temporary
  file of an append lives in the gitignored `.plumb/cache/`, not in the kind directory, so a
  crash never leaves a committable stray file; new entries never use the `.000000`
  microsecond stamp, which marks a migrated name; reads order entries with a heap-ordered
  walk of the chain, so a skewed clock never puts an entry before the entry it chains to;
  the evidence index cursor is the list of applied digests, because a legacy line's name
  (`evidence.jsonl:<line>`) is reused when the file is rewritten.
- [LOW] (latency, owner rule "Hook latency stays in seconds") A warm read of 2000 events
  costs about 35 to 45 ms on this machine when it is quiet, and up to about 75 ms while other
  lanes run tests on the two cores; `tests/logs/test_read_cost.py` takes the best of ten.
  The first open of a freshly written file costs about 7 ms on this Windows machine (on-access
  scanning), once per file: migrating plumb's ~530 legacy entries costs a few seconds once.
  The evidence pack cache keeps every test-run payload (about 50 KB each); if evidence grows
  to hundreds of runs, slim the cache to the fields readers use.
- [LOW] (test layout) `tests/logs/` has an `__init__.py`, so its modules import as
  `logs.test_owner_text` and `logs.test_two_worktrees`. The plan gives the same basenames to
  other lanes (`test_owner_text.py` in ids, mergedriver, awareness and present;
  `test_two_worktrees.py` in awareness; `test_install.py` in mergedriver and host); in
  pytest's default import mode, two test files with one basename and no package collide at
  collection. Fix: each new test directory gets an `__init__.py`, or the files are renamed.
- [LOW] (drift) Editing shared files left links of other requirements stale (SR-003, SR-008,
  SR-010, SR-017, SR-018, SR-025, SR-027, SR-030, SR-034, SR-047 to SR-049 among them); the
  lane repinned only its own SR-006, SR-073 and SR-074. Fix: the coordinator reviews and
  repins them at Integrate.
- [LOW] (pre-existing, not this lane) `tests/host/test_latency.py::
  test_intent_lines_survive_cpu_contention` fails on `main` (89f499b) as on this branch: the
  prompt "ok, and SR-002 needs work" is now read as an objection to SR-002, so the relay line
  the test expects is not offered. It comes from the audit-round-5 objection scoping, not from
  the log format.
- [LOW] (ordering edge) `importer/recheck.py` checks that an import approval's import event is
  "the log entry right before it" in read order. Reads now order by `at`, then the chain, then
  the name: the approval always follows its import event, but an entry merged from another
  branch with a stamp between the two could sit in between. Fix: compare the approval's
  `prev` with the cited import event instead of the read-order neighbour.

## SP6 lane LOGS, review (2026-10-07): medium and low findings

The review's HIGH finding (a cold read in a new worktree or clone opened every entry file:
seconds past the 2 s hook ceiling) is fixed in `log._read_uncached`, the one place a reader
reads an entry file: many misses come from another worktree's pack cache, then from one
`git cat-file --batch`, and only the rest from disk (`tests/logs/test_cold_read.py`, one test
per entry point; `tests/logs/test_read_cost.py` times a real `git worktree add` and a fresh
clone with no priming pass). The rest are recorded here.

- [MEDIUM] (migrate message) `migrate()` can return refused entries after it has written
  files: the "<name>: exists with other content" case is found inside the write loop in
  `log.py`, after earlier lines were written, yet `logcmd` prints "refused; nothing was
  migrated". No data is lost (truncation is skipped when anything is refused), but the
  owner-facing message is false. Fix: say what was written, or check every existing name
  before writing anything.
- [MEDIUM] (migrate holds the lock) `migrate()` holds the per-worktree log lock while it writes
  every entry file, about 7 ms per new file on this Windows machine. Above about 1400 legacy
  lines the run passes `LOCK_STALE_S` (10 s): a concurrent appender may delete the lock as
  stale and append against a head pointer migrate is about to rebuild (a silent fork; every
  `prev` still resolves), and meanwhile every hook append waits `LOCK_WAIT_S` (2 s) and raises
  `LogLockTimeout` (a lost prompt or test-run entry plus 2 s of hook latency). Rare and done
  once. Fix: refresh the lock's mtime during long runs, or write the files before taking the
  lock and take it only for truncation and the head rebuild.
- [MEDIUM] (lane scope) The lane wrote to files plan 3.1 gives to the coordinator:
  `contracts.py` (`LogEntry.name`, `MigrationReport`, `CoreAPI.log_read` `since`), `api.py`,
  `cli.py` (the `log` route), `validate.py`, `boundary/report.py`, `verify/api.py`,
  `present/owner_text.py` (new), `tests/logutil.py` and the ten rewired test files; phase 0
  had not run. At Integrate `owner_text.py` becomes an add/add against the coordinator's or
  other lanes' copies, and the contract classes may diverge from what
  `tests/integration/test_contracts.py` and the other lanes expect. Fix: merge LOGS first and
  reconcile the contracts by hand.
- [MEDIUM] (spec 6.5 step 3) The spec says merging an emptied legacy file under `merge=union`
  leaves exactly the appended lines. It does not: union keeps the old lines too. A lane
  branched before the migration and merged after it brings back all ~510 old lines plus the
  new ones; the legacy file is then "present", the warm order cache is off, every read parses
  the 570 KB JSONL again and validate warns until `plumb log migrate` runs again. Readers'
  digest dedup and the next migration absorb it. Fix: Integrate (8.1) runs the migration
  after every lane merge, as the plan says; correct the spec's sentence.
- [LOW] (migrate dedup) `migrate()` dedupes planned lines by file name (the `seen` set), not by
  digest, then truncates. Two distinct legacy lines with the same `at` second and the same
  `digest[8:16]` get one name; the second is counted as skipped and lost when the legacy files
  are emptied (about 2^-32 per same-second pair). Fix: refuse, rather than skip, when `seen`
  holds a different digest for that name.
- [LOW] (migrate race) A `FileExistsError` race in `_write_new` during `migrate()` counts the
  line as skipped without comparing digests, and the legacy files are then truncated: a
  concurrent writer's file at the same name is trusted. Fix: compare the digest of the file
  found, as the pre-check does.
- [LOW] (head pointer) `_write_json_atomic` swallows a failed `os.replace` of
  `.plumb/cache/log-head.json` (a Windows sharing violation, say an antivirus scanner holding
  it). The old pointer still names an existing file, so the next append chains to a stale
  `prev` and forks the chain inside one worktree. `verify_chain` accepts it and ordering falls
  back to `at` then the name: no data loss, only a needless fork. Fix: on a failed replace,
  remove the pointer so the next append rebuilds it by a scan.
- [LOW] (read order at Integrate) The read order (`at`, then the chain, then the name) differs
  from the legacy file order on plumb's own events log: `main`'s `events.jsonl` has four
  non-monotonic union-merge seams (lines 122, 199, 262, 271, all `repin`), and the digest
  sequences first differ at index 98, before and after migration. By design (spec 6.3); only
  `repin` entries move today, so state is unaffected. Fix: at Integrate, check that status,
  confirm and claims output is unchanged after `plumb log migrate`.
- [LOW] (import recheck order) `recheck_import_approvals` requires the import event to be the
  read-order neighbour of its approval; an entry merged from another branch with a stamp
  between the two (same or adjacent second) sits in between and gives a spurious validate
  error. Already recorded above; fix: compare the approval's `prev` with the cited event.
- [LOW] (line endings) `GITATTRIBUTES_LINES` has no rule for the entry files. With
  `core.autocrlf=true` (set on this machine and in C:/coding/plumb) `git add .plumb/log` warns
  "LF will be replaced by CRLF" once per entry file and checkouts write CRLF. Readers are
  unaffected (the digest is computed from the fields; the cold read accepts a blob whose size
  differs by the CRLF conversion), but the noise and size differences remain. Fix: add
  `log/**/*.json -text` (or `eol=lf`) to `.plumb/.gitattributes`.
- [LOW] (validate in a new worktree) `log.verify_chain` (plumb validate, the merge check)
  reads every entry file itself, by design: it is the tamper check of the files on disk. In a
  worktree or clone git has just written, the first `plumb validate` therefore pays the
  on-access scan once per file (seconds for ~500 entries). It is not on a hook path. Fix if it
  matters: compare each file's size and mtime with the pack cache and git's index, and read
  only files git reports as modified (`git diff-files`) or untracked.
- [LOW] (cold read with loose objects) The cold read's git path costs about 0.5 ms per loose
  object on this machine (about 1 s for 2000 entries committed moments before and never
  packed, with no warm sibling worktree); packed objects (a clone, after `git gc`) cost about
  0.07 ms each, and a warm sibling's pack cache answers in tens of ms. The usual case (the
  main worktree's hooks have read its log) takes the sibling path. Fix if it matters: run
  `git gc --auto` after a migration, or read loose objects with zlib directly.

## SP6 lane LOGS, review round 2 (2026-10-07): medium and low findings

No HIGH finding. The review checked the hash chain, the migration and the merge and found them
sound: append (temporary file in the cache, `os.link` with no replace, the head pointer under
the per-worktree lock), the dual-format read with digest dedup and a topological order (an
ancestor always comes before its descendant), `verify_chain`, `migrate` (byte-identical
fields, deterministic names, refuses bad lines, truncates only when nothing is refused),
`merge.log_integrity` (one `git diff` for entry files, legacy lines accepted as migrated
digests), the evidence index cursor (a digest prefix that rebuilds on reorder) and the bounded
cold read (sibling pack, then one `git cat-file --batch`). A simulated migration of plumb's
own 528 legacy lines (509 `repin`, 1 `triage`, 18 `test-run`) found no line to refuse and no
duplicate names. Every test named in plan section 5 exists. The edge cases recorded above
(the false "nothing was migrated" message, the lock held during a long migrate, the 2^-32
name-collision skip, the `FileExistsError` race, `merge=union` bringing back old lines, the
import recheck using the read-order neighbour) stand.

- [MEDIUM] (migrate pre-check) `migrate()` treats an existing entry file at a line's migrated
  name as the same entry when its `digest` field matches the line's digest (`log.py` around
  lines 808-814); it never checks `entry_digest(existing)`, then truncates the legacy files.
  If that file's payload was edited but its `digest` field kept, the line counts as skipped,
  nothing is refused and `events.jsonl` is emptied: the genuine line is lost and only the
  tampered copy remains. `verify_chain` still flags the digest mismatch, so the tamper is
  detected, but the original cannot be recovered. Fix: skip only when
  `existing.get('digest') == entry_digest(existing) == raw['digest']`; otherwise refuse.
- [MEDIUM] (pack cache trusted) Readers take entry content from the gitignored pack cache
  (`.plumb/cache/log-<stream>.json`), keyed only on each file's size and mtime and never
  checked against the entry's digest; a cold read can also take content from a sibling
  worktree's pack cache (`_read_from_siblings`), matched on name and size. `verify_chain`
  reads the files themselves, so an edited cache changes what confirm, glance and validate's
  semantic checks see while `plumb validate` and `merge.log_integrity` stay clean; before this
  lane any edit to `events.jsonl` was reported by validate. Confirmed in a scratch dir: append
  an approval of SR-001, read once, rewrite `log-events.json` so the cached payload says
  SR-999; `log.read` returns an approval of SR-999 and `log.verify_chain` returns `[]`. The
  edit-tool guard denies writes under `.plumb/log/**` only, not `.plumb/cache/`. Not HIGH: the
  spec mandates the cache and the threat model already accepts forging uncommitted entries.
  Fix: check `entry_digest(raw) == raw['digest']` on sibling and pack hits, and let validate
  compare the pack with the files it already reads.
- [MEDIUM] (import recheck order, raised from LOW) The read order (`at`, then the chain, then
  the name) can put an entry merged from another branch between an import event and its
  `by: import` approval; `recheck_import_approvals` then raises a validate ERROR, which holds
  the merge. Parallel work (R10) triggers it: worktree A writes the import event at
  10:00:00.100 and its approval at 10:00:00.150, worktree B logs a prompt at 10:00:00.120;
  after the merge the prompt sits between the two and validate reports "by: import approval's
  import event is not the log entry right before it". Fix at Integrate (outside the lane):
  compare the approval's `prev` with `import_event`, as `import_problem` already does, instead
  of the read-order neighbour.
- [MEDIUM] (lane scope, phase 0) Phase 0 never ran: `main` is still at 89f499b, and the IDS,
  MERGEDRIVER and AWARENESS lanes branch from it too. The contract shapes this lane added match
  spec 12 (`LogEntry.name`, `MigrationReport`, the read signature with `since`,
  `MergeReport.legacy_log_lines`), so no contract is broken, but merging LOGS and then another
  lane that also created `present/owner_text.py` or extended `contracts.py` conflicts. Already
  recorded above (lane scope); the coordinator reconciles by hand at Integrate.
- [LOW] (spec edit) The lane rewrote spec section 6.3 in `docs/specs/sp6-parallel-work.md`, a
  coordinator-owned file (plan 3.1 lets lanes only append to `docs/followups.md`), to describe
  the cold-read design (sibling pack, `git cat-file --batch`). The lane-scope follow-up above
  lists the other coordinator files but not this one. At Integrate the coordinator should
  review that 6.3 text as a spec change before other lanes or verifiers read it as the
  contract.
- [LOW] (stray root cache, outside the lane) The lane's focused set fails one test,
  `tests/core/test_primitives.py::test_find_root_prefers_plumb_dir`, because a `C:/.plumb/`
  directory now exists on this machine (created 2026-10-07 10:39, holding only
  `cache/changing.json` and a leftover `.changing.json.<pid>.<ns>.tmp`). `find_root` then
  resolves any path without a nearer `.plumb/` to `C:/`. `changing.json` is not written by
  this lane's code; it looks like an AWARENESS-lane writer that ran with no project root and
  created `.plumb/cache` at the drive root. Fix: writers of `.plumb/cache` must refuse when
  `find_root` found neither `.plumb/` nor `.git`, and the test should not depend on the drive
  root being clean. The directory was left in place (not created by this lane).
## SP6 lane IDS (2026-10-07)

Lane IDS (`lane/ids`, worktree `C:/coding/plumb-ids`): SR-070 to SR-072 implemented with
their tests; R17's renumber label added as SR-071 EX-6 (proposed). Every item of plan 4 (I1
to I7) is done. Open items, medium and low:

- [MEDIUM] (plan 3.2, phase 0) Phase 0 was not on `main` when the lane started (no
  `contracts` additions, no `ids` stubs, no `present/owner_text.py`, no `tests/gitrepo.py`).
  The lane added the IDS pieces itself, additively, against the plan's names: `IdState`,
  `Collision`, `MergeFixResult` and `RecordStatus.carried_from` in `contracts.py`;
  `present/owner_text.py` with `bare_cli_verbs` and the IDS constants only (the other lanes'
  constants still to add); the `merge-fix` and `ids` routes and help lines in `cli.py`;
  `MergeReport.id_collisions` with its section and exit 1 in `boundary/report.py`; the
  lane-local `tests/ids/gitrepo.py`. The coordinator reconciles these with the other lanes at
  Integrate (expect an add/add on `present/owner_text.py`). `tests/ids/` has an
  `__init__.py` so its `test_owner_text.py` does not clash with the other lanes' files of
  that name; the other lanes need the same.
- [MEDIUM] (drift from shared files) The lane's edits of shared modules left other SRs'
  whole-file `implemented_by` links stale (SR-001, SR-004, SR-005, SR-007, SR-012, SR-015,
  SR-027, SR-028, SR-030, SR-031, SR-033, SR-034, SR-035, SR-037, SR-039, SR-041, SR-047,
  SR-048, SR-049, SR-052, SR-053, SR-057, SR-059, SR-060, SR-061, SR-062, SR-063, SR-064,
  SR-068, SR-069). Lanes repin only their own SRs; the coordinator reviews and repins at
  Integrate.
- [LOW] (spec 5.5) `merge.touched_requirements` reads the range's trailers without the
  renumber map, so an incoming commit's `SR: SR-070` also marks this side's SR-070 as touched
  at the merge boundary (conservative: one more requirement checked, never one fewer).
- [LOW] (spec 5.4) A carried approval carries no `verified_by` test pins: the changed-test
  check of a carried confirmation starts again from the owner's next approval; the escalated
  set check (`boundary.report._set_confirmed`) and the importer's `_approved_before` ignore
  carried approvals (both conservative).
- [LOW] (spec 5.2) A duplicate ID at two paths with no merge in progress and no merge commit
  at `HEAD` renumbers the later-added file and rewrites only that record's own references;
  references elsewhere are left for `plumb validate` to report.
- [LOW] (spec 12 config) `ids.retries` and `ids.retry_s` are read from the config when it
  has an `ids` section; `config.py` does not have one yet (phase 0), so the defaults (50
  tries, 3 s) hold.
- [LOW] (pre-existing, R14) `plumb --help`'s `merge:` category line is cut at its first
  comma by `help_text` ("one full run, claims"), and the merge report's other sections still
  print bare `plumb approve` / `plumb tests run` text; neither is SP6 text.

## SP6 lane IDS review (2026-10-07)

The review's two HIGH findings are fixed on `lane/ids`. (1) A merge that a person resolved
by hand to one file (a `kept-one` collision) is now reported by `ids.collisions`, the one
choke point that `plumb check --merge`, `plumb merge-check`, the pre-push hook and
`plumb merge-fix` all read. It is reported for a merge in progress (`MERGE_HEAD`) and for
every merge commit in `base..HEAD`. `merge-fix` restores the lost incoming record under a
new ID. (2) The reference rewrite now decides which side added each reference by its
place: a test marker belongs to the test node it decorates, and a body wikilink is placed
by its line's position. It no longer goes by identical line text. The open review findings
follow, medium and low:

- [MEDIUM] (`ids/reservation.py`, spec 4.3) Seeding scans only this worktree's record files
  and the local branch tips. It misses the uncommitted records of other linked worktrees
  that were created before `refs/plumb/ids` existed. The first reservation can then hand
  out an ID that another worktree already wrote. This is the reuse SR-070 exists to
  prevent, open for one upgrade window. Example: worktree A has an uncommitted SR-080 from
  the old local numbering, and worktree B runs `plumb new requirement` first after the
  upgrade. The seed sees SR-079 as the highest and reserves SR-080. A cheap fix: when
  seeding and in `ids sync`, also read the `.plumb/` directories listed by
  `git worktree list --porcelain`.
- [MEDIUM] (`ids/mergefix.py`) A duplicate with no merge context (no `MERGE_HEAD`, and
  `HEAD` is not a merge commit) gives an empty `_Context`. `_candidates` then returns
  nothing, so only the incoming file is renamed: no references are rewritten and no
  commits are mapped, yet the output still reports success ("0 references"). If
  SR-005-imported.md had incoming DEC or test references, they would still point at
  SR-005 without any warning. Fix by deriving a base from `git log --diff-filter=A` of the
  later file, or by reporting a remaining collision or a warning that the references could
  not be classified.
- [MEDIUM] (`merge.py`, spec 5.5) `touched_requirements` gives the merge boundary its set
  of touched requirements, which feeds the R1 confirmations. It reads `SR:` trailers with
  plain `parse_sr_trailer`, not through `ids.trailer_aliases`, because only `claims_check`
  was rewired. After merge-fix, an incoming commit's `SR: SR-002` marks the first parent's
  SR-002 as touched, so the owner is asked to confirm the wrong record. The renumbered
  SR-003 is caught only through its path. This supersedes the LOW entry above.
- [MEDIUM] (`ids/aliases.py`, spec 5.4) `renumber_problems` checks neither that the listed
  approvals "come from the incoming side" nor that the `to` record exists. `carry()` still
  moves listed approvals off the old ID whenever the old record's current hash differs
  from the pin. Two failure cases:
  - A hand-written renumber entry (from SR-005 to an ID that does not exist) lists an owner
    approval of SR-005's earlier words, after SR-005 was edited. `plumb validate` accepts
    the entry, and `carry()` then drops that approval from SR-005's standing approvals.
    SR-005 then reads as never owner-confirmed, which matters for checks such as R8 B
    ("never auto-approve an edit to an owner-confirmed record").
  - A hand-written entry can move an approval of stale words onto a byte-identical copy
    under a new ID.

  The record is tamper-evident only, which R2 accepts, so this stays medium. Separately,
  the abbreviated-sha fallback of `map_trailer` (`s.startswith(sha) or sha.startswith(s)`)
  can match the wrong commit when the sha is short.
- [MEDIUM] (`ids/mergefix.py`) `rewrite.trailers` maps every `SR:` occurrence of the old
  ID in MERGE_MSG and SQUASH_MSG, including trailers that name the first parent's record.
  The spec allows only those for the incoming side's work. Squash-merging a branch whose
  message lists both sides' work under SR-070 rewrites them all to SR-081, so the commit
  claims the wrong requirement for our side's paths.
- [MEDIUM] (`ids/reservation.py`) Two rough edges:
  - `_swap` lets a `NoGit` from `hash-object` or `update-ref` (for example a read-only
    object store) escape as a traceback, with no exit code.
  - A ref that points at a non-blob, or at a blob that does not parse, reads as missing or
    empty. A non-blob makes every compare-and-swap fail until `IdBusy`. An unparsable blob
    resets `high` to the local maximum, so the next reservation starts from local files
    only and can reuse an ID that another worktree reserved.
- [MEDIUM] (`ids/mergefix.py`, spec 5.1) merge-fix only half-works during a rebase or a
  cherry-pick. `context()` looks only at `MERGE_HEAD` and `HEAD^2`, so an add/add left by a
  rebase or cherry-pick gets an empty `_Context`. The record is renamed, but no other
  file's references are rewritten, nothing is staged, no commits are mapped, and `held`
  covers only the working tree. Example: during `git rebase`, a replayed commit adds SR-070
  and upstream also added SR-070. merge-fix renames the incoming record to SR-081 and
  prints "now SR-081 (0 references ...)", but the markers, links and trailers that the
  replayed commits carry still name SR-070. Later replayed commits may already use the
  reserved number, which causes a fresh collision. Spec 5.1 limits merge-fix to
  `MERGE_HEAD`, but the command neither refuses nor warns.
- [MEDIUM] (`ids/rewrite.py`) `rewrite.record()` returns the file unchanged, counting 0
  references, when the merged record file does not parse, for example when git left text
  conflict markers because no merge driver was installed. The incoming side's references
  in that file are skipped without a word, and merge-fix still reports success. Example:
  without the driver, both sides edit FEAT-001 near the same lines and the incoming side
  adds `requirements: [SR-070]` (its own SR-070). merge-fix renumbers that record to SR-081
  but skips FEAT-001, which still has conflict markers. Once the owner resolves the
  conflict, FEAT-001 points at this side's SR-070, the wrong record, and a second run
  finds nothing to fix. merge-fix should list such files as remaining, or refuse while
  record paths are unmerged. The same applies to `rewrite.markers` on a test file that does
  not parse.
- [MEDIUM] (`ids/ref.py`) `update()` raises `Moved` on any `update-ref` failure, including
  a stale `refs/plumb/ids.lock` left by a crashed process. From then on, every `plumb new`,
  capture or decide retries for 3 s and exits 2 with "another session is creating records;
  try again in a moment", and that message stays true until someone deletes the `.lock`
  file by hand. A fix would tell "cannot lock ref" apart from a real old-value mismatch and
  name the lock file in the message.
- [MEDIUM] (`ids/collision.py`, kept-one, new with this fix) merge-fix fixes a `kept-one`
  collision only for the merge it works on: the merge in progress, or `HEAD` as a merge
  commit. `merge-check` reports a `kept-one` from an older merge commit in `base..HEAD`,
  but `merge-fix` does not see it ("nothing to fix"), so the owner must restore that record
  by hand. Scanning `base..HEAD` also costs about three git calls for each merge commit in
  the range, which is cheap for usual pushes but grows with long-lived branches that merge
  `main` often.
- [LOW] (`merge.py`, spec 5.4) `approved_ends()` reads approvals through `checked_entries`
  without the renumber carry, so a carried requirement's owner-approved code ends are not
  recognised. After a pure renumber from SR-070 to SR-081, SR-081 shows as confirmed
  (carried), yet the merge boundary lists its `implemented_by` ends as "extended" and waits
  for the owner (exit 4). This errs on the safe side but contradicts "a renumber alone keeps
  the owner's confirmation".
- [LOW] (`boundary/report.py`, spec 10 and R18) `collision_lines()` puts raw `.plumb` file
  paths in the owner-facing merge report, for example
  `SR-070: "a" and "b" hold one ID (.plumb/requirements/SR-070.md (both branches added it)); /plumb merge-fix fixes it`.
  The spec asks for titles and "/plumb merge-fix fixes it", and R18 counts `.plumb` paths as
  internals the owner should not see.
- [LOW] (`ids/reservation.py`, spec 4.3) The first seed reads only branch tips and this
  worktree's files (see the MEDIUM seeding entry above). Right after the upgrade, a
  reservation can hand out a pre-SP6 ID from another worktree's uncommitted files, and
  nothing flags it until the merge.
- [LOW] (`ids/cli.py`, spec 5.6) `plumb merge-fix --dry-run` exits 0 even when it would
  renumber collisions, because only sides that do not parse end up in `remaining`. Spec 5.6
  ties exit 1 to "a collision remains", and a dry run fixes nothing. An agent that runs the
  dry run as a check sees exit 0 and treats the merge as collision-free.
- [LOW] (sp6-plan 3.1 and 4, ownership) The modules are named `reservation.py` and
  `collision.py`, not `reserve.py` and `collisions.py`. Because phase 0 was not on `main`,
  the lane also edits files the coordinator owns: `contracts.py`, `owner_text.py`, `cli.py`,
  `store.py`, `confirm.py`, `claims.py`, `validate.py`, `boundary/report.py`, `glance.py`,
  `cards.py`, `importer/apply.py`, `capture.py` and `approvals.py`. The other lanes did the
  same. Integration will hit add/add or text conflicts in `present/owner_text.py`,
  `contracts.py` (the `MergeReport` and `Collision.how` fields), `boundary/report.py` and
  `cli.ROUTES` across all four lanes. The lane gate's check that every path is in the
  lane's row of 3.1 fails.

## SP6 lane IDS review, round 2 (2026-10-07)

The round's three HIGH findings are fixed on `lane/ids`, each at one choke point with one
test per entry point:

1. Same record, not a collision (spec 5.1, concept 4.4). `collision.same_record` compares
   record hashes, which leave `links` and their pins out, and is the only "same content"
   test that `unmerged_add_add`, `duplicates`, `kept_one` and `preview` make. A side that
   only ran `plumb link` or `plumb repin` on a record both sides imported, or a merge driver
   resolution that is equal after parsing, is no longer renumbered into a second copy
   (`tests/ids/test_same_record.py`).
2. A carried approval counts in every reader at the merge boundary (R17). What an approval
   pinned is read through `confirm.pinned_through_renumbers` (backed by
   `ids.aliases.carried_items`, the same conditions as `carry`), in `merge.approved_ends`
   and `boundary.report._set_confirmed`. A past commit's `SR:` trailer is read through
   `claims.claimed_ids`, in `claims_check` and `merge.touched_requirements`
   (`changed_paths` now returns `(sha, message)` pairs). After a pure renumber, merge-check
   no longer lists the carried requirement as "extended", no longer holds an escalated set
   whose member was renumbered, and no longer counts the first parent's record as touched by
   the incoming commits (`tests/ids/test_carried_readers.py`). This supersedes the earlier
   LOW and MEDIUM `touched_requirements` entries, the LOW `approved_ends()` entry, and the
   "escalated set check ignores carried approvals" part of the LOW carried-pins entry.
3. merge-fix renumbers nothing while a file naming the ID cannot be read (spec 5.3, 5.6).
   `mergefix._unresolved` is the one gate before any reservation or write, dry run
   included. It covers each record, test or claims file whose incoming version names a
   colliding ID and that is still unmerged (`git ls-files -u`) or does not read
   (`rewrite.readable`: conflict markers, a broken record, Python or YAML). merge-fix then
   prints `owner_text.FIX_BLOCKED`, lists the files in `MergeFixResult.blocked`, keeps every
   collision in `remaining` and exits 1 (`tests/ids/test_unresolved.py`). This supersedes
   the MEDIUM `rewrite.record()` entry.

Open, medium and low (from the review, restated where an earlier entry already had them):

- [MEDIUM] (`ids/cli.py`, spec 5.6) `plumb merge-fix --dry-run` exits 0 when it would
  renumber collisions: `remaining` holds only the sides that do not parse, and spec 5.6
  ties exit 1 to "a collision remains". An agent that runs the dry run as a check during an
  add/add merge gets exit 0 and treats the merge as collision-free, while merge-check still
  holds it with exit 1. (A blocked dry run now exits 1.)
- [MEDIUM] (`ids/rewrite.py`, spec 5.3) `rewrite.trailers` maps every old-ID token in the
  `SR:` lines of MERGE_MSG and SQUASH_MSG, including trailers that name the first parent's
  record; the spec limits the rewrite to the incoming side's work. A squash merge whose
  message carries `SR: SR-070` for both sides' work is rewritten to `SR-081` only, so the
  commit claims the wrong requirement for our side's paths, and claims check attributes
  them to the incoming record.
- [MEDIUM] (`ids/ref.py`) `update()` turns every `update-ref` failure into `Moved`,
  including a stale `refs/plumb/ids.lock` left by a crashed process. Every reservation then
  retries for 3 s and fails with the misleading `ID_BUSY` text ("another session is
  creating records; try again in a moment") until someone deletes the `.lock` file by hand.
- [MEDIUM] (`contracts.py`, plan 3.1 ownership) Phase 0 was not on `main`, so the lane wrote
  coordinator-owned files itself: `contracts.py`, `cli.py` ROUTES, `store.py`,
  `confirm.py`, `claims.py`, `validate.py`, `boundary/report.py`, `glance.py`, `cards.py`,
  `approvals.py`, `capture.py`, `importer/apply.py` and a new `present/owner_text.py`
  (this round adds `MergeFixResult.blocked`, `owner_text.FIX_BLOCKED`,
  `confirm.pinned_through_renumbers`, `claims.claimed_ids` and `claims.trailer_aliases`).
  The lane gate's "every path in the lane's row" check fails. At Integrate the four lanes
  each create `present/owner_text.py` and edit `MergeReport`, `cli.ROUTES` and contracts:
  expect add/add and text conflicts that the coordinator reconciles by hand, with a risk of
  dropping one lane's constants or fields.
- [MEDIUM] (`ids/aliases.py`, R17, found while fixing item 2) Only the renumbered record's
  approvals are carried. Another incoming record that the rewrite changes (a decision whose
  body or `rationale` names `SR-070`, an escalated anchor's `members`, a feature's
  `requirements`) gets a new hash, so its own approval no longer pins it. A matters-true
  decision that decides the renumbered requirement then waits at the merge boundary, and
  `capture.spec.set_state` (the stop hook, `/plumb review`) reads an escalated set whose
  anchor lists the renumbered member as unconfirmed. The owner is asked again about words
  that changed only by the ID. A fix in the same spirit as `approval_aliases`: the
  `renumber` entry records each rewritten record's hash before and after the rewrite, and
  the carry accepts an approval of the "before" hash while the record still hashes to the
  "after" one.
- [LOW] (`confirm.approved_test_pins`, spec 5.4) Still reads approvals without the carry,
  on purpose: the rewrite changes the `mark.sr` argument inside the acceptance test, so
  carrying the pinned test hashes verbatim would turn every carried confirmation with tests
  into "acceptance test changed". A carried confirmation therefore has no changed-test
  check until the owner's next approval (the earlier LOW carried-pins entry, still open).
- [LOW] (`boundary/report.py`, spec 10 and R18) `collision_lines()` puts raw
  `.plumb/requirements/...` paths in the owner-facing merge report; spec 10 and R18 ask for
  titles, without internals. The owner sees `SR-070: "a" and "b" hold one ID
  (.plumb/requirements/SR-070.md (both branches added it))`.
## SP6 lane MERGEDRIVER (2026-10-07)

Delivered on `lane/mergedriver`: the record merge driver (SR-075), intent conflicts with their
card, the owner's choice and the stop-hook, brief and status-card surfaces (SR-076), the merge
report's `unmerged` and `intent_conflicts` sections and the quick merge check at git's
pre-merge-commit, installed by default (SR-077, R17). Notes for Integrate and open items:

- [INTEGRATE] Phase 0 had not run when the lane started, so the lane wrote its own part of
  the coordinator files: `present/owner_text.py` (new in IDS, LOGS and this lane: an add/add
  to join by hand; `bare_cli_verbs` is the IDS lane's version), `contracts.py`
  (`DriverResult`, `IntentConflict`, `StatusSnapshot.conflicts`), `cli.py` (routes and help
  for `merge-driver`, `conflict`, `conflicts`), `boundary/report.py` (`unmerged`,
  `intent_conflicts`, their exits and sections), `boundary/cli.py`
  (`--hook pre-merge-commit`, `--install/--uninstall-pre-merge-commit`), `commands.py`
  (`plumb init` adopts git: driver and quick check), `hosts/claude_code/install.py`
  (`git_adoption`, status lines, the `conflict choose` deny rule), `stop.py`,
  `session_start.py`, `snapshot.py`, `present/render.py`, `present/review.py`,
  `present/cli.py` (`plumb show IC-###`), `validate.py` (text-merged record named in the
  owner's terms) and the `/plumb` command and skill templates.
- [INTEGRATE] `IC` IDs come from `plumb.ids.reserve(kind="conflict")` once the IDS lane is
  merged (the driver calls it when importable); until then the driver uses the highest IC
  this worktree knows (record files, resolution entries in both log layouts, and its own
  `.plumb/cache/ic-reserved.json`) plus one, which is unique within one clone's worktree only.
- [INTEGRATE] R17 says plumb's own repository gets the quick merge check after Integrate:
  `plumb hooks install` now installs it with the driver, and (review round 1) the pre-push
  hook too, where the one full run happens. The quick check holds every merge that touches a
  requirement the owner has not confirmed, and every plumb record is still proposed, so the
  coordinator's own merges will be held until the owner confirms them (or are made with
  `git merge --no-verify`, which bypasses the hook like any git hook). Decide the order
  (install after the lane merges) and tell the owner.
- [MEDIUM] (spec 8.4, deny rules) Claude Code's deny rules match a command prefix, so "deny
  `plumb conflict choose` without `--prompt`" cannot be written. The lane denies
  `conflict choose` entirely and gives the agent `plumb conflict relay` (the relay; `choose
  --prompt ... --quote ...` stays accepted as the spec's form). The owner's terminal path is
  unchanged. Fix: update spec 8.4 and 11 to name `conflict relay` as the agent's form.
- [FIXED, review round 2: HIGH] (R17, spec 10) The pre-merge-commit hook runs only when
  `git merge` commits on its own; a merge stopped by a text conflict and finished with `git commit` is covered only at
  push and by `/plumb merge-check`. Fix: let the commit-msg hook run the same quick check
  when `MERGE_HEAD` exists (one more git call per merge commit, no test run).
- [MEDIUM] (spec 7.2 latency) The driver itself merges a record in a few milliseconds
  (tested under 300 ms in process), but one `python -m plumb merge-driver` process takes about
  0.4 s here, 0.25 s of it the interpreter start and 0.11 s importing `plumb.contracts`. Fix:
  if it matters, let the driver import only `plumb.model`'s helpers without `contracts`.
- [LOW] (git behaviour) When the quick check refuses a merge, git has not yet written the
  merge message, so `git commit --no-edit` aborts with an empty message; the `/plumb`
  command tells the agent to finish with `git commit -m "Merge <branch>"` and the merged
  work's `SR:` trailers.
- [FIXED, review round 1: HIGH] (spec 7.3) A record that already carried an open `conflict`
  block and was merged again with another conflicting change got a new block, losing the
  older block's other version and its IC. `merge_texts` now never replaces an open block:
  when either side carries one and the merge conflicts again (or the two sides carry
  different blocks) it text-merges the file and exits 1, so git leaves it unmerged with both
  versions (SR-076 EX-6).
- [LOW] (relay reader) The choice relay reads the quote with `approvals.objection_clauses`,
  so "use feat-x's instead" is refused ("instead" reads as a change clause); "keep feat-x's"
  works. Conservative by design (R2).
- [LOW] (config) `merge.premerge_run_full` (spec 10, 12) was not added: R17 rules that the
  merge-time check never runs the suite, so the key would contradict the owner. Fix: drop it
  from spec 10 and 12.
- [LOW] (drift) The lane extended files other requirements are implemented by (SR-012,
  SR-015, SR-027, SR-047, SR-061, SR-063, SR-064, SR-066 to SR-068 among them); their links are
  stale until the coordinator reviews and repins them (lanes repin only their own records).

## MERGEDRIVER lane review, round 1 (2026-10-07)

Four HIGH findings fixed on `lane/mergedriver`, each as a class:
- An open intent conflict is never replaced by a merge: `merge_texts` (the one place a
  conflict block is written) refuses with exit 1 when ours or theirs already carries an open
  block and the merge conflicts again, or when the two sides carry different blocks (SR-076
  EX-6; tests for ours, theirs and both).
- No git hook calls a judgment backend or writes the log: `conflicts.conflict_rows(hook=)` is
  the one builder of the merge boundary's conflict cards; the pre-merge-commit check and the
  pre-push report pass `hook=True` (cached judgments only), `/plumb merge-check` and `/plumb
  conflicts` still judge live (SR-077 EX-7; one test per hook).
- The full suite has a hook again: `git_adoption` (init and hooks install) installs the
  pre-push hook with the quick merge check, keeps a foreign one byte-identical and says so in
  plain words; hooks uninstall removes it and hooks status lists it (SR-077 EX-8).
- [INTEGRATE] SR-051 (an SP3 record) said "plumb hooks install does not install it", which
  contradicts R17; the lane restated it (title and statement) for R17. It stays proposed, and
  its links are stale until the coordinator reviews and repins them.

Medium and low findings from the same review:
- [MEDIUM, FIXED with the HIGH above] (premerge.py) The pre-merge-commit hook called
  `conflict_card(core, c)` without `CACHED_ONLY`, so with JEV configured it waited up to 5 s
  per open conflict and appended judgment entries to the log in the middle of the merge. The
  pre-push report path is covered by the same fix.
- [FIXED, review rounds 1 and 2] (install.py) `git_adoption` installed only the pre-merge-commit hook,
  so nothing ran the full suite or caught a leftover conflict block before a push. The
  pre-push hook is now installed by default. Still open: the driver exits 0 on an intent
  conflict, so a rebase, a cherry-pick or `git commit` after a text conflict commits a record
  carrying a conflict block with no hold until push. Fix: run the quick check from commit-msg
  when MERGE_HEAD/REBASE_HEAD exists (see the MEDIUM above on MERGE_HEAD).
- [LOW] (conflicts.py) For a relayed choice, the stated-set check compares only the block's
  stored ours/theirs hash strings, not the field values the card showed. An edit to
  `fields.<name>.theirs` after the card was shown goes unnoticed by `relay_choice` and by the
  stop hook's shown-key. Bounded: the result no longer matches feat-x's hash, so no approval
  re-confirms it. Fix: include a digest of `conflict.fields` in `stated_key`.
- [FIXED, review round 2: HIGH] (premerge.py) The docstring says the check reads "the
  staged merge result", but
  `open_conflicts` and touched-record confirmation read the work-tree record index
  (`core.index()`); only the path list comes from `git diff --cached`. After the owner
  chooses a side (`core.write_record` does not stage), `plumb merge-check` passes and `git
  commit -m ...` records the staged record that still carries the block.
  `test_commit_completes_after_choice` hides this with an explicit `git add -A`. Fix: stage
  the chosen record, or read the staged blobs.
- [MEDIUM] (conflicts.py) `turn_cards` marks a conflict's key as shown in
  `conflicts-shown.json` whatever the display mode, while `write_stated` records conflicts
  only when display == 'owner'. On a stop with display 'unseen', the card is never shown
  again in the session and any relayed choice is refused until a new session or an explicit
  /plumb conflicts. Fix: mark shown only when display == 'owner'.
- [MEDIUM] (owner_text.py, sp6-plan 3.1) Phase 0 never ran, so the lane wrote
  coordinator-owned files (contracts.py, cli.py ROUTES, boundary/report.py, boundary/cli.py,
  commands.py, install.py, stop/session_start/snapshot, present/*, validate.py, templates);
  `present/owner_text.py` is also added independently by the IDS and LOGS lanes. Integrate
  must reconcile the add/add on owner_text.py and the overlapping edits by hand.
- [LOW] (merge.py) `_merge_list` flags a conflict only when both sides removed the same item
  and each added a different one. One side rewriting X to X1 while the other deletes X merges
  clean with X1, silently overriding a deliberate removal in will/wont/assumptions. Fix:
  treat "removed on one side, removed-and-replaced on the other" as a conflict.
- [LOW] (driver.py, spec 7.2 latency) One `python -m plumb merge-driver` process per record
  file costs about 0.4 s against spec 7.2's 300 ms; a merge touching 20 records spends about
  8 s starting drivers. Already recorded above as MEDIUM; noted for Integrate's latency
  checks.

## MERGEDRIVER lane review, round 2 (2026-10-07)

Two HIGH findings fixed on `lane/mergedriver`, as one class. The guarantee: no commit that
records another line's work is made while what it records carries an open intent conflict
(and, for a merge, a touched requirement not yet confirmed, a file no requirement declares
or two records holding one ID); the check judges what git will record. The choke point is
`premerge.check`; its entry points, one test each (`tests/mergedriver/test_commit_hold.py`):
- `git merge` and `git pull` committing on their own: the pre-merge-commit hook (as before).
- `git commit` after a text conflict, after `git merge --no-commit`, and `git merge
  --continue`: the new `prepare-commit-msg` hook, the one hook git runs for every commit
  (a rebase runs neither pre-commit nor commit-msg; verified here with git on Windows). Its
  shell lines exit at once outside a merge, rebase, cherry-pick or revert, so an ordinary
  commit pays no Python start; under `git merge` they leave the check to plumb's
  pre-merge-commit hook.
- Rebase, cherry-pick and revert: the driver now exits 1 on an intent conflict whenever no
  `GITHEAD_*` variable says `git merge` runs it, so git stops on the record; continuing with
  the block still in it is held by prepare-commit-msg (a step is checked for open intent
  conflicts only; its requirements are its branch's business until the branch merges).
- What is checked is what is committed: the check holds while any `.plumb/` file differs
  from the index being committed (`git status` reads the `GIT_INDEX_FILE` git hands the
  hook) or a record file cannot be read (a text merge left in it). A choice made during an
  operation (`conflict relay` or `choose`) stages the record and `.plumb/log`, and the
  `/plumb` template's "finish the merge" stages `.plumb` before the check and the commit.
- `plumb init`, `plumb hooks install` and `merge-check --install-pre-merge-commit` install
  both hooks; uninstall and hooks status cover both; a foreign prepare-commit-msg is kept
  (`hook_lines` in `--json`). Spec 8.2 and 10 carry a lane note; SR-077 gains EX-9 and EX-10.

Notes for Integrate and open items from round 2:
- [INTEGRATE] git has no `--no-verify` for prepare-commit-msg. The coordinator's own merges
  finished by hand (text conflicts in shared files) are held while their records are
  unconfirmed; `git -c plumb.mergeHold=false commit` (or `merge --continue`) bypasses the
  hold for one command, like `git merge --no-verify` for the pre-merge-commit hook.
- [MEDIUM] (conflicts.py) `turn_cards` records a card as shown (`conflicts-shown.json`)
  whatever the display mode, while `write_stated` stores conflicts only when display ==
  'owner'. After an 'unseen' stop the card is never shown again in that session, and a
  relayed choice is refused ("card was not shown") until the owner runs /plumb conflicts.
- [MEDIUM] (hosts/claude_code/install.py, spec 8.4 and 11) The plan (D6, the deny-rule test)
  denies `plumb conflict choose` only without `--prompt`; the lane denies `conflict choose`
  entirely and adds `plumb conflict relay`, which the spec does not have. The safety holds
  (`choose_owner` calls `require_owner`), but an agent following spec 8.4's form is blocked.
  Update spec 8.4 and 11 at Integrate.
- [MEDIUM] (driver.py, spec 7.2) One `python -m plumb merge-driver` process takes about
  420-470 ms here (interpreter start plus about 90 ms importing `plumb.contracts`), against
  7.2's 300 ms per file; the test bounds the process at 2 s only. A merge where both sides
  changed 20 records spends about 8-9 s starting drivers.
- [LOW] (merge.py) `_merge_list` reports a conflict only when both sides removed the same
  item and each added a different one: base wont [X], ours [X1], theirs [] merges clean to
  [X1], silently overriding the deliberate removal.
- [LOW] (conflicts.py) In a rebase, `named_takes` maps "mine"/"ours" to the ours side, which
  is the upstream being rebased onto, not the owner's feature branch; with no usable label
  the sides fall back to short hashes. "keep mine" during a rebase of feat-x onto main can
  apply main's version. Follows spec 8.4 to the letter, against what the owner likely means.
- [MEDIUM] (conflicts.py, R17.1, R8 B) `relay_choice` accepts a bare affirmation ("ok",
  "yes") as choosing the combined version, though the card offers three choices; a bare
  assent picks among options. Fix: for combined, require "combined" in the named takes.
- [MEDIUM] (driver.py) `reserve_ic` swallows every exception from `ids.reserve` (IdBusy after
  the CAS retries, or a TypeError: spec 12's `reserve(paths, kind, count)` has no `local=`)
  and falls back to this worktree's highest IC plus one; ICs live only inside record files
  and log entries, so the IDS seeding (by file name) never sees another branch's ICs. Two
  worktrees can both write IC-004, and a relayed choice can apply to the wrong record. Fix:
  fail loudly (exit 1) on IdBusy and pass or seed the known ICs explicitly.
- [MEDIUM] (templates/plumb-command.md, R2, spec 8.4) For a record left in text-merge form
  (UNPARSABLE, or STILL_OPEN), the template applies "keep mine/theirs" with `git checkout
  --ours/--theirs` and `git add`, skipping the relay's guarantees (logged owner prompt, card
  in the stated set, a quote naming one side). An agent can discard an open IC block (the
  only copy of an earlier side's intent) with no owner words logged.
- [MEDIUM] (Phase 0, plan 3.1) The lane wrote coordinator-owned files (contracts.py, cli.py,
  boundary/report.py, validate.py, the host hooks and templates, a new present/owner_text.py
  that IDS, LOGS and AWARENESS also add) and edited coordinator-owned records (SR-051
  restated, a DEC-021 pin). At Integrate, expect add/add on owner_text.py and conflicts in
  report.py and contracts.py; a careless hand-merge can drop `intent_conflicts` or
  `unmerged` from `exit_code`, silently disabling the exit-4 hold at pre-push.
- [LOW] (premerge.py latency) The quick check run by hand during a real in-progress merge
  in a scratch clone: warm 1.4 s, first cold run 5.6 s (interpreter start and imports on
  Windows). Inside R17's "seconds" when warm; the first merge after a reboot or venv sync
  blocks about 5 s. The new prepare-commit-msg hook adds no Python start outside a merge,
  rebase, cherry-pick or revert.
- [LOW] (DEC-021) Its chosen text still says "the optional pre-merge-commit hook", but init
  and hooks install now install it by default (R17); SR-051 was restated, DEC-021 was not.
- [LOW] (conflicts.py) `turn_cards` writes `conflicts-shown.json` for every card it renders,
  even when the stop hook's display is 'unseen'; such a card is never shown again
  automatically in that session and a relay is refused (same root as the MEDIUM above).
- [LOW] (gitconfig.py, plan, spec 12) `mergedriver.install(root, launcher: str)` takes a
  string where the contract says a Launcher (a phase-0 call site written to the spec would
  put a repr in the driver command); the module is `gitconfig.py`, not the plan's
  `mergedriver/install.py`; `merge.premerge_run_full`, dropped per R17, is still named in
  spec 10 and 12.
## SP6 lane AWARENESS (2026-10-07)

Built: sp6 9 (SR-078, SR-079) and ruling R17's early intent conflicts (new proposed records
SR-080 "Intent in flight is shared through refs/plumb/claims" and SR-081 "Intent conflicts
are caught at capture, before any implementation", FEAT-006, derived from INT-022). Nothing
unfinished in the lane's rows A1 to A6. Medium and low findings:

- [MEDIUM, Integrate] Phase 0 had not run when this lane started, so the lane wrote its own
  call sites in coordinator files: `contracts.py` (`Overlap`, `StatusSnapshot.overlaps`,
  `overlap_labels`, `conflicts`, `ClarifyView.inflight`), `config.py` (`AwarenessConfig`),
  `cli.py` (route `inflight` and its help line), `commands.py` (`plumb status` section and
  `--json` `elsewhere`), the four hooks, `snapshot.py`, `present/render.py`
  (`overlap_parts`), `present/report.py`, `capture/capture.py` and `capture/clarify.py`
  (the R17 choke points), the `/plumb` command template and the plumb-clarify skill
  template. `present/owner_text.py` was created by IDS, LOGS and this lane separately
  (add/add at merge): keep one `bare_cli_verbs` and the union of the constants. `plumb
  init`'s commented `config.yaml` does not list the `awareness` keys yet (LOGS owns that
  hunk of `commands.py`).
- [MEDIUM] The early intent-conflict check runs at `plumb capture` and `plumb clarify`
  (R17 names those two). `plumb new`, `plumb intent`, `plumb example` and `plumb decide`
  write records without it: their records are claimed in `refs/plumb/claims` by the stop
  hook (any writer, one choke point) and the overlap line reaches the agent, but no early
  card is shown. Routing those commands through `early.after_capture` would close it.
- [MEDIUM, Integrate] Editing the shared files above left other requirements' links stale
  (`plumb validate`: 66 warnings, 0 errors), e.g. SR-017, SR-026, SR-034, SR-043, SR-061 to
  SR-063 on `config.py`, `contracts.py`, `capture.py`, `clarify.py`, the hooks. The lane
  repinned only its own SR-078 to SR-081; the rest wait for review at Integrate.
- [LOW] `awareness/inflight.py` has its own compare-and-swap helpers for
  `refs/plumb/claims`; IDS's `ids/ref.py` does the same for `refs/plumb/ids`. Fold them into
  one ref module after both lanes merge.
- [LOW] A claim recorded on the default branch clears as soon as a commit lands there (the
  branch tip moved and is trivially reachable); other branches then meet that intent at
  merge through the record merge driver.
- [LOW] The warm overlap check measures about 30 ms for five worktrees (budget 50 ms): the
  register is read twice per prompt (`claim_overlaps`, `raised_lines`) and
  `gitfiles.current` runs three times. Memoize per hook call if it gets close.
- [LOW] The same-record early card says "the same requirement is being changed on both
  branches"; with JEV configured it could add the advisory compatibility line the merge
  card has. The feature-overlap card already shows it.
- [LOW] `StatusSnapshot.conflicts` is not filled by this lane (MERGEDRIVER's
  `open_conflicts`); an early conflict counts as a question and a proposed record.
- [LOW] Spec 9.4 keys the stop hook's owner line like the prompt delta's agent line, so a
  record the prompt hook already named to the agent this session is not repeated to the
  owner at the stop; the owner still sees the status card's "N also changed on <branch>".
- [LOW] `record_claim` prunes merged claims with one `git merge-base --is-ancestor` per
  moved claim tip, cached, without the hook's deadline (the stop hook starts it only with
  0.4 s left).
- [LOW, pre-existing] `tests/host/test_latency.py::test_intent_lines_survive_cpu_contention`
  fails on `main` as on this branch (LOGS lane's note above). `present/report.py`'s "awaits
  you" line and the session brief's triage line still name bare `plumb confirm`/`plumb
  triage` (R14, not SP6 text).
- [R14 matrix, Integrate] New owner entry points: "what are the other branches working on?"
  (`plumb inflight`), "drop that work" (`plumb inflight drop <branch>`), "is anyone else
  changing X?" and `/plumb status` (overlaps), the early conflict card's answer ("keep
  feat-x's", "keep this one", "both") relayed like any decision.

## SP6 lane AWARENESS, review round (2026-10-07): medium and low findings

The four HIGH findings of this round are fixed on `lane/awareness` (a claim clears exactly
when its branch merges; the owner's answer is stored and shown branch-neutrally; "the same
version" means the same record hash). These were recorded, not fixed:

- [MEDIUM] `awareness/early.py` `check_text` (the clarify read-back) turns any record the
  request names, or relevance-matches at score >= 1.0, into a deterministic conflict card
  when another branch claims it, without asking JEV whether the request changes that record.
  A merely related or compatible mention should get only the one-line warning (R17, R18.4).
  Probe: feat-x claims SR-005; on main, `clarify('add a status card colour; do not touch
  SR-005')` returns `conflicts=[('SR-005', '')]` and the skill says to ask it first.
- [MEDIUM] Same function, second reading: it also skips the same-version check and raises
  the depth from trivial to incremental, so a request that only mentions a claimed record
  ("add a test for the relay checks") asks the owner "which one, or both?", against R11's
  "ask only questions that change what gets built".
- [MEDIUM] `awareness/publish.py`: when HEAD moved, `publish()` replaces `pending` with only
  this turn's `changed_paths`, so uncommitted edits from earlier turns drop out of
  `changing.json` and other worktrees stop being warned about them (turn 1 edits SR-005
  uncommitted; turn 2 commits other files and touches SR-006; SR-005 disappears).
- [MEDIUM] `contracts.py` and the other coordinator-owned files: the lane edits
  `contracts.py`, `config.py`, `cli.py`, `commands.py`, `capture/capture.py`,
  `capture/clarify.py`, the hooks and `present/*`; plan 3.1 gives AWARENESS only
  `src/plumb/awareness/**` and `tests/awareness/**`. With phase 0 not on main, the IDS,
  LOGS and MERGEDRIVER lanes add overlapping wiring (StatusSnapshot fields, `Overlap`,
  `config._NESTED`, the hooks): expect textual conflicts or duplicated fields at Integrate.
- [MEDIUM] `.plumb/requirements/SR-080.md`, `SR-081.md`: the lane created two records,
  which plan 3.1 and section 1 reserve to the coordinator. IDS reservation is not merged, so
  a parallel lane (MERGEDRIVER for R17's merge hold, IDS for renumbering) could take SR-080
  from local numbering and collide add/add at Integrate.
- [MEDIUM] `awareness/early.py` `raise_conflicts` creates the DEC with `chosen` already set
  to this branch's version, so a bare "ok" or a relayed confirmation picks this branch's
  side although the card asks "which one, or both?": the default comes from the agent, not
  from the owner's choice.
- [LOW] `awareness/early.py`: two branches capturing the same record within the window
  between `check_records` and `record_claim` each raise a DEC (neither sees the other's
  conflict entry yet), so the conflict is asked twice instead of once.
- [LOW] `capture/capture.py`: if `after_capture` raises anything but `InflightBusy` after
  `raise_conflicts` wrote DECs, `_inflight_check` returns `written=[]`: the DECs exist but are
  not in the capture's written list or its intent set, and the capture reports "intent in
  flight not checked".
- [LOW] `awareness/turn.py`: the stop hook's register write is gated only by the initial
  0.4 s check; `update()` then retries for up to 3 s, each git call has a 5 s timeout, and
  the merged check inside `record_claim` (and now `refresh`) ignores the deadline. Two
  sessions stopping together on the two-core machine can exceed the 2 s guidance.
- [LOW] `awareness/inflight.py`: a claim on the default branch clears as soon as any commit
  lands there (another branch's merge included) while the main worktree's captured intent
  is still uncommitted; main's claim then disappears for every other branch.
- [LOW, residual of the merge fix] A branch whose own commits were made with no plumb write
  after them (no capture, no stop hook on that branch: commits from a bare terminal) and
  that is then merged by FAST-FORWARD keeps its claim until the branch is deleted or the
  work dropped (`plumb inflight drop`): the graph alone cannot tell that fast-forward from a
  branch fast-forwarding to `main`, and the second must keep its claim. A `--no-ff` merge,
  or any plumb write on the branch after its commits, clears it.

## SP6 lane AWARENESS, review round 2 (2026-10-07): medium and low findings

The two HIGH findings of this round are fixed on `lane/awareness` (a branch holds each
record in one claim, at the version it wrote last; a branch the default branch has
taken whole has nothing committed in flight, so its claim does not come back). These
were recorded, not fixed:

- [MEDIUM] `capture/capture.py`: capture runs the R8 B auto-approval gate on `written`
  before `_inflight_check`, so a new requirement that JEV judges to contradict another
  branch's intent in flight can be auto-confirmed in the same capture; the owner is asked
  the early-conflict DEC only afterwards ("asked immediately, before anything" does not hold
  for auto-approved records). Scenario: auto-approve on with a passing calibration; feat-x
  claims FEAT-002 with "A relay confirms a group"; on main the owner's words support "A
  relay confirms one record at a time"; `gate()` confirms the new SR, then `after_capture`
  judges it "contradicts" and raises a proposed DEC. If the owner later picks feat-x's
  version, a confirmed requirement contradicts the decision.
- [MEDIUM] `awareness/early.py` `check_text` (the clarify read-back) treats any record that
  `core.relevant()` ranks at score >= 1.0 as "the same record being changed": it shows a
  deterministic Conflict card and raises the depth from trivial with no JEV judgment,
  although R17 reserves the deterministic path for the same record actually being changed.
  Scenario: feat-x claims SR-005 "relay checks"; on main the owner asks for something that
  only mentions relays (a docs typo near the relay wording); clarify shows the Conflict card
  and "ask this conflict first": an intent question nobody raised.
- [MEDIUM] `awareness/inflight.py`: every writer prunes the shared register through
  `active()` inside the CAS mutate, and a claim whose branch is missing from
  `gitfiles.branch_tips` is dropped for every worktree for good. `branch_tips` reads
  packed-refs first and then the loose refs, so a concurrent `git pack-refs` or `gc`
  (packed-refs read before the rewrite, loose ref deleted before the walk) makes a live
  branch look deleted, and its claim and raised-conflict answers are lost.
- [MEDIUM] `awareness/inflight.py` `merged()`: a fast-forward merge clears a claim only when
  its `own` field holds the branch's own commit (set by `record_claim`, or by `refresh` in
  the stop hook after a commit). A branch whose commits were made outside a plumb session
  (CLI commit, no Stop hook) keeps `own=''` and `base` at the claim; after
  `git merge --ff-only feat-x` its commits sit on main's first-parent line, so the claim
  never clears until the branch is deleted, and other branches keep raising or naming
  conflicts for work that has landed (extends the round-1 residual note).
- [LOW] `capture/capture.py` and the coordinator-owned files: the lane edits
  `capture/capture.py`, `capture/clarify.py`, `cli.py`, `commands.py`, `config.py`,
  `contracts.py`, the `hosts/claude_code` hooks, templates and `present/render.py`, while
  plan 3.1 gives AWARENESS only `src/plumb/awareness/**` and `tests/awareness/**`. R17's
  wiring was added to this lane's task with no recorded coordinator contract change, so
  expect textual conflicts at Integrate with MERGEDRIVER's or the coordinator's phase-0
  edits to `stop.py`, `session_start.py` or `contracts.py`.
- [MEDIUM] `awareness/publish.py`: `note_edit` (the async post-edit hook) and `publish`
  (stop and session start) both read `changing.json`, modify it and write it back with no
  coordination. Both are atomic replaces, so an edit path that lands between the stop hook's
  read and its write is lost from `pending`, and other worktrees stop hearing that the record
  is being edited until the path is published again.

## SP6 Integrate (2026-10-07)

Merged on `main`: LOGS (39cbe73), the migration of plumb's own logs (6957d1b: 528 legacy
lines, digests and `prev` unchanged, `plumb status --json` identical before and after),
IDS (50c4d62), MERGEDRIVER (d4aec25), AWARENESS (3f978d5), then the e2e test, the hooks and
the docs (882e53c). Phase 0 never ran: each lane wrote its own part of the coordinator's
contracts, routes and `owner_text`, and the merges joined them.

- [MEDIUM] (merge report, stale links from an intent conflict) A record the driver leaves
  in an intent conflict no longer matches its links' pins, so `merge-check` holds the merge
  with exit 1 ("links of touched requirements hold the merge") before the conflict card's
  exit 4. The agent's repin pins the conflicted content, and the owner's choice makes the
  links stale again. Fix: report links whose source holds an open intent conflict under
  that conflict, not as stale holds, and repin them when the choice is recorded. The e2e
  test (`tests/integration/test_parallel_e2e.py`) repins after the merge and asserts exit 4.
- [MEDIUM, R14, pre-existing SP3 text; for the review phase to grade] The merge report and
  its gates still name bare commands that reach the owner (the pre-push hook prints the
  report at `git push`): "merge waits for your confirmation: `plumb approve ...`", "review
  the change, then plumb repin SR-001#3" (`boundary/gates.py`), "+N more (plumb merge-check
  --json)", "(plumb fidelity SR-...)", "(plumb tests run --nodes <id>)", "(plumb spec show
  ...)", "`plumb approve --exempt`". Fix: route every merge-report line through
  `present.owner_text` with one `bare_cli_verbs` test per surface, as SP6 did for its own
  sections.
- [LOW] (find_root) A stray `C:/.plumb/` (created 10:39 by an earlier test run, holding
  only `cache/changing.json`) made `plumb init` in a fresh repository under the temp
  directory resolve to `C:/`, because `find_root` prefers any ancestor `.plumb/` over a
  nearer `.git`; the first e2e run wrote record folders there. The directory was removed.
  Fix: stop the upward `.plumb/` search at the first `.git`, and make `.plumb/cache`
  writers refuse when no root was found.
- [LOW] (log integrity, line endings) `merge.log_integrity` compares entry files by blob, so
  a CRLF-only rewrite of an entry (a Windows clone checked out with `core.autocrlf=true`,
  then switched to `false`) is reported as "entry modified" although its digest is
  unchanged. The IDS test helper `clone` did exactly that; it now clones with
  `core.autocrlf=false`. Fix: for an `M` entry, compare the parsed digest before reporting.
- [LOW] (signature drift between lanes) IDS changed `merge.touched_requirements` to take
  `(commit, message)` pairs; MERGEDRIVER's `boundary/premerge.py` still passed messages and
  crashed the quick merge check on every held merge. Fixed at Integrate; the frozen phase-0
  contract would have caught it.
- [LOW] (tests) `test_intent_lines_survive_cpu_contention` prompted "ok, and SR-002 needs
  work", which the audit-round-5 scoping rightly reads as an objection; it now says "ok,
  confirm SR-002". `tests/logs/test_single_writer.py` lists `ids/mergefix.py` (it only
  stages entries). `test_template_steps_commit_the_choice` looks for the committed
  `conflict-resolution` entry file.
- [LOW] (owner_text) MERGEDRIVER and AWARENESS each defined the status card's conflict
  wording; `CONFLICTS_CARD_PLURAL` is now an alias of `CONFLICTS_CARD_MANY`, and the status
  card draws both overlap and conflict parts from `render.overlap_parts` only.
- [LOW] (test economy) pytest-xdist is not installed, so `-n 2` is unavailable: the focused
  sets took 5 to 8 minutes each and the single full run is serial.
- [LOW] (lane helpers) Each lane carries its own `tests/<lane>/gitrepo.py`; the phase-0
  `tests/gitrepo.py` was never written. Fold them into one helper.
- [NOTE] R17 (later than plan 8.2) installs the quick merge check on plumb's own repository
  after Integrate: `plumb hooks install` wrote the record merge driver, pre-merge-commit,
  prepare-commit-msg and pre-push hooks beside commit-msg. `plumb ids sync` seeded
  `refs/plumb/ids` (DEC 22, FEAT 6, INT 22, NC 3, SR 81). `plumb repin --all-stale` (with a
  note; never a confirmation) refreshed the 205 pins the lane merges and earlier work left
  stale, as the LOGS lane's follow-up asked.
- [LOW] (R14 matrix) No feature -> owner entry point matrix document exists on `main` yet
  (an R14/SP7 deliverable); the SP6 rows live in spec 11 and in the AWARENESS lane's note
  above. Fold them into the matrix when it is written.
- [NOTE] The single full run (`plumb merge-check 89f499b`, run 20261007T032404Z-f69bfd3a,
  serial, 28 min 49 s): 1311 tests, 1307 passed, 4 failed, all real cross-lane or stale
  expectations, none flaky: `test_every_route_names_a_module_path` (the SP6 routes),
  `test_no_module_computes_record_numbers_outside_store_and_ids` (the driver formatted and
  computed `IC` numbers itself; it now goes through `ids.format_id` and `ids.local_next`,
  the one allocator), `test_only_log_py_writes_under_plumb_log` (`mergedriver/conflicts.py`
  only stages entries) and `test_explain_by_id` (stale since audit round 2: an unchecked
  quote is not called "your words"). Per the failure policy the failed tests plus the
  covering modules reran with evidence (run 20261007T033517Z-bd1ea609: 132 passed). Those
  fixes touch modules most tests import, so the full run's evidence is now stale on the
  current tree and `plumb merge-check` reports exit 5 (unverified acceptance tests) besides
  exit 4 for the 134 proposed records; the next full run is the pre-push hook's.

## SP6 audit: early intent conflicts in two real worktrees (2026-10-07)

The audit exercised the real CLI and hooks in scratch repositories with parallel worktrees
and merges carrying an intent conflict. Its five HIGH findings were fixed in the same change
as one class each: the owner's answer to an early conflict card is recorded through one
choke point (`plumb.awareness.answer`: `plumb conflict relay|choose DEC-###`, the capture,
clarify, stop-hook and /plumb conflicts cards; a plain `relay` naming the other version is
refused); a merge-time conflict between the two versions a confirmed early decision chose
between is settled by that answer (`answer.apply_settled` in the quick merge check and
/plumb conflicts, the card says "already answered"), and the owner's pick on a merge card
answers a still-open early decision; only a confident JEV verdict may say "judged
compatible" (`early.overlap_line`). The medium and low findings below were not fixed.

- [MEDIUM] (SP6 audit, stop hook) `stop.handle` returns before `at_stop` when the turn
  changed no file, so `inflight.sync_decisions` never runs for a turn whose only change is
  the owner's answer. The new early-answer path (`answer.record_answer`) now syncs the
  register itself, but an answer confirmed through plain `relay` ("ok") or `approve` still
  reaches the other lanes only after a later turn changes a file (or `plumb inflight sync`).
  Fix: run `inflight.sync_decisions` on every stop (it is cheap and writes only on change),
  or call it from `relay` and `approve` after an approval of a DEC a claim references; add a
  hook-level test (relay, stop, the other worktree's prompt line says "settled"). Reported
  twice by the audit.
- [MEDIUM] (SP6 audit, early.py) One DEC per branch pair: with three lanes changing SR-001,
  capture raised two pairwise decisions (and printed "asked once for every branch" twice),
  and the owner could answer them inconsistently. Fix: one open conflict DEC per record that
  lists every in-flight version as an option; a later lane joins it as a new alternative.
- [MEDIUM] (SP6 audit, awareness) Stale awareness after a merge: feat-b's prompt hook still
  warned that SR-001 "is also being changed on branch feat-c" after feat-c merged, and an
  early DEC raised against a merged branch was still listed. Fix: base the overlap scan on
  the merged-branch test the claims use; retarget or supersede an early DEC whose
  counterpart merged (its question then reads "main's version"). Partly addressed: the
  quick merge check no longer lists an early DEC beside the open conflict card on its record.
- [MEDIUM] (SP6 audit, R14, pre-push) The pre-push hook output (`merge-check --hook
  pre-push`) still gives shell instructions and internal IDs: "merge waits for your
  confirmation: `plumb approve SR-001 SR-003 DEC-001`, or say ok in the session", "push with
  --no-verify to bypass the hook", "(plumb tests waive --merge <sha> --reason ...)", "plumb
  link SR-001 implemented_by app.py". The pre-merge-commit path already says "/plumb confirm
  <title>". Fix: route the merge report's confirmation and refusal lines through
  `present.owner_text` ("/plumb confirm <title>", "say 'waive the full run'"), drop the
  --no-verify hint from owner text. R14 is SP7 scope (R18); reported three times.
- [MEDIUM] (SP6 audit, merge-check) A confirmed early DEC whose chosen side differs from
  the record's merged content (the owner answered the merge card differently) passes the
  quick check and surfaces only as a stale link in `plumb drift`. Fix: treat it as an open
  intent conflict in merge-check and cite the early answer on the merge card. (A merge
  meeting exactly the two versions the DEC chose between is now settled by it.)
- [LOW] (SP6 audit, pre-push range) The first push of a ref new on the remote checks
  `<HEAD>..HEAD` ("touched requirements: none"), so confirmations and claims of the merged
  work are never verified at push. Fix: for a new remote ref, take the base from the remote
  default branch's merge-base, or the root commit when the remote is empty. Reported twice.
- [LOW] (SP6 audit, init) `plumb init` in a fresh repository installs pre-merge-commit,
  pre-push and prepare-commit-msg but no commit-msg hook (the SR-trailer check). R15 is SP7
  scope: install it in init, or record it with the plugin work.
- [LOW] (SP6 audit, spec drift) docs/specs/sp6-parallel-work.md section 10 still says the
  pre-merge-commit hook runs the full suite unless `merge.premerge_run_full: false`; the
  implementation follows R17 (no test run). Fix: drop that sentence and state that the hook
  never runs tests.
- [LOW] (SP6 audit, inflight summary) An update-only capture (no INT, no new SR) records an
  empty claim summary (`feat-b: "" (SR-001 ...)`). Fix: fall back to the updated record's
  title or new statement.
- [LOW] (SP6 audit, README) "Logs never conflict" says each prompt is a small file under
  `.plumb/log/<kind>/`; prompts live in the untracked `.plumb/session/prompts.jsonl`. Fix:
  say prompts are local session state and keep the per-entry claim for the tracked logs.
- [LOW] (early-answer fix, clarify) `early.check_text` matches a request only against this
  worktree's records, so a request about a requirement that exists only on the other branch
  (a new SR there) is not checked at read-back; capture still checks it by feature. Fix:
  also match the request against the claimed records' words (term overlap) before judging.
- [LOW] (early-answer fix, merge driver) A settled conflict is applied by the quick merge
  check after git wrote the merge tree, so the merge is held once and "finish the merge"
  records it. Settling inside the record merge driver (reading the confirmed decision from
  both sides) would let the merge commit on its own.
- [LOW] (flaky, seen once) `tests/present/test_present_confirm.py::
  test_relayed_ok_then_confirms_exactly_the_shown` failed once inside a larger focused run
  (the prompt hook listed FEAT-001 and FEAT-002 beside SR-010, as if the stop hook had seen
  the uncommitted fixture records as this turn's changes) and passed on rerun, alone and in
  the same set. It depends on file times against the turn start. Fix: commit the fixture
  records before the turn, or start the turn after writing them.

## SP6 audit 2: fast-forwards, the default branch and idle worktrees (2026-10-07)

The second audit drove `plumb init`, two parallel worktrees and merges carrying an intent
conflict through the real CLI and git hooks. Its four HIGH findings were fixed as one class
each, at one choke point with one test per entry point:

- a merge into the default branch that git would fast-forward is held: `plumb init` and
  `hooks install` set `branch.<default>.mergeoptions` to `--no-ff` (`premerge.ff_hold`), so
  a plain `git merge` or `git pull` records a merge commit the quick check holds, and the new
  post-merge hook runs the same check after an explicit fast-forward (`--ff-only`,
  `pull.ff=only`) and puts the default branch back (`git reset --keep`) when it holds
  (`tests/mergedriver/test_fast_forward.py`);
- every early-conflict card is built by `answer.card_conflict`: on a branch that is neither
  side both versions are labelled by branch from the decision's pinned words (or the live
  claims), "this one" and "theirs" are refused there (`relay`, `choose`), and a decision
  whose record a merge left in conflict is asked by that merge card alone, its relay routed
  to it (`tests/awareness/test_early_off_side.py`);
- every claim goes through `early.claim` (capture, the stop hook's `claim_changes` after a
  direct edit or `plumb new`, `plumb inflight sync`), which runs the same-record check and
  raises the decision once with its card; a read-back card answered before anything is
  written is raised as its decision at the answer (`answer.raise_shown`)
  (`tests/awareness/test_claim_check.py`);
- another worktree whose HEAD or branch moved since it last published counts for nothing
  once the default branch holds that HEAD (`publish.moved_since`, `publish.contains`), for
  every reader (`tests/awareness/test_idle_merged.py`).

Residuals of the fixes, not fixed:

- [MEDIUM] (audit 2, fast-forward) A move of the default branch that is not a merge (`git
  rebase feat-x` or `git pull --rebase` on main, `git reset --hard feat-x`, `git
  update-ref`) still goes unchecked: git runs no merge hook for them, and a
  reference-transaction hook costs about 0.5 s per checkout on this machine (measured), too
  much for every ref update. The pre-push hook still checks the pushed range. Fix candidate:
  a `/plumb` route that does those moves through `git merge --no-ff`.
- [LOW] (audit 2, fast-forward) With `branch.<default>.mergeoptions=--no-ff`, a `git pull`
  of a collaborator's main into main records a merge commit even when it could
  fast-forward. The owner can set `--ff` there (plumb keeps an owner's own option, and the
  post-merge hook still checks the fast-forward).
- [LOW] (audit 2, early check at the stop hook) The stop hook judges a new record in a
  feature another branch claims with the hook-mode backend; with JEV configured that is one
  call of up to its hook timeout per new record. Records changed elsewhere are matched
  deterministically and never judged.
- [LOW] (audit 2, stop hook question) `stop._dec_question` still tells the agent the owner
  may answer "keep this one" for an early decision; off both branches the relay refuses
  those words and names the branches to use, so nothing is recorded wrongly, but the line
  could name the branches instead.

The audit's medium and low findings, recorded without fixing:

- [MEDIUM] (audit 2, R17, relay / stop.py, prompt.py) After the owner answered DEC-001 with
  "keep feat-a's" on feat-b, feat-b's SR-001 still held the losing wording (mod 256); the
  next prompt hook ("carry on") and the stop hook gave the feat-b agent no signal that its
  own record now contradicts the owner's answer (only the relay's one-time output said so).
  The lane can build the rejected behaviour for the rest of the session; the merge restores
  the record from the earlier answer, but code built meanwhile drifts. Fix: in the prompt or
  stop delta, when this worktree's version of a record differs from a settled early answer
  that chose another branch's version, emit one line telling the agent to adopt the chosen
  wording first; once, deduplicated by hash (R9).
- [MEDIUM] (audit 2, Decision 5, early card rendering) After feat-a fast-forwarded into main,
  `/plumb conflicts` and the stop hook showed a second card next to IC-001 whose two sides
  were identical ("feat-a: add(a, b) returns min(a + b, 100) ... / this work: the same"): a
  meaningless question. The root cause (a claim surviving a fast-forward) is already a
  MEDIUM above; the spurious owner question was not. Fix: suppress an early card whose two
  sides have the same hash or text; when the record is also under an IC, show only the IC
  card noting it also answers the decision. (Partly addressed by the HIGH fix: a decision
  whose record holds an open merge conflict is now asked by that card alone.)
- [MEDIUM] (audit 2, R9 and R17, clarify.py / early.check_text) `plumb clarify "Make add
  wrap around modulo 256 instead of overflowing."` and `plumb inflight check` with the same
  words found no conflict ("terms no record covers: add"), although `plumb resolve add` maps
  those words to SR-001 at score 1.00 and feat-a had SR-001 in flight; the read-back check
  fired only when the request named SR-001 or echoed its title (capture still caught it).
  Fix: use the `plumb resolve` resolver with per-term matching in the clarify early check.
- [LOW] (audit 2, R14, README Quickstart step 3) The README says "This build has no `plumb
  new` command", but `plumb new` exists and works; the Quickstart and "At a merge boundary"
  still give the owner `uv run plumb ...` commands. Fix: remove the stale sentence; leave the
  R14 rewrite of owner docs to SP7.
- [MEDIUM] (audit 2, R17, early.check_text) In two fresh worktrees, feat-c captured
  "Reminders are delivered by email only" (a new SR in FEAT-001); on feat-d, `plumb clarify
  "Reminders must never be sent by email, only by SMS"` did not mention feat-c, flagged
  feat-a and feat-b (an unrelated timing change) and set "depth: escalated (contradicts
  confirmed SR-001)", a spurious contradiction; capture later caught the overlap only as
  "could not be judged (0.60)", with no card and no DEC. Already recorded as LOW and MEDIUM
  above; consider raising its priority. Fix: match the request against other branches'
  claimed records' words before judging; reserve the deterministic "contradicts" depth for
  the same record actually being changed.
- [MEDIUM] (audit 2, R15, init) In a fresh repository `plumb init` installed
  pre-merge-commit, pre-push and prepare-commit-msg (now also post-merge) plus the merge
  driver, but no commit-msg hook; a commit with no SR trailer went through. Already a LOW
  above. Fix: install the commit-msg trailer hook in init with the merge hooks, or carry it
  explicitly into the SP7 R15 lane.
- [LOW] (audit 2, R17, early.raise_conflicts) The early DEC is written with `chosen:
  feat-b's version` (the raising branch's side) before the owner answers, so every view
  before the answer (plumb show, the brief) shows a choice the owner never made. Already a
  MEDIUM above. Fix: write early DECs with no chosen side ("awaiting your choice") until the
  owner's words pick one.
- [MEDIUM] (audit 2, R9 and R17, early.check_text word resolution) In wtD, `plumb clarify
  "subtraction must allow negative results"` reported "no record covers it yet" and no
  conflict although feat-c had SR-002 "subtract numbers" in flight; the record's own words
  ("change subtract numbers so negative results are allowed") produced the card. An
  inflection ("subtraction" against "subtract") silently disables the read-back's early
  check. Fix: normalize word stems in record resolution, or fall back to the claims of the
  touched feature and the records the agent then edits (the stop hook's claim check now
  catches the edit itself).
- [MEDIUM] (audit 2, R10.5, merge-check --hook pre-push base selection) The first push of
  main to an empty bare remote read "07d2773..HEAD plus uncommitted changes", "touched
  requirements: none", "approvals in range: none": the base was HEAD itself, so the
  confirmations, claims and approvals of every pushed commit went unchecked; only the full
  run ran. Already a LOW above. Fix: for a new remote ref (zero oid) use the merge-base with
  the default branch, or the root.

## SP6 audit 3: a merged branch that goes on, the losing lane, example labels (2026-10-07)

The third audit drove two parallel worktrees, a `--no-ff` merge and a merge with an intent
conflict through the real CLI and hooks. Its three HIGH findings were fixed as one class
each, at one choke point with one test per entry point:

- a claim clears record by record once that record landed (R17: "A claim clears when its
  branch merges"): `inflight.active`, the one reader every surface uses, drops a claimed
  record when the default branch holds exactly its version (same hash, one `git cat-file
  --batch`, cached) or when the commit stamped as writing it (`commit`, stamped when the
  claim moves to a tip holding that version) is reachable from the default branch; when
  `refresh` moves a claim to a new tip it drops the committed records the branch no longer
  changes since its merge base (`changing.json`), so a branch merged with `--no-ff` and then
  continued never asks main a made-up question
  (`tests/awareness/test_merged_continued.py`: capture, the clarify read-back, the stop
  hook's claim, the brief and status; one test per way a merged record is recognised);
- the losing lane is told (R17: "both lanes build on it"): `answer.superseded` finds every
  record of this checkout whose words differ from the version the owner chose in a
  confirmed early decision (held here, or carried by another branch's claim); the prompt
  delta and the stop hook name it on every turn, status lists it, and a relayed "ok" of it
  is refused naming the decision, until the record matches the answer
  (`tests/awareness/test_early_losing_lane.py`);
- an intent card labels each example with its own requirement's confirmation state, never
  the anchor intent's (`contracts.example_groups`, used by the capture card and the
  presented card; `tests/capture/test_capture.py`, `tests/present/test_intent_card.py`).

Medium and low findings, recorded and not fixed:

- [MEDIUM] (audit 3, R17, stop hook block reason for an early conflict found on the Edit
  path; reproduced in sp6audit/wt-c) Lane feat-c edited SR-001 with the Edit tool (no
  `plumb capture`) while feat-d had another statement in flight. The Stop hook raised
  DEC-002 and blocked, but its reason reads only "DEC-002 holds that question for the
  agent: show the card above and ask the owner now": no card or question text is above it,
  so the agent has nothing to show the owner without running another command (on the
  capture path the card is printed; an earlier Stop block in wt-b carried the question).
  Fix: make the Stop and prompt hook reasons for an early conflict carry the card itself
  (both versions labelled by branch, and the "keep X's / keep this one / both" line), built
  by the renderer capture uses.
- [MEDIUM] (audit 3, R17 and R14, hook text vs the plain relay; approvals.py plain relay,
  awareness/answer.py) The hook and capture output tell the agent to "relay those words as
  the answer to DEC-001"; the natural `plumb relay DEC-001 --quote "keep this one"` is
  refused with "the quote does not affirm (no affirmation term such as ok...)", which does
  not name the command that works (`plumb conflict relay DEC-001`). An agent following the
  hook text literally fails, and the owner's answer may go unrecorded. Fix: name `plumb
  conflict relay <DEC>` in the hook and capture text, or hand an early-conflict DEC in plain
  `plumb relay` to `answer.relay`, or refuse naming the right command.
- [MEDIUM] (audit 3, Decision 5 and R11, capture/clarify.py depth, heuristic backend)
  "reminders should go out just 2 hours before the deadline" contradicts confirmed SR-001
  ("24 hours"), yet `plumb clarify` classed it "depth: trivial (maps to confirmed
  FEAT-001)... no questions"; the same request phrased with "instead of" escalated. Whether
  a contradiction is caught depends on wording (a heuristic limit; the prompt hook's
  generic "compare ... if it contradicts, ask" line partly covers it). Fix: when a request
  names a confirmed requirement's subject and states a different value or behaviour, class
  it at least INCREMENTAL with the read-back question drafted; add a clarify test for this
  phrasing.
- [LOW] (audit 3, R10, plumb init) `plumb init` silently sets `branch.main.mergeoptions
  --no-ff`, and the post-merge hook moves main back after a held fast-forward. Both work and
  stay cheap (about 1.5 s, no test run), but they change the owner's git behaviour without
  saying so, drifting toward guarded publishing. Fix: init's output lists, in plain words,
  the git settings it changes and how to turn them off (`plumb.mergeHold=false` is already
  honoured).
- [LOW] (audit 3, user request on pi-agent-factory intent management; FEAT-023
  intent-confirmed fast track vs plumb R8/R12) plumb already carries FEAT-023's core
  (teach-back read-back, calibration before auto-approval, judge unavailable falls back to
  the human). Not ported, as refinements rather than omissions of the owner's decisions:
  (1) SHADOW MODE, where the judge records verdicts without acting to build calibration
  labels before auto-approval is ever on; (2) explicit wrong-fast-track and disagreement
  records; (3) revising a record invalidates every automatic pass on it, so only changed
  items return to the owner. Candidate follow-ups: shadow-mode logging of triage verdicts
  against the owner's later confirm or revoke fits R12's calibration cheaply.
- [MEDIUM] (audit 3, R10.4, hosts/claude_code/stop.py at_stop, awareness/publish.py) In a
  worktree whose `changing.json` was never written, a commit followed by `plumb hook stop`
  published nothing and wrote no claim (no `changing.json`, no `refs/plumb/claims` entry,
  an empty errors.log); the other worktree reported "also being changed elsewhere: nothing"
  until a session start ran in the first one. Fix: have the stop hook publish from the
  committed diff when no `changing.json` exists, as session start does, or log a
  skipped-step line so the miss is visible.
- [MEDIUM] (audit 3, R10.3, validate.py) While a merged record carries an open `conflict:`
  block (IC-001 on SR-001), plain `plumb validate` reports "0 errors" and never mentions it;
  the record's top-level statement silently shows main's side. Only `check --merge`, the
  brief and status show the card. A merge completed with the documented
  `plumb.mergeHold=false` bypass leaves main with an unresolved intent conflict while
  validate looks clean. Fix: validate reports an open record conflict block as a finding (a
  warning; an error on the default branch).
- [MEDIUM] (audit 3, R14, boundary merge-check report used by the pre-push hook and `check
  --merge`) The quick merge hold names /plumb commands, but the full merge report the
  pre-push hook prints to the owner still says "`plumb approve SR-001 SR-003 DEC-001`, or
  say ok" and "(plumb tests waive --merge HEAD --reason ...)". R14 is SP7 scope (R18). Fix:
  route the merge-check report through the owner-text templates (/plumb confirm <title>,
  plain words for the waiver) in SP7.
- [LOW] (audit 3, R15, commands.py init) In a fresh repository `plumb init` installed
  pre-merge-commit, prepare-commit-msg, post-merge and pre-push plus the merge driver, but no
  commit-msg hook (recorded twice above). R15 is SP7 scope. Fix: install the commit-msg
  trailer hook in init (SP7).
- [MEDIUM] (audit 3, R14 and R17, boundary/prepush.py and boundary/report.py, installed by
  default by `plumb init`) Pushing a branch carrying a proposed SR, the pre-push output told
  the owner to run `plumb approve SR-003`, `plumb link SR-003 implemented_by ...` and `plumb
  repin SR-001#0`, and to "push with --no-verify to bypass the hook"; the quick merge check
  output is clean. R14 is SP7 scope. Fix: route the pre-push and merge-report owner lines
  through `plumb.present.owner_text` (/plumb confirm and plain words) and add
  `bare_cli_verbs` tests for the pre-push surface.
- [MEDIUM] (audit 3, R17 and "awareness must stay cheap", awareness/early.py check_records
  and _judge, heuristic path) Without JEV, every new requirement captured in a feature other
  branches have in flight gets one "could not be judged (a quick word check, 0.60)" line per
  branch, each telling the agent "If they differ, show the owner both and ask": in wt-k an
  unrelated "absolute value" SR drew four (div float, div floor, two pow versions).
  Conversely, two directly contradicting new "divide numbers" requirements (float vs floor
  int, wt-e vs wt-f) never reached the owner: the stop hook was silent and the status card
  showed no overlap, so both new IDs would merge side by side with no intent conflict. Fix:
  stay silent for clearly disjoint statements (no shared subject), raise an early card when
  titles match within a feature, and cap the lines per capture.
- [LOW] (audit 3, R17 RENUMBER, merge-boundary glance after `plumb merge-fix`) After
  merge-fix renumbered the clone's SR-003 "power" to SR-007, the glance correctly shows
  "carried by renumber SR-003 -> SR-007" but also lists the incoming approval row as "owner
  SR-003 ... | plumb revoke SR-003", and here SR-003 is another record ("subtract"):
  following that hint targets the wrong record. Fix: map the glance's approval rows through
  the renumber aliases, or drop the revoke hint for renumbered rows.
- [LOW] (audit 3, R10.5, pre-push hook range "<sha>..HEAD plus uncommitted changes") During
  a held merge, pushing the already clean main (9de2ccb) was refused because of the
  uncommitted in-progress merge in the working tree, not the pushed commits, and the full
  suite still ran although the push was already held. Also seen: when the merge driver
  applies an earlier answer it first prints "waits for your choice" and then "nothing to ask
  again"; one stop message shows both the DEC Question card and the Conflict card for the
  same question. Fix: check only the pushed refs' commits, and skip the full run when a
  cheap hold already refuses the push.

## SP6 audit round-3 verification (2026-10-07, commit 5ca928b)

Two real worktrees, the real CLI and hooks. The HIGH finding (an early answer became a
permanent lock: `answer.superseded` compared every record with the chosen text, so a record
the owner later changed and confirmed was refused and named on every turn, also on a fresh
branch made from main) is fixed at the one choke point: a record is named only while it
still holds the version the owner turned down (its hash or its words as asked; the
register's conflict entries now carry both versions). The three 5ca928b fixes behaved as
claimed: a merged and continued claim cleared on main with no false card, the losing lane
was told through the prompt delta and status and its relayed ok was refused, and examples
were labelled by their own requirement's state.

- [MEDIUM] (R16 and R2, approvals.py owner_scope/_check_scope, the reservation check via
  `_ASSENT`) Plain affirmations that restate exactly the record shown are refused as
  objections: "ok, SR-001 reminder timing at three days is right" and "ok, four days it is,
  SR-001 is right" both fail with "the owner's words object to or ask to change SR-001",
  while "ok, SR-001 is right" is accepted. An owner who restates the confirmed content is
  treated as making a reservation, which forces a second prompt. Fix: treat words that
  restate the record's own current content as assent, not a reservation (next to the R16
  objection-scope work).
- [MEDIUM] (R14, hosts/claude_code/stop.py:158, present/owner_text.py:182, the refusal of
  `approvals.relay`) The stop hook's block and the capture instruction tell the agent to
  "relay those words as the answer to DEC-001". The natural call, `plumb relay DEC-001
  --quote "keep this one"`, is refused with "the quote does not affirm (no affirmation term
  such as ok ...)", and the refusal does not point to `plumb conflict relay`, the call that
  works. The agent can stall on the owner's conflict answer or ask the owner to repeat
  themselves with "ok". Fix: route a plain `plumb relay` of an early decision to the
  conflict relay, or have its refusal name `plumb conflict relay DEC-### --prompt ...
  --quote ...`; name that exact command in the stop-hook instruction.
- [LOW] (R18, the stop hook's owner-visible systemMessage and the intent cards) Stop
  summaries say "touched DEC-001", "confirmed DEC-001 on your prompt \"keep this one\"" and
  "covering tests 0: 0 fresh pass..."; cards label examples "(unconfirmed-edit)" and
  "SR-001/EX-1" without titles. This is R18 scope not yet implemented (not a regression of
  5ca928b). No `.claude-plugin` exists yet, so `claude plugin validate/test` had nothing to
  exercise. Fix: the SP7 R18/R19 work.
- [LOW] (R17, answer.superseded, found while fixing the HIGH finding) Two narrow edges of the
  losing-lane signal: (a) when the owner later deliberately returns to the version once
  turned down (a later confirmation of those exact words), every branch holding it is still
  named, because the signal does not compare against confirmations newer than the decision;
  (b) a branch made from the losing lane before it adopted the answer hears nothing, since
  the register's conflict entry names only the losing branch itself. Conflict entries written
  before this fix carry no versions and supersede nothing. Fix: compare against the record's
  newest owner confirmation, and match descendants of the losing branch.

## SP6 audit round-4 verification (2026-10-07, commits 5ca928b and c7b1343)

Two real worktrees, the real CLI and hooks. The HIGH finding (a change that landed on main
cleared its claim, and with it the only signal capture checked: feat-x, made before, then
captured different words for the same requirement with no card, no decision and silent
status, brief, prompt and stop hooks, until the merge asked) is fixed at the one choke point
every reader of other branches' intent shares, `inflight.others`: the default branch's
changes since this branch's merge base (`inflight.since_fork`: merge-base, one diff, one
`git cat-file --batch`, cached by both tips) join the other branches' claims as one claim of
the default branch. Capture, the clarify read-back and the stop hook's claim raise the early
card and one decision when this work changes such a record differently; status, the session
brief and the prompt delta say the requirement was changed on main after this branch
started; the owner's answer settles the later merge. New proposed example SR-081 EX-14.

- [MEDIUM] (R17 "the answer is recorded once (a DEC) and both lanes build on it"; owner
  decision 5 "a short alignment summary at the end of each turn"; awareness/turn.py
  `at_stop` -> lines.delta_lines, whose per_turn superseded line the session emitter
  deduplicates; tests/awareness/test_early_losing_lane.py::test_stop_hook_names_it) On the
  losing lane (the owner kept main's version), the prompt hook names the record that still
  holds the turned-down words on every turn, and status, the session-start brief and the
  relay refusal (exit 3, naming DEC-001) all work, but the stop hook's end-of-turn summary
  never names it in a real turn: the prompt hook runs first and emits that line, so the
  stop hook's emitter treats it as already shown, and the owner's summary read only "plumb
  ● awaits you · SR 0/1 ok · 3 awaits you / touched 1 file(s)...". The test writes
  turn.json by hand and never runs the prompt hook. The agent is still told, so this stays
  MEDIUM. Fix: show the superseded line in the stop hook's owner summary as an owner-visible
  line not deduplicated against the agent-facing prompt delta, and make the test run the
  prompt hook before the stop hook.
- [LOW] (c7b1343 "a record is named (prompt delta, stop hook, status, brief)"; commands.py
  `brief` vs awareness.lines.brief_entries) On the losing lane the CLI brief does not name
  the superseded record; only the session-start hook's brief does, through brief_entries.
  Fix: add the superseded lines to query.brief_lines, or document that only the session
  brief carries them.
- [LOW] (found while fixing the HIGH finding; awareness/inflight.py `since_fork`) Without
  git (the prompt hook), the since-fork list is read from its cache only while the default
  branch's tip is unchanged; after main moves, the prompt delta is silent about main's newer
  changes until the next stop hook, session start, capture or status refreshes it. Status
  lists every requirement main changed since the fork, which can be long on an old branch.
  Fix: refresh the cache from the post-commit and post-merge points too, and cap status's
  list with "+N more".

## Merge of feat/jev-openrouter (2026-10-07)

- [MEDIUM] (R14; capture/jevcmd.py `auto_approve`, `config_show`) The owner has no /plumb
  route for turning automatic confirmation on or off or for seeing the settings: `config
  auto-approve on|off` and `config show` still need the owner's own terminal
  (`require_owner`). jev status and its refusals now say "only you can turn it on" instead
  of naming the CLI, but they cannot name a slash command yet. Fix: a /plumb route whose
  owner action is the typed slash command (logged by the prompt hook) or a confirm button
  (R19), recorded as `by: owner`.
- [LOW] (R14/R18; validate.py, the `auto-approve-mirror` warning) validate's warning still
  says "plumb config auto-approve on, in the owner's own terminal". validate output is the
  agent's interface, but the agent may repeat it. Fix with the route above.
- [LOW] (R18; capture/jevcmd.py `status_lines`) jev status prints config keys
  ("judgment.backend", "validated against") for the agent to translate; the /plumb template
  tells the agent to answer in plain words. A plain-words rendering for the owner would
  remove the reliance on the agent.

## SP7 spec and plan review (2026-10-07): medium and low findings

The five HIGH findings of this review were fixed in `docs/specs/sp7-owner-surface.md`,
`docs/plans/sp7-plan.md` and the SP7 records (typed-command approvals recorded as
`agent-relayed`; plain words never approve records the owner has not been shown; the R16
scope filter for a bare ok too; the Obsidian vault as an owner surface; record content
checked at the owner's level where it is written). The findings below are recorded, not
fixed.

- [MEDIUM] (R14 "jev setup/status/calibrate"; R8 `plumb jev setup` stores only the variable
  NAME; spec 6.1 row 30, 6.3 `jev status` row; `src/plumb/capture/jevcmd.py:185-191`; reported
  twice) Using JEV needs a secret in an environment variable, and the spec gives the owner no
  shell-free way to put it there or to learn how. `jev setup` answers "set
  OPENROUTER_API_KEY in your own environment ... or name an env file outside it", a
  system-internals instruction that `shell_commands` does not catch, and the 6.3 table does
  not scan the `jev setup` output. Fix: explain the credential idea in one plain sentence
  first, then offer an owner-level route ("tell me where your key file is", or where to
  enter the key in the operating system's or Claude Code's settings) instead of "set <VAR> in
  your environment"; the agent never handles the secret. Add `jev setup`'s owner lines to
  `tests/surface/test_jev_text.py`.
- [MEDIUM] (R18.4 refinement "only question user for intent/tradeoffs related problems";
  spec 8.5 "an unsure verdict is an intent gap, never a pass") JEV is optional, so the
  heuristic is the default judge; if it returns "unsure" for many member and won't pairs,
  each becomes an owner question about plumb's own uncertainty rather than a real intent or
  tradeoff. Fix: the agent first tries to settle an unsure won't judgment (restating the
  member, or asking the host agent through the fidelity packet) and raises a question only
  for a confirmed tension; cap such questions per set.
- [MEDIUM] (R19 "Render /plumb answers via the CommandOutput site"; spec 5.5) Only the
  deterministic routes (status, pane, confirm without words) are drawn on CommandOutput;
  every other /plumb answer goes to the agent and appears as ordinary model output. Fix:
  state this limit as a decision, or have the agent's /plumb answers end in a structured
  `--json` view the mod draws on CommandOutput once the agent finishes.
- [MEDIUM] (R14 "`/plumb` against a named repository from another session"; spec 6.1 row 7;
  reported three times, once as low) Only status is routed for another repository (`plumb
  status --root`). Confirm, explain, review, init, merge-check and the other routes cannot
  target a named repository from another session. The plugin makes /plumb available inside
  every repository, so this is a partial omission. Fix: let every route take "for
  <repository>" / "in <repository>" and resolve it to `--root`, with owner-only actions
  still checked against that repository's prompt log; or name the scope limit as a
  decision.
- [MEDIUM, superseded] (R14 "resolves the records, shows what is being confirmed, and relays
  the owner's typed words"; spec 7.2, matrix rows 18 and 20) Plain words resolved to one set
  were confirmed at once and shown afterwards with Undo. Fixed with the HIGH finding on the
  same point: spec 7.2's show-first rule (at once only by ID or for records shown in the
  previous reply; otherwise shown first, confirmed on "ok" or a press), SR-088 EX-3 and EX-7.
- [MEDIUM] (R19 "CONFIRM BUTTONS ([Confirm] [Show all]) in the band and pane"; spec 4.7 and
  11; plan 8.4 and 10 item 5) plumb's own repository keeps its per-repository install, so
  the mod stays idle there apart from one migration line, yet plan DoD item 5 says the owner
  confirms the SP7 records "by pressing Confirm once the plugin is installed". In the one
  repository where those records await him no band, pane or Confirm button appears, and the
  migration line keeps offering "move plumb to the plugin", which spec 11 says not to do
  there. Fix: either state that in plumb's own repository confirmation is by "ok" or
  /plumb confirm only and suppress the migration line there, or let the mod draw (read-only
  plus buttons) when the legacy install is plumb's own development install.
- [MEDIUM] (R9 card format "Examples  EX-1 ...  EX-2 ...   (proposed)"; R18 "SR-/INT-/DEC-/EX-
  ids without titles" are jargon; spec 6.3 `jargon()` rule) Examples have no titles, so the
  R9 card layout ("EX-1 ...") would fail the scanner, and the spec does not say how example
  lines are labelled. Fix: state the card wording for examples (for example "Example 1:
  given ... when ... then ..." without the EX- prefix) and add it to
  `tests/surface/test_summary_text.py`.
- [LOW] (R14: hook outputs "name the /plumb command or the plain words to say"; spec 6.3
  pre-push and merge hook rows) When the owner pushes or merges from a terminal or an IDE
  instead of through the agent, the rewritten hook output says "say 'waive the full run'"
  with no Claude Code session to say it in. Fix: phrase the hook lines as "in Claude Code,
  say ... or type /plumb ...".

## SP7 spec and plan review, round 2 (2026-10-07): medium and low findings

The one HIGH finding of this round was fixed in `docs/specs/sp7-owner-surface.md` (new 6.6,
6.1, 6.2, 6.3, 9 and 12) and `docs/plans/sp7-plan.md` (3.1, 3.2, 3.3, S3, S5, S6, 8.3):
every CLI answer the agent may show the owner, on any route of the matrix, is now an entry
point of the owner-level guarantee. One choke point (`cliutil.answer`: the default text is
`present.answers.render`, today's text moves behind `--details`, `--json` stays the agent's),
one class registry (`present.answers.FORMS`, every CLI form of 6.1 as `owner`, `agent` or
`none`), one test per `owner` form, and the e2e scans the stdout of every routed CLI call.
New proposed example SR-089 EX-9. The findings below are recorded, not fixed. Several
repeat entries of the first round; they are noted as such.

- [MEDIUM] (R16 "Objection and change detection must be scoped to the sentences that name,
  or plainly refer to, the records being approved. An unrelated request in the same message
  must neither block nor count."; spec 8.1 rule 1 and the dark-mode example; reported twice)
  Rule 1 keeps every clause of the sentence that holds the ok in scope, whatever it is
  about, so "ok, and also add a dark mode" or "Ok, confirm DEC-017 and DEC-018, and make
  plumb a plugin" still holds the ok back: the R16 bug class with a comma where the owner
  happened to type a period. Defensible (R16 scopes by sentence; refusing is the safe
  failure; objections after the ok such as "ok, I know SR-007 is wrong, rewrite it" must
  still count). Fix: inside the ok's sentence, count a clause only when it is a correction
  without its own object ("except ...", "but ...") or meets rule 2 or rule 3; a clause after
  "and"/"and also" that names no record of T, has no distinctive word of T and no reference
  back is out of scope. Add an SR-090 example and a test for "Ok, confirm DEC-017 and
  DEC-018, and make plumb a plugin"; otherwise record the conservative choice as a known
  limit.
- [MEDIUM] (R14 "`/plumb` against a named repository from another session"; spec 6.1 row 7;
  reported twice this round, three times in round 1) Only status is routed for another
  repository (`plumb status --root`); init, explain, confirm, merge-check and the other
  routes cannot target a named repository. Fix: a general "<route> for <that repository>"
  rule in the `/plumb` template (6.2): the agent resolves the repository and passes
  `--root` to any agent-side route, with owner-only actions checked against that
  repository's prompt log; one e2e case beyond status (for example `/plumb init for <path>`
  or "confirm ... in <other repository>").
- [MEDIUM] (R15 "status line where plugins allow it"; spec 4.3 "Status line") The spec says
  plugins have no status-line field, but the mod API of this build exposes
  `$.ui.status(text)`, which pins a plugin status line under the prompt. The band covers the
  need, but the spec states the platform limit wrongly. Fix: correct the statement, and
  either draw the one-line status card with `$.ui.status` when the band is hidden or the
  card setting is compact, or record why the band alone suffices.
- [MEDIUM] (Decision 5; R14 "`/plumb confirm <plain words or IDs>` ... relays the owner's
  typed words"; spec 4.2 "First session" with 7.2) While the first bootstrap runs, every hook
  but session-start exits at once, so the prompt hook logs nothing; an "ok" or a typed
  `/plumb confirm` in that window has no logged prompt and is refused during the owner's
  first session. Fix: have `plumb-hook` keep a minimal prompt-digest log in `sh` during the
  bootstrap (one sha256 line), or have the mod log typed prompts once ready; otherwise say
  plainly that confirmations wait for "plumb is ready", and add a test.
- [MEDIUM] (R14 "error messages NEVER instruct the owner to run a shell command"; R15 "a uv
  tool install the plugin bootstraps"; spec 4.2) There are owner lines for "getting ready"
  and for a missing Python, none for a bootstrap that fails (no network, a uv or pip error, a
  failed wheel install). Every hook exits 0 until `current.json` exists, so the owner sees
  "plumb is getting ready ..." at every session start and never learns plumb is not working.
  Fix: record the failure under `PLUMB_HOME`, show one plain line ("plumb could not finish
  setting itself up; say 'fix plumb's setup'"), add a matrix row and
  `tests/plugin/test_env.py::test_failed_bootstrap_line`.
- [MEDIUM] (R14 matrix "covering every plumb feature"; R17 "The single full suite runs at
  push (pre-push)"; spec 6.1) The matrix has no row for pushing ("push my work"), although
  the owner never pushes from a shell and the e2e expects "a push whose pre-push report is
  read"; `test_every_matrix_row_routed` cannot cover it. Fix: add a row "push", "push my
  work" -> `git push` through the pre-push hook, answered at the owner's level and pointing
  to rows 34 (waive) and 52 (why was it held).
- [MEDIUM] (R15 "Existing per-repository installs ... are migrated or remain supported as a
  fallback"; spec 4.7 band line vs 4.7 last paragraph and 11; repeats a round-1 entry) In
  plumb's own repository, which keeps its legacy install on purpose, the band invites "move
  plumb to the plugin" every session, a migration the spec says must not happen there (the
  hooks would then run the bundled wheel instead of the code under development); 4.7 also
  says the plugin "stays silent there". Fix: suppress the invitation there through a config
  key such as `plugin.legacy_on_purpose`, and test it.
- [MEDIUM] (R18.4 "only question user for intent/tradeoffs related problems" ... "a `will`
  that cannot be served without breaking a `wont`"; spec 8.5 intent gaps; close to a round-1
  entry on unsure verdicts) Any member the judge says goes against a won't item, and any
  unsure verdict, becomes an owner question. A badly worded requirement that could simply be
  rewritten is the agent's to fix. Fix: treat a won't contradiction as a gap the agent
  repairs first (reword or drop the member); raise an intent gap only when the will it
  serves cannot be met without the contradiction, or the reading is ambiguous; bound how
  often an unsure verdict may fall back to asking.
- [LOW] (R14 "resolves the records, shows what is being confirmed, and relays the owner's
  typed words"; spec 7.2 "Show first") For plain words naming records not shown in the
  previous reply, a typed `/plumb confirm` takes two owner steps (the cards, then "ok" or a
  press). Justified by the KEEP list ("approvals pinned to exact content"). Fix: keep it,
  and make the cards' offer line say that one "ok" or Confirm finishes the step.
- [LOW] (R19 "Render /plumb answers via the CommandOutput site"; spec 5.5; reported twice,
  repeats a round-1 entry) Only the deterministic routes (status, pane, confirm without
  words) are drawn on CommandOutput; every other `/plumb` answer is model text. Fix: say
  explicitly that agent-routed answers stay model text, and why, or draw on CommandOutput
  the rows whose answer is a deterministic CLI view (6.6's `owner` forms are candidates).
- [LOW] (R14; spec 5.5 and 7.2) Without the mod, and on a host that does not run the prompt
  hook for typed slash commands, no prompt is logged and every `/plumb confirm`, revoke,
  auto-confirm or waive is refused; the spec leaves the check to the MOD lane (M1) with no
  fallback. Fix: make M1's answer a spec rule: if slash commands are not seen by the prompt
  hook, owner-only slash routes without the mod send the owner to "ok" after the cards, and
  the matrix and `docs/hosts.md` say so.
- [LOW] (R18 "never in plumb's or the codebase's internals (hashes, record kinds, links,
  file paths, test node ids)"; spec 6.3 JARGON) JARGON lists link kinds and record IDs but
  not the words "record(s)", "requirement" or "link(s)", so today's status card line "links:
  current 1033, stale 0" would pass. Some kind words (intent, examples, tests) are in R9's
  card format the owner liked, so this is calibration. Fix: add "record(s)", "requirement"
  (where the owner did not use it) and "link(s)" to JARGON with CONCEPTS explanations, or
  document which kind words are owner-level by R9.
- [LOW] (R18; spec 3) The principles are numbered 1, 2, 6, 3, 4, 5. Editorial. Fix:
  renumber them.

## SP8 lane SELECT (2026-10-10)

- HB1 probe (coverage 7.16.2, contexts switched per test node, 5 of plumb's verify test files,
  32 tests): 24.8 s plain against 37.1 s under coverage (about 1.5 times, dominated by tests
  that start subprocesses, which coverage does not follow); the data file for those 32 tests
  is 90 KB with 13 460 (line, test) pairs, about 420 executed lines a test. The suite is about
  1 400 tests, so an inverted function-to-tests map is several megabytes as JSON: the store
  is SQLite (`.plumb/cache/funcmap.sqlite`, in the gitignored cache). Final numbers of the
  whole-suite map are added under HB6 below.
