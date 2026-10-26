# What `clarify --wait` answers

On any message, after you record it as proposed (`capture`), run
`plumb clarify --wait --json` and act on its answer. On an ordinary message plumb checks
nothing of the request itself (read it back in your own reply, see Depth): the answer is
`ask` with plumb's judge's questions on what you recorded, or `ready` with what the judge
approved on the owner's behalf. When the owner types `/plumb clarify <words>`, your
first action is `plumb clarify --wait`. Run it before you read code, plan or edit
anything: edits are refused until it has answered, and do not build until the owner has
answered any question it returns. It collects the check plumb started on the
owner's message and says which of these things happened:

- ready (nothing blocks the request, or it was only a question or an answer): go ahead. When
  it lists what it assumed, build on that and tell the owner in one line what you assumed;
  they flip an assumption by saying so.
- ask (plumb's judge has questions about what the owner meant): put them to the owner as
  plumb-records says, then run `plumb clarify --wait --json` again after their answers.
  Ask no more than it gives. An option "Study it in the room" or "Study it first" is the owner's to take: they
  answer it by pressing the band's line that follows, and you open nothing.
- a choice question (`card`: the one that blocks, because no answer is better supported; its
  recommended option comes first): ask it with the question tool as `ask` does, with the
  options as the card names them. When it names a diagram file, draw it first with the
  diagram:architecture-diagram skill (a picture of the choice, for a question about structure
  or flow). Build nothing until they answer; plumb reads their answer from the tool.
  Never answer the question yourself.
- a spec session offered (more than one question has no better-supported answer): the question
  asks whether to hold a short spec session; ask it with the question tool and stop; if they
  accept, run the escalated depth below.
- couldn't check (the check failed or took too long): ask the question tool exactly "Build
  without the check?" with two options, "Wait" and "Build anyway", and stop. Only the owner
  says to build without the check: the answer "Build anyway" (it releases the gate),
  `/plumb go` typed as their whole message, or plain words that plumb reads from their next
  message and accepts. You never release it for them. "Wait" builds nothing until the check
  runs again on their next message.
- waiting (the check is not finished yet): build nothing and run `plumb clarify --wait`
  again, twice at most; still waiting after that, build nothing, tell the owner the check of
  their request has not finished, and stop. On an ordinary message `waiting` means plumb's
  judge is still reading the records: go on with the work and run it again before the turn
  ends.
- held (the request changes a record the owner confirmed and no intent loop ran for it): the
  line names the record and its examples; build nothing and run `plumb intent <the owner's
  words>` to open the loop for it, or stop and say in one line that edits are held until the
  owner types `/plumb go`.

With `--json` the answer is `{state, message_digest, card, lines}` (and `questions` on
`ask`); `state` is `ready`, `ask`, `card`, `escalation`, `couldnt_check`, `waiting` or
`held`. `message_digest` is the sha256 of the owner's message: the `<digest>` that `--prompt`
takes (12 or more hex digits are enough).

Once you are past that, `plumb clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, see
../plumb-records/references/capture-doc.md) which of your drafted questions matter, ranked.
