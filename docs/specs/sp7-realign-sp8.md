# SP7 re-aligned with SP8: the owner surface draws SP8's cards

Status: proposed, 2026-10-11. Re-aligns `docs/specs/sp7-owner-surface.md` and
`docs/plans/sp7-plan.md` (both frozen, not edited) with `docs/specs/sp8-intent-by-exception.md`
(built). `DEC-031` (as it reads now): re-align SP7 with SP8 and build it in parallel with the
everyday loop, in separate worktrees. Records: `FEAT-007`, `FEAT-008`, `INT-008`, `SR-012`,
`SR-105`, `SR-086`, `SR-088`, `SR-112`, `SR-113`, `DEC-029`, `DEC-030`. Where this note and
the frozen SP7 spec disagree, this note wins; where either disagrees with the owner's words,
the words win.

The owner's wants for SP7 (conversation of 10-11 Oct):

- cards with buttons to **confirm**, **ask for a change** and **leave the record open**;
- every click is logged, and a click confirms because only the owner can click (no agent
  action confirms);
- no list-style summary at the end of a turn: cards only (`SR-012`, `INT-008`);
- one card per feature (`DEC-029`).

What exists today (checked in the code on 2026-10-11): none of SP7's code (no `plugin/`, no
`plumb.mod`, no `owner_actions`, no `guard`, no `launcher`, no phase-0 contracts). SP8 is in:
`CardState` and `ClarifyQuestion` (`contracts.py`), the builders and text rendering
(`understand/cards.py`), the session store `.plumb/session/<s>/cards.json` with one writer
(`understand/cardstore.py`), the reader's answer path (`understand/read.py`: `_apply_card`
and the `effects` registry per card kind), settling with `via: typed | button` already
accepted for the settle switch, Undo and the gate release, the edit gate (`gate.sh`,
`pretool.py`), the progress file and the status line. The stop hook still prints the SP1/SP5
list summary, the status card and the SP5 intent cards, then appends SP8's cards
(`stop.py` `summary()` + `understand_parts()`): that is what `SR-012` now forbids.

## (a) Superseded by SP8: drop from SP7

| SP7 section | Why it goes | Replaced by |
|---|---|---|
| 8.1 the relay's objection scope (`SR-090`, `_in_scope`, distinctive words) | word rules; the agent-run prose relay no longer exists | the reader (SP8 4.1); `SR-090` superseded |
| 8.2 `is_bare_assent` and the auto-approval gate on bare assent | assent vocabulary is a word rule; `autoapprove.py` is superseded | the judge's premise carries the stored question (`premise.py`); settling (SP8 7) |
| 8.3 the self-challenge hints (absolutes, "users want") | fixed word lists (`INT-029`) | the clarifier's gaps and labelled assumptions (SP8 4.3) |
| 8.5's won't judgment "JEV, else the heuristic" | no heuristic, no fallback | the judge (`contradicts`) |
| 7.2 `via: words` (`approvals.relay`) and "show first by resolving words" | prose never matched by plumb | the reader; a `show_first` card (SP8 6) |
| 7.2 `/plumb confirm <words>` | `confirm` takes IDs only (`SR-088` EX-10) | prose to the reader |
| 5.7 offer actions `group` (triage) and `auto_approve` | triage groups and auto-approval are gone | backlog feature card (`DEC-029`); the settle switch (`DEC-030`) |
| 5.4 the summary line under each answer ("✓ aligned — touched … · 7 checks pass") | a summary, not a card (`INT-008` won't) | the status line (band) and the one settled line (`SR-105` EX-1) |
| 6.3 the rewrite of the stop hook's list summary (sp1 lines, status card, intent cards) | that summary is removed, not reworded | cards only (slice 3) |
| 6.1 rows 18, 19, 22, 27 as written (relay, `--group`, `auto-confirm`) | as above | rows rewritten: confirm = typed IDs, a button, or prose to the reader; `/plumb settle on|off <kind>`; `/plumb undo` |
| 4.3 the prompt hook's "relay line" | removed by SP8 | the read job |

## (b) What SP7 keeps

- **Plugin (4, `SR-082`–`SR-084`, `DEC-023`)**: marketplace, bundled environment, `plumb-hook`,
  `/plumb init`, launcher, migration, silence when not adopted. One change: `pre-tool` adopts
  SP8's `gate.sh` fast path for the edit tools and adds the Bash guard of 4.3 behind it.
- **Mod (5, `SR-085`–`SR-087`, `DEC-024`, `DEC-025`)**: the handshake and `mod.json`, the key
  that only the mod holds, `plumb mod press` refused under the session marker and run with the
  marker removed, `present.json`, the band, the pane, `/plumb` answered on `CommandOutput`,
  the background section, the fallback, the guard inside the mod.
- **Owner text (6.3, 6.5, 6.6, `SR-089`)**: `shell_commands` and `jargon`, record content at the
  owner's level (`agent_notes`), route answers through `cliutil.answer`, the README split.
- **Owner actions (7, `SR-088`)**: one choke point, narrowed to `via: terminal | command |
  button` (`command` = typed IDs; `words` is the reader's, not SP7's).
- **Capture leftovers**: `done_when` (8.4), the deterministic part of the structure check
  (8.5), records in an intent conflict are not stale links (8.6, `SR-095`).
- **The owner e2e** (12 item 2), with the flows of (c) in place of the relay flows.

## (c) What changes so SP7 renders SP8's cards

**C1. One card model for everything that needs the owner.** Every owner-facing item is a
`CardState` in `cards.json`: SP8's kinds (clarify, trial, backlog, beyond, contradicts,
couldnt_check, show_first, settle_offer, stale_link) plus the ones the stop hook still draws
its own way today, which become card kinds built in `understand/cards.py`: `regression`
(`SR-012` EX-2), `decision` (a decision that matters), `conflict` and `early_conflict` (SP6),
`drift` (`SR-113` EX-2: an aligned intent and requirement, code that moved away). SP7's
`ModCard`/`ModOffer` are not added: the snapshot carries `CardState` JSON as `cardstore`
writes it.

**C2. Choices are data, not only labels.** `ClarifyQuestion` gains `choices:
tuple[Choice, ...]`, `Choice = {label, answer: accepted|rejected|change|open, change:
str|None}`, in the order of `resolutions` (recommended first). The mapping SP8 4.1 states in
prose becomes data, built once per kind in `cards.py` (keep = accepted, drop = rejected,
reword = change; pick a version = change carrying that version; trial and backlog yes/no;
Build anyway/Wait). The reader's prompt and the buttons read the same `choices`.

**C3. The buttons.** Each card question shows its suggested choices as buttons (an `accepted`
choice is labelled **Confirm** when the card offers no other wording), then always **Ask for
a change** and **Leave open**. A feature card (`DEC-029`) has one set of buttons for all its
items ("these 18 about the merge check would be settled; right?") and **Show all**, which
expands the items, each with its own three buttons (an exception for one item).

**C4. How a click reaches plumb.** The mod draws a card from the snapshot and records an offer
per drawn question: `offer_id = digest(card id, question id, record hash)`, written to
`.plumb/session/<s>/offers/` with `drawn_at` (SP7 5.7, unchanged). A click runs `plumb mod
press --session <s> --offer <offer_id> --choice <n>` with the key on stdin. plumb checks the
key against `mod.json`, the marker is absent, the offer was drawn before the press, and the
question's record is still at the offered hash (else nothing is confirmed, the card is closed
and the new version is shown as a fresh card, as `read._close_stale` does today).

**C5. One answer path for prose and clicks.** `read._apply_card` and `_Applying.confirm` move
to `understand/answer.py` as `apply_answer(core, session, card, question, choice, source)`,
where `source` is either `owner-words {job, digest, evidence, confidence}` (the reader, after
its threshold) or `button {offer_id, key_digest}` (a click: no threshold, the owner pressed
it). The effects registry runs the same handler for both. So a click on a trial card labels
calibration exactly as a prose yes does, and an answered card closes the same way.

**C6. Every click is logged, and only a click or the owner's words confirm.**

| Button | Log entries | Effect |
|---|---|---|
| Confirm (an `accepted` choice) | `card-press` + `approval {by: owner, via: button, offer, card, question, records: [{id, hash}]}`, marker `none` | confirmed at the shown version; the band says so; a model note tells the agent |
| a `rejected` choice | `card-press` + the SP8 rejection entry with `by: owner, via: button` | as a prose "no" (`misread` for trial labels) |
| Ask for a change | `card-press {answer: change}` | nothing confirmed; the question is marked `change_requested`; the owner's next message is read against it, and the reader's `change` becomes the recapture card it is today |
| Leave open | `card-press {answer: open}` | nothing confirmed; the card's status becomes `left_open` |
| Undo (settled line), Build anyway, settle on/off | `revocation by: undone, via: button`; `gate` release `button`; `settle-config via: button` | as already accepted by `recheck_settled`, `gate`, `settle` |

`confirm.py` accepts `by: owner, via: button` on `approval` with its re-check (the offer
exists in that session, was drawn before the entry, names this record at this hash, the key
digest is the one in `mod.json`, marker `none`). An approval written any other way by the
agent is not accepted (`SR-112` EX-7). Tamper-evident, not tamper-proof (SP7 5.7).

**C7. Cards only at the end of a turn.** The stop hook's owner output is `StopParts` and
nothing else: what the owner's words confirmed, the one settled line with Undo, the cards
(`SR-105` order). The SP1 lines, the status card and the SP5 intent cards leave the owner's
output; the status card moves to the status line. With the mod active, the stop hook writes
`present.json` (`{turn, confirmations, settled, cards}`) and no `systemMessage`; the panel
draws the cards and the agent's reply names them in one line instead of repeating them.
Without the mod (fallback, other hosts), the same parts print as text, the agent presents
the cards in its reply, and the owner answers in prose or by a typed command.

**C8. One card per feature.** Cards are grouped by feature (by derived intent where a record
has no feature) in the snapshot, in the band count ("3 await you: merge check, reminders,
settling") and in the pane. Records a single turn proposed that the judge could not settle
come as one feature card (`SR-012` EX-4), not one card each.

## (d) Revised plan, in order

Each slice is one branch from `main`, merged when its gate passes. Gates are targeted tests
only. The everyday-loop stream (`DEC-031`) runs alongside; the shared file is `stop.py`
(slice 3), which only this plan's slice 3 edits while it is open.

| # | Slice | Gate (targeted tests) | Serves |
|---|---|---|---|
| 0 | Contracts: `Choice` and `choices` on `ClarifyQuestion` (default empty; `cardstore` reads and writes it); `card-press` log kind; `approval` accepts `by: owner, via: button` (re-check stubbed to refuse); `left_open` and `change_requested` statuses; the `present.json` shape. Propose the new examples on `SR-086` (leave open, ask for a change) as proposed records | `tests/understand/test_contracts.py` (the card store round trip with choices); `tests/core/test_log.py` (the new kinds) | `SR-105`, `SR-086` |
| 1 | `choices_for(kind)` in `cards.py` for every SP8 kind; the reader's prompt lists choices | new `tests/understand/test_card_choices.py` (one case per kind); `tests/understand/test_read_job.py`, `test_read_cards.py` unchanged and green | `SR-105`, `SR-101` |
| 2 | `understand/answer.py`: the reader's `_apply_card` and `confirm` moved behind `apply_answer(source=…)`; behaviour unchanged | the existing answer tests unchanged and green: `tests/understand/test_read_apply.py`, `test_read_cards.py`, `test_card_pins.py`, `test_trial.py`, `test_backlog.py`, `test_owner_only.py` | `SR-101`, `SR-112` |
| 3 | Cards only: `regression`, `decision`, `conflict`, `early_conflict`, `drift` card kinds; the stop hook's owner output is `StopParts` only; status card to the status line; new-turn records grouped per feature | `tests/host/test_stop.py` (the cards-only cases), `tests/understand/test_summary.py`, one test per `SR-012` example and `SR-113` EX-2 | `SR-012`, `INT-008`, `SR-105`, `SR-113`, `DEC-029` |
| 4 | Python side of the press: `plumb mod hello` (first wins), offers recorded at draw, `plumb mod press --offer --choice`, `card-press` logging for all buttons, `confirm.py` re-check for `via: button` | `tests/mod/test_hello.py`, `tests/mod/test_press.py` (wrong key, no key, under the marker: exit 3 and nothing written; a changed record left out and re-carded; Leave open and Ask for a change write no approval; Confirm writes `by: owner, via: button` at the shown hash; a hand-written button approval is rejected) | `SR-086`, `SR-112`, `SR-105` |
| 5 | Owner-text scanners `shell_commands` and `jargon`, run on `cards.render`, the settled line and every card field in `present.json` | `tests/present/test_owner_text.py`, `tests/surface/test_card_text.py` (one case per card kind) | `SR-089` |
| 6 | Plugin (SP7 4 as written, with `gate.sh` adopted in `pre-tool` and the guard table naming `mod press|hello|typed`, `settle`, `undo` and `go` without the owner's proof) | SP7 4.8's tests, `tests/plugin/test_guard.py` with the SP8 forms | `SR-082`–`SR-084` |
| 7 | The mod: handshake, `present.json`, the band (status, SP8 progress, cards awaiting per feature), the card panel with the three buttons, Show all, Undo on the settled line, notices and model notes, fallback | `claude plugin test plugin`: `band.test.tsx`, `buttons.test.tsx` (each button calls `plumb mod press` with the key on stdin, never in argv), `fallback.test.tsx`; `tests/mod/test_handshake.py` | `SR-085`, `SR-086`, `SR-087`, `SR-108` |
| 8 | The pane per feature and `/plumb` on `CommandOutput` (status and what awaits, drawn as cards) | `pane.test.tsx`, `command.test.tsx`, `tests/mod/test_snapshot.py` | `SR-085`, `DEC-029` |
| 9 | Surface: owner matrix rewritten per (a), `/plumb` template routes, route answers (6.6), record text checks (6.5), README | SP7 6.6 and 6.5 tests, `tests/surface/test_matrix.py` | `SR-088`, `SR-089` |
| 10 | Integrate: the owner e2e on the flows of (c) (Confirm, Ask for a change then prose, Leave open, Undo, Build anyway, a feature card with one exception), the live smoke | `tests/owner/test_owner_flows_e2e.py`; the one full run at merge | `FEAT-007` |

Slices 0 to 5 are Python only and do not wait on the Claude Code mod API; 6 and 7 can start
once 0 is in. Dropped from the frozen plan: lane CAPTURE2's 8.1 to 8.3 and its relay tests,
SURFACE's rewrite of the list summary, MOD's `summary.test.tsx`.

## (e) Open questions for the owner

1. **After "Ask for a change", where do your words go?** Recommended: the click puts the
   cursor in your message box with "Change to '<topic>': " already written; what you type is
   read against that card. If Claude Code's panel cannot prefill the box, the agent asks you
   one question in its next reply instead.
2. **Is "No" (drop it, wait) a button too?** Recommended: yes, wherever the card suggests it
   (a trial or backlog no, "drop it" on a card that goes beyond your words, "wait" on a
   failed check), beside Ask for a change and Leave open. Everywhere else, the three buttons
   you named.
3. **How long does "Leave open" last?** Recommended: the card stops coming at the end of
   turns until its record changes; it stays listed under what awaits you in the band and the
   pane, and `/plumb` shows it again on request. It never confirms, settles or rejects
   anything.
