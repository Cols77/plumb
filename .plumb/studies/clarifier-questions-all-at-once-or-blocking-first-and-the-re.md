---
title: "Clarifier questions: all at once, or blocking first and the rest paced?"
topic: "the October rule that the clarifier asks every gap that changes what gets built in one turn (DEC-106), against the new wording that asks blocking gaps at once and paces the others by principle, three a turn (SR-223, SR-334); both sides laid out, nothing chosen"
step: "build"
loop: "8297b5279d17"
why: "you chose to study this question before answering it"
recommend: "md"
depth: "md"
status: "opened"
---

# Clarifier questions: all at once, or blocking first and the rest paced?

## What the question is about

When you type `/plumb intent <words>`, plumb's clarifier reads your words with the conversation and finds the gaps: things it cannot settle from your words, the records or the code. Each gap ends one of three ways: a labelled assumption (there was a recommendable answer), a question asked now, or a question that waits. The study is about the line between "asked now" and "waits".

## The two pictures

**All at once.** Your earlier decision (the intent "clarification on command") said: every question that changes what gets built is asked in the same turn, specific, with options and a recommendation, before anything is built. Example from the requirement: the request "let users export their data" drafts four questions; one is already answered by a confirmed record, one has options that build the same thing; exactly the two left are asked, together, in that turn. Another: two or three gaps with no better-supported option are all asked in the same turn, never one per turn.

**Blocking first, the rest paced.** The later intent ("issues reach you through the question tool, paced by principle") adds a backlog: when many questions wait, plumb groups them by the principle they hinge on and asks at most three per turn, between tasks. Example: 62 questions wait, 50 of them hinge on four principles; a turn ends and you are asked at most three, each a principle, and the turn-end line counts the rest. A question that blocks the task in hand is still asked at once, even when three were already asked.

## How they fit together

The two are not rivals; they apply to different questions:

- A question that blocks the work now (its answer changes what gets built in this loop) is asked in the same turn, all such questions together. This is the "all at once" rule, unchanged.
- A question that does not block (it concerns later work, a backlog of records waiting on a judge, a principle behind many small gaps) waits and is paced: by principle, at most three per turn, between tasks.
- Answering a principle settles every question that hinges on it, so pacing by principle shrinks the backlog faster than asking each question.

The requirement for the clarifier now says both in one sentence: blocking questions in the same turn, non-blocking ones paced by principle at most three per turn.

## What changes for you

- In an intent loop you still get every blocking question up front, before the build. Nothing of that waits.
- Outside a loop, or when a backlog has built up, you see at most three questions per turn, each one a principle, and a count of what still waits at the end of the turn.
- An answer you give settles what hinges on it even before the judge approves the record that carries it.

## What stays open

The one timing decision still proposed is when the clarifier change itself lands (after the browser merge, as its own branch). It changes nothing about which questions come first.
