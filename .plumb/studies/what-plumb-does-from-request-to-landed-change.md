---
title: "What plumb does, from request to landed change"
topic: "how plumb works"
step: ""
loop: ""
why: "the owner asked for an example study mixing text, diagrams and animated workflows"
recommend: "video"
depth: "video"
records: [{"id": "SR-272", "title": "Long plumb work shows its step and progress", "hash": "sha256:dafd76d3c63233462a33c0f54f8af6956f6017739bc140b7cd9b21ec3af5e812"}, {"id": "SR-273", "title": "plumb's model work runs as batched background jobs", "hash": "sha256:76bf4a5cc3e163604ce73f5610725d50a3fde45d1935aee017eee443a1cdb733"}, {"id": "SR-220", "title": "What plumb cannot settle goes to a debug workflow, the owner last", "hash": "sha256:10e13345d2320a143d169d55f5cf2a8d5143ed353304b733f776d5f5925360c6"}, {"id": "SR-245", "title": "With no judge reachable, plumb says so once and holds only what...", "hash": "sha256:51ffbb1ed6107aa49e7ce2ecb817e529bae3528995d73f9803385b132d9d5c30"}, {"id": "SR-260", "title": "The merge is the one hold on unapproved or conflicting intent", "hash": "sha256:e586584e8c495edeca773b2dc2dd3fc6ddb88c162fea071091e34d679b6a57df"}, {"id": "SR-291", "title": "The band shows the intent loop's step and the step's progress", "hash": "sha256:f33197ee2c653b234dca47a5b6717ff817496e6e46ca011693c406fa2cadf575"}, {"id": "SR-294", "title": "A new study is announced in plumb's colours, never forced open", "hash": "sha256:2d4c323c430ed5931d7e50ee02b5874b2658050fc21afbdbda294f240a9d58c0"}, {"id": "SR-361", "title": "Every judge question is asked as soon as it is raised", "hash": "sha256:4002e934b7c16d0c70ffb7c0fc3feba08f739774ea70f5a90d3bbd2be759f29f"}, {"id": "SR-371", "title": "A study being written shows its progress in the band", "hash": "sha256:ceaf7de4310a0dedd56357c6e75f3dabe9c1331aa059bb893adf4a277e210d2a"}, {"id": "DEC-238", "title": "How far does the debug workflow go by itself once a case's rerun...", "hash": "sha256:0dd2e3e435652a1e327fc5500c2818ce0100a7352f20612934e40836e5df4fa0"}, {"id": "DEC-260", "title": "Does a judge job that fails open a debug case at its first...", "hash": "sha256:c980c9334cf09385f917fa98d5d796559b9e71eee6aac2a234befafa8a3c9771"}, {"id": "DEC-131", "title": "Where does the progress of long plumb work show?", "hash": "sha256:58ed4e43e056e7ac3dca839fac88790b58dd5ed3ffa48c5884954b23aa8c6253"}]
changed: "What plumb cannot settle goes to a debug workflow, the owner last, The merge is the one hold on unapproved or conflicting intent, Every judge question is asked as soon as it is raised"
refresh: ""
clips: {"one-request": {"state": "ready", "reason": "", "revisions": 1}, "debug-case": {"state": "ready", "reason": "", "revisions": 6}}
status: "opened"
---

# What plumb does, from request to landed change

plumb keeps what you asked for as small, linked records, has a judge approve them on your behalf, ties them to the code and tests that prove them, and checks all of it before anything merges. This study shows that path once, from the outside in: the shape of the records, the animated trip of one request, what happens when plumb itself gets stuck, and where you still decide.

## The records and what they point at

You never read these. They exist so plumb can answer "why is this here?" and "what did we agree?" later.

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

## What plumb does when it is stuck

plumb does not ask you about its own failures. When a judge cannot settle after its rounds, or a judge job fails three times, the case goes to a debug workflow that runs in the background (SR-220, DEC-260).

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

Watch what the debug workflow is *not* allowed to do: it may rerun a step and fix plumb on a branch, but it never changes what a record means and never approves anything. Landing on main waits for your word (DEC-238).

## Where you still decide

- Questions only you can settle: intent choices and trade-offs, asked in plain words through the question tool.
- Study depth: Markdown, diagrams or video is your press in the band, as this study was (SR-294, SR-371 shows its progress while it is written).
- Landing on main: a fix is ready on a branch; you give the word.

Long plumb work reports its step and progress where you look: the band, the status line, the terminal (SR-272), including the bar you saw while this study was being written.

Written from: SR-272 Long plumb work shows its step and progress, SR-273 plumb's model work runs as batched background jobs, SR-220 What plumb cannot settle goes to a debug workflow, the owner last, SR-245 With no judge reachable, plumb says so once and holds only what..., SR-260 The merge is the one hold on unapproved or conflicting intent, SR-291 The band shows the intent loop's step and the step's progress, SR-294 A new study is announced in plumb's colours, never forced open, SR-361 Every judge question is asked as soon as it is raised, SR-371 A study being written shows its progress in the band, DEC-238 How far does the debug workflow go by itself once a case's rerun..., DEC-260 Does a judge job that fails open a debug case at its first..., DEC-131 Where does the progress of long plumb work show?
