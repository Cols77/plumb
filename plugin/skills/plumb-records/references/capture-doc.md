# The capture document and the drafted questions

## `plumb capture --prompt <digest> --file doc.json`

One call records the read-back of a request: the intent (INT), its requirements (SR) with
given/when/then examples, and the decisions (DEC), all proposed and linked. `<digest>` is the
sha256 of the owner's message: `message_digest` in `plumb clarify --wait --json`.

```json
{
  "intent": {"quote": "add multiply next to add",
             "readback": "Add multiply beside add",
             "will": ["multiply(a, b) returns a * b"],
             "wont": ["no floats yet"],
             "assumptions": ["integers only, like add"]},
  "requirements": [{"title": "multiply returns the product",
                    "statement": "multiply(a, b) returns a * b",
                    "examples": [{"given": "a = 2 and b = 3", "when": "multiply runs",
                                  "then": "it returns 6", "quote": "2 times 3 is 6"},
                                 {"given": "a = 0", "when": "multiply runs",
                                  "then": "it returns 0"}],
                    "implemented_by": ["src/calc.py"],
                    "proof": {"plan": "run multiply 2 3 and see 6", "kind": "command"}}],
  "decisions": [{"question": "Floats too?", "chosen": "integers only",
                 "alternatives": ["floats too"], "matters": true,
                 "recommended": "integers only", "decides": ["#1"]}]
}
```

- `quote` is the owner's words, verbatim; an example's `quote` is the words it rests on.
- Give edge cases their own examples (here `a = 0`).
- `proof` is how the owner will see it working, matched to what changed: `kind` is
  `live-session` (anything drawn on screen), `hook`, `command` or `other`. Record the evidence
  once shown: `plumb proof SR-### --evidence <path> --summary "..." --passed`.
- `supersedes: ["SR-076"]` on a requirement retires existing requirements the new one replaces
  (a `supersedes` link; capture names the old one's still-tested examples, so move them with
  `updates` first). Capture also names live requirements the new ones contradict or may change.
- `implemented_by` names the paths the requirement changes; `decides: ["#1"]` points at the
  first requirement of this document.
- An escalated request sets `"mode": "escalated"` in `intent`; then show
  `plumb spec show INT-###`.

## `plumb clarify "<the request>" --questions q.json`

The questions you drafted, ranked by whether their answer changes what gets built; those the
records or a default already answer are dropped. Ask the first, one per message.

```json
[
  {"question": "Which formats can users export?",
   "options": [{"label": "CSV only", "will": ["export as CSV"]},
               {"label": "CSV and JSON", "will": ["export as CSV", "export as JSON"]}],
   "recommended": "CSV only"},
  {"question": "Who can export?",
   "options": ["each user, their own data", "admins, everyone's"],
   "recommended": "each user, their own data"}
]
```

An option is a label, or `{label, will, wont}` saying what it builds: two options that build
the same thing make the question not matter.
