# Why retired cards stayed in the band's count (case report-ec092f5e, 2026-11-04)

## What the owner saw

The status band said 73 questions await them; `/plumb status` said 29. The other 44 were open
cards in old sessions' card stores (27 choice, 7 principle, 7 trial, 3 clarify), which nothing
can show or answer since the card surface was removed.

## What the owner had decided

- 2026-10-16, P12: cards retired.
- 2026-10-26: "Cards are deprecated, it should be removed totally from the project".
- 2026-11-02: "Yes, retire the cards".
- SR-337: the band's line carries "the count of questions waiting".
- SR-373: "There are no cards: nothing the owner reads and presses, no card store, no offers, no
  full-card text."

## Why nothing caught it

1. **The plan's deletion list left the store out.** Phase 5 of
   `docs/plans/2026-10-26-review-resolution.md` names `fullcard.py`, `cardcontent.py`, `press.py`,
   `offers.py` and others, not `understand/cardstore.py`. SR-373 said "no card store"; no plan
   item delivered it, and no gate compared the two.
2. **"Remove the card engine" removed the drawing only.** Commit `1aa0b21fc` says "what the rest
   still needs stays where it is written". Fourteen modules still read the store, so it looked
   needed, and it still is for live behaviour (see below).
3. **A test wrote the wrong behaviour down.** `a9c01bec0` (2026-10-20) made `awaiting_count` add
   open cards, and `test_awaiting_counts_open_questions_and_cards` asserted it, linked to SR-337
   whose words say questions. A passing test linked to a requirement reads as proof of it; every
   check stayed green. No check compares what a test asserts with what the requirement says.
4. **The sentence had no example.** SR-373's "no card store" has no example and so no test: a
   requirement's claim with no example holds nothing at the merge. Requirements waiting on a
   judge (about 460) were also not read against the code.
5. **Two counts, one label.** The band and `/plumb status` computed "questions waiting" separately
   and no test compared them. The owner found the gap by reading both.
6. **No check that a retired feature is gone.** The owner asked on 2026-10-26 that ponytail audits
   catch this; an audit is a habit, not a gate, and none caught it.

7. **The job that should have closed answered questions read only cards.** SR-218 says the judge
   reads each open question against what the owner decided and withdraws what is settled. That
   job is `understand/tidy.py`; it read the card store only, so when questions moved from cards
   to the question tool it stopped seeing any, and it had no test on a judge question. The owner
   asked why they were re-asked things they had answered; this was the reason.

## What changed

- The band counts judge questions only, the same as `/plumb status`; a test asserts that both
  give the same count with a card present in a store.
- The leftover card files of old sessions are deleted (archive kept outside the repository).
- The job reads the judge's waiting questions against the owner's logged answers and confirmed
  records. A question closes only when the quoted words are really in that answer or record, is
  logged as `answer-bound`, tells the agent one line, and `plumb question reopen` undoes it.

## What is still open

The store itself is not gone: `understand/cardstore.py` still carries live behaviour (the gate's
choice when a check cannot be made, reading a typed answer against what is open, stale-link
questions, tidy). SR-373's "no card store" stays untrue until that is moved or retired. When it
is, a test that fails if anything imports `cardstore` closes point 6 for this feature.
