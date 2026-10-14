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
CARD_JUDGED = "  Compatible? JEV: {verdict} ({probability:.2f}){reason}"
CARD_NO_JUDGMENT = "  Compatible? no judgment available"
CARD_UNAVAILABLE = "  Compatible? judging unavailable: {cause}"
CARD_SAY = ("  Waits on its card for the owner ({ours}'s, {theirs}'s, or combined); "
            "do not ask in words")
CARD_SAY_COMBINED = ("  Waits on its card for the owner ({ours}'s, {theirs}'s, or the "
                     "combined one); do not ask in words")
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
PREMERGE_UNCONFIRMED = "  {record} \"{title}\" is not confirmed yet; /plumb approve {record}"
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

# -- the plugin (SP7 4, SR-082 to SR-084)
INIT_DONE = ("plumb now follows this repository. It will show what you asked for, keep the work "
             "tied to it and check merges and pushes.")
COMMIT_MSG_INSTALLED = ("plumb: each commit is checked for the requirement it says it serves")
FOREIGN_COMMIT_MSG_HOOK = ("plumb: your own commit-msg hook was kept; say \"call plumb from my "
                           "commit-msg hook\" to add the check of the requirement each commit "
                           "serves")
NOT_ADOPTED = "/plumb:plumb init to adopt this repository"
GETTING_READY = ("plumb is getting ready for its first run; it will follow this session from "
                 "your next message")
NEEDS_PYTHON = ("plumb needs Python 3.12 on this machine; say 'install what plumb needs' and I "
                "will set it up")
OLD_INSTALL = ("plumb is set up here the old way; say 'move plumb to the plugin' to switch")
IGNORED = ("plumb will stay out of this repository; say 'use plumb here again' to bring it back")
UNIGNORED = "plumb will offer to follow this repository again"
MIGRATE_DONE = ("plumb now runs from the plugin here: its old settings and copies are gone, and "
                "git's checks call plumb's launcher.")
MIGRATE_KEPT = "  kept, because you changed it: {what}"
MIGRATE_KEPT_SETTINGS = "  kept, because they are yours: your own Claude Code settings"
MIGRATE_NOTHING = "plumb was not set up here the old way; nothing to move."


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
EARLY_CARD_SAY = ("  Waits on its card for the owner ({branch}'s, this one, or both); "
                  "do not ask in words")
# the same card shown on a branch that is neither side (the default branch after one side
# merged): both versions are labelled by branch, and only a branch's name answers it
EARLY_CARD_SAY_NAMED = ("  Waits on its card for the owner ({a}'s, {b}'s, or both); "
                        "do not ask in words")
EARLY_QUESTION = 'Branch {branch} says "{theirs}"; this request says "{ours}": which one, or both?'
EARLY_THEIRS = "{branch}'s version"          # every option names its branch: the answer
# words that name "this side" only from the raising branch's point of view: shown on another
# branch, they become "<raising branch>'s version"
EARLY_RELATIVE = ("this request's version", "this request", "this work's version", "this work",
                  "this one", "keep this one", "this version", "ours", "mine")
EARLY_BOTH = "both, combined"
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
# First wordings (JUDGE finishes them): the stale card, the steps of the worker and the
# gate's two choices.
STEP_READING = "reading your answer"
STEP_CHECKING = "checking your request"
STEP_JUDGING = "judging {n} records"
STEP_JUDGING_BACKLOG = "judging the backlog"
GATE_BUILD_ANYWAY = "Build anyway"
GATE_WAIT = "Wait"
GATE_BUILD_NOTE = ("Builds now without the check; what the check would have caught is not "
                   "looked at")
GATE_WAIT_NOTE = "Builds nothing until the check runs again on your next message"
GATE_CLOSED = "Waiting for your answer before building: {reason}"
NOT_AVAILABLE = "not available in this build"
CONFIRM_YOU_SAID = "you said: {evidence}"
READBACK_CHANGE = ('To be sure I have it: "{title}" should change so that {change}. Say yes, '
                   'or tell me what to fix.')
CARD_CHANGED_SINCE = ('Nothing was confirmed: "{title}" changed after I showed it to you. I am '
                      'showing you what it says now.')
TYPED_CONFIRMED = "Confirmed: {titles}"
TYPED_NEEDS_IDS = ("I could not tell which records you meant from those words alone, so they "
                   "went to the reader; I will confirm what it finds.")
TYPED_SETTLE_GONE = "That switch no longer exists; nothing changed. Records are confirmed by you, or by the judge reading your words when automatic confirmation is on."
AUTO_APPROVE_SWITCHED = "Automatic confirmation is now {state}."
AUTO_APPROVE_NOT_YET = "Automatic confirmation is switched on, but not in effect yet: {reason}."
BACKLOG_DONE = "{judged} records judged, {cards} cards waiting for you"

# -- JUDGE: the cards, the trial and the summary
DOUBT_BEYOND = ("You did not ask for {title}; Yes confirms it too, so choose Not quite to "
                "drop it")
DOUBT_CONTRADICTS = ('You confirmed {other}; {title} contradicts it. Yes confirms {title} too, '
                     "so choose Not quite to keep only {other}")
DOUBT_CONTRADICTS_UNNAMED = ("{title} contradicts something you said. Yes confirms it too, so "
                             "choose Not quite to drop it")
BEYOND_KEEP = "Keep it: this is what I meant"
BEYOND_DROP = "Drop it"
BEYOND_REWORD = "Reword it (say how)"
BACKLOG_STARTED = ("Judging the backlog: {records} records are queued in {jobs} groups; the status "
                   "line shows how far it is.")
BACKLOG_NOTHING = "Nothing in the backlog is left to judge."
EXAMPLE_N = "example {n}"
COULDNT_CHECK_ISSUE = "the check did not finish; I will try again on your next message"
READBACK_YES = "Yes, that is it"
READBACK_NOT_QUITE = "Not quite"


_PLUMB_VERB = re.compile(r"(?<![\w/.:-])plumb[ \t]+([a-z][a-z-]*)(?![\w-]*:)")


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


# --------------------------------------------------------------------------- SP8 STALE
# The stale-link card (SR-111): what the owner reads when what they confirmed may have changed
# and the agent could not settle it alone. Titles, never record IDs; no commands.
STALE_ISSUE_CODE = ('{path} changed after you confirmed "{title}", and I could not settle '
                    "whether it still does what you asked")
STALE_ISSUE_RECORD = ('"{title}" rests on "{other}", which was reworded since, and I could '
                      "not settle whether the two still agree")
STALE_OPTION_KEEP = "Keep the wording as it is"
STALE_OPTION_REWORD = "Reword it to match the change"
STALE_OPTION_UNDO = "Undo the change"
# SR-116: what each default option does and leaves undone, and why the first is recommended
STALE_CONSEQUENCE_KEEP = ("Keeps the requirement as it reads and the change as made; leaves "
                          "unchecked whether the change still does what the requirement says")
STALE_CONSEQUENCE_REWORD = ("Rewrites the requirement to say what the code now does; keeps the "
                            "change and drops what the old wording promised")
STALE_CONSEQUENCE_UNDO = ("Puts the code back as it was when you confirmed the requirement; "
                          "keeps the wording and drops whatever the change was for")
STALE_WHY_KEEP = ("I could not tell whether the change matters to what you asked; keeping both "
                  "as they are changes nothing while you read the change shown with this card")
STALE_HOLD_ENDED = ('I held the turn open {n} times for "{title}" and then let it go; it waits '
                    "for your answer below.")


# --------------------------------------------------------------------------- SP7 slice 3
# Cards only at the end of a turn (sp7-realign-sp8 C1, C7, C8; SR-012, SR-116): the kinds the
# stop hook drew its own way, and what every card shows so the owner can choose without asking
# back. Titles, never record IDs; no commands.

REGRESSION_ISSUE = "a test that passed before now fails: {what}"
REGRESSION_FIX = "Fix the code so it passes again"
REGRESSION_CHANGE = "The test is wrong now: change it (say how)"
REGRESSION_WAIT = "Leave it failing for now"
REGRESSION_EVIDENCE = "{test} passed in an earlier run and fails now{note}"
REGRESSION_TEST_CHANGED = " (the test itself was changed since it passed)"
REGRESSION_LAST_RUN = " (last run {run})"
REGRESSION_HIDDEN = ("{test} passed, then failed, and passes now only because the test itself "
                     "was changed")

# SR-030: a confirmed requirement whose acceptance test changed since the owner confirmed it
TEST_CHANGED_ISSUE = ("the test that checks it was changed since you confirmed it: {tests}; is "
                      "the new test right?")
TEST_CHANGED_SAYS = "What you confirmed: {text}"
TEST_CHANGED_EXAMPLES = "Cases the test checks: {text}"
TEST_CHANGED_RESTORE = "Put the test back as you confirmed it"
TEST_CHANGED_KEEP = "The new test is right: confirm it"
TEST_CHANGED_LATER = "Leave it for now"


CONFLICT_ISSUE = "{ours} and {theirs} changed it in different ways"
CONFLICT_SIDE = "{side} says: {text}"
EARLY_TYPED_CHOOSE = ('To answer, type: /plumb conflict choose "{title}" --take '
                      "<{branch} | {ours} | both>")
EARLY_ISSUE = '{branch} says "{theirs}"; {label} says "{ours}"'

DRIFT_REQUEST = 'the request behind the change: "{text}" ({at})'
DRIFT_NO_REQUEST = "the request behind the change is not on file"


# the parts of every card (SR-129): each option, the recommended one marked, what it does
FULL_OPTION = "  {n}. {text}{mark}"
FULL_RECOMMENDED = " (recommended)"
FULL_CONSEQUENCE = " - {text}"
FULL_DIAGRAM = "Diagram: {path} (open it to see it)"
FULL_NOT_DRAWN = ("{n} more cards wait for you; there was no time left to draw them in full "
                  "this turn: {topics}")
FULL_INCOMPLETE = ("{n} cards wait until the agent writes what each option does and why one is "
                   "recommended; they stay open and are shown once complete.")
# SR-161: the one line at a turn end naming the cards plumb withdrew, and why
CARDS_WITHDRAWN = "Withdrawn: {items}"
WITHDRAWN_LINK_CURRENT = "its link is current again"
WITHDRAWN_LINK_GONE = "its link no longer exists"
WITHDRAWN_SUPERSEDED = "{ids} is superseded"
WITHDRAWN_CONFIRMED = "you confirmed what it asked about"
# SR-162: the tidy job's reasons, its step and the line when it could not run
STEP_TIDYING = "checking your open questions"
TIDY_ANSWERED = 'you confirmed {record}: "{quote}"'
TIDY_DUPLICATE = 'it asks what "{other}" asks'
TIDY_COULD_NOT_RUN = "I could not check whether your open questions are already answered; they all stay."
# SR-116 EX-4: what the agent is told at the next prompt when cards were shown at turn end
CARDS_WAITING_AGENT = ("plumb: {n} cards were shown to the owner at the end of the last turn "
                       "and await their answer ({topics}). If you mention them, say in one line "
                       "that cards are waiting; do not restate them or ask the owner to answer "
                       "them in prose.")

# --------------------------------------------------------------------------- SP7 PRESS
# What a button press on a card answers (sp7-realign-sp8 C3, C6; DEC-032, DEC-034). Titles,
# never record IDs; no commands.
BUTTON_ASK_CHANGE = "Ask for a change"
BUTTON_LEAVE_OPEN = "Leave open"
PRESS_PREFILL = "Change to '{topic}': "
PRESS_CONFIRMED = 'You pressed {label}: now confirmed: {titles}.'
PRESS_REJECTED = 'You pressed {label}: dropped: {titles}.'
# a trial No (a misreading, SR-124): plumb's reading is marked wrong; the record is not dropped
PRESS_MISREAD = ("You pressed {label}: plumb's reading of {titles} is marked wrong; the record "
                 "stays as it is.")
PRESS_LEFT_OPEN = ('Left open: "{topic}". It stops coming back at the end of each turn until '
                   "it changes; it stays listed under what awaits you.")
PRESS_CHANGE = 'Say what to change about "{topic}"; your next message is read against it.'
PRESS_ANSWERED = 'You pressed {label} on "{topic}".'
PRESS_CHANGED_SINCE = '"{title}" changed since it was shown; nothing was confirmed.'
PRESS_ALREADY = '"{topic}" was already answered; nothing changed.'
PRESS_MODEL_CONFIRMED = ("The owner pressed {label}; now confirmed: {records}. Do not ask "
                         "again.")
PRESS_MODEL_REJECTED = "The owner pressed {label}; dropped: {records}."
PRESS_MODEL_MISREAD = ("The owner pressed {label}; plumb's reading of {records} is marked wrong. "
                       "The record stays: do not remove or rewrite it.")
PRESS_MODEL_LEFT_OPEN = ('The owner pressed Leave open on "{topic}". Do not ask about it '
                         "again until it changes.")
PRESS_MODEL_CHANGE = ('The owner pressed Ask for a change on "{topic}"; their next message '
                      "says what to change.")
PRESS_MODEL_ANSWERED = 'The owner pressed {label} on "{topic}".'
PRESS_MODEL_CHANGED = ("The owner pressed {label}, but {records} changed since it was shown; "
                       "nothing was confirmed and the new version is shown as a fresh card.")

# --------------------------------------------------------------------------- SP7 MOD
# What plumb's panel adds (SP7 5.1, 5.8; sp7-realign-sp8 C6, C7).
