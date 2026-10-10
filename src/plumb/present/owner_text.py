"""Every SP6 owner-visible string, in one place: the R14 choke point (sp6 11.1).

No text SP6 shows the owner names a bare ``plumb <verb>`` or any other shell command: it
names a ``/plumb`` command or the plain words to say. Lanes import these constants and
format functions and never inline owner wording; ``bare_cli_verbs`` is the test every
surface's output passes. Each lane's constants sit under its own heading.
"""

from __future__ import annotations

import re

# -- LOGS (sp6 6)
# 6.5, 10: the warning in plumb validate and in the merge report while legacy lines remain
LEGACY_LOG = ("plumb: {n} log entries are still in the old format (say \"migrate the logs\", "
              "or /plumb migrate the logs)")

# -- IDS (sp6 4, 5, 10)
ID_UNRESERVED = ("plumb: {ids} is not reserved (no git repository); /plumb merge-fix fixes "
                 "a collision later")
ID_BUSY = ("plumb: could not reserve an ID (another session is creating records); try again "
           "in a moment")
RENUMBERED = ("plumb: {old} \"{title}\" from the merged branch is now {new} ({references} "
              "references in {files} files; {approval}; {commits} commits' trailers mapped)")
APPROVAL_CARRIED = "the owner's approval carried"
APPROVAL_NONE = "no approval to carry"
COLLISION = ("  {id}: \"{ours}\" and \"{theirs}\" hold one ID ({where}); /plumb merge-fix "
             "fixes it")
COLLISIONS_HEADER = "ID collisions hold the merge (two records with one ID):"
NOTHING_TO_FIX = "plumb: no ID collision; nothing to fix"
WOULD_RENUMBER = "plumb: {old} \"{title}\" from the merged branch would become {new}"
FIX_REMAINS = ("plumb: {id} still has two records ({where}); say \"keep mine\" or \"keep "
               "theirs\" for it, then /plumb merge-fix")
FIX_BLOCKED = ("plumb: {id} \"{title}\" is not renumbered yet: {files} files that name it "
               "still hold merge conflicts; resolve them, then /plumb merge-fix")
PREVIEW = ("plumb: merging {ref} would bring {id} \"{theirs}\" while this branch holds {id} "
           "\"{ours}\"; /plumb merge-fix renumbers it after the merge")
# R17: an "ok" carried across a renumber is labelled wherever the confirmation is shown
CARRIED = "carried by renumber {old} -> {new}"
CARRIED_GLANCE = ("  carried by renumber {old} -> {new} \"{title}\": the owner's earlier ok of "
                  "these exact words (say \"revoke {new}\" if you did not mean it)")


def carried(old: str, new: str) -> str:
    return CARRIED.format(old=old, new=new)

# -- MERGEDRIVER: the driver's stderr, which git shows during the merge (7.4 to 7.6)
MERGED_FIELDS = "plumb: {record} \"{title}\" merged field by field ({what})"
CONFLICT_WRITTEN = ("plumb: {record} \"{title}\" was changed differently on {ours} and "
                    "{theirs}; it waits for your choice (/plumb conflicts)")
ADD_ADD = ("plumb: {record} was created on both sides as different records; /plumb merge-fix "
           "renumbers the incoming one")
UNPARSABLE = ("plumb: the record file of {record} \"{title}\" holds both versions of a text "
              "merge; say \"keep mine\" or \"keep theirs\" for it")
STILL_OPEN = ("plumb: {record} \"{title}\" still waits for your choice on an earlier conflict "
              "and was changed again on {ours} and {theirs}; git keeps both versions of it: "
              "say \"keep mine\" or \"keep theirs\" for it")
NO_DRIVER = ("plumb: the record file of {record} \"{title}\" was merged as plain text; "
             "/plumb init installs the record merge")

# -- the hooks status line of the driver (7.1)
DRIVER_STATUS = "merge driver: {state}"
DRIVER_MISSING = " (/plumb init installs it)"
DRIVER_INSTALLED = "installed"
DRIVER_NOT_INSTALLED = "not installed"
DRIVER_HALF = "attribute without driver"

# -- the merge report's unmerged section (8.5, 7.6, 10)
UNMERGED_HEADER = "record files git left unmerged hold the merge:"
MODIFY_DELETE = ("  {record} \"{title}\" was changed on {changed} and removed on {removed}; "
                 "say \"keep the changed one\" or \"keep it removed\"")

# -- the conflict card (8.3), wherever it appears
CARD_HEAD = "▸ Conflict  {ic} on {record} \"{title}\"   (awaits your choice)"
CARD_FIELD = "  {name}:"
CARD_MERGED = "  Merged on their own: {what}"
CARD_COMBINED = "  combined (proposed)"
CARD_JUDGED = "  Compatible? JEV: {verdict} ({probability:.2f}){reason}"
CARD_NO_JUDGMENT = "  Compatible? no judgment available"
CARD_SAY = "  Say: \"keep {ours}'s\", \"keep {theirs}'s\", or how to combine them"
CARD_SAY_COMBINED = ("  Say: \"keep {ours}'s\", \"keep {theirs}'s\", \"ok, the combined one\", "
                     "or how to combine them")
CONFLICTS_HEADER = "intent conflicts wait for your choice (/plumb conflicts):"
NO_CONFLICTS = "plumb: no intent conflict waits for you"
CONFLICTS_BRIEF = "plumb: {n} intent conflict(s) await your choice (/plumb conflicts)"
CONFLICTS_CARD = "{n} conflict awaits you"
CONFLICTS_CARD_MANY = "{n} conflicts await you"

# -- choosing a side (8.4)
CHOOSE_REFUSED = ("plumb: only the owner chooses a side; say which version to keep (for "
                  "example \"keep {theirs}'s\")")
CHOSEN = "plumb: {record} \"{title}\" now holds {side} version"
CHOSEN_RECONFIRMED = " (your earlier ok of that version holds again)"
CHOSEN_PROPOSED = " (it waits for your ok, like any new wording)"
PROPOSED = ("plumb: a combined version of {record} \"{title}\" is shown in its conflict card; "
            "nothing changes until you choose")

# -- the merge-time check and its hook (10, R17)
MERGE_HELD = ("plumb: the merge is not recorded yet; once this is settled, say \"finish the "
              "merge\"")
FOREIGN_HOOK = ("plumb: your own pre-merge-commit hook was kept; say \"call plumb from my merge "
                "hook\" to add it")
PREMERGE_INSTALLED = ("plumb: merges are checked before git records them (a quick check, no "
                      "test run; the full test run happens when you push)")
PREPUSH_INSTALLED = ("plumb: pushes run the full test run once before git sends them (the "
                     "one full run; merges stay quick)")
FOREIGN_PREPUSH_HOOK = ("plumb: your own pre-push hook was kept; say \"call plumb from my push "
                        "hook\" to add the full test run to it")
COMMIT_HOLD_INSTALLED = ("plumb: merges finished by hand, rebases and cherry-picks get the same "
                         "quick check before git records them")
PREMERGE_REMOVED = "plumb: merges are no longer checked before git records them"
PREMERGE_UNCONFIRMED = "  {record} \"{title}\" is not confirmed yet; /plumb confirm {title}"
PREMERGE_UNDECLARED = ("  {path} changed without a requirement that declares it; ask the agent "
                       "to link it to the requirement it serves")
PREMERGE_COLLISION = ("  {record}: two different records hold this ID; /plumb merge-fix fixes "
                      "it")
PREMERGE_OK = "plumb: merge check: nothing holds this merge"
FOREIGN_COMMIT_HOOK = ("plumb: your own prepare-commit-msg hook was kept; say \"call plumb from "
                       "my commit hook\" to add the check of merges finished by hand, rebases "
                       "and cherry-picks")
PREMERGE_UNSTAGED_HEADER = "plumb's files changed but are not part of what git will record:"
PREMERGE_UNSTAGED = "  {path} is left out; say \"{finish}\" to include it"
PREMERGE_UNREADABLE_HEADER = "records plumb cannot read, so it cannot check them:"
STEP_HELD = ("plumb: this {operation} step is not recorded yet; once this is settled, say "
             "\"continue the {operation}\"")
STEP_OK = "plumb: {operation} check: nothing holds this step"
# R17 at a fast-forward (no merge commit, so git runs no pre-merge-commit hook): the
# post-merge hook checks what came in and puts the default branch back when it holds
FF_HEADER = ("plumb: quick merge check (no test run): {merging} into {into} (git moved {into} "
             "straight to it, without a merge commit)")
FF_UNDONE = ("plumb: so {into} was put back where it was and nothing is recorded yet; say "
             "\"merge {merging}\" to bring it in as a merge that waits until this is settled")
FF_NOT_UNDONE = ("plumb: {into} could not be put back ({why}); say \"undo the merge of "
                 "{merging}\" before anything else")
FOREIGN_POST_HOOK = ("plumb: your own post-merge hook was kept; say \"call plumb from my "
                     "post-merge hook\" so a fast-forward of the main branch is checked too")
POST_HOOK_INSTALLED = ("plumb: a fast-forward of the main branch gets the same quick check "
                       "(it is put back when the check holds)")
FF_HOLD_SET = ("plumb: merges into {branch} always record a merge commit, so the quick check "
               "sees every one")
FF_HOLD_REMOVED = "plumb: merges into {branch} may fast-forward again"


def conflicts_card(n: int) -> str:
    """The status card's part for open intent conflicts ("1 conflict awaits you")."""
    return (CONFLICTS_CARD if n == 1 else CONFLICTS_CARD_MANY).format(n=n)

# -- AWARENESS (sp6 9.4, SR-078): one line per record another worktree or branch changes
OVERLAP = 'plumb: {id} "{title}" is also being changed on branch {branch}'
OVERLAP_WORKTREE = " (worktree {worktree})"
OVERLAP_CLAIMED = ' (intent in flight there: "{summary}")'
MORE_OVERLAPS = "plumb: +{n} more also being changed elsewhere (/plumb status)"
OVERLAP_CARD = "{n} also changed on {labels}"
OVERLAP_CARD_ASCII = "overlap {n} ({labels})"
# R17: a change that already landed on the default branch after this branch started from
# it (its claim cleared there, but this branch still holds the words it replaced)
OVERLAP_SINCE_FORK = ('plumb: {id} "{title}" was changed on {branch} after this branch '
                      "started from it; build on {branch}'s words, or ask the owner which "
                      "holds before changing it here")
SINCE_FORK_SUMMARY = "changed there after this branch started"
CONFLICTS_CARD_PLURAL = CONFLICTS_CARD_MANY
STATUS_OVERLAPS_HEADER = "also being changed elsewhere (ask \"is anyone else changing X?\"):"
STATUS_NO_OVERLAPS = "also being changed elsewhere: nothing"

# -- intent in flight (ruling R17, SR-080, SR-081): the early intent-conflict card
EARLY_CARD_HEAD = '▸ Conflict  {id} "{title}"   (awaits your choice, before any work)'
EARLY_CARD_SIDE = "  {label:<10}  {text}"
EARLY_CARD_JUDGED = "  Compatible? {judgment}"
EARLY_CARD_SAME = "the same requirement is being changed on both branches"
EARLY_CARD_SAY = ('  Say: "keep {branch}\'s", "keep this one", or "both" (and how they '
                  "combine)")
# the same card shown on a branch that is neither side (the default branch after one side
# merged): both versions are labelled by branch, and only a branch's name answers it
EARLY_CARD_SAY_NAMED = ('  Say: "keep {a}\'s", "keep {b}\'s", or "both" (and how they '
                        "combine)")
EARLY_QUESTION = 'Branch {branch} says "{theirs}"; this request says "{ours}": which one, or both?'
EARLY_THEIRS = "{branch}'s version"          # every option names its branch: the answer
EARLY_CHOSEN = EARLY_THEIRS                   # reads the same on every branch (R17)
# words that name "this side" only from the raising branch's point of view: shown on another
# branch, they become "<raising branch>'s version"
EARLY_RELATIVE = ("this request's version", "this request", "this work's version", "this work",
                  "this one", "keep this one", "this version", "ours", "mine")
EARLY_BOTH = "both, combined"
EARLY_RECORDED = ("plumb: asked once for every branch working on {id} \"{title}\"; the answer "
                  "settles it there too")
EARLY_ASK = ("plumb: {dec} holds that question for the agent: show the card above and ask the "
             "owner now, before any implementation; the owner's own words (\"keep ...'s\", "
             "\"keep this one\" or \"both\") answer it as they are (relay them as the "
             "answer to {dec}), then build on the answer")
EARLY_KNOWN = ('plumb: {id} "{title}": the owner is asked on branch {branch} whether this work '
               "or that branch's holds; build on the answer")
EARLY_SETTLED = ('plumb: {id} "{title}": the owner settled it on branch {branch}: "{chosen}"; '
                 "build on that")
EARLY_COMPATIBLE = ('plumb: {id} "{title}" shares its feature with intent in flight on branch '
                    '{branch} ("{summary}"); judged compatible, nothing to ask')
# R12/R17: only a confident JEV verdict may say "compatible"; a word check or an unsure
# verdict names both versions and leaves the call to the agent's reading
EARLY_UNJUDGED = ('plumb: {id} "{title}" shares its feature with intent in flight on branch '
                  '{branch}; whether they agree could not be judged ({who}): {branch} says '
                  '"{theirs}"; this says "{ours}". If they differ, show the owner both and ask '
                  "which holds, or both")
# the owner's answer to an early conflict card, once recorded (answer.record_answer)
EARLY_ANSWERED = ('plumb: {id} "{title}": your answer is recorded: {chosen}; every branch '
                  "working on it builds on that")
# a merge-time conflict the owner already answered before work began (answer.apply_settled)
# R17, the losing lane: this checkout's record still holds the version the owner turned down
EARLY_SUPERSEDED = ('plumb: {id} "{title}" here still says "{ours}", but the owner chose '
                    '{chosen}: "{theirs}"; change it to match that answer before building on it')
EARLY_SUPERSEDED_RELAY = ('{id} "{title}" still holds the version the owner turned down when '
                          'answering {dec} (the owner chose {chosen}: "{theirs}"); an ok does '
                          "not confirm it: change it to match that answer first, or show the "
                          "owner that conflict again and relay the new pick as the answer to "
                          "{dec}")
EARLY_APPLIED = ('plumb: {id} "{title}" now holds {chosen}, as you answered before work '
                 'began; nothing to ask again (say "finish the merge" to record it)')
CARD_SETTLED = ("  Already answered by you before work began: {chosen} ({side}'s side); "
                "nothing to choose again")
# the state of an early-conflict decision's card (a DEC that asks which version holds)
EARLY_DEC_STATE = "awaits your choice — {say}"
EARLY_DRY_RUN = "plumb: nothing recorded (a preview)"
INFLIGHT_BUSY = ("plumb: could not record this work's intent for the other branches (another "
                 "session is recording at the same moment); it is retried at the end of the "
                 "turn")
INFLIGHT_NONE = "intent in flight on other branches: none"
INFLIGHT_HEADER = "intent in flight on other branches:"
INFLIGHT_LINE = '  {branch}: "{summary}" ({records})'


# --------------------------------------------------------------------------- SP8 UNDERSTAND
# First wordings (JUDGE finishes them): the six card kinds, the settled line, the steps of the
# worker, the gate's two choices and the reply that names the settle switch and the buttons.
CARD_CLARIFY = 'Before I build this, one question about "{topic}": {issue}'
CARD_TRIAL = 'A trial run on "{topic}": {issue}'
CARD_BACKLOG = 'An older record to look at again, "{topic}": {issue}'
CARD_BEYOND = 'This goes beyond your words, "{topic}": {issue}'
CARD_CONTRADICTS = 'This seems to contradict what you said, "{topic}": {issue}'
CARD_COULDNT_CHECK = 'I could not check "{topic}": {issue}'
CARD_STALE_LINK = 'Something you confirmed may have changed, "{topic}": {issue}'
CARD_EVIDENCE = "  Evidence: {evidence}"
CARD_RESOLUTION = "  {n}. {text}"
SETTLED_LINE = "Settled from your words: {titles}"
SETTLED_GLANCE = "settled from your words"
SETTLED_COUNT = "{n} settled from your words"
SETTLED_UNDO ="{title} (say undo to take it back)"
STEP_READING = "reading your answer"
STEP_CHECKING = "checking your request"
STEP_JUDGING = "judging {n} records"
STEP_JUDGING_BACKLOG = "judging the backlog"
GATE_BUILD_ANYWAY = "Build anyway"
GATE_WAIT = "Wait"
GATE_CLOSED = "Waiting for your answer before building: {reason}"
SETTLE_REPLY = ('Settling is {state}. Say "settle on" to let confirmed wording settle by '
                'itself, "undo" to take a settled record back, or use the buttons.')
NOT_AVAILABLE = "not available in this build"
CONFIRM_YOU_SAID = "you said: {evidence}"
READBACK_CHANGE = ('To be sure I have it: "{title}" should change so that {change}. Say yes, '
                   'or tell me what to fix.')
CARD_SHOW_FIRST = 'Look at this first, "{topic}": {issue}'
TYPED_CONFIRMED = "Confirmed: {titles}"
TYPED_NEEDS_IDS = ("I could not tell which records you meant from those words alone, so they "
                   "went to the reader; I will confirm what it finds.")
OWNER_ONLY_REPLY = ("Nothing changed: saying that in a message does not {action}. Use the "
                    "button, or type {command}.")
BACKLOG_DONE = "{judged} records judged, {cards} cards waiting for you"

# -- JUDGE: the cards, the trial and the summary
TRIAL_ISSUE = "plumb would settle {what} from your words; is that right?"
TRIAL_ISSUE_ONE = "plumb would settle this from your words; is that right?"
TRIAL_BELOW = "plumb would not settle this; right?"
TRIAL_ONE_BELOW = "One of them (the last) is one it would not settle."
CONFIRM_ISSUE = "this one is always asked on its own, never settled for you; is it what you meant?"
OPTION_ISSUE = "you picked one option among several; is it what you meant?"
EDIT_ISSUE = "you had confirmed this and it was changed; is the new wording what you mean?"
TRIAL_YES = "Yes, that is what I meant"
TRIAL_NO = "No, that is not what I meant"
BEYOND_KEEP = "Keep it: this is what I meant"
BEYOND_DROP = "Drop it"
BEYOND_REWORD = "Reword it (say how)"
CONTRADICTS_KEEP_OLD = "Keep what you confirmed before"
CONTRADICTS_KEEP_NEW = "Keep the new wording"
CONTRADICTS_COMBINE = "Combine them (say how)"
BACKLOG_FEATURE = "these {n} about {topic} would be settled; right?"
BACKLOG_FEATURE_TOPIC = "{topic}"
BACKLOG_YES = "Yes, all of them"
BACKLOG_EXCEPT = "Yes, except the ones I name"
BACKLOG_NO = "No, none of them"
NO_ORIGINAL_WORDS = ("your original words are not on file for this one; here is how it reads "
                     "now: {readback}")
NO_ORIGINAL_ACCEPT = "Accept it as it reads"
NO_ORIGINAL_CORRECT = "Correct it (say how)"
EXAMPLE_N = "example {n}"
COULDNT_CHECK_ISSUE = "the check did not finish ({step}); I will try again on your next message"
COULDNT_CHECK_WAIT = "Wait for the check"
COULDNT_CHECK_GO = "Build anyway"
SETTLED_UNDO_LINE = "{title} (Undo)"
SETTLED_HOW = ("To take one back, use its Undo button or type /plumb undo followed by its "
               "title.")
SETTLE_OFFER_INTENT = ("plumb can now settle your intent read-backs from your words when it is "
                       "sure. It is off until you turn it on: type /plumb settle on intent or "
                       "use the button. You can turn it off the same way.")
SETTLE_ON_REQUIREMENTS = ("plumb now settles requirements and their examples from your words "
                          "when it is sure, and tells you in one line each turn. To switch it "
                          "off, type /plumb settle off requirement or use the button.")
SETTLE_SWITCHED = "Settling for {kind} is now {state}."
SETTLE_STATE_LINE = "Settling for {kind}: {state}"
SETTLE_REFUSED_PROSE = ("Nothing changed: saying that in a message does not switch settling. "
                        "Use the button, or type /plumb settle {state} {kind}.")
SETTLE_REFUSED_AGENT = ("Only you switch settling, from the button or by typing /plumb settle "
                        "{state} {kind} yourself.")
UNDO_DONE = "{title} is proposed again and waits for you."
UNDO_REFUSED = ("Only you undo a settled record: use its Undo button, or type /plumb undo "
                "followed by its title.")
UNDO_UNKNOWN = "Nothing settled is called \"{what}\"."


_PLUMB_VERB = re.compile(r"(?<![\w/.-])plumb[ \t]+([a-z][a-z-]*)(?![\w-]*:)")


def bare_cli_verbs(text: str) -> list[str]:
    """Every ``plumb <verb>`` in ``text`` whose verb is a CLI route, not preceded by ``/``
    and not directly followed by ``:`` (so ``/plumb merge-fix`` and the label "plumb log:
    not available" pass, while ``plumb merge-fix`` and ``uv run plumb log migrate`` do
    not)."""
    from plumb.cli import ROUTES

    out: list[str] = []
    for match in _PLUMB_VERB.finditer(text):
        verb = match.group(1)
        if verb in ROUTES or verb in _SP6_VERBS:
            out.append(f"plumb {verb}")
    return out


# the SP6 verbs, recognised even before their routes exist in this build
_SP6_VERBS = frozenset({"merge-fix", "ids", "log", "merge-driver", "conflict", "conflicts",
                        "inflight"})
