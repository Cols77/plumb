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
