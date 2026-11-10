# What `clarify --wait` answers

On any message, after you record it as proposed (`capture`), run
`iaso clarify --wait --json` and act on its answer. On an ordinary message iaso checks
nothing of the request itself (read it back in your own reply, see Depth): the answer is
`ask` with iaso's judge's questions on what you recorded, or `ready` with what the judge
approved on the owner's behalf. When the owner types `/iaso clarify <words>`, your
first action is `iaso clarify --wait`. Run it before you read code, plan or edit
anything: edits are refused until it has answered, and do not build until the owner has
answered any question it returns. It collects the check iaso started on the
owner's message and says which of these things happened:

- ready (nothing blocks the request, or it was only a question or an answer): go ahead. When
  it lists what it assumed, build on that and tell the owner in one line what you assumed;
  they flip an assumption by saying so.
- ask (iaso's judge has questions about what the owner meant): put them to the owner as
  iaso-records says, then run `iaso clarify --wait --json` again after their answers.
  Ask no more than it gives. An option "Study it in the room" or "Study it first" is the
  owner's to take: they answer it by pressing the band's line that follows, and you open
  nothing.
- couldn't check: when the check failed (no judge reachable), say so once in one line and
  work on; nothing is held and nothing is decided by rule. When it is still running, build
  nothing yet and treat it as waiting.
- waiting (the check is not finished yet): build nothing and run `iaso clarify --wait`
  again, twice at most; still waiting after that, build nothing, tell the owner the check of
  their request has not finished, and stop. On an ordinary message `waiting` means iaso's
  judge is still reading the records: go on with the work and run it again before the turn
  ends.
- held (the request changes a record the owner confirmed and no intent loop ran for it): the
  line names the record and its examples; build nothing and run `iaso intent <the owner's
  words>` to open the loop for it, or stop and say in one line that edits are held until the
  owner types `/iaso go`.

With `--json` the answer is `{state, message_digest, lines}` (and `questions` on
`ask`); `state` is `ready`, `ask`, `couldnt_check`, `waiting` or
`held`. `message_digest` is the sha256 of the owner's message: the `<digest>` that `--prompt`
takes (12 or more hex digits are enough).

Once you are past that, `iaso clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, see
../iaso-records/references/capture-doc.md) which of your drafted questions matter, ranked.
