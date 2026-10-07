"""Every SP6 owner-visible string, in one place (sp6 11.1, R14).

No text SP6 shows the owner names a bare ``plumb <verb>`` or any other shell command: it
names a ``/plumb`` command or the plain words to say. Lanes import these constants and
format functions and never inline owner wording; ``bare_cli_verbs`` is the test every
surface's output passes.

Phase 0 had not run when the SP6 lanes started: each lane wrote the part it needs, and the
coordinator joins them at Integrate. This is the MERGEDRIVER lane's part (sp6 7, 8, 10).
"""

from __future__ import annotations

import re

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
PREMERGE_REMOVED = "plumb: merges are no longer checked before git records them"
PREMERGE_UNCONFIRMED = "  {record} \"{title}\" is not confirmed yet; /plumb confirm {title}"
PREMERGE_UNDECLARED = ("  {path} changed without a requirement that declares it; ask the agent "
                       "to link it to the requirement it serves")
PREMERGE_COLLISION = ("  {record}: two different records hold this ID; /plumb merge-fix fixes "
                      "it")
PREMERGE_OK = "plumb: merge check: nothing holds this merge"


def conflicts_card(n: int) -> str:
    """The status card's part for open intent conflicts ("1 conflict awaits you")."""
    return (CONFLICTS_CARD if n == 1 else CONFLICTS_CARD_MANY).format(n=n)


_PLUMB_VERB = re.compile(r"(?<![/\w-])plumb[ \t]+([a-z][a-z-]*)(?![\w-]*:)")


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
_SP6_VERBS = frozenset({"merge-fix", "ids", "log", "merge-driver", "conflict", "conflicts"})
