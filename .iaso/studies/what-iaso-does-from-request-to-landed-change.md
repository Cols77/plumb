---
title: "What iaso does, from request to landed change"
topic: "how iaso works"
step: ""
loop: ""
why: "the owner asked for an example study mixing text, diagrams and animated workflows"
recommend: "video"
depth: "video"
records: [{"id": "SR-272", "title": "Long iaso work shows its step and progress", "hash": "sha256:cdda64eabd985c0c5b4bbc45619c1acfa5a7c78420cd4ef78fd2a7161e50c83e"}, {"id": "SR-273", "title": "iaso's model work runs as batched background jobs", "hash": "sha256:ec636c4a8a6e83dcbafd1c5205b8e3ad38aa2b4f2dd7ae5570f06a3d68462962"}, {"id": "SR-220", "title": "What iaso cannot settle goes to a debug workflow, the owner last", "hash": "sha256:10e13345d2320a143d169d55f5cf2a8d5143ed353304b733f776d5f5925360c6"}, {"id": "SR-245", "title": "With no judge reachable, iaso says so once and holds only what...", "hash": "sha256:e991ff42c027fd144648b59d9529cdf73a803c47f954452e36b4b7fde9c013c8"}, {"id": "SR-260", "title": "The merge is the one hold on unapproved or conflicting intent", "hash": "sha256:e586584e8c495edeca773b2dc2dd3fc6ddb88c162fea071091e34d679b6a57df"}, {"id": "SR-291", "title": "The band shows the intent loop's step and the step's progress", "hash": "sha256:f33197ee2c653b234dca47a5b6717ff817496e6e46ca011693c406fa2cadf575"}, {"id": "SR-294", "title": "A new study is announced in iaso's colours, never forced open", "hash": "sha256:ce53caab508f0dceb174e52f27bbd7e97ebe4dfc408981a2219f3bb0a8d70dc6"}, {"id": "SR-361", "title": "Every judge question is asked as soon as it is raised", "hash": "sha256:4002e934b7c16d0c70ffb7c0fc3feba08f739774ea70f5a90d3bbd2be759f29f"}, {"id": "SR-371", "title": "A study being written shows its progress in the band", "hash": "sha256:ceaf7de4310a0dedd56357c6e75f3dabe9c1331aa059bb893adf4a277e210d2a"}, {"id": "DEC-238", "title": "How far does the debug workflow go by itself once a case's rerun...", "hash": "sha256:9818750e47e7a260a5318816ee460c33cd56ba3e30f3e01666c113df0d67637b"}, {"id": "DEC-260", "title": "Does a judge job that fails open a debug case at its first...", "hash": "sha256:c980c9334cf09385f917fa98d5d796559b9e71eee6aac2a234befafa8a3c9771"}, {"id": "DEC-131", "title": "Where does the progress of long iaso work show?", "hash": "sha256:d527244f7e33b36d4b62150bfc74dbe15dfea073978c69385132fb19efa019c4"}]
changed: "What iaso cannot settle goes to a debug workflow, the owner last, The merge is the one hold on unapproved or conflicting intent, Every judge question is asked as soon as it is raised"
refresh: ""
clips: {"one-request": {"state": "ready", "reason": "", "revisions": 1}, "debug-case": {"state": "ready", "reason": "", "revisions": 6}}
status: "opened"
---

# What iaso does, from request to landed change

iaso keeps what you asked for as small, linked records, has a judge approve them on your behalf, ties them to the code and tests that prove them, and checks all of it before anything merges. This study shows that path once, from the outside in: the shape of the records, the animated trip of one request, what happens when iaso itself gets stuck, and where you still decide.

## The records and what they point at

You never read these. They exist so iaso can answer "why is this here?" and "what did we agree?" later.

```mermaid
flowchart LR
  you["Your words (verbatim)"] --> INT["Intent (INT): what you want"]
  INT --> SR["Requirements (SR): given / when / then examples"]
  INT --> DEC["Decisions (DEC): the choices that matter"]
  SR --> CODE["Code it changes"]
  SR --> TESTS["Tests that prove each example"]
  DEC --> SR
  JUDGE["Judge (a model, in the background)"] -. approves or asks .-> INT
  JUDGE -. approves or asks .-> SR
```

An intent holds your request in your own words. Each requirement under it carries examples written as *given, when, then*, and each example is linked to the test that proves it. Decisions record the choices that change what gets built. A judge reads the new records in the background and either approves them on your behalf or comes back with a question only you can settle (SR-273, SR-361).

## One request, start to landed change

Watch for three things: the records are written before the code, the judge never blocks the agent while it works (it runs as a background job), and a merge is checked twice, quickly when git records it and fully when you push (SR-260).

```video
one-request
```

The point of the clip is the order. Records come first and the judge works beside the agent, so a question reaches you at the agent's next chance to ask, grouped by principle, not one by one (SR-361). Tests are linked to examples, so "tests pass" means "the examples you agreed to hold".

## What iaso does when it is stuck

iaso does not ask you about its own failures. When a judge cannot settle after its rounds, or a judge job fails three times, the case goes to a debug workflow that runs in the background (SR-220, DEC-260).

```mermaid
stateDiagram-v2
  [*] --> Working: judge job queued
  Working --> Retried: fails, larger budget each time
  Retried --> DebugCase: third failure in a row
  DebugCase --> Resolved: rerun passes
  DebugCase --> FixOnBranch: rerun fails again
  FixOnBranch --> WaitsForYou: tests green, nothing stale, judge review passed
  WaitsForYou --> [*]: main takes it on your word
```

```video
debug-case
```

Watch what the debug workflow is *not* allowed to do: it may rerun a step and fix iaso on a branch, but it never changes what a record means and never approves anything. Landing on main waits for your word (DEC-238).

## Where you still decide

- Questions only you can settle: intent choices and trade-offs, asked in plain words through the question tool.
- Study depth: Markdown, diagrams or video is your press in the band, as this study was (SR-294, SR-371 shows its progress while it is written).
- Landing on main: a fix is ready on a branch; you give the word.

Long iaso work reports its step and progress where you look: the band, the status line, the terminal (SR-272), including the bar you saw while this study was being written.

Written from: SR-272 Long iaso work shows its step and progress, SR-273 iaso's model work runs as batched background jobs, SR-220 What iaso cannot settle goes to a debug workflow, the owner last, SR-245 With no judge reachable, iaso says so once and holds only what..., SR-260 The merge is the one hold on unapproved or conflicting intent, SR-291 The band shows the intent loop's step and the step's progress, SR-294 A new study is announced in iaso's colours, never forced open, SR-361 Every judge question is asked as soon as it is raised, SR-371 A study being written shows its progress in the band, DEC-238 How far does the debug workflow go by itself once a case's rerun..., DEC-260 Does a judge job that fails open a debug case at its first..., DEC-131 Where does the progress of long iaso work show?
