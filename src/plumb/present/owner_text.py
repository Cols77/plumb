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
_SP6_VERBS = frozenset({"merge-fix", "ids", "log", "merge-driver", "conflict", "conflicts"})
